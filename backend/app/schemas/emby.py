from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EmbyPathMapping(BaseModel):
    container_root: str
    emby_root: str


class EmbySettingsData(BaseModel):
    enabled: bool = False
    server_url: str | None = None
    api_key: str | None = None
    path_mappings: list[EmbyPathMapping] = Field(default_factory=list)
    upload_actor_portraits: bool = True


class EmbyTestRequest(BaseModel):
    server_url: str | None = None
    api_key: str | None = None
    path_mappings: list[EmbyPathMapping] | None = None


class EmbyLibrary(BaseModel):
    id: str | None = None
    name: str
    locations: list[str] = Field(default_factory=list)


class EmbyConnectionResponse(BaseModel):
    ok: bool
    authorized: bool
    server_version: str | None = None
    server_name: str | None = None
    libraries: list[EmbyLibrary] = Field(default_factory=list)
    diagnostics: dict[str, object] = Field(default_factory=dict)


class EmbyLibrariesResponse(BaseModel):
    libraries: list[EmbyLibrary] = Field(default_factory=list)


class EmbyRetryResponse(BaseModel):
    job_id: int
    state: str
    retry_emby_only: bool = True


class EmbyLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int | None = None
    job_id: int | None = None
    metadata_record_id: int | None = None
    actor_id: int | None = None
    local_path: str | None = None
    emby_path: str | None = None
    emby_item_id: str | None = None
    emby_person_id: str | None = None
