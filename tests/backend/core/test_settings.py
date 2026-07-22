import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import pytest

from backend.app.core.redaction import REDACTED
from backend.app.core.settings import Settings
from backend.app.main import create_app


SETTINGS_ENV_VARS = (
    "CONFIG_DIR",
    "DATABASE_URL",
    "STORAGE_ROOTS",
    "FLARESOLVERR_URL",
    "PROXY_URL",
    "EMBY_SERVER_URL",
    "EMBY_API_KEY",
    "AUTH_ENABLED",
    "WORKER_ENABLED",
    "MONITOR_ENABLED",
)


@pytest.fixture(autouse=True)
def clean_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_default_config_dir_and_database_url() -> None:
    settings = Settings()

    assert settings.config_dir == Path("/config")
    assert settings.database_url is None
    assert settings.effective_database_url == "sqlite:////config/xona.db"


def test_explicit_database_url_overrides_default_config_database(tmp_path: Path) -> None:
    configured_url = "sqlite:////tmp/custom-xona.db"

    settings = Settings(config_dir=tmp_path / "config", database_url=configured_url)

    assert settings.effective_database_url == configured_url


def test_storage_roots_env_parses_to_immutable_absolute_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORAGE_ROOTS", "/a:/storage/media")

    settings = Settings()

    assert settings.storage_roots == (Path("/a"), Path("/storage/media"))
    assert isinstance(settings.storage_roots, tuple)
    with pytest.raises(AttributeError):
        settings.storage_roots.append(Path("/other"))


def test_storage_roots_do_not_resolve_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "real-media"
    target.mkdir()
    symlink = tmp_path / "media-link"
    symlink.symlink_to(target, target_is_directory=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STORAGE_ROOTS", symlink.name)

    settings = Settings()

    assert settings.storage_roots == (tmp_path / symlink.name,)
    assert settings.storage_roots[0] != target


def test_flaresolverr_url_is_preserved_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = "http://solver.local:8191/custom/path?token=a%2Fb"
    monkeypatch.setenv("FLARESOLVERR_URL", endpoint)

    settings = Settings()

    assert settings.flaresolverr_url == endpoint


def test_public_settings_redacts_secret_values() -> None:
    settings = Settings(
        flaresolverr_url="http://solver.local:8191/custom",
        proxy_url="http://proxy-user:proxy-pass@proxy.local:8080",
        emby_server_url="http://emby.local:8096",
        emby_api_key="emby-api-key-secret",
    )

    public_settings = settings.public_dict()
    rendered = repr(public_settings)

    assert public_settings["flaresolverr_url"] == "http://solver.local:8191/custom"
    assert public_settings["emby_server_url"] == "http://emby.local:8096"
    assert "proxy-user" not in rendered
    assert "proxy-pass" not in rendered
    assert "emby-api-key-secret" not in rendered
    assert public_settings.get("emby_api_key") in {None, REDACTED}
    assert REDACTED in rendered


def test_create_app_accepts_settings_injection(tmp_path: Path) -> None:
    settings = Settings(config_dir=tmp_path / "config")

    app = create_app(settings)

    assert app.title == "Xona"
    assert app.state.settings is settings


def test_pydantic_settings_lower_bound_supports_no_decode() -> None:
    pyproject_path = Path(__file__).parents[3] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    requirement = next(
        (
            dependency
            for dependency in dependencies
            if dependency.lower().startswith("pydantic-settings")
        ),
        None,
    )

    assert requirement is not None
    match = re.search(r">=\s*(\d+(?:\.\d+){0,2})", requirement)
    assert match is not None

    lower_bound = tuple(int(part) for part in match.group(1).split("."))
    lower_bound += (0,) * (3 - len(lower_bound))

    assert lower_bound >= (2, 7, 0), "NoDecode requires pydantic-settings>=2.7.0"
