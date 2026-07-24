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
from backend.app.schemas.source import SourceSearchResult
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
    def __init__(self, flaresolverr: FakeSavedSettingsFlareSolverr, session) -> None:
        self.flaresolverr = flaresolverr
        self.session = session

    async def search(self, query: str) -> list[SourceSearchResult]:
        assert query == "Sample Work Alpha"
        return []


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
        assert FakeSavedSettingsFlareSolverr.instances[0].closed is True
    finally:
        engine.dispose()
