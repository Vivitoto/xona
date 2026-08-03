# Xona UI Redesign Implementation Plan

> **For implementer:** Use TDD where behavior or rendered structure changes. For visual-only CSS changes, add or update focused render tests when selectors, labels, or layout wrappers change; otherwise verify with build and browser inspection.

**Goal:** Rebuild Xona's UI into a compact, modern, consistent local-tool interface using neutral colors, pill selection states, tighter button sizing, cleaner layout, and less noisy copy.

**Architecture:** Keep the current React/Vite structure and API contracts. Introduce the redesign through global CSS variables and existing shared components first, then refactor each page to use the same layout primitives. Avoid backend changes unless a frontend test reveals a contract issue.

**Tech Stack:** React, TypeScript, Vite, Vitest, Testing Library, lucide-react, CSS variables.

---

## Guardrails

- Do not push, publish, upload, or trigger releases.
- Do not remove pagination, fixed-height scroll areas, or modal flows.
- Do not expand 100+ batch items into a long page.
- Do not use black-background/white-text as the default design language.
- Keep primary actions compact and limited to one per section.
- Remove unnecessary comments and verbose UI copy when touching a file.
- Preserve existing tests unless visible text or structure intentionally changes.

## Target Button System

Implement these CSS-level sizes and reuse them across pages:

| Class / Variant | Height | Padding | Use |
| --- | --- | --- | --- |
| default button | 34–36px | compact horizontal | normal actions |
| `.button-compact` | 30–32px | tighter | table/tool row actions |
| `.icon-button` | 30–32px square | none/minimal | close, refresh, back |
| `.button-row` buttons | equal height | aligned | grouped actions |
| `.primary` | 36px max | compact | one main section CTA |
| `.secondary` | 34–36px | compact | normal secondary action |
| `.ghost` | 32–34px | compact | low-priority action |

Selected and active states:

- Pill radius by default.
- Active: light fill + dark gray border.
- Hover: light gray fill + gray border.
- Focus: visible but not oversized.
- Icon size: 15–16px unless a page explicitly needs larger.

---

## Task 1: Update UI Standards Doc

**Files:**
- Modify: `docs/ui-standards.md`
- Test: none

**Steps:**
1. Replace old primary-color-filled tab/button language with the neutral pill system.
2. Add the button size table from this plan.
3. Add explicit guidance: no default black-background/white-text language; compact row buttons; one primary CTA per section.
4. Check docs diff manually.

**Verify:**
```bash
git diff -- docs/ui-standards.md
```

Expected: docs describe the new palette, button sizing, pill tabs, hover border states, and compact density.

---

## Task 2: Global CSS Variables and Base Controls

**Files:**
- Modify: `frontend/src/styles.css`

**Test first:**
Run existing frontend type/build gate to capture baseline.

```bash
cd frontend
npm run lint
npm run build
```

**Implementation:**
1. Replace blue/purple light theme variables with neutral warm gray tokens.
2. Replace dark theme tokens with neutral dark gray tokens, keeping dark mode readable.
3. Rewrite base `button`, `button.secondary`, `.link-button`, `input`, `select`, `textarea` styles:
   - compact heights,
   - pill or soft rounded shape,
   - border/gray hover,
   - no shimmer effects,
   - smaller shadows.
4. Add reusable `.button-compact`, `.icon-button`, `.ghost`, `.toolbar`, `.section-grid`, and density helpers if missing.
5. Keep focus-visible accessible.

**Verify:**
```bash
cd frontend
npm run lint
npm run build
```

Expected: typecheck/build pass; no visual-only TypeScript changes.

---

## Task 3: Shared Navigation, Tabs, Forms, Sections

**Files:**
- Modify: `frontend/src/components/AppLayout.tsx`
- Modify: `frontend/src/components/Tabs.tsx`
- Modify: `frontend/src/components/FormField.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`

**Step 1: Update tests if visible structure changes**
- Keep role/name assertions for main nav and page content.
- Add or preserve assertions for Dashboard shortcuts and safety toggle.

