from __future__ import annotations

import pytest

from backend.app.integrations.xchina_config import (
    DEFAULT_XCHINA_BASE_URL,
    DEFAULT_XCHINA_MAX_SEARCH_PAGES,
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
