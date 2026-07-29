from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from backend.app.core.settings import Settings
from backend.app.integrations.xchina import FetchedAsset
from backend.app.main import create_app
from backend.app.schemas.source import (
    SourceActorRef,
    SourceAsset,
    SourceSearchResult,
    SourceVideoDetail,
)


ORIGIN = "http://testserver"


class FakeXChinaAdapter:
    def __init__(self) -> None:
        self.search_queries: list[str] = []
        self.detail_urls: list[str] = []
        self.asset_urls: list[str] = []

    async def search(self, query: str) -> list[SourceSearchResult]:
        self.search_queries.append(query)
        return [
            SourceSearchResult(
                source_candidate_id="XC-001",
                title="Sample Work Alpha",
                url="https://www.xchina.co/videos/xc-001.html",
                release_date="2026-01-02",
                thumbnail_url="https://img.xchina.download/thumb.jpg",
                actors=[SourceActorRef(name="Actor One", source_id="ACT-001")],
                studio="Studio One",
                series="Series One",
            )
        ]

    async def fetch_video_detail(self, url: str) -> SourceVideoDetail:
        self.detail_urls.append(url)
        return xchina_detail(source_url=url)

    async def fetch_asset(self, url: str) -> FetchedAsset:
        self.asset_urls.append(url)
        return FetchedAsset(
            url=url,
            content=b"\xff\xd8\xff\xe0proxied-jpeg",
            content_type="image/jpeg",
        )


def test_xchina_search_does_not_require_local_job_or_media(tmp_path: Path) -> None:
    adapter = FakeXChinaAdapter()

    async def run() -> httpx.Response:
        app = create_app(_settings(tmp_path))
        app.state.xchina_adapter = adapter
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.post(
                    "/api/xchina/search",
                    json={"query": "Sample Work Alpha"},
                    headers={"Origin": ORIGIN},
                )

    response = asyncio.run(run())

    assert response.status_code == 200, response.text
    assert adapter.search_queries == ["Sample Work Alpha"]
    payload = response.json()
    assert "job_id" not in payload
    assert "media_path" not in payload
    assert payload["query"] == "Sample Work Alpha"
    assert payload["normalized_query"] == "Sample Work Alpha"
    assert payload["candidates"] == [
        {
            "source": "xchina",
            "source_candidate_id": "XC-001",
            "title": "Sample Work Alpha",
            "image_url": "https://img.xchina.download/thumb.jpg",
            "actors": ["Actor One"],
            "studio": "Studio One",
            "series": "Series One",
            "release_date": "2026-01-02",
            "url": "https://www.xchina.co/videos/xc-001.html",
        }
    ]
    assert "confidence_score" not in payload["candidates"][0]


def test_xchina_search_uses_optional_normalized_query(tmp_path: Path) -> None:
    adapter = FakeXChinaAdapter()

    async def run() -> httpx.Response:
        app = create_app(_settings(tmp_path))
        app.state.xchina_adapter = adapter
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.post(
                    "/api/xchina/search",
                    json={"query": "Raw.Title", "normalized_query": "Raw Title"},
                    headers={"Origin": ORIGIN},
                )

    response = asyncio.run(run())

    assert response.status_code == 200, response.text
    assert adapter.search_queries == ["Raw Title"]
    assert response.json()["query"] == "Raw.Title"
    assert response.json()["normalized_query"] == "Raw Title"


def test_xchina_detail_accepts_direct_source_url_without_local_job(tmp_path: Path) -> None:
    adapter = FakeXChinaAdapter()
    source_url = "https://www.xchina.co/video/id-XC-001.html"

    async def run() -> httpx.Response:
        app = create_app(_settings(tmp_path))
        app.state.xchina_adapter = adapter
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.post(
                    "/api/xchina/detail",
                    json={"source_url": source_url},
                    headers={"Origin": ORIGIN},
                )

    response = asyncio.run(run())

    assert response.status_code == 200, response.text
    assert adapter.detail_urls == [source_url]
    payload = response.json()
    assert "job_id" not in payload
    assert "confidence_score" not in payload
    assert payload["source_url"] == source_url
    assert payload["detail"]["source_id"] == "XC-001"
    assert payload["metadata"]["xchina_id"] == "XC-001"
    assert payload["metadata"]["title"] == "Sample Work Alpha"
    assert payload["metadata"]["assets"]["poster_url"] == "https://img.xchina.download/poster.jpg"


