from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import Job
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.main import create_app
from backend.app.services.jobs import JobService
from backend.app.services.worker import Worker


ORIGIN = "http://testserver"


def test_emby_failure_keeps_local_complete_and_retry_is_emby_only(tmp_path: Path) -> None:
    settings = Settings(config_dir=tmp_path / "config", auth_enabled=False)
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    sessionmaker = get_sessionmaker(engine)
    try:
        with sessionmaker() as session:
            job = JobService(session).create_job(
                media_identity="media-a",
                state="notifying_emby",
                payload={"local_operations_complete": True},
            )
            session.commit()

        worker = Worker(
            sessionmaker,
            handlers={"notifying_emby": lambda _job: (_ for _ in ()).throw(RuntimeError("api_key=secret"))},
        )
        assert asyncio.run(worker.run_once()) is True

        with sessionmaker() as session:
            loaded = session.get(Job, job.id)
            assert loaded is not None
            assert loaded.state == "local_complete_emby_failed"
            assert loaded.payload["local_operations_complete"] is True

        async def run_api() -> httpx.Response:
            app = create_app(settings)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url=ORIGIN,
                ) as client:
                    return await client.post(
                        f"/api/jobs/{job.id}/retry-emby",
                        headers={"Origin": ORIGIN},
                    )

        response = asyncio.run(run_api())
        assert response.status_code == 200, response.text
        assert response.json() == {
            "job_id": job.id,
            "state": "notifying_emby",
            "retry_emby_only": True,
        }
    finally:
        engine.dispose()
