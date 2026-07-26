from __future__ import annotations

from backend.app.integrations.xchina_config import (
    DEFAULT_XCHINA_MAX_SEARCH_PAGES,
    xchina_max_search_pages,
)


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
