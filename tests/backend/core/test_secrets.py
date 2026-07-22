import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from backend.app.core.secrets import APP_SECRET_FILENAME, ensure_app_secret


APP_SECRET_REJECTION_ERRORS = (OSError, RuntimeError, ValueError)


def test_ensure_app_secret_creates_config_dir_and_0600_secret_file(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"

    secret = ensure_app_secret(config_dir)

    secret_files = [path for path in config_dir.iterdir() if path.is_file()]
    assert len(secret_files) == 1

    secret_file = secret_files[0]
    assert secret_file.read_text(encoding="utf-8").strip() == secret
    assert secret
    assert stat.S_IMODE(secret_file.stat().st_mode) == 0o600


def test_ensure_app_secret_reuses_existing_secret_without_regeneration(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"

    first_secret = ensure_app_secret(config_dir)
    secret_files = [path for path in config_dir.iterdir() if path.is_file()]
    assert len(secret_files) == 1
    secret_file = secret_files[0]

    second_secret = ensure_app_secret(config_dir)

    assert second_secret == first_secret
    assert secret_file.read_text(encoding="utf-8").strip() == first_secret
    assert stat.S_IMODE(secret_file.stat().st_mode) == 0o600
    assert [path for path in config_dir.iterdir() if path.is_file()] == [secret_file]


def test_ensure_app_secret_tightens_existing_secret_file_permissions(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    secret_file = config_dir / APP_SECRET_FILENAME
    secret_file.write_text("existing-secret\n", encoding="utf-8")
    secret_file.chmod(0o644)

    secret = ensure_app_secret(config_dir)

    assert secret == "existing-secret"
    assert stat.S_IMODE(secret_file.stat().st_mode) == 0o600


def test_ensure_app_secret_concurrent_calls_share_single_0600_secret(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    worker_count = 16
    start = Barrier(worker_count)

    def call_ensure_app_secret() -> str:
        start.wait()
        return ensure_app_secret(config_dir)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(call_ensure_app_secret) for _ in range(worker_count)]
        results = [future.result() for future in futures]

    secret_path = config_dir / APP_SECRET_FILENAME
    secrets = set(results)

    assert len(secrets) == 1
    assert next(iter(secrets))
    assert secret_path.read_text(encoding="utf-8").strip() == results[0]
    assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600
    assert sorted(path.name for path in config_dir.iterdir()) == [APP_SECRET_FILENAME]


def test_ensure_app_secret_rejects_existing_empty_secret_file(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / APP_SECRET_FILENAME).write_text("\n", encoding="utf-8")

    with pytest.raises(APP_SECRET_REJECTION_ERRORS):
        ensure_app_secret(config_dir)


def test_ensure_app_secret_rejects_existing_directory_secret_path(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / APP_SECRET_FILENAME).mkdir()

    with pytest.raises(APP_SECRET_REJECTION_ERRORS):
        ensure_app_secret(config_dir)


def test_ensure_app_secret_rejects_existing_symlink_secret_file(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    target = tmp_path / "external-secret"
    target.write_text("do-not-read-through-symlink\n", encoding="utf-8")
    (config_dir / APP_SECRET_FILENAME).symlink_to(target)

    with pytest.raises(APP_SECRET_REJECTION_ERRORS):
        ensure_app_secret(config_dir)
