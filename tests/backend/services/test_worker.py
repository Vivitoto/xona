from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import backend.app.services.worker as worker_module
from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import Job, WatchRule
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.integrations.assets import FetchedAsset
from backend.app.schemas.assets import AssetSelection
from backend.app.schemas.source import SourceActorRef, SourceAsset, SourceSearchResult, SourceVideoDetail
from backend.app.services.jobs import JobService
from backend.app.services.settings_store import SettingsStore
from backend.app.services.worker import Worker


def _database(tmp_path: Path):
    settings = Settings(config_dir=tmp_path / "config")
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return engine, get_sessionmaker(engine)


class FakeSavedSettingsFlareSolverr:
    instances: list["FakeSavedSettingsFlareSolverr"] = []

    def __init__(self, url: str, *, proxy_url: str | None = None) -> None:
        self.url = url
        self.proxy_url = proxy_url
        self.closed = False
        self.instances.append(self)

    async def close(self) -> None:
        self.closed = True


class FakeSavedSettingsXChina:
    instances: list["FakeSavedSettingsXChina"] = []

    def __init__(
        self,
        flaresolverr: FakeSavedSettingsFlareSolverr,
        session,
        *,
        base_url: str = "https://www.xchina.co",
    ) -> None:
        self.flaresolverr = flaresolverr
        self.session = session
        self.base_url = base_url
        self.instances.append(self)

    async def search(self, query: str) -> list[SourceSearchResult]:
        assert query == "Sample Work Alpha"
        return []


class FakeAutoAdapter:
    async def search(self, query: str) -> list[SourceSearchResult]:
        assert query == "Sample Work Alpha"
        return [
            SourceSearchResult(
                source_candidate_id="XC-001",
                title="Sample Work Alpha",
                url="https://xchina.example.test/videos/xc-001.html",
                thumbnail_url="https://images.example.test/thumb.jpg",
            )
        ]

    async def fetch_video_detail(self, url: str) -> SourceVideoDetail:
        assert url.endswith("xc-001.html")
        return SourceVideoDetail(
            source_id="XC-001",
            source_url=url,
            title="Sample Work Alpha",
            poster=SourceAsset(url="https://images.example.test/poster.jpg", kind="poster"),
            fanart=SourceAsset(url="https://images.example.test/fanart.jpg", kind="fanart"),
            is_complete=True,
        )

    async def fetch_asset(self, url: str) -> FetchedAsset:
        return FetchedAsset(url=url, content=b"asset-bytes", content_type="image/jpeg")


class SearchMetadataOnlyAutoAdapter(FakeAutoAdapter):
    async def search(self, query: str) -> list[SourceSearchResult]:
        assert query == "Sample Work Alpha"
        return [
            SourceSearchResult(
                source_candidate_id="XC-001",
                title="Sample Work Alpha",
                url="https://xchina.example.test/videos/xc-001.html",
                release_date="2026-01-02",
                thumbnail_url="https://images.example.test/thumb.jpg",
                actors=[SourceActorRef(name="Actor One", source_id="ACT-001")],
                studio="Studio One",
                series="Series One",
            )
        ]

    async def fetch_video_detail(self, url: str) -> SourceVideoDetail:
        detail = await super().fetch_video_detail(url)
        return detail.model_copy(
            update={
                "source_id": "",
                "source_url": "",
                "title": "",
                "release_date": None,
                "studio": None,
                "series": None,
                "actors": [],
                "poster": None,
                "is_complete": False,
                "completeness_flags": ["source_id", "title", "poster", "actors"],
            }
        )


class FailingAutoSearchAdapter:
    async def search(self, query: str) -> list[SourceSearchResult]:
        raise RuntimeError("FlareSolverr request failed")


