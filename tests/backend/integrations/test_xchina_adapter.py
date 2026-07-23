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

    async def request_get(self, url: str) -> FlareSolverrResponse:
        self.urls.append(url)
        return FlareSolverrResponse(url=url, status_code=200, text=self.responses[url])


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
