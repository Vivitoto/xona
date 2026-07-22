from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config

from backend.app.db.session import create_engine_for_url

if TYPE_CHECKING:
    from backend.app.core.settings import Settings


def run_migrations(
    *,
    database_url: str | None = None,
    settings: Settings | None = None,
) -> None:
    has_database_url = database_url is not None and database_url.strip() != ""
    has_settings = settings is not None
    if has_database_url == has_settings:
        raise ValueError("Provide exactly one of database_url or settings.")

    if has_database_url:
        assert database_url is not None
        target_url = database_url
    elif settings is not None:
        target_url = settings.effective_database_url
    else:  # pragma: no cover - kept for type narrowing after validation above.
        raise ValueError("Provide exactly one of database_url or settings.")

    engine = create_engine_for_url(target_url)
    engine.dispose()

    config = _alembic_config(target_url)
    command.upgrade(config, "head")


def _alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option(
        "script_location", _escape_configparser_value(str(_alembic_directory()))
    )
    config.attributes["database_url"] = database_url
    return config


def _escape_configparser_value(value: str) -> str:
    return value.replace("%", "%%")


def _alembic_directory() -> Path:
    return Path(__file__).resolve().parent / "alembic"


def main() -> None:
    from backend.app.core.settings import Settings

    run_migrations(settings=Settings())


if __name__ == "__main__":
    main()
