# Xona Final Release Gates

Task 34 adds one mandatory local release gate: `scripts/release_gate.sh`. It is fail-fast, runs from the repository root, redacts common secret forms from command output, and does not push, publish, upload, or intentionally contact xchina or Emby.

## Gate Order

Run the gate with:

```bash
bash scripts/release_gate.sh
```

The script runs these gates in order:

1. Backend and integration tests: `python -m pytest tests/backend tests/integration`
2. Backend lint: `python -m ruff check backend tests`
3. Backend type check: `python -m mypy backend/app`
4. Frontend unit tests: `cd frontend && npm test -- --run`
5. Frontend lint: `cd frontend && npm run lint`
6. Frontend type check: `cd frontend && npm run typecheck`
7. Frontend production build: `cd frontend && npm run build`
8. Frontend Playwright: `cd frontend && npx playwright test`
9. Docker image build: `docker compose build`
10. Docker app startup: `docker compose up -d`
11. Container healthcheck: `python docker/healthcheck.py`（release gate 会等待健康，确保 entrypoint 自动迁移完成）
12. In-container migration idempotency check: `docker compose exec -T app python -m backend.app.db.migrations`
13. Disposable synthetic media smoke: `python scripts/disposable_smoke.py`
14. Disposable media and fixture privacy tests: `python -m pytest tests/smoke/test_disposable_media_smoke.py tests/backend/fixtures/test_fixture_privacy.py`
15. Standalone fixture privacy check: `python scripts/check_plan_fixture_privacy.py`
16. Explicit Compose cleanup: `docker compose down`

## Cleanup Behavior

The script installs an EXIT trap before running gates. Once any Docker Compose command may have touched the project, `COMPOSE_TOUCHED=1` causes the trap to run `docker compose down` on every exit path.

The explicit final `docker compose down` remains part of the gate order. The trap is a safety cleanup that also runs after failures and after the explicit cleanup step. Trap cleanup errors are ignored so the original failing gate status is preserved.

## Data And External Service Boundaries

Default release gates use only repository fixtures and synthetic disposable smoke data under generated `/tmp/xona-smoke-*` roots. They must not use real user media, committed live xchina page dumps, cookies, credentials, API keys, or proxy secrets.

The real xchina smoke command is separate, opt-in, and read-only:

```bash
XONA_REAL_XCHINA_SMOKE=1 \
XONA_REAL_XCHINA_FLARESOLVERR_URL=http://solver.example:8191/v1 \
XONA_REAL_XCHINA_QUERY=SMOKE-001 \
python scripts/real_xchina_smoke.py
```

`scripts/real_xchina_smoke.py` is not part of default release gates and is never called by `scripts/release_gate.sh`. It refuses broad or home-directory paths, creates only a disposable smoke root, organizes no files, and reports `read_only=true`.

## Environment

Playwright Chromium can be selected with `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`. The release gate also accepts `XONA_PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` as a project-specific alias and exports it to Playwright only when the existing Playwright variable is unset.

Docker Compose uses the local variables documented in `README.md`, including `XONA_PORT`, `CONFIG_ROOT`, `MEDIA_ROOT`, `STORAGE_ROOTS`, `PUID`, and `PGID`.
