from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HistoryPlanRead(BaseModel):
    plan_id: str
    job_id: int | None = None
    mode: str
    status: str
    verification_status: str
    target_paths: list[str] = Field(default_factory=list)
    created_at: datetime


class HistoryPlansResponse(BaseModel):
    plans: list[HistoryPlanRead]


class RollbackResponse(BaseModel):
    plan_id: str
    status: str
    reversed_steps: list[str] = Field(default_factory=list)
    refusal_reason: str | None = None
