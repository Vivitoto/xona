# Xona Implementation Plan

**Implementer TDD Instruction:** This is a strict red-green-refactor plan. For every task, first create or modify only the listed tests and fixtures, run the listed failing command, and confirm the expected failure reason. Then make the smallest implementation change in only the listed application files, rerun the listed passing command, run the broader verification command when provided, and make the local commit shown for that task. Do not skip the red phase, do not touch real user media, do not use unsanitized live xchina pages as committed fixtures, and do not combine tasks unless the preceding task is already committed locally.

**Goal:** Build the first-release local-first Docker web application described in `docs/plans/2026-07-22-xona-design.md`: scan mounted media roots, search and scrape xchina metadata through a configurable exact FlareSolverr endpoint and optional proxy, score candidates, support manual and watched organization workflows, write Emby-compatible metadata and actor assets, journal reversible file operations, and optionally notify Emby. The application must be safe by default, keep state under `/config`, and never organize files without an immutable previewable plan.

**Architecture:** Use a monorepo with `backend/` for a FastAPI service, `frontend/` for a React/Vite application, `tests/` for backend and integration tests, and Docker artifacts at repository root. The backend owns settings, storage-root validation, scanning, matching, xchina scraping, metadata generation, asset materialization, actor cache, operation planning/execution, durable jobs, watch rules, Emby integration, authentication, and REST APIs. The frontend consumes existing REST APIs and provides the Dashboard, Manual Organizer, Automatic Monitors, Review Queue, Task Center, Actor Library, History/Rollback, and Settings pages. SQLite in WAL mode under `/config` is the source of truth. File operations run through a persistent single-worker queue and an operation journal.

**Path compatibility note:** Backend runtime modules include `backend/app/api/emby.py`, `backend/app/main.py`, and `backend/app/db/models.py`, preserving the required path fragments `/app/api/emby.py`, `/app/main.py`, and `/app/db/models.py`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic, SQLite WAL, watchdog with polling fallback, httpx, selectolax or BeautifulSoup/lxml, RapidFuzz, pytest, pytest-asyncio, respx, freezegun, ruff, mypy, React, TypeScript, Vite, Vitest, React Testing Library, Playwright, Docker, Docker Compose, PUID/PGID entrypoint handling, and a `/healthz` container healthcheck.

## Global Rules For Implementers

- Keep each task dependency-aware: start only after all prior tasks pass and are committed.
- Keep first release scope only. Do not add deferred AI face cropping, watermarking, translation, extra metadata providers, or mobile apps.
- For live network smoke tests, require explicit environment variables and use disposable roots under `/tmp/xona-smoke-*`; default test runs must not use the network.
- Use `/config` in production and `tmp_path` or a test-specific temporary directory in tests.
- Treat configured FlareSolverr URLs as complete endpoints. If the user stores `http://host:8191/v1`, call exactly that URL. If the user stores `http://host:8191/custom`, call exactly that URL. Never append `/v1`.
- Redact secrets in logs, API responses, task events, migration errors, Docker logs, test diagnostics, and UI output. Redacted values should appear as `********` or omit the field.
- Every SQLAlchemy model change must be shipped with an explicit Alembic migration file in the same task. Each migration task must include an upgrade test that creates a database at the prior schema state and runs `alembic upgrade head` or `backend/app/db/migrations.py::run_migrations(database_url or settings)`. Do not rely only on `Base.metadata.create_all` for migration coverage.
- `backend/app/db/migrations.py::run_migrations(database_url or settings)` is the canonical application migration entry point. Docker must run it before Uvicorn starts.
- Env `STORAGE_ROOTS` are bootstrap roots and immutable while the process runs. UI roots are persisted in SQLite. Reconciliation must never silently discard persisted roots, and execution must revalidate roots at the moment of action.
- Protect all `/api/*` routes through global auth middleware or dependency except `/api/auth/*` and intentionally public health/static paths.
- Secret updates use omission as unchanged, explicit new values as replacement, and reject redacted placeholders such as `********`. The frontend must never submit placeholder values.
- Do not add real or unsanitized xchina fixtures. Committed fixtures must be tiny, synthetic, sanitized, and free of cookies, credentials, absolute user paths, oversized live dumps, and explicit page dumps.
- Every commit command is local only. Do not push or publish.

## Task 01 - Repository Bootstrap, Packaging, Health Endpoint

**Depends on:** none.

**Files to create/modify/test:**

- Create `pyproject.toml`
- Create `.python-version`
- Create `.gitignore`
- Create `backend/__init__.py`
- Create `backend/app/__init__.py`
- Create `backend/app/main.py`
- Create `backend/app/api/__init__.py`
- Create `backend/app/api/health.py`
- Create `tests/backend/test_health.py`
- Create `tests/backend/test_installed_import.py`
- Create `frontend/package.json`
- Create `frontend/index.html`
- Create `frontend/tsconfig.json`
- Create `frontend/tsconfig.node.json`
- Create `frontend/vite.config.ts`
- Create `frontend/src/main.tsx`
- Create `frontend/src/App.tsx`
- Create `frontend/src/App.test.tsx`
- Create `frontend/src/test/setup.ts`

**Failing-test steps:**

1. Add a backend health test that imports `create_app` from `backend.app.main`, calls `GET /healthz`, and expects `{"status": "ok"}`.
2. Add an installed-package test that runs `import backend.app.main` after `python -m pip install -e .`.
3. Add a frontend shell test that renders `App` and expects a heading named `Xona`.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/test_health.py tests/backend/test_installed_import.py
```

Expected failure before implementation: `ModuleNotFoundError: No module named 'backend'` or missing `create_app`.

```bash
cd frontend && npm test -- --run src/App.test.tsx
```

Expected failure before implementation: missing `package.json` or missing Vite/Vitest dependencies.

**Minimal implementation steps:**

- Define `pyproject.toml` with `[build-system]`, `setuptools.build_meta`, explicit setuptools package discovery for `backend*`, Python `>=3.12`, runtime dependencies, and test dependencies.
- Add `backend/__init__.py` and `backend/app/__init__.py` so installed imports work consistently.
- Implement `backend/app/main.py` with `create_app()` and include the health router.
- Implement `backend/app/api/health.py` with public `GET /healthz`.
- Create a minimal React/Vite shell that renders the heading and configures Vitest with `@testing-library/jest-dom/vitest`.

**Green command and expected pass:**

```bash
python -m pip install -e ".[test]"
python -m pytest tests/backend/test_health.py tests/backend/test_installed_import.py
cd frontend && npm install && npm test -- --run src/App.test.tsx
```

Expected pass: backend health and installed import tests pass; frontend shell test passes.

**Local commit command:**

```bash
git add pyproject.toml .python-version .gitignore backend/__init__.py backend/app/__init__.py backend/app/main.py backend/app/api/__init__.py backend/app/api/health.py tests/backend/test_health.py tests/backend/test_installed_import.py frontend/package.json frontend/index.html frontend/tsconfig.json frontend/tsconfig.node.json frontend/vite.config.ts frontend/src/main.tsx frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/test/setup.ts && git commit -m "Bootstrap application packages"
```

## Task 02 - Runtime Settings, Config Directory, Secret Generation, Redaction

**Depends on:** Task 01.

**Files to create/modify/test:**

- Create `backend/app/core/__init__.py`
- Create `backend/app/core/settings.py`
- Create `backend/app/core/secrets.py`
- Create `backend/app/core/redaction.py`
- Modify `backend/app/main.py`
- Create `tests/backend/core/test_settings.py`
- Create `tests/backend/core/test_secrets.py`
- Create `tests/backend/core/test_redaction.py`

**Failing-test steps:**

1. Test default `config_dir` is `/config` and default database URL is `sqlite:////config/xona.db`.
2. Test `STORAGE_ROOTS=/a:/storage/media` parses as immutable bootstrap roots `["/a", "/storage/media"]`.
3. Test the FlareSolverr endpoint is stored exactly, including a custom path, with no normalization that appends `/v1`.
4. Test proxy URLs, Emby API keys, app secrets, cookies, and credentials are redacted in public settings and log payloads.
5. Test first-run app secret generation writes a durable `0600` file under a temporary config directory.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/core/test_settings.py tests/backend/core/test_secrets.py tests/backend/core/test_redaction.py
```

Expected failure before implementation: `ModuleNotFoundError: No module named 'backend.app.core'`.

**Minimal implementation steps:**

- Implement `Settings` with `pydantic_settings.BaseSettings`.
- Include fields for `config_dir`, `database_url`, `storage_roots`, `flaresolverr_url`, `proxy_url`, `emby_server_url`, `emby_api_key`, `auth_enabled`, `worker_enabled`, and `monitor_enabled`.
- Add `effective_database_url` returning `sqlite:///{config_dir}/xona.db` unless explicitly configured.
- Normalize bootstrap storage roots to absolute `Path` values without resolving symlinks.
- Implement `ensure_app_secret(config_dir: Path) -> str` using `secrets.token_urlsafe(48)` and no regeneration when the file already exists.
- Implement a shared redaction utility that redacts URL credentials, cookies, API keys, bearer tokens, passwords, and known secret field names.
- Wire `create_app(settings: Settings | None = None)` for dependency injection in tests.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/core/test_settings.py tests/backend/core/test_secrets.py tests/backend/core/test_redaction.py tests/backend/test_health.py
```

Expected pass: settings parse correctly, exact FlareSolverr endpoint is preserved, secrets are durable and redacted.

**Local commit command:**

```bash
git add backend/app/core/__init__.py backend/app/core/settings.py backend/app/core/secrets.py backend/app/core/redaction.py backend/app/main.py tests/backend/core/test_settings.py tests/backend/core/test_secrets.py tests/backend/core/test_redaction.py && git commit -m "Add runtime settings and redaction"
```

## Task 03 - SQLite Session, Migration Runner, Initial Schema

**Depends on:** Task 02.

**Files to create/modify/test:**

- Create `backend/app/db/__init__.py`
- Create `backend/app/db/base.py`
- Create `backend/app/db/session.py`
- Create `backend/app/db/models.py`
- Create `backend/app/db/migrations.py`
- Create `backend/app/db/alembic/env.py`
- Create `backend/app/db/alembic/script.py.mako`
- Create `backend/app/db/alembic/versions/0001_initial_settings_storage.py`
- Create `alembic.ini`
- Modify `backend/app/main.py`
- Create `tests/backend/db/test_database.py`
- Create `tests/backend/db/test_migrations_initial.py`

**Failing-test steps:**

1. Test a temporary SQLite database starts with WAL mode, foreign keys enabled, and busy timeout configured.
2. Test `run_migrations(database_url=...)` creates the initial `settings`, `storage_roots`, and Alembic version tables.
3. Test `run_migrations(settings=...)` accepts injected settings and creates the database file under a temporary config directory.
4. Test the initial migration path does not call `Base.metadata.create_all`.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/db/test_database.py tests/backend/db/test_migrations_initial.py
```

Expected failure before implementation: missing `backend.app.db.session`, missing `backend.app.db.migrations`, or missing Alembic schema.

**Minimal implementation steps:**

- Create SQLAlchemy 2 declarative base and initial models for persisted settings and storage roots.
- Implement `create_engine_for_settings(settings)` with SQLite `check_same_thread=False`, `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, and `PRAGMA busy_timeout=5000`.
- Implement `get_sessionmaker(engine)`.
- Implement `backend/app/db/migrations.py::run_migrations(database_url or settings)` as the single application migration runner.
- Configure Alembic under `backend/app/db/alembic` so `alembic upgrade head` and `run_migrations` use the same metadata.
- Keep `0001_initial_settings_storage.py` deterministic and limited to first persisted settings and storage-root tables.
- Call `run_migrations(settings=settings)` during FastAPI lifespan startup when tests enable lifespan.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/db/test_database.py tests/backend/db/test_migrations_initial.py
alembic upgrade head
```

Expected pass: migrations create the initial schema, SQLite settings are active, and app startup can run migrations.

**Local commit command:**

```bash
git add backend/app/db/__init__.py backend/app/db/base.py backend/app/db/session.py backend/app/db/models.py backend/app/db/migrations.py backend/app/db/alembic/env.py backend/app/db/alembic/script.py.mako backend/app/db/alembic/versions/0001_initial_settings_storage.py alembic.ini backend/app/main.py tests/backend/db/test_database.py tests/backend/db/test_migrations_initial.py && git commit -m "Add SQLite migrations"
```

