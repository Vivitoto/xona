from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

import httpx
from sqlalchemy import select

from backend.app.core.settings import Settings
from backend.app.db.models import OperationPlan as OperationPlanModel
from backend.app.main import create_app
from backend.app.schemas.actors import ActorOutputPlan
from backend.app.schemas.assets import MaterializedAsset, MaterializedAssetSet
from backend.app.schemas.media import MediaScanItem
from backend.app.schemas.operations import GeneratedArtifact
from backend.app.schemas.templates import TemplatePreview
from backend.app.services.jobs import JobService
from backend.app.services.operation_executor import OperationExecutor, OperationJournal
from backend.app.services.organizer_plans import OrganizerPlanService
from backend.app.services.storage_roots import StorageRootService


ORIGIN = "http://testserver"


def test_organize_records_list_detail_filters_and_rollback(tmp_path: Path) -> None:
    root = tmp_path / "media"
    incoming = root / "incoming"
    destination = root / "organized"
    cache = root / "cache"
    incoming.mkdir(parents=True)
    destination.mkdir()
    cache.mkdir()
    source = _write(incoming / "movie.mkv", b"movie-bytes")
    failed_source = _write(incoming / "failed.mkv", b"failed-bytes")
    poster_cache = _write(cache / "poster.jpg", b"poster-bytes")
    actor_cache = _write(cache / "actor.jpg", b"actor-bytes")
    expected_target = destination / "Movie Title" / "Movie Title.mkv"
    settings = Settings(
        config_dir=tmp_path / "config",
        storage_roots=(root,),
        auth_enabled=False,
    )

    async def run() -> dict[str, httpx.Response]:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            with app.state.sessionmaker() as session:
                storage_roots = StorageRootService(settings, session)
                job_service = JobService(session)
                job = job_service.create_job(
                    media_identity="movie-identity",
                    state="ready",
                    manual=True,
                    payload={"selected_candidate": {"title": "Movie Title"}},
                )
                plan = OrganizerPlanService(session, storage_roots).create_plan(
                    mode="copy",
                    media_items=[_media_item(source, identity="movie-identity")],
                    destination_root=destination,
                    template_preview=TemplatePreview(
                        folder_path="Movie Title",
                        filename="Movie Title.mkv",
                    ),
                    materialized_assets=MaterializedAssetSet(
                        assets=[
                            MaterializedAsset(
                                kind="poster",
                                relative_path="poster.jpg",
                                cache_path=poster_cache,
                                content_type="image/jpeg",
                                size_bytes=poster_cache.stat().st_size,
                                sha256=_sha256(poster_cache.read_bytes()),
                            )
                        ],
                    ),
                    generated_artifacts=[
                        GeneratedArtifact(
                            relative_path="Movie Title.nfo",
                            content_text="<movie><title>Movie Title</title></movie>",
                            artifact_type="nfo",
                        )
                    ],
                    actor_output_plans=[
                        ActorOutputPlan(
                            operation="copy",
                            source_path=actor_cache,
                            destination_path=destination
                            / "Movie Title"
                            / ".actors"
                            / "Actor One.jpg",
                            relative_path=Path(".actors") / "Actor One.jpg",
                            destination_inside_root=True,
                            actor_name="Actor One",
                            actor_source_id="ACT-1",
                        )
                    ],
                    job_id=job.id,
                )
                job_service.transition_job(job.id, "executing")
                OperationExecutor(
                    storage_roots,
                    journal=OperationJournal(session),
                ).execute(plan)
                job_service.transition_job(job.id, "completed")
                completed_row = session.scalar(
                    select(OperationPlanModel).where(
                        OperationPlanModel.plan_id == plan.plan_id
                    )
                )
                assert completed_row is not None
                completed_row.status = "completed"

                failed_plan = OrganizerPlanService(session, storage_roots).create_plan(
                    mode="move",
                    media_items=[_media_item(failed_source, identity="failed-identity")],
                    destination_root=destination,
                    template_preview=TemplatePreview(
                        folder_path="Failed Title",
                        filename="Failed Title.mkv",
                    ),
                )
                failed_row = session.scalar(
                    select(OperationPlanModel).where(
                        OperationPlanModel.plan_id == failed_plan.plan_id
                    )
                )
                assert failed_row is not None
                failed_row.status = "failed"
                session.commit()

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=ORIGIN,
            ) as client:
                records = await client.get("/api/organize-records?limit=50")
                completed_record = next(
                    record
                    for record in records.json()["records"]
                    if record["name"] == "Movie Title"
                )
                target_mtime_ns = expected_target.stat().st_mtime_ns
                expected_target.write_bytes(b"modified-after-completion")
                modified_records = await client.get("/api/organize-records?limit=50")
                modified_filter = await client.get(
                    "/api/organize-records",
                    params={"status": "modified"},
                )
                expected_target.write_bytes(b"movie-bytes")
                os.utime(expected_target, ns=(target_mtime_ns, target_mtime_ns))
                detail = await client.get(
                    f"/api/organize-records/{completed_record['record_id']}"
                )
                rollbackable = await client.get(
                    "/api/organize-records",
                    params={"status": "rollbackable"},
                )
                mode = await client.get(
                    "/api/organize-records",
                    params={"mode": "copy"},
                )
                metadata = await client.get(
                    "/api/organize-records",
                    params={"metadata": "nfo"},
                )
                search = await client.get(
                    "/api/organize-records",
                    params={"q": "Movie Title"},
                )
                failed = await client.get(
                    "/api/organize-records",
                    params={"status": "failed"},
                )
                rollback = await client.post(
                    f"/api/organize-records/{completed_record['record_id']}/rollback",
                    headers={"Origin": ORIGIN},
                )
                return {
                    "records": records,
                    "detail": detail,
                    "modified_records": modified_records,
                    "modified_filter": modified_filter,
                    "rollbackable": rollbackable,
                    "mode": mode,
                    "metadata": metadata,
                    "search": search,
                    "failed": failed,
                    "rollback": rollback,
                    "after_rollback": await client.get(
                        "/api/organize-records",
                        params={"q": "Movie Title"},
                    ),
                }

    responses = asyncio.run(run())

    assert responses["records"].status_code == 200
    records = responses["records"].json()["records"]
    completed = next(record for record in records if record["name"] == "Movie Title")
    assert completed["display_index"].startswith("#")
    assert completed["status"] == "completed"
    assert completed["mode"] == "copy"
    assert completed["metadata"]["nfo"] is True
    assert completed["metadata"]["poster"] is True
    assert completed["metadata"]["actors"] is True
    assert completed["can_rollback"] is True
    assert completed["can_rerun"] is True

    modified_records = responses["modified_records"].json()["records"]
    modified = next(record for record in modified_records if record["name"] == "Movie Title")
    assert modified["status"] == "completed"
    assert modified["verification_status"] == "externally_modified"
    assert _record_names(responses["modified_filter"]) == ["Movie Title"]

    detail = responses["detail"].json()
    assert detail["record_id"] == completed["record_id"]
    assert detail["plan"]["plan_id"] == completed["plan_id"]
    assert detail["target_path"] == str(expected_target)

    assert _record_names(responses["rollbackable"]) == ["Movie Title"]
    assert _record_names(responses["mode"]) == ["Movie Title"]
    assert _record_names(responses["metadata"]) == ["Movie Title"]
    assert _record_names(responses["search"]) == ["Movie Title"]
    assert _record_names(responses["failed"]) == ["Failed Title"]

    rollback = responses["rollback"].json()
    assert responses["rollback"].status_code == 200
    assert rollback["record_id"] == completed["record_id"]
    assert rollback["status"] == "rolled_back"
    assert rollback["reversed_steps"]
    assert not expected_target.exists()
    assert source.exists()

    after_rollback = responses["after_rollback"].json()["records"][0]
    assert after_rollback["status"] == "rolled_back"
    assert after_rollback["can_rollback"] is False


def _record_names(response: httpx.Response) -> list[str]:
    assert response.status_code == 200
    return [record["name"] for record in response.json()["records"]]


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _media_item(path: Path, *, identity: str) -> MediaScanItem:
    stat = path.stat()
    return MediaScanItem(
        path=path,
        group_key=path.stem,
        identity=identity,
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
