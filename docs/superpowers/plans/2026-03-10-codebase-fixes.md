# Codebase Fixes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all issues identified in the comprehensive codebase analysis — security, data integrity, deprecated patterns, and code quality.

**Architecture:** Independent fixes across frontend and backend. Each task modifies 1-3 files max and can be tested independently. Tasks are grouped by dependency — groups can run in parallel, tasks within a group are sequential.

**Tech Stack:** React 19, Zustand 5, TanStack Query v5, Dexie 4, Zod 4, FastAPI, Pydantic v2, SQLAlchemy 2, TypeScript 5.9

**Items already done (confirmed during analysis — skip):**
- FastAPI `lifespan` — already uses `lifespan` context manager, no `on_event()` anywhere
- Dexie `syncStatus` index — already exists since schema version 1
- `python-jose` / `passlib` — dead dependencies (not imported anywhere), removal is Task 2

---

## Chunk 1: Critical Fixes (Must Fix)

### Task 1: Surface nonwear export failures to user

**Files:**
- Modify: `frontend/src/pages/export.tsx:152-163`

- [ ] **Step 1: Update export mutation to track nonwear failure**

In `export.tsx`, the export mutation silently swallows nonwear export failures. Change the mutation to warn the user when nonwear export fails but sleep succeeds.

```typescript
// In exportMutation mutationFn (around line 153)
const exportMutation = useMutation({
  mutationFn: async (request: ExportRequest) => {
    const [sleepOk, nonwearOk] = await Promise.all([
      downloadFromEndpoint("/export/csv/download", request),
      downloadFromEndpoint("/export/csv/download/nonwear", request).catch(() => false),
    ]);
    if (!sleepOk) throw new Error("Export failed");
    return { success: true, nonwearOk };
  },
  onSuccess: (data) => {
    if (!data.nonwearOk) {
      alert({ title: "Partial Export", description: "Sleep data exported successfully, but nonwear markers could not be exported. There may be no nonwear data for the selected files." });
    }
  },
  onError: (error: Error) => {
    alert({ title: "Export Failed", description: error.message });
  },
});
```

- [ ] **Step 2: Verify typecheck passes**

Run: `cd /opt/sleep-scoring-web/frontend && npx tsc --noEmit`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/export.tsx
git commit -m "fix(export): surface nonwear export failures to user instead of silent skip"
```

---

### Task 2: Remove dead dependencies (python-jose, passlib)

**Files:**
- Modify: `pyproject.toml:56-57`

- [ ] **Step 1: Remove unused dependencies from pyproject.toml**

Remove these two lines from the `[project.optional-dependencies] web` section:
```
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
```

These packages are NOT imported anywhere in the codebase. The auth system uses `secrets.compare_digest()` directly.

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore: remove unused python-jose and passlib dependencies"
```

---

### Task 3: Add marker timestamp validation in Pydantic schemas

**Files:**
- Modify: `sleep_scoring_web/schemas/models.py:28-79`

- [ ] **Step 1: Add field validators to SleepPeriod and ManualNonwearPeriod**

Add timestamp range validation to prevent invalid values (negative timestamps, far-future dates). Unix timestamp range: 0 to 4102444800 (year 2100).

```python
# In SleepPeriod class, after the existing fields:
@field_validator("onset_timestamp", "offset_timestamp")
@classmethod
def _validate_timestamp(cls, v: float | None) -> float | None:
    if v is not None and (v < 0 or v > 4_102_444_800):
        msg = f"Timestamp {v} out of valid range (0 to year 2100)"
        raise ValueError(msg)
    return v

# In ManualNonwearPeriod class, after the existing fields:
@field_validator("start_timestamp", "end_timestamp")
@classmethod
def _validate_timestamp(cls, v: float | None) -> float | None:
    if v is not None and (v < 0 or v > 4_102_444_800):
        msg = f"Timestamp {v} out of valid range (0 to year 2100)"
        raise ValueError(msg)
    return v
```

- [ ] **Step 2: Verify backend typecheck passes**

