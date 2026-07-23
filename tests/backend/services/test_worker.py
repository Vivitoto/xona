from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import Job
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.services.jobs import JobService
from backend.app.services.worker import Worker


def _database(tmp_path: Path):
    settings = Settings(config_dir=tmp_path / "config")
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return engine, get_sessionmaker(engine)


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
