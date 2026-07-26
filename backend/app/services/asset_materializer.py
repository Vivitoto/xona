from __future__ import annotations

import hashlib
import inspect
import logging
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.db.models import AssetMaterialization
from backend.app.integrations.assets import (
    FetchedAsset,
    detect_content_type,
    normalize_content_type,
    normalize_fetched_asset,
)
from backend.app.schemas.assets import (
    AssetMaterializationPolicy,
    AssetSelection,
    LogicalAsset,
    MaterializedAsset,
    MaterializedAssetSet,
    MissingAsset,
)
from backend.app.services.normalization import sanitize_path_component

logger = logging.getLogger(__name__)
IMAGE_ASSET_KINDS = {
    "poster",
    "fanart",
    "backdrop",
    "extrafanart",
    "thumb",
    "clearlogo",
    "actor_portrait",
}


class AssetAdapter(Protocol):
    async def fetch_asset(
        self,
        url: str,
        *,
        referer_url: str | None = None,
    ) -> FetchedAsset:
        ...


class AssetMaterializer:
    def __init__(
        self,
        adapter: AssetAdapter,
        config_dir: Path | str,
        *,
        session: Session | None = None,
    ) -> None:
        self._adapter = adapter
        self._config_dir = Path(config_dir)
        self._session = session

    async def materialize(
        self,
        selection: AssetSelection,
        policy: AssetMaterializationPolicy,
        *,
        plan_id: str | None = None,
    ) -> MaterializedAssetSet:
        logger.info(
            "Asset materialization started assets=%s pre_missing=%s strict=%s plan_id=%s",
            len(selection.assets),
            len(selection.missing_required),
            policy.strict,
            plan_id,
        )
        materialized: list[MaterializedAsset] = []
        missing: list[MissingAsset] = list(selection.missing_required)

        for asset in selection.assets:
            if asset.missing_reason or (not asset.source_url and asset.inline_bytes is None):
                missing.append(_missing(asset, asset.missing_reason or "missing_source_url"))
                continue

            cached = self._cached_asset(asset, policy)
            if cached is not None:
                if isinstance(cached, str):
                    logger.warning(
                        "Asset cache rejected kind=%s relative_path=%s reason=%s",
                        asset.kind,
                        asset.relative_path,
                        cached,
                    )
                    missing.append(_missing(asset, cached))
                    continue
                logger.info(
                    "Asset cache hit kind=%s relative_path=%s size=%s",
                    cached.kind,
                    cached.relative_path,
                    cached.size_bytes,
                )
                materialized.append(cached)
                continue

            result = await self._download_or_inline(asset, policy)
            if isinstance(result, MissingAsset):
                missing.append(result)
                self._record_refusal(asset, result.reason)
                logger.warning(
                    "Asset materialization refused kind=%s relative_path=%s reason=%s",
                    asset.kind,
                    asset.relative_path,
                    result.reason,
                )
                continue

            cache_path = self._cache_path(asset, plan_id=plan_id)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(result.content)
            sha256 = hashlib.sha256(result.content).hexdigest()
            materialized_asset = MaterializedAsset(
                kind=asset.kind,
                relative_path=asset.relative_path,
                source_url=asset.source_url,
                cache_path=cache_path,
                content_type=result.content_type,
                size_bytes=len(result.content),
                sha256=sha256,
                actor_name=asset.actor_name,
                actor_source_id=asset.actor_source_id,
            )
            materialized.append(materialized_asset)
            self._record_success(asset, materialized_asset)
            logger.info(
                "Asset materialized kind=%s relative_path=%s size=%s",
                materialized_asset.kind,
                materialized_asset.relative_path,
                materialized_asset.size_bytes,
            )

        failed = policy.strict and any(item.required for item in missing)
        if self._session is not None:
            self._session.flush()
        logger.info(
            "Asset materialization completed materialized=%s missing=%s failed=%s",
            len(materialized),
            len(missing),
            failed,
        )
        return MaterializedAssetSet(assets=materialized, missing=missing, failed=failed)

    def _cached_asset(
        self,
        asset: LogicalAsset,
        policy: AssetMaterializationPolicy,
    ) -> MaterializedAsset | str | None:
        if self._session is None or not asset.source_url:
            return None
        record = (
            self._session.query(AssetMaterialization)
            .filter(
                AssetMaterialization.source_url == asset.source_url,
                AssetMaterialization.relative_path == asset.relative_path,
                AssetMaterialization.status == "materialized",
            )
            .order_by(AssetMaterialization.id.desc())
            .first()
        )
        if record is None:
            return None
        cache_path = Path(record.cache_path)
        if not _valid_cached_file(cache_path, record.size_bytes, record.sha256):
            return "cache_integrity_failed"
        if not _content_type_allowed_for_asset(asset, record.content_type, policy):
            return "cache_integrity_failed"
        return MaterializedAsset(
            kind=record.kind,
            relative_path=record.relative_path,
            source_url=record.source_url,
            cache_path=cache_path,
            content_type=record.content_type,
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            actor_name=record.actor_name,
            actor_source_id=record.actor_source_id,
        )

    async def _download_or_inline(
        self,
        asset: LogicalAsset,
        policy: AssetMaterializationPolicy,
    ) -> FetchedAsset | MissingAsset:
        if asset.inline_bytes is not None:
            fetched = FetchedAsset(
                url=asset.source_url or f"inline:{asset.kind}",
                content=asset.inline_bytes,
                content_type=detect_content_type(
                    asset.inline_bytes,
                    declared_content_type=asset.content_type,
                    url=asset.relative_path,
                ),
            )
        else:
            assert asset.source_url is not None
            try:
                if asset.referer_url is not None and _adapter_accepts_referer_url(self._adapter):
                    fetched = await self._adapter.fetch_asset(
                        asset.source_url,
                        referer_url=asset.referer_url,
                    )
                else:
                    fetched = await self._adapter.fetch_asset(asset.source_url)
            except Exception as exc:
                reason = _download_failure_reason(exc)
                logger.warning(
                    "Asset download failed kind=%s relative_path=%s error=%s",
                    asset.kind,
                    asset.relative_path,
                    redact_payload(str(exc)),
                )
                return _missing(asset, reason)
        fetched = normalize_fetched_asset(
            fetched,
            fallback_url=asset.source_url or asset.relative_path,
        )
        content_type = normalize_content_type(fetched.content_type)
        if not _content_type_allowed_for_asset(asset, content_type, policy):
            return _missing(asset, "content_type_not_allowed")
        if len(fetched.content) > policy.max_bytes:
            return _missing(asset, "download_too_large")
        if hashlib.sha256(fetched.content).hexdigest() == hashlib.sha256(b"").hexdigest():
            return _missing(asset, "empty_download")
        return FetchedAsset(url=fetched.url, content=fetched.content, content_type=content_type)

    def _cache_path(self, asset: LogicalAsset, *, plan_id: str | None) -> Path:
        filename = sanitize_path_component(Path(asset.relative_path).name)
        if asset.kind == "actor_portrait":
            actor_key = sanitize_path_component(
                asset.actor_source_id
                or asset.actor_name
                or hashlib.sha256((asset.source_url or filename).encode("utf-8")).hexdigest()[:16]
            )
            return self._config_dir / "actor-cache" / "xchina" / actor_key / filename
        if plan_id:
            parts = [sanitize_path_component(part) for part in Path(asset.relative_path).parts]
            return self._config_dir / "asset-cache" / "plans" / sanitize_path_component(plan_id) / Path(*parts)
        source = "xchina"
        digest = hashlib.sha256((asset.source_url or asset.relative_path).encode("utf-8")).hexdigest()
        return self._config_dir / "asset-cache" / source / digest[:2] / digest / filename

    def _record_success(self, asset: LogicalAsset, materialized: MaterializedAsset) -> None:
        if self._session is None:
            return
        self._session.add(
            AssetMaterialization(
                kind=asset.kind,
                relative_path=asset.relative_path,
                source_url=asset.source_url,
                cache_path=str(materialized.cache_path),
                content_type=materialized.content_type,
                expected_size_bytes=None,
                observed_size_bytes=materialized.size_bytes,
                size_bytes=materialized.size_bytes,
                sha256=materialized.sha256,
                status="materialized",
                actor_name=asset.actor_name,
                actor_source_id=asset.actor_source_id,
            )
        )

    def _record_refusal(self, asset: LogicalAsset, reason: str) -> None:
        if self._session is None:
            return
        self._session.add(
            AssetMaterialization(
                kind=asset.kind,
                relative_path=asset.relative_path,
                source_url=asset.source_url,
                cache_path="",
                content_type=asset.content_type or "",
                expected_size_bytes=None,
                observed_size_bytes=0,
                size_bytes=0,
                sha256="",
                status="missing",
                missing_reason=reason,
                actor_name=asset.actor_name,
                actor_source_id=asset.actor_source_id,
            )
        )


