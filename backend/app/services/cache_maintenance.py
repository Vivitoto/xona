from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.app.schemas.settings import (
    CacheAreaStats,
    CacheCleanupAreaResult,
    CacheMaintenanceCleanupResponse,
    CacheMaintenanceResponse,
)


class CacheMaintenanceError(ValueError):
    pass


@dataclass(frozen=True)
class _CacheArea:
    key: str
    label: str
    path: Path
    cleanup_supported: bool = True
    warnings: tuple[str, ...] = ()


class CacheMaintenanceService:
    def __init__(
        self,
        config_dir: Path | str,
        *,
        xchina_cache_dir: Path | str | None = None,
    ) -> None:
        self._config_dir = Path(config_dir)
        self._xchina_cache_dir = Path(xchina_cache_dir) if xchina_cache_dir else None

    def stats(self) -> CacheMaintenanceResponse:
        areas = [self._stats_for_area(area) for area in self._areas()]
        warnings = [warning for area in areas for warning in area.warnings]
        return CacheMaintenanceResponse(
            areas=areas,
            total_file_count=sum(area.file_count for area in areas),
            total_size_bytes=sum(area.size_bytes for area in areas),
            warnings=warnings,
        )

    def cleanup(self, area_keys: list[str]) -> CacheMaintenanceCleanupResponse:
        if not area_keys:
            raise CacheMaintenanceError("area_keys_required")
        requested_keys = list(dict.fromkeys(area_keys))
        areas = {area.key: area for area in self._areas()}
        unknown = [key for key in requested_keys if key not in areas]
        if unknown:
            raise CacheMaintenanceError(f"unknown_cache_area:{','.join(unknown)}")

        results: list[CacheCleanupAreaResult] = []
        for key in requested_keys:
            area = areas[key]
            if not area.cleanup_supported:
                raise CacheMaintenanceError(f"unsafe_cache_path:{area.path}")
            self._require_safe_path(area.path)
            results.append(self._cleanup_area(area))

        warnings = [warning for result in results for warning in result.warnings]
        return CacheMaintenanceCleanupResponse(
            results=results,
            deleted_files=sum(result.deleted_files for result in results),
            deleted_bytes=sum(result.deleted_bytes for result in results),
            warnings=warnings,
        )

    def _areas(self) -> list[_CacheArea]:
        areas = [
            _CacheArea(
                key="local_metadata",
                label="本地元数据缓存",
                path=self._config_dir / "cache" / "local_metadata",
            ),
            _CacheArea(
                key="asset_cache",
                label="元数据资源缓存",
                path=self._config_dir / "asset-cache",
            ),
            _CacheArea(
                key="actor_cache",
                label="演员头像缓存",
                path=self._config_dir / "actor-cache",
            ),
        ]
        if self._xchina_cache_dir is not None:
            xchina_path = self._xchina_cache_dir
            warnings: tuple[str, ...] = ()
            cleanup_supported = True
            if not self._is_safe_path(xchina_path):
                warnings = (f"unsafe_cache_path:{xchina_path}",)
                cleanup_supported = False
            areas.append(
                _CacheArea(
                    key="xchina_cache",
                    label="XChina 页面缓存",
                    path=xchina_path,
                    cleanup_supported=cleanup_supported,
                    warnings=warnings,
                )
            )
        return areas

    def _stats_for_area(self, area: _CacheArea) -> CacheAreaStats:
        warnings = list(area.warnings)
        if not area.cleanup_supported:
            return CacheAreaStats(
                key=area.key,
                label=area.label,
                path=area.path,
                exists=area.path.exists(),
                cleanup_supported=False,
                warnings=warnings,
            )
        self._require_safe_path(area.path)
        if not area.path.exists():
            warnings.append(f"cache_dir_missing:{area.path}")
            return CacheAreaStats(
                key=area.key,
                label=area.label,
                path=area.path,
                exists=False,
                warnings=warnings,
            )
        if not area.path.is_dir():
            warnings.append(f"cache_path_not_directory:{area.path}")
            return CacheAreaStats(
                key=area.key,
                label=area.label,
                path=area.path,
                exists=True,
                cleanup_supported=False,
                warnings=warnings,
            )
        file_count, size_bytes = _directory_file_stats(area.path)
        return CacheAreaStats(
            key=area.key,
            label=area.label,
            path=area.path,
            exists=True,
            file_count=file_count,
            size_bytes=size_bytes,
            warnings=warnings,
        )

    def _cleanup_area(self, area: _CacheArea) -> CacheCleanupAreaResult:
        warnings = list(area.warnings)
        if not area.path.exists():
            warnings.append(f"cache_dir_missing:{area.path}")
            return CacheCleanupAreaResult(
                key=area.key,
                label=area.label,
                path=area.path,
                warnings=warnings,
            )
        if not area.path.is_dir():
            warnings.append(f"cache_path_not_directory:{area.path}")
            return CacheCleanupAreaResult(
                key=area.key,
                label=area.label,
                path=area.path,
                warnings=warnings,
            )
        file_count, size_bytes = _directory_file_stats(area.path)
        shutil.rmtree(area.path)
        return CacheCleanupAreaResult(
            key=area.key,
            label=area.label,
            path=area.path,
            deleted_files=file_count,
            deleted_bytes=size_bytes,
            removed=True,
            warnings=warnings,
        )

    def _require_safe_path(self, path: Path) -> None:
        if not self._is_safe_path(path):
            raise CacheMaintenanceError(f"unsafe_cache_path:{path}")

    def _is_safe_path(self, path: Path) -> bool:
        if "\0" in str(path) or not path.is_absolute():
            return False
        try:
            safe_config = self._config_dir.resolve(strict=self._config_dir.exists())
            safe_path = path.resolve(strict=path.exists())
            safe_path.relative_to(safe_config)
        except (OSError, RuntimeError, ValueError):
            return False
        return safe_path != safe_config


def _directory_file_stats(path: Path) -> tuple[int, int]:
    file_count = 0
    size_bytes = 0
    for item in path.rglob("*"):
        try:
            stat = item.lstat()
        except OSError:
            continue
        if item.is_file() or item.is_symlink():
            file_count += 1
            size_bytes += stat.st_size
    return file_count, size_bytes
