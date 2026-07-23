from __future__ import annotations

import errno
from pathlib import Path

import pytest

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.schemas.media import MediaScanItem
from backend.app.schemas.templates import TemplatePreview
from backend.app.services.operation_executor import OperationExecutionError, OperationExecutor
from backend.app.services.organizer_plans import OrganizerPlanService
from backend.app.services.storage_roots import StorageRootService


def _database(tmp_path: Path, storage_root: Path):
    settings = Settings(config_dir=tmp_path / "config", storage_roots=(storage_root,))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return settings, engine, get_sessionmaker(engine)


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _media_item(path: Path) -> MediaScanItem:
    stat = path.stat()
    return MediaScanItem(
        path=path,
        group_key=path.stem,
        identity=f"inode:{stat.st_dev}:{stat.st_ino}",
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )


def _plan(tmp_path: Path, *, mode: str):
    root = tmp_path / "media"
    source = _write(root / "incoming" / "sample.mkv", b"movie-bytes")
    destination = root / "organized"
    settings, engine, sessionmaker = _database(tmp_path, root)
    session = sessionmaker()
    storage_roots = StorageRootService(settings, session)
    plan = OrganizerPlanService(session, storage_roots).create_plan(
        mode=mode,
        media_items=[_media_item(source)],
        destination_root=destination,
        template_preview=TemplatePreview(
            folder_path="Movie",
            filename="Renamed.mkv",
            validation_errors=[],
            warnings=[],
        ),
    )
    session.commit()
    return engine, session, storage_roots, plan, source


def test_source_changed_after_preview_is_refused_without_writing_target(tmp_path: Path) -> None:
    engine, session, storage_roots, plan, source = _plan(tmp_path, mode="copy")
    source.write_bytes(b"changed")
    try:
        with pytest.raises(OperationExecutionError) as exc_info:
            OperationExecutor(storage_roots).execute(plan)

        assert exc_info.value.error_code == "source_integrity_mismatch"
        assert plan.steps[0].target_path.exists() is False
    finally:
        session.close()
        engine.dispose()


def test_temp_corruption_is_detected_and_move_keeps_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, session, storage_roots, plan, source = _plan(tmp_path, mode="move")

    def raise_exdev(self: Path, new_target: Path) -> Path:
        raise OSError(errno.EXDEV, "cross-device link")

    def corrupt_temp(temp_path: Path) -> None:
        temp_path.write_bytes(b"corrupt")

    monkeypatch.setattr(Path, "rename", raise_exdev)
    try:
        with pytest.raises(OperationExecutionError) as exc_info:
            OperationExecutor(storage_roots, after_copy=corrupt_temp).execute(plan)

        assert exc_info.value.error_code == "target_integrity_mismatch"
        assert source.read_bytes() == b"movie-bytes"
        assert plan.steps[0].target_path.exists() is False
    finally:
        session.close()
        engine.dispose()
