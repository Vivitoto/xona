from __future__ import annotations

import stat
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _assert_in_order(text: str, snippets: list[str]) -> None:
    position = -1
    for snippet in snippets:
        next_position = text.find(snippet, position + 1)
        assert next_position != -1, f"missing ordered snippet: {snippet}"
        position = next_position


def test_release_gate_script_has_fail_fast_root_chdir_and_redacted_output() -> None:
    script_path = PROJECT_ROOT / "scripts" / "release_gate.sh"
    script = script_path.read_text(encoding="utf-8")

    assert script.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in script
    assert 'cd "${REPO_ROOT}"' in script
    assert script_path.stat().st_mode & stat.S_IXUSR
    assert "redact_stream()" in script
    assert "********" in script
    assert "printenv" not in script
    assert "env |" not in script


def test_release_gate_runs_required_commands_in_order() -> None:
    script = _read("scripts/release_gate.sh")

    _assert_in_order(
        script,
        [
            'run_step "Backend and integration tests" python -m pytest tests/backend tests/integration',
            'run_step "Backend lint" python -m ruff check backend tests',
            'run_step "Backend typecheck" python -m mypy backend/app',
            "cd frontend",
            'run_step "Frontend unit tests" npm test -- --run',
            'run_step "Frontend lint" npm run lint',
            'run_step "Frontend typecheck" npm run typecheck',
            'run_step "Frontend build" npm run build',
            'run_step "Frontend Playwright" npx playwright test',
            "cd ..",
            "COMPOSE_TOUCHED=1",
            'run_step "Docker Compose build" docker compose build',
            'run_step "Docker Compose up" docker compose up -d',
            'run_step "Container healthcheck" wait_for_container_health',
            (
                'run_step "In-container migrations" docker compose exec -T app '
                "python -m backend.app.db.migrations"
            ),
            'run_step "Disposable media smoke script" python scripts/disposable_smoke.py',
            (
                'run_step "Disposable media and fixture privacy tests" python -m pytest '
                "tests/smoke/test_disposable_media_smoke.py "
                "tests/backend/fixtures/test_fixture_privacy.py"
            ),
            'run_step "Fixture privacy script" python scripts/check_plan_fixture_privacy.py',
            'run_step "Docker Compose down" docker compose down',
        ],
    )


def test_release_gate_trap_runs_compose_down_after_compose_is_touched() -> None:
    script = _read("scripts/release_gate.sh")

    assert "COMPOSE_TOUCHED=0" in script
    assert "trap cleanup EXIT" in script
    assert "trap - EXIT" in script
    assert 'if [[ "${COMPOSE_TOUCHED}" == "1" ]]; then' in script
    assert "docker compose down 2>&1 | redact_stream || true" in script
    assert script.index("COMPOSE_TOUCHED=1") < script.index(
        'run_step "Docker Compose build" docker compose build'
    )


def test_release_gate_keeps_real_xchina_smoke_separate_and_opt_in() -> None:
    script = _read("scripts/release_gate.sh")
    docs = _read("docs/plans/2026-07-22-xona-release-gates.md")
    readme = _read("README.md")

    assert "real_xchina_smoke.py" not in script
    for body in (docs, readme):
        lowered = body.lower()
        assert "scripts/real_xchina_smoke.py" in body
        assert "opt-in" in lowered
        assert "read-only" in lowered
        assert "not part of default release gates" in lowered or "separate from the default release gate" in lowered
        assert "user media" in lowered


def test_docs_record_exact_gates_cleanup_and_playwright_env() -> None:
    docs = _read("docs/plans/2026-07-22-xona-release-gates.md")
    readme = _read("README.md")

    for snippet in [
        "python -m pytest tests/backend tests/integration",
        "python -m ruff check backend tests",
        "python -m mypy backend/app",
        "cd frontend && npm test -- --run",
        "cd frontend && npm run lint",
        "cd frontend && npm run typecheck",
        "cd frontend && npm run build",
        "cd frontend && npx playwright test",
        "docker compose build",
        "docker compose up -d",
        "docker compose exec -T app python -m backend.app.db.migrations",
        "python docker/healthcheck.py",
        "python scripts/disposable_smoke.py",
        "python scripts/check_plan_fixture_privacy.py",
        "docker compose down",
    ]:
        assert snippet in docs

    for body in (docs, readme):
        assert "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH" in body
        assert "XONA_PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH" in body
        assert "docker compose down" in body
        assert "push, publish, upload" in body
        assert "synthetic" in body.lower()
        assert "disposable" in body.lower()


def _write_fake_command(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _run_release_gate_with_fake_tools(tmp_path: Path, *, fail_selector: str) -> tuple[int, list[str]]:
    import os
    import subprocess

    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    log_path = tmp_path / "commands.log"

    python_body = f"""
set -euo pipefail
printf 'python %s\\n' "$*" >> {log_path}
if [[ "$*" == "-m pytest tests/backend tests/integration" && "{fail_selector}" == "backend" ]]; then
  exit 42
fi
exit 0
"""
    npm_body = f"""
set -euo pipefail
printf 'npm %s\\n' "$*" >> {log_path}
exit 0
"""
    npx_body = f"""
set -euo pipefail
printf 'npx %s\\n' "$*" >> {log_path}
exit 0
"""
    docker_body = f"""
set -euo pipefail
printf 'docker %s\\n' "$*" >> {log_path}
if [[ "$*" == "compose up -d" && "{fail_selector}" == "compose-up" ]]; then
  exit 43
fi
exit 0
"""
    _write_fake_command(fakebin / "python", python_body)
    _write_fake_command(fakebin / "python3", python_body)
    _write_fake_command(fakebin / "npm", npm_body)
    _write_fake_command(fakebin / "npx", npx_body)
    _write_fake_command(fakebin / "docker", docker_body)

    env = os.environ.copy()
    env["PATH"] = f"{fakebin}:/usr/bin:/bin"
    env["XONA_PYTHON_BIN"] = "python"
    result = subprocess.run(
        ["bash", "scripts/release_gate.sh"],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    commands = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
    return result.returncode, commands


def test_release_gate_fail_fast_when_backend_gate_fails(tmp_path: Path) -> None:
    returncode, commands = _run_release_gate_with_fake_tools(tmp_path, fail_selector="backend")

    assert returncode == 42
    assert commands == ["python -m pytest tests/backend tests/integration"]


def test_release_gate_trap_cleans_up_after_compose_failure(tmp_path: Path) -> None:
    returncode, commands = _run_release_gate_with_fake_tools(tmp_path, fail_selector="compose-up")

    assert returncode == 43
    assert "docker compose build" in commands
    assert "docker compose up -d" in commands
    assert commands[-1] == "docker compose down"
    assert "docker compose exec -T app python -m backend.app.db.migrations" not in commands
