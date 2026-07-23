from __future__ import annotations

from backend.app.services.normalization import (
    normalize_filename_for_search,
    sanitize_path_component,
)


def test_normalize_filename_cleans_unicode_punctuation_separators_and_whitespace() -> None:
    normalized = normalize_filename_for_search("ＡＢＣ-１２３＿sample---title  .mp4")

    assert normalized.search_text == "ABC-123 sample title"
    assert normalized.identifier == "ABC-123"


def test_normalize_filename_strips_quality_and_source_tags() -> None:
    normalized = normalize_filename_for_search(
        "site-prefix ABC123 [1080p WEB-DL x264 h264 HEVC] Nice Title 4K.mkv"
    )

    assert normalized.identifier == "ABC123"
    assert normalized.search_text == "ABC123 Nice Title"
    assert normalized.technical_tokens == ["1080p", "WEB-DL", "x264", "h264", "HEVC", "4K"]


def test_normalize_filename_preserves_identifier_and_parent_hint() -> None:
    normalized = normalize_filename_for_search(
        "release-site_XYZ-999 Final.cut.part1.mp4",
        parent_name="Parent Series",
    )

    assert normalized.identifier == "XYZ-999"
    assert normalized.multipart_index == 1
    assert "part1" not in normalized.search_text
    assert normalized.parent_hint == "Parent Series"


def test_normalize_filename_removes_site_prefix_suffix_and_multipart_from_search() -> None:
    normalized = normalize_filename_for_search("xchina-ABC-321.demo-release-CD2.mp4")

    assert normalized.identifier == "ABC-321"
    assert normalized.site_prefix == "xchina"
    assert normalized.release_suffix == "release"
    assert normalized.multipart_index == 2
    assert normalized.search_text == "ABC-321 demo"


def test_sanitize_path_component_removes_unsafe_names_without_empty_output() -> None:
    assert sanitize_path_component("CON") == "CON_"
    assert sanitize_path_component("../bad/name\0") == "bad_name"
    assert sanitize_path_component("   ...   ") == "untitled"
    assert len(sanitize_path_component("x" * 300, max_length=40)) == 40
