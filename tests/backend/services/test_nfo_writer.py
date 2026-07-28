from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from backend.app.integrations.xchina import parse_video_detail
from backend.app.schemas.metadata import MetadataRecordData
from backend.app.services.metadata import normalize_source_video
from backend.app.services.nfo import movie_nfo_relative_path, render_movie_nfo


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "xchina"


def test_movie_nfo_relative_path_uses_rendered_template_stem() -> None:
    assert movie_nfo_relative_path("Sample Work Alpha") == "Sample Work Alpha.nfo"
    assert (
        movie_nfo_relative_path("XC-001 - Sample Work Alpha.mkv")
        == "XC-001 - Sample Work Alpha.nfo"
    )


def test_movie_nfo_contains_emby_kodi_metadata() -> None:
    detail = parse_video_detail(
        (FIXTURE_ROOT / "video_detail_sample.html").read_text(encoding="utf-8"),
        source_url="https://example.test/videos/sample-work-alpha.html",
        base_url="https://example.test",
    )
    record = normalize_source_video(detail)
    record.actors[0].role = "Lead"
    record.actors[0].portrait_reference = ".actors/Actor One.jpg"

    root = ElementTree.fromstring(render_movie_nfo(record))

    assert root.tag == "movie"
    assert root.findtext("title") == "Sample Work Alpha"
    assert root.findtext("originaltitle") == "Original Sample Alpha"
    assert root.findtext("sorttitle") == "Sample Work Alpha"
    assert root.findtext("plot") == "A short sanitized outline for parser testing."
    assert root.findtext("outline") == "A short sanitized outline for parser testing."
    assert root.findtext("premiered") == "2026-01-15"
    assert root.findtext("releasedate") == "2026-01-15"
    assert root.findtext("runtime") == "92"
    assert root.findtext("studio") == "Studio Example"
    assert root.findtext("set/name") == "Series Example"
    assert root.findtext("director") == "Director Example"
    assert [item.text for item in root.findall("genre")] == ["Drama", "Feature"]
    assert [item.text for item in root.findall("tag")] == ["Sample Tag", "Collection"]
    unique_id = root.find("uniqueid")
    assert unique_id is not None
    assert unique_id.attrib == {"type": "xchina", "default": "true"}
    assert unique_id.text == "XC-001"
    assert root.findtext("sourceurl") == "https://example.test/videos/sample-work-alpha.html"

    actor = root.findall("actor")[0]
    assert actor.findtext("name") == "Actor One"
    assert actor.findtext("role") == "Lead"
    assert actor.findtext("profile") == "https://example.test/models/actor-one.html"
    assert actor.findtext("thumb") == ".actors/Actor One.jpg"


def test_movie_nfo_uses_local_unique_id_when_source_id_is_absent() -> None:
    record = MetadataRecordData(
        source="local",
        xchina_id=None,
        source_url="file:///media/incoming/Unmatched.Work.mp4",
        title="Unmatched Work",
        plot="Local draft.",
        tags=["local-generated", "unmatched"],
    )

    root = ElementTree.fromstring(render_movie_nfo(record))

    unique_id = root.find("uniqueid")
    assert unique_id is not None
    assert unique_id.attrib == {"type": "local", "default": "true"}
    assert unique_id.text is not None
    assert unique_id.text.startswith("local-")
    assert root.findtext("id") == unique_id.text
    assert root.findtext("title") == "Unmatched Work"
