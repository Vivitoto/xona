from __future__ import annotations

from pathlib import Path

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.schemas.media import MediaScanItem
from backend.app.schemas.templates import TemplatePreview
from backend.app.services.operation_executor import OperationExecutor
from backend.app.services.organizer_plans import OrganizerPlanService
from backend.app.services.recovery import RecoveryService
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


def _plan(tmp_path: Path):
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
    return engine, session, storage_roots, plan


def test_recovery_classifies_completed_partial_and_modified_steps(tmp_path: Path) -> None:
    engine, session, storage_roots, plan = _plan(tmp_path)
    try:
        report = RecoveryService().inspect_plan(plan)
        assert report.pending == (plan.steps[0].step_id,)

        temp_path = RecoveryService.temp_path_for_step(plan, plan.steps[0])
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(b"partial")
        report = RecoveryService().inspect_plan(plan)
        assert report.partial == (plan.steps[0].step_id,)

        temp_path.unlink()
        OperationExecutor(storage_roots).execute(plan)
        report = RecoveryService().inspect_plan(plan)
        assert report.completed == (plan.steps[0].step_id,)

        plan.steps[0].target_path.write_bytes(b"modified")
        report = RecoveryService().inspect_plan(plan)
        assert report.externally_modified == (plan.steps[0].step_id,)
    finally:
        session.close()
        engine.dispose()
