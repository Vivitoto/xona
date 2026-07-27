from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any, Protocol
from urllib.parse import quote, urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag
from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.db.models import HttpCache
from backend.app.integrations.assets import (
    FetchedAsset,
    content_type_from_headers,
    detect_content_type,
    normalize_fetched_asset,
)
from backend.app.integrations.flaresolverr import FlareSolverrResponse
from backend.app.integrations.xchina_config import DEFAULT_XCHINA_BASE_URL, normalize_xchina_base_url
from backend.app.schemas.source import (
    SourceActorDetail,
    SourceActorRef,
    SourceAsset,
    SourceSearchResult,
    SourceVideoDetail,
)


PARSER_VERSION = "xchina-v2"
REQUEST_PAYLOAD_VERSION = "flaresolverr-request-v1"
DEFAULT_SEARCH_PAGE_LIMIT = 50
XCHINA_SITE_HOSTS = {"xchina.co", "www.xchina.co", "en.xchina.co"}

XCHINA_COMMON_SERIES_PATHS: dict[str, str] = {
    "censored_av": "/videos/series-6395aba3deb74.html",
    "model_media": "/videos/series-5f904550b8fcc.html",
    "uncensored_av": "/videos/series-6395ab7fee104.html",
    "independent_creators": "/videos/series-61bf6e439fed6.html",
    "pans_videos": "/videos/series-63963186ae145.html",
    "tangxin_vlog": "/videos/series-61014080dbfde.html",
    "txvlog": "/videos/series-61014080dbfde.html",
    "peach_media": "/videos/series-5fe8403919165.html",
    "star_media": "/videos/series-6054e93356ded.html",
    "timi_media": "/videos/series-60153c49058ce.html",
    "91mv": "/videos/series-5fe840718d665.html",
}


class XChinaParseError(ValueError):
    pass


class FlareSolverrLike(Protocol):
    async def request_get(self, url: str) -> FlareSolverrResponse: ...


