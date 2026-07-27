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


def test_search_follows_known_keyword_page_number_shape(tmp_path: Path) -> None:
    first_url = "https://example.test/videos/keyword-page%20shape.html"
    second_url = "https://example.test/videos/keyword-page%20shape/2.html"
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr(
                {
                    first_url: _fixture("keyword_numbered_page_1.html"),
                    second_url: _fixture("keyword_numbered_page_2.html"),
                }
            )
            adapter = XChinaAdapter(flaresolverr, session, base_url="https://example.test")

            results = asyncio.run(adapter.search("page shape"))

            assert [item.source_candidate_id for item in results] == ["KEY001", "KEY002"]
            assert flaresolverr.urls == [first_url, second_url]
            assert session.query(HttpCache).count() == 2
    finally:
        engine.dispose()


def test_fetch_listing_follows_series_pagination_and_deduplicates_results(
    tmp_path: Path,
) -> None:
    first_url = "https://example.test/videos/series-61014080dbfde.html"
    second_url = "https://example.test/videos/series-61014080dbfde/2.html"
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr(
                {
                    first_url: _fixture("series_page_1.html"),
                    second_url: _fixture("series_page_2.html"),
                }
            )
            adapter = XChinaAdapter(flaresolverr, session, base_url="https://example.test")

            results = asyncio.run(adapter.fetch_listing("/videos/series-61014080dbfde.html"))

            assert [item.source_candidate_id for item in results] == [
                "SERIES001",
                "SERIES002",
                "SERIES003",
            ]
            assert flaresolverr.urls == [first_url, second_url]
            assert session.query(HttpCache).count() == 2
    finally:
        engine.dispose()


def test_fetch_listing_follows_general_xchina_listing_numbered_pagination(
    tmp_path: Path,
) -> None:
    first_url = "https://example.test/videos/category-demo.html"
    second_url = "https://example.test/videos/category-demo/2.html"
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr(
                {
                    first_url: _fixture("general_numbered_page_1.html"),
                    second_url: _fixture("general_numbered_page_2.html"),
                }
            )
            adapter = XChinaAdapter(flaresolverr, session, base_url="https://example.test")

            results = asyncio.run(adapter.fetch_listing("/videos/category-demo.html"))

            assert [item.source_candidate_id for item in results] == ["GEN001", "GEN002"]
            assert flaresolverr.urls == [first_url, second_url]
            assert session.query(HttpCache).count() == 2
    finally:
        engine.dispose()


def test_fetch_series_supports_named_common_series_and_numbered_pagination(
    tmp_path: Path,
) -> None:
    first_url = "https://example.test/videos/series-61014080dbfde.html"
    second_url = "https://example.test/videos/series-61014080dbfde/2.html"
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr(
                {
                    first_url: _fixture("series_numbered_page_1.html"),
                    second_url: _fixture("series_numbered_page_2.html"),
                }
            )
            adapter = XChinaAdapter(flaresolverr, session, base_url="https://example.test")

            results = asyncio.run(adapter.fetch_series("tangxin_vlog"))

            assert [item.source_candidate_id for item in results] == ["NUM001", "NUM002"]
            assert flaresolverr.urls == [first_url, second_url]
            assert session.query(HttpCache).count() == 2
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("alias", "expected_url"),
    [
        ("Censored AV", "https://example.test/videos/series-6395aba3deb74.html"),
        ("Model Media", "https://example.test/videos/series-5f904550b8fcc.html"),
        ("Uncensored AV", "https://example.test/videos/series-6395ab7fee104.html"),
        ("Independent Creators", "https://example.test/videos/series-61bf6e439fed6.html"),
        ("Pans Videos", "https://example.test/videos/series-63963186ae145.html"),
        ("Peach Media", "https://example.test/videos/series-5fe8403919165.html"),
        ("Star Media", "https://example.test/videos/series-6054e93356ded.html"),
        ("Timi Media", "https://example.test/videos/series-60153c49058ce.html"),
        ("91mv", "https://example.test/videos/series-5fe840718d665.html"),
    ],
)
def test_fetch_series_supports_xchina_main_listing_aliases(
    tmp_path: Path,
    alias: str,
    expected_url: str,
) -> None:
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr({expected_url: _fixture("general_numbered_page_2.html")})
            adapter = XChinaAdapter(flaresolverr, session, base_url="https://example.test")

            results = asyncio.run(adapter.fetch_series(alias))

            assert [item.source_candidate_id for item in results] == ["GEN002"]
            assert flaresolverr.urls == [expected_url]
    finally:
        engine.dispose()


def test_fetch_listing_ignores_off_host_next_links(tmp_path: Path) -> None:
    first_url = "https://example.test/videos/series-61014080dbfde.html"
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr(
                {first_url: _fixture("series_offhost_next.html")}
            )
            adapter = XChinaAdapter(flaresolverr, session, base_url="https://example.test")

            results = asyncio.run(adapter.fetch_listing(first_url))

            assert [item.source_candidate_id for item in results] == ["SAFE001"]
            assert flaresolverr.urls == [first_url]
            assert session.query(HttpCache).count() == 1
    finally:
        engine.dispose()


def test_fetch_listing_allows_known_xchina_host_next_links(tmp_path: Path) -> None:
    first_url = "https://xchina.co/videos/series-demo.html"
    second_url = "https://en.xchina.co/videos/series-demo/2.html"
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            flaresolverr = FakeFlareSolverr(
                {
                    first_url: _fixture("general_numbered_page_1.html").replace(
                        "/videos/category-demo/2.html",
                        second_url,
                    ),
                    second_url: _fixture("general_numbered_page_2.html"),
                }
            )
            adapter = XChinaAdapter(flaresolverr, session, base_url="https://xchina.co")

            results = asyncio.run(adapter.fetch_listing("/videos/series-demo.html"))

            assert [item.source_candidate_id for item in results] == ["GEN001", "GEN002"]
            assert flaresolverr.urls == [first_url, second_url]
    finally:
        engine.dispose()


def test_fetch_listing_rejects_off_host_start_url(tmp_path: Path) -> None:
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            adapter = XChinaAdapter(FakeFlareSolverr({}), session, base_url="https://example.test")

            with pytest.raises(XChinaParseError):
                asyncio.run(adapter.fetch_listing("https://offsite.example/videos/series-demo.html"))
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
