from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.db.models import Job, OperationPlan
from backend.app.schemas.jobs import (
    JobActionResponse,
    JobEventsResponse,
    JobEventRead,
    JobListResponse,
    JobSummaryRead,
)
from backend.app.services.jobs import InvalidJobTransition, JobService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


async def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


@router.get("", response_model=JobListResponse)
async def list_jobs(
    state: str | None = None,
    session: Session = Depends(get_db),
) -> JobListResponse:
    service = JobService(session)
    jobs = service.list_jobs(state=state)
    logger.info("Jobs listed state=%s count=%s", state or "all", len(jobs))
    return JobListResponse(
        jobs=[_job_summary(session, job) for job in jobs]
    )


@router.get("/{job_id}", response_model=JobSummaryRead)
async def get_job(job_id: int, session: Session = Depends(get_db)) -> JobSummaryRead:
    try:
        job = JobService(session).get_job(job_id)
        logger.info("Job detail requested job_id=%s state=%s", job.id, job.state)
        return _job_summary(session, job)
    except ValueError as exc:
        logger.warning("Job detail rejected job_id=%s error=%s", job_id, exc)
        raise HTTPException(status_code=404, detail="Job not found") from exc


@router.get("/{job_id}/events", response_model=JobEventsResponse)
async def get_job_events(
    job_id: int,
    session: Session = Depends(get_db),
) -> JobEventsResponse:
    try:
        events = JobService(session).list_events(job_id)
    except ValueError as exc:
        logger.warning("Job events rejected job_id=%s error=%s", job_id, exc)
        raise HTTPException(status_code=404, detail="Job not found") from exc
    logger.info("Job events listed job_id=%s count=%s", job_id, len(events))
    return JobEventsResponse(
        events=[
            JobEventRead(
                id=event.id,
                job_id=event.job_id,
                from_state=event.from_state,
                to_state=event.to_state,
                payload=redact_payload(event.payload),
            )
            for event in events
        ]
    )


@router.post("/{job_id}/retry", response_model=JobActionResponse)
async def retry_job(
    job_id: int,
    session: Session = Depends(get_db),
) -> JobActionResponse:
    service = JobService(session)
    try:
        logger.info("Job retry requested job_id=%s", job_id)
        job = service.retry_job(job_id)
        session.commit()
    except (ValueError, InvalidJobTransition) as exc:
        session.rollback()
        logger.warning("Job retry rejected job_id=%s error=%s", job_id, redact_payload(str(exc)))
        raise HTTPException(status_code=400, detail=redact_payload(str(exc))) from exc
    logger.info("Job retry accepted job_id=%s state=%s", job.id, job.state)
    return JobActionResponse(job=_job_summary(session, job))


@router.post("/{job_id}/cancel", response_model=JobActionResponse)
async def cancel_job(
    job_id: int,
    session: Session = Depends(get_db),
) -> JobActionResponse:
    service = JobService(session)
    try:
        logger.info("Job cancel requested job_id=%s", job_id)
        job = service.cancel_job(job_id, payload={"cancelled_by": "api"})
        session.commit()
    except (ValueError, InvalidJobTransition) as exc:
        session.rollback()
        logger.warning("Job cancel rejected job_id=%s error=%s", job_id, redact_payload(str(exc)))
        raise HTTPException(status_code=400, detail=redact_payload(str(exc))) from exc
    logger.info("Job cancel accepted job_id=%s state=%s", job.id, job.state)
    return JobActionResponse(job=_job_summary(session, job))


def _job_summary(session: Session, job: Job) -> JobSummaryRead:
    payload = redact_payload(job.payload or {})
    manual = payload.get("manual") if isinstance(payload, dict) else None
    manual = manual if isinstance(manual, dict) else {}
    auto = payload.get("auto") if isinstance(payload, dict) else None
    auto = auto if isinstance(auto, dict) else {}
    plan_id = manual.get("plan_id") or _latest_plan_id(session, job.id)
    plan_id = plan_id or auto.get("plan_id")
    gate_reasons = (
        manual.get("selection_refusal_reasons")
        or manual.get("gate_reasons")
        or auto.get("gate_reasons")
        or []
    )
    return JobSummaryRead(
        id=job.id,
        state=job.state,
        media_identity=job.media_identity,
        rule_id=job.rule_id,
        manual=job.manual,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        next_run_at=job.next_run_at,
        last_error_code=job.last_error_code,
        payload=payload,
        plan_id=plan_id,
        selected_candidate=_selected_candidate_summary(manual),
        gate_reasons=[str(reason) for reason in gate_reasons],
        retryable=job.state in {"failed", "review_required"},
        retry_emby_available=job.state == "local_complete_emby_failed",
    )


def _latest_plan_id(session: Session, job_id: int) -> str | None:
    row = session.scalar(
        select(OperationPlan)
        .where(OperationPlan.job_id == job_id)
        .order_by(OperationPlan.created_at.desc(), OperationPlan.id.desc())
        .limit(1)
    )
    return row.plan_id if row is not None else None


def _selected_candidate_summary(manual: dict[str, Any]) -> dict[str, Any] | None:
    detail = manual.get("selected_detail")
    if not isinstance(detail, dict):
        return None
    return {
        "source_id": detail.get("source_id"),
        "title": detail.get("title"),
        "source_url": redact_payload(detail.get("source_url")),
    }
