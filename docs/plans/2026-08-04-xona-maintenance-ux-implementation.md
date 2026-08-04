# Xona Maintenance UX Implementation Plan

**Date:** 2026-08-04

## Constraints

- Do not push, tag, publish, or upload.
- Preserve existing local metadata APIs and route names unless explicitly adding cache-maintenance endpoints.
- Keep batch pages bounded for 100+ files.
- Cache cleanup must only remove known Xona cache directories under the config directory.
- Use tests before/with implementation for behavior changes.

## Task 1 — Clarify organize-record verification wording

Files:
- `frontend/src/pages/TaskCenterPage.tsx`
- `frontend/src/pages/TaskCenterPage.test.tsx`
- Optionally `frontend/src/pages/HistoryRollbackPage.tsx` / tests if same confusing label appears there.

Steps:
1. Update tests so `externally_modified` records are presented as completed records with a rollback-safety warning, not as incomplete organization.
2. Change label copy from `目标被外部修改` to `已完成，目标后续变更` or equivalent.
3. Keep rollback disabled and warning tone.
4. Keep modified filter behavior.

Verify:
```bash
cd frontend && npm test -- --run src/pages/TaskCenterPage.test.tsx src/pages/HistoryRollbackPage.test.tsx
```

## Task 2 — Batch UX component extraction and filters

Files:
- `frontend/src/pages/UnmatchedVideosPage.tsx`
- New files under `frontend/src/pages/local-metadata/`
- `frontend/src/pages/UnmatchedVideosPage.test.tsx`
- `frontend/src/styles.css` if needed.

Steps:
1. Extract low-risk batch summary/filter/list components from the page.
2. Add batch output display filters: all, needs attention, ready, running, done.
3. Add compact execution summary with selected count, ready count, failed count, and destructive-mode warning.
4. Keep current batch table/list visible limit and collapsed details.
5. Do not move complex mutation/business logic out of the route unless it remains straightforward.

Verify:
```bash
cd frontend && npm test -- --run src/pages/UnmatchedVideosPage.test.tsx
cd frontend && npm run build
```

## Task 3 — Cache maintenance backend

Files:
- New: `backend/app/services/cache_maintenance.py`
- Modify: `backend/app/schemas/settings.py`
- Modify: `backend/app/api/settings.py`
- Tests: new or existing settings API tests.

Steps:
1. Add schemas for cache area stats and cleanup requests/responses.
2. Implement a service that scans only safe config-owned cache roots:
   - `cache/local_metadata`
   - `asset-cache`
   - `actor-cache`
   - configured XChina cache dir only when inside config dir.
3. Expose:
   - `GET /api/settings/cache-maintenance`
   - `POST /api/settings/cache-maintenance/cleanup`
4. Cleanup requires explicit area keys; missing dirs are warnings/zero removals, not errors.
5. Refuse unsafe paths outside config dir.

Verify:
```bash
python3 -m pytest tests/backend/api/test_settings_api.py tests/backend/services/test_cache_maintenance.py
```

## Task 4 — Cache maintenance frontend

Files:
- New: `frontend/src/pages/settings/CacheMaintenanceSettings.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/SettingsPage.test.tsx`

Steps:
1. Add a settings section/tab for cache maintenance.
2. Load stats on demand or when section opens.
3. Render file count, size, path, and warnings per cache area.
4. Provide cleanup buttons for safe areas with confirmation.
5. Show cleanup result feedback.

Verify:
```bash
cd frontend && npm test -- --run src/pages/SettingsPage.test.tsx
cd frontend && npm run lint && npm run build
```

## Task 5 — Full verification and local commit

Run:
```bash
python3 -m pytest tests/backend/services/test_cache_maintenance.py tests/backend/api/test_settings_api.py tests/backend/api/test_organize_records_api.py tests/backend/api/test_history_api.py
cd frontend && npm run lint && npm run build && npm test -- --run
cd .. && git diff --check && git status --short
```

Then create a local commit only. Do not push or tag.
