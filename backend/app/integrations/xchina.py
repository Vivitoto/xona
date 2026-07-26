from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any, Protocol
from urllib.parse import quote, urljoin

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
from backend.app.schemas.source import (
    SourceActorDetail,
    SourceActorRef,
    SourceAsset,
    SourceSearchResult,
    SourceVideoDetail,
)


PARSER_VERSION = "xchina-v1"
REQUEST_PAYLOAD_VERSION = "flaresolverr-request-v1"


class XChinaParseError(ValueError):
    pass


class FlareSolverrLike(Protocol):
    async def request_get(self, url: str) -> FlareSolverrResponse:
        ...


class XChinaAdapter:
    def __init__(
        self,
        flaresolverr: FlareSolverrLike,
        session: Session,
        *,
        base_url: str = "https://www.xchina.co",
        limiter: asyncio.Semaphore | None = None,
    ) -> None:
        self._flaresolverr = flaresolverr
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._limiter = limiter or asyncio.Semaphore(1)
        self._asset_referers: dict[str, str] = {}

    async def test_connection(self) -> bool:
        await self.search("sample")
        return True

    async def search(self, query: str) -> list[SourceSearchResult]:
        url = f"{self._base_url}/videos/keyword-{quote(query, safe='')}.html"
        html = await self._cached_get(url)
        return parse_search_results(html, base_url=self._base_url)

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


def parse_search_results(html: str, *, base_url: str) -> list[SourceSearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SourceSearchResult] = []
    for card in soup.select(".video-card"):
        if not isinstance(card, Tag):
            continue
        title_link = _select_one(card, ".title")
        title = _text(title_link)
        href = _attr(title_link, "href")
        source_id = str(card.get("data-source-id") or "").strip()
        if not source_id or not title or not href:
            continue
        thumbnail = _select_one(card, ".thumbnail")
        time = _select_one(card, "time")
        results.append(
            SourceSearchResult(
                source_candidate_id=source_id,
                title=title,
                url=_absolute(href, base_url),
                release_date=_attr(time, "datetime") or _text(time) or None,
                thumbnail_url=_absolute(_attr(thumbnail, "src"), base_url),
                actors=_actor_refs(card, base_url=base_url),
                studio=_text(_select_one(card, ".studio")) or None,
                series=_text(_select_one(card, ".series")) or None,
            )
        )
    for card in soup.select(".item.video"):
        if not isinstance(card, Tag):
            continue
        title_link = _select_one(card, ".title a") or _select_one(card, "a[title]")
        title = _text(title_link) or _attr(title_link, "title") or ""
        href = _attr(title_link, "href")
        source_id = _source_id_from_url(href)
        if not source_id or not title or not href:
            continue
        tags = [_text(tag) for tag in card.select(".tags > div") if _text(tag)]
        results.append(
            SourceSearchResult(
                source_candidate_id=source_id,
                title=title,
                url=_absolute(href, base_url),
                thumbnail_url=_thumbnail_from_card(card, base_url),
                actors=_actor_refs(card, base_url=base_url),
                studio=None,
                series=tags[0] if tags else None,
            )
        )
    return results