class XChinaAdapter:
    def __init__(
        self,
        flaresolverr: FlareSolverrLike,
        session: Session,
        *,
        base_url: str = DEFAULT_XCHINA_BASE_URL,
        limiter: asyncio.Semaphore | None = None,
        max_search_pages: int = DEFAULT_SEARCH_PAGE_LIMIT,
    ) -> None:
        self._flaresolverr = flaresolverr
        self._session = session
        self._base_url = normalize_xchina_base_url(base_url)
        self._limiter = limiter or asyncio.Semaphore(1)
        self._max_search_pages = max(1, max_search_pages)
        self._asset_referers: dict[str, str] = {}

    async def test_connection(self) -> bool:
        await self.search("sample")
        return True

    async def search(self, query: str) -> list[SourceSearchResult]:
        return await self.fetch_listing(f"/videos/keyword-{quote(query, safe='')}.html")

    async def fetch_listing(self, path_or_url: str) -> list[SourceSearchResult]:
        return await self._fetch_video_listing(_normalize_listing_url(path_or_url, self._base_url))

    async def browse_listing(self, path_or_url: str) -> list[SourceSearchResult]:
        return await self.fetch_listing(path_or_url)

    async def fetch_series(self, series: str) -> list[SourceSearchResult]:
        return await self.fetch_listing(_series_listing_path(series))

    async def _fetch_video_listing(self, start_url: str) -> list[SourceSearchResult]:
        url: str | None = start_url
        page_urls_seen: set[str] = set()
        result_keys_seen: set[tuple[str, str]] = set()
        results: list[SourceSearchResult] = []
        for _page_index in range(self._max_search_pages):
            if url is None:
                break
            page_key = _url_key(url)
            if page_key in page_urls_seen:
                break
            page_urls_seen.add(page_key)

            html = await self._cached_get(url)
            _append_unique_results(
                results,
                parse_listing_results(html, base_url=self._base_url),
                result_keys_seen,
            )
            url = parse_listing_next_page_url(html, current_url=url, base_url=self._base_url)
        return results

    async def fetch_video_detail(self, url: str) -> SourceVideoDetail:
        html = await self._cached_get(url)
        try:
            detail = parse_video_detail(html, source_url=url, base_url=self._base_url)
        except XChinaParseError as exc:
            raise XChinaParseError(
                f"Failed to parse detail {redact_payload(url)}: {redact_payload(str(exc))}"
            ) from exc
        self._remember_video_asset_referers(detail)
        return detail

    async def fetch_actor_detail(self, url: str) -> SourceActorDetail:
        html = await self._cached_get(url)
        detail = parse_actor_detail(html, source_url=url, base_url=self._base_url)
        if detail.portrait_url:
            self._asset_referers[detail.portrait_url] = detail.profile_url
        return detail

    async def fetch_asset(
        self,
        url: str,
        *,
        referer_url: str | None = None,
    ) -> FetchedAsset:
        async with self._limiter:
            request_asset = getattr(self._flaresolverr, "request_asset", None)
            if callable(request_asset):
                result = await request_asset(
                    url,
                    referer_url=referer_url or self._asset_referers.get(url),
                    base_url=self._base_url,
                )
                return _coerce_fetched_asset(url, result)
            response = await self._flaresolverr.request_get(url)
            content = response.text.encode("utf-8")
            return FetchedAsset(
                url=response.url or url,
                content=content,
                content_type=detect_content_type(
                    content,
                    declared_content_type=content_type_from_headers(response.headers),
                    url=response.url or url,
                ),
            )

    def _remember_video_asset_referers(self, detail: SourceVideoDetail) -> None:
        for asset in [detail.poster, detail.fanart, *detail.backdrops, detail.trailer]:
            if asset is not None and asset.url:
                self._asset_referers[asset.url] = detail.source_url
        for actor in detail.actors:
            if actor.portrait_url:
                self._asset_referers[actor.portrait_url] = detail.source_url

    async def _cached_get(self, url: str) -> str:
        key = cache_key("GET", url)
        cached = self._session.get(HttpCache, key)
        if cached is not None:
            return cached.response_text

        async with self._limiter:
            cached = self._session.get(HttpCache, key)
            if cached is not None:
                return cached.response_text
            response = await self._flaresolverr.request_get(url)
            entry = HttpCache(
                cache_key=key,
                method="GET",
                url=url,
                request_json={
                    "request_payload_version": REQUEST_PAYLOAD_VERSION,
                    "parser_version": PARSER_VERSION,
                },
                response_text=response.text,
                status_code=response.status_code,
                parser_version=PARSER_VERSION,
            )
            self._session.add(entry)
            self._session.commit()
            return response.text