Run: `cd /opt/sleep-scoring-web && ruff check sleep_scoring_web/schemas/models.py`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add sleep_scoring_web/schemas/models.py
git commit -m "fix(schemas): add timestamp range validation to SleepPeriod and ManualNonwearPeriod"
```

---

### Task 4: Add row-level locking to annotation patch functions

**Files:**
- Modify: `sleep_scoring_web/api/markers.py:2366-2472`

The `_patch_sleep_annotation()` and `_patch_nonwear_annotation()` functions do read-then-update without row locking, which could cause lost updates if two background tasks modify the same annotation concurrently.

- [ ] **Step 1: Add `with_for_update()` to SELECT queries in both patch functions**

In `_patch_sleep_annotation()` (line ~2367):
```python
# Change:
existing = await db.execute(
    select(UserAnnotation).where(...)
)
# To:
existing = await db.execute(
    select(UserAnnotation).where(...).with_for_update()
)
```

Same change in `_patch_nonwear_annotation()` (line ~2428):
```python
existing = await db.execute(
    select(UserAnnotation).where(...).with_for_update()
)
```

- [ ] **Step 2: Verify backend lint passes**

Run: `cd /opt/sleep-scoring-web && ruff check sleep_scoring_web/api/markers.py`

- [ ] **Step 3: Commit**

```bash
git add sleep_scoring_web/api/markers.py
git commit -m "fix(markers): add row-level locking to annotation patch functions to prevent lost updates"
```

---

### Task 5: Fix sync engine race condition

**Files:**
- Modify: `frontend/src/services/sync.ts:88-169`

The `pullMarkers()` function checks `syncStatus` then later saves, but another tab/operation could modify the marker between check and save.

- [ ] **Step 1: Wrap the check-and-save in a Dexie transaction**

Replace the pull loop body (lines 100-164) to use a transaction for the check+save:

```typescript
// Inside the for (const date of file.availableDates) loop:
try {
  // Check if local has pending changes — skip pull (local wins)
  const localMarker = await localDb.getMarkers(file.id!, date, username);
  if (localMarker?.syncStatus === "pending") continue;

  const response = await fetch(
    `${getApiBase()}/markers/${file.serverFileId}/${date}`,
    {
      headers: {
        ...(sitePassword ? { "X-Site-Password": sitePassword } : {}),
        "X-Username": username || "anonymous",
      },
    },
  );

  if (response.status === 404) continue;
  if (!response.ok) {
    errors.push(`Pull failed for ${date}: ${response.status}`);
    continue;
  }

  const data = await response.json();

  const sleepMarkers = (data.sleep_markers ?? []).map((m: Record<string, unknown>) => ({
    onsetTimestamp: toMilliseconds(m.onset_timestamp as number | null),
    offsetTimestamp: toMilliseconds(m.offset_timestamp as number | null),
    markerIndex: m.marker_index as number,
    markerType: m.marker_type as MarkerType,
  }));

  const nonwearMarkers = (data.nonwear_markers ?? []).map((m: Record<string, unknown>) => ({
    startTimestamp: toMilliseconds(m.start_timestamp as number | null),
    endTimestamp: toMilliseconds(m.end_timestamp as number | null),
    markerIndex: m.marker_index as number,
  }));

  const remoteHash = await computeMarkerHash({
    sleepMarkers,
    nonwearMarkers,
    isNoSleep: data.is_no_sleep ?? false,
    notes: data.notes ?? "",
  });

  // Skip if content is the same
  if (localMarker?.contentHash === remoteHash) continue;

  // Atomic check+save: re-verify not pending inside transaction
  const db = localDb.getDb();
  await db.transaction("rw", db.markers, async () => {
    const current = await db.markers
      .where("[fileId+date+username]")
      .equals([file.id!, date, username])
      .first();
    // Re-check inside transaction — if became pending since our check, skip
    if (current?.syncStatus === "pending") return;

    await localDb.saveMarkers(
      file.id!,
      date,
      username,
      sleepMarkers,
      nonwearMarkers,
      data.is_no_sleep ?? false,
      data.notes ?? "",
    );
    const updated = await db.markers
      .where("[fileId+date+username]")
      .equals([file.id!, date, username])
      .first();
    if (updated?.id) {
      await db.markers.update(updated.id, { syncStatus: "synced" });
    }
  });
  pulled++;
} catch (err) {
  errors.push(`Pull error for ${date}: ${err}`);
}
```

Note: This requires `localDb` to export `getDb`. Check if it already does — the `db/index.ts` re-exports from `@/lib/workspace-db`.

- [ ] **Step 2: Add getDb re-export if not present**

Check `frontend/src/db/index.ts` — it imports `getDb` from `@/lib/workspace-db`. Add re-export if not already there:
```typescript
export { getDb } from "@/lib/workspace-db";
```

- [ ] **Step 3: Verify typecheck passes**

Run: `cd /opt/sleep-scoring-web/frontend && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/sync.ts frontend/src/db/index.ts
git commit -m "fix(sync): wrap pull check+save in Dexie transaction to prevent race condition"
```

---

## Chunk 2: Dependency Upgrades

### Task 6: Upgrade @uppy packages from v4 to v5

**Files:**
- Modify: `frontend/package.json` (dependencies)
- Modify: `frontend/src/hooks/useTusUpload.ts` (if API changes)
- Modify: `frontend/src/lib/uppy-gzip-plugin.ts` (if API changes)

- [ ] **Step 1: Check Uppy v5 changelog for breaking changes**

Read the Uppy v5 migration guide. Key changes to watch for:
- Constructor API changes
- Event handler signature changes (`upload-progress`, `upload-success`, `upload-error`)
- Plugin registration API changes

- [ ] **Step 2: Update package.json dependencies**

```bash
cd /opt/sleep-scoring-web/frontend
# Use Docker for npm since bun isn't in PATH
docker run --rm -v "$(pwd):/app" -w /app node:22-slim sh -c "npm install @uppy/core@^5 @uppy/react@^5 @uppy/status-bar@^5 @uppy/tus@^5 && chown -R $(id -u):$(id -g) node_modules package.json package-lock.json"
```

- [ ] **Step 3: Update useTusUpload.ts for any API changes**

Review and update import paths, constructor, event signatures as needed based on v5 changelog.

- [ ] **Step 4: Update uppy-gzip-plugin.ts for any API changes**

Review and update the custom plugin class if BasePlugin API changed.

- [ ] **Step 5: Verify typecheck passes**

Run: `cd /opt/sleep-scoring-web/frontend && npx tsc --noEmit`

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/hooks/useTusUpload.ts frontend/src/lib/uppy-gzip-plugin.ts
git commit -m "chore(deps): upgrade @uppy packages from v4 to v5"
```

