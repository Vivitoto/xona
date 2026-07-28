from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from backend.app.db.models import MetadataRecord
from backend.app.schemas.metadata import MetadataActor, MetadataAssets, MetadataRecordData
from backend.app.schemas.source import SourceActorRef, SourceAsset, SourceVideoDetail


def source_detail_with_search_result_fallbacks(
    detail: SourceVideoDetail,
    search_result: Mapping[str, Any] | None,
) -> SourceVideoDetail:
    if search_result is None:
        return detail

    updates: dict[str, Any] = {}
    for detail_field, search_field in (
        ("source_id", "source_candidate_id"),
        ("source_url", "url"),
        ("title", "title"),
        ("release_date", "release_date"),
        ("studio", "studio"),
        ("series", "series"),
    ):
        if _clean(_optional_text(getattr(detail, detail_field))):
            continue
        fallback = _clean(_optional_text(search_result.get(search_field)))
        if fallback:
            updates[detail_field] = fallback

    if not detail.actors:
        actors = _actor_refs_from_search_result(search_result.get("actors"))
        if actors:
            updates["actors"] = actors

    if detail.poster is None:
        thumbnail_url = _clean(_optional_text(search_result.get("thumbnail_url")))
        if thumbnail_url:
            updates["poster"] = SourceAsset(url=thumbnail_url, kind="poster")

    if not updates:
        return detail

    updated = detail.model_copy(update=updates)
    completeness_flags = _merged_completeness_flags(detail, updated, updates.keys())
    return updated.model_copy(
        update={
            "is_complete": not completeness_flags,
            "completeness_flags": completeness_flags,
        }
    )


def normalize_source_video(detail: SourceVideoDetail) -> MetadataRecordData:
    plot = _clean(detail.plot)
    return MetadataRecordData(
        source=detail.source,
        xchina_id=detail.source_id,
        source_url=detail.source_url,
        title=detail.title,
        original_title=_clean(detail.original_title),
        sort_title=detail.title,
        plot=plot,
        outline=plot,
        release_date=_clean(detail.release_date),
        runtime_minutes=detail.runtime_minutes,
        studio=_clean(detail.studio),
        series=_clean(detail.series),
        director=_clean(detail.director),
        actors=[
            MetadataActor(
                name=actor.name,
                source_id=actor.source_id,
                profile_url=actor.profile_url,
                portrait_url=actor.portrait_url,
            )
            for actor in detail.actors
        ],
        genres=list(detail.genres),
        tags=list(detail.tags),
        assets=MetadataAssets(
            poster_url=detail.poster.url if detail.poster else None,
            fanart_url=detail.fanart.url if detail.fanart else None,
            backdrop_urls=[asset.url for asset in detail.backdrops],
            trailer_url=detail.trailer.url if detail.trailer else None,
        ),
    )


def persist_metadata_record(
    session: Session,
    record: MetadataRecordData,
    *,
    media_item_id: int | None = None,
) -> MetadataRecord:
    existing = (
        session.query(MetadataRecord)
        .filter(
            MetadataRecord.source == record.source,
            MetadataRecord.source_id == record.source_id,
            MetadataRecord.media_item_id == media_item_id,
        )
        .one_or_none()
    )
    normalized_json = record.model_dump(mode="json")
    if existing is None:
        existing = MetadataRecord(
            media_item_id=media_item_id,
            source=record.source,
            source_id=record.source_id,
            source_url=record.source_url,
            title=record.title,
            original_title=record.original_title,
            normalized_json=normalized_json,
        )
        session.add(existing)
    else:
        existing.source_url = record.source_url
        existing.title = record.title
        existing.original_title = record.original_title
        existing.normalized_json = normalized_json
    session.flush()
    return existing


def _merged_completeness_flags(
    original: SourceVideoDetail,
    updated: SourceVideoDetail,
    updated_fields: Any,
) -> list[str]:
    resolved_fields = {
        field
        for field in updated_fields
        if field in _COMPLETENESS_FLAG_FIELDS and _detail_field_has_value(updated, field)
    }
    preserved_flags = [
        flag
        for flag in original.completeness_flags
        if _field_for_completeness_flag(flag) not in resolved_fields
    ]
    return _dedupe([*preserved_flags, *_video_completeness_flags(updated)])


_COMPLETENESS_FLAG_FIELDS = {
    "source_id",
    "title",
    "poster",
    "actors",
    "release_date",
}


def _video_completeness_flags(detail: SourceVideoDetail) -> list[str]:
    return [
        f"missing_{key}"
        for key in ("source_id", "title", "poster", "actors")
        if not _detail_field_has_value(detail, key)
    ]


def _detail_field_has_value(detail: SourceVideoDetail, field: str) -> bool:
    value = getattr(detail, field)
    if isinstance(value, str):
        return _clean(value) is not None
    return bool(value)


def _field_for_completeness_flag(flag: str) -> str:
    return flag.removeprefix("missing_")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        unique.append(value)
        seen.add(value)
    return unique


def _actor_refs_from_search_result(value: Any) -> list[SourceActorRef]:
    if not isinstance(value, list):
        return []

    actors: list[SourceActorRef] = []
    for item in value:
        if isinstance(item, SourceActorRef):
            actor = item
        elif isinstance(item, Mapping):
            name = _clean(_optional_text(item.get("name")))
            if not name:
                continue
            actor = SourceActorRef(
                name=name,
                source_id=_clean(_optional_text(item.get("source_id"))),
                profile_url=_clean(_optional_text(item.get("profile_url"))),
                portrait_url=_clean(_optional_text(item.get("portrait_url"))),
            )
        else:
            continue
        actors.append(actor)
    return actors


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
