from __future__ import annotations
from pathlib import Path

from backend.app.schemas.assets import AssetSelection, LogicalAsset, MissingAsset
from backend.app.schemas.metadata import MetadataRecordData
from backend.app.services.normalization import sanitize_path_component


def select_assets(
    record: MetadataRecordData,
    *,
    include_source_snapshot: bool = False,
) -> AssetSelection:
    assets: list[LogicalAsset] = []
    missing_required: list[MissingAsset] = []

    _add_url_asset(
        assets,
        missing_required,
        kind="poster",
        relative_path="poster.jpg",
        source_url=record.assets.poster_url,
        referer_url=record.source_url,
        required=True,
    )
    _add_url_asset(
        assets,
        missing_required,
        kind="fanart",
        relative_path="fanart.jpg",
        source_url=record.assets.fanart_url,
        referer_url=record.source_url,
        required=True,
    )
    for index, url in enumerate(record.assets.backdrop_urls, start=1):
        assets.append(
            LogicalAsset(
                kind="backdrop",
                relative_path=_backdrop_relative_path(index),
                source_url=url,
                referer_url=record.source_url,
            )
        )
        assets.append(
            LogicalAsset(
                kind="extrafanart",
                relative_path=f"extrafanart/fanart{index}.jpg",
                source_url=url,
                referer_url=record.source_url,
            )
        )
    _add_url_asset(
        assets,
        missing_required,
        kind="thumb",
        relative_path="thumb.jpg",
        source_url=record.assets.thumb_url,
        referer_url=record.source_url,
        required=False,
    )
    _add_url_asset(
        assets,
        missing_required,
        kind="clearlogo",
        relative_path="clearlogo.png",
        source_url=record.assets.clearlogo_url,
        referer_url=record.source_url,
        required=False,
    )
    _add_url_asset(
        assets,
        missing_required,
        kind="trailer",
        relative_path=_trailer_name(record.assets.trailer_url),
        source_url=record.assets.trailer_url,
        referer_url=record.source_url,
        required=False,
    )
    for actor in record.actors:
        if not actor.portrait_url:
            continue
        relative_path = f".actors/{sanitize_path_component(actor.name)}.jpg"
        actor.portrait_reference = relative_path
        assets.append(
            LogicalAsset(
                kind="actor_portrait",
                relative_path=relative_path,
                source_url=actor.portrait_url,
                referer_url=actor.profile_url or record.source_url,
                actor_name=actor.name,
                actor_source_id=actor.source_id,
            )
        )
    if include_source_snapshot:
        assets.append(
            LogicalAsset(
                kind="source_snapshot",
                relative_path="source-snapshot.html",
                source_url=record.source_url,
                referer_url=record.source_url,
            )
        )

    return AssetSelection(assets=assets, missing_required=missing_required)


def _add_url_asset(
    assets: list[LogicalAsset],
    missing_required: list[MissingAsset],
    *,
    kind: str,
    relative_path: str,
    source_url: str | None,
    referer_url: str | None,
    required: bool,
) -> None:
    if source_url:
        assets.append(
            LogicalAsset(
                kind=kind,
                relative_path=relative_path,
                source_url=source_url,
                referer_url=referer_url,
                required=required,
            )
        )
        return
    if required:
        missing_required.append(
            MissingAsset(
                kind=kind,
                relative_path=relative_path,
                required=True,
                reason="missing_source_url",
            )
        )


def _backdrop_relative_path(index: int) -> str:
    return "backdrop.jpg" if index == 1 else f"backdrop{index - 1}.jpg"


def _trailer_name(url: str | None) -> str:
    suffix = Path(url or "").suffix.lower()
    if suffix in {".mp4", ".mkv", ".mov", ".avi"}:
        return f"trailer{suffix}"
    return "trailer.mp4"