def test_worker_leases_pending_jobs_and_resumes_expired_leases(tmp_path: Path) -> None:
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            job = JobService(session).create_job(media_identity="media-a")
            session.commit()
            job_id = job.id

        worker = Worker(sessionmaker, worker_id="worker-1")
        assert asyncio.run(worker.run_once()) is True

        with sessionmaker() as session:
            loaded = session.get(Job, job_id)
            assert loaded is not None
            assert loaded.state == "waiting_stable"
            loaded.state = "searching"
            loaded.lease_owner = "dead-worker"
            loaded.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.commit()

        resumed = Worker(
            sessionmaker,
            worker_id="worker-2",
            handlers={"searching": lambda job: "matched"},
        )
        assert asyncio.run(resumed.run_once()) is True

        with sessionmaker() as session:
            loaded = session.get(Job, job_id)
            assert loaded is not None
            assert loaded.state == "matched"
            assert loaded.lease_owner is None
    finally:
        engine.dispose()


def test_cancelled_jobs_are_not_processed_by_worker(tmp_path: Path) -> None:
    engine, sessionmaker = _database(tmp_path)
    try:
        with sessionmaker() as session:
            service = JobService(session)
            job = service.create_job(media_identity="media-a")
            service.cancel_job(job.id)
            session.commit()

        called = False

        def handler(job: Job) -> str:
            nonlocal called
            called = True
            return "waiting_stable"

        worker = Worker(sessionmaker, handlers={"discovered": handler})
        assert asyncio.run(worker.run_once()) is False
        assert called is False
    finally:
        engine.dispose()


def test_auto_worker_uses_saved_xchina_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeSavedSettingsFlareSolverr.instances.clear()
    FakeSavedSettingsXChina.instances.clear()
    monkeypatch.setattr(worker_module, "FlareSolverrClient", FakeSavedSettingsFlareSolverr)
    monkeypatch.setattr(worker_module, "XChinaAdapter", FakeSavedSettingsXChina)

    root = tmp_path / "media"
    source = root / "incoming"
    destination = root / "organized"
    source.mkdir(parents=True)
    destination.mkdir()
    media_file = source / "Sample.Work.Alpha.mkv"
    media_file.write_bytes(b"movie-bytes")
    settings = Settings(config_dir=tmp_path / "config", storage_roots=(root,))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    sessionmaker = get_sessionmaker(engine)
    try:
        with sessionmaker() as session:
            SettingsStore(session).update_app_settings(
                {
                    "xchina": {
                        "base_url": "https://auto.xchina.test",
                        "flaresolverr_url": "http://solver:8191/v1",
                        "proxy_url": "http://proxy:8080",
                    }
                }
            )
            session.add(
                WatchRule(
                    rule_id="rule-auto",
                    source_directory=str(source),
                    destination_directory=str(destination),
                    recursive=True,
                    realtime=True,
                    polling_interval_seconds=60,
                    stability_seconds=0,
                    stable_check_count=1,
                    organization_mode="copy",
                    folder_templates=["{studio}", "{title}"],
                    filename_template="{xchina_id} - {title}",
                    asset_policy="strict",
                    emby_options={},
                    metadata_options={},
                    include_patterns=["*.mkv"],
                    exclude_patterns=[],
                    excluded_destination_prefixes=[],
                    confidence_threshold=92,
                    enabled=True,
                )
            )
            job = JobService(session).create_job(
                media_identity="media-auto",
                rule_id="rule-auto",
                manual=False,
                state="searching",
                payload={"last_seen_path": str(media_file)},
            )
            session.commit()
            job_id = job.id

        worker = Worker(sessionmaker, settings=settings, poll_interval_seconds=0)
        assert asyncio.run(worker.run_once()) is True

        with sessionmaker() as session:
            loaded = session.get(Job, job_id)
            assert loaded is not None
            assert loaded.state == "review_required"
            assert "search_adapter_unconfigured" not in loaded.payload["auto"]["gate_reasons"]
        assert FakeSavedSettingsFlareSolverr.instances
        assert FakeSavedSettingsFlareSolverr.instances[0].url == "http://solver:8191/v1"
        assert FakeSavedSettingsFlareSolverr.instances[0].proxy_url == "http://proxy:8080"
        assert FakeSavedSettingsFlareSolverr.instances[0].closed is False
        asyncio.run(worker.close())
        assert FakeSavedSettingsFlareSolverr.instances[0].closed is True
        assert FakeSavedSettingsXChina.instances[0].base_url == "https://auto.xchina.test"
    finally:
        engine.dispose()


