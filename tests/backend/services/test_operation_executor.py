from __future__ import annotations

import errno
from pathlib import Path

import pytest

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import OperationStep as OperationStepModel
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.schemas.media import MediaScanItem
from backend.app.schemas.templates import TemplatePreview
from backend.app.services.operation_executor import (
    OperationExecutionError,
    OperationExecutor,
    OperationJournal,
)
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


def _plan(tmp_path: Path, *, mode: str, content: bytes = b"movie-bytes"):
    root = tmp_path / "media"
    source = _write(root / "incoming" / "sample.mkv", content)
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
    return settings, engine, session, storage_roots, plan, source, destination / "Movie" / "Renamed.mkv"


def test_same_filesystem_move_uses_path_rename_and_records_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, engine, session, storage_roots, plan, source, target = _plan(
        tmp_path,
        mode="move",
    )
    calls: list[tuple[Path, Path]] = []
    original_rename = Path.rename

    def spy_rename(self: Path, new_target: Path) -> Path:
        calls.append((self, Path(new_target)))
        return original_rename(self, new_target)

    monkeypatch.setattr(Path, "rename", spy_rename)
    try:
        journal = OperationJournal(session)
        OperationExecutor(storage_roots, journal=journal).execute(plan)
        session.commit()

        assert calls == [(source, target)]
        assert source.exists() is False
        assert target.read_bytes() == b"movie-bytes"
        assert [event["event"] for event in journal.events] == [
            "plan_started",
            "step_started",
            "step_completed",
            "plan_completed",
        ]
        completed = session.query(OperationStepModel).one()
        assert completed.status == "completed"
        assert completed.step_json["journal"][-1]["observed_sha256"]
    finally:
        session.close()
        engine.dispose()


def test_copy_uses_temp_file_verifies_target_and_leaves_source(tmp_path: Path) -> None:
    settings, engine, session, storage_roots, plan, source, target = _plan(
        tmp_path,
        mode="copy",
    )
    try:
        OperationExecutor(storage_roots, journal=OperationJournal(session)).execute(plan)
        session.commit()

        assert source.read_bytes() == b"movie-bytes"
        assert target.read_bytes() == b"movie-bytes"
        assert list(target.parent.glob(".xona.*.tmp")) == []
    finally:
        session.close()
        engine.dispose()


def test_cross_filesystem_move_verifies_copy_before_removing_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, engine, session, storage_roots, plan, source, target = _plan(
        tmp_path,
        mode="move",
    )

    def raise_exdev(self: Path, new_target: Path) -> Path:
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(Path, "rename", raise_exdev)
    try:
        OperationExecutor(storage_roots, journal=OperationJournal(session)).execute(plan)
        session.commit()

        assert source.exists() is False
        assert target.read_bytes() == b"movie-bytes"
    finally:
        session.close()
        engine.dispose()


def test_existing_target_at_execution_fails_safely_and_keeps_source(tmp_path: Path) -> None:
    settings, engine, session, storage_roots, plan, source, target = _plan(
        tmp_path,
        mode="copy",
    )
    _write(target, b"late-collision")
    try:
        journal = OperationJournal(session)
        with pytest.raises(OperationExecutionError) as exc_info:
            OperationExecutor(storage_roots, journal=journal).execute(plan)
        session.commit()

        assert exc_info.value.error_code == "target_exists"
        assert source.read_bytes() == b"movie-bytes"
        assert target.read_bytes() == b"late-collision"
        assert journal.events[-2]["event"] == "step_failed"
        assert journal.events[-2]["error_code"] == "target_exists"
        assert journal.events[-1]["event"] == "plan_failed"
    finally:
        session.close()
        engine.dispose()