def parse_video_detail(html: str, *, source_url: str, base_url: str) -> SourceVideoDetail:
    soup = BeautifulSoup(html, "html.parser")
    article = _select_one(soup, ".video-detail")
    if article is None:
        raise XChinaParseError("video detail container not found")
    source_id = str(article.get("data-source-id") or "").strip() or _source_id_from_url(source_url)
    title = _text(_select_one(article, "h1")) or _text(_select_one(soup, "h1"))
    if not title:
        first_text_item = _select_one(article, ".item .text")
        title = _text(first_text_item)
    if not source_id or not title:
        raise XChinaParseError("required video detail fields missing")

    runtime = _attr(_select_one(article, ".runtime"), "data-minutes")
    actors = _actor_refs(_select_one(article, ".actors") or article, base_url=base_url)
    poster = _asset(article, ".poster", "poster", base_url) or _screenshot_asset(
        soup, 0, "poster", base_url
    )
    fanart = _asset(article, ".fanart", "fanart", base_url) or _screenshot_asset(
        soup, 1, "fanart", base_url
    )
    backdrops = [
        SourceAsset(url=_absolute(_attr(backdrop, "src"), base_url), kind="backdrop")
        for backdrop in article.select(".backdrop")
        if _attr(backdrop, "src")
    ]
    if not backdrops:
        backdrops = [
            SourceAsset(url=_absolute(src, base_url), kind="backdrop")
            for src in _screenshot_urls(soup)[1:]
        ]
    trailer_url = _attr(_select_one(article, ".trailer"), "href")
    trailer = (
        SourceAsset(url=_absolute(trailer_url, base_url), kind="trailer")
        if trailer_url
        else None
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
        plot=_text(_select_one(article, ".plot")) or None,
        release_date=_attr(_select_one(article, ".release-date"), "datetime")
        or _text(_select_one(article, ".release-date"))
        or None,
        runtime_minutes=int(runtime) if runtime and runtime.isdigit() else None,
        studio=_text(_select_one(article, ".studio")) or None,
        series=_text(_select_one(article, ".series")) or (categories[-1] if categories else None),
        director=_text(_select_one(article, ".director")) or None,
        actors=actors,
        genres=[_text(item) for item in article.select(".genres li") if _text(item)]
        or categories[:1],
        tags=[_text(item) for item in article.select(".tags li") if _text(item)],
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
    profile = _select_one(soup, ".actor-profile")
    if profile is None:
        raise XChinaParseError("actor profile container not found")
    source_id = str(profile.get("data-actor-id") or "").strip()
    name = _text(_select_one(profile, "h1"))
    if not source_id or not name:
        raise XChinaParseError("required actor fields missing")
    portrait = _absolute(_attr(_select_one(profile, ".portrait"), "src"), base_url)
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
    for link in root.select(".actor, .actors a, .model-item"):
        name = _text(link)
        if not name:
            continue
        href = _attr(link, "href")
        if not href and isinstance(link.parent, Tag):
            href = _attr(link.parent, "href")
        source_id = (
            str(link.get("data-actor-id") or "").strip()
            or _source_id_from_url(href)
            or None
        )
        key = (name, source_id)
        if key in seen:
            continue
        seen.add(key)
        actors.append(
            SourceActorRef(
                name=name,
                source_id=source_id,
                profile_url=_absolute(href, base_url),
                portrait_url=_style_background_url(str(link.get("style") or ""), base_url),
            )
        )
    return actors


def _asset(root: Tag, selector: str, kind: str, base_url: str) -> SourceAsset | None:
    url = _attr(_select_one(root, selector), "src")
    if not url:
        return None
    return SourceAsset(url=_absolute(url, base_url), kind=kind)


def _thumbnail_from_card(card: Tag, base_url: str) -> str | None:
    src = _attr(_select_one(card, "img"), "src")
    if src:
        return _absolute(src, base_url)
    return _style_background_url(str((_select_one(card, ".img") or card).get("style") or ""), base_url)


def _style_background_url(style: str, base_url: str) -> str | None:
    match = re.search(r"url\((['\"]?)(.*?)\1\)", style)
    if not match:
        return None
    url = match.group(2).strip()
    return _absolute(url, base_url) if url else None


def _source_id_from_url(url: str | None) -> str:
    if not url:
        return ""
    match = re.search(r"/id-([A-Za-z0-9]+)\.html", url)
    return match.group(1) if match else ""


def _screenshot_urls(soup: BeautifulSoup) -> list[str]:
    urls: list[str] = []
    for image in soup.select(".screenshot-container img"):
        src = _attr(image, "src")
        if src:
            urls.append(src)
    return urls


def _screenshot_asset(
    soup: BeautifulSoup,
    index: int,
    kind: str,
    base_url: str,
) -> SourceAsset | None:
    urls = _screenshot_urls(soup)
    if index >= len(urls):
        return None
    return SourceAsset(url=_absolute(urls[index], base_url), kind=kind)


def _detail_categories(article: Tag, *, base_url: str) -> list[str]:
    categories: list[str] = []
    for item in article.select(".item"):
        icon = _select_one(item, ".fa-video-camera")
        if icon is None:
            continue
        for link in item.select("a[href]"):
            href = _attr(link, "href") or ""
            if "/videos/series-" not in href:
                continue
            text = _text(link)
            if text:
                categories.append(text)
    return categories


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


def _absolute(url: str | None, base_url: str) -> str:
    if not url:
        return ""
    return urljoin(f"{base_url.rstrip('/')}/", url)


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