## Task 04 - Global Authentication, Secure Cookies, Route Coverage

**Depends on:** Task 03.

**Files to create/modify/test:**

- Create `backend/app/core/auth.py`
- Create `backend/app/api/auth.py`
- Modify `backend/app/db/models.py`
- Create `backend/app/db/alembic/versions/0002_auth_tables.py`
- Modify `backend/app/main.py`
- Create `tests/backend/api/test_auth.py`
- Create `tests/backend/api/test_global_auth_routes.py`
- Create `tests/backend/api/test_secret_redaction.py`
- Create `tests/backend/db/test_migration_upgrade_0002_auth.py`

**Failing-test steps:**

1. Test auth disabled allows local access to public and API routes.
2. Test auth enabled requires login for every `/api/*` route except `/api/auth/*`.
3. Test `/healthz`, static assets, and SPA fallback paths remain public by explicit allowlist.
4. Test password hashes are stored instead of raw passwords.
5. Test session cookies use `HttpOnly`, `SameSite=Lax`, and `Secure` when HTTPS cookies are configured.
6. Test logout clears the session and unsafe cross-origin authenticated requests are rejected.
7. Test the route coverage helper fails if a new `/api/*` route is not classified as protected or intentionally public.
8. Test an old database at revision `0001` upgrades to head through `run_migrations`.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/api/test_auth.py tests/backend/api/test_global_auth_routes.py tests/backend/api/test_secret_redaction.py tests/backend/db/test_migration_upgrade_0002_auth.py
```

Expected failure before implementation: missing auth routes, missing global guard, or missing `0002_auth_tables.py`.

**Minimal implementation steps:**

- Add user credential and session tables in `backend/app/db/models.py` plus `0002_auth_tables.py`.
- Implement password hashing with `passlib.context.CryptContext`.
- Implement signed session cookies using the app secret from Task 02.
- Add `POST /api/auth/setup`, `POST /api/auth/login`, `POST /api/auth/logout`, and `GET /api/auth/me`.
- Add global middleware or a router-level dependency that protects `/api/*` except `/api/auth/*`.
- Centralize route classification in a small helper used by `tests/backend/api/test_global_auth_routes.py`.
- Run the migration upgrade test from a real revision `0001` database to head.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/api/test_auth.py tests/backend/api/test_global_auth_routes.py tests/backend/api/test_secret_redaction.py tests/backend/db/test_migration_upgrade_0002_auth.py
```

Expected pass: auth is optional, all non-exempt API routes are protected when enabled, and the auth migration upgrades cleanly.

**Local commit command:**

```bash
git add backend/app/core/auth.py backend/app/api/auth.py backend/app/db/models.py backend/app/db/alembic/versions/0002_auth_tables.py backend/app/main.py tests/backend/api/test_auth.py tests/backend/api/test_global_auth_routes.py tests/backend/api/test_secret_redaction.py tests/backend/db/test_migration_upgrade_0002_auth.py && git commit -m "Add global API authentication"
```

## Task 05 - Storage Roots Source Of Truth and Safe Browsing API

**Depends on:** Task 04.

**Files to create/modify/test:**

- Create `backend/app/services/__init__.py`
- Create `backend/app/services/settings_store.py`
- Create `backend/app/services/storage_roots.py`
- Create `backend/app/schemas/__init__.py`
- Create `backend/app/schemas/storage_roots.py`
- Create `backend/app/api/storage_roots.py`
- Modify `backend/app/main.py`
- Modify `tests/backend/api/test_global_auth_routes.py`
- Create `tests/backend/services/test_settings_store.py`
- Create `tests/backend/services/test_storage_root_source_of_truth.py`
- Create `tests/backend/services/test_storage_roots.py`
- Create `tests/backend/api/test_storage_roots_api.py`

**Failing-test steps:**

1. Test env `STORAGE_ROOTS` bootstrap roots are immutable while the process runs and are marked as env-sourced.
2. Test UI-created roots are persisted in `storage_roots` and survive process restart.
3. Test reconciliation reports removed, missing, duplicate, and invalid roots without silently deleting database rows.
4. Test execution-time validation re-resolves a stored root and refuses if it no longer exists or has become unsafe.
5. Test browsing rejects `../`, absolute paths outside roots, URL-encoded traversal, NUL, and symlink escape.
6. Test destination paths under watch sources are reported as excluded prefixes for monitor loop prevention.
7. Test storage root API routes are protected by the global auth route coverage test.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_settings_store.py tests/backend/services/test_storage_root_source_of_truth.py tests/backend/services/test_storage_roots.py tests/backend/api/test_storage_roots_api.py tests/backend/api/test_global_auth_routes.py
```

Expected failure before implementation: missing settings store, storage root service, or `/api/storage-roots` routes.

**Minimal implementation steps:**

- Implement a settings store that persists typed JSON settings with a `secret` marker and redacted read path.
- Implement `StorageRootService` with `list_roots`, `validate_inside_root`, `browse`, `reconcile_roots`, and `is_destination_inside_watch_source`.
- Use `Path.resolve(strict=False)` plus per-component existing-path checks to reject symlink escapes.
- Expose `GET /api/storage-roots`, `POST /api/storage-roots`, `PUT /api/storage-roots/{root_id}`, `DELETE /api/storage-roots/{root_id}`, `GET /api/storage-roots/browse`, and `POST /api/storage-roots/validate`.
- Return only paths that are inside configured roots.
- Register the storage API and update the global auth route coverage allow/protect list.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_settings_store.py tests/backend/services/test_storage_root_source_of_truth.py tests/backend/services/test_storage_roots.py tests/backend/api/test_storage_roots_api.py tests/backend/api/test_global_auth_routes.py
```

Expected pass: storage roots have deterministic precedence, unsafe paths are rejected, and APIs are protected.

**Local commit command:**

```bash
git add backend/app/services/__init__.py backend/app/services/settings_store.py backend/app/services/storage_roots.py backend/app/schemas/__init__.py backend/app/schemas/storage_roots.py backend/app/api/storage_roots.py backend/app/main.py tests/backend/api/test_global_auth_routes.py tests/backend/services/test_settings_store.py tests/backend/services/test_storage_root_source_of_truth.py tests/backend/services/test_storage_roots.py tests/backend/api/test_storage_roots_api.py && git commit -m "Add storage root source of truth"
```

## Task 06 - Filename Normalization and Safe Path Components

**Depends on:** Task 05.

**Files to create/modify/test:**

- Create `backend/app/services/normalization.py`
- Create `backend/app/schemas/normalization.py`
- Create `tests/backend/services/test_filename_normalization.py`

**Failing-test steps:**

1. Test Unicode NFKC normalization, punctuation cleanup, separator collapse, and whitespace cleanup.
2. Test stripping quality/source tags such as `1080p`, `4K`, `WEB-DL`, `x264`, `h264`, and `HEVC`.
3. Test useful identifiers and parent-directory hints are preserved.
4. Test site prefixes, release suffixes, and multipart markers are removed from search text but retained in structured fields.
5. Test unsafe filesystem names are sanitized without producing empty values.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_filename_normalization.py
```

Expected failure before implementation: missing normalization module or `normalize_filename_for_search`.

**Minimal implementation steps:**

- Implement `NormalizedName` and `normalize_filename_for_search`.
- Preserve work identifiers matching patterns such as `[A-Z]{2,10}-?\d{2,6}`.
- Strip only known technical tokens from bracketed fragments.
- Implement `sanitize_path_component(value: str, max_length: int = 180) -> str`.
- Reject `.` and `..`, remove control characters and NUL, replace path separators, avoid Windows reserved device names, collapse whitespace, and return `untitled` for empty output.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_filename_normalization.py
```

Expected pass: normalization and safe path component generation are deterministic.

**Local commit command:**

```bash
git add backend/app/services/normalization.py backend/app/schemas/normalization.py tests/backend/services/test_filename_normalization.py && git commit -m "Add filename normalization"
```

## Task 07 - Media Scanner, Sidecar Grouping, Stable Identity

**Depends on:** Task 06.

**Files to create/modify/test:**

- Create `backend/app/services/scanner.py`
- Create `backend/app/schemas/media.py`
- Modify `backend/app/db/models.py`
- Create `backend/app/db/alembic/versions/0003_media_items.py`
- Create `tests/backend/services/test_scanner.py`
- Create `tests/backend/db/test_migration_upgrade_0003_media_items.py`

**Failing-test steps:**

1. Test recursive and non-recursive scans with `.mp4`, `.mkv`, `.avi`, `.mov`, subtitles, images, and existing NFO.
2. Test multipart grouping for names such as `SAMPLE-CD1.mp4`, `SAMPLE-CD2.mp4`, `SAMPLE.part1.mp4`, and `SAMPLE.part2.mp4`.
3. Test ignored temporary extensions such as `.part`, `.crdownload`, `.tmp`, and configurable ignore patterns.
4. Test stable identity uses device/inode when available and falls back to path, size, and mtime.
5. Test discovered media and sidecars can be persisted with foreign keys enforced.
6. Test an old database at revision `0002` upgrades to head through `run_migrations`.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_scanner.py tests/backend/db/test_migration_upgrade_0003_media_items.py
```

Expected failure before implementation: missing scanner module, missing media models, or missing `0003_media_items.py`.

**Minimal implementation steps:**

- Add `media_items` and `media_sidecars` models plus `0003_media_items.py`.
- Implement `MediaScanItem`, `scan_directory`, supported video extensions, ignored extension checks, sidecar grouping, multipart grouping, and `media_identity`.
- Keep scanning pure; persist rows through explicit repository methods.
- Use `StorageRootService` for path validation before scanning.
- Run the migration upgrade test against a real `0002` database.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_scanner.py tests/backend/services/test_storage_roots.py tests/backend/db/test_migration_upgrade_0003_media_items.py
```

Expected pass: scanner groups media correctly and the media migration upgrades cleanly.

**Local commit command:**

```bash
git add backend/app/services/scanner.py backend/app/schemas/media.py backend/app/db/models.py backend/app/db/alembic/versions/0003_media_items.py tests/backend/services/test_scanner.py tests/backend/db/test_migration_upgrade_0003_media_items.py && git commit -m "Add media scanning"
```

## Task 08 - FlareSolverr Client With 3.4.6 Proxy Semantics

**Depends on:** Task 07.

**Files to create/modify/test:**

- Create `backend/app/integrations/__init__.py`
- Create `backend/app/integrations/flaresolverr.py`
- Create `backend/app/core/logging.py`
- Modify `backend/app/core/redaction.py`
- Create `tests/backend/integrations/test_flaresolverr.py`

**Failing-test steps:**

1. Use `respx` to assert the configured endpoint is called exactly and no `/v1` is appended.
2. Test unauthenticated proxy behavior: `request.get` without a session sends `{"proxy": {"url": "<proxy-url>"}}`.
3. Test credentialed HTTP proxy behavior: credentials are sent only on `sessions.create`, then `request.get` with that session omits `proxy`.
4. Test credentialed SOCKS proxy parsing and session creation payload.
5. Test per-request username/password is never sent on `request.get`.
6. Test session creation failure, Cloudflare block, non-ok status, timeout, malformed response, and asset request failure all redact credentials.
7. Test asset requests call the same exact endpoint and use the same proxy/session semantics.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/integrations/test_flaresolverr.py
```

Expected failure before implementation: missing FlareSolverr client or incorrect endpoint/proxy payloads.

**Minimal implementation steps:**

- Implement `FlareSolverrClient` with `request_get`, `request_asset`, `create_session`, `destroy_session`, and `test_connection`.
- Use `httpx.AsyncClient.post(endpoint, json=payload)` with `endpoint` unchanged.
- Implement proxy parsing:
  - no credentials: allow `request.get` with `proxy.url`;
  - credentials: create a session using proxy URL without credentials plus `username` and `password`;
  - `request.get` with a session omits proxy.
- Support HTTP, HTTPS, SOCKS4, and SOCKS5 proxy URL parsing.
- Redact secrets on every exception, log record, and diagnostic payload.
- Keep xchina site concurrency outside the generic client by exposing a caller-controlled limiter hook.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/integrations/test_flaresolverr.py tests/backend/core/test_redaction.py
```

Expected pass: FlareSolverr 3.4.6-compatible endpoint and proxy behavior is covered.

**Local commit command:**

```bash
git add backend/app/integrations/__init__.py backend/app/integrations/flaresolverr.py backend/app/core/logging.py backend/app/core/redaction.py tests/backend/integrations/test_flaresolverr.py && git commit -m "Add FlareSolverr client"
```

## Task 09 - XChina Search, Detail, Actor Parsing, HTTP Cache, Fixture Privacy

**Depends on:** Task 08.

**Files to create/modify/test:**

- Create `backend/app/integrations/xchina.py`
- Create `backend/app/schemas/source.py`
- Modify `backend/app/db/models.py`
- Create `backend/app/db/alembic/versions/0004_http_cache.py`
- Create `tests/backend/fixtures/xchina/search_keyword_sample.html`
- Create `tests/backend/fixtures/xchina/video_detail_sample.html`
- Create `tests/backend/fixtures/xchina/actor_detail_sample.html`
- Create `tests/backend/fixtures/test_fixture_privacy.py`
- Create `tests/backend/integrations/test_xchina_parser.py`
- Create `tests/backend/integrations/test_xchina_adapter.py`
- Create `tests/backend/db/test_migration_upgrade_0004_http_cache.py`

**Failing-test steps:**

1. Commit only sanitized fixtures with generic titles, actor names, dates, image URLs, and xchina-shaped markup.
2. Test fixture privacy scanning rejects `Set-Cookie`, `cf_clearance`, `__cf_bm`, proxy credentials, absolute user paths, oversized live dumps, explicit content text, and unsanitized full page dumps.
3. Test search route construction uses `/videos/keyword-<urlencoded>.html`.
4. Test search parsing extracts title, URL, date, thumbnail, actors, studio/series if present, and source candidate ID.
5. Test detail parsing extracts xchina ID, source URL, title, original title, plot/outline, release date, runtime, studio, series, director, actors, genres/tags, poster, fanart/backdrops, trailer if present, source snapshot eligibility, and completeness flags.
6. Test actor parsing extracts actor/model ID, canonical name, aliases, profile URL, portrait URL, biography fields, associated works, and placeholder-image detection.
7. Test adapter caches search/detail responses in `http_cache` and surfaces malformed detail errors with secrets redacted.
8. Test an old database at revision `0003` upgrades to head through `run_migrations`.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/fixtures/test_fixture_privacy.py tests/backend/integrations/test_xchina_parser.py tests/backend/integrations/test_xchina_adapter.py tests/backend/db/test_migration_upgrade_0004_http_cache.py
```

Expected failure before implementation: missing xchina parser, missing sanitized fixtures, or missing `0004_http_cache.py`.

**Minimal implementation steps:**

- Define source schemas for search results, video detail, actor detail, actor refs, and source assets.
- Implement pure parser functions for search, video detail, and actor detail.
- Implement `XChinaAdapter` with `test_connection`, `search`, `fetch_video_detail`, `fetch_actor_detail`, and response cache helpers.
- Use a single in-flight xchina limiter around FlareSolverr calls.
- Add `http_cache` model and deterministic cache keys based on method, URL, request payload version, and parser version.
- Keep fixture content synthetic and small; fixture privacy tests are part of the default backend suite.
- Run the migration upgrade test against a real `0003` database.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/fixtures/test_fixture_privacy.py tests/backend/integrations/test_xchina_parser.py tests/backend/integrations/test_xchina_adapter.py tests/backend/integrations/test_flaresolverr.py tests/backend/db/test_migration_upgrade_0004_http_cache.py
```

Expected pass: sanitized fixtures parse, HTTP cache persists safely, and fixture privacy checks pass.

**Local commit command:**

```bash
git add backend/app/integrations/xchina.py backend/app/schemas/source.py backend/app/db/models.py backend/app/db/alembic/versions/0004_http_cache.py tests/backend/fixtures/xchina/search_keyword_sample.html tests/backend/fixtures/xchina/video_detail_sample.html tests/backend/fixtures/xchina/actor_detail_sample.html tests/backend/fixtures/test_fixture_privacy.py tests/backend/integrations/test_xchina_parser.py tests/backend/integrations/test_xchina_adapter.py tests/backend/db/test_migration_upgrade_0004_http_cache.py && git commit -m "Add xchina adapter and fixture privacy checks"
```

## Task 10 - Confidence Scoring and Ambiguity Gates

**Depends on:** Task 09.

**Files to create/modify/test:**

- Create `backend/app/services/matching.py`
- Create `backend/app/schemas/matching.py`
- Create `tests/backend/services/test_matching.py`
- Create `tests/backend/services/test_confidence_ambiguity.py`
- Create `tests/backend/services/test_auto_execution_gate.py`

**Failing-test steps:**

1. Test no candidates returns `review_required` with `no_candidates`.
2. Test exact ties and non-exact ties return `review_required` with `tie`.
3. Test insufficient lead returns `review_required` when top score lead is less than `10`.
4. Test one strong candidate can auto-approve only when complete, conflict-free, asset policy satisfied, and score is at least default `92`.
5. Test non-unique detail pages, unresolved multipart groups, incomplete metadata, file conflicts, missing strict assets, threshold failures, and manual-selection safety refusals.
6. Test manual selection bypasses score threshold and lead checks but never bypasses unsafe path, conflict, incomplete required metadata, unresolved multipart, or strict asset failures.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_matching.py tests/backend/services/test_confidence_ambiguity.py tests/backend/services/test_auto_execution_gate.py
```

Expected failure before implementation: missing matching service or missing ambiguity reasons.

**Minimal implementation steps:**

- Implement score schemas with a transparent breakdown for identifier, title similarity, token coverage, studio/series, actor, date, parent hints, aliases, and asset readiness.
- Use RapidFuzz for title similarity and deterministic weighting for other components.
- Clamp scores to `0..100`.
- Implement `can_auto_execute` with required defaults: `score >= 92` and `lead >= 10`.
- Return explicit reasons for every ambiguity and safety condition listed in the failing tests.
- Implement a separate manual-selection safety gate so confidence bypass does not bypass safety.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_matching.py tests/backend/services/test_confidence_ambiguity.py tests/backend/services/test_auto_execution_gate.py
```

Expected pass: confidence, ambiguity, and manual-selection gates are deterministic and complete.

**Local commit command:**

```bash
git add backend/app/services/matching.py backend/app/schemas/matching.py tests/backend/services/test_matching.py tests/backend/services/test_confidence_ambiguity.py tests/backend/services/test_auto_execution_gate.py && git commit -m "Add confidence scoring gates"
```

## Task 11 - Metadata Records, NFO Writer, Asset Selection

**Depends on:** Task 10.

**Files to create/modify/test:**

- Create `backend/app/services/metadata.py`
- Create `backend/app/services/nfo.py`
- Create `backend/app/services/assets.py`
- Create `backend/app/schemas/metadata.py`
- Modify `backend/app/db/models.py`
- Create `backend/app/db/alembic/versions/0005_metadata_records.py`
- Create `tests/backend/services/test_metadata_model.py`
- Create `tests/backend/services/test_nfo_writer.py`
- Create `tests/backend/services/test_asset_selection.py`
- Create `tests/backend/db/test_migration_upgrade_0005_metadata_records.py`

**Failing-test steps:**

1. Test normalization from `SourceVideoDetail` to an internal metadata record.
2. Test Emby/Kodi-compatible movie NFO contains title, original title, sort title, plot/outline, release/premiere date, runtime, studio, series, director, actors with role/profile URL/portrait reference, genres, tags, xchina unique ID, and source URL.
3. Test selected asset declarations produce intended relative names: `poster.jpg`, `fanart.jpg`, numbered backdrops, `thumb.jpg`, `clearlogo.png`, `extrafanart/`, trailer, `.actors/`, normalized JSON, and optional source snapshot.
4. Test missing required logical asset declarations are surfaced before file planning.
5. Test an old database at revision `0004` upgrades to head through `run_migrations`.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_metadata_model.py tests/backend/services/test_nfo_writer.py tests/backend/services/test_asset_selection.py tests/backend/db/test_migration_upgrade_0005_metadata_records.py
```

Expected failure before implementation: missing metadata/NFO services or missing `0005_metadata_records.py`.

**Minimal implementation steps:**

- Add `metadata_records`, `search_queries`, and `search_candidates` models plus `0005_metadata_records.py`.
- Implement `MetadataRecordData`, `MetadataActor`, and `MetadataAssets`.
- Implement `render_movie_nfo(record) -> bytes` with `xml.etree.ElementTree`.
- Implement logical `select_assets(record, settings) -> AssetSelection` without downloading bytes.
- Persist normalized metadata JSON in `metadata_records.normalized_json`.
- Run the migration upgrade test against a real `0004` database.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_metadata_model.py tests/backend/services/test_nfo_writer.py tests/backend/services/test_asset_selection.py tests/backend/db/test_migration_upgrade_0005_metadata_records.py
```

Expected pass: metadata records persist, NFO XML parses, and logical asset selection is deterministic.

**Local commit command:**

```bash
git add backend/app/services/metadata.py backend/app/services/nfo.py backend/app/services/assets.py backend/app/schemas/metadata.py backend/app/db/models.py backend/app/db/alembic/versions/0005_metadata_records.py tests/backend/services/test_metadata_model.py tests/backend/services/test_nfo_writer.py tests/backend/services/test_asset_selection.py tests/backend/db/test_migration_upgrade_0005_metadata_records.py && git commit -m "Add metadata and NFO generation"
```

## Task 12 - Asset Materialization Cache and Strict/Lenient Outcomes

**Depends on:** Task 11.

**Files to create/modify/test:**

- Create `backend/app/services/asset_materializer.py`
- Create `backend/app/schemas/assets.py`
- Modify `backend/app/integrations/xchina.py`
- Modify `backend/app/db/models.py`
- Create `backend/app/db/alembic/versions/0006_asset_materializations.py`
- Create `tests/backend/services/test_asset_materializer.py`
- Create `tests/backend/services/test_asset_materializer_corruption.py`
- Create `tests/backend/db/test_migration_upgrade_0006_asset_materializations.py`

**Failing-test steps:**

1. Test selected movie images, trailer bytes, and source snapshot are fetched through `XChinaAdapter` and FlareSolverr, then cached under `/config/asset-cache` or a per-plan cache.
2. Test actor portraits are fetched through `XChinaAdapter` and cached under `/config/actor-cache`.
3. Test cache reuse avoids duplicate network calls and validates stored SHA-256 and size before reuse.
4. Test content type allowlist and maximum size validation reject invalid downloads.
5. Test strict mode fails the materialization result when required assets are missing.
6. Test lenient mode records missing assets with explicit reasons and returns remaining materialized assets.
7. Test corrupted downloads and corrupted cached files are detected and refused.
8. Test materialized output exposes concrete cached paths, byte counts, SHA-256 values, and portrait bytes needed by operation plans, `.actors` output, and Emby portrait upload.
9. Test an old database at revision `0005` upgrades to head through `run_migrations`.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_asset_materializer.py tests/backend/services/test_asset_materializer_corruption.py tests/backend/db/test_migration_upgrade_0006_asset_materializations.py
```

Expected failure before implementation: missing asset materializer, missing cache integrity handling, or missing `0006_asset_materializations.py`.

**Minimal implementation steps:**

- Add asset cache/materialization models plus `0006_asset_materializations.py`.
- Implement `AssetMaterializer.materialize(selection, policy, plan_id=None) -> MaterializedAssetSet`.
- Cache movie assets beneath `/config/asset-cache/<source>/<hash>/` or `/config/asset-cache/plans/<plan_id>/`.
- Cache actor portraits beneath `/config/actor-cache/<source>/<source_id-or-hash>/`.
- Validate HTTP content type, byte count, configured maximum size, SHA-256, and expected size before returning a usable asset.
- Store materialization records with source URL, cache path, content type, expected size, observed size, SHA-256, and missing/refusal reason.
- Return separate strict failure and lenient missing-record outcomes without writing media destination files.
- Run the migration upgrade test against a real `0005` database.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_asset_materializer.py tests/backend/services/test_asset_materializer_corruption.py tests/backend/integrations/test_xchina_adapter.py tests/backend/db/test_migration_upgrade_0006_asset_materializations.py
```

Expected pass: materialized assets are cached, verified, reusable, and policy-aware.

**Local commit command:**

```bash
git add backend/app/services/asset_materializer.py backend/app/schemas/assets.py backend/app/integrations/xchina.py backend/app/db/models.py backend/app/db/alembic/versions/0006_asset_materializations.py tests/backend/services/test_asset_materializer.py tests/backend/services/test_asset_materializer_corruption.py tests/backend/db/test_migration_upgrade_0006_asset_materializations.py && git commit -m "Add asset materialization cache"
```

## Task 13 - Actor Records, Actor Cache, Per-Movie `.actors` Output

**Depends on:** Task 12.

**Files to create/modify/test:**

- Create `backend/app/services/actors.py`
- Create `backend/app/schemas/actors.py`
- Modify `backend/app/db/models.py`
- Create `backend/app/db/alembic/versions/0007_actors.py`
- Create `tests/backend/services/test_actor_cache.py`
- Create `tests/backend/services/test_actors_output.py`
- Create `tests/backend/db/test_migration_upgrade_0007_actors.py`

**Failing-test steps:**

1. Test actor records store canonical name, aliases, xchina actor/model ID and URL, portrait source URL, local portrait cache path, biography/profile fields, associated works, last refresh timestamp, and optional Emby Person ID.
2. Test global portrait cache paths are under `/config/actor-cache` and use sanitized filenames or hashed IDs.
3. Test per-movie `.actors/<safe-name>.jpg` output plans use materialized portrait cache files or cached bytes.
4. Test `.actors` output can be planned as copy, hard link, or symlink while preserving root safety metadata.
5. Test actor merge preserves aliases, media links, portrait cache metadata, and source identifiers.
6. Test missing-image filters return actors without usable portrait cache entries.
7. Test an old database at revision `0006` upgrades to head through `run_migrations`.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_actor_cache.py tests/backend/services/test_actors_output.py tests/backend/db/test_migration_upgrade_0007_actors.py
```

Expected failure before implementation: missing actor service, missing actor models, or missing `0007_actors.py`.

**Minimal implementation steps:**

- Add `actors`, `actor_aliases`, and `actor_media_links` models plus `0007_actors.py`.
- Implement `ActorCacheService.upsert_from_source`, `portrait_cache_path`, `plan_movie_actor_outputs`, `merge`, and missing-image queries.
- Reuse `sanitize_path_component` and verified materialized portrait records.
- Return planned `.actors` outputs only; actual destination writes remain executor-owned.
- Run the migration upgrade test against a real `0006` database.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_actor_cache.py tests/backend/services/test_actors_output.py tests/backend/services/test_asset_materializer.py tests/backend/db/test_migration_upgrade_0007_actors.py
```

Expected pass: actor records, portrait cache metadata, and `.actors` output plans are deterministic.

**Local commit command:**

```bash
git add backend/app/services/actors.py backend/app/schemas/actors.py backend/app/db/models.py backend/app/db/alembic/versions/0007_actors.py tests/backend/services/test_actor_cache.py tests/backend/services/test_actors_output.py tests/backend/db/test_migration_upgrade_0007_actors.py && git commit -m "Add actor cache records"
```

## Task 14 - Naming Template Engine and Preview

**Depends on:** Task 13.

**Files to create/modify/test:**

- Create `backend/app/services/templates.py`
- Create `backend/app/schemas/templates.py`
- Modify `backend/app/services/normalization.py`
- Create `tests/backend/services/test_templates.py`

**Failing-test steps:**

1. Test supported variables: `{number}`, `{title}`, `{original_title}`, `{studio}`, `{series}`, `{year}`, `{release_date}`, `{actors}`, `{first_actor}`, `{source_filename}`, and `{xchina_id}`.
2. Test path separators, traversal, control characters, reserved names, empty values, and excessive component length are sanitized.
3. Test unknown variables return validation errors rather than silent empty strings.
4. Test live preview returns folder path, filename, and validation warnings.
5. Test templates cannot create nested paths except through explicit folder-template components sanitized one component at a time.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_templates.py
```

Expected failure before implementation: missing template engine or preview schema.

**Minimal implementation steps:**

- Implement `TemplateContext`, `RenderedTemplate`, and `TemplatePreview`.
- Derive `{year}` from `release_date`.
- Use `sanitize_path_component` for each folder and filename component.
- Return precise validation errors for unknown variables and unsafe empty output.
- Keep preview pure; do not access the filesystem in this service.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_templates.py tests/backend/services/test_filename_normalization.py
```

Expected pass: valid templates render and invalid templates report precise errors.

**Local commit command:**

```bash
git add backend/app/services/templates.py backend/app/schemas/templates.py backend/app/services/normalization.py tests/backend/services/test_templates.py && git commit -m "Add naming templates"
```

## Task 15 - Job State Machine and Persistent SQLite Worker

**Depends on:** Task 14.

**Files to create/modify/test:**

- Create `backend/app/services/jobs.py`
- Create `backend/app/services/worker.py`
- Create `backend/app/schemas/jobs.py`
- Modify `backend/app/db/models.py`
- Create `backend/app/db/alembic/versions/0008_jobs.py`
- Modify `backend/app/main.py`
- Create `tests/backend/services/test_jobs.py`
- Create `tests/backend/services/test_worker.py`
- Create `tests/backend/db/test_migration_upgrade_0008_jobs.py`

**Failing-test steps:**

1. Test valid job states and reject invalid transitions.
2. Test every transition writes a redacted `job_events` row.
3. Test durable worker leases pending jobs from SQLite and resumes after process restart.
4. Test one active job per `(rule_id, media_identity)` and one active manual job per `media_identity`.
5. Test bounded retry with exponential backoff for network stages.
6. Test cancellation prevents additional destructive work and preserves completed local operations for recovery.
7. Test an old database at revision `0007` upgrades to head through `run_migrations`.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_jobs.py tests/backend/services/test_worker.py tests/backend/db/test_migration_upgrade_0008_jobs.py
```

Expected failure before implementation: missing job service, worker, job models, or `0008_jobs.py`.

**Minimal implementation steps:**

- Add `jobs` and `job_events` models plus `0008_jobs.py`.
- Implement explicit job states: `discovered`, `waiting_stable`, `searching`, `review_required`, `matched`, `scraping`, `materializing_assets`, `planning`, `ready`, `executing`, `notifying_emby`, `completed`, `local_complete_emby_failed`, `failed`, `cancelled`, and `rolled_back`.
- Add lease fields, attempt counters, `next_run_at`, `last_error_code`, `rule_id`, `media_identity`, and redacted event payload storage.
- Implement `transition_job`, transition validation, job event writing, retry scheduling, cancellation, and deterministic `Worker.run_once()`.
- Start the worker in FastAPI lifespan only when `settings.worker_enabled` is true.
- Run the migration upgrade test against a real `0007` database.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_jobs.py tests/backend/services/test_worker.py tests/backend/db/test_migration_upgrade_0008_jobs.py
```

Expected pass: jobs are durable, transitions are validated, and events are redacted.

**Local commit command:**

```bash
git add backend/app/services/jobs.py backend/app/services/worker.py backend/app/schemas/jobs.py backend/app/db/models.py backend/app/db/alembic/versions/0008_jobs.py backend/app/main.py tests/backend/services/test_jobs.py tests/backend/services/test_worker.py tests/backend/db/test_migration_upgrade_0008_jobs.py && git commit -m "Add durable job worker"
```

## Task 16 - Immutable Operation Plans

**Depends on:** Task 15.

**Files to create/modify/test:**

- Create `backend/app/services/organizer_plans.py`
- Create `backend/app/schemas/operations.py`
- Modify `backend/app/db/models.py`
- Create `backend/app/db/alembic/versions/0009_operation_plans.py`
- Create `tests/backend/services/test_operation_plans.py`
- Create `tests/backend/services/test_organization_modes.py`
- Create `tests/backend/db/test_migration_upgrade_0009_operation_plans.py`

**Failing-test steps:**

1. Test every mode produces an immutable plan with source paths, target paths, operation type, expected size, SHA-256 when available, sidecars, generated artifacts, materialized asset cache paths, conflicts, and safety warnings.
2. Test preview mode plans no destructive file steps.
3. Test in-place mode allows identical source/destination directories and plans rename plus metadata writes.
4. Test move, copy, hard link, and symbolic link preserve grouped videos, subtitles, multipart segments, sidecars, materialized movie assets, source snapshot, and `.actors` outputs.
5. Test destination collisions fail unless the target is an explicitly allowed generated metadata replacement.
6. Test source, target, target parent, and temp parent must be inside currently configured storage roots.
7. Test an old database at revision `0008` upgrades to head through `run_migrations`.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_operation_plans.py tests/backend/services/test_organization_modes.py tests/backend/db/test_migration_upgrade_0009_operation_plans.py
```

Expected failure before implementation: missing organizer plan service, operation models, or `0009_operation_plans.py`.

**Minimal implementation steps:**

- Add `operation_plans` and `operation_steps` models plus `0009_operation_plans.py`.
- Implement immutable schemas for operation steps and plans.
- Implement `build_operation_plan` from media items, metadata records, template previews, materialized assets, actor output plans, mode, and root validation.
- Store `plan_json` as immutable data; retries create new plan versions instead of mutating completed previews.
- Use `StorageRootService` for all path validation during planning.
- Mark conflicts explicitly and never create a plan that silently overwrites existing destination files.
- Run the migration upgrade test against a real `0008` database.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_operation_plans.py tests/backend/services/test_organization_modes.py tests/backend/services/test_storage_roots.py tests/backend/db/test_migration_upgrade_0009_operation_plans.py
```

Expected pass: operation plans are immutable, complete, root-safe, and collision-aware.

**Local commit command:**

```bash
git add backend/app/services/organizer_plans.py backend/app/schemas/operations.py backend/app/db/models.py backend/app/db/alembic/versions/0009_operation_plans.py tests/backend/services/test_operation_plans.py tests/backend/services/test_organization_modes.py tests/backend/db/test_migration_upgrade_0009_operation_plans.py && git commit -m "Add immutable operation plans"
```

## Task 17 - Journaled Executor, TOCTOU Root Safety, File Integrity, Rollback

**Depends on:** Task 16.

**Files to create/modify/test:**

- Create `backend/app/services/operation_executor.py`
- Create `backend/app/services/recovery.py`
- Create `backend/app/services/rollback.py`
- Modify `backend/app/services/storage_roots.py`
- Create `tests/backend/services/test_operation_executor.py`
- Create `tests/backend/services/test_operation_toctou.py`
- Create `tests/backend/services/test_file_integrity.py`
- Create `tests/backend/services/test_operation_recovery.py`
- Create `tests/backend/services/test_rollback.py`

**Failing-test steps:**

1. Test same-filesystem move uses atomic `Path.rename` and never overwrites.
2. Test cross-filesystem move/copy computes source SHA-256 before copying, verifies target SHA-256 and size, fsyncs temp files, atomically finalizes, fsyncs destination directory, then removes source only after verification.
3. Test journal records step start, observed size, observed mtime, observed SHA-256, and safe error codes before the next step begins.
4. Test before every write, rename, copy, hard link, symlink, and remove step the executor re-resolves source, target, target parent, and temp parent.
5. Test symlink ancestors and a destination directory swapped to a symlink between preview and execution are refused.
6. Test all resolved paths remain inside currently configured mounted roots at execution time.
7. Test no-follow/open-dir patterns are used where practical for parent directories.
8. Test corruption between copy and finalize is detected and refused without removing the source.
9. Test restart recovery identifies completed, partial, and externally modified targets.
10. Test rollback verifies target size/hash/mtime before reversing and refuses if verification fails.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_operation_executor.py tests/backend/services/test_operation_toctou.py tests/backend/services/test_file_integrity.py tests/backend/services/test_operation_recovery.py tests/backend/services/test_rollback.py
```

Expected failure before implementation: missing executor, recovery, rollback, TOCTOU checks, or integrity verification.

**Minimal implementation steps:**

- Implement `OperationExecutor.execute(plan, journal)`.
- Implement `OperationJournal` methods for plan start, step start, step completion, and step failure.
- Implement `resolve_for_step` that validates source, target, target parent, temp parent, symlink ancestors, and root containment immediately before each filesystem action.
- Use destination-directory temp files named `.xona.<plan_id>.<step_id>.tmp`.
- For cross-filesystem operations, catch `errno.EXDEV`, copy to temp, verify SHA-256 and size, fsync file and directory, atomic rename into place, fsync directory again, and only then remove the source when the plan requires source removal.
- Store size, mtime, and SHA-256 in the journal for every completed file-affecting step.
- Implement recovery and rollback verification with refusal reasons that are safe to expose through APIs.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_operation_executor.py tests/backend/services/test_operation_toctou.py tests/backend/services/test_file_integrity.py tests/backend/services/test_operation_recovery.py tests/backend/services/test_rollback.py
```

Expected pass: execution is journaled, root-safe at action time, integrity-verified, recoverable, and rollback-safe.

**Local commit command:**

```bash
git add backend/app/services/operation_executor.py backend/app/services/recovery.py backend/app/services/rollback.py backend/app/services/storage_roots.py tests/backend/services/test_operation_executor.py tests/backend/services/test_operation_toctou.py tests/backend/services/test_file_integrity.py tests/backend/services/test_operation_recovery.py tests/backend/services/test_rollback.py && git commit -m "Add safe operation executor"
```

## Task 18 - Watch Rules, Stability Detection, Durable Monitor State

**Depends on:** Task 17.

**Files to create/modify/test:**

- Create `backend/app/services/watch_rules.py`
- Create `backend/app/services/stability.py`
- Create `backend/app/api/watch_rules.py`
- Create `backend/app/schemas/watch_rules.py`
- Modify `backend/app/db/models.py`
- Create `backend/app/db/alembic/versions/0010_watch_monitor_state.py`
- Modify `backend/app/main.py`
- Modify `tests/backend/api/test_global_auth_routes.py`
- Create `tests/backend/services/test_watch_rules.py`
- Create `tests/backend/services/test_stability_detection.py`
- Create `tests/backend/services/test_durable_monitor_state.py`
- Create `tests/backend/services/test_duplicate_active_jobs.py`
- Create `tests/backend/api/test_watch_rules_api.py`
- Create `tests/backend/db/test_migration_upgrade_0010_watch_monitor_state.py`

**Failing-test steps:**

1. Test watch rule storage for source directory, destination directory, recursive flag, real-time/polling mode, polling interval, stability duration, stable check count, organization mode, folder template, filename template, metadata/image selection, confidence threshold, strict/lenient asset policy, Emby options, include/exclude patterns, and excluded destination prefixes.
2. Test rule validation checks read/write capability before saving.
3. Test output-inside-source automatically stores excluded destination prefixes to prevent loops.
4. Test durable state is persisted per `(rule_id, media_identity)` with size, mtime, stable count, last enqueued job, terminal state, and last seen path.
5. Test discovered files enter `waiting_stable` only once per active identity.
6. Test processing starts only after size and mtime are unchanged for configured stable checks, minimum age is met, and temporary markers are absent.
7. Test unique constraints prevent duplicate active jobs for the same `(rule_id, media_identity)`.
8. Test restart and event-storm scenarios do not enqueue duplicate active jobs.
9. Test an old database at revision `0009` upgrades to head through `run_migrations`.
10. Test watch-rule API routes are protected by the global auth route coverage test.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_watch_rules.py tests/backend/services/test_stability_detection.py tests/backend/services/test_durable_monitor_state.py tests/backend/services/test_duplicate_active_jobs.py tests/backend/api/test_watch_rules_api.py tests/backend/api/test_global_auth_routes.py tests/backend/db/test_migration_upgrade_0010_watch_monitor_state.py
```

Expected failure before implementation: missing watch rule service, durable monitor state, unique active-job constraint, API routes, or `0010_watch_monitor_state.py`.

**Minimal implementation steps:**

- Add `watch_rules` and `monitor_media_state` models plus `0010_watch_monitor_state.py`.
- Add a partial unique index or equivalent durable lock to prevent duplicate active jobs by `(rule_id, media_identity)` while terminal states remain reusable.
- Implement `WatchRuleService` create, update, list, delete, validate, and scan-now helpers.
- Implement `StabilityDetector` with size, mtime, stable count, minimum age, temporary extension, and sibling marker checks.
- Persist excluded destination prefixes with each rule and apply them before enqueue.
- Expose `GET /api/watch-rules`, `POST /api/watch-rules`, `PUT /api/watch-rules/{rule_id}`, `DELETE /api/watch-rules/{rule_id}`, and `POST /api/watch-rules/{rule_id}/scan-now`.
- Register the API and update global auth route coverage.
- Run the migration upgrade test against a real `0009` database.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_watch_rules.py tests/backend/services/test_stability_detection.py tests/backend/services/test_durable_monitor_state.py tests/backend/services/test_duplicate_active_jobs.py tests/backend/api/test_watch_rules_api.py tests/backend/api/test_global_auth_routes.py tests/backend/db/test_migration_upgrade_0010_watch_monitor_state.py
```

Expected pass: watch rules, stability, durable monitor state, and duplicate prevention work across restarts.

**Local commit command:**

```bash
git add backend/app/services/watch_rules.py backend/app/services/stability.py backend/app/api/watch_rules.py backend/app/schemas/watch_rules.py backend/app/db/models.py backend/app/db/alembic/versions/0010_watch_monitor_state.py backend/app/main.py tests/backend/api/test_global_auth_routes.py tests/backend/services/test_watch_rules.py tests/backend/services/test_stability_detection.py tests/backend/services/test_durable_monitor_state.py tests/backend/services/test_duplicate_active_jobs.py tests/backend/api/test_watch_rules_api.py tests/backend/db/test_migration_upgrade_0010_watch_monitor_state.py && git commit -m "Add durable watch rules"
```

## Task 19 - Filesystem Monitor Integration

**Depends on:** Task 18.

**Files to create/modify/test:**

- Create `backend/app/services/monitor.py`
- Modify `backend/app/services/worker.py`
- Modify `backend/app/main.py`
- Create `tests/backend/services/test_monitor.py`
- Create `tests/backend/services/test_monitor_restart.py`

**Failing-test steps:**

1. Test watchdog event handling updates durable monitor state and enqueues a scan candidate once per stable media identity.
2. Test polling fallback scans on schedule when real-time mode is disabled or watchdog startup fails.
3. Test include/exclude patterns and excluded destination prefixes apply before enqueue.
4. Test monitor service can start, stop, and reload rules without losing in-flight jobs.
5. Test restart with preexisting durable state resumes stability counting without duplicate active jobs.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/services/test_monitor.py tests/backend/services/test_monitor_restart.py
```

Expected failure before implementation: missing monitor service or monitor/worker wiring.

**Minimal implementation steps:**

- Implement `MonitorService.start`, `stop`, `reload_rules`, and `scan_rule_once`.
- Wrap watchdog observers behind an interface so tests can inject fake events.
- On events, update `monitor_media_state`, create a `discovered` job when allowed by the unique active-job guard, and transition to `waiting_stable`.
- Polling mode should call scanner and stability detector on interval.
- Wire monitor startup in FastAPI lifespan only when `settings.monitor_enabled` is true.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/services/test_monitor.py tests/backend/services/test_monitor_restart.py tests/backend/services/test_durable_monitor_state.py tests/backend/services/test_worker.py
```

Expected pass: monitor integration is durable, restart-safe, and loop-safe.

**Local commit command:**

```bash
git add backend/app/services/monitor.py backend/app/services/worker.py backend/app/main.py tests/backend/services/test_monitor.py tests/backend/services/test_monitor_restart.py && git commit -m "Add filesystem monitor integration"
```

## Task 20 - Manual Organizer APIs

**Depends on:** Task 19.

**Files to create/modify/test:**

- Create `backend/app/api/manual.py`
- Create `backend/app/services/manual.py`
- Create `backend/app/schemas/manual.py`
- Modify `backend/app/main.py`
- Modify `tests/backend/api/test_global_auth_routes.py`
- Create `tests/backend/api/test_manual_api.py`

**Failing-test steps:**

1. Test directory scan endpoint validates storage roots and enqueues discovered media.
2. Test filename search endpoint accepts pasted local filename and editable normalized query.
3. Test batch search returns candidate cards with image, title, actors, studio/series, date, URL, confidence score, and score breakdown.
4. Test explicit manual candidate selection bypasses confidence threshold but still refuses unsafe paths, unresolved multipart, incomplete required metadata, strict asset failures, and destination collisions.
5. Test preview endpoint materializes selected assets and returns complete metadata and immutable operation plan.
6. Test execute endpoint accepts approved immutable plans only.
7. Test manual API routes are protected by the global auth route coverage test.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/api/test_manual_api.py tests/backend/api/test_global_auth_routes.py
```

Expected failure before implementation: missing `/api/manual` routes or manual orchestration service.

**Minimal implementation steps:**

- Add `POST /api/manual/scan`, `POST /api/manual/search`, `POST /api/manual/jobs/{job_id}/select-candidate`, `POST /api/manual/jobs/{job_id}/preview`, `POST /api/manual/plans/{plan_id}/execute`, and `GET /api/manual/jobs/{job_id}`.
- Use Pydantic request/response models with explicit paths as strings and normalized query fields.
- Wire scanner, xchina adapter, matching, metadata, asset materializer, actor cache, templates, operation planner, job service, and executor enqueue path.
- Persist queries, candidates, selected details, materialized assets, and plans.
- Return redacted diagnostics only and update auth route coverage.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/api/test_manual_api.py tests/backend/api/test_global_auth_routes.py tests/backend/services/test_auto_execution_gate.py tests/backend/services/test_operation_plans.py
```

Expected pass: manual API supports scan, search, select, preview, execute, and auth coverage.

**Local commit command:**

```bash
git add backend/app/api/manual.py backend/app/services/manual.py backend/app/schemas/manual.py backend/app/main.py tests/backend/api/test_global_auth_routes.py tests/backend/api/test_manual_api.py && git commit -m "Add manual organizer API"
```

## Task 21 - Emby Connector, Path Mappings, Optional Notification API

**Depends on:** Task 20.

**Files to create/modify/test:**

- Create `backend/app/integrations/emby.py`
- Create `backend/app/schemas/emby.py`
- Create `backend/app/api/emby.py`
- Modify `backend/app/services/settings_store.py`
- Modify `backend/app/services/worker.py`
- Modify `backend/app/db/models.py`
- Create `backend/app/db/alembic/versions/0011_emby_links.py`
- Modify `backend/app/main.py`
- Modify `tests/backend/api/test_global_auth_routes.py`
- Create `tests/backend/integrations/test_emby.py`
- Create `tests/backend/api/test_emby_api.py`
- Create `tests/backend/services/test_emby_retry.py`
- Create `tests/backend/db/test_migration_upgrade_0011_emby_links.py`

**Failing-test steps:**

1. Test settings support one or more container-root to Emby-visible-root mappings.
2. Test organized paths are translated through mappings before Emby lookup.
3. Test missing mapping diagnostics identify the unmatched container root without leaking secrets.
4. Test connection test reports server version, accessible libraries, authorization status, and path visibility assumptions.
5. Test API keys are never returned after save or in errors.
6. Test post-organization flow requests library scan, locates item by mapped path, refreshes item while preferring local metadata, locates linked people, uploads cached actor portrait bytes for missing person images, and persists Emby item/person associations.
7. Test local file success is not rolled back on Emby failure; job becomes `local_complete_emby_failed`.
8. Test Emby phase can be retried independently without re-running local file operations.
9. Test Emby API routes are protected by the global auth route coverage test.
10. Test an old database at revision `0010` upgrades to head through `run_migrations`.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/integrations/test_emby.py tests/backend/api/test_emby_api.py tests/backend/services/test_emby_retry.py tests/backend/api/test_global_auth_routes.py tests/backend/db/test_migration_upgrade_0011_emby_links.py
```

Expected failure before implementation: missing Emby connector/API, path mapping support, or `0011_emby_links.py`.

**Minimal implementation steps:**

- Add `emby_links` model plus `0011_emby_links.py`.
- Implement `EmbyPathMapper` for ordered container-root to Emby-visible-root mappings with clear missing-mapping diagnostics.
- Implement `EmbyClient` connection test, library scan, item lookup, item refresh, people lookup, and person portrait upload.
- Upload portraits from verified cached bytes returned by the asset materializer or actor cache.
- Add `POST /api/emby/test`, `GET /api/emby/libraries`, and `POST /api/jobs/{job_id}/retry-emby`.
- Extend worker Emby phase and independent retry behavior.
- Register routes, update auth route coverage, and run the migration upgrade test against a real `0010` database.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/integrations/test_emby.py tests/backend/api/test_emby_api.py tests/backend/services/test_emby_retry.py tests/backend/api/test_global_auth_routes.py tests/backend/db/test_migration_upgrade_0011_emby_links.py
```

Expected pass: Emby integration maps paths, uploads cached portraits, redacts secrets, and retries independently.

**Local commit command:**

```bash
git add backend/app/integrations/emby.py backend/app/schemas/emby.py backend/app/api/emby.py backend/app/services/settings_store.py backend/app/services/worker.py backend/app/db/models.py backend/app/db/alembic/versions/0011_emby_links.py backend/app/main.py tests/backend/api/test_global_auth_routes.py tests/backend/integrations/test_emby.py tests/backend/api/test_emby_api.py tests/backend/services/test_emby_retry.py tests/backend/db/test_migration_upgrade_0011_emby_links.py && git commit -m "Add Emby integration"
```

## Task 22 - Jobs and History APIs

**Depends on:** Task 21.

**Files to create/modify/test:**

- Create `backend/app/api/jobs.py`
- Create `backend/app/api/history.py`
- Create `backend/app/schemas/history.py`
- Modify `backend/app/services/jobs.py`
- Modify `backend/app/services/rollback.py`
- Modify `backend/app/main.py`
- Modify `tests/backend/api/test_global_auth_routes.py`
- Create `tests/backend/api/test_jobs_api.py`
- Create `tests/backend/api/test_history_api.py`

**Failing-test steps:**

1. Test `GET /api/jobs?state=review_required` returns only review-required jobs with gate reasons and candidate summaries.
2. Test `GET /api/jobs/{job_id}` returns current job state, payload summary, selected candidate, plan reference, retry state, and safe diagnostics.
3. Test `GET /api/jobs/{job_id}/events` returns chronological events with secrets redacted from logs and payloads.
4. Test `POST /api/jobs/{job_id}/retry` schedules a safe retry for failed or review-required jobs.
5. Test `POST /api/jobs/{job_id}/cancel` cancels pending or running jobs without corrupting completed operation steps.
6. Test `GET /api/history/plans` returns completed, failed, rolled-back, and local-complete-Emby-failed plans with verification status.
7. Test `POST /api/plans/{plan_id}/rollback` refuses rollback when target verification fails and returns a precise safe refusal reason.
8. Test jobs/history routes are protected by the global auth route coverage test.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/api/test_jobs_api.py tests/backend/api/test_history_api.py tests/backend/api/test_global_auth_routes.py
```

Expected failure before implementation: missing `backend/app/api/jobs.py`, missing `backend/app/api/history.py`, or missing required endpoints.

**Minimal implementation steps:**

- Add `GET /api/jobs`, `GET /api/jobs/{job_id}`, `GET /api/jobs/{job_id}/events`, `POST /api/jobs/{job_id}/retry`, and `POST /api/jobs/{job_id}/cancel`.
- Add `GET /api/history/plans` and `POST /api/plans/{plan_id}/rollback`.
- Keep handlers thin and delegate state changes to job, recovery, and rollback services.
- Redact event payloads and log snippets before serializing.
- Surface rollback verification refusal without exposing raw secrets or unsafe absolute paths outside configured roots.
- Register routes and update global auth route coverage.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/api/test_jobs_api.py tests/backend/api/test_history_api.py tests/backend/api/test_global_auth_routes.py tests/backend/services/test_rollback.py tests/backend/services/test_jobs.py
```

Expected pass: Review Queue, Task Center, and History/Rollback backend APIs exist and enforce redaction and safety.

**Local commit command:**

```bash
git add backend/app/api/jobs.py backend/app/api/history.py backend/app/schemas/history.py backend/app/services/jobs.py backend/app/services/rollback.py backend/app/main.py tests/backend/api/test_global_auth_routes.py tests/backend/api/test_jobs_api.py tests/backend/api/test_history_api.py && git commit -m "Add jobs and history APIs"
```

## Task 23 - Settings APIs for Storage, XChina, FlareSolverr, Proxy, Naming, Assets, Confidence, Safety, Emby, Auth

**Depends on:** Task 22.

**Files to create/modify/test:**

- Create `backend/app/api/settings.py`
- Create `backend/app/schemas/settings.py`
- Modify `backend/app/services/settings_store.py`
- Modify `backend/app/main.py`
- Modify `tests/backend/api/test_global_auth_routes.py`
- Create `tests/backend/api/test_settings_api.py`
- Create `tests/backend/api/test_settings_secret_update.py`
- Create `tests/backend/services/test_settings_store_secrets.py`

**Failing-test steps:**

1. Test settings endpoints save and retrieve storage roots, xchina settings, exact FlareSolverr endpoint, proxy, Emby settings, Emby path mappings, naming templates, metadata/assets, confidence threshold, safety options, and authentication mode.
2. Test FlareSolverr connection test returns HTTP status, elapsed time, Cloudflare state, cookie count, and sanitized errors.
3. Test xchina connection test returns sanitized source diagnostics.
4. Test template preview calls the template engine and returns warnings.
5. Test default confidence threshold is `92`.
6. Test threshold outside `0..100`, invalid mounted roots, invalid path mappings, and unsafe cache directories are rejected.
7. Test secret update semantics: omitted secret means unchanged, explicit new secret replaces the old value, and redacted placeholder values such as `********` are rejected.
8. Test settings routes are protected by the global auth route coverage test.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/api/test_settings_api.py tests/backend/api/test_settings_secret_update.py tests/backend/services/test_settings_store_secrets.py tests/backend/api/test_global_auth_routes.py
```

Expected failure before implementation: missing settings API, missing secret update behavior, or missing auth coverage.

**Minimal implementation steps:**

- Add typed schemas grouped by UI sections: `StorageSettings`, `XChinaSettings`, `EmbySettings`, `NamingSettings`, `MetadataAssetSettings`, `ConfidenceSafetySettings`, and `AuthSettings`.
- Add `GET /api/settings`, `PUT /api/settings`, `POST /api/settings/flaresolverr/test`, `POST /api/settings/xchina/test`, and `POST /api/settings/templates/preview`.
- Use shared redaction and explicit secret update semantics.
- Validate storage roots through `StorageRootService`, FlareSolverr through `FlareSolverrClient`, xchina through `XChinaAdapter`, templates through the template engine, and Emby path mappings through `EmbyPathMapper`.
- Register routes and update global auth route coverage.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/api/test_settings_api.py tests/backend/api/test_settings_secret_update.py tests/backend/services/test_settings_store_secrets.py tests/backend/api/test_global_auth_routes.py tests/backend/integrations/test_flaresolverr.py tests/backend/integrations/test_emby.py
```

Expected pass: settings are persisted, validated, redacted, and protected.

**Local commit command:**

```bash
git add backend/app/api/settings.py backend/app/schemas/settings.py backend/app/services/settings_store.py backend/app/main.py tests/backend/api/test_global_auth_routes.py tests/backend/api/test_settings_api.py tests/backend/api/test_settings_secret_update.py tests/backend/services/test_settings_store_secrets.py && git commit -m "Add settings API"
```

## Task 24 - Actor Management APIs

**Depends on:** Task 23.

**Files to create/modify/test:**

- Create `backend/app/api/actors.py`
- Modify `backend/app/services/actors.py`
- Modify `backend/app/integrations/xchina.py`
- Modify `backend/app/integrations/emby.py`
- Modify `backend/app/main.py`
- Modify `tests/backend/api/test_global_auth_routes.py`
- Create `tests/backend/api/test_actors_api.py`

**Failing-test steps:**

1. Test `GET /api/actors` supports missing-image filter and search by canonical name or alias.
2. Test `GET /api/actors/{actor_id}` returns actor profile, aliases, portrait cache state, linked works, and Emby link.
3. Test alias edit updates `actor_aliases`.
4. Test merge combines aliases, media links, and cache metadata.
5. Test image replacement validates content type and size, writes a verified cached portrait under `/config/actor-cache`, and stores SHA-256.
6. Test refresh fetches xchina actor detail through FlareSolverr with redacted diagnostics.
7. Test linked works returns local metadata records.
8. Test Emby synchronization uploads missing portraits from cached bytes when enabled and redacts API keys in errors.
9. Test actor routes are protected by the global auth route coverage test.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/api/test_actors_api.py tests/backend/api/test_global_auth_routes.py
```

Expected failure before implementation: missing actors API or missing protected-route coverage.

**Minimal implementation steps:**

- Add `GET /api/actors`, `GET /api/actors/{actor_id}`, `PUT /api/actors/{actor_id}/aliases`, `POST /api/actors/{actor_id}/merge`, `POST /api/actors/{actor_id}/portrait`, `POST /api/actors/{actor_id}/refresh`, `GET /api/actors/{actor_id}/works`, and `POST /api/actors/{actor_id}/sync-emby`.
- Validate uploaded image content type, byte size, SHA-256, and storage path.
- Delegate xchina refresh, portrait cache update, linked-work queries, and Emby sync to existing services.
- Register routes and update global auth route coverage.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/api/test_actors_api.py tests/backend/api/test_global_auth_routes.py tests/backend/services/test_actor_cache.py tests/backend/services/test_asset_materializer.py
```

Expected pass: actor management APIs support first-release actions and are protected.

**Local commit command:**

```bash
git add backend/app/api/actors.py backend/app/services/actors.py backend/app/integrations/xchina.py backend/app/integrations/emby.py backend/app/main.py tests/backend/api/test_global_auth_routes.py tests/backend/api/test_actors_api.py && git commit -m "Add actor management API"
```

## Task 25 - React App Shell, API Client, Settings Pages

**Depends on:** Task 24.

**Files to create/modify/test:**

- Modify `frontend/package.json`
- Modify `frontend/src/App.tsx`
- Create `frontend/src/api/client.ts`
- Create `frontend/src/api/types.ts`
- Create `frontend/src/components/AppLayout.tsx`
- Create `frontend/src/components/FormField.tsx`
- Create `frontend/src/pages/DashboardPage.tsx`
- Create `frontend/src/pages/SettingsPage.tsx`
- Create `frontend/src/pages/settings/StorageSettings.tsx`
- Create `frontend/src/pages/settings/XChinaSettings.tsx`
- Create `frontend/src/pages/settings/EmbySettings.tsx`
- Create `frontend/src/pages/settings/NamingSettings.tsx`
- Create `frontend/src/pages/settings/MetadataAssetSettings.tsx`
- Create `frontend/src/pages/settings/AuthSettings.tsx`
- Create `frontend/src/styles.css`
- Create `frontend/src/pages/SettingsPage.test.tsx`

**Failing-test steps:**

1. Test navigation exposes Dashboard, Manual Organizer, Automatic Monitors, Review Queue, Task Center, Actor Library, History/Rollback, and Settings.
2. Test Settings page has sections for storage roots, xchina, exact FlareSolverr endpoint, proxy, Emby, Emby path mappings, naming templates, metadata/assets, confidence/safety, and authentication.
3. Test the FlareSolverr endpoint field label makes clear the value is exact and the client does not append `/v1`.
4. Test secret fields display redacted placeholders but omit unchanged secret values from submit payloads.
5. Test explicit new secret values are submitted and placeholder strings such as `********` are never submitted.
6. Test template preview calls `/api/settings/templates/preview`.

**Red command and expected failure:**

```bash
cd frontend && npm test -- --run src/pages/SettingsPage.test.tsx src/App.test.tsx
```

Expected failure before implementation: missing API client, layout, settings pages, or secret placeholder behavior.

**Minimal implementation steps:**

- Implement `apiFetch<T>(path, options)` with same-origin base URL, JSON error handling, and auth-aware responses.
- Implement a dense utilitarian layout with accessible navigation and stable dimensions.
- Implement settings forms using backend endpoints from Task 23.
- Use tabs, checkboxes, segmented controls, numeric inputs, and clear validation messages.
- Ensure redacted placeholders are display-only values and never included in PUT payloads.
- Keep first screen as Dashboard, not a landing page.

**Green command and expected pass:**

```bash
cd frontend && npm test -- --run src/pages/SettingsPage.test.tsx src/App.test.tsx
```

Expected pass: shell and settings UI render, preserve exact endpoint semantics, and submit safe secret payloads.

**Local commit command:**

```bash
git add frontend/package.json frontend/src/App.tsx frontend/src/api/client.ts frontend/src/api/types.ts frontend/src/components/AppLayout.tsx frontend/src/components/FormField.tsx frontend/src/pages/DashboardPage.tsx frontend/src/pages/SettingsPage.tsx frontend/src/pages/settings/StorageSettings.tsx frontend/src/pages/settings/XChinaSettings.tsx frontend/src/pages/settings/EmbySettings.tsx frontend/src/pages/settings/NamingSettings.tsx frontend/src/pages/settings/MetadataAssetSettings.tsx frontend/src/pages/settings/AuthSettings.tsx frontend/src/styles.css frontend/src/pages/SettingsPage.test.tsx && git commit -m "Add React shell and settings UI"
```

## Task 26 - React Manual Organizer

**Depends on:** Task 25.

**Files to create/modify/test:**

- Create `frontend/src/pages/ManualOrganizerPage.tsx`
- Create `frontend/src/components/CandidateCard.tsx`
- Create `frontend/src/components/OperationPlanView.tsx`
- Modify `frontend/src/App.tsx`
- Modify `frontend/src/api/types.ts`
- Create `frontend/src/pages/ManualOrganizerPage.test.tsx`

**Failing-test steps:**

1. Test Manual Organizer supports directory selection, scan, pasted filename search, editable normalized query, batch search, explicit candidate selection, detail URL entry, preview, and execute.
2. Test candidate cards show image, title, actors, studio/series, date, URL, confidence score, and score breakdown.
3. Test manual selection displays safety refusal reasons for collisions, unresolved multipart, incomplete metadata, unsafe paths, and strict asset failures.
4. Test operation preview renders all planned steps, materialized assets, `.actors` outputs, conflicts, generated files, and target paths before execution.
5. Test execute action calls `/api/manual/plans/{plan_id}/execute` only after an approved preview.

**Red command and expected failure:**

```bash
cd frontend && npm test -- --run src/pages/ManualOrganizerPage.test.tsx
```

Expected failure before implementation: missing manual organizer page or components.

**Minimal implementation steps:**

- Implement the page using `/api/manual/scan`, `/api/manual/search`, `/api/manual/jobs/{job_id}/select-candidate`, `/api/manual/jobs/{job_id}/preview`, `/api/manual/plans/{plan_id}/execute`, and `/api/storage-roots/browse`.
- Use accessible buttons, loading states, disabled states, and deterministic candidate selection.
- Reuse `CandidateCard` and `OperationPlanView` with stable layouts that do not resize on hover or loading.
- Render API errors exactly enough for safety decisions without exposing secrets.

**Green command and expected pass:**

```bash
cd frontend && npm test -- --run src/pages/ManualOrganizerPage.test.tsx src/App.test.tsx
```

Expected pass: manual workflow UI renders and calls only existing backend APIs.

**Local commit command:**

```bash
git add frontend/src/pages/ManualOrganizerPage.tsx frontend/src/components/CandidateCard.tsx frontend/src/components/OperationPlanView.tsx frontend/src/App.tsx frontend/src/api/types.ts frontend/src/pages/ManualOrganizerPage.test.tsx && git commit -m "Add manual organizer UI"
```

## Task 27 - React Review Queue, Task Center, History/Rollback

**Depends on:** Task 26.

**Files to create/modify/test:**

- Create `frontend/src/pages/ReviewQueuePage.tsx`
- Create `frontend/src/pages/TaskCenterPage.tsx`
- Create `frontend/src/pages/HistoryRollbackPage.tsx`
- Create `frontend/src/components/JobTimeline.tsx`
- Modify `frontend/src/components/OperationPlanView.tsx`
- Modify `frontend/src/App.tsx`
- Modify `frontend/src/api/types.ts`
- Create `frontend/src/pages/ReviewQueuePage.test.tsx`
- Create `frontend/src/pages/TaskCenterPage.test.tsx`
- Create `frontend/src/pages/HistoryRollbackPage.test.tsx`

**Failing-test steps:**

1. Test Review Queue calls `GET /api/jobs?state=review_required` and lists review reasons from confidence and safety gates.
2. Test Task Center calls `GET /api/jobs/{job_id}`, `GET /api/jobs/{job_id}/events`, `POST /api/jobs/{job_id}/retry`, `POST /api/jobs/{job_id}/cancel`, and `POST /api/jobs/{job_id}/retry-emby`.
3. Test JobTimeline renders chronological events and never renders proxy credentials, API keys, cookies, or bearer tokens.
4. Test History/Rollback calls `GET /api/history/plans` and shows verification status.
5. Test rollback calls `POST /api/plans/{plan_id}/rollback` and displays verification refusal when rollback is unsafe.

**Red command and expected failure:**

```bash
cd frontend && npm test -- --run src/pages/ReviewQueuePage.test.tsx src/pages/TaskCenterPage.test.tsx src/pages/HistoryRollbackPage.test.tsx
```

Expected failure before implementation: missing review queue, task center, history pages, or job timeline.

**Minimal implementation steps:**

- Implement pages using jobs/history APIs from Task 22 and Emby retry API from Task 21.
- Render job state filters, retry/cancel controls, redacted event timelines, plan summaries, rollback verification status, and refusal messages.
- Reuse `OperationPlanView` for historical plans.
- Keep dense tables and lists scannable with stable row heights.

**Green command and expected pass:**

```bash
cd frontend && npm test -- --run src/pages/ReviewQueuePage.test.tsx src/pages/TaskCenterPage.test.tsx src/pages/HistoryRollbackPage.test.tsx
```

Expected pass: review, task, and history UIs render and call only existing backend APIs.

**Local commit command:**

```bash
git add frontend/src/pages/ReviewQueuePage.tsx frontend/src/pages/TaskCenterPage.tsx frontend/src/pages/HistoryRollbackPage.tsx frontend/src/components/JobTimeline.tsx frontend/src/components/OperationPlanView.tsx frontend/src/App.tsx frontend/src/api/types.ts frontend/src/pages/ReviewQueuePage.test.tsx frontend/src/pages/TaskCenterPage.test.tsx frontend/src/pages/HistoryRollbackPage.test.tsx && git commit -m "Add review task and history UI"
```

## Task 28 - React Automatic Monitors and Actor Library

**Depends on:** Task 27.

**Files to create/modify/test:**

- Create `frontend/src/pages/AutomaticMonitorsPage.tsx`
- Create `frontend/src/pages/ActorLibraryPage.tsx`
- Create `frontend/src/components/WatchRuleEditor.tsx`
- Create `frontend/src/components/ActorPortrait.tsx`
- Create `frontend/src/components/ActorMergeDialog.tsx`
- Modify `frontend/src/App.tsx`
- Modify `frontend/src/api/types.ts`
- Create `frontend/src/pages/AutomaticMonitorsPage.test.tsx`
- Create `frontend/src/pages/ActorLibraryPage.test.tsx`

**Failing-test steps:**

1. Test monitor editor supports source, destination, recursive flag, real-time/polling mode, polling interval, stability duration, stable check count, organization mode, templates, metadata/image selection, confidence threshold, asset policy, Emby options, include/exclude patterns, and excluded destination prefixes.
2. Test monitor editor warns when destination is inside watched source and shows the persisted auto-exclusion.
3. Test monitor actions call `/api/watch-rules`, `/api/watch-rules/{rule_id}`, `/api/watch-rules/{rule_id}/scan-now`, and `/api/storage-roots/browse`.
4. Test actor library supports missing-image filtering, alias editing, merge, image replacement, refresh, linked works, and Emby sync action.
5. Test actor actions call the actor APIs from Task 24 and never expose secret diagnostics.
6. Test actor portrait components use accessible alt text and render a clear placeholder state when missing.

**Red command and expected failure:**

```bash
cd frontend && npm test -- --run src/pages/AutomaticMonitorsPage.test.tsx src/pages/ActorLibraryPage.test.tsx
```

Expected failure before implementation: missing monitor and actor library pages.

**Minimal implementation steps:**

- Implement monitor page using watch-rule and storage-root APIs.
- Implement actor library page using actor APIs and Emby sync action.
- Use segmented controls for organization mode and monitor mode, checkboxes for binary settings, numeric inputs for intervals and thresholds, tabs/filters for actor library, and icon buttons with accessible labels where appropriate.
- Keep table rows dense, stable, and free of nested cards.

**Green command and expected pass:**

```bash
cd frontend && npm test -- --run src/pages/AutomaticMonitorsPage.test.tsx src/pages/ActorLibraryPage.test.tsx
```

Expected pass: monitors and actor library render all first-release controls and call only existing APIs.

**Local commit command:**

```bash
git add frontend/src/pages/AutomaticMonitorsPage.tsx frontend/src/pages/ActorLibraryPage.tsx frontend/src/components/WatchRuleEditor.tsx frontend/src/components/ActorPortrait.tsx frontend/src/components/ActorMergeDialog.tsx frontend/src/App.tsx frontend/src/api/types.ts frontend/src/pages/AutomaticMonitorsPage.test.tsx frontend/src/pages/ActorLibraryPage.test.tsx && git commit -m "Add monitor and actor library UI"
```

## Task 29 - Dockerfile, Compose, Entrypoint, PUID/PGID, Healthcheck

**Depends on:** Task 28.

**Files to create/modify/test:**

- Create `Dockerfile`
- Create `docker-compose.yml`
- Create `.env.example`
- Create `docker/entrypoint.sh`
- Create `docker/healthcheck.py`
- Modify `backend/app/main.py`
- Modify `frontend/package.json`
- Create `tests/integration/test_container_config.py`
- Create `tests/integration/test_container_uid_gid.py`

**Failing-test steps:**

1. Test Dockerfile uses a frontend build stage and a Python runtime stage that installs the backend package.
2. Test compose example maps `/config`, a disposable storage root `/a`, port `8732`, `PUID`, `PGID`, and `STORAGE_ROOTS`.
3. Test entrypoint creates or reuses the configured group/user, prepares `/config`, then runs migrations and Uvicorn as `PUID:PGID` using `gosu`, `su-exec`, or `setpriv`, so `/config/app.db` is not root-owned.
4. Test Compose defines the application service with the stable name `app` for health, migration, and release-gate commands.
5. Test healthcheck calls `http://127.0.0.1:8732/healthz`.
6. Test static frontend assets are served by FastAPI in production.
7. Test installed import of `backend.app.main` works inside the built image.
8. Test a container started with disposable `/config` and `/a` roots under the current host UID/GID runs the app process with that UID/GID and creates files under `/a` with matching ownership.

**Red command and expected failure:**

```bash
python -m pytest tests/integration/test_container_config.py tests/integration/test_container_uid_gid.py
docker build -t xona:test .
```

Expected failure before implementation: missing Docker artifacts, missing migration invocation, or process UID/GID mismatch.

**Minimal implementation steps:**

- Build frontend with `node:20` and copy `frontend/dist` into the Python runtime image.
- Install the backend package in the Python runtime image through `pip install .`.
- Add an entrypoint that creates `/config`, creates or reuses the requested group/user, applies ownership to `/config`, then runs `python -m backend.app.db.migrations` and execs Uvicorn on `0.0.0.0:8732` under the configured identity.
- Use `setpriv`, `gosu`, or `su-exec` for both migration and Uvicorn commands; keep the command non-interactive and avoid creating root-owned database files.
- Define the Compose application service as `app` so release commands can use `docker compose exec -T app ...` deterministically.
- Add FastAPI static mount and SPA fallback for non-API routes.
- Keep FlareSolverr, proxy, xchina, and Emby settings configured in the UI or environment, not hard-coded in compose.

**Green command and expected pass:**

```bash
python -m pytest tests/integration/test_container_config.py tests/integration/test_container_uid_gid.py
docker build -t xona:test .
CONFIG_ROOT="$(mktemp -d)"
MEDIA_ROOT="$(mktemp -d)"
docker run --rm -d --name xona-test -p 8732:8732 -e PUID="$(id -u)" -e PGID="$(id -g)" -e STORAGE_ROOTS=/a -v "$CONFIG_ROOT":/config -v "$MEDIA_ROOT":/a xona:test
python docker/healthcheck.py
docker rm -f xona-test
```

Expected pass: image builds, migrations run, service starts, healthcheck succeeds, and container UID/GID ownership is correct.

**Local commit command:**

```bash
git add Dockerfile docker-compose.yml .env.example docker/entrypoint.sh docker/healthcheck.py backend/app/main.py frontend/package.json tests/integration/test_container_config.py tests/integration/test_container_uid_gid.py && git commit -m "Add Docker deployment"
```

## Task 30 - Backend Integration Flow With Mocked XChina and Emby

**Depends on:** Task 29.

**Files to create/modify/test:**

- Create `tests/integration/conftest.py`
- Create `tests/integration/test_manual_end_to_end.py`
- Create `tests/integration/test_watch_end_to_end.py`
- Modify `backend/app/main.py`
- Modify `backend/app/services/manual.py`
- Modify `backend/app/services/worker.py`
- Modify `backend/app/services/monitor.py`
- Modify `backend/app/services/organizer_plans.py`
- Modify `backend/app/services/operation_executor.py`
- Modify `backend/app/integrations/xchina.py`
- Modify `backend/app/integrations/emby.py`

**Failing-test steps:**

1. Test a disposable sample media file under `tmp_path/source` can be scanned, searched against mocked xchina responses, manually selected, previewed, and executed in preview mode without changing the media file.
2. Test copy mode copies a disposable file to `tmp_path/output`, writes NFO/images from materialized fixture bytes, writes `.actors`, journals size/mtime/hash, and completes.
3. Test automatic monitor flow waits for stability, searches, scores at least `92` with at least a `10` point lead, materializes assets, plans, executes, and completes.
4. Test low confidence, exact ties, incomplete metadata, or insufficient lead becomes `review_required`.
5. Test mocked Emby failure yields `local_complete_emby_failed` and retry succeeds without touching local files again.
6. Test no integration test reads or writes outside its temporary directory.

**Red command and expected failure:**

```bash
python -m pytest tests/integration/test_manual_end_to_end.py tests/integration/test_watch_end_to_end.py
```

Expected failure before implementation: missing integration wiring or incomplete service orchestration.

**Minimal implementation steps:**

- Add integration app fixtures that create a temporary config directory, run migrations, configure storage roots to temp source/output, and override FlareSolverr, xchina, and Emby clients.
- Use only small generated text/binary sample files in `tmp_path`.
- Exercise public API calls instead of private service shortcuts where practical.
- Fix service wiring exposed by integration tests without changing public API contracts.

**Green command and expected pass:**

```bash
python -m pytest tests/integration/test_manual_end_to_end.py tests/integration/test_watch_end_to_end.py
python -m pytest tests/backend tests/integration
```

Expected pass: mocked first-release workflows complete safely in disposable directories.

**Local commit command:**

```bash
git add tests/integration/conftest.py tests/integration/test_manual_end_to_end.py tests/integration/test_watch_end_to_end.py backend/app/main.py backend/app/services/manual.py backend/app/services/worker.py backend/app/services/monitor.py backend/app/services/organizer_plans.py backend/app/services/operation_executor.py backend/app/integrations/xchina.py backend/app/integrations/emby.py && git commit -m "Add mocked backend integration flows"
```

## Task 31 - Playwright UI Integration Against Disposable Roots

**Depends on:** Task 30.

**Files to create/modify/test:**

- Modify `frontend/package.json`
- Create `frontend/playwright.config.ts`
- Create `frontend/e2e/manual-organizer.spec.ts`
- Create `frontend/e2e/settings-and-monitor.spec.ts`
- Create `frontend/e2e/review-task-history.spec.ts`
- Create `frontend/e2e/actor-library.spec.ts`
- Create `tests/integration/playwright_server.py`
- Modify `backend/app/main.py`

**Failing-test steps:**

1. Test Settings can save exact FlareSolverr endpoint text, proxy fields, Emby path mappings, templates, confidence threshold, and asset policy against a disposable backend.
2. Test Manual Organizer scans temp media, searches mocked candidates, shows confidence breakdown, previews materialized assets, and executes preview/copy modes.
3. Test Review Queue, Task Center, and History/Rollback screens use jobs/history APIs and show redacted events.
4. Test Automatic Monitors can create a rule, show destination exclusion, trigger scan-now, and display review-required items.
5. Test Actor Library can filter missing images, edit aliases, upload replacement portrait fixture bytes, and trigger Emby sync.
6. Test responsive desktop and mobile viewports do not show overlapping controls or clipped critical text.

**Red command and expected failure:**

```bash
cd frontend && npx playwright test
```

Expected failure before implementation: missing Playwright config, missing e2e specs, or incomplete UI/backend fixture server.

**Minimal implementation steps:**

- Add Playwright config with web server startup using the disposable backend fixture server.
- Seed only synthetic temporary media and sanitized fixture bytes.
- Use route mocking for external network and Emby behavior.
- Add assertions for secret redaction and API call paths.
- Keep screenshots on failure under ignored test output directories.

**Green command and expected pass:**

```bash
cd frontend && npx playwright test
```

Expected pass: UI workflows pass against disposable mocked backend state.

**Local commit command:**

```bash
git add frontend/package.json frontend/playwright.config.ts frontend/e2e/manual-organizer.spec.ts frontend/e2e/settings-and-monitor.spec.ts frontend/e2e/review-task-history.spec.ts frontend/e2e/actor-library.spec.ts tests/integration/playwright_server.py backend/app/main.py && git commit -m "Add Playwright integration tests"
```

## Task 32 - Disposable Smoke Harness and Real Smoke Safety Guards

**Depends on:** Task 31.

**Files to create/modify/test:**

- Create `scripts/disposable_smoke.py`
- Create `scripts/real_xchina_smoke.py`
- Create `tests/smoke/test_disposable_media_smoke.py`
- Create `tests/smoke/test_real_smoke_safety.py`
- Modify `.gitignore`

**Failing-test steps:**

1. Test disposable smoke canonicalizes and resolves all paths, rejects symlinks, rejects non-existent paths where existence is required, and rejects ambiguous equivalent paths.
2. Test disposable root must be under an explicitly generated temporary directory matching `/tmp/xona-smoke-*`.
3. Test disposable smoke cannot read or write outside its generated temp root and cannot touch user media roots.
4. Test real xchina smoke is opt-in through explicit environment variables, read-only, and performs no file organization against xchina results.
5. Test real smoke refuses symlinked paths, home-directory paths, broad roots such as `/`, and any path not under its generated disposable root.
6. Test default smoke commands run without network and without user media access.

**Red command and expected failure:**

```bash
python -m pytest tests/smoke/test_disposable_media_smoke.py tests/smoke/test_real_smoke_safety.py
```

Expected failure before implementation: missing smoke scripts or missing path safety guards.

**Minimal implementation steps:**

- Implement `scripts/disposable_smoke.py` to generate its own temp root, create synthetic media, run mocked scan/search/preview/copy flow, and tear down only its own temp paths.
- Implement `scripts/real_xchina_smoke.py` as read-only and opt-in using explicit env vars for FlareSolverr endpoint and test query.
- Canonicalize and resolve every path before use.
- Refuse symlink ancestors, non-existent required paths, ambiguous resolved paths, home-directory roots, root filesystem paths, and any path outside the generated temp root.
- Ensure real xchina smoke never organizes files and never reads user media.

**Green command and expected pass:**

```bash
python -m pytest tests/smoke/test_disposable_media_smoke.py tests/smoke/test_real_smoke_safety.py
python scripts/disposable_smoke.py
```

Expected pass: disposable smoke is safe and real xchina smoke is opt-in/read-only.

**Local commit command:**

```bash
git add scripts/disposable_smoke.py scripts/real_xchina_smoke.py tests/smoke/test_disposable_media_smoke.py tests/smoke/test_real_smoke_safety.py .gitignore && git commit -m "Add smoke safety harness"
```

## Task 33 - Static Analysis, Types, API Contract Audit

**Depends on:** Task 32.

**Files to create/modify/test:**

- Modify `pyproject.toml`
- Modify `frontend/package.json`
- Create `tests/backend/api/test_openapi_contract.py`
- Create `tests/frontend_api_contract/test_frontend_api_paths.py`
- Create `scripts/check_api_contract.py`
- Create `scripts/check_plan_fixture_privacy.py`

**Failing-test steps:**

1. Test ruff configuration covers backend and tests.
2. Test mypy configuration checks `backend/app` with practical strictness for first release.
3. Test frontend lint, typecheck, and build scripts exist.
4. Test OpenAPI includes every backend route expected by the frontend.
5. Test frontend source does not call non-existent `/api/*` paths.
6. Test fixture privacy checker can be run as a standalone script and includes the same banned patterns as `tests/backend/fixtures/test_fixture_privacy.py`.

**Red command and expected failure:**

```bash
python -m pytest tests/backend/api/test_openapi_contract.py tests/frontend_api_contract/test_frontend_api_paths.py
python -m ruff check backend tests
python -m mypy backend/app
cd frontend && npm run lint && npm run typecheck && npm run build
```

Expected failure before implementation: missing tooling config, missing contract checker, or unresolved lint/type/build issues.

**Minimal implementation steps:**

- Add ruff and mypy configuration to `pyproject.toml`.
- Add frontend `lint`, `typecheck`, and `build` scripts.
- Implement OpenAPI and frontend path audit scripts that compare frontend API calls with registered backend routes.
- Reuse fixture privacy rules in both pytest and standalone script form.
- Fix only issues required by lint, type, build, and API contract checks.

**Green command and expected pass:**

```bash
python -m pytest tests/backend/api/test_openapi_contract.py tests/frontend_api_contract/test_frontend_api_paths.py
python -m ruff check backend tests
python -m mypy backend/app
cd frontend && npm run lint && npm run typecheck && npm run build
```

Expected pass: lint, type, build, fixture privacy, and frontend/backend API contract checks pass.

**Local commit command:**

```bash
git add pyproject.toml frontend/package.json tests/backend/api/test_openapi_contract.py tests/frontend_api_contract/test_frontend_api_paths.py scripts/check_api_contract.py scripts/check_plan_fixture_privacy.py && git commit -m "Add quality and API contract gates"
```

## Task 34 - Final Mandatory Release Gates

**Depends on:** Task 33.

**Files to create/modify/test:**

- Create `scripts/release_gate.sh`
- Create `docs/plans/2026-07-22-xona-release-gates.md`
- Modify `README.md`

**Failing-test steps:**

1. Test release gate script fails fast when backend or integration tests fail.
2. Test release gate script runs backend lint and type checks.
3. Test release gate script runs frontend unit tests, lint, typecheck, and production build.
4. Test release gate script runs Playwright.
5. Test release gate script runs `docker compose build`, `docker compose up -d`, an in-container migration upgrade through the `app` service, healthcheck, disposable media smoke, fixture privacy test, and `docker compose down`.
6. Test `docker compose down` runs through a shell trap even when an earlier release gate command fails.
7. Test real xchina smoke remains separate, opt-in, read-only, and never uses user media.

**Red command and expected failure:**

```bash
bash scripts/release_gate.sh
```

Expected failure before implementation: missing release gate script or missing required gate command.

**Minimal implementation steps:**

- Implement `scripts/release_gate.sh` with `set -euo pipefail` and a `trap 'docker compose down' EXIT`.
- Include the required command sequence:

  ```bash
  python -m pytest tests/backend tests/integration
  python -m ruff check backend tests
  python -m mypy backend/app
  cd frontend && npm test -- --run && npm run lint && npm run typecheck && npm run build && npx playwright test
  cd ..
  docker compose build
  docker compose up -d
  docker compose exec -T app python -m backend.app.db.migrations
  python docker/healthcheck.py
  python -m pytest tests/smoke/test_disposable_media_smoke.py tests/backend/fixtures/test_fixture_privacy.py
  docker compose down
  ```

- Document that `scripts/real_xchina_smoke.py` is a separate opt-in read-only command and is not part of default release gates.
- Keep release gate outputs redacted and ensure disposable smoke creates its own temp roots.

**Green command and expected pass:**

```bash
bash scripts/release_gate.sh
```

Expected pass: backend and integration tests, backend lint/type check, frontend unit tests/lint/typecheck/build, Playwright, Docker Compose build/up, in-container migration upgrade, healthcheck, disposable media smoke, fixture privacy test, and Docker Compose down all complete.

**Local commit command:**

```bash
git add scripts/release_gate.sh docs/plans/2026-07-22-xona-release-gates.md README.md && git commit -m "Add release gate script"
```

## Dependency and API Order Audit

- Tasks are sequential and every `Depends on` entry points only to a lower-numbered task.
- Every SQLAlchemy model change is paired with an Alembic migration and an upgrade test in the same task.
- Frontend settings UI begins after settings APIs exist.
- Frontend manual organizer UI begins after manual APIs exist.
- Frontend Review Queue, Task Center, and History/Rollback UI begins after jobs/history APIs exist.
- Frontend monitor and actor library UI begins after watch-rule and actor APIs exist.
- FlareSolverr endpoint handling remains exact throughout the plan; no task appends `/v1`.
- Asset materialization occurs before immutable operation planning and execution.
- Real xchina smoke remains opt-in, read-only, and separate from default release gates.
