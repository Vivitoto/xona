from __future__ import annotations

from backend.app.schemas.metadata import MetadataActor, MetadataAssets, MetadataRecordData
from backend.app.services.assets import select_assets


def _record() -> MetadataRecordData:
    return MetadataRecordData(
        source="xchina",
        xchina_id="XC-001",
        source_url="https://example.test/videos/sample-work-alpha.html",
        title="Sample Work Alpha",
        original_title="Original Sample Alpha",
        sort_title="Sample Work Alpha",
        release_date="2026-01-15",
        actors=[
            MetadataActor(
                name="Actor One",
                source_id="ACT-001",
                profile_url="https://example.test/models/actor-one.html",
                portrait_url="https://images.example.test/actor-one.jpg",
            )
        ],
        assets=MetadataAssets(
            poster_url="https://images.example.test/poster-alpha.jpg",
            fanart_url="https://images.example.test/fanart-alpha.jpg",
            backdrop_urls=[
                "https://images.example.test/backdrop-alpha-1.jpg",
                "https://images.example.test/backdrop-alpha-2.jpg",
            ],
            thumb_url="https://images.example.test/thumb-alpha.jpg",
            clearlogo_url="https://images.example.test/clearlogo-alpha.png",
            trailer_url="https://media.example.test/trailer-alpha.mp4",
        ),
    )


def test_selects_logical_assets_with_deterministic_relative_names() -> None:
    selection = select_assets(_record(), include_source_snapshot=True)

    by_kind = {(asset.kind, asset.relative_path): asset for asset in selection.assets}
    assert ("poster", "poster.jpg") in by_kind
    assert ("fanart", "fanart.jpg") in by_kind
    assert ("backdrop", "backdrop.jpg") in by_kind
    assert ("backdrop", "backdrop1.jpg") in by_kind
    assert ("extrafanart", "extrafanart/fanart1.jpg") in by_kind
    assert ("thumb", "thumb.jpg") in by_kind
    assert ("clearlogo", "clearlogo.png") in by_kind
    assert ("trailer", "trailer.mp4") in by_kind
    assert ("actor_portrait", ".actors/Actor One.jpg") in by_kind
    assert ("normalized_json", "xchina-normalized.json") not in by_kind
    assert ("source_snapshot", "source-snapshot.html") in by_kind
    assert selection.missing_required == []


def test_missing_required_logical_assets_are_explicit() -> None:
    record = _record()
    record.assets.poster_url = None
    record.assets.fanart_url = None

    selection = select_assets(record)

    assert [missing.relative_path for missing in selection.missing_required] == [
        "poster.jpg",
        "fanart.jpg",
    ]
    assert [missing.reason for missing in selection.missing_required] == [
        "missing_source_url",
        "missing_source_url",
    ]
