from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.integrations.xchina_config import DEFAULT_XCHINA_MAX_SEARCH_PAGES
from backend.app.schemas.emby import EmbyPathMapping
from backend.app.schemas.operations import AssetPolicy, OrganizationMode


class StorageSettings(BaseModel):
    roots: list[Path] = Field(default_factory=list)
    env_roots: list[Path] = Field(default_factory=list)


class XChinaSettings(BaseModel):
    base_url: str = "https://www.xchina.co"
    flaresolverr_url: str | None = None
    proxy_url: str | None = None
    cache_dir: Path | None = None
    max_search_pages: int = Field(default=DEFAULT_XCHINA_MAX_SEARCH_PAGES, ge=1)


class EmbySettings(BaseModel):
    enabled: bool = False
    server_url: str | None = None
    api_key: str | None = None
    path_mappings: list[EmbyPathMapping] = Field(default_factory=list)
    upload_actor_portraits: bool = True


class NamingSettings(BaseModel):
    folder_templates: list[str] = Field(default_factory=lambda: ["{studio}", "{title}"])
    filename_template: str = "{title}"


class MetadataAssetSettings(BaseModel):
    write_nfo: bool = True
    include_source_snapshot: bool = False
    asset_policy: AssetPolicy = "lenient"
    max_asset_bytes: int = Field(default=10 * 1024 * 1024, ge=1)


class OrganizationDefaultsSettings(BaseModel):
    destination_directory: Path | None = None
    organization_mode: OrganizationMode = "copy"
    folder_templates: list[str] = Field(default_factory=lambda: ["{studio}", "{title}"])
    filename_template: str = "{title}"
    asset_policy: AssetPolicy = "lenient"
    include_source_snapshot: bool = False


class ConfidenceSafetySettings(BaseModel):
    confidence_threshold: int = Field(default=92, ge=0, le=100)
    refuse_destination_collisions: bool = True
    refuse_unresolved_multipart: bool = True
    cache_dir: Path | None = None


class AuthSettings(BaseModel):
    enabled: bool = False
    username: str | None = None


class AppSettingsRead(BaseModel):
    storage: StorageSettings = Field(default_factory=StorageSettings)
    xchina: XChinaSettings = Field(default_factory=XChinaSettings)
    emby: EmbySettings = Field(default_factory=EmbySettings)
    naming: NamingSettings = Field(default_factory=NamingSettings)
    metadata_assets: MetadataAssetSettings = Field(default_factory=MetadataAssetSettings)
    organization_defaults: OrganizationDefaultsSettings = Field(
        default_factory=OrganizationDefaultsSettings
    )
    confidence_safety: ConfidenceSafetySettings = Field(default_factory=ConfidenceSafetySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)


class AppSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    storage: StorageSettings | None = None
    xchina: XChinaSettings | None = None
    emby: EmbySettings | None = None
    naming: NamingSettings | None = None
    metadata_assets: MetadataAssetSettings | None = None
    organization_defaults: OrganizationDefaultsSettings | None = None
    confidence_safety: ConfidenceSafetySettings | None = None
    auth: AuthSettings | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_defaults(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        migrated = dict(values)
        if "organization_defaults" not in migrated and "manual_defaults" in migrated:
            migrated["organization_defaults"] = migrated["manual_defaults"]
        migrated.pop("manual_defaults", None)
        return migrated


class FlareSolverrTestRequest(BaseModel):
    url: str | None = None
    test_url: str = "https://example.test/"
    proxy_url: str | None = None


class FlareSolverrTestResponse(BaseModel):
    ok: bool
    status_code: int | None = None
    elapsed_ms: int
    cloudflare_state: str = "unknown"
    cookie_count: int = 0
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class XChinaTestRequest(BaseModel):
    query: str = "sample"


class XChinaTestResponse(BaseModel):
    ok: bool
    candidate_count: int = 0
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class TemplatePreviewRequest(BaseModel):
    folder_templates: list[str]
    filename_template: str
    context: dict[str, Any] = Field(default_factory=dict)


class TemplatePreviewResponse(BaseModel):
    folder_path: str | None
    filename: str | None
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