def _missing(asset: LogicalAsset | MissingAsset, reason: str) -> MissingAsset:
    return MissingAsset(
        kind=asset.kind,
        relative_path=asset.relative_path,
        required=asset.required,
        reason=reason,
    )


def _download_failure_reason(exc: Exception) -> str:
    explicit = getattr(exc, "reason", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    status_code = getattr(exc, "status_code", None)
    if status_code == 403:
        return "hotlink_forbidden"
    rendered = str(exc).lower()
    if "403" in rendered and "forbidden" in rendered:
        return "hotlink_forbidden"
    return "download_failed"


def _adapter_accepts_referer_url(adapter: AssetAdapter) -> bool:
    try:
        parameters = inspect.signature(adapter.fetch_asset).parameters
    except (TypeError, ValueError):
        return False
    return "referer_url" in parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _valid_cached_file(path: Path, expected_size: int, expected_sha256: str) -> bool:
    if not path.is_file():
        return False
    content = path.read_bytes()
    return (
        len(content) == expected_size
        and hashlib.sha256(content).hexdigest() == expected_sha256
    )


def _content_type_allowed(content_type: str, policy: AssetMaterializationPolicy) -> bool:
    normalized = normalize_content_type(content_type)
    return normalized in {item.lower() for item in policy.allowed_content_types}


def _content_type_allowed_for_asset(
    asset: LogicalAsset,
    content_type: str,
    policy: AssetMaterializationPolicy,
) -> bool:
    normalized = normalize_content_type(content_type)
    if asset.kind in IMAGE_ASSET_KINDS:
        return normalized.startswith("image/") and _content_type_allowed(normalized, policy)
    return _content_type_allowed(normalized, policy)
