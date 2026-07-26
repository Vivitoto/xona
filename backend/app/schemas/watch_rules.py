from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.operations import AssetPolicy, OrganizationMode


class WatchRuleCreate(BaseModel):
    source_directory: Path
    destination_directory: Path | None = None
    recursive: bool = True
    realtime: bool = True
    polling_interval_seconds: int = Field(default=60, ge=1)
    stability_seconds: int = Field(default=30, ge=0)
    stable_check_count: int = Field(default=2, ge=1)
    organization_mode: OrganizationMode | None = None
    folder_templates: list[str] = Field(default_factory=list)
    filename_template: str | None = None
    asset_policy: AssetPolicy | None = None
    emby_options: dict[str, Any] = Field(default_factory=dict)
    metadata_options: dict[str, Any] = Field(default_factory=dict)
    include_patterns: list[str] = Field(default_factory=lambda: ["*"])
    exclude_patterns: list[str] = Field(default_factory=list)
    excluded_destination_prefixes: list[Path] = Field(default_factory=list)
    confidence_threshold: int = Field(default=92, ge=0, le=100)
    enabled: bool = True

    @field_validator("destination_directory", "filename_template", "asset_policy", mode="before")
    @classmethod
    def empty_string_as_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class WatchRuleUpdate(BaseModel):
    source_directory: Path | None = None
    destination_directory: Path | None = None
    recursive: bool | None = None
    realtime: bool | None = None
    polling_interval_seconds: int | None = Field(default=None, ge=1)
    stability_seconds: int | None = Field(default=None, ge=0)
    stable_check_count: int | None = Field(default=None, ge=1)
    organization_mode: OrganizationMode | None = None
    folder_templates: list[str] | None = None
    filename_template: str | None = None
    asset_policy: AssetPolicy | None = None
    emby_options: dict[str, Any] | None = None
    metadata_options: dict[str, Any] | None = None
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    excluded_destination_prefixes: list[Path] | None = None
    confidence_threshold: int | None = Field(default=None, ge=0, le=100)
    enabled: bool | None = None


class WatchRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    source_directory: Path
    destination_directory: Path
    recursive: bool
    realtime: bool
    polling_interval_seconds: int
    stability_seconds: int
    stable_check_count: int
    organization_mode: str
    folder_templates: list[str]
    filename_template: str
    asset_policy: str
    emby_options: dict[str, Any]
    metadata_options: dict[str, Any]
    include_patterns: list[str]
    exclude_patterns: list[str]
    excluded_destination_prefixes: list[Path]
    confidence_threshold: int
    enabled: bool


class WatchRuleList(BaseModel):
    rules: list[WatchRuleRead]


class ScanNowResponse(BaseModel):
    rule_id: str
    enqueued_jobs: list[int]
