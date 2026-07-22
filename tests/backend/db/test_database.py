from __future__ import annotations

from pathlib import Path

from backend.app.core.settings import Settings
from backend.app.db.session import create_engine_for_settings, get_sessionmaker


def _sqlite_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.as_posix()}"


def test_sqlite_engine_enables_wal_foreign_keys_and_busy_timeout(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    database_path = config_dir / "xona.db"
    settings = Settings(config_dir=config_dir, database_url=_sqlite_url(database_path))

    engine = create_engine_for_settings(settings)
    try:
        sessionmaker = get_sessionmaker(engine)

        with sessionmaker() as session:
            connection = session.connection()

            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
            assert (
                connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower()
                == "wal"
            )
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 5000
    finally:
        engine.dispose()
