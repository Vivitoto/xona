from __future__ import annotations

import re
from pathlib import Path


FIXTURE_ROOT = Path(__file__).resolve().parent / "xchina"
FORBIDDEN_LITERAL = (
    "Set-Cookie",
    "cf_clearance",
    "__cf_bm",
    "password=",
    "api_key=",
    "Bearer ",
)
FORBIDDEN_REGEX = (
    re.compile(r"https?://[^\\s/]+:[^\\s/@]+@"),
    re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+"),
    re.compile(r"[A-Za-z]:\\\\Users\\\\"),
)


def test_xchina_fixtures_are_tiny_synthetic_and_private() -> None:
    fixture_paths = sorted(FIXTURE_ROOT.glob("*.html"))
    assert {path.name for path in fixture_paths} == {
        "actor_detail_sample.html",
        "general_numbered_page_1.html",
        "general_numbered_page_2.html",
        "keyword_numbered_page_1.html",
        "keyword_numbered_page_2.html",
        "listing_cards_cloudstream.html",
        "search_keyword_page_1.html",
        "search_keyword_page_2.html",
        "search_keyword_realistic.html",
        "search_keyword_sample.html",
        "series_numbered_page_1.html",
        "series_numbered_page_2.html",
        "series_offhost_next.html",
        "series_page_1.html",
        "series_page_2.html",
        "video_detail_cloudstream.html",
        "video_detail_realistic.html",
        "video_detail_sample.html",
    }

    for path in fixture_paths:
        content = path.read_text(encoding="utf-8")
        assert path.stat().st_size < 20_000
        for forbidden in FORBIDDEN_LITERAL:
            assert forbidden not in content
        for pattern in FORBIDDEN_REGEX:
            assert pattern.search(content) is None
