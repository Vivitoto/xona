from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import Job, OperationPlan as OperationPlanModel
from backend.app.schemas.operations import OperationPlan, OperationStep
from backend.app.schemas.organize_records import (
    OrganizeMetadataFlags,
    OrganizeRecordRead,
    OrganizeRecordsResponse,
    OrganizeRollbackResponse,
)
from backend.app.services.jobs import InvalidJobTransition, JobService
from backend.app.services.recovery import RecoveryService
from backend.app.services.rollback import RollbackRefused, RollbackService
from backend.app.services.storage_roots import StorageRootService

router = APIRouter(prefix="/api/organize-records", tags=["organize-records"])


async def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


@router.get("", response_model=OrganizeRecordsResponse)
async def list_organize_records(
    limit: int = Query(default=50, ge=1, le=500),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    metadata: str | None = Query(default=None),
    session: Session = Depends(get_db),
) -> OrganizeRecordsResponse:
    rows = list(
        session.scalars(
            select(OperationPlanModel).order_by(
                OperationPlanModel.created_at.desc(),
                OperationPlanModel.id.desc(),
            ).limit(limit * 4)
        )
    )
    jobs_by_id = _jobs_by_id(session, [row.job_id for row in rows if row.job_id is not None])
    records = [_record_from_plan(row, jobs_by_id.get(row.job_id)) for row in rows]
    records = [record for record in records if _record_matches(record, q=q, status=status, mode=mode, metadata=metadata)]
    return OrganizeRecordsResponse(records=records[:limit])


@router.get("/{record_id}", response_model=OrganizeRecordRead)
async def get_organize_record(
    record_id: str,
    session: Session = Depends(get_db),
) -> OrganizeRecordRead:
    row = _row_for_record_id(session, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Organize record not found")
    job = session.get(Job, row.job_id) if row.job_id is not None else None
    return _record_from_plan(row, job, include_plan=True)


@router.post("/{record_id}/rollback", response_model=OrganizeRollbackResponse)
async def rollback_organize_record(
    record_id: str,
    request: Request,
    session: Session = Depends(get_db),
) -> OrganizeRollbackResponse:
    row = _row_for_record_id(session, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Organize record not found")
    plan = _operation_plan(row)
    settings: Settings = request.app.state.settings
    storage_roots = StorageRootService(settings, session)
    try:
        result = RollbackService(storage_roots).rollback(plan)
    except RollbackRefused as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "rollback_refused", "reason": exc.reason},
        ) from exc
    row.status = "rolled_back"
    if row.job_id is not None:
        try:
            JobService(session).transition_job(
                row.job_id,
                "rolled_back",
                payload={"plan_id": row.plan_id, "record_id": _record_id(row)},
            )
        except (ValueError, InvalidJobTransition):
            pass
    session.commit()
    return OrganizeRollbackResponse(
        record_id=_record_id(row),
        plan_id=row.plan_id,
        status=row.status,
        reversed_steps=list(result.reversed_steps),
    )


def _jobs_by_id(session: Session, job_ids: list[int]) -> dict[int, Job]:
    if not job_ids:
        return {}
    return {
        job.id: job
        for job in session.scalars(select(Job).where(Job.id.in_(job_ids)))
    }


def _row_for_record_id(session: Session, record_id: str) -> OperationPlanModel | None:
    if record_id.startswith("job-"):
        try:
            job_id = int(record_id.removeprefix("job-"))
        except ValueError:
            return None
        return session.scalar(
            select(OperationPlanModel)
            .where(OperationPlanModel.job_id == job_id)
            .order_by(OperationPlanModel.created_at.desc(), OperationPlanModel.id.desc())
        )
    if record_id.startswith("planrow-"):
        try:
            row_id = int(record_id.removeprefix("planrow-"))
        except ValueError:
            return None
        return session.get(OperationPlanModel, row_id)
    return session.scalar(
        select(OperationPlanModel).where(OperationPlanModel.plan_id == record_id)
    )


def _record_from_plan(
    row: OperationPlanModel,
    job: Job | None,
    *,
    include_plan: bool = False,
) -> OrganizeRecordRead:
    plan = _operation_plan(row)
    verification = _verification_status(plan)
    source_paths = _source_paths(plan)
    target_paths = [str(step.target_path) for step in plan.steps]
    source_path = _primary_source_path(plan, source_paths)
    target_path = _primary_target_path(plan)
    metadata = _metadata_flags(plan.steps)
    status = _record_status(row, job, verification)
    rerun_path = target_path or source_path

    return OrganizeRecordRead(
        record_id=_record_id(row),
        display_index=f"#{job.id}" if job is not None else f"#{row.id}",
        job_id=job.id if job is not None else row.job_id,
        plan_id=row.plan_id,
        short_plan_id=_short_plan_id(row.plan_id),
        name=_display_name(plan, job, target_path, source_path),
        source_path=source_path,
        target_path=target_path,
        mode=row.mode,
        status=status,
        verification_status=verification,
        metadata=metadata,
        created_at=row.created_at,
        can_rollback=_can_rollback(row, plan, verification),
        can_rerun=rerun_path is not None,
        rerun_path=rerun_path,
        source_paths=source_paths,
        target_paths=target_paths,
        plan=plan if include_plan else None,
    )


def _operation_plan(row: OperationPlanModel) -> OperationPlan:
    return OperationPlan.model_validate(row.plan_json).model_copy(
        update={"database_id": row.id}
    )


