from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.app.core.redaction import redact_payload
from backend.app.db.models import Job, JobEvent
from backend.app.schemas.jobs import JOB_STATES


TERMINAL_STATES = {"completed", "failed", "cancelled", "rolled_back"}
ACTIVE_STATES = set(JOB_STATES) - TERMINAL_STATES
PROCESSABLE_STATES = {
    "discovered",
    "waiting_stable",
    "searching",
    "matched",
    "scraping",
    "materializing_assets",
    "planning",
    "ready",
    "executing",
    "notifying_emby",
}
VALID_TRANSITIONS = {
    "discovered": {"waiting_stable", "searching", "failed", "cancelled"},
    "waiting_stable": {"searching", "failed", "cancelled"},
    "searching": {"review_required", "matched", "failed", "cancelled"},
    "review_required": {"matched", "failed", "cancelled"},
    "matched": {"scraping", "failed", "cancelled"},
    "scraping": {"materializing_assets", "failed", "cancelled"},
    "materializing_assets": {"planning", "failed", "cancelled"},
    "planning": {"ready", "failed", "cancelled"},
    "ready": {"executing", "failed", "cancelled"},
    "executing": {"notifying_emby", "completed", "failed", "cancelled"},
    "notifying_emby": {"completed", "local_complete_emby_failed", "failed", "cancelled"},
    "local_complete_emby_failed": {
        "notifying_emby",
        "completed",
        "failed",
        "cancelled",
        "rolled_back",
    },
    "completed": {"rolled_back"},
    "failed": {"rolled_back"},
    "cancelled": {"rolled_back"},
    "rolled_back": set(),
}


class InvalidJobTransition(ValueError):
    pass


