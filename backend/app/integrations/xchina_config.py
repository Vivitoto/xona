from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

DEFAULT_XCHINA_BASE_URL = "https://www.xchina.co"
DEFAULT_XCHINA_MAX_SEARCH_PAGES = 50
DEFAULT_XCHINA_IMAGE_HOSTS = {
    "www.xchina.co",
    "xchina.co",
    "img.xchina.download",
    "upload.xchina.io",
}


def xchina_base_url(store_settings: Mapping[str, Any] | None) -> str:
    configured = (store_settings or {}).get("base_url")
    if isinstance(configured, str) and configured.strip():
        return configured.strip().rstrip("/")
    return DEFAULT_XCHINA_BASE_URL


def xchina_max_search_pages(store_settings: Mapping[str, Any] | None) -> int:
    configured = (store_settings or {}).get("max_search_pages")
    if isinstance(configured, int):
        return max(1, configured)
    if isinstance(configured, str) and configured.strip():
        try:
            return max(1, int(configured.strip()))
        except ValueError:
            return DEFAULT_XCHINA_MAX_SEARCH_PAGES
    return DEFAULT_XCHINA_MAX_SEARCH_PAGES


def xchina_allowed_image_hosts(store_settings: Mapping[str, Any] | None) -> set[str]:
    hosts = set(DEFAULT_XCHINA_IMAGE_HOSTS)
    parsed = urlsplit(xchina_base_url(store_settings))
    if parsed.hostname:
        hosts.add(parsed.hostname.lower())
    return hosts


def is_allowed_xchina_resource_url(
    url: str,
    store_settings: Mapping[str, Any] | None,
) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return False
    return parsed.hostname.lower() in xchina_allowed_image_hosts(store_settings)
