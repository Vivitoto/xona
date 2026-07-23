from __future__ import annotations

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


def _build_plan(tmp_path: Path):
    root = tmp_path / "media"
    source = _write(root / "incoming" / "sample.mkv", b"movie-bytes")
    destination = root / "organized"
    settings, engine, sessionmaker = _database(tmp_path, root)
    session = sessionmaker()
    storage_roots = StorageRootService(settings, session)
    plan = OrganizerPlanService(session, storage_roots).create_plan(
        mode="copy",
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


def test_destination_parent_swapped_to_symlink_is_refused(tmp_path: Path) -> None:
    engine, session, storage_roots, plan, source = _build_plan(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = plan.steps[0].target_path
    target.parent.parent.mkdir(parents=True)
    target.parent.parent.rmdir()
    target.parent.parent.symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(OperationExecutionError) as exc_info:
            OperationExecutor(storage_roots).execute(plan)

        assert exc_info.value.error_code == "symlink_ancestor"
        assert source.read_bytes() == b"movie-bytes"
        assert target.exists() is False
    finally:
        session.close()
        engine.dispose()


def test_source_replaced_by_symlink_escape_is_refused_at_execution(tmp_path: Path) -> None:
    engine, session, storage_roots, plan, source = _build_plan(tmp_path)
    outside_source = _write(tmp_path / "outside" / "sample.mkv", b"outside")
    source.unlink()
    source.symlink_to(outside_source)
    try:
        with pytest.raises(OperationExecutionError) as exc_info:
            OperationExecutor(storage_roots).execute(plan)

        assert exc_info.value.error_code in {"outside_storage_root", "symlink_ancestor"}
        assert plan.steps[0].target_path.exists() is False
    finally:
        session.close()
        engine.dispose()
