from __future__ import annotations

import os
import secrets as secrets_lib
from pathlib import Path

APP_SECRET_FILENAME = "app_secret"


def ensure_app_secret(config_dir: Path) -> str:
    config_path = Path(config_dir)
    config_path.mkdir(parents=True, exist_ok=True)

    secret_path = config_path / APP_SECRET_FILENAME
    if secret_path.exists():
        os.chmod(secret_path, 0o600)
        return secret_path.read_text(encoding="utf-8").strip()

    secret = secrets_lib.token_urlsafe(48)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        file_descriptor = os.open(secret_path, flags, 0o600)
    except FileExistsError:
        os.chmod(secret_path, 0o600)
        return secret_path.read_text(encoding="utf-8").strip()

    with os.fdopen(file_descriptor, "w", encoding="utf-8") as secret_file:
        secret_file.write(f"{secret}\n")
    os.chmod(secret_path, 0o600)
    return secret