---

## Chunk 3: Pattern Improvements (Frontend)

### Task 7: Adopt queryOptions() pattern for TanStack Query

**Files:**
- Create: `frontend/src/api/query-options.ts`
- Modify: Files that use `useQuery` (update imports to use shared options)

This task extracts query configurations into reusable `queryOptions()` calls, following TanStack Query v5 best practices. This enables sharing query keys and configs between `useQuery`, `prefetchQuery`, and `queryClient.invalidateQueries`.

- [ ] **Step 1: Create query-options.ts with extracted options**

Create `frontend/src/api/query-options.ts`:

```typescript
import { queryOptions } from "@tanstack/react-query";
import { fetchWithAuth, getApiBase } from "@/api/client";

// Re-usable query option factories

export function filesQueryOptions() {
  return queryOptions({
    queryKey: ["files"],
    queryFn: () => fetchWithAuth<{ items: Array<{ id: number; filename: string; participant_id: string | null; status: string }>; total: number }>(`${getApiBase()}/files`),
  });
}

export function exportColumnsQueryOptions() {
  return queryOptions({
    queryKey: ["export-columns"],
    queryFn: () => fetchWithAuth<{ columns: Array<{ name: string; category: string; description: string | null; data_type: string; is_default: boolean }>; categories: Array<{ name: string; columns: string[] }> }>(`${getApiBase()}/export/columns`),
  });
}
```

- [ ] **Step 2: Update export.tsx to use queryOptions**

Replace inline query configs with imported options:
```typescript
import { filesQueryOptions, exportColumnsQueryOptions } from "@/api/query-options";

// Replace:
const { data: filesData } = useQuery({ queryKey: ["files"], queryFn: ... });
// With:
const { data: filesData } = useQuery({ ...filesQueryOptions(), enabled: isAuthenticated && caps.server });
```

- [ ] **Step 3: Verify typecheck passes**

Run: `cd /opt/sleep-scoring-web/frontend && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/query-options.ts frontend/src/pages/export.tsx
git commit -m "refactor(frontend): adopt queryOptions() pattern for TanStack Query v5"
```

---

### Task 8: Add branded timestamp types

**Files:**
- Create: `frontend/src/utils/branded-timestamps.ts`
- Modify: `frontend/src/utils/timestamps.ts` (update conversion functions)

- [ ] **Step 1: Create branded timestamp types**

Create `frontend/src/utils/branded-timestamps.ts`:

