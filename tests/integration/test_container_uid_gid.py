from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_entrypoint_prepares_config_before_dropping_privileges() -> None:
    entrypoint = _read("docker/entrypoint.sh")

    mkdir_index = entrypoint.index('mkdir -p "$CONFIG_DIR"')
    chown_index = entrypoint.index('chown -R "$PUID:$PGID" "$CONFIG_DIR"')
    migration_index = entrypoint.index("run_as_app python -m backend.app.db.migrations")
    uvicorn_index = entrypoint.index('exec_as_app "$@"')

    assert mkdir_index < chown_index < migration_index < uvicorn_index


def test_entrypoint_creates_or_reuses_requested_group_and_user() -> None:
    entrypoint = _read("docker/entrypoint.sh")

    assert 'PUID="${PUID:-1000}"' in entrypoint
    assert 'PGID="${PGID:-1000}"' in entrypoint
    assert 'getent group "$1"' in entrypoint
    assert 'getent passwd "$1"' in entrypoint
    assert 'groupadd --gid "$PGID" "$group_name"' in entrypoint
    assert 'useradd \\' in entrypoint
    assert '--uid "$PUID"' in entrypoint
    assert '--gid "$group_name"' in entrypoint


def test_entrypoint_runs_migrations_and_uvicorn_as_requested_uid_gid() -> None:
    entrypoint = _read("docker/entrypoint.sh")

    assert "run_as_app python -m backend.app.db.migrations" in entrypoint
    assert 'exec_as_app "$@"' in entrypoint
    assert 'setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"' in entrypoint
    assert 'gosu "$PUID:$PGID" "$@"' in entrypoint
    assert 'su-exec "$PUID:$PGID" "$@"' in entrypoint
