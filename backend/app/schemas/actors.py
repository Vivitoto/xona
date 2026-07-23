from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.operations import OperationName


class ActorOutputPlan(BaseModel):
    operation: OperationName
    source_path: Path
    destination_path: Path
    relative_path: Path
    destination_inside_root: bool
    actor_name: str
    actor_source_id: str | None = None


class ActorData(BaseModel):
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    source: str = "xchina"
    source_id: str | None = None
    profile_url: str | None = None
    portrait_source_url: str | None = None
    portrait_cache_path: Path | None = None
    biography: str | None = None
    profile_fields: dict[str, str] = Field(default_factory=dict)
    associated_works: list[dict[str, str]] = Field(default_factory=list)
    emby_person_id: str | None = None


class ActorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    source: str
    source_id: str | None = None
    profile_url: str | None = None
    portrait_source_url: str | None = None
    portrait_cache_path: str | None = None
    portrait_sha256: str | None = None
    portrait_size_bytes: int | None = None
    biography: str | None = None
    profile_fields: dict[str, Any] = Field(default_factory=dict)
    associated_works: list[dict[str, Any]] = Field(default_factory=list)
    emby_person_id: str | None = None
    linked_works: list[dict[str, Any]] = Field(default_factory=list)


class ActorListResponse(BaseModel):
    actors: list[ActorRead]


class ActorAliasesUpdate(BaseModel):
    aliases: list[str] = Field(default_factory=list)


class ActorMergeRequest(BaseModel):
    duplicate_actor_id: int


class ActorPortraitResponse(BaseModel):
    actor: ActorRead
    sha256: str
    size_bytes: int


class ActorRefreshResponse(BaseModel):
    actor: ActorRead
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ActorWorksResponse(BaseModel):
    actor_id: int
    works: list[dict[str, Any]] = Field(default_factory=list)


class ActorSyncEmbyResponse(BaseModel):
    actor: ActorRead
    uploaded_portrait: bool = False
    diagnostics: dict[str, Any] = Field(default_factory=dict)
