#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

COMPOSE_TOUCHED=0
PYTHON_BIN="${XONA_PYTHON_BIN:-python}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  if [[ "${PYTHON_BIN}" == "python" ]] && command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    printf '[release-gate] missing Python executable: %s\n' "${PYTHON_BIN}" >&2
    exit 127
  fi
fi

python() {
  command "${PYTHON_BIN}" "$@"
}

redact_stream() {
  sed -E \
    -e 's#(Authorization:[[:space:]]*Bearer[[:space:]]+)[^[:space:]]+#\1********#g' \
    -e 's#(authorization:[[:space:]]*Bearer[[:space:]]+)[^[:space:]]+#\1********#g' \
    -e 's#(Bearer[[:space:]]+)[A-Za-z0-9._~+/=-]+#\1********#g' \
    -e 's#(api[_-]?key[[:space:]]*[:=][[:space:]]*)[^[:space:],;}"]+#\1********#g' \
    -e 's#(API[_-]?KEY[[:space:]]*[:=][[:space:]]*)[^[:space:],;}"]+#\1********#g' \
    -e 's#(token[[:space:]]*[:=][[:space:]]*)[^[:space:],;}"]+#\1********#g' \
    -e 's#(TOKEN[[:space:]]*[:=][[:space:]]*)[^[:space:],;}"]+#\1********#g' \
    -e 's#(password[[:space:]]*[:=][[:space:]]*)[^[:space:],;}"]+#\1********#g' \
    -e 's#(PASSWORD[[:space:]]*[:=][[:space:]]*)[^[:space:],;}"]+#\1********#g' \
    -e 's#(secret[[:space:]]*[:=][[:space:]]*)[^[:space:],;}"]+#\1********#g' \
    -e 's#(SECRET[[:space:]]*[:=][[:space:]]*)[^[:space:],;}"]+#\1********#g' \
    -e 's#(cookie[[:space:]]*[:=][[:space:]]*)[^[:space:],;}"]+#\1********#g' \
    -e 's#(COOKIE[[:space:]]*[:=][[:space:]]*)[^[:space:],;}"]+#\1********#g' \
    -e 's#(https?://[^:/[:space:]@]+):[^@/[:space:]]+@#\1:********@#g' \
    -e 's#((cf_clearance|__cf_bm)=)[^;[:space:]]+#\1********#g'
}

run_step() {
  local label="$1"
  shift
  printf '\n[release-gate] %s\n' "${label}"
  "$@" 2>&1 | redact_stream
}

cleanup() {
  local status=$?
  trap - EXIT
  if [[ "${COMPOSE_TOUCHED}" == "1" ]]; then
    printf '\n[release-gate] cleanup: docker compose down\n'
    cd "${REPO_ROOT}"
    docker compose down 2>&1 | redact_stream || true
  fi
  exit "${status}"
}

trap cleanup EXIT

if [[ -n "${XONA_PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH:-}" && -z "${PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH:-}" ]]; then
  export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH="${XONA_PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH}"
fi

run_step "Backend and integration tests" python -m pytest tests/backend tests/integration
run_step "Backend lint" python -m ruff check backend tests
run_step "Backend typecheck" python -m mypy backend/app

cd frontend
run_step "Frontend unit tests" npm test -- --run
run_step "Frontend lint" npm run lint
run_step "Frontend typecheck" npm run typecheck
run_step "Frontend build" npm run build
run_step "Frontend Playwright" npx playwright test
cd ..

COMPOSE_TOUCHED=1
run_step "Docker Compose build" docker compose build
run_step "Docker Compose up" docker compose up -d
run_step "In-container migrations" docker compose exec -T app python -m backend.app.db.migrations
run_step "Container healthcheck" python docker/healthcheck.py

run_step "Disposable media smoke script" python scripts/disposable_smoke.py
run_step "Disposable media and fixture privacy tests" python -m pytest tests/smoke/test_disposable_media_smoke.py tests/backend/fixtures/test_fixture_privacy.py
run_step "Fixture privacy script" python scripts/check_plan_fixture_privacy.py

run_step "Docker Compose down" docker compose down
COMPOSE_TOUCHED=0
