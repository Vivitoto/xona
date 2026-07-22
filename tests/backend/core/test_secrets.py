import stat
from pathlib import Path

from backend.app.core.secrets import ensure_app_secret


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
