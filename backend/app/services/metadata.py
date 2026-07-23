from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.db.models import MetadataRecord
from backend.app.schemas.metadata import MetadataActor, MetadataAssets, MetadataRecordData
from backend.app.schemas.source import SourceVideoDetail


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
            MetadataRecord.source_id == record.xchina_id,
            MetadataRecord.media_item_id == media_item_id,
        )
        .one_or_none()
    )
    normalized_json = record.model_dump(mode="json")
    if existing is None:
        existing = MetadataRecord(
            media_item_id=media_item_id,
            source=record.source,
            source_id=record.xchina_id,
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


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None