def test_xchina_detail_accepts_embedded_detail_payload_without_adapter(
    tmp_path: Path,
) -> None:
    source_url = "https://www.xchina.co/videos/xc-001.html"

    async def run() -> httpx.Response:
        app = create_app(_settings(tmp_path))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return await client.post(
                    "/api/xchina/detail",
                    json={
                        "source_url": source_url,
                        "detail": xchina_detail(source_url=source_url).model_dump(mode="json"),
                    },
                    headers={"Origin": ORIGIN},
                )

    response = asyncio.run(run())

    assert response.status_code == 200, response.text
    assert response.json()["metadata"]["source_url"] == source_url
    assert response.json()["metadata"]["actors"][0]["name"] == "Actor One"


def test_xchina_detail_rejects_unsafe_urls_before_adapter_fetch(tmp_path: Path) -> None:
    adapter = FakeXChinaAdapter()
    unsafe_urls = [
        "http://127.0.0.1/videos/xc-001.html",
        "https://www.xchina.co:444/videos/xc-001.html",
        "file:///etc/passwd",
        "https://user:pass@www.xchina.co/videos/xc-001.html",
        "https://example.com/videos/xc-001.html",
        "https://www.xchina.co/admin",
    ]

    async def run() -> list[httpx.Response]:
        app = create_app(_settings(tmp_path))
        app.state.xchina_adapter = adapter
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                return [
                    await client.post(
                        "/api/xchina/detail",
                        json={"source_url": url},
                        headers={"Origin": ORIGIN},
                    )
                    for url in unsafe_urls
                ]

    responses = asyncio.run(run())

    assert [response.status_code for response in responses] == [400] * len(unsafe_urls)
    assert adapter.detail_urls == []


def test_xchina_image_proxy_reuses_xchina_image_safety_rules(tmp_path: Path) -> None:
    adapter = FakeXChinaAdapter()

    async def run() -> tuple[httpx.Response, httpx.Response]:
        app = create_app(_settings(tmp_path))
        app.state.xchina_adapter = adapter
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                allowed = await client.get(
                    "/api/xchina/image-proxy",
                    params={"url": "https://img.xchina.download/poster.jpg"},
                )
                rejected = await client.get(
                    "/api/xchina/image-proxy",
                    params={"url": "https://example.com/poster.jpg"},
                )
                return allowed, rejected

    allowed, rejected = asyncio.run(run())

    assert allowed.status_code == 200, allowed.text
    assert allowed.headers["content-type"] == "image/jpeg"
    assert allowed.content == b"\xff\xd8\xff\xe0proxied-jpeg"
    assert rejected.status_code == 400
    assert adapter.asset_urls == ["https://img.xchina.download/poster.jpg"]


def xchina_detail(*, source_url: str) -> SourceVideoDetail:
    return SourceVideoDetail(
        source_id="XC-001",
        source_url=source_url,
        title="Sample Work Alpha",
        original_title="Sample Work Alpha Original",
        plot="Synthetic plot.",
        release_date="2026-01-02",
        runtime_minutes=90,
        studio="Studio One",
        series="Series One",
        director="Director One",
        actors=[SourceActorRef(name="Actor One", source_id="ACT-001")],
        genres=["Drama"],
        tags=["Tag One"],
        poster=SourceAsset(url="https://img.xchina.download/poster.jpg", kind="poster"),
        fanart=SourceAsset(url="https://img.xchina.download/fanart.jpg", kind="fanart"),
        is_complete=True,
    )


def _settings(tmp_path: Path) -> Settings:
    media_root = tmp_path / "media"
    media_root.mkdir()
    return Settings(
        config_dir=tmp_path / "config",
        storage_roots=(media_root,),
        auth_enabled=False,
    )
