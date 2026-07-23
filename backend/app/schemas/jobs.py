from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


JOB_STATES = (
    "discovered",
    "waiting_stable",
    "searching",
    "review_required",
    "matched",
    "scraping",
    "materializing_assets",
    "planning",
    "ready",
    "executing",
    "notifying_emby",
    "completed",
    "local_complete_emby_failed",
    "failed",
    "cancelled",
    "rolled_back",
)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    state: str
    media_identity: str
    rule_id: str | None = None
    manual: bool = False
    attempts: int = 0
    max_attempts: int = 3
    next_run_at: datetime | None = None
    last_error_code: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class JobEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    from_state: str | None = None
    to_state: str
    payload: dict[str, Any] = Field(default_factory=dict)


class JobSummaryRead(JobRead):
    plan_id: str | None = None
    selected_candidate: dict[str, Any] | None = None
    gate_reasons: list[str] = Field(default_factory=list)
    retryable: bool = False
    retry_emby_available: bool = False


class JobListResponse(BaseModel):
    jobs: list[JobSummaryRead]


class JobEventsResponse(BaseModel):
    events: list[JobEventRead]


class JobActionResponse(BaseModel):
    job: JobSummaryRead
