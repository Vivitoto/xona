from __future__ import annotations

from pathlib import Path

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.services.storage_roots import StorageRootService, StorageRootValidationError


def _store(tmp_path: Path, roots: tuple[Path, ...] = ()):
    settings = Settings(config_dir=tmp_path / "config", storage_roots=roots)
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    return settings, engine, get_sessionmaker(engine)


def test_env_bootstrap_roots_are_marked_env_and_immutable(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    settings, engine, sessionmaker = _store(tmp_path, (media_root,))
    try:
        with sessionmaker() as session:
            service = StorageRootService(settings, session)
            [root] = service.list_roots()
            assert root.source == "env"

            try:
                service.update_root(root.id, enabled=False)
            except StorageRootValidationError as exc:
                assert "read-only" in str(exc)
            else:  # pragma: no cover - assertion branch
                raise AssertionError("bootstrap roots must be immutable")
    finally:
        engine.dispose()


def test_ui_created_roots_persist_across_service_restarts(tmp_path: Path) -> None:
    user_root = tmp_path / "user-media"
    user_root.mkdir()
    settings, engine, sessionmaker = _store(tmp_path)
    try:
        with sessionmaker() as session:
            created = StorageRootService(settings, session).add_root(user_root)
            session.commit()

        with sessionmaker() as session:
            roots = StorageRootService(settings, session).list_roots()
            assert [(root.id, root.path, root.source) for root in roots] == [
                (created.id, str(user_root), "user")
            ]
    finally:
        engine.dispose()


def test_reconciliation_reports_without_deleting_rows(tmp_path: Path) -> None:
    env_root = tmp_path / "env"
    missing_root = tmp_path / "missing"
    duplicate_one = tmp_path / "dupe"
    env_root.mkdir()
    duplicate_one.mkdir()
    settings, engine, sessionmaker = _store(tmp_path, (env_root,))
    try:
        with sessionmaker() as session:
            service = StorageRootService(settings, session)
            env_row = service.list_roots()[0]
            service.add_root(missing_root)
            service.add_root(duplicate_one)
            service.add_root(duplicate_one / ".." / "dupe")
            session.commit()

        restarted = Settings(config_dir=settings.config_dir, storage_roots=())
        with sessionmaker() as session:
            service = StorageRootService(restarted, session)
            report = service.reconcile_roots()
            persisted_paths = {
                root.path for root in service.list_roots(include_disabled=True)
            }

        assert str(env_row.path) in report.removed
        assert str(missing_root) in report.missing
        assert str(duplicate_one.resolve()) in report.duplicates
        assert persisted_paths >= {str(env_root), str(missing_root), str(duplicate_one)}
    finally:
        engine.dispose()
