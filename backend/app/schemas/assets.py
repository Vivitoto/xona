from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


DEFAULT_ALLOWED_CONTENT_TYPES = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "video/mp4",
    "text/html",
    "application/json",
)


class LogicalAsset(BaseModel):
    kind: str
    relative_path: str
    source_url: str | None = None
    required: bool = False
    missing_reason: str | None = None
    content_type: str | None = None
    inline_bytes: bytes | None = None
    actor_name: str | None = None
    actor_source_id: str | None = None


class MissingAsset(BaseModel):
    kind: str
    relative_path: str
    required: bool = False
    reason: str


class AssetSelection(BaseModel):
    assets: list[LogicalAsset] = Field(default_factory=list)
    missing_required: list[MissingAsset] = Field(default_factory=list)


class AssetMaterializationPolicy(BaseModel):
    strict: bool = True
    max_bytes: int = 10 * 1024 * 1024
    allowed_content_types: tuple[str, ...] = DEFAULT_ALLOWED_CONTENT_TYPES


class MaterializedAsset(BaseModel):
    kind: str
    relative_path: str
    source_url: str | None = None
    cache_path: Path
    content_type: str
    size_bytes: int
    sha256: str
    actor_name: str | None = None
    actor_source_id: str | None = None


class MaterializedAssetSet(BaseModel):
    assets: list[MaterializedAsset] = Field(default_factory=list)
    missing: list[MissingAsset] = Field(default_factory=list)
    failed: bool = False

    def by_relative_path(self, relative_path: str) -> MaterializedAsset | None:
        for asset in self.assets:
            if asset.relative_path == relative_path:
                return asset
        return None
