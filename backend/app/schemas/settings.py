from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.emby import EmbyPathMapping


class StorageSettings(BaseModel):
    roots: list[Path] = Field(default_factory=list)


class XChinaSettings(BaseModel):
    base_url: str = "https://www.xchina.co"
    flaresolverr_url: str | None = None
    proxy_url: str | None = None
    cache_dir: Path | None = None


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
    asset_policy: str = "lenient"
    max_asset_bytes: int = Field(default=10 * 1024 * 1024, ge=1)


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
    confidence_safety: ConfidenceSafetySettings = Field(
        default_factory=ConfidenceSafetySettings
    )
    auth: AuthSettings = Field(default_factory=AuthSettings)


class AppSettingsUpdate(BaseModel):
    storage: StorageSettings | None = None
    xchina: XChinaSettings | None = None
    emby: EmbySettings | None = None
    naming: NamingSettings | None = None
    metadata_assets: MetadataAssetSettings | None = None
    confidence_safety: ConfidenceSafetySettings | None = None
    auth: AuthSettings | None = None


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