def _verification_status(plan: OperationPlan) -> str:
    report = RecoveryService().inspect_plan(plan, verify_content_hash=False)
    if report.externally_modified:
        return "externally_modified"
    if report.partial:
        return "partial"
    if report.pending:
        return "pending"
    return "verified"


def _record_status(row: OperationPlanModel, job: Job | None, verification: str) -> str:
    if row.status == "rolled_back" or (job is not None and job.state == "rolled_back"):
        return "rolled_back"
    if row.status == "failed" or (job is not None and job.state == "failed"):
        return "failed"
    if verification == "externally_modified":
        return "externally_modified"
    if job is not None and job.state not in {"completed", "rolled_back", "failed", "cancelled"}:
        return job.state
    return _classified_row_status(row.status)


def _record_id(row: OperationPlanModel) -> str:
    return f"job-{row.job_id}" if row.job_id is not None else f"planrow-{row.id}"


def _short_plan_id(plan_id: str) -> str:
    if plan_id.startswith("plan_"):
        return plan_id[:13]
    return plan_id[:12]


def _display_name(
    plan: OperationPlan,
    job: Job | None,
    target_path: str | None,
    source_path: str | None,
) -> str:
    selected = job.payload.get("selected_candidate") if job is not None else None
    if isinstance(selected, dict) and isinstance(selected.get("title"), str):
        return selected["title"]
    for candidate in (target_path, str(plan.target_directory), source_path, job.media_identity if job is not None else None):
        if candidate:
            return Path(candidate).stem or Path(candidate).name or candidate
    return plan.plan_id


def _primary_source_path(plan: OperationPlan, source_paths: list[str]) -> str | None:
    media_step = next(
        (step for step in plan.steps if step.category == "media" and step.source_path is not None),
        None,
    )
    if media_step and media_step.source_path is not None:
        return str(media_step.source_path)
    return source_paths[0] if source_paths else None


def _primary_target_path(plan: OperationPlan) -> str | None:
    media_step = next((step for step in plan.steps if step.category == "media"), None)
    if media_step is not None:
        return str(media_step.target_path)
    return str(plan.target_directory) if plan.target_directory else None


def _source_paths(plan: OperationPlan) -> list[str]:
    paths: list[str] = []
    for snapshot in plan.source_snapshot:
        paths.append(str(snapshot.path))
    for step in plan.steps:
        if step.source_path is not None:
            paths.append(str(step.source_path))
    return _unique(paths)


def _metadata_flags(steps: tuple[OperationStep, ...]) -> OrganizeMetadataFlags:
    flags = OrganizeMetadataFlags()
    for step in steps:
        path = str(step.target_path).lower()
        name = Path(path).name.lower()
        if step.generated_artifact or step.operation == "write_generated":
            if name.endswith(".nfo"):
                flags.nfo = True
        if step.actor_output or step.category == "actor_output" or "/.actors/" in path:
            flags.actors = True
        if step.category in {"asset", "generated_artifact", "actor_output"}:
            if "poster" in name:
                flags.poster = True
            if "fanart" in name:
                flags.fanart = True
            if "thumb" in name:
                flags.thumb = True
            if "backdrop" in name:
                flags.backdrop = True
    return flags


def _can_rollback(row: OperationPlanModel, plan: OperationPlan, verification: str) -> bool:
    if row.status != "completed" or verification != "verified" or plan.mode == "preview":
        return False
    return any(step.operation != "preview" for step in plan.steps)


def _record_matches(
    record: OrganizeRecordRead,
    *,
    q: str | None,
    status: str | None,
    mode: str | None,
    metadata: str | None,
) -> bool:
    if status and status != "all":
        if status == "rollbackable":
            if not record.can_rollback:
                return False
        elif status == "modified":
            if record.verification_status != "externally_modified":
                return False
        elif record.status != status:
            return False
    if mode and mode != "all" and record.mode != mode:
        return False
    if metadata and metadata != "all" and not _metadata_matches(record.metadata, metadata):
        return False
    if q and q.strip():
        needle = q.strip().lower()
        haystack = "\n".join(
            value
            for value in [
                record.record_id,
                record.display_index,
                str(record.job_id or ""),
                record.plan_id or "",
                record.short_plan_id or "",
                record.name,
                record.source_path or "",
                record.target_path or "",
            ]
            if value
        ).lower()
        if needle not in haystack:
            return False
    return True


def _metadata_matches(flags: OrganizeMetadataFlags, metadata: str) -> bool:
    if metadata == "nfo":
        return flags.nfo
    if metadata == "cover":
        return flags.poster or flags.fanart or flags.thumb or flags.backdrop
    if metadata == "missing_nfo":
        return not flags.nfo
    if metadata == "missing_cover":
        return not (flags.poster or flags.fanart or flags.thumb or flags.backdrop)
    if metadata == "actors":
        return flags.actors
    return True


_CLASSIFIED_STATUSES = frozenset({
    "completed", "failed", "rolled_back", "approved", "planned",
})
_ACTIVE_STATE_LABELS: dict[str, str] = {
    "searching": "搜索中",
    "review_required": "待复核",
    "matched": "已匹配",
    "scraping": "搜刮元数据",
    "materializing_assets": "下载素材",
    "planning": "生成计划",
    "ready": "待执行",
    "executing": "执行中",
}


def _classified_row_status(raw: str) -> str:
    if raw in _CLASSIFIED_STATUSES:
        return raw
    return _ACTIVE_STATE_LABELS.get(raw, raw)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
