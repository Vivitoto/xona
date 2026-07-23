from __future__ import annotations

import fnmatch
import hashlib
import os
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.app.db.models import MediaItem, MediaSidecar
from backend.app.schemas.media import MediaScanItem, MediaSidecarScanItem
from backend.app.services.storage_roots import StorageRootService


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".sub", ".vtt"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
NFO_EXTENSIONS = {".nfo"}
IGNORED_EXTENSIONS = {".part", ".crdownload", ".tmp"}
MULTIPART_RE = re.compile(r"(?i)(?:[\s._-]+(?:cd|disc|disk|part)[\s._-]*(\d{1,3}))$")


def scan_directory(
    directory: Path | str,
    *,
    recursive: bool = True,
    ignore_patterns: tuple[str, ...] = (),
    storage_roots: StorageRootService | None = None,
) -> list[MediaScanItem]:
    root = Path(directory)
    if storage_roots is not None:
        storage_roots.validate_inside_root(root)
    if not root.is_dir():
        raise ValueError(f"Scan path is not a directory: {root}")

    files = sorted(_iter_files(root, recursive=recursive), key=lambda path: str(path))
    sidecars_by_group: dict[tuple[Path, str], list[MediaSidecarScanItem]] = {}
    media_paths: list[Path] = []
    for path in files:
        if _ignored(path, ignore_patterns):
            continue
        extension = path.suffix.lower()
        if extension in VIDEO_EXTENSIONS:
            media_paths.append(path)
        elif extension in SUBTITLE_EXTENSIONS | IMAGE_EXTENSIONS | NFO_EXTENSIONS:
            group_key, _ = _group_from_stem(path.stem)
            sidecars_by_group.setdefault((path.parent, group_key), []).append(
                MediaSidecarScanItem(path=path, kind=_sidecar_kind(extension))
            )

    items: list[MediaScanItem] = []
    for path in media_paths:
        group_key, multipart_index = _group_from_stem(path.stem)
        stat_result = path.stat()
        items.append(
            MediaScanItem(
                path=path,
                group_key=group_key,
                multipart_index=multipart_index,
                identity=media_identity(path, stat_result=stat_result),
                size_bytes=stat_result.st_size,
                mtime_ns=stat_result.st_mtime_ns,
                sidecars=sidecars_by_group.get((path.parent, group_key), []),
            )
        )
    return items


def media_identity(path: Path | str, *, stat_result: Any | None = None) -> str:
    media_path = Path(path)
    stat_result = stat_result or media_path.stat()
    device = int(getattr(stat_result, "st_dev", 0) or 0)
    inode = int(getattr(stat_result, "st_ino", 0) or 0)
    if device and inode:
        return f"inode:{device}:{inode}"
    fallback = f"{media_path}:{getattr(stat_result, 'st_size', 0)}:{getattr(stat_result, 'st_mtime_ns', 0)}"
    digest = hashlib.sha256(fallback.encode("utf-8")).hexdigest()
    return f"path:{media_path}:{digest}"


def persist_scan_items(
    session: Session,
    storage_root_id: int,
    items: list[MediaScanItem],
) -> list[MediaItem]:
    persisted: list[MediaItem] = []
    for item in items:
        media = MediaItem(
            storage_root_id=storage_root_id,
            path=str(item.path),
            relative_path=item.path.name,
            filename=item.path.name,
            group_key=item.group_key,
            multipart_index=item.multipart_index,
            identity=item.identity,
            size_bytes=item.size_bytes,
            mtime_ns=item.mtime_ns,
        )
        session.add(media)
        session.flush()
        for sidecar in item.sidecars:
            session.add(
                MediaSidecar(
                    media_item_id=media.id,
                    path=str(sidecar.path),
                    kind=sidecar.kind,
                    extension=sidecar.path.suffix.lower(),
                )
            )
        persisted.append(media)
    session.flush()
    return persisted


def _iter_files(root: Path, *, recursive: bool) -> list[Path]:
    if recursive:
        return [path for path in root.rglob("*") if path.is_file()]
    return [path for path in root.iterdir() if path.is_file()]


def _ignored(path: Path, ignore_patterns: tuple[str, ...]) -> bool:
    if path.suffix.lower() in IGNORED_EXTENSIONS:
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in ignore_patterns)


def _group_from_stem(stem: str) -> tuple[str, int | None]:
    match = MULTIPART_RE.search(stem)
    if match is None:
        return stem, None
    return stem[: match.start()].rstrip(" ._-"), int(match.group(1))


def _sidecar_kind(extension: str) -> str:
    if extension in SUBTITLE_EXTENSIONS:
        return "subtitle"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    return "nfo"