**Step 2: Implement**
1. Compact sidebar nav into pill buttons.
2. Reduce page header vertical weight.
3. Make theme/safety controls compact pill controls.
4. Make `Tabs` segmented/pill without API change.
5. Extend `Section` only if needed for actions/description; otherwise use CSS and existing markup.
6. Ensure `CheckboxField` and `FormField` align cleanly in grids.

**Verify:**
```bash
cd frontend
npm test -- --run src/App.test.tsx
npm run build
```

Expected: App tests and build pass.

---

## Task 4: Dashboard Redesign

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/styles.css`

**Step 1: Test**
Update Dashboard assertions to expect:
- `媒体工作台`,
- shortcut cards,
- compact workflow labels,
- no unsupported fake metrics.

**Step 2: Implement**
1. Make hero compact.
2. Use an aligned entry-card grid.
3. Use compact action buttons with 15–16px icons.
4. Keep only true data metrics.
5. Remove verbose copy.

**Verify:**
```bash
cd frontend
npm test -- --run src/App.test.tsx
npm run build
```

Expected: Dashboard renders concise shortcuts and compact actions.

---

## Task 5: Local Metadata Page Restructure

**Files:**
- Modify: `frontend/src/pages/UnmatchedVideosPage.tsx`
- Modify: `frontend/src/pages/UnmatchedVideosPage.test.tsx`
- Modify: `frontend/src/styles.css`

**Step 1: Tests**
Update tests around:
- single/batch tabs,
- batch cover settings,
- similar-frame fallback controls,
- batch submit flow,
- compact warnings.

Do not weaken business assertions.

**Step 2: Implement single workflow**
1. Group source/frame controls together.
2. Group cover controls and preview separately.
3. Group metadata/NFO controls separately.
4. Group plan/execute output separately.
5. Convert low-frequency controls to compact grids or details blocks.
6. Make frame/cover preview grids bounded and compact.

**Step 3: Implement batch workflow**
1. Keep scan/rules/task/results as clear blocks.
2. Keep batch results capped by `BATCH_TABLE_VISIBLE_LIMIT` or scroll.
3. Use compact row actions.
4. Keep per-item details collapsed by default.
5. Shorten verbose helper text.

**Verify:**
```bash
cd frontend
npm test -- --run src/pages/UnmatchedVideosPage.test.tsx
npm run build
```

Expected: tests pass; page stays usable for large batches without long expansion.

---

## Task 6: XChina Search Page

**Files:**
- Modify: `frontend/src/pages/XChinaSearchPage.tsx`
- Modify: `frontend/src/pages/XChinaSearchPage.test.tsx`
- Modify: `frontend/src/components/CandidateCard.tsx`
- Modify: `frontend/src/styles.css`

**Test:**
Preserve search, result selection, and safety-mode expectations.

**Implementation:**
1. Separate search controls, results, and detail preview.
2. Make candidate cards denser.
3. Use compact buttons for result actions.
4. Keep image safety behavior.
5. Remove redundant helper copy.

**Verify:**
```bash
cd frontend
npm test -- --run src/pages/XChinaSearchPage.test.tsx
npm run build
```

---

## Task 7: Tasks, Review, History, Logs

**Files:**
- Modify: `frontend/src/pages/TaskCenterPage.tsx`
- Modify: `frontend/src/pages/ReviewQueuePage.tsx`
- Modify: `frontend/src/pages/HistoryRollbackPage.tsx`
- Modify: `frontend/src/pages/LogsPage.tsx`
- Modify: related `*.test.tsx`
- Modify: `frontend/src/components/OperationPlanView.tsx`
- Modify: `frontend/src/components/ProgressLog.tsx`
- Modify: `frontend/src/styles.css`

**Test:**
Run each related page test after updating expected labels/classes only where needed.

**Implementation:**
1. Use compact metric/status rows.
2. Keep tables inside `.table-wrap`.
3. Keep timelines/logs in fixed-height scroll areas.
4. Convert row actions to compact buttons.
5. Keep danger actions visually distinct but not oversized.
6. Keep payloads/details readable and bounded.

**Verify:**
```bash
cd frontend
npm test -- --run \
  src/pages/TaskCenterPage.test.tsx \
  src/pages/ReviewQueuePage.test.tsx \
  src/pages/HistoryRollbackPage.test.tsx \
  src/pages/LogsPage.test.tsx
