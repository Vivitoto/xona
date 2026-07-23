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
        "search_keyword_sample.html",
        "video_detail_sample.html",
    }

    for path in fixture_paths:
        content = path.read_text(encoding="utf-8")
        assert path.stat().st_size < 20_000
        for forbidden in FORBIDDEN_LITERAL:
            assert forbidden not in content
        for pattern in FORBIDDEN_REGEX:
            assert pattern.search(content) is None
