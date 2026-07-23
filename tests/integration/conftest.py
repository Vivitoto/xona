from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from backend.app.core.settings import Settings
from backend.app.db.models import AssetMaterialization, MediaItem, OperationPlan, OperationStep
from backend.app.integrations.xchina import FetchedAsset
from backend.app.main import create_app
from backend.app.schemas.source import (
    SourceActorRef,
    SourceAsset,
    SourceSearchResult,
    SourceVideoDetail,
)
from backend.app.services.worker import Worker


ORIGIN = "http://testserver"
MEDIA_BYTES = b"synthetic disposable movie bytes"
POSTER_BYTES = b"\xff\xd8poster-fixture-bytes\xff\xd9"
FANART_BYTES = b"\xff\xd8fanart-fixture-bytes\xff\xd9"
ACTOR_BYTES = b"\xff\xd8actor-fixture-bytes\xff\xd9"


@dataclass(frozen=True)
class MediaLayout:
    root: Path
    config: Path
    source: Path
    output: Path
    media_file: Path


@pytest.fixture
def media_layout(tmp_path: Path) -> MediaLayout:
    source = tmp_path / "source"
    output = tmp_path / "output"
    config = tmp_path / "config"
    source.mkdir()
    output.mkdir()
    media_file = source / "XC-001.Sample.Work.Alpha.mkv"
    media_file.write_bytes(MEDIA_BYTES)
    return MediaLayout(
        root=tmp_path,
        config=config,
        source=source,
        output=output,
        media_file=media_file,
    )


@pytest.fixture
def settings_for_layout(media_layout: MediaLayout):
    def factory(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "config_dir": media_layout.config,
            "storage_roots": (media_layout.root,),
            "auth_enabled": False,
        }
        values.update(overrides)
        return Settings(**values)

    return factory


@dataclass
class MockXChina:
    results: list[SourceSearchResult]
    details: dict[str, SourceVideoDetail]
    assets: dict[str, tuple[bytes, str]]
    searches: list[str] = field(default_factory=list)
    detail_fetches: list[str] = field(default_factory=list)
    asset_fetches: list[str] = field(default_factory=list)

    async def search(self, query: str) -> list[SourceSearchResult]:
        self.searches.append(query)
        return list(self.results)

    async def fetch_video_detail(self, url: str) -> SourceVideoDetail:
        self.detail_fetches.append(url)
        return self.details[url]

    async def fetch_asset(self, url: str) -> FetchedAsset:
        self.asset_fetches.append(url)
        content, content_type = self.assets[url]
        return FetchedAsset(url=url, content=content, content_type=content_type)


@dataclass
class MockEmby:
    fail_next_refresh: bool = False
    scan_calls: int = 0
    lookup_paths: list[str] = field(default_factory=list)
    refreshed_item_ids: list[str] = field(default_factory=list)

    async def scan_library(self) -> None:
        self.scan_calls += 1
        if self.fail_next_refresh:
            self.fail_next_refresh = False
            raise RuntimeError("mock_emby_failure api_key=secret")

    async def find_item_by_path(self, emby_path: str) -> dict[str, str] | None:
        self.lookup_paths.append(emby_path)
        return {"Id": "emby-item-1", "Path": emby_path}

    async def refresh_item(self, item_id: str) -> None:
        self.refreshed_item_ids.append(item_id)


