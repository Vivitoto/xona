from __future__ import annotations

import errno
import os
import secrets as secrets_lib
import stat
import tempfile
from pathlib import Path

APP_SECRET_FILENAME = "app_secret"


def _read_existing_secret(secret_path: Path) -> str:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    file_descriptor = os.open(secret_path, flags)
    try:
        file_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise RuntimeError(f"{secret_path} must be a regular file")

        if stat.S_IMODE(file_stat.st_mode) != 0o600:
            os.fchmod(file_descriptor, 0o600)

        with os.fdopen(file_descriptor, "r", encoding="utf-8") as secret_file:
            file_descriptor = -1
            secret = secret_file.read().strip()
    finally:
        if file_descriptor != -1:
            os.close(file_descriptor)

    if not secret:
        raise ValueError(f"{secret_path} must not be empty")
    return secret


def ensure_app_secret(config_dir: Path) -> str:
    config_path = Path(config_dir)
    config_path.mkdir(parents=True, exist_ok=True)

    secret_path = config_path / APP_SECRET_FILENAME
    try:
        return _read_existing_secret(secret_path)
    except FileNotFoundError:
        pass

    secret = secrets_lib.token_urlsafe(48)
    file_descriptor, temp_name = tempfile.mkstemp(
        dir=config_path,
        prefix=f".{APP_SECRET_FILENAME}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        os.fchmod(file_descriptor, 0o600)
        secret_data = f"{secret}\n".encode("utf-8")
        with os.fdopen(file_descriptor, "wb") as temp_file:
            file_descriptor = -1
            written = temp_file.write(secret_data)
            if written != len(secret_data):
                raise OSError("failed to write app secret")
            temp_file.flush()
            os.fsync(temp_file.fileno())

        try:
            os.link(temp_path, secret_path)
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise
            return _read_existing_secret(secret_path)
    finally:
        if file_descriptor != -1:
            os.close(file_descriptor)
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass

    return secret
