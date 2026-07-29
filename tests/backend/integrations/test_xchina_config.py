from __future__ import annotations

import pytest

from backend.app.integrations.xchina_config import (
    DEFAULT_XCHINA_BASE_URL,
    DEFAULT_XCHINA_MAX_SEARCH_PAGES,
    is_allowed_xchina_detail_url,
    normalize_xchina_base_url,
    xchina_allowed_image_hosts,
    xchina_base_url,
    xchina_max_search_pages,
)


def test_xchina_base_url_defaults_to_reference_main_url() -> None:
    assert DEFAULT_XCHINA_BASE_URL == "https://xchina.co"
    assert xchina_base_url({}) == "https://xchina.co"
    assert "xchina.co" in xchina_allowed_image_hosts({})
    assert "en.xchina.co" in xchina_allowed_image_hosts({})


def test_xchina_base_url_normalizes_and_requires_origin_only() -> None:
    assert normalize_xchina_base_url(" HTTPS://XCHINA.CO/ ") == "https://xchina.co"
    assert normalize_xchina_base_url("https://mirror.xchina.test:8443") == "https://mirror.xchina.test:8443"

    for value in (
        "xchina.co",
        "ftp://xchina.co",
        "https://xchina.co/videos",
        "https://xchina.co?lang=en",
        "https://xchina.co/#top",
        "https://user:pass@xchina.co",
        "https://xchina.co:bad",
    ):
        with pytest.raises(ValueError):
            normalize_xchina_base_url(value)


def test_xchina_max_search_pages_defaults_and_clamps_to_one() -> None:
    assert xchina_max_search_pages({}) == DEFAULT_XCHINA_MAX_SEARCH_PAGES
    assert (
        xchina_max_search_pages({"max_search_pages": "not-a-number"})
        == DEFAULT_XCHINA_MAX_SEARCH_PAGES
    )
    assert xchina_max_search_pages({"max_search_pages": 0}) == 1
    assert xchina_max_search_pages({"max_search_pages": "0"}) == 1
    assert xchina_max_search_pages({"max_search_pages": 200}) == 200
    assert xchina_max_search_pages({"max_search_pages": "200"}) == 200


def test_xchina_detail_url_allows_current_video_and_legacy_videos_paths() -> None:
    assert is_allowed_xchina_detail_url("https://xchina.co/video/id-abc123.html", {})
    assert is_allowed_xchina_detail_url("https://www.xchina.co/video/id-abc123.html", {})
    assert is_allowed_xchina_detail_url("https://en.xchina.co/video/id-abc123.html", {})
    assert is_allowed_xchina_detail_url("https://xchina.co/videos/legacy-abc123.html", {})


def test_xchina_detail_url_keeps_host_scheme_port_and_credential_guards() -> None:
    for url in (
        "http://xchina.co/video/id-abc123.html",
        "https://xchina.co:444/video/id-abc123.html",
        "https://user:pass@xchina.co/video/id-abc123.html",
        "https://example.com/video/id-abc123.html",
        "https://xchina.co/admin/id-abc123.html",
    ):
        assert not is_allowed_xchina_detail_url(url, {})
