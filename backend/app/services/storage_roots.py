from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import StorageRoot
from backend.app.schemas.storage_roots import BrowseEntry


class StorageRootValidationError(ValueError):
    pass


@dataclass(frozen=True)
class RootValidation:
    root: StorageRoot
    path: Path
    relative_path: Path


@dataclass(frozen=True)
class ReconciliationReport:
    removed: list[str]
    missing: list[str]
    duplicates: list[str]
    invalid: list[str]


class StorageRootService:
    def __init__(self, settings: Settings, session: Session) -> None:
        self._settings = settings
        self._session = session

    def list_roots(self, *, include_disabled: bool = False) -> list[StorageRoot]:
        self._ensure_bootstrap_roots()
        statement = select(StorageRoot).order_by(StorageRoot.id)
        if not include_disabled:
            statement = statement.where(StorageRoot.enabled.is_(True))
        return list(self._session.scalars(statement))

    def add_root(self, path: Path | str) -> StorageRoot:
        normalized = self._normalize_root_path(path)
        existing = self._root_by_path(normalized)
        if existing is not None:
            if existing.source == "env":
                raise StorageRootValidationError("Cannot replace env-sourced storage root")
            existing.enabled = True
            return existing

        root = StorageRoot(path=str(normalized), source="user", enabled=True)
        self._session.add(root)
        self._session.flush()
        return root

    def update_root(
        self,
        root_id: int,
        *,
        path: Path | str | None = None,
        enabled: bool | None = None,
    ) -> StorageRoot:
        root = self._get_root(root_id, include_disabled=True)
        if root.source == "env":
            raise StorageRootValidationError("Cannot modify env-sourced storage root")
        if path is not None:
            root.path = str(self._normalize_root_path(path))
        if enabled is not None:
            root.enabled = enabled
        self._session.flush()
        return root

    def delete_root(self, root_id: int) -> None:
        root = self._get_root(root_id, include_disabled=True)
        if root.source == "env":
            raise StorageRootValidationError("Cannot delete env-sourced storage root")
        self._session.delete(root)
        self._session.flush()

    def validate_inside_root(self, path: Path | str) -> RootValidation:
        candidate = _decode_path(path)
        if _contains_nul(candidate):
            raise StorageRootValidationError("Path contains NUL")
        if not candidate.is_absolute():
            raise StorageRootValidationError("Path must be absolute")

        safe_candidate = _resolve_existing_path(candidate)
        for root in self.list_roots():
            root_path = Path(root.path)
            if not root_path.exists():
                raise StorageRootValidationError(f"Storage root does not exist: {root_path}")
            if not root_path.is_dir():
                raise StorageRootValidationError(f"Storage root is not a directory: {root_path}")
            resolved_root = root_path.resolve(strict=True)
            try:
                relative = safe_candidate.relative_to(resolved_root)
            except ValueError:
                continue
            return RootValidation(root=root, path=safe_candidate, relative_path=relative)

        raise StorageRootValidationError("Path is outside configured storage roots")

    def browse(self, root_id: int, relative_path: str | Path = "") -> list[BrowseEntry]:
        root = self._get_root(root_id)
        root_path = Path(root.path)
        if not root_path.exists():
            raise StorageRootValidationError(f"Storage root does not exist: {root_path}")
        if not root_path.is_dir():
            raise StorageRootValidationError(f"Storage root is not a directory: {root_path}")

        requested = _decode_path(relative_path)
        if _contains_nul(requested):
            raise StorageRootValidationError("Path contains NUL")
        if requested.is_absolute():
            target = requested
        else:
            if _has_parent_traversal(requested):
                raise StorageRootValidationError("Parent traversal is not allowed")
            target = root_path / requested

        resolved_root = root_path.resolve(strict=True)
        resolved_target = _resolve_existing_path(target)
        try:
            relative = resolved_target.relative_to(resolved_root)
        except ValueError as exc:
            raise StorageRootValidationError("Path escapes storage root") from exc
        if _has_parent_traversal(relative):
            raise StorageRootValidationError("Parent traversal is not allowed")
        if not resolved_target.exists():
            raise StorageRootValidationError(f"Path does not exist: {target}")
        if not resolved_target.is_dir():
            raise StorageRootValidationError("Browse path must be a directory")

        entries: list[BrowseEntry] = []
        for child in sorted(resolved_target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            resolved_child = _resolve_existing_path(child)
            try:
                resolved_child.relative_to(resolved_root)
            except ValueError:
                continue
            entries.append(
                BrowseEntry(name=child.name, path=resolved_child, is_dir=child.is_dir())
            )
        return entries

    def reconcile_roots(self) -> ReconciliationReport:
        self._ensure_bootstrap_roots()
        current_env_paths = {str(path) for path in self._settings.storage_roots}
        removed: list[str] = []
        missing: list[str] = []
        invalid: list[str] = []
        resolved_seen: dict[str, str] = {}
        duplicates: set[str] = set()

        for root in self.list_roots(include_disabled=True):
            root_path = Path(root.path)
            if root.source == "env" and root.path not in current_env_paths:
                removed.append(root.path)
            if not root_path.is_absolute() or _contains_nul(root_path):
                invalid.append(root.path)
                continue
            if not root_path.exists():
                missing.append(root.path)
                continue
            try:
                resolved = str(root_path.resolve(strict=True))
            except OSError:
                invalid.append(root.path)
                continue
            if resolved in resolved_seen:
                duplicates.add(resolved)
            else:
                resolved_seen[resolved] = root.path

        return ReconciliationReport(
            removed=sorted(removed),
            missing=sorted(missing),
            duplicates=sorted(duplicates),
            invalid=sorted(invalid),
        )

    def is_destination_inside_watch_source(
        self, destination: Path | str, watch_sources: list[Path | str]
    ) -> bool:
        destination_path = _resolve_existing_path(Path(destination))
        for source in watch_sources:
            source_path = Path(source)
            if not source_path.exists():
                continue
            try:
                destination_path.relative_to(source_path.resolve(strict=True))
            except ValueError:
                continue
            return True
        return False

    def _ensure_bootstrap_roots(self) -> None:
        for path in self._settings.storage_roots:
            existing = self._root_by_path(path)
            if existing is None:
                self._session.add(StorageRoot(path=str(path), source="env", enabled=True))
            elif existing.source == "user":
                existing.source = "env"
                existing.enabled = True
        self._session.flush()

    def _root_by_path(self, path: Path) -> StorageRoot | None:
        return self._session.scalar(select(StorageRoot).where(StorageRoot.path == str(path)))

    def _get_root(self, root_id: int, *, include_disabled: bool = False) -> StorageRoot:
        self._ensure_bootstrap_roots()
        root = self._session.get(StorageRoot, root_id)
        if root is None or (not include_disabled and not root.enabled):
            raise StorageRootValidationError("Storage root not found")
        return root

    @staticmethod
    def _normalize_root_path(path: Path | str) -> Path:
        root_path = Path(path)
        if _contains_nul(root_path):
            raise StorageRootValidationError("Path contains NUL")
        if not root_path.is_absolute():
            root_path = Path.cwd() / root_path
        return root_path


def _decode_path(path: Path | str) -> Path:
    return Path(unquote(os.fspath(path)))


def _contains_nul(path: Path | str) -> bool:
    return "\0" in os.fspath(path)


def _has_parent_traversal(path: Path) -> bool:
    return any(part == ".." for part in path.parts)


def _resolve_existing_path(path: Path) -> Path:
    if path.exists():
        return path.resolve(strict=True)
    existing = path
    missing_parts: list[str] = []
    while not existing.exists() and existing.parent != existing:
        missing_parts.append(existing.name)
        existing = existing.parent
    if not existing.exists():
        return path.resolve(strict=False)
    resolved = existing.resolve(strict=True)
    for part in reversed(missing_parts):
        resolved = resolved / part
    return resolved
