from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from backend.app.main import create_app
from scripts import check_api_contract, check_plan_fixture_privacy

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_static_analysis_config_declares_requested_scope() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '[tool.ruff]' in pyproject
    assert 'src = ["backend", "tests"]' in pyproject
    assert '[tool.mypy]' in pyproject
    assert 'files = ["backend/app"]' in pyproject
    assert '"mypy>=1.11.0"' in pyproject
    assert '"ruff>=0.6.0"' in pyproject


def test_backend_openapi_exposes_public_api_paths() -> None:
    paths = create_app().openapi()["paths"]

    assert "/api/history/plans" in paths
    assert "/api/organize-records" in paths
    assert "/api/organize-records/{record_id}" in paths
    assert "/api/organize-records/{record_id}/rollback" in paths
    assert "/api/plans/{plan_id}/rollback" in paths
    assert "/api/watch-rules" in paths


def test_api_contract_script_loads_backend_paths_from_openapi() -> None:
    openapi_paths = {
        path for path in create_app().openapi()["paths"] if path.startswith("/api")
    }
    loaded_paths = set(check_api_contract.load_backend_openapi_paths())

    assert openapi_paths <= loaded_paths
    assert "/api/local-metadata/cache/{asset_id:path}" in loaded_paths
    assert "/api/local-metadata/plans/{plan_id}/cleanup-cache" in loaded_paths
    assert check_api_contract.route_matches(
        "/api/local-metadata/cache/frames/frame.jpg",
        "/api/local-metadata/cache/{asset_id:path}",
    )


def test_fixture_privacy_script_reuses_pytest_banned_patterns() -> None:
    privacy_test = _load_fixture_privacy_test()

    assert check_plan_fixture_privacy.FORBIDDEN_LITERAL == privacy_test.FORBIDDEN_LITERAL
    assert [pattern.pattern for pattern in check_plan_fixture_privacy.FORBIDDEN_REGEX] == [
        pattern.pattern for pattern in privacy_test.FORBIDDEN_REGEX
    ]


def test_fixture_privacy_script_passes_for_current_fixtures(capsys) -> None:
    assert check_plan_fixture_privacy.main([]) == 0

    output = capsys.readouterr().out
    assert "Fixture privacy check passed" in output


def test_fixture_privacy_script_reports_forbidden_content(tmp_path: Path, capsys) -> None:
    fixture_path = tmp_path / "leaky.html"
    fixture_path.write_text(
        "Set-Cookie: session=secret\nSaved at /home/example/live-dump.html",
        encoding="utf-8",
    )

    assert check_plan_fixture_privacy.main([str(tmp_path)]) == 1

    output = capsys.readouterr().out
    assert "Set-Cookie" in output
    assert "/(?:Users|home)/[A-Za-z0-9_.-]+" in output


def _load_fixture_privacy_test() -> ModuleType:
    test_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "test_fixture_privacy.py"
    )
    spec = importlib.util.spec_from_file_location("_fixture_privacy_test", test_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
