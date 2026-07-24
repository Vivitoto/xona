from __future__ import annotations

from pathlib import Path

from backend.app.integrations.xchina import (
    parse_actor_detail,
    parse_search_results,
    parse_video_detail,
)


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "xchina"


def _fixture(name: str) -> str:
    return (FIXTURE_ROOT / name).read_text(encoding="utf-8")


def test_search_parser_extracts_candidates() -> None:
    results = parse_search_results(_fixture("search_keyword_sample.html"), base_url="https://example.test")

    assert len(results) == 2
    assert results[0].source_candidate_id == "XC-001"
    assert results[0].title == "Sample Work Alpha"
    assert results[0].url == "https://example.test/videos/sample-work-alpha.html"
    assert results[0].release_date == "2026-01-15"
    assert results[0].thumbnail_url == "https://images.example.test/thumb-alpha.jpg"
    assert [actor.name for actor in results[0].actors] == ["Actor One", "Actor Two"]
    assert results[0].studio == "Studio Example"
    assert results[0].series == "Series Example"


def test_realistic_search_parser_extracts_current_xchina_cards() -> None:
    results = parse_search_results(_fixture("search_keyword_realistic.html"), base_url="https://xchina.co")

    assert len(results) == 2
    assert results[0].source_candidate_id == "6a5ccfe84b03f"
    assert results[0].title == "七天控精挑战 前三天精华打包 全程高压精神支配"
    assert results[0].url == "https://xchina.co/video/id-6a5ccfe84b03f.html"
    assert results[0].thumbnail_url == "https://img.xchina.download/cover/6a5ccfe84b03f.webp"
    assert [actor.name for actor in results[0].actors] == ["nana_taipei"]
    assert results[0].actors[0].source_id == "6266ada45ba33"
    assert results[0].series == "糖心Vlog"


def test_realistic_video_detail_parser_extracts_current_xchina_detail_page() -> None:
    detail = parse_video_detail(
        _fixture("video_detail_realistic.html"),
        source_url="https://xchina.co/video/id-6a5ccfe84b03f.html",
        base_url="https://xchina.co",
    )

    assert detail.source_id == "6a5ccfe84b03f"
    assert detail.title == "七天控精挑战 前三天精华打包 全程高压精神支配"
    assert detail.series == "糖心Vlog"
    assert detail.genres == ["中文AV"]
    assert [actor.name for actor in detail.actors] == ["nana_taipei"]
    assert detail.actors[0].source_id == "6266ada45ba33"
    assert detail.actors[0].portrait_url == "https://upload.xchina.io/model/6894b60a1ae47.jpg"
    assert detail.poster and detail.poster.url == "https://img.xchina.download/cover/6a5ccfe84b03f.webp"
    assert detail.fanart and detail.fanart.url == "https://img.xchina.download/screenshot/6a5ccfe84b03f.webp"
    assert detail.is_complete is True


def test_video_detail_parser_extracts_complete_metadata() -> None:
    detail = parse_video_detail(
        _fixture("video_detail_sample.html"),
        source_url="https://example.test/videos/sample-work-alpha.html",
        base_url="https://example.test",
    )

    assert detail.source_id == "XC-001"
    assert detail.source_url == "https://example.test/videos/sample-work-alpha.html"
    assert detail.title == "Sample Work Alpha"
    assert detail.original_title == "Original Sample Alpha"
    assert detail.plot == "A short sanitized outline for parser testing."
    assert detail.release_date == "2026-01-15"
    assert detail.runtime_minutes == 92
    assert detail.studio == "Studio Example"
    assert detail.series == "Series Example"
    assert detail.director == "Director Example"
    assert [actor.source_id for actor in detail.actors] == ["ACT-001", "ACT-002"]
    assert detail.genres == ["Drama", "Feature"]
    assert detail.tags == ["Sample Tag", "Collection"]
    assert detail.poster.url.endswith("poster-alpha.jpg")
    assert detail.fanart.url.endswith("fanart-alpha.jpg")
    assert detail.backdrops[0].url.endswith("backdrop-alpha-1.jpg")
    assert detail.trailer.url.endswith("trailer-alpha.mp4")
    assert detail.source_snapshot_eligible is True
    assert detail.is_complete is True


def test_actor_parser_extracts_profile_and_placeholder_state() -> None:
    actor = parse_actor_detail(
        _fixture("actor_detail_sample.html"),
        source_url="https://example.test/models/actor-one.html",
        base_url="https://example.test",
    )

    assert actor.source_id == "ACT-001"
    assert actor.canonical_name == "Actor One"
    assert actor.aliases == ["Alias One", "Sample Alias"]
    assert actor.profile_url == "https://example.test/models/actor-one.html"
    assert actor.portrait_url == "https://images.example.test/actor-one.jpg"
    assert actor.biography == "Synthetic biography text for parser tests."
    assert actor.fields["Birthplace"] == "Example City"
    assert actor.fields["Birthday"] == "2000-01-01"
    assert actor.associated_works == [{"source_id": "XC-001", "title": "Sample Work Alpha", "url": "https://example.test/videos/sample-work-alpha.html"}]
    assert actor.placeholder_image is False