def test_auto_worker_sends_search_source_failure_to_review_without_retrying_job(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = root / "incoming"
    destination = root / "organized"
    source.mkdir(parents=True)
    destination.mkdir()
    media_file = source / "Sample.Work.Alpha.mkv"
    media_file.write_bytes(b"movie-bytes")
    settings = Settings(config_dir=tmp_path / "config", storage_roots=(root,))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    sessionmaker = get_sessionmaker(engine)
    try:
        with sessionmaker() as session:
            session.add(
                WatchRule(
                    rule_id="rule-auto-source-failure",
                    source_directory=str(source),
                    destination_directory=str(destination),
                    recursive=True,
                    realtime=True,
                    polling_interval_seconds=60,
                    stability_seconds=0,
                    stable_check_count=1,
                    organization_mode="copy",
                    folder_templates=["{studio}", "{title}"],
                    filename_template="{xchina_id} - {title}",
                    asset_policy="strict",
                    emby_options={},
                    metadata_options={},
                    include_patterns=["*.mkv"],
                    exclude_patterns=[],
                    excluded_destination_prefixes=[],
                    confidence_threshold=92,
                    enabled=True,
                )
            )
            job = JobService(session).create_job(
                media_identity="media-auto-source-failure",
                rule_id="rule-auto-source-failure",
                manual=False,
                state="searching",
                payload={"last_seen_path": str(media_file)},
            )
            session.commit()
            job_id = job.id

        worker = Worker(
            sessionmaker,
            settings=settings,
            search_adapter=FailingAutoSearchAdapter(),
            poll_interval_seconds=0,
        )
        assert asyncio.run(worker.run_once()) is True

        with sessionmaker() as session:
            loaded = session.get(Job, job_id)
            assert loaded is not None
            assert loaded.state == "review_required"
            assert loaded.attempts == 0
            auto_payload = loaded.payload["auto"]
            assert auto_payload["gate_reasons"] == ["search_source_unavailable"]
            assert auto_payload["candidate_ids"] == []
            assert auto_payload["search_error"] == "search_source_unavailable"
            assert auto_payload["search_query_id"]
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("metadata_options", "expected_include_source_snapshot"),
    [
        ({}, True),
        ({"include_source_snapshot": False}, False),
    ],
)
def test_auto_worker_passes_snapshot_default_to_asset_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata_options: dict[str, object],
    expected_include_source_snapshot: bool,
) -> None:
    seen: list[bool] = []

    def fake_select_assets(
        _record,
        *,
        include_source_snapshot: bool = False,
    ) -> AssetSelection:
        seen.append(include_source_snapshot)
        return AssetSelection()

    monkeypatch.setattr(worker_module, "select_assets", fake_select_assets)

    root = tmp_path / "media"
    source = root / "incoming"
    destination = root / "organized"
    source.mkdir(parents=True)
    destination.mkdir()
    media_file = source / "Sample.Work.Alpha.mkv"
    media_file.write_bytes(b"movie-bytes")
    settings = Settings(config_dir=tmp_path / "config", storage_roots=(root,))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    sessionmaker = get_sessionmaker(engine)
    try:
        with sessionmaker() as session:
            SettingsStore(session).update_app_settings(
                {
                    "organization_defaults": {
                        "include_source_snapshot": True,
                    }
                }
            )
            session.add(
                WatchRule(
                    rule_id="rule-auto-snapshot",
                    source_directory=str(source),
                    destination_directory=str(destination),
                    recursive=True,
                    realtime=True,
                    polling_interval_seconds=60,
                    stability_seconds=0,
                    stable_check_count=1,
                    organization_mode="copy",
                    folder_templates=["{studio}", "{title}"],
                    filename_template="{xchina_id} - {title}",
                    asset_policy="strict",
                    emby_options={},
                    metadata_options=metadata_options,
                    include_patterns=["*.mkv"],
                    exclude_patterns=[],
                    excluded_destination_prefixes=[],
                    confidence_threshold=60,
                    enabled=True,
                )
            )
            job = JobService(session).create_job(
                media_identity=f"media-auto-snapshot-{expected_include_source_snapshot}",
                rule_id="rule-auto-snapshot",
                manual=False,
                state="searching",
                payload={"last_seen_path": str(media_file)},
            )
            session.commit()
            job_id = job.id

        adapter = FakeAutoAdapter()
        worker = Worker(
            sessionmaker,
            settings=settings,
            search_adapter=adapter,
            asset_adapter=adapter,
            poll_interval_seconds=0,
        )
        assert asyncio.run(worker.run_once()) is True

        with sessionmaker() as session:
            loaded = session.get(Job, job_id)
            assert loaded is not None
            assert loaded.state == "matched"
        assert seen == [expected_include_source_snapshot]
    finally:
        engine.dispose()