class JobService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_job(
        self,
        *,
        media_identity: str,
        rule_id: str | None = None,
        manual: bool = False,
        payload: dict[str, Any] | None = None,
        state: str = "discovered",
    ) -> Job:
        if state not in JOB_STATES:
            raise ValueError(f"Unknown job state: {state}")
        self._ensure_no_active_duplicate(
            media_identity=media_identity,
            rule_id=rule_id,
            manual=manual,
        )
        now = _utcnow()
        job = Job(
            rule_id=rule_id,
            media_identity=media_identity,
            manual=manual,
            state=state,
            payload=redact_payload(payload or {}),
            next_run_at=now,
            created_at=now,
            updated_at=now,
        )
        self._session.add(job)
        self._session.flush()
        self._write_event(job, None, state, payload or {})
        return job

    def list_jobs(self, *, state: str | None = None, manual: bool | None = None) -> list[Job]:
        statement = select(Job).order_by(Job.created_at.desc(), Job.id.desc())
        if state is not None:
            statement = statement.where(Job.state == state)
        if manual is not None:
            statement = statement.where(Job.manual.is_(manual))
        return list(self._session.scalars(statement))

    def get_job(self, job_id: int) -> Job:
        return self._get_job(job_id)

    def list_events(self, job_id: int) -> list[JobEvent]:
        self._get_job(job_id)
        return list(
            self._session.scalars(
                select(JobEvent)
                .where(JobEvent.job_id == job_id)
                .order_by(JobEvent.created_at, JobEvent.id)
            )
        )

    def transition_job(
        self,
        job_id: int,
        to_state: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> Job:
        job = self._get_job(job_id)
        if to_state not in JOB_STATES:
            raise InvalidJobTransition(f"Unknown job state: {to_state}")
        if to_state not in VALID_TRANSITIONS[job.state]:
            raise InvalidJobTransition(f"Invalid transition: {job.state} -> {to_state}")
        from_state = job.state
        job.state = to_state
        job.updated_at = _utcnow()
        if to_state in TERMINAL_STATES or to_state == "review_required":
            job.lease_owner = None
            job.lease_expires_at = None
        self._write_event(job, from_state, to_state, payload or {})
        self._session.flush()
        return job

    def cancel_job(
        self,
        job_id: int,
        *,
        payload: dict[str, Any] | None = None,
    ) -> Job:
        job = self._get_job(job_id)
        if job.state == "cancelled":
            return job
        if "cancelled" not in VALID_TRANSITIONS[job.state]:
            raise InvalidJobTransition(f"Cannot cancel job from state {job.state}")
        return self.transition_job(job.id, "cancelled", payload=payload)

    def retry_job(self, job_id: int) -> Job:
        job = self._get_job(job_id)
        if job.state not in {"failed", "review_required"}:
            raise InvalidJobTransition(f"Cannot retry job from state {job.state}")
        from_state = job.state
        job.state = "searching" if from_state == "review_required" else "discovered"
        job.attempts = 0
        job.last_error_code = None
        job.next_run_at = _utcnow()
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = _utcnow()
        self._write_event(
            job,
            from_state,
            job.state,
            {"retry": True, "retry_scope": "full"},
        )
        self._session.flush()
        return job

    def retry_emby(self, job_id: int) -> Job:
        job = self._get_job(job_id)
        if job.state != "local_complete_emby_failed":
            raise InvalidJobTransition(f"Cannot retry Emby from state {job.state}")
        job.next_run_at = _utcnow()
        job.lease_owner = None
        job.lease_expires_at = None
        return self.transition_job(
            job.id,
            "notifying_emby",
            payload={"retry": True, "retry_scope": "emby"},
        )

    def schedule_retry(
        self,
        job: Job,
        *,
        error_code: str,
        base_delay_seconds: int = 60,
    ) -> Job:
        job.attempts += 1
        job.last_error_code = error_code
        job.updated_at = _utcnow()
        if job.attempts >= job.max_attempts:
            if "failed" in VALID_TRANSITIONS[job.state]:
                self.transition_job(
                    job.id,
                    "failed",
                    payload={"error_code": error_code, "attempts": job.attempts},
                )
            return job
        delay = base_delay_seconds * (2 ** (job.attempts - 1))
        job.next_run_at = _utcnow() + timedelta(seconds=delay)
        job.lease_owner = None
        job.lease_expires_at = None
        self._write_event(
            job,
            job.state,
            job.state,
            {"retry": True, "error_code": error_code, "attempts": job.attempts},
        )
        self._session.flush()
        return job

    def lease_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> Job | None:
        now = _as_naive_utc(now or _utcnow())
        statement = (
            select(Job)
            .where(
                Job.state.in_(PROCESSABLE_STATES),
                or_(Job.next_run_at.is_(None), Job.next_run_at <= now),
                or_(Job.lease_owner.is_(None), Job.lease_expires_at <= now),
            )
            .order_by(Job.next_run_at, Job.id)
            .limit(1)
        )
        job = self._session.scalar(statement)
        if job is None:
            return None
        job.lease_owner = worker_id
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.updated_at = now
        self._session.flush()
        return job

    def release_lease(self, job: Job) -> None:
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = _utcnow()
        self._session.flush()

    def _ensure_no_active_duplicate(
        self,
        *,
        media_identity: str,
        rule_id: str | None,
        manual: bool,
    ) -> None:
        if manual:
            duplicate = self._session.scalar(
                select(Job).where(
                    Job.manual.is_(True),
                    Job.media_identity == media_identity,
                    Job.state.in_(ACTIVE_STATES),
                )
            )
        else:
            duplicate = self._session.scalar(
                select(Job).where(
                    Job.manual.is_(False),
                    Job.rule_id == rule_id,
                    Job.media_identity == media_identity,
                    Job.state.in_(ACTIVE_STATES),
                )
            )
        if duplicate is not None:
            raise ValueError("An active job already exists for this media identity")

    def _get_job(self, job_id: int) -> Job:
        job = self._session.get(Job, job_id)
        if job is None:
            raise ValueError("Job not found")
        return job

    def _write_event(
        self,
        job: Job,
        from_state: str | None,
        to_state: str,
        payload: dict[str, Any],
    ) -> None:
        self._session.add(
            JobEvent(
                job_id=job.id,
                from_state=from_state,
                to_state=to_state,
                payload=redact_payload(payload),
                created_at=_utcnow(),
            )
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
