from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection as SQLiteConnection
from typing import TYPE_CHECKING, Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from backend.app.core.settings import Settings


def create_engine_for_settings(settings: Settings) -> Engine:
    return create_engine_for_url(settings.effective_database_url)


def create_engine_for_url(database_url: str) -> Engine:
    url = make_url(database_url)
    connect_args: dict[str, Any] = {}

    if url.get_backend_name() == "sqlite":
        _ensure_sqlite_parent_directory(url.database)
        connect_args["check_same_thread"] = False

    engine = create_engine(url, connect_args=connect_args)

    if url.get_backend_name() == "sqlite":
        event.listen(engine, "connect", _configure_sqlite_connection)

    return engine


def get_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _ensure_sqlite_parent_directory(database_path: str | None) -> None:
    if not database_path or database_path == ":memory:":
        return
    Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _configure_sqlite_connection(
    dbapi_connection: SQLiteConnection,
    _connection_record: object,
) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()
