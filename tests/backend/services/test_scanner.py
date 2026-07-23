from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.app.core.settings import Settings
from backend.app.db.migrations import run_migrations
from backend.app.db.models import MediaItem, MediaSidecar, StorageRoot
from backend.app.db.session import create_engine_for_settings, get_sessionmaker
from backend.app.services.scanner import media_identity, persist_scan_items, scan_directory


def test_scan_directory_groups_media_sidecars_and_respects_recursion(tmp_path: Path) -> None:
    root = tmp_path / "media"
    nested = root / "nested"
    nested.mkdir(parents=True)
    for relative in [
        "Sample.mp4",
        "Sample.srt",
        "Sample.jpg",
        "Sample.nfo",
        "Ignored.tmp",
        "Download.part",
        "nested/Deep.mkv",
    ]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic", encoding="utf-8")

    shallow = scan_directory(root, recursive=False)
    assert [item.path.name for item in shallow] == ["Sample.mp4"]
    assert {sidecar.path.name for sidecar in shallow[0].sidecars} == {
        "Sample.srt",
        "Sample.jpg",
        "Sample.nfo",
    }

    recursive = scan_directory(root, recursive=True)
    assert [item.path.name for item in recursive] == ["Sample.mp4", "Deep.mkv"]


def test_scan_directory_groups_multipart_names(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    for name in ["SAMPLE-CD1.mp4", "SAMPLE-CD2.mp4", "OTHER.part1.mp4", "OTHER.part2.mp4"]:
        (root / name).write_text("synthetic", encoding="utf-8")

    items = scan_directory(root)
    groups = {(item.group_key, item.multipart_index) for item in items}

    assert groups == {("SAMPLE", 1), ("SAMPLE", 2), ("OTHER", 1), ("OTHER", 2)}


def test_ignored_extensions_and_patterns_are_skipped(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    for name in ["Keep.mov", "Skip.mp4", "Temp.crdownload", "Scratch.tmp", "Partial.part"]:
        (root / name).write_text("synthetic", encoding="utf-8")

    items = scan_directory(root, ignore_patterns=("Skip*",))

    assert [item.path.name for item in items] == ["Keep.mov"]


def test_media_identity_uses_inode_then_falls_back_to_path_size_mtime(tmp_path: Path) -> None:
    path = tmp_path / "movie.mp4"
    path.write_text("synthetic", encoding="utf-8")

    inode_identity = media_identity(path)
    assert inode_identity.startswith("inode:")

    fake_stat = SimpleNamespace(st_dev=0, st_ino=0, st_size=9, st_mtime_ns=123)
    fallback = media_identity(path, stat_result=fake_stat)
    assert fallback.startswith("path:")
    assert str(path) in fallback


def test_scan_items_can_be_persisted_with_foreign_keys(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    (root / "Sample.mp4").write_text("synthetic", encoding="utf-8")
    (root / "Sample.srt").write_text("subtitle", encoding="utf-8")
    settings = Settings(config_dir=tmp_path / "config")
    run_migrations(settings=settings)
    engine = create_engine_for_settings(settings)
    try:
        sessionmaker = get_sessionmaker(engine)
        with sessionmaker() as session:
            storage_root = StorageRoot(path=str(root), source="user", enabled=True)
            session.add(storage_root)
            session.flush()
            persist_scan_items(session, storage_root.id, scan_directory(root))
            session.commit()

        with sessionmaker() as session:
            assert session.query(MediaItem).count() == 1
            assert session.query(MediaSidecar).count() == 1
    finally:
        engine.dispose()
