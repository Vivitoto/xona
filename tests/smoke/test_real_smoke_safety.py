from __future__ import annotations

from pathlib import Path

import pytest

from scripts import real_xchina_smoke
from scripts.disposable_smoke import SmokeSafetyError, cleanup_disposable_root, create_disposable_root


def test_real_smoke_is_skipped_without_explicit_opt_in() -> None:
    result = real_xchina_smoke.run_real_xchina_smoke(environ={})

    assert result.status == "skipped"
    assert result.enabled is False
    assert result.read_only is True
    assert result.organized_files == 0
    assert result.result_count == 0


def test_real_smoke_requires_all_explicit_environment_variables() -> None:
    with pytest.raises(SmokeSafetyError, match="must be set"):
        real_xchina_smoke.config_from_env({real_xchina_smoke.ENABLE_ENV: "true"})

    with pytest.raises(SmokeSafetyError, match=real_xchina_smoke.FLARESOLVERR_URL_ENV):
        real_xchina_smoke.config_from_env({real_xchina_smoke.ENABLE_ENV: "1"})

    with pytest.raises(SmokeSafetyError, match=real_xchina_smoke.QUERY_ENV):
        real_xchina_smoke.config_from_env(
            {
                real_xchina_smoke.ENABLE_ENV: "1",
                real_xchina_smoke.FLARESOLVERR_URL_ENV: "http://solver.local:8191/v1",
            }
        )

    config = real_xchina_smoke.config_from_env(
        {
            real_xchina_smoke.ENABLE_ENV: "1",
            real_xchina_smoke.FLARESOLVERR_URL_ENV: "http://solver.local:8191/v1",
            real_xchina_smoke.QUERY_ENV: "SMOKE-001",
        }
    )
    assert config.enabled is True
    assert config.flaresolverr_url == "http://solver.local:8191/v1"
    assert config.query == "SMOKE-001"


def test_real_smoke_path_guard_rejects_symlink_home_broad_and_outside_paths(tmp_path: Path) -> None:
    root = create_disposable_root()
    try:
        inside = root / "probe"
        inside.write_text("probe", encoding="utf-8")
        assert (
            real_xchina_smoke.validate_real_smoke_path(
                inside,
                disposable_root=root,
                require_exists=True,
            )
            == inside
        )

        link = root / "probe-link"
        link.symlink_to(inside)
        with pytest.raises(SmokeSafetyError, match="symlink"):
            real_xchina_smoke.validate_real_smoke_path(
                link,
                disposable_root=root,
                require_exists=True,
            )

        with pytest.raises(SmokeSafetyError, match="home-directory"):
            real_xchina_smoke.validate_real_smoke_path(
                Path.home(),
                disposable_root=root,
                require_exists=True,
            )

        with pytest.raises(SmokeSafetyError, match="broad"):
            real_xchina_smoke.validate_real_smoke_path(
                Path("/"),
                disposable_root=root,
                require_exists=True,
            )

        outside = tmp_path / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        with pytest.raises(SmokeSafetyError, match="outside"):
            real_xchina_smoke.validate_real_smoke_path(
                outside,
                disposable_root=root,
                require_exists=True,
            )
    finally:
        cleanup_disposable_root(root)


def test_opted_in_real_smoke_is_read_only_and_uses_injected_search_without_organization() -> None:
    calls: list[real_xchina_smoke.RealSmokeConfig] = []

    async def fake_search(config: real_xchina_smoke.RealSmokeConfig) -> list[object]:
        calls.append(config)
        return [{"title": "synthetic result"}]

    result = real_xchina_smoke.run_real_xchina_smoke(
        environ={
            real_xchina_smoke.ENABLE_ENV: "1",
            real_xchina_smoke.FLARESOLVERR_URL_ENV: "http://solver.local:8191/v1",
            real_xchina_smoke.QUERY_ENV: "SMOKE-001",
        },
        search_runner=fake_search,
    )

    assert result.status == "passed"
    assert result.enabled is True
    assert result.read_only is True
    assert result.organized_files == 0
    assert result.result_count == 1
    assert result.disposable_root is not None
    assert not result.disposable_root.exists()
    assert [call.query for call in calls] == ["SMOKE-001"]


def test_default_real_smoke_does_not_call_network() -> None:
    def forbidden_search(_config: real_xchina_smoke.RealSmokeConfig) -> list[object]:
        raise AssertionError("network/search runner should not be called without opt-in")

    result = real_xchina_smoke.run_real_xchina_smoke(
        environ={},
        search_runner=forbidden_search,
    )

    assert result.status == "skipped"
