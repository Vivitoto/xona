from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.db.models import Actor, ActorAlias, ActorMediaLink, MetadataRecord
from backend.app.integrations.xchina import FetchedAsset
from backend.app.schemas.actors import ActorOutputPlan
from backend.app.schemas.assets import MaterializedAsset
from backend.app.schemas.metadata import MetadataRecordData
from backend.app.schemas.source import SourceActorDetail
from backend.app.services.normalization import sanitize_path_component


OUTPUT_MODES = {"copy", "hardlink", "symlink"}
PORTRAIT_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_PORTRAIT_BYTES = 5 * 1024 * 1024


class ActorDetailAdapter(Protocol):
    async def fetch_actor_detail(self, url: str) -> SourceActorDetail:
        ...

    async def fetch_asset(self, url: str) -> FetchedAsset:
        ...


class EmbyActorClient(Protocol):
    async def find_person(self, name: str) -> dict[str, object] | None:
        ...

    async def upload_person_portrait(
        self,
        person_id: str,
        portrait_bytes: bytes,
        *,
        content_type: str,
    ) -> None:
        ...


class ActorCacheService:
    def __init__(self, session: Session, config_dir: Path | str) -> None:
        self._session = session
        self._config_dir = Path(config_dir)

    def portrait_cache_path(
        self,
        *,
        source: str,
        source_id: str | None,
        name: str,
        portrait_url: str | None,
    ) -> Path:
        key_material = source_id or portrait_url or name
        key = sanitize_path_component(source_id or hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:16])
        filename = f"{sanitize_path_component(name)}.jpg"
        return self._config_dir / "actor-cache" / sanitize_path_component(source) / key / filename

    def upsert_from_source(
        self,
        detail: SourceActorDetail,
        *,
        portrait_cache_path: Path | None = None,
        portrait_sha256: str | None = None,
        portrait_size_bytes: int | None = None,
        emby_person_id: str | None = None,
    ) -> Actor:
        actor = self._session.scalar(
            select(Actor).where(
                Actor.source == detail.source,
                Actor.source_id == detail.source_id,
            )
        )
        if actor is None:
            actor = Actor(
                canonical_name=detail.canonical_name,
                source=detail.source,
                source_id=detail.source_id,
            )
            self._session.add(actor)
            self._session.flush()
        actor.canonical_name = detail.canonical_name
        actor.profile_url = detail.profile_url
        actor.portrait_source_url = detail.portrait_url
        actor.biography = detail.biography
        actor.profile_fields = dict(detail.fields)
        actor.associated_works = list(detail.associated_works)
        actor.last_refresh_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if portrait_cache_path is not None:
            actor.portrait_cache_path = str(portrait_cache_path)
        if portrait_sha256 is not None:
            actor.portrait_sha256 = portrait_sha256
        if portrait_size_bytes is not None:
            actor.portrait_size_bytes = portrait_size_bytes
        if emby_person_id is not None:
            actor.emby_person_id = emby_person_id
        for alias in detail.aliases:
            self.add_alias(actor, alias)
        for work in detail.associated_works:
            self._add_media_link(
                actor,
                source_id=work.get("source_id"),
                title=work.get("title"),
                source_url=work.get("url"),
            )
        self._session.flush()
        return actor

    def list_actors(
        self,
        *,
        search: str | None = None,
        missing_image: bool = False,
    ) -> list[Actor]:
        actors = list(self._session.scalars(select(Actor).order_by(Actor.canonical_name)))
        if search:
            needle = " ".join(search.lower().split())
            actors = [
                actor
                for actor in actors
                if needle in actor.canonical_name.lower()
                or any(needle in alias.alias.lower() for alias in actor.aliases)
            ]
        if missing_image:
            missing_ids = {actor.id for actor in self.actors_missing_images()}
            actors = [actor for actor in actors if actor.id in missing_ids]
        return actors

    def get_actor(self, actor_id: int) -> Actor:
        return self._get_actor(actor_id)

    def set_aliases(self, actor_id: int, aliases: list[str]) -> Actor:
        actor = self._get_actor(actor_id)
        for alias in list(actor.aliases):
            self._session.delete(alias)
        actor.aliases.clear()
        self._session.flush()
        for alias in aliases:
            self.add_alias(actor, alias)
        self._session.flush()
        return actor

    def replace_portrait(
        self,
        actor_id: int,
        content: bytes,
        *,
        content_type: str,
        expected_sha256: str | None = None,
        max_bytes: int = MAX_PORTRAIT_BYTES,
    ) -> Actor:
        actor = self._get_actor(actor_id)
        normalized_content_type = content_type.split(";", 1)[0].strip().lower()
        suffix = PORTRAIT_CONTENT_TYPES.get(normalized_content_type)
        if suffix is None:
            raise ValueError("unsupported_portrait_content_type")
        if not content or len(content) > max_bytes:
            raise ValueError("invalid_portrait_size")
        digest = hashlib.sha256(content).hexdigest()
        if expected_sha256 is not None and expected_sha256.lower() != digest:
            raise ValueError("portrait_sha256_mismatch")
        cache_root = (self._config_dir / "actor-cache").resolve(strict=False)
        target = (
            cache_root
            / "local"
            / str(actor.id)
            / f"{sanitize_path_component(actor.canonical_name)}{suffix}"
        ).resolve(strict=False)
        try:
            target.relative_to(cache_root)
        except ValueError as exc:
            raise ValueError("portrait_path_escapes_cache") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        actor.portrait_cache_path = str(target)
        actor.portrait_sha256 = digest
        actor.portrait_size_bytes = len(content)
        actor.last_refresh_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self._session.flush()
        return actor

    async def refresh_actor(
        self,
        actor_id: int,
        adapter: ActorDetailAdapter,
    ) -> Actor:
        actor = self._get_actor(actor_id)
        if not actor.profile_url:
            raise ValueError("actor_profile_url_missing")
        detail = await adapter.fetch_actor_detail(actor.profile_url)
        portrait_path = None
        portrait_sha256 = None
        portrait_size = None
        if detail.portrait_url:
            fetched = await adapter.fetch_asset(detail.portrait_url)
            portrait_path = self.portrait_cache_path(
                source=detail.source,
                source_id=detail.source_id,
                name=detail.canonical_name,
                portrait_url=detail.portrait_url,
            )
            portrait_path.parent.mkdir(parents=True, exist_ok=True)
            portrait_path.write_bytes(fetched.content)
            portrait_sha256 = hashlib.sha256(fetched.content).hexdigest()
            portrait_size = len(fetched.content)
        return self.upsert_from_source(
            detail,
            portrait_cache_path=portrait_path,
            portrait_sha256=portrait_sha256,
            portrait_size_bytes=portrait_size,
            emby_person_id=actor.emby_person_id,
        )

    def linked_works(self, actor_id: int) -> list[dict[str, object]]:
        actor = self._get_actor(actor_id)
        works: list[dict[str, object]] = []
        for link in actor.media_links:
            record = (
                self._session.get(MetadataRecord, link.metadata_record_id)
                if link.metadata_record_id is not None
                else None
            )
            works.append(
                {
                    "metadata_record_id": link.metadata_record_id,
                    "source_id": link.source_id,
                    "title": link.title or (record.title if record is not None else None),
                    "source_url": link.source_url
                    or (record.source_url if record is not None else None),
                    "metadata": redact_payload(record.normalized_json)
                    if record is not None
                    else None,
                }
            )
        return works

    async def sync_emby(
        self,
        actor_id: int,
        client: EmbyActorClient,
        *,
        upload_portrait: bool,
    ) -> tuple[Actor, bool]:
        actor = self._get_actor(actor_id)
        person = await client.find_person(actor.canonical_name)
        if person is None:
            raise ValueError("emby_person_not_found")
        person_id = str(person.get("Id") or person.get("id") or "")
        if not person_id:
            raise ValueError("emby_person_id_missing")
        uploaded = False
        if upload_portrait and actor.portrait_cache_path:
            portrait_path = Path(actor.portrait_cache_path)
            if not portrait_path.is_file():
                raise ValueError("portrait_cache_missing")
            content = portrait_path.read_bytes()
            if actor.portrait_sha256 and hashlib.sha256(content).hexdigest() != actor.portrait_sha256:
                raise ValueError("portrait_cache_integrity_failed")
            await client.upload_person_portrait(
                person_id,
                content,
                content_type=_portrait_content_type(portrait_path),
            )
            uploaded = True
        actor.emby_person_id = person_id
        self._session.flush()
        return actor, uploaded

    def add_alias(self, actor: Actor, alias: str) -> ActorAlias:
        cleaned = " ".join(alias.split())
        if not cleaned or cleaned == actor.canonical_name:
            return ActorAlias(actor_id=actor.id, alias=cleaned)
        existing = self._session.scalar(
            select(ActorAlias).where(
                ActorAlias.actor_id == actor.id,
                ActorAlias.alias == cleaned,
            )
        )
        if existing is not None:
            return existing
        alias_row = ActorAlias(actor=actor, alias=cleaned)
        self._session.add(alias_row)
        self._session.flush()
        return alias_row

    def merge(self, primary_actor_id: int, duplicate_actor_id: int) -> Actor:
        if primary_actor_id == duplicate_actor_id:
            raise ValueError("Cannot merge an actor into itself")
        primary = self._get_actor(primary_actor_id)
        duplicate = self._get_actor(duplicate_actor_id)
        self.add_alias(primary, duplicate.canonical_name)
        for alias in list(duplicate.aliases):
            self.add_alias(primary, alias.alias)
            self._session.delete(alias)
        for link in list(duplicate.media_links):
            duplicate.media_links.remove(link)
            primary.media_links.append(link)
        if not primary.portrait_cache_path and duplicate.portrait_cache_path:
            primary.portrait_cache_path = duplicate.portrait_cache_path
            primary.portrait_sha256 = duplicate.portrait_sha256
            primary.portrait_size_bytes = duplicate.portrait_size_bytes
        if not primary.portrait_source_url:
            primary.portrait_source_url = duplicate.portrait_source_url
        if not primary.profile_url:
            primary.profile_url = duplicate.profile_url
        self._session.delete(duplicate)
        self._session.flush()
        return primary

    def actors_missing_images(self) -> list[Actor]:
        actors = list(self._session.scalars(select(Actor).order_by(Actor.id)))
        return [
            actor
            for actor in actors
            if not actor.portrait_cache_path
            or not Path(actor.portrait_cache_path).is_file()
            or not actor.portrait_size_bytes
        ]

    def _add_media_link(
        self,
        actor: Actor,
        *,
        source_id: str | None,
        title: str | None,
        source_url: str | None,
    ) -> ActorMediaLink | None:
        if not source_id and not title:
            return None
        existing = self._session.scalar(
            select(ActorMediaLink).where(
                ActorMediaLink.actor_id == actor.id,
                ActorMediaLink.source_id == source_id,
            )
        )
        if existing is not None:
            return existing
        link = ActorMediaLink(
            actor_id=actor.id,
            source_id=source_id,
            title=title,
            source_url=source_url,
        )
        self._session.add(link)
        return link

    def _get_actor(self, actor_id: int) -> Actor:
        actor = self._session.get(Actor, actor_id)
        if actor is None:
            raise ValueError("Actor not found")
        return actor