def happy_detail(
    *,
    source_id: str = "XC-001",
    title: str = "Sample Work Alpha",
    complete: bool = True,
    include_assets: bool = True,
) -> SourceVideoDetail:
    return SourceVideoDetail(
        source_id=source_id,
        source_url=f"https://xchina.example.test/videos/{source_id.lower()}.html",
        title=title,
        original_title=f"{title} Original",
        plot="Synthetic fixture plot.",
        release_date="2026-01-02" if complete else None,
        runtime_minutes=91,
        studio="Studio One",
        series="Series One",
        director="Director One",
        actors=[
            SourceActorRef(
                name="Actor One",
                source_id="ACT-001",
                profile_url="https://xchina.example.test/actors/act-001.html",
                portrait_url="https://images.example.test/actor-one.jpg",
            )
        ],
        genres=["Drama"],
        tags=["Synthetic"],
        poster=SourceAsset(
            url="https://images.example.test/poster.jpg",
            kind="poster",
        )
        if include_assets
        else None,
        fanart=SourceAsset(
            url="https://images.example.test/fanart.jpg",
            kind="fanart",
        )
        if include_assets
        else None,
        is_complete=complete,
        completeness_flags=[] if complete else ["missing_release_date"],
    )


def result_for_detail(detail: SourceVideoDetail, *, title: str | None = None) -> SourceSearchResult:
    return SourceSearchResult(
        source_candidate_id=detail.source_id,
        title=title or detail.title,
        url=detail.source_url,
        release_date=detail.release_date,
        thumbnail_url="https://images.example.test/thumb.jpg",
        actors=detail.actors,
        studio=detail.studio,
        series=detail.series,
    )


def happy_xchina() -> MockXChina:
    detail = happy_detail()
    return MockXChina(
        results=[
            result_for_detail(detail),
            SourceSearchResult(
                source_candidate_id="XC-999",
                title="Unrelated Work",
                url="https://xchina.example.test/videos/xc-999.html",
                thumbnail_url="https://images.example.test/thumb.jpg",
            ),
        ],
        details={detail.source_url: detail},
        assets={
            "https://images.example.test/poster.jpg": (POSTER_BYTES, "image/jpeg"),
            "https://images.example.test/fanart.jpg": (FANART_BYTES, "image/jpeg"),
            "https://images.example.test/actor-one.jpg": (ACTOR_BYTES, "image/jpeg"),
        },
    )


def app_with_mocks(
    settings: Settings,
    *,
    xchina: MockXChina,
    emby: MockEmby | None = None,
):
    app = create_app(settings)
    app.state.xchina_adapter = xchina
    app.state.manual_search_adapter = xchina
    if emby is not None:
        app.state.emby_client = emby
    return app


@asynccontextmanager
async def api_client(app):
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=ORIGIN,
        ) as client:
            yield client


async def run_worker_until_state(
    app,
    client: httpx.AsyncClient,
    job_id: int,
    expected_states: set[str],
    *,
    max_runs: int = 20,
) -> dict[str, Any]:
    worker = Worker(
        app.state.sessionmaker,
        settings=app.state.settings,
        search_adapter=app.state.xchina_adapter,
        asset_adapter=app.state.xchina_adapter,
        emby_client=getattr(app.state, "emby_client", None),
        poll_interval_seconds=0,
    )
    latest = (await client.get(f"/api/jobs/{job_id}")).json()
    for _ in range(max_runs):
        if latest["state"] in expected_states:
            return latest
        await worker.run_once()
        latest = (await client.get(f"/api/jobs/{job_id}")).json()
    raise AssertionError(f"job {job_id} did not reach {expected_states}: {latest}")


def run(coro):
    return asyncio.run(coro)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_disposable_database_paths(app, root: Path) -> None:
    with app.state.sessionmaker() as session:
        for media in session.query(MediaItem).all():
            _assert_under(Path(media.path), root)
        for asset in session.query(AssetMaterialization).all():
            if asset.cache_path:
                _assert_under(Path(asset.cache_path), root)
        for plan in session.query(OperationPlan).all():
            for key in ("destination_root", "target_directory"):
                value = plan.plan_json.get(key)
                if value:
                    _assert_under(Path(value), root)
        for step in session.query(OperationStep).all():
            if step.source_path:
                _assert_under(Path(step.source_path), root)
            _assert_under(Path(step.target_path), root)


def _assert_under(path: Path, root: Path) -> None:
    path.resolve(strict=False).relative_to(root.resolve(strict=False))
