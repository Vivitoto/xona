from __future__ import annotations

from pydantic import BaseModel, Field


class MatchInput(BaseModel):
    search_text: str
    identifier: str | None = None
    title: str | None = None
    actors: list[str] = Field(default_factory=list)
    studio: str | None = None
    release_date: str | None = None
    parent_hint: str | None = None


class CandidateMetadata(BaseModel):
    source_id: str
    title: str
    original_title: str | None = None
    identifiers: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    studio: str | None = None
    series: str | None = None
    release_date: str | None = None
    complete: bool = False
    asset_ready: bool = False
    unique_detail: bool = True


class ScoreResult(BaseModel):
    candidate: CandidateMetadata
    total: int
    breakdown: dict[str, int]


class ExecutionSafety(BaseModel):
    unsafe_path: bool = False
    file_conflict: bool = False
    unresolved_multipart: bool = False
    strict_assets_missing: bool = False


class MatchDecision(BaseModel):
    action: str
    reasons: list[str] = Field(default_factory=list)
    selected: CandidateMetadata | None = None
    score: ScoreResult | None = None
