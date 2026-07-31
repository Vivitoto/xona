from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import textwrap
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CURRENT_HEAD_REVISION = "0012_local_metadata_batches"


def _sqlite_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.as_posix()}"


def _table_names(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def _alembic_revision(database_path: Path) -> str:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row is not None
    return str(row[0])


def _copy_project_for_wheel(target_root: Path) -> Path:
    source_copy = target_root / "source"
    source_copy.mkdir()
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", source_copy / "pyproject.toml")
    shutil.copytree(
        PROJECT_ROOT / "backend",
        source_copy / "backend",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return source_copy


def _installed_major_version(distribution_name: str) -> int:
    match = re.match(r"\d+", version(distribution_name))
    if match is None:
        raise ValueError(f"Cannot parse version for {distribution_name!r}.")
    return int(match.group())


def _build_isolation_args() -> list[str]:
    try:
        setuptools_major = _installed_major_version("setuptools")
        version("wheel")
    except (PackageNotFoundError, ValueError):
        return []
    if setuptools_major < 69:
        return []
    return ["--no-build-isolation"]


def test_alembic_config_preserves_percent_script_location(
    tmp_path: Path, monkeypatch
) -> None:
    from backend.app.db import migrations

    alembic_directory = (
        tmp_path / "installed%site" / "backend" / "app" / "db" / "alembic"
    )
    alembic_directory.mkdir(parents=True)
    monkeypatch.setattr(migrations, "_alembic_directory", lambda: alembic_directory)

    config = migrations._alembic_config(_sqlite_url(tmp_path / "xona.db"))

    assert config.get_main_option("script_location") == str(alembic_directory)


def test_alembic_config_keeps_percent_database_url_in_attributes(
    tmp_path: Path, monkeypatch
) -> None:
    from backend.app.db import migrations

    alembic_directory = tmp_path / "backend" / "app" / "db" / "alembic"
    alembic_directory.mkdir(parents=True)
    database_url = _sqlite_url(tmp_path / "db%2Froot" / "xona.db")
    monkeypatch.setattr(migrations, "_alembic_directory", lambda: alembic_directory)

    config = migrations._alembic_config(database_url)

    assert config.attributes["database_url"] == database_url
    assert config.get_main_option("sqlalchemy.url") is None


def test_installed_wheel_runs_packaged_alembic_migrations(tmp_path: Path) -> None:
    source_copy = _copy_project_for_wheel(tmp_path)
    wheelhouse = tmp_path / "wheelhouse"
    site_target = tmp_path / "installed%root" / "site"
    run_dir = tmp_path / "run"
    database_path = tmp_path / "db%2Froot" / "xona.db"
    wheelhouse.mkdir()
    site_target.mkdir(parents=True)
    run_dir.mkdir()

    pip_env = os.environ.copy()
    pip_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    pip_env["PIP_NO_INPUT"] = "1"
    requires_python_args = (
        ["--ignore-requires-python"] if sys.version_info < (3, 12) else []
    )
    build_isolation_args = _build_isolation_args()

    wheel_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            *build_isolation_args,
            "--no-deps",
            *requires_python_args,
            "--wheel-dir",
            str(wheelhouse),
            str(source_copy),
        ],
        cwd=tmp_path,
        env=pip_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert wheel_result.returncode == 0, (
        f"stdout:\n{wheel_result.stdout}\n\nstderr:\n{wheel_result.stderr}"
    )
    wheels = sorted(wheelhouse.glob("xona-*.whl"))
    assert len(wheels) == 1

    install_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            *requires_python_args,
            "--target",
            str(site_target),
            str(wheels[0]),
        ],
        cwd=tmp_path,
        env=pip_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert install_result.returncode == 0, (
        f"stdout:\n{install_result.stdout}\n\nstderr:\n{install_result.stderr}"
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(site_target)
    env["PYTHONSAFEPATH"] = "1"
    env["XONA_DATABASE_URL"] = _sqlite_url(database_path)
    env["XONA_INSTALLED_SITE"] = str(site_target)
    env["XONA_REPO_ROOT"] = str(PROJECT_ROOT)

    script = textwrap.dedent(
        """
        from __future__ import annotations

        import os
        import sys
        from pathlib import Path

        installed_site = Path(os.environ["XONA_INSTALLED_SITE"]).resolve()
        repo_root = Path(os.environ["XONA_REPO_ROOT"]).resolve()

        def is_relative_to(path: Path, base: Path) -> bool:
            try:
                path.relative_to(base)
            except ValueError:
                return False
            return True

        cwd = Path.cwd().resolve()
        if cwd == repo_root or is_relative_to(cwd, repo_root):
            raise AssertionError(f"subprocess cwd is inside repo: {cwd}")

        pythonpath = os.environ["PYTHONPATH"]
        pythonpath_entries = pythonpath.split(os.pathsep)
        if Path(pythonpath_entries[0]).resolve() != installed_site:
            raise AssertionError(
                "installed target is not first on PYTHONPATH: "
                f"{pythonpath!r}"
            )

        sys.path[:] = [
            str(installed_site),
            *[
                entry
                for entry in sys.path
                if entry
                and Path(entry).resolve() != installed_site
                and not is_relative_to(Path(entry).resolve(), repo_root)
            ],
        ]
        first_path = Path(sys.path[0]).resolve()
        if first_path != installed_site:
            raise AssertionError(
                f"installed target is not first on sys.path: {sys.path!r}"
            )

        for entry in sys.path:
            if not entry:
                continue
            resolved_entry = Path(entry).resolve()
            if resolved_entry == repo_root or is_relative_to(resolved_entry, repo_root):
                raise AssertionError(f"repo path leaked onto sys.path: {sys.path!r}")

        import backend

        backend_path = Path(backend.__file__).resolve()
        if not is_relative_to(backend_path, installed_site):
            raise AssertionError(
                f"backend imported outside installed target: {backend_path}"
            )
        if is_relative_to(backend_path, repo_root):
            raise AssertionError(f"backend imported from source tree: {backend_path}")

        from backend.app.db.migrations import run_migrations

        run_migrations(database_url=os.environ["XONA_DATABASE_URL"])
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    )
    assert {"settings", "storage_roots", "alembic_version"} <= _table_names(
        database_path
    )
    revision = _alembic_revision(database_path)
    assert revision == CURRENT_HEAD_REVISION
