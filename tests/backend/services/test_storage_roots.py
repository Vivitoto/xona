from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import pytest

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.services.storage_roots import StorageRootService, StorageRootValidationError


def _service(tmp_path: Path, root: Path):
    settings = Settings(config_dir=tmp_path / "config", storage_roots=(root,))
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    sessionmaker = get_sessionmaker(engine)
    session = sessionmaker()
    return settings, engine, session, StorageRootService(settings, session)


def test_validate_inside_root_re_resolves_at_execution_time(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    _, engine, session, service = _service(tmp_path, root)
    try:
        target = root / "movie.mp4"
        target.write_text("synthetic", encoding="utf-8")
        assert service.validate_inside_root(target).relative_path == Path("movie.mp4")

        root.rename(tmp_path / "moved")
        with pytest.raises(StorageRootValidationError, match="does not exist"):
            service.validate_inside_root(target)
    finally:
        session.close()
        engine.dispose()


def test_browse_rejects_traversal_absolute_nul_and_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "media"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "movie.mp4").write_text("synthetic", encoding="utf-8")
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (root / "escape").symlink_to(outside, target_is_directory=True)
    _, engine, session, service = _service(tmp_path, root)
    try:
        [storage_root] = service.list_roots()
        assert [entry.name for entry in service.browse(storage_root.id)] == ["movie.mp4"]

        unsafe_inputs = [
            "../outside",
            quote("../outside"),
            str(outside / "secret.txt"),
            "bad\0path",
            "escape/secret.txt",
        ]
        for value in unsafe_inputs:
            with pytest.raises(StorageRootValidationError):
                service.browse(storage_root.id, value)
    finally:
        session.close()
        engine.dispose()


def test_destination_under_watch_sources_is_excluded(tmp_path: Path) -> None:
    root = tmp_path / "media"
    watch_source = root / "incoming"
    destination = watch_source / "organized" / "movie.mp4"
    watch_source.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    _, engine, session, service = _service(tmp_path, root)
    try:
        assert service.is_destination_inside_watch_source(destination, [watch_source])
        assert not service.is_destination_inside_watch_source(
            root / "organized" / "movie.mp4", [watch_source]
        )
    finally:
        session.close()
        engine.dispose()
