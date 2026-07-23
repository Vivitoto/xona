from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from sqlalchemy import select

from backend.app.core.settings import Settings
from backend.app.db.models import OperationPlan as OperationPlanModel
from backend.app.main import create_app
from backend.app.schemas.media import MediaScanItem
from backend.app.schemas.templates import TemplatePreview
from backend.app.services.jobs import JobService
from backend.app.services.operation_executor import OperationExecutor, OperationJournal
from backend.app.services.organizer_plans import OrganizerPlanService
from backend.app.services.storage_roots import StorageRootService


ORIGIN = "http://testserver"


def test_history_lists_plans_and_rollback_verifies_targets(tmp_path: Path) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    destination = root / "organized"
    incoming.mkdir(parents=True)
    destination.mkdir()
    source = incoming / "movie.mkv"
    source.write_bytes(b"movie")
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            with app.state.sessionmaker() as session:
                job = JobService(session).create_job(
                    media_identity="history-media",
                    state="ready",
                    manual=True,
                )
                stat = source.stat()
                item = MediaScanItem(
                    path=source,
                    group_key="movie",
                    identity="history-media",
                    size_bytes=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                )
                plan = OrganizerPlanService(
                    session,
                    StorageRootService(settings, session),
                ).create_plan(
                    mode="copy",
                    media_items=[item],
                    destination_root=destination,
                    template_preview=TemplatePreview(
                        folder_path="Movie",
                        filename="Movie",
                    ),
                    job_id=job.id,
                )
                JobService(session).transition_job(job.id, "executing")
                OperationExecutor(
                    StorageRootService(settings, session),
                    journal=OperationJournal(session),
                ).execute(plan)
                JobService(session).transition_job(job.id, "completed")
                row = session.scalar(
                    select(OperationPlanModel).where(
                        OperationPlanModel.plan_id == plan.plan_id
                    )
                )
                assert row is not None
                row.status = "completed"
                session.commit()

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                history = await client.get("/api/history/plans")
                plan_id = history.json()["plans"][0]["plan_id"]
                rollback = await client.post(
                    f"/api/plans/{plan_id}/rollback",
                    headers={"Origin": ORIGIN},
                )
                return {"history": history, "rollback": rollback}

    responses = asyncio.run(run())

    assert responses["history"].status_code == 200
    assert responses["history"].json()["plans"][0]["verification_status"] == "verified"
    assert responses["rollback"].json()["status"] == "rolled_back"
    assert not (destination / "Movie" / "Movie.mkv").exists()
