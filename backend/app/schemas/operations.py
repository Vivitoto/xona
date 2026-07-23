from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


OrganizationMode = Literal["preview", "in_place", "move", "copy", "hardlink", "symlink"]
OperationName = Literal[
    "preview",
    "rename",
    "move",
    "copy",
    "hardlink",
    "symlink",
    "write_generated",
]
OperationCategory = Literal["media", "sidecar", "asset", "generated_artifact", "actor_output"]


class FrozenOperationModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class GeneratedArtifact(FrozenOperationModel):
    relative_path: str
    artifact_type: str = "metadata"
    content_text: str | None = None
    expected_size_bytes: int | None = None
    sha256: str | None = None
    allow_replace_existing: bool = False


class OperationFileSnapshot(FrozenOperationModel):
    path: Path
    kind: str
    expected_size_bytes: int | None = None
    mtime_ns: int | None = None
    sha256: str | None = None
    sidecar: bool = False
    materialized_asset: bool = False
    generated_artifact: bool = False
    actor_output: bool = False


class OperationConflict(FrozenOperationModel):
    target_path: Path
    reason: str
    source_path: Path | None = None
    allowed: bool = False


class OperationSafetyWarning(FrozenOperationModel):
    code: str
    message: str
    path: Path | None = None


class OperationStep(FrozenOperationModel):
    step_id: str
    operation: OperationName
    category: OperationCategory
    source_path: Path | None = None
    target_path: Path
    temp_parent_path: Path
    expected_size_bytes: int | None = None
    mtime_ns: int | None = None
    sha256: str | None = None
    sidecar: bool = False
    materialized_asset: bool = False
    generated_artifact: bool = False
    actor_output: bool = False
    destructive: bool = False
    allow_existing_generated_replacement: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationPlan(FrozenOperationModel):
    plan_id: str
    version: int = 1
    database_id: int | None = None
    job_id: int | None = None
    mode: OrganizationMode
    destination_root: Path
    target_directory: Path
    source_snapshot: tuple[OperationFileSnapshot, ...] = ()
    materialized_asset_cache_paths: tuple[Path, ...] = ()
    steps: tuple[OperationStep, ...] = ()
    conflicts: tuple[OperationConflict, ...] = ()
    safety_warnings: tuple[OperationSafetyWarning, ...] = ()
    created_at: datetime

    def snapshot_json(self) -> dict[str, Any]:
        snapshot = self.model_dump(mode="json")
        snapshot.pop("database_id", None)
        return snapshot