```typescript
/**
 * Branded types for timestamp units to prevent ms/sec confusion.
 *
 * Usage:
 *   const ms = 1710000000000 as TimestampMs;
 *   const sec = toSeconds(ms); // TimestampSec
 *   // toSeconds(sec) would be a type error
 */

declare const __ms: unique symbol;
declare const __sec: unique symbol;

export type TimestampMs = number & { readonly [__ms]: never };
export type TimestampSec = number & { readonly [__sec]: never };

/** Type-safe conversion: milliseconds to seconds */
export function msToSec(ms: TimestampMs): TimestampSec {
  return (ms / 1000) as TimestampSec;
}

/** Type-safe conversion: seconds to milliseconds */
export function secToMs(sec: TimestampSec): TimestampMs {
  return (sec * 1000) as TimestampMs;
}

/** Cast a raw number to TimestampMs (use at system boundaries) */
export function asMs(n: number): TimestampMs {
  return n as TimestampMs;
}

/** Cast a raw number to TimestampSec (use at system boundaries) */
export function asSec(n: number): TimestampSec {
  return n as TimestampSec;
}
```

- [ ] **Step 2: Verify typecheck passes**

Run: `cd /opt/sleep-scoring-web/frontend && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/utils/branded-timestamps.ts
git commit -m "feat(types): add branded timestamp types to prevent ms/sec confusion"
```

Note: Adopting these types across the full codebase is a separate, larger effort. This task only creates the types and conversion functions. Gradual adoption can happen file-by-file.

---

### Task 9: Document no-sleep semantics change

**Files:**
- Modify: `CLAUDE.md` (add to Data Hierarchy section)

- [ ] **Step 1: Add documentation about no-sleep + NAP coexistence**

Add to the "Data Hierarchy" section of CLAUDE.md, after the existing content:

```markdown
### No-Sleep Date Semantics

A date marked `isNoSleep = true` means **no main sleep occurred**, but **NAP markers are allowed**. When toggling no-sleep:
- **MAIN_SLEEP markers are deleted** (irrecoverable)
- **NAP markers are preserved**
- Metrics are still computed for NAP periods on no-sleep dates
- Export emits a no-sleep sentinel row AND any NAP marker rows for that date
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document no-sleep + NAP coexistence semantics"
```

---

## Chunk 4: Backend Refactor

### Task 10: Split markers.py into sub-routers

**Files:**
- Modify: `sleep_scoring_web/api/markers.py` (keep CRUD + shared models)
- Create: `sleep_scoring_web/api/markers_import.py` (import endpoint + helpers)
- Create: `sleep_scoring_web/api/markers_tables.py` (onset/offset table endpoints)
- Create: `sleep_scoring_web/api/markers_autoscore.py` (auto-scoring endpoint)
- Modify: `sleep_scoring_web/main.py` (register new sub-routers)

This is a large refactor. The 3,424 LOC `markers.py` should be split into focused modules:

1. `markers.py` — CRUD (GET/PUT/DELETE markers), shared models, background task functions (~800 LOC)
2. `markers_import.py` — CSV import endpoint and helpers (~600 LOC)
3. `markers_tables.py` — Onset/offset table data endpoints (~400 LOC)
4. `markers_autoscore.py` — Auto-scoring endpoint (~500 LOC)

- [ ] **Step 1: Identify section boundaries in markers.py**

Read the full file and identify which functions/classes belong to each module. Map imports.

- [ ] **Step 2: Create markers_import.py**

Extract the import endpoint (`POST /import-sleep-csv`), related models (`SleepImportResponse`, etc.), and helper functions (`_patch_sleep_annotation`, `_patch_nonwear_annotation`, `_update_user_annotation`).

The background task functions (`_patch_sleep_annotation`, `_patch_nonwear_annotation`, `_update_user_annotation`, `_calculate_and_store_metrics`) should stay in `markers.py` or move to a `markers_tasks.py` since they're shared.

- [ ] **Step 3: Create markers_tables.py**

Extract onset/offset table endpoints and their models.

- [ ] **Step 4: Create markers_autoscore.py**

Extract the auto-scoring endpoint and its logic.

- [ ] **Step 5: Update markers.py**

Remove extracted code, add imports from new modules where needed.

- [ ] **Step 6: Register new routers in main.py**

```python
from sleep_scoring_web.api import markers_import, markers_tables, markers_autoscore

app.include_router(markers_import.router, prefix=f"{settings.api_prefix}/markers", tags=["markers"])
app.include_router(markers_tables.router, prefix=f"{settings.api_prefix}/markers", tags=["markers"])
app.include_router(markers_autoscore.router, prefix=f"{settings.api_prefix}/markers", tags=["markers"])
```

- [ ] **Step 7: Verify backend lint and typecheck**

```bash
cd /opt/sleep-scoring-web
ruff check sleep_scoring_web/api/markers*.py
ruff format sleep_scoring_web/api/markers*.py
```

- [ ] **Step 8: Commit**

```bash
git add sleep_scoring_web/api/markers*.py sleep_scoring_web/main.py
git commit -m "refactor(backend): split markers.py into focused sub-modules"
```
