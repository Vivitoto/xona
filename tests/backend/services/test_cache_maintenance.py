from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.cache_maintenance import (
    CacheMaintenanceError,
    CacheMaintenanceService,
)


def test_cache_maintenance_scans_safe_roots_and_reports_missing_dirs(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    local_file = config_dir / "cache" / "local_metadata" / "ab" / "frame.jpg"
    asset_file = config_dir / "asset-cache" / "poster.jpg"
    xchina_file = config_dir / "cache" / "xchina" / "page.html"
    local_file.parent.mkdir(parents=True)
    asset_file.parent.mkdir(parents=True)
    xchina_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"local")
    asset_file.write_bytes(b"asset-cache")
    xchina_file.write_bytes(b"html")

    service = CacheMaintenanceService(
        config_dir,
        xchina_cache_dir=config_dir / "cache" / "xchina",
    )

    stats = service.stats()

    areas = {area.key: area for area in stats.areas}
    assert areas["local_metadata"].file_count == 1
    assert areas["local_metadata"].size_bytes == 5
    assert areas["asset_cache"].file_count == 1
    assert areas["asset_cache"].size_bytes == 11
    assert areas["actor_cache"].exists is False
    assert areas["actor_cache"].warnings == [
        f"cache_dir_missing:{config_dir / 'actor-cache'}"
    ]
    assert areas["xchina_cache"].file_count == 1
    assert areas["xchina_cache"].size_bytes == 4
    assert stats.total_file_count == 3
    assert stats.total_size_bytes == 20


def test_cache_maintenance_cleanup_only_removes_requested_safe_areas(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    local_file = config_dir / "cache" / "local_metadata" / "ab" / "frame.jpg"
    asset_file = config_dir / "asset-cache" / "poster.jpg"
    keep_file = config_dir / "logs" / "xona.log"
    local_file.parent.mkdir(parents=True)
    asset_file.parent.mkdir(parents=True)
    keep_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"local")
    asset_file.write_bytes(b"asset")
    keep_file.write_bytes(b"keep")

    service = CacheMaintenanceService(config_dir)

    result = service.cleanup(["local_metadata", "actor_cache"])

    assert result.deleted_files == 1
    assert result.deleted_bytes == 5
    assert not (config_dir / "cache" / "local_metadata").exists()
    assert asset_file.is_file()
    assert keep_file.is_file()
    assert [area.key for area in result.results] == ["local_metadata", "actor_cache"]
    assert result.results[1].deleted_files == 0
    assert result.results[1].warnings == [
        f"cache_dir_missing:{config_dir / 'actor-cache'}"
    ]


def test_cache_maintenance_cleanup_requires_explicit_known_area_keys(
    tmp_path: Path,
) -> None:
    service = CacheMaintenanceService(tmp_path / "config")

    with pytest.raises(CacheMaintenanceError, match="area_keys_required"):
        service.cleanup([])

    with pytest.raises(CacheMaintenanceError, match="unknown_cache_area"):
        service.cleanup(["logs"])


def test_cache_maintenance_refuses_unsafe_configured_xchina_cache(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    outside_cache = tmp_path / "outside-cache"
    outside_cache.mkdir()
    (outside_cache / "page.html").write_bytes(b"html")

    service = CacheMaintenanceService(config_dir, xchina_cache_dir=outside_cache)

    stats = service.stats()
    xchina = next(area for area in stats.areas if area.key == "xchina_cache")
    assert xchina.cleanup_supported is False
    assert xchina.file_count == 0
    assert xchina.warnings == [f"unsafe_cache_path:{outside_cache}"]

    with pytest.raises(CacheMaintenanceError, match="unsafe_cache_path"):
        service.cleanup(["xchina_cache"])
