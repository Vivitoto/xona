from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import check_api_contract

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_frontend_quality_scripts_exist() -> None:
    package_json = json.loads(
        (REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    )

    scripts = package_json["scripts"]
    assert scripts["lint"]
    assert scripts["typecheck"]
    assert scripts["build"]


def test_frontend_api_paths_are_registered_in_backend_openapi() -> None:
    report = check_api_contract.audit_frontend_api_paths()

    assert report.missing == ()
    assert "/api/history/plans" in report.unique_frontend_paths
    assert "/api/plans/{}/rollback" in report.unique_frontend_paths
    assert "/api/watch-rules" in report.unique_frontend_paths


@pytest.mark.parametrize(
    ("raw_path", "expected"),
    [
        ("/api/jobs?state=review_required", "/api/jobs"),
        ("/api/actors${...}", "/api/actors"),
        ("/api/jobs/${jobId}/events", "/api/jobs/{}/events"),
        ("/api/actors/${actor.id}/aliases", "/api/actors/{}/aliases"),
        ("/api/plans/${planId}/rollback", "/api/plans/{}/rollback"),
        ("/api/watch-rules/{rule_id}/scan-now", "/api/watch-rules/{}/scan-now"),
        ("/api/storage-roots/browse?${query}", "/api/storage-roots/browse"),
    ],
)
def test_frontend_api_path_normalization(raw_path: str, expected: str) -> None:
    assert check_api_contract.normalize_api_path(raw_path) == expected


def test_frontend_paths_match_backend_route_templates() -> None:
    assert check_api_contract.route_matches(
        "/api/jobs/{}/events",
        "/api/jobs/{job_id}/events",
    )
    assert check_api_contract.route_matches(
        "/api/jobs/42/retry",
        "/api/jobs/{job_id}/retry",
    )
    assert check_api_contract.route_matches(
        "/api/jobs/{}/{}",
        "/api/jobs/{job_id}/retry",
    )
    assert not check_api_contract.route_matches(
        "/api/jobs/{}/unknown-action",
        "/api/jobs/{job_id}/retry",
    )


def test_api_contract_cli_reports_missing_frontend_path(
    tmp_path: Path,
    capsys,
) -> None:
    source_path = tmp_path / "Page.tsx"
    source_path.write_text('apiFetch("/api/not-a-real-route");\n', encoding="utf-8")

    assert check_api_contract.main(["--frontend-src", str(tmp_path)]) == 1

    output = capsys.readouterr().out
    assert "/api/not-a-real-route" in output
    assert "Registered backend API routes" in output


def test_api_contract_ignores_e2e_fixture_paths_under_test_tree(tmp_path: Path) -> None:
    e2e_dir = tmp_path / "e2e"
    e2e_dir.mkdir()
    (e2e_dir / "fixture.ts").write_text('fetch("/api/e2e/reset");\n', encoding="utf-8")

    report = check_api_contract.audit_frontend_api_paths(
        tmp_path,
        backend_paths=("/api/jobs",),
    )

    assert report.references == ()
    assert report.missing == ()
