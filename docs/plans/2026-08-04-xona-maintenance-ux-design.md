# Xona Maintenance UX Design

**Date:** 2026-08-04

## Goal

Optimize Xona after the v1.2.6 UI release in three areas without changing the main product flow:

1. Split the large local metadata page into maintainable frontend components.
2. Improve large-batch organization UX for 100+ files.
3. Add safe cache visibility and cleanup controls.

Also clarify the organize-record status currently shown as `目标被外部修改`: this is a completed record whose target no longer matches rollback verification, not an incomplete organize operation.

## Scope

### In scope

- Local-only code changes and tests.
- Refactor `UnmatchedVideosPage.tsx` into component modules while keeping route/API behavior stable.
- Batch list/status/filter/summary UX improvements.
- Backend API for cache stats and safe cleanup under `/config`-owned Xona cache directories.
- Frontend settings/maintenance UI for cache stats and cleanup.
- Task/organize record wording that distinguishes completion from rollback safety.

### Out of scope

- GitHub push, tag, Docker release, R2 upload, or external publish.
- Replacing local metadata API contracts.
- Reworking information architecture or route names.
- Deleting media files or organized output files.
- Destructive cache cleanup outside known Xona cache roots.

## External-target-modified semantics

Current backend recovery logic marks a plan `externally_modified` when the target exists but does not match the operation journal's rollback verification expectations. In the organize-record API this status currently overrides display status, which can look like incomplete work even though files were organized.

New UX semantics:

- Operation status remains completed when the row/job completed.
- Verification label explains rollback safety: `目标后续变更` / `不可安全回滚`.
- Rollback button remains disabled unless verification is clean.
- Filters can still expose modified records for audit.

## Architecture

### Frontend component split

Keep `UnmatchedVideosPage` as the route-level container and move presentational/section-level pieces into `frontend/src/pages/local-metadata/`.

Initial extraction should prioritize low-risk components with explicit props:

- `BatchRunSummary` — selected/count/status/risk summary.
- `BatchOutputFilters` — compact filters for output state groups.
- `BatchOutputList` — bounded list rendering and item status presentation.
- `CacheMaintenanceSettings` — cache stats and cleanup UI under settings.
- Optional single-workflow section components if low risk; otherwise leave complex state handlers in the container.

Avoid a massive state-management rewrite in this iteration.

### Batch UX

Add a lightweight display filter for batch output items:

- `all`
- `needs_attention` (failed / execute_failed / cancelled)
- `ready` (succeeded with executable plan)
- `running`
- `done`

Add a compact batch summary before execution:

- selected videos
- generated drafts / output items
- ready to execute
- failed / cancelled
- destructive mode warning for move / in-place

Keep `BATCH_TABLE_VISIBLE_LIMIT`, bounded scroll regions, and collapsed details.

### Cache management

Add a backend service that only scans and removes known safe cache roots:

- local metadata cache: `<config>/cache/local_metadata`
- asset cache: `<config>/asset-cache`
- actor cache: `<config>/actor-cache`
- XChina HTTP cache directory only if configured under a safe config-owned path; otherwise report it but do not delete without stronger validation.

API shape:

- `GET /api/settings/cache-maintenance`
- `POST /api/settings/cache-maintenance/cleanup`

Response includes per-cache file count, byte count, path, and cleanup warnings. Cleanup accepts explicit cache keys and returns removed file/byte counts.

Safety constraints:

- Never delete media roots.
- Never delete operation output directories.
- Resolve paths and require them to be equal to or under the configured Xona config directory for this iteration.
- Missing directories are not errors.

### Testing

Backend:

- Cache stats report sizes for fake config cache trees.
- Cleanup removes only requested safe cache dirs.
- Cleanup refuses unsafe paths outside config dir.
- Existing local metadata/history/organize tests remain green.

Frontend:

- Local metadata tests cover batch filtering/summary labels.
- Settings tests cover cache maintenance rendering and cleanup call.
- Task center tests cover clarified external-modified wording and disabled rollback.

## Release strategy

After implementation, run local verification only and commit locally. If Vito later confirms release, bump to `1.2.7`, push through GitHub API, tag, and verify Docker images using the established release checklist.
