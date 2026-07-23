from __future__ import annotations

from pathlib import Path

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import MetadataRecord
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.integrations.xchina import parse_video_detail
from backend.app.services.metadata import normalize_source_video, persist_metadata_record


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "xchina"


def _detail():
    return parse_video_detail(
        (FIXTURE_ROOT / "video_detail_sample.html").read_text(encoding="utf-8"),
        source_url="https://example.test/videos/sample-work-alpha.html",
        base_url="https://example.test",
    )


def test_normalizes_source_video_to_internal_metadata_record() -> None:
    record = normalize_source_video(_detail())

    assert record.source == "xchina"
    assert record.xchina_id == "XC-001"
    assert record.title == "Sample Work Alpha"
    assert record.original_title == "Original Sample Alpha"
    assert record.sort_title == "Sample Work Alpha"
    assert record.outline == "A short sanitized outline for parser testing."
    assert record.release_date == "2026-01-15"
    assert record.runtime_minutes == 92
    assert record.studio == "Studio Example"
    assert record.series == "Series Example"
    assert record.director == "Director Example"
    assert [actor.name for actor in record.actors] == ["Actor One", "Actor Two"]
    assert record.assets.poster_url == "https://images.example.test/poster-alpha.jpg"
    assert record.assets.backdrop_urls == [
        "https://images.example.test/backdrop-alpha-1.jpg"
    ]


def test_persists_normalized_metadata_json(tmp_path: Path) -> None:
    settings = Settings(config_dir=tmp_path / "config")
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    try:
        with get_sessionmaker(engine)() as session:
            record_data = normalize_source_video(_detail())

            persisted = persist_metadata_record(session, record_data)
            session.commit()

            loaded = session.get(MetadataRecord, persisted.id)
            assert loaded is not None
            assert loaded.source == "xchina"
            assert loaded.source_id == "XC-001"
            assert loaded.normalized_json["title"] == "Sample Work Alpha"
            assert loaded.normalized_json["actors"][0]["source_id"] == "ACT-001"
    finally:
        engine.dispose()
