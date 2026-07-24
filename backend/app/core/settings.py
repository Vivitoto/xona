from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from backend.app.core.redaction import redact_payload


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    config_dir: Path = Path("/config")
    database_url: str | None = None
    storage_roots: Annotated[tuple[Path, ...], NoDecode] = ()
    auto_storage_roots: bool = True
    flaresolverr_url: str | None = None
    proxy_url: str | None = None
    emby_server_url: str | None = None
    emby_api_key: str | None = None
    auth_enabled: bool = False
    auth_username: str | None = None
    auth_password_hash: str | None = None
    auth_cookie_secure: bool = False
    worker_enabled: bool = False
    monitor_enabled: bool = False

    @field_validator("config_dir", mode="before")
    @classmethod
    def _normalize_config_dir(cls, value: Any) -> Path:
        return _absolute_path(value)

    @field_validator("storage_roots", mode="before")
    @classmethod
    def _normalize_storage_roots(cls, value: Any) -> tuple[Path, ...]:
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            values: tuple[Any, ...] = tuple(part for part in value.split(os.pathsep) if part)
        elif isinstance(value, Path):
            values = (value,)
        else:
            values = tuple(value)
        return tuple(_absolute_path(path) for path in values)

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.config_dir / 'xona.db'}"

    def bootstrap_storage_roots(self) -> tuple[tuple[Path, str], ...]:
        if self.storage_roots:
            return tuple((path, "env") for path in self.storage_roots)
        if not self.auto_storage_roots:
            return ()
        return tuple(
            (path, "mount")
            for path in discover_container_storage_roots(config_dir=self.config_dir)
        )

    def public_dict(self) -> dict[str, Any]:
        values = self.model_dump()
        values["effective_database_url"] = self.effective_database_url
        return redact_payload(values)


def discover_container_storage_roots(
    *,
    config_dir: Path,
    mountinfo_path: Path = Path("/proc/self/mountinfo"),
    in_container: bool | None = None,
    path_is_dir: Callable[[Path], bool] | None = None,
) -> tuple[Path, ...]:
    if in_container is None:
        in_container = Path("/.dockerenv").exists()
    if not in_container:
        return ()
    try:
        mountinfo = mountinfo_path.read_text(encoding="utf-8")
    except OSError:
        return ()

    is_dir = path_is_dir or Path.is_dir
    excluded_prefixes = (
        Path("/proc"),
        Path("/sys"),
        Path("/dev"),
        Path("/run"),
        Path("/app"),
        Path("/tmp"),
        Path("/var"),
        config_dir,
    )
    pseudo_fs = {
        "autofs",
        "bpf",
        "cgroup",
        "cgroup2",
        "configfs",
        "debugfs",
        "devpts",
        "devtmpfs",
        "fusectl",
        "hugetlbfs",
        "mqueue",
        "proc",
        "pstore",
        "ramfs",
        "securityfs",
        "sysfs",
        "tmpfs",
        "tracefs",
    }
    roots: list[Path] = []
    seen: set[Path] = set()
    for line in mountinfo.splitlines():
        parsed = _parse_mountinfo_line(line)
        if parsed is None:
            continue
        mount_point, fs_type = parsed
        if mount_point == Path("/") or fs_type in pseudo_fs:
            continue
        if any(_is_relative_to(mount_point, prefix) for prefix in excluded_prefixes):
            continue
        if not is_dir(mount_point):
            continue
        if mount_point not in seen:
            seen.add(mount_point)
            roots.append(mount_point)
    return tuple(sorted(roots, key=lambda path: str(path)))


def _parse_mountinfo_line(line: str) -> tuple[Path, str] | None:
    try:
        left, right = line.split(" - ", 1)
        left_fields = left.split()
        right_fields = right.split()
        mount_point = Path(_decode_mountinfo_field(left_fields[4]))
        fs_type = right_fields[0]
    except (IndexError, ValueError):
        return None
    return mount_point, fs_type


def _decode_mountinfo_field(value: str) -> str:
    return value.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _absolute_path(value: Any) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path.cwd() / path
