from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup, Tag
from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.db.models import HttpCache
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


@dataclass(frozen=True)
class FetchedAsset:
    url: str
    content: bytes
    content_type: str


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
            return parse_video_detail(html, source_url=url, base_url=self._base_url)
        except XChinaParseError as exc:
            raise XChinaParseError(
                f"Failed to parse detail {redact_payload(url)}: {redact_payload(str(exc))}"
            ) from exc

    async def fetch_actor_detail(self, url: str) -> SourceActorDetail:
        html = await self._cached_get(url)
        return parse_actor_detail(html, source_url=url, base_url=self._base_url)

    async def fetch_asset(self, url: str) -> FetchedAsset:
        async with self._limiter:
            request_asset = getattr(self._flaresolverr, "request_asset", None)
            if callable(request_asset):
                result = await request_asset(url)
                return _coerce_fetched_asset(url, result)
            response = await self._flaresolverr.request_get(url)
            return FetchedAsset(
                url=response.url or url,
                content=response.text.encode("utf-8"),
                content_type=_content_type_from_headers(response.headers)
                or _guess_content_type(url),
            )

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
        href = title_link.get("href") if title_link else None
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
    return results


def parse_video_detail(html: str, *, source_url: str, base_url: str) -> SourceVideoDetail:
    soup = BeautifulSoup(html, "html.parser")
    article = _select_one(soup, ".video-detail")
    if article is None:
        raise XChinaParseError("video detail container not found")
    source_id = str(article.get("data-source-id") or "").strip()
    title = _text(_select_one(article, "h1"))
    if not source_id or not title:
        raise XChinaParseError("required video detail fields missing")

    runtime = _attr(_select_one(article, ".runtime"), "data-minutes")
    actors = _actor_refs(_select_one(article, ".actors") or article, base_url=base_url)
    poster = _asset(article, ".poster", "poster", base_url)
    fanart = _asset(article, ".fanart", "fanart", base_url)
    backdrops = [
        SourceAsset(url=_absolute(_attr(backdrop, "src"), base_url), kind="backdrop")
        for backdrop in article.select(".backdrop")
        if _attr(backdrop, "src")
    ]
    trailer_url = _attr(_select_one(article, ".trailer"), "href")
    trailer = (
        SourceAsset(url=_absolute(trailer_url, base_url), kind="trailer")
        if trailer_url
        else None
    )
    flags = _completeness_flags(
        {
            "source_id": source_id,
            "title": title,
            "release_date": _attr(_select_one(article, ".release-date"), "datetime"),
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
        series=_text(_select_one(article, ".series")) or None,
        director=_text(_select_one(article, ".director")) or None,
        actors=actors,
        genres=[_text(item) for item in article.select(".genres li") if _text(item)],
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
    for link in root.select(".actor, .actors a"):
        name = _text(link)
        if not name:
            continue
        actors.append(
            SourceActorRef(
                name=name,
                source_id=str(link.get("data-actor-id") or "").strip() or None,
                profile_url=_absolute(_attr(link, "href"), base_url),
            )
        )
    return actors


def _asset(root: Tag, selector: str, kind: str, base_url: str) -> SourceAsset | None:
    url = _attr(_select_one(root, selector), "src")
    if not url:
        return None
    return SourceAsset(url=_absolute(url, base_url), kind=kind)


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
        return result
    if isinstance(result, bytes):
        return FetchedAsset(
            url=url,
            content=result,
            content_type=_guess_content_type(url),
        )
    if isinstance(result, FlareSolverrResponse):
        return FetchedAsset(
            url=result.url or url,
            content=result.text.encode("utf-8"),
            content_type=_content_type_from_headers(result.headers)
            or _guess_content_type(url),
        )
    if isinstance(result, tuple) and len(result) == 2:
        content, content_type = result
        if isinstance(content, bytes) and isinstance(content_type, str):
            return FetchedAsset(url=url, content=content, content_type=content_type)
    raise TypeError("Unsupported fetched asset response")


def _guess_content_type(url: str) -> str:
    guessed, _encoding = mimetypes.guess_type(url)
    return guessed or "application/octet-stream"


def _content_type_from_headers(headers: dict[str, str] | None) -> str | None:
    if not headers:
        return None
    for key, value in headers.items():
        if key.lower() == "content-type":
            return value.split(";", 1)[0].strip().lower()
    return None