npm run build
```

---

## Task 8: Actor Library and Dialogs

**Files:**
- Modify: `frontend/src/pages/ActorLibraryPage.tsx`
- Modify: `frontend/src/pages/ActorLibraryPage.test.tsx`
- Modify: `frontend/src/components/ActorMergeDialog.tsx`
- Modify: `frontend/src/components/ActorPortrait.tsx`
- Modify: `frontend/src/components/DirectoryPicker.tsx`
- Modify: `frontend/src/styles.css`

**Implementation:**
1. Compact actor filters and toolbar.
2. Align actor cards/list rows.
3. Apply new dialog surface and icon-button close style.
4. Keep image safety mode intact.
5. Keep dialog content scrollable under viewport height.

**Verify:**
```bash
cd frontend
npm test -- --run src/pages/ActorLibraryPage.test.tsx
npm run build
```

---

## Task 9: Settings Pages

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/pages/SettingsPage.test.tsx`
- Modify: `frontend/src/pages/settings/*.tsx`
- Modify: `frontend/src/components/TemplateGuide.tsx`
- Modify: `frontend/src/components/WatchRuleEditor.tsx`
- Modify: `frontend/src/styles.css`

**Test:**
Preserve settings load/save behavior and required field labels.

**Implementation:**
1. Make settings tabs pill/segmented.
2. Use compact grid groups.
3. Keep directory fields using `DirectoryPicker`.
4. Keep sensitive placeholders masked.
5. Trim verbose descriptions while preserving necessary format examples.
6. Keep watch-rule editor controls aligned and compact.

**Verify:**
```bash
cd frontend
npm test -- --run src/pages/SettingsPage.test.tsx
npm run build
```

---

## Task 10: Copy and Comment Cleanup

**Files:**
- Modify touched `frontend/src/**/*.tsx`
- Modify touched `frontend/src/styles.css`

**Implementation:**
1. Search touched files for stale comments and verbose helper text.
2. Remove comments that only restate obvious code.
3. Keep comments for non-obvious edge cases.
4. Shorten user-facing descriptions without removing useful examples.

**Verify:**
```bash
cd frontend
npm run lint
npm run build
```

Expected: no TypeScript issues; UI copy remains clear but shorter.

---

## Task 11: Final Frontend Gate

**Files:**
- No direct edits unless failures require fixes.

**Commands:**
```bash
cd frontend
npm run lint
npm test -- --run
npm run build
```

Expected: all frontend tests, lint, and build pass.

If unrelated existing failures appear, isolate them by rerunning the impacted page tests and document the blocker.

---

## Task 12: Visual Inspection

**Preferred:** use browser automation or local screenshot inspection after the app can run.

**Commands:**
```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

Inspect at least:

- Dashboard
- Local metadata single tab
- Local metadata batch tab
- XChina search
- Settings
- Logs

Check:

- Buttons are compact and aligned.
- Active nav/tab states use pill + border + gray fill.
- Hover states show gray fill/border.
- Long lists are bounded.
- Dialogs fit viewport and scroll internally.
- No obvious black-background/white-text default styling.

---

## Execution Notes

- This plan touches many frontend files. Prefer phase commits after each verified task if the working tree is clean.
- Current repository may already contain unrelated local changes. Do not mix commits unless explicitly approved.
- If using Codex, constrain it to `/home/vito/.openclaw/workspace/Docker/xona`, no push, no publish, no uploads, no unrelated deletes.