def test_auto_worker_plan_uses_search_result_metadata_when_detail_is_missing_it(
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = root / "incoming"
    destination = root / "organized"
    source.mkdir(parents=True)
    destination.mkdir()
    media_file = source / "Sample.Work.Alpha.mkv"
    media_file.write_bytes(b"movie-bytes")
    settings = Settings(config_dir=tmp_path / "config", storage_roots=(root,))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    sessionmaker = get_sessionmaker(engine)
    try:
        with sessionmaker() as session:
            session.add(
                WatchRule(
                    rule_id="rule-auto-search-series",
                    source_directory=str(source),
                    destination_directory=str(destination),
                    recursive=True,
                    realtime=True,
                    polling_interval_seconds=60,
                    stability_seconds=0,
                    stable_check_count=1,
                    organization_mode="copy",
                    folder_templates=[],
                    filename_template=(
                        "{studio} - {series} - {release_date} - {title}"
                    ),
                    asset_policy="strict",
                    emby_options={},
                    metadata_options={},
                    include_patterns=["*.mkv"],
                    exclude_patterns=[],
                    excluded_destination_prefixes=[],
                    confidence_threshold=60,
                    enabled=True,
                )
            )
            job = JobService(session).create_job(
                media_identity="media-auto-search-series",
                rule_id="rule-auto-search-series",
                manual=False,
                state="searching",
                payload={"last_seen_path": str(media_file)},
            )
            session.commit()
            job_id = job.id

        adapter = SearchMetadataOnlyAutoAdapter()
        worker = Worker(
            sessionmaker,
            settings=settings,
            search_adapter=adapter,
            asset_adapter=adapter,
            poll_interval_seconds=0,
        )
        for _ in range(5):
            assert asyncio.run(worker.run_once()) is True

        with sessionmaker() as session:
            loaded = session.get(Job, job_id)
            assert loaded is not None
            assert loaded.state == "ready"
            auto_payload = loaded.payload["auto"]
            metadata = auto_payload["metadata"]
            assert metadata["xchina_id"] == "XC-001"
            assert metadata["source_url"] == "https://xchina.example.test/videos/xc-001.html"
            assert metadata["title"] == "Sample Work Alpha"
            assert metadata["studio"] == "Studio One"
            assert metadata["series"] == "Series One"
            assert metadata["release_date"] == "2026-01-02"
            media_steps = [
                step
                for step in auto_payload["previewed_plan"]["steps"]
                if step["category"] == "media"
            ]
            assert Path(media_steps[0]["target_path"]).name == (
                "Studio One - Series One - 2026-01-02 - Sample Work Alpha.mkv"
            )
    finally:
        engine.dispose()
