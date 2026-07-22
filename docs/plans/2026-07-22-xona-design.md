# Xona Design

**Date:** 2026-07-22

## 1. Purpose

Build a local-first Docker web application that scans mounted media directories, searches and scrapes metadata from xchina.co through a configurable FlareSolverr endpoint and optional proxy, calculates candidate confidence, supports manual review and automatic directory monitoring, organizes media safely, writes Emby-compatible metadata and images, maintains actor portraits, and optionally notifies Emby through its API.

The application is a metadata organizer. It does not download source media.

## 2. Product Decisions

- Implement a dedicated application rather than extending MDC-NG or Movie Data Capture.
- Optimize first for Emby while keeping Kodi/Jellyfin-compatible NFO and image naming.
- Support manual organization and automatic watched-directory organization.
- Support preview, in-place, move, copy, hard-link, and symbolic-link modes.
- Permit source and destination directories to be any selectable subdirectories under one or more Docker-mounted roots; separate source/output mounts are not required.
- Make FlareSolverr endpoint and proxy fully configurable.
- Treat the FlareSolverr URL as an exact endpoint. Do not append `/v1`; the user supplies the complete URL.
- Provide a configurable auto-execution confidence threshold, defaulting to 92.
- Auto-execute only when the top candidate reaches the threshold, leads the second candidate by at least 10 points, has complete required metadata, and produces no file conflict.
- Support local metadata-only operation and optional Emby API integration.
- Store state in SQLite under `/config` and retain operation journals for retry and rollback.

## 3. Chosen Architecture

### 3.1 Technology stack

- Backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic
- Frontend: React, TypeScript, Vite
- Database: SQLite in WAL mode
- Background work: persistent SQLite-backed task runner owned by the backend process
- File monitoring: watchdog/inotify with polling fallback
- HTML parsing: selectolax or BeautifulSoup/lxml behind a source adapter
- Similarity scoring: RapidFuzz plus deterministic token and identifier features
- HTTP: httpx
- Testing: pytest, pytest-asyncio, respx, Vitest, React Testing Library
- Packaging: multi-stage Docker build and Docker Compose

The first release stays single-container for the application. FlareSolverr is external and configured by URL. The task runner is durable and single-worker by default to avoid stressing xchina or corrupting file operations.

### 3.2 Runtime layout

```text
Browser
  -> Xona Web UI
      -> FastAPI API
          -> scanner / monitor
          -> matcher
          -> xchina source adapter
          -> metadata normalizer
          -> organizer / operation journal
          -> actor library
          -> Emby connector
          -> SQLite

Mounted paths:
  /config              application state
  /a, /storage/*, ...  user-defined media roots
```

The UI folder picker may browse only configured mounted roots. It must reject traversal, symlink escape, and paths outside those roots.

## 4. Main Components

### 4.1 Storage-root and path service

- Discover or configure allowed container-side mount roots.
- Present a safe directory browser in the UI.
- Allow each job to choose source and destination directories independently.
- Allow source and destination to be identical for in-place mode.
- Detect when the destination is inside a watched source and automatically exclude it from monitoring to prevent loops.
- Validate read/write capability before saving a rule.

### 4.2 Media scanner

- Recursively or non-recursively scan supported video extensions.
- Group video files with subtitles, existing NFO files, images, and multipart suffixes.
- Ignore temporary extensions and configurable patterns.
- Record size, mtime, inode/device where available, and a stable media identity.
- Avoid re-enqueuing unchanged files.

### 4.3 Manual organization

The manual page supports:

- selecting and scanning a directory;
- pasting a local filename into search;
- editing the normalized search query;
- searching one file or a batch;
- viewing candidate cards with image, title, actors, studio/series, date, URL, and confidence explanation;
- selecting a candidate explicitly;
- opening an xchina detail URL directly;
- previewing the complete file operation and metadata plan;
- executing one or more approved plans.

An explicit manual candidate selection bypasses the automatic confidence threshold but still performs file conflict and safety checks.

### 4.4 Automatic monitoring

Each monitor rule stores:

- source directory;
- destination directory;
- recursive flag;
- real-time or polling mode;
- polling interval;
- stability duration and number of stable checks;
- organization mode;
- folder and filename templates;
- metadata/image selection;
- confidence threshold;
- strict or lenient asset policy;
- Emby notification options;
- include/exclude patterns.

A discovered file enters `waiting_stable`. Processing starts only after its size and mtime remain stable, its minimum age is met, and temporary download markers are absent.

### 4.5 XChina source adapter

The source interface exposes:

- connection test;
- search by keyword and media type;
- fetch video detail;
- fetch actor/model detail;
- fetch image and asset bytes with policy checks.

The xchina implementation:

- sends requests through the exact configured FlareSolverr endpoint;
- passes an optional configured HTTP/SOCKS proxy to FlareSolverr where supported;
- persists session cookies and user-agent data with expiry;
- rate-limits requests and defaults to one in-flight site operation;
- caches search and detail responses;
- detects Cloudflare block pages, expired sessions, placeholder images, and malformed details;
- rebuilds the FlareSolverr session on eligible failures;
- surfaces actionable diagnostics rather than silently returning no results.

The observed xchina search routes include `/videos/keyword-<encoded>.html`; parsing remains isolated in the adapter so site changes do not affect the organizer core.

### 4.6 Matching and confidence

Before scoring, normalize Unicode, punctuation, separators, whitespace, quality/source tags, site prefixes, common release suffixes, and multipart markers while retaining the original name.

A candidate score from 0 to 100 combines:

- exact or normalized work identifier match;
- fuzzy title similarity;
- title token coverage;
- studio/series token match;
- actor name match;
- date/year match;
- parent-directory hints;
- previously confirmed local aliases.

The response includes a score breakdown. Automatic execution requires:

1. top score >= configured threshold;
2. top score - second score >= 10;
3. unique, complete selected detail;
4. no destination collision or unresolved multipart ambiguity;
5. required metadata/assets satisfy the selected strictness policy.

Otherwise the task becomes `review_required`.

### 4.7 Metadata and image writer

Produce Emby/Kodi-compatible movie NFO with available fields:

- title and original title;
- sort title;
- plot/outline;
- release/premiere date;
- runtime;
- studio, series, director;
- actors with name, role, profile URL, and portrait reference;
- genres and tags;
- xchina unique ID and source URL.

Selectable assets:

- movie NFO;
- `poster.jpg`;
- `fanart.jpg` and numbered backdrops;
- `thumb.jpg`;
- `clearlogo.png` when available;
- `extrafanart/`;
- trailer when the source provides one;
- `.actors/` portraits;
- normalized metadata JSON;
- optional source-page snapshot for diagnostics.

Strict mode fails before file organization if a required selected asset cannot be obtained. Lenient mode records missing assets and continues.

### 4.8 Naming templates

Folder and media filenames have separate templates. Initial variables:

- `{number}`
- `{title}`
- `{original_title}`
- `{studio}`
- `{series}`
- `{year}`
- `{release_date}`
- `{actors}`
- `{first_actor}`
- `{source_filename}`
- `{xchina_id}`

The template engine must sanitize path separators, control characters, reserved names, traversal, empty values, and excessive component length. The UI shows a live preview and validation errors.

### 4.9 File organizer and journal

Modes:

- preview only;
- in-place rename and metadata write;
- move;
- copy;
- hard link;
- symbolic link.

Every execution begins with an immutable plan containing source paths, target paths, operation type, expected size, associated sidecars, conflicts, and generated artifacts.

Safety requirements:

- never silently overwrite;
- use atomic rename on the same filesystem;
- for cross-filesystem move: copy to temporary target, verify size, atomically finalize, then remove source;
- keep videos, subtitles, multipart segments, and sidecars grouped;
- write generated metadata through temporary files and atomic replacement;
- record each completed operation before proceeding;
- on restart, reconcile interrupted operations instead of blindly retrying destructive steps;
- allow rollback only after verifying the target has not been externally modified.

### 4.10 Actor library

Store actors in a global cache under `/config/actor-cache` and in SQLite with:

- canonical name;
- aliases;
- xchina actor/model ID and URL;
- portrait source URL and local portrait path;
- biography and available profile fields;
- associated works;
- last refresh timestamp;
- optional Emby Person ID.

Per-movie `.actors/<safe-name>.jpg` output may copy, hard-link, or symlink to the global cache according to configuration. The actor UI supports missing-image filtering, alias editing, merge, image replacement, refresh, linked works, and Emby synchronization.

The first release uses xchina plus existing local/Emby data. Additional actor sources remain a later adapter extension.

### 4.11 Emby connector

Optional settings:

- server URL;
- API key;
- optional user ID;
- selected library IDs;
- scan after organization;
- refresh matched media;
- update missing actor portraits;
- protect local NFO from online replacement.

Connection test reports server version, accessible libraries, authorization, and path visibility assumptions.

Post-organization flow:

1. request library scan;
2. locate the item by path and local metadata;
3. refresh the item while preferring local metadata;
4. locate linked people;
5. upload cached portraits for missing actor images when enabled;
6. persist Emby item/person associations.

Emby failure does not roll back correct local file work. Such a task becomes `local_complete_emby_failed` and the Emby phase can be retried independently.

### 4.12 Authentication and secrets

- Optional local web authentication with username/password.
- Generate an application secret under `/config` on first start.
- Store password hashes, never plaintext passwords.
- Keep Emby keys and sensitive configuration out of logs and UI responses after save.
- Use CSRF-safe same-origin API behavior and secure cookies when authentication is enabled.

## 5. Data Model

Initial tables:

- `settings`
- `storage_roots`
- `watch_rules`
- `media_items`
- `media_sidecars`
- `search_queries`
- `search_candidates`
- `metadata_records`
- `actors`
- `actor_aliases`
- `actor_media_links`
- `jobs`
- `job_events`
- `operation_plans`
- `operation_steps`
- `emby_links`
- `http_cache`

Important job states:

- `discovered`
- `waiting_stable`
- `searching`
- `review_required`
- `matched`
- `scraping`
- `planning`
- `ready`
- `executing`
- `notifying_emby`
- `completed`
- `local_complete_emby_failed`
- `failed`
- `cancelled`
- `rolled_back`

State transitions are validated and journaled.

## 6. Web UI

Pages:

1. Dashboard
2. Manual Organizer
3. Automatic Monitors
4. Review Queue
5. Task Center
6. Actor Library
7. History and Rollback
8. Settings
   - storage roots
   - xchina
   - exact FlareSolverr endpoint
   - proxy
   - Emby
   - naming templates
   - metadata/assets
   - confidence and safety
   - authentication

Connection-test screens show HTTP status, elapsed time, Cloudflare state, cookie count, and sanitized errors.

## 7. Error Handling and Recovery

- SQLite WAL and explicit transactions for state changes.
- Idempotent job stages.
- Bounded retry with exponential backoff for network requests.
- Site rate limiting and response cache.
- Cloudflare-specific diagnostics and session refresh.
- Placeholder/broken asset filtering.
- Interrupted file operations enter reconciliation before retry.
- User-visible logs omit API keys, cookies, and proxy credentials.
- Failed tasks retain metadata and plan context for correction and retry.

## 8. Docker Deployment

The repository provides `Dockerfile`, `docker-compose.yml`, and `.env.example`.

Example:

```yaml
services:
  app:
    build: .
    ports:
      - "8732:8732"
    environment:
      PUID: "1000"
      PGID: "1000"
      STORAGE_ROOTS: "/a"
    volumes:
      - ./config:/config
      - /host/media:/a
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
```

FlareSolverr and proxy values are configured in the Web UI and are not hard-coded. The FlareSolverr value is stored and called exactly as entered.

## 9. First Release Scope

Included:

- safe mounted-root browser;
- manual filename search and candidate selection;
- directory scan and batch review;
- automatic monitoring with stability checks;
- confidence scoring and guarded automatic execution;
- preview/in-place/move/copy/hard-link/symlink modes;
- xchina search/detail/actor scraping through configurable FlareSolverr and proxy;
- Emby-compatible NFO and selectable images;
- actor portrait cache and `.actors` output;
- optional Emby scan, refresh, and missing portrait synchronization;
- durable jobs, retries, logs, operation journal, and rollback;
- Docker Compose deployment.

Deferred:

- AI face cropping;
- watermarks;
- automatic translation;
- many additional metadata sources;
- native mobile apps.

## 10. Testing and Acceptance

Automated tests cover:

- filename normalization and score breakdown;
- auto-execution threshold and 10-point lead rule;
- mounted-root traversal and symlink escape prevention;
- xchina search/detail/actor fixture parsing;
- Cloudflare and FlareSolverr error handling;
- NFO schema and image naming;
- actor cache and `.actors` behavior;
- all organization modes in temporary filesystems;
- same-filesystem and simulated cross-filesystem move behavior;
- collision prevention and interrupted-operation reconciliation;
- output-inside-watch-loop prevention;
- monitor stability detection;
- Emby API mocks and independent retry;
- API and frontend interaction tests.

Release verification:

- backend tests pass;
- frontend tests and production build pass;
- Docker image builds;
- Compose service becomes healthy;
- mounted path browser works against a disposable fixture directory;
- real xchina smoke test succeeds using the configured FlareSolverr/proxy without touching user media;
- a disposable sample file completes preview and one safe organization mode end-to-end.
