from __future__ import annotations

import os
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

    def public_dict(self) -> dict[str, Any]:
        values = self.model_dump()
        values["effective_database_url"] = self.effective_database_url
        return redact_payload(values)


def _absolute_path(value: Any) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path.cwd() / path
