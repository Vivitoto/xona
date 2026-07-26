from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.matching import ExecutionSafety
from backend.app.schemas.operations import AssetPolicy, OrganizationMode
from backend.app.schemas.source import SourceVideoDetail


class ManualMediaItemRead(BaseModel):
    path: Path
    group_key: str
    identity: str
    size_bytes: int
    multipart_index: int | None = None


class ManualScanRequest(BaseModel):
    directory: Path
    recursive: bool = True
    ignore_patterns: list[str] = Field(default_factory=list)


class ManualJobSummary(BaseModel):
    job_id: int
    state: str
    media_identity: str
    media_items: list[ManualMediaItemRead] = Field(default_factory=list)


class ManualScanResponse(BaseModel):
    scanned_count: int
    jobs: list[ManualJobSummary]


class ManualSearchRequest(BaseModel):
    job_id: int | None = None
    filename: str | None = None
    query: str | None = None
    normalized_query: str | None = None


class ManualCandidateCard(BaseModel):
    candidate_id: int
    source: str
    source_candidate_id: str
    title: str
    image_url: str | None = None
    actors: list[str] = Field(default_factory=list)
    studio: str | None = None
    series: str | None = None
    release_date: str | None = None
    url: str
    confidence_score: int
    score_breakdown: dict[str, int] = Field(default_factory=dict)


class ManualSearchResponse(BaseModel):
    job_id: int
    search_query_id: int
    query: str
    normalized_query: str
    candidates: list[ManualCandidateCard] = Field(default_factory=list)


class ManualSelectCandidateRequest(BaseModel):
    candidate_id: int | None = None
    source_url: str | None = None
    detail: SourceVideoDetail | None = None
    safety: ExecutionSafety = Field(default_factory=ExecutionSafety)
    strict_assets: bool = False


class ManualSelectCandidateResponse(BaseModel):
    job_id: int
    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    selected_candidate: ManualCandidateCard | None = None
    metadata_record_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ManualPreviewRequest(BaseModel):
    destination_root: Path
    mode: OrganizationMode = "copy"
    folder_templates: list[str] = Field(default_factory=lambda: ["{studio}", "{title}"])
    filename_template: str = "{title}"
    asset_policy: AssetPolicy = "lenient"
    include_source_snapshot: bool = False


class ManualOrganizeRequest(ManualPreviewRequest):
    pass


class ManualPreviewResponse(BaseModel):
    job_id: int
    plan_id: str
    metadata: dict[str, Any]
    materialized_assets: list[dict[str, Any]] = Field(default_factory=list)
    missing_assets: list[dict[str, Any]] = Field(default_factory=list)
    plan: dict[str, Any]


class ManualExecutePlanRequest(BaseModel):
    approved: bool
    plan_version: int = 1


class ManualExecutePlanResponse(BaseModel):
    plan_id: str
    job_id: int | None = None
    state: str


class ManualJobRead(BaseModel):
    job_id: int
    state: str
    payload: dict[str, Any]
    candidates: list[ManualCandidateCard] = Field(default_factory=list)
    selected_metadata: dict[str, Any] | None = None
    plan_id: str | None = None
