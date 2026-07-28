# Xona Local Metadata v1 Design

## Goal

Reposition Xona around two focused workflows:

1. XChina search/link discovery for external scrapers.
2. Local metadata generation and organization for videos that external scrapers cannot match.

This v1 implementation focuses on workflow 2 while preserving existing XChina/manual organization code.

## Product Positioning

Xona should organize files only when it has a usable metadata package. For unmatched videos, Xona can create that package locally:

- title from cleaned filename
- technical metadata from ffprobe
- screenshots from ffmpeg
- poster/fanart generated from screenshots
- movie NFO generated from local metadata
- existing operation preview/execution stack reused for final organization

XChina search becomes a separate utility workflow and should no longer be the only path into organization.

## v1 Scope

### Included

- New UI page: **Unmatched Videos**.
- Single-video local metadata workflow:
  - choose/enter a video path under configured storage roots
  - analyze file with ffprobe when available
  - generate frame candidates using ffmpeg
  - default title = cleaned filename stem
  - edit title in UI
  - select cover template
  - generate poster preview and fanart preview
  - generate NFO preview
  - generate organization preview using existing template/operation planning
- Minimal batch workflow:
  - scan/list videos from a directory using existing scanner/manual scan where possible
  - select multiple videos
  - apply batch metadata edits to draft fields: title prefix/suffix, studio, series, tags, plot
  - batch-generate local metadata drafts and send them to review-like list/status in-page
- Cover templates v1:
  - `simple_poster`: single image + bottom title
  - `jav_classic_left_strip`: left small frames + right large frame + title band
  - `tangxin_vlog`: full image, gradient overlay, rounded/heavy title with stroke/glow-like shadow
- Poster text defaults to title only. Video technical info belongs in NFO, not poster.
- Conservative write policy:
  - no overwrite by default
  - organization still goes through preview/approval flow

### Excluded from v1

- Full visual template editor.
- Face/object-aware crop.
- AI/VLM metadata inference.
- Full persistent review queue schema migration for local metadata packages.
- XChina search UI split; planned for later.
- Publishing/release.

## UI Design

### Navigation

Add primary nav item:

- `Unmatched Videos` / `未匹配视频`

Keep existing manual organizer as-is for now.

### Unmatched Videos Page

Sections:

1. Source input
   - video path input
   - directory path input for scan
   - analyze/generate buttons

2. Single draft editor
   - file info: path, size, duration, resolution
   - title input, default from filename clean
   - plot input, default local-generated message
   - tags input, default `local-generated, unmatched`
   - cover template selector
   - frame candidates
   - poster/fanart previews
   - NFO preview

3. Batch panel
   - scan directory
   - selectable videos table
   - batch metadata edit controls
   - generate drafts
   - draft status table/cards

4. Organization preview
   - destination root
   - mode: preview/copy/move/hardlink/symlink
   - folder/file template fields reused or simplified
   - generate plan with generated NFO/poster/fanart artifacts

## Backend Design

### New module: local_metadata

Suggested files:

- `backend/app/schemas/local_metadata.py`
- `backend/app/services/video_probe.py`
- `backend/app/services/cover_templates.py`
- `backend/app/services/local_metadata.py`
- `backend/app/api/local_metadata.py`

### API endpoints

- `POST /api/local-metadata/analyze`
  - input: video_path
  - output: technical info, cleaned title, warnings

- `POST /api/local-metadata/frames`
  - input: video_path, time_points or percentages
  - output: generated frame cache references/URLs

- `POST /api/local-metadata/cover-preview`
  - input: video_path, title, template, selected frames
  - output: poster/fanart cache references/URLs

- `POST /api/local-metadata/nfo-preview`
  - input: local metadata fields
  - output: XML text

- `POST /api/local-metadata/preview-plan`
  - input: video item, metadata, selected/generated poster/fanart, destination root, mode, template
  - output: existing OperationPlan preview

### Data model

No DB migration in v1 unless necessary. Use request/response draft models and cache generated frames/previews under config/cache/local_metadata.

A future v2 can persist `MetadataPackageDraft` rows for review queue integration.

## Cover Template Principles

- Poster text defaults to title only.
- Fanart should default to clean screenshot or blurred/dimmed background with no large text.
- Title must support:
  - auto-fit
  - max lines
  - stroke/outline
  - shadow
  - template-specific font style
- First implementation can use Pillow. Docker image should install `ffmpeg`; Python dependency should add `Pillow`.

## Implementation Plan

1. Add dependencies and Docker runtime support: Pillow + ffmpeg.
2. Add local metadata schemas/services/API.
3. Extend NFO rendering to support local-generated records without XChina ID.
4. Add frontend API client types/functions.
5. Add Unmatched Videos page and nav.
6. Add tests:
   - filename title cleaning
   - NFO local-generated unique ID handling
   - cover template generation smoke using synthetic images or mocked frames
   - API path contract if practical
7. Run gates:
   - `PYTHONPATH=. pytest -q`
   - `ruff check .`
   - `mypy backend/app`
   - frontend lint/test/build
   - Docker build and local `/healthz`

## Safety / Release

This work remains local until Vito confirms a release checklist. Do not push, tag, publish Docker images, or upload artifacts without explicit confirmation.
