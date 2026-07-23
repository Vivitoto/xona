# Xona

Xona is a local-first Docker web app for scanning mounted media roots, matching xchina metadata, previewing organization plans, writing Emby-compatible metadata, and keeping file operations reversible.

## Local Setup

Install backend test tools and frontend dependencies:

```bash
python3 -m pip install -e ".[test]"
cd frontend && npm install
```

Run focused local checks without Docker:

```bash
python3 -m pytest tests/backend tests/integration
python3 -m ruff check backend tests
python3 -m mypy backend/app
cd frontend && npm test -- --run && npm run lint && npm run typecheck && npm run build
```

## Release Gate

The mandatory local release gate is:

```bash
bash scripts/release_gate.sh
```

It runs backend tests, integration tests, lint, mypy, frontend unit tests, frontend lint, frontend typecheck, production build, Playwright, Docker Compose build/up, in-container migrations, healthcheck, synthetic disposable smoke, fixture privacy checks, and Docker Compose cleanup. It does not push, publish, upload, or include the real xchina smoke.

Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/path/to/chromium` when Playwright must use a system browser. The release gate also accepts `XONA_PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` and maps it to the Playwright variable when the Playwright variable is unset.

## Docker Compose

Use disposable local paths for first runs:

```bash
mkdir -p config media
docker compose build
docker compose up -d
python docker/healthcheck.py
docker compose down
```

The Compose service is named `app`; migrations can be run in the container with:

```bash
docker compose exec -T app python -m backend.app.db.migrations
```

## Environment Variables

Common local variables:

| Variable | Purpose |
| --- | --- |
| `XONA_PORT` | Host port for the web app, default `8732`. |
| `CONFIG_ROOT` | Host directory mounted to `/config`, default `./config`. |
| `MEDIA_ROOT` | Host directory mounted to `/a`, default `./media`. |
| `STORAGE_ROOTS` | Bootstrap storage roots inside the container, default `/a`. |
| `PUID` / `PGID` | UID/GID used by the container process, default `1000`. |
| `CONFIG_DIR` | In-container config directory, default `/config`. |
| `DATABASE_URL` | Optional database URL override. |
| `FLARESOLVERR_URL` | Exact FlareSolverr endpoint, including any path. |
| `PROXY_URL` | Optional proxy URL for configured integrations. |
| `EMBY_SERVER_URL` / `EMBY_API_KEY` | Optional Emby integration settings. |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` | Optional Chromium executable for Playwright. |

Do not store real cookies, passwords, API keys, or proxy credentials in committed files.

## Real Xchina Smoke

`scripts/real_xchina_smoke.py` is separate from the default release gate. It is opt-in and read-only, requires `XONA_REAL_XCHINA_SMOKE=1`, `XONA_REAL_XCHINA_FLARESOLVERR_URL`, and `XONA_REAL_XCHINA_QUERY`, and must use only its generated disposable root. It is never part of default release gates and must not touch user media.