def cache_key(method: str, url: str, payload: dict[str, Any] | None = None) -> str:
    material = {
        "method": method.upper(),
        "url": url,
        "payload": payload or {},
        "request_payload_version": REQUEST_PAYLOAD_VERSION,
        "parser_version": PARSER_VERSION,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_listing_results(html: str, *, base_url: str) -> list[SourceSearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SourceSearchResult] = []
    seen: set[tuple[str, str]] = set()
    for card in soup.select(".video-card, .item.video"):
        if not isinstance(card, Tag):
            continue
        result = _listing_result_from_card(card, base_url=base_url)
        if result is None:
            continue
        key = (result.source, result.source_candidate_id)
        if key in seen:
            continue
        seen.add(key)
        results.append(result)
    return results


def parse_search_results(html: str, *, base_url: str) -> list[SourceSearchResult]:
    return parse_listing_results(html, base_url=base_url)


def parse_listing_next_page_url(
    html: str,
    *,
    current_url: str,
    base_url: str,
) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for selector in (
        'a[rel~="next"]',
        'link[rel~="next"]',
        'a[aria-label*="Next"]',
        'a[aria-label*="下一"]',
        ".pagination a.next",
        ".pagination .next a",
        ".pager a.next",
        ".pager .next a",
    ):
        candidate = _next_page_from_link(_select_one(soup, selector), current_url, base_url)
        if candidate:
            return candidate

    for link in soup.select("a[href]"):
        label = _text(link).strip().lower()
        classes = _attribute_values(link, "class")
        rel = _attribute_values(link, "rel")
        if not (
            "next" in classes
            or "next" in rel
            or label in {"next", "next ›", "›", ">", "下一页", "下一頁"}
            or "下一" in label
        ):
            continue
        candidate = _next_page_from_link(link, current_url, base_url)
        if candidate:
            return candidate

    candidate = _next_page_from_numbered_links(soup, current_url, base_url)
    if candidate:
        return candidate

    return _next_page_from_pagination_text(soup, current_url, base_url)


def parse_search_next_page_url(
    html: str,
    *,
    current_url: str,
    base_url: str,
) -> str | None:
    return parse_listing_next_page_url(html, current_url=current_url, base_url=base_url)


def _listing_result_from_card(card: Tag, *, base_url: str) -> SourceSearchResult | None:
    title_link = _card_title_link(card)
    title = _text(title_link) or _attr(title_link, "title") or _attr(card, "data-title") or ""
    href = _attr(title_link, "href") or _card_video_href(card)
    source_id = _card_source_id(card, href)
    if not source_id or not title or not href:
        return None

    time = _select_one(card, "time")
    return SourceSearchResult(
        source_candidate_id=source_id,
        title=title,
        url=_absolute(href, base_url),
        release_date=_attr(time, "datetime") or _text(time) or None,
        thumbnail_url=_thumbnail_from_card(card, base_url),
        actors=_actor_refs(card, base_url=base_url),
        studio=_text(_select_one(card, ".studio")) or None,
        series=_card_series(card),
    )


def _card_title_link(card: Tag) -> Tag | None:
    for selector in (
        ".title a[href]",
        "a.title[href]",
        "a[href*='/video/id-']",
        "a[href*='/videos/'][title]",
        "a[title][href]",
    ):
        link = _select_one(card, selector)
        if link is not None:
            return link
    return _card_video_link(card)


def _card_video_href(card: Tag) -> str | None:
    return _attr(_card_video_link(card), "href")


def _card_video_link(card: Tag) -> Tag | None:
    for link in card.select("a[href]"):
        href = _attr(link, "href") or ""
        if "/model/" in href or "/models/" in href or "/series-" in href:
            continue
        if "/video/" in href or "/videos/" in href:
            return link if isinstance(link, Tag) else None
    return None


def _card_source_id(card: Tag, href: str | None) -> str:
    for attribute in ("data-source-id", "data-video-id", "data-id"):
        value = str(card.get(attribute) or "").strip()
        if value:
            return value
    return _source_id_from_url(href)


def parse_video_detail(html: str, *, source_url: str, base_url: str) -> SourceVideoDetail:
    soup = BeautifulSoup(html, "html.parser")
    article = _select_one(soup, ".video-detail")
    if article is None:
        raise XChinaParseError("video detail container not found")
    source_id = (
        _first_attr(article, ("data-source-id", "data-video-id", "data-id"))
        or _detail_code(article)
        or _source_id_from_url(source_url)
        or _source_id_from_url(_meta_content(soup, property_name="og:url"))
    )
    title = _detail_title(soup, article)
    if not source_id or not title:
        raise XChinaParseError("required video detail fields missing")

    runtime = _detail_runtime_minutes(article)
    actors = _actor_refs(_select_one(article, ".actors") or article, base_url=base_url)
    poster = (
        _asset(article, ".poster, .cover, .video-cover img, .cover img", "poster", base_url)
        or _asset_from_url(_meta_content(soup, property_name="og:image"), "poster", base_url)
        or _screenshot_asset(soup, 0, "poster", base_url)
    )
    fanart = _asset(article, ".fanart, .fanart img", "fanart", base_url) or _screenshot_asset(
        soup, 1, "fanart", base_url
    )
    backdrops = _detail_backdrops(soup, article, base_url=base_url)
    trailer_url = _attr(_select_one(article, ".trailer"), "href")
    trailer = (
        SourceAsset(url=_absolute(trailer_url, base_url), kind="trailer") if trailer_url else None
    )
    categories = _detail_categories(article, base_url=base_url)
    flags = _completeness_flags(
        {
            "source_id": source_id,
            "title": title,
            "poster": poster,
            "actors": actors,
        }
    )

    return SourceVideoDetail(
        source_id=source_id,
        source_url=source_url,
        title=title,
        original_title=_text(_select_one(article, ".original-title")) or None,
        plot=_detail_plot(soup, article),
        release_date=_attr(_select_one(article, ".release-date"), "datetime")
        or _text(_select_one(article, ".release-date"))
        or _detail_text_by_icon(article, ("fa-calendar", "fa-calendar-days"))
        or None,
        runtime_minutes=runtime,
        studio=_text(_select_one(article, ".studio")) or None,
        series=_text(_select_one(article, ".series")) or (categories[-1] if categories else None),
        director=_text(_select_one(article, ".director")) or None,
        actors=actors,
        genres=_detail_genres(article) or categories[:1],
        tags=_detail_tags(article),
        poster=poster,
        fanart=fanart,
        backdrops=backdrops,
        trailer=trailer,
        source_snapshot_eligible=True,
        is_complete=not flags,
        completeness_flags=flags,
    )


def parse_actor_detail(html: str, *, source_url: str, base_url: str) -> SourceActorDetail:
    soup = BeautifulSoup(html, "html.parser")
    profile = _select_one(soup, ".actor-profile, .model-profile, .model-detail")
    if profile is None:
        raise XChinaParseError("actor profile container not found")
    source_id = (
        _first_attr(profile, ("data-actor-id", "data-model-id", "data-source-id", "data-id"))
        or _source_id_from_url(source_url)
    )
    name = _text(_select_one(profile, "h1"))
    if not source_id or not name:
        raise XChinaParseError("required actor fields missing")
    portrait = _image_url_from_node(
        _select_one(profile, ".portrait, .avatar, .model-item, img"),
        base_url,
    )
    fields: dict[str, str] = {}
    terms = profile.select("dt")
    definitions = profile.select("dd")
    for term, definition in zip(terms, definitions):
        key = _text(term)
        value = _text(definition)
        if key and value:
            fields[key] = value
    works: list[dict[str, str]] = []
    for link in profile.select(".works a"):
        source_work_id = str(link.get("data-source-id") or "").strip()
        title = _text(link)
        href = _attr(link, "href")
        if source_work_id and title and href:
            works.append(
                {
                    "source_id": source_work_id,
                    "title": title,
                    "url": _absolute(href, base_url),
                }
            )
    return SourceActorDetail(
        source_id=source_id,
        canonical_name=name,
        aliases=[_text(item) for item in profile.select(".aliases li") if _text(item)],
        profile_url=source_url,
        portrait_url=portrait,
        biography=_text(_select_one(profile, ".biography")) or None,
        fields=fields,
        associated_works=works,
        placeholder_image=not portrait or "placeholder" in portrait.lower(),
    )


def _actor_refs(root: Tag, *, base_url: str) -> list[SourceActorRef]:
    actors: list[SourceActorRef] = []
    seen: set[tuple[str, str | None]] = set()
    for node in root.select(
        ".actor, .actors a, .model-item, .model-container a[href], "
        ".model-avatar-container a[href]"
    ):
        name = _text(node) or _attr(node, "title") or _attr(_select_one(node, "img"), "alt") or ""
        if not name:
            continue
        profile_link = node if _attr(node, "href") else _closest_link(node)
        href = _attr(profile_link, "href")
        source_id = _actor_source_id(node, profile_link, href)
        key = (name, source_id)
        if key in seen:
            continue
        seen.add(key)
        actors.append(
            SourceActorRef(
                name=name,
                source_id=source_id,
                profile_url=_absolute(href, base_url) or None,
                portrait_url=_image_url_from_node(node, base_url)
                or _image_url_from_node(profile_link, base_url),
            )
        )
    return actors


def _actor_source_id(node: Tag, profile_link: Tag | None, href: str | None) -> str | None:
    return (
        _first_attr(node, ("data-actor-id", "data-model-id", "data-source-id", "data-id"))
        or _first_attr(profile_link, ("data-actor-id", "data-model-id", "data-source-id", "data-id"))
        or _source_id_from_url(href)
        or None
    )


def _closest_link(node: Tag | None) -> Tag | None:
    parent = node.parent if node is not None else None
    while isinstance(parent, Tag):
        if _attr(parent, "href"):
            return parent
        parent = parent.parent
    return None


def _asset(
    root: BeautifulSoup | Tag,
    selector: str,
    kind: str,
    base_url: str,
) -> SourceAsset | None:
    url = _image_url_from_node(_select_one(root, selector), base_url)
    if not url:
        return None
    return SourceAsset(url=url, kind=kind)


def _asset_from_url(url: str | None, kind: str, base_url: str) -> SourceAsset | None:
    absolute_url = _absolute(url, base_url)
    return SourceAsset(url=absolute_url, kind=kind) if absolute_url else None


def _thumbnail_from_card(card: Tag, base_url: str) -> str | None:
    for node in (
        _select_one(card, ".img"),
        _select_one(card, ".thumbnail"),
        _select_one(card, "img"),
        card,
    ):
        url = _image_url_from_node(node, base_url)
        if url:
            return url
    return None


def _image_url_from_node(node: Tag | None, base_url: str) -> str | None:
    if node is None:
        return None
    for value in _image_url_candidates(node):
        return _absolute(value, base_url)
    for child in node.select("img, source, [data-src], [data-original], [data-lazy-src], [style]"):
        if not isinstance(child, Tag):
            continue
        for value in _image_url_candidates(child):
            return _absolute(value, base_url)
    return None


def _image_url_candidates(node: Tag) -> list[str]:
    candidates: list[str] = []
    for attribute in (
        "data-src",
        "data-original",
        "data-lazy-src",
        "data-url",
        "src",
        "poster",
    ):
        value = _attr(node, attribute)
        if value:
            candidates.append(value)
    srcset = _attr(node, "srcset") or _attr(node, "data-srcset")
    if srcset:
        first_srcset_url = srcset.split(",", maxsplit=1)[0].strip().split(" ", maxsplit=1)[0]
        if first_srcset_url:
            candidates.append(first_srcset_url)
    style_url = _style_background_url(str(node.get("style") or ""))
    if style_url:
        candidates.append(style_url)
    return candidates


def _style_background_url(style: str) -> str | None:
    match = re.search(r"url\(\s*(['\"]?)(.*?)\1\s*\)", style)
    if not match:
        return None
    url = match.group(2).strip()
    return url or None


def _source_id_from_url(url: str | None) -> str:
    if not url:
        return ""
    match = re.search(r"/id-([A-Za-z0-9_-]+)\.html", url)
    return match.group(1) if match else ""


def _screenshot_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    urls: list[str] = []
    for image in soup.select(
        ".screenshot-container img, .screenshots img, .screen-shots img, "
        ".preview img, .backdrops img, .swiper-slide img"
    ):
        if not isinstance(image, Tag):
            continue
        url = _image_url_from_node(image, base_url)
        if url:
            urls.append(url)
    return _dedupe_urls(urls)


def _screenshot_asset(
    soup: BeautifulSoup,
    index: int,
    kind: str,
    base_url: str,
) -> SourceAsset | None:
    urls = _screenshot_urls(soup, base_url)
    if index >= len(urls):
        return None
    return SourceAsset(url=urls[index], kind=kind)


def _detail_backdrops(
    soup: BeautifulSoup,
    article: Tag,
    *,
    base_url: str,
) -> list[SourceAsset]:
    urls: list[str] = []
    for backdrop in article.select(".backdrop, .backdrop img"):
        if not isinstance(backdrop, Tag):
            continue
        url = _image_url_from_node(backdrop, base_url)
        if url:
            urls.append(url)
    urls.extend(_screenshot_urls(soup, base_url)[1:])
    return [SourceAsset(url=url, kind="backdrop") for url in _dedupe_urls(urls)]


def _detail_title(soup: BeautifulSoup, article: Tag) -> str:
    title = _text(_select_one(article, "h1")) or _text(_select_one(soup, "h1"))
    if title:
        return title
    title = _detail_text_by_icon(article, ("fa-address-card", "fa-heading"))
    if title:
        return title
    first_text_item = _select_one(article, ".item .text")
    return _text(first_text_item)


def _detail_code(article: Tag) -> str:
    for item in article.select(".item"):
        if not isinstance(item, Tag):
            continue
        if not _item_has_icon(item, ("fa-hashtag",)):
            continue
        code = _text(_select_one(item, "code")) or _text(_select_one(item, ".text"))
        cleaned = _clean_source_code(code)
        if cleaned:
            return cleaned
    code = _text(_select_one(article, "code"))
    return _clean_source_code(code)


def _clean_source_code(code: str) -> str:
    match = re.search(r"[A-Za-z0-9][A-Za-z0-9_-]*", code)
    return match.group(0) if match else ""


def _detail_plot(soup: BeautifulSoup, article: Tag) -> str | None:
    for selector in (".plot", ".description", "[itemprop='description']"):
        text = _text(_select_one(article, selector))
        if text:
            return text
    return _meta_content(soup, name="description") or None


def _detail_runtime_minutes(article: Tag) -> int | None:
    runtime_node = _select_one(article, ".runtime")
    runtime = _attr(runtime_node, "data-minutes")
    if runtime and runtime.isdigit():
        return int(runtime)
    text = _text(runtime_node) or _detail_text_by_icon(article, ("fa-clock", "fa-stopwatch"))
    return _runtime_minutes_from_text(text)


def _runtime_minutes_from_text(text: str) -> int | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", cleaned)
    if match:
        first = int(match.group(1))
        second = int(match.group(2))
        third = int(match.group(3) or 0)
        if match.group(3) is None:
            return first
        return first * 60 + second + (1 if third >= 30 else 0)
    match = re.search(r"(\d+)\s*(?:minutes?|mins?|分钟|分)", cleaned, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return int(cleaned) if cleaned.isdigit() else None


def _detail_text_by_icon(article: Tag, icon_classes: tuple[str, ...]) -> str:
    for item in article.select(".item"):
        if isinstance(item, Tag) and _item_has_icon(item, icon_classes):
            text = _text(_select_one(item, ".text"))
            if text:
                return text
    return ""


def _item_has_icon(item: Tag, icon_classes: tuple[str, ...]) -> bool:
    classes: set[str] = set()
    for icon in item.select("i[class]"):
        if isinstance(icon, Tag):
            classes.update(_attribute_values(icon, "class"))
    return any(icon_class in classes for icon_class in icon_classes)


def _detail_categories(article: Tag, *, base_url: str) -> list[str]:
    categories: list[str] = []
    for item in article.select(".item"):
        if not isinstance(item, Tag) or not _item_has_icon(
            item, ("fa-video-camera", "fa-film", "fa-folder", "fa-list")
        ):
            continue
        for link in item.select("a[href]"):
            href = _attr(link, "href") or ""
            if "/videos/series-" not in href:
                continue
            text = _text(link)
            if text:
                categories.append(text)
    return _dedupe_text(categories)


def _detail_genres(article: Tag) -> list[str]:
    genres = [_text(item) for item in article.select(".genres li, .genres a") if _text(item)]
    return _dedupe_text(genres)


def _detail_tags(article: Tag) -> list[str]:
    tags: list[str] = []
    for item in article.select(".tags li, .tags a, a[href*='/tags/'], a[href*='/videos/tag-']"):
        text = _text(item)
        if text:
            tags.append(text)
    for item in article.select(".item"):
        if isinstance(item, Tag) and _item_has_icon(item, ("fa-tags", "fa-tag")):
            tags.extend(_text(link) for link in item.select("a[href]") if _text(link))
    return _dedupe_text(tags)


def _card_series(card: Tag) -> str | None:
    explicit = _text(_select_one(card, ".series"))
    if explicit:
        return explicit
    for link in card.select("a[href*='/videos/series-']"):
        text = _text(link)
        if text:
            return text
    tags = _card_tag_texts(card)
    return tags[0] if tags else None


def _card_tag_texts(card: Tag) -> list[str]:
    tags: list[str] = []
    for tag in card.select(".tags > div, .tags a, .tag"):
        if not isinstance(tag, Tag) or "empty" in _attribute_values(tag, "class"):
            continue
        text = _text(tag)
        if not text:
            continue
        if re.fullmatch(r"\d+", text) or re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", text):
            continue
        tags.append(text)
    return _dedupe_text(tags)


def _completeness_flags(values: dict[str, Any]) -> list[str]:
    return [f"missing_{key}" for key, value in values.items() if not value]


def _select_one(root: BeautifulSoup | Tag, selector: str) -> Tag | None:
    found = root.select_one(selector)
    return found if isinstance(found, Tag) else None


def _text(tag: Tag | None) -> str:
    if tag is None:
        return ""
    return " ".join(tag.get_text(" ", strip=True).split())


def _attr(tag: Tag | None, name: str) -> str | None:
    if tag is None:
        return None
    value = tag.get(name)
    return str(value).strip() if value else None


def _attribute_values(tag: Tag, name: str) -> set[str]:
    value = tag.get(name)
    if value is None:
        return set()
    if isinstance(value, str):
        return {value.lower()}
    return {str(item).lower() for item in value}


def _first_attr(tag: Tag | None, names: tuple[str, ...]) -> str:
    for name in names:
        value = _attr(tag, name)
        if value:
            return value
    return ""


def _meta_content(
    soup: BeautifulSoup,
    *,
    property_name: str | None = None,
    name: str | None = None,
) -> str:
    selector = ""
    if property_name is not None:
        selector = f'meta[property="{property_name}"]'
    elif name is not None:
        selector = f'meta[name="{name}"]'
    if not selector:
        return ""
    return _attr(_select_one(soup, selector), "content") or ""


def _absolute(url: str | None, base_url: str) -> str:
    if not url:
        return ""
    return urljoin(f"{base_url.rstrip('/')}/", url)


def _append_unique_results(
    output: list[SourceSearchResult],
    page_results: list[SourceSearchResult],
    seen: set[tuple[str, str]],
) -> None:
    for result in page_results:
        key = (result.source, result.source_candidate_id)
        if key in seen:
            continue
        seen.add(key)
        output.append(result)


def _normalize_listing_url(path_or_url: str, base_url: str) -> str:
    value = path_or_url.strip()
    if not value:
        raise XChinaParseError("listing URL required")
    value = XCHINA_COMMON_SERIES_PATHS.get(value, value)
    url = _absolute(value, base_url)
    if not _is_allowed_listing_url(url, base_url):
        raise XChinaParseError("listing URL must be an on-site /videos page")
    return _url_key(url)


def _series_listing_path(series: str) -> str:
    value = series.strip()
    alias = _series_alias_key(value)
    if alias in XCHINA_COMMON_SERIES_PATHS:
        return XCHINA_COMMON_SERIES_PATHS[alias]
    if re.fullmatch(r"series-[A-Za-z0-9]+", value):
        return f"/videos/{value}.html"
    if re.fullmatch(r"[A-Za-z0-9]+", value):
        return f"/videos/series-{value}.html"
    return value


def _series_alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _is_allowed_listing_url(url: str, base_url: str) -> bool:
    candidate_parts = urlsplit(_url_key(url))
    base_parts = urlsplit(base_url)
    if candidate_parts.scheme not in {"http", "https"}:
        return False
    if not _is_same_xchina_site_location(candidate_parts, base_parts):
        return False
    return candidate_parts.path == "/videos" or candidate_parts.path.startswith("/videos/")


def _is_same_xchina_site_location(candidate: Any, base: Any) -> bool:
    candidate_host = (candidate.hostname or "").lower()
    base_host = (base.hostname or "").lower()
    if not candidate_host or not base_host:
        return False
    if candidate.scheme != base.scheme:
        return False
    if _effective_port(candidate) != _effective_port(base):
        return False
    if candidate_host == base_host:
        return True
    return candidate_host in XCHINA_SITE_HOSTS and base_host in XCHINA_SITE_HOSTS


def _effective_port(parts: Any) -> int | None:
    try:
        explicit_port = parts.port
    except ValueError:
        return None
    if explicit_port is not None:
        return explicit_port
    if parts.scheme == "http":
        return 80
    if parts.scheme == "https":
        return 443
    return None


def _next_page_from_link(link: Tag | None, current_url: str, base_url: str) -> str | None:
    href = _attr(link, "href")
    if not href:
        return None
    candidate = _absolute(href, base_url)
    if not _is_allowed_next_listing_url(candidate, current_url, base_url):
        return None
    return _url_key(candidate)


def _is_allowed_next_listing_url(candidate: str, current_url: str, base_url: str) -> bool:
    candidate_key = _url_key(candidate)
    if not candidate_key or candidate_key == _url_key(current_url):
        return False
    return _is_allowed_listing_url(candidate_key, base_url)


def _next_page_from_numbered_links(
    soup: BeautifulSoup,
    current_url: str,
    base_url: str,
) -> str | None:
    current_listing = _known_listing_page(current_url)
    if current_listing is None:
        return None
    current_route, current_page = current_listing
    candidates: list[tuple[int, str]] = []
    links = soup.select(
        ".pagination a[href], .pager a[href], .pages a[href], .page-numbers a[href], "
        ".page-item a[href], .layui-laypage a[href]"
    )
    if not links:
        links = soup.select("a[href]")
    for link in links:
        if not isinstance(link, Tag):
            continue
        href = _attr(link, "href")
        candidate = _absolute(href, base_url)
        if not _is_allowed_next_listing_url(candidate, current_url, base_url):
            continue
        listing = _known_listing_page(candidate)
        if listing is None:
            continue
        route, page = listing
        if route == current_route and page > current_page:
            candidates.append((page, _url_key(candidate)))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _next_page_from_pagination_text(
    soup: BeautifulSoup,
    current_url: str,
    base_url: str,
) -> str | None:
    current_listing = _known_listing_page(current_url)
    if current_listing is None:
        return None
    _, current_page = current_listing
    page_numbers: list[int] = []
    for container in soup.select(".pagination, .pager, .pages, .page-numbers, .layui-laypage"):
        text = _text(container) if isinstance(container, Tag) else ""
        page_numbers.extend(int(value) for value in re.findall(r"\b\d+\b", text))
    if not page_numbers or max(page_numbers) <= current_page:
        return None
    return _known_listing_url_for_page(current_url, current_page + 1, base_url)


def _known_listing_page(url: str) -> tuple[str, int] | None:
    path = urlsplit(_url_key(url)).path
    match = re.fullmatch(r"(/videos/[^/]+?)(?:/(\d+))?\.html", path)
    if not match:
        return None
    page = int(match.group(2) or "1")
    return match.group(1), page


def _known_listing_url_for_page(current_url: str, page: int, base_url: str) -> str | None:
    listing = _known_listing_page(current_url)
    if listing is None:
        return None
    route, _current_page = listing
    path = f"{route}.html" if page <= 1 else f"{route}/{page}.html"
    current_parts = urlsplit(_url_key(current_url))
    current_origin = f"{current_parts.scheme}://{current_parts.netloc}"
    candidate = _absolute(path, current_origin)
    return _url_key(candidate) if _is_allowed_listing_url(candidate, base_url) else None


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = " ".join(value.split())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        output.append(cleaned)
    return output


def _dedupe_urls(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = _url_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _url_key(url: str) -> str:
    return urldefrag(url)[0]


def _coerce_fetched_asset(url: str, result: Any) -> FetchedAsset:
    if isinstance(result, FetchedAsset):
        return normalize_fetched_asset(result, fallback_url=url)
    if isinstance(result, bytes):
        return FetchedAsset(
            url=url,
            content=result,
            content_type=detect_content_type(result, url=url),
        )
    if isinstance(result, FlareSolverrResponse):
        content = result.content if result.content is not None else result.text.encode("utf-8")
        return FetchedAsset(
            url=result.url or url,
            content=content,
            content_type=detect_content_type(
                content,
                declared_content_type=content_type_from_headers(result.headers),
                url=result.url or url,
            ),
        )
    if isinstance(result, tuple) and len(result) == 2:
        content, content_type = result
        if isinstance(content, bytes) and isinstance(content_type, str):
            return FetchedAsset(
                url=url,
                content=content,
                content_type=detect_content_type(
                    content,
                    declared_content_type=content_type,
                    url=url,
                ),
            )
    raise TypeError("Unsupported fetched asset response")