def plan_movie_actor_outputs(
    record: MetadataRecordData,
    materialized_assets: list[MaterializedAsset],
    *,
    movie_root: Path | str,
    mode: str = "copy",
) -> list[ActorOutputPlan]:
    if mode not in OUTPUT_MODES:
        raise ValueError(f"Unsupported actor output mode: {mode}")
    root = Path(movie_root)
    assets_by_source_id = {
        asset.actor_source_id: asset
        for asset in materialized_assets
        if asset.kind == "actor_portrait" and asset.actor_source_id
    }
    assets_by_name = {
        asset.actor_name: asset
        for asset in materialized_assets
        if asset.kind == "actor_portrait" and asset.actor_name
    }
    plans: list[ActorOutputPlan] = []
    for actor in record.actors:
        asset = None
        if actor.source_id:
            asset = assets_by_source_id.get(actor.source_id)
        asset = asset or assets_by_name.get(actor.name)
        if asset is None:
            continue
        filename = f"{sanitize_path_component(actor.name)}.jpg"
        relative_path = Path(".actors") / filename
        destination = root / relative_path
        plans.append(
            ActorOutputPlan(
                operation=mode,
                source_path=asset.cache_path,
                destination_path=destination,
                relative_path=relative_path,
                destination_inside_root=_is_relative_to(destination, root),
                actor_name=actor.name,
                actor_source_id=actor.source_id,
            )
        )
    return plans


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _portrait_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return "application/octet-stream"
