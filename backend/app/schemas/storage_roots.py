from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class StorageRootRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    path: Path
    source: str
    enabled: bool


class StorageRootList(BaseModel):
    roots: list[StorageRootRead]


class StorageRootCreate(BaseModel):
    path: Path


class StorageRootUpdate(BaseModel):
    path: Path | None = None
    enabled: bool | None = None


class BrowseEntry(BaseModel):
    name: str
    path: Path
    is_dir: bool


class BrowseResponse(BaseModel):
    root: StorageRootRead
    entries: list[BrowseEntry]


class ValidatePathRequest(BaseModel):
    path: Path


class ValidatePathResponse(BaseModel):
    inside_root: bool
    root_id: int
    relative_path: Path
