from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.schemas.operations import OperationPlan


class OrganizeMetadataFlags(BaseModel):
    nfo: bool = False
    poster: bool = False
    fanart: bool = False
    thumb: bool = False
    backdrop: bool = False
    actors: bool = False


class OrganizeRecordRead(BaseModel):
    record_id: str
    display_index: str
    job_id: int | None = None
    plan_id: str | None = None
    short_plan_id: str | None = None
    name: str
    source_path: str | None = None
    target_path: str | None = None
    mode: str | None = None
    status: str
    verification_status: str
    metadata: OrganizeMetadataFlags = Field(default_factory=OrganizeMetadataFlags)
    created_at: datetime
    can_rollback: bool = False
    can_rerun: bool = False
    rerun_path: str | None = None
    source_paths: list[str] = Field(default_factory=list)
    target_paths: list[str] = Field(default_factory=list)
    plan: OperationPlan | None = None


class OrganizeRecordsResponse(BaseModel):
    records: list[OrganizeRecordRead]


class OrganizeRollbackResponse(BaseModel):
    record_id: str
    plan_id: str
    status: str
    reversed_steps: list[str] = Field(default_factory=list)
    refusal_reason: str | None = None
