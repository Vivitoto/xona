from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import HttpCache
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.integrations.flaresolverr import FlareSolverrResponse
from backend.app.integrations.xchina import XChinaAdapter, XChinaParseError


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "xchina"


class FakeFlareSolverr:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.urls: list[str] = []
        self.asset_requests: list[tuple[str, str | None, str | None]] = []

    async def request_get(self, url: str) -> FlareSolverrResponse:
        self.urls.append(url)
        return FlareSolverrResponse(url=url, status_code=200, text=self.responses[url])

    async def request_asset(
        self,
        url: str,
        *,
        referer_url: str | None = None,
        base_url: str | None = None,
    ) -> bytes:
        self.asset_requests.append((url, referer_url, base_url))
        return b"\xff\xd8\xffasset-bytes"


def _database(tmp_path: Path):
    settings = Settings(config_dir=tmp_path / "config")
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return engine, get_sessionmaker(engine)


def _fixture(name: str) -> str:
    return (FIXTURE_ROOT / name).read_text(encoding="utf-8")


def test_search_constructs_keyword_route_and_uses_cache(tmp_path: Path) -> None:
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr(
                {"https://example.test/videos/keyword-alpha%20sample.html": _fixture("search_keyword_sample.html")}
            )
            adapter = XChinaAdapter(flaresolverr, session, base_url="https://example.test")

            first = asyncio.run(adapter.search("alpha sample"))
            second = asyncio.run(adapter.search("alpha sample"))

            assert [item.title for item in first] == ["Sample Work Alpha", "Sample Work Beta"]
            assert [item.title for item in second] == ["Sample Work Alpha", "Sample Work Beta"]
            assert flaresolverr.urls == ["https://example.test/videos/keyword-alpha%20sample.html"]
            assert session.query(HttpCache).count() == 1
    finally:
        engine.dispose()


def test_search_follows_pagination_links_and_deduplicates_results(tmp_path: Path) -> None:
    first_url = "https://example.test/videos/keyword-alpha%20sample.html"
    second_url = "https://example.test/videos/keyword-alpha%20sample-2.html"
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr(
                {
                    first_url: _fixture("search_keyword_page_1.html"),
                    second_url: _fixture("search_keyword_page_2.html"),
                }
            )
            adapter = XChinaAdapter(flaresolverr, session, base_url="https://example.test")

            first = asyncio.run(adapter.search("alpha sample"))
            second = asyncio.run(adapter.search("alpha sample"))

            assert [item.source_candidate_id for item in first] == [
                "XC-001",
                "XC-002",
                "XC-003",
            ]
            assert [item.source_candidate_id for item in second] == [
                "XC-001",
                "XC-002",
                "XC-003",
            ]
            assert flaresolverr.urls == [first_url, second_url]
            assert session.query(HttpCache).count() == 2
    finally:
        engine.dispose()


def test_search_stops_at_configured_page_limit(tmp_path: Path) -> None:
    first_url = "https://example.test/videos/keyword-alpha%20sample.html"
    second_url = "https://example.test/videos/keyword-alpha%20sample-2.html"
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr(
                {
                    first_url: _fixture("search_keyword_page_1.html"),
                    second_url: _fixture("search_keyword_page_2.html"),
                }
            )
            adapter = XChinaAdapter(
                flaresolverr,
                session,
                base_url="https://example.test",
                max_search_pages=1,
            )

            results = asyncio.run(adapter.search("alpha sample"))

            assert [item.source_candidate_id for item in results] == ["XC-001", "XC-002"]
            assert flaresolverr.urls == [first_url]
            assert session.query(HttpCache).count() == 1
    finally:
        engine.dispose()


def test_fetch_video_detail_uses_cache_and_redacts_malformed_errors(tmp_path: Path) -> None:
    good_url = "https://example.test/videos/sample-work-alpha.html"
    bad_url = "https://example.test/videos/bad.html?api_key=secret-token"
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr(
                {
                    good_url: _fixture("video_detail_sample.html"),
                    bad_url: "<html><body>missing fields</body></html>",
                }
            )
            adapter = XChinaAdapter(flaresolverr, session, base_url="https://example.test")

            detail = asyncio.run(adapter.fetch_video_detail(good_url))
            cached = asyncio.run(adapter.fetch_video_detail(good_url))
            assert detail.source_id == "XC-001"
            assert cached.source_id == "XC-001"
            assert flaresolverr.urls.count(good_url) == 1

            with pytest.raises(XChinaParseError) as exc:
                asyncio.run(adapter.fetch_video_detail(bad_url))
            rendered = str(exc.value)
            assert "secret-token" not in rendered
            assert "********" in rendered
    finally:
        engine.dispose()


def test_fetch_asset_passes_detail_referrer_and_base_url_context(tmp_path: Path) -> None:
    detail_url = "https://example.test/videos/sample-work-alpha.html"
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr({detail_url: _fixture("video_detail_sample.html")})
            adapter = XChinaAdapter(flaresolverr, session, base_url="https://example.test")

            detail = asyncio.run(adapter.fetch_video_detail(detail_url))
            assert detail.poster is not None
            asset = asyncio.run(adapter.fetch_asset(detail.poster.url))

            assert asset.content == b"\xff\xd8\xffasset-bytes"
            assert flaresolverr.asset_requests == [
                (detail.poster.url, detail_url, "https://example.test")
            ]
    finally:
        engine.dispose()


def test_fetch_asset_uses_base_url_context_without_known_detail(tmp_path: Path) -> None:
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr({})
            adapter = XChinaAdapter(flaresolverr, session, base_url="https://example.test")

            asyncio.run(adapter.fetch_asset("https://upload.xchina.io/video/orphan.webp"))

            assert flaresolverr.asset_requests == [
                (
                    "https://upload.xchina.io/video/orphan.webp",
                    None,
                    "https://example.test",
                )
            ]
    finally:
        engine.dispose()
