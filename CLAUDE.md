# CLAUDE.md

<!-- Deploy test: 2026-01-11-v1 -->

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **IMPORTANT: The desktop PyQt6 application (`sleep_scoring_app/`, `tests/`) is ARCHIVED and NOT under active development. Do NOT modify, fix, or refactor any desktop app code. All development effort goes to the web application (frontend + backend).**

## Commands

### Web Application - Docker

**CRITICAL: NEVER use `docker compose down -v`** — the `-v` flag deletes database volumes and ALL stored data (files, markers, diary entries, user settings). This is irreversible. Only use `down` (without `-v`) or `docker compose restart`.

**Local Development**:
```bash
cd docker
docker compose -f docker-compose.local.yml up -d --build
docker compose -f docker-compose.local.yml logs -f backend
docker compose -f docker-compose.local.yml down          # Safe: keeps data
# docker compose -f docker-compose.local.yml down -v     # DANGEROUS: DESTROYS ALL DATA
```

**Production** (uses packages from GitHub Releases):
```bash
cd docker
export GITHUB_REPO=your-org/sleep-scoring-web
export PACKAGES_VERSION=0.1.0
docker compose up -d --build
docker compose logs -f backend
docker compose down                                       # Safe: keeps data
```

**Publishing Packages** (run before production builds):
```bash
git tag packages-v0.1.0
git push origin packages-v0.1.0
```

**Access Points:**
- Frontend: http://localhost:8501
- Backend API: http://localhost:8500
- API Docs: http://localhost:8500/docs

### Frontend (TypeScript/React)

```bash
cd frontend

# Typecheck (NEVER run in parallel — OOM risk, see memory/tsc-oom.md)
npx tsc --noEmit

# Dev server
npx vite dev

# Production build
npx vite build

# NOTE: bun is NOT in system PATH — always use npx
```

### Backend (Python/FastAPI)

```bash
# Lint and format
ruff check sleep_scoring_web/ && ruff format sleep_scoring_web/

# Type check
basedpyright sleep_scoring_web/
```

### Rust WASM Crate

```bash
cd /opt/sleep-scoring-web/monorepo/packages/sleep-scoring-wasm

# Run tests (25 unit + 3 golden)
cargo test

# Build WASM for frontend
wasm-pack build --target web --out-dir ../../apps/sleep-scoring-demo/frontend/src/wasm/pkg crates/algorithms
```

## Project Overview

Web application for visual sleep scoring of accelerometer data. React+Vite frontend with FastAPI backend, plus a local-first WASM PWA mode for offline processing.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (React + Vite + TypeScript)                       │
│  ├── Pages & Components (UI)                                │
│  ├── Zustand Store (state management)                       │
│  ├── Hooks (data loading, autosave, connectivity)           │
│  ├── Services (data-source, sync, local-processing)         │
│  ├── Web Worker + Comlink (off-main-thread WASM)            │
│  └── IndexedDB via Dexie (local-first persistence)          │
├─────────────────────────────────────────────────────────────┤
│  Rust WASM (packages/sleep-scoring-wasm/)                   │
│  ├── Sadeh 1994, Cole-Kripke 1992 (sleep/wake)             │
│  ├── Choi 2011 (nonwear detection)                          │
│  ├── CSV Parser (ActiGraph + GENEActiv)                     │
│  └── Epoching (raw 100Hz → 60s counts)                      │
├─────────────────────────────────────────────────────────────┤
│  Backend (FastAPI + PostgreSQL)                              │
│  ├── REST API (files, markers, activity data)               │
│  ├── TUS resumable upload                                   │
│  └── Sleep scoring algorithms (Python)                      │
└─────────────────────────────────────────────────────────────┘
```

### Dual Data Mode

The app supports two data sources per file:
- **Server mode**: Files uploaded via TUS, processed server-side, stored in PostgreSQL
- **Local mode**: Files opened from local filesystem, processed client-side via WASM, stored in IndexedDB

`FileRecord.source` determines which `DataSource` handles each file. Both coexist.

---

## Key Files

### Frontend (`frontend/src/`)

| File | Purpose |
|------|---------|
| `store/index.ts` | Main Zustand store (file, date, markers, UI state) |
| `store/sync-store.ts` | Sync status store (online, pending, conflicts) |
| `services/data-source.ts` | DataSource interface + Server/Local implementations |
| `services/local-processing.ts` | Full local file processing pipeline |
| `services/sync.ts` | Push/pull marker sync engine |
| `workers/wasm-worker.ts` | Comlink-exposed WASM worker |
| `workers/index.ts` | Singleton worker + typed wrapper |
| `db/schema.ts` | Dexie database schema (FileRecord, ActivityDay, MarkerRecord) |
| `db/index.ts` | CRUD service layer for IndexedDB |
| `hooks/useMarkerAutoSave.ts` | Marker autosave with debounce |
| `hooks/useConnectivity.ts` | Online detection (navigator + health check) |
| `hooks/useLocalFile.ts` | File System Access API + fallback |
| `lib/content-hash.ts` | SHA-256 hashing for sync dedup |
| `lib/chunked-reader.ts` | Chunked file reading for multi-GB CSVs |
| `components/layout.tsx` | Main layout with sidebar + offline banner |

### Backend (`sleep_scoring_web/`)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app entry point |
| `api/` | REST API routes |
| `services/` | Business logic services |
| `models/` | SQLAlchemy models |

### Rust WASM (`packages/sleep-scoring-wasm/`)

| File | Purpose |
|------|---------|
| `crates/algorithms/src/sadeh.rs` | Sadeh 1994 algorithm |
| `crates/algorithms/src/cole_kripke.rs` | Cole-Kripke 1992 algorithm |
| `crates/algorithms/src/choi.rs` | Choi 2011 nonwear detection |
| `crates/algorithms/src/csv_parser.rs` | CSV column detection + parsing |
| `crates/algorithms/src/epoching.rs` | Raw → epoch conversion |
| `crates/algorithms/src/lib.rs` | wasm_bindgen exports |

---

## Coding Standards

### Frontend (TypeScript/React)

#### NEVER Use Effect-Synced Refs for Zustand Store Values in Callbacks (CRITICAL)

```tsx
// WRONG — ref can be stale when callback fires in the same render cycle
const sleepMarkersRef = useRef(sleepMarkers);
useEffect(() => { sleepMarkersRef.current = sleepMarkers; }, [sleepMarkers]);
const save = useCallback(() => {
  api.saveMarkers(sleepMarkersRef.current); // ← CAN BE STALE
}, []);

// CORRECT — getState() is synchronous and always current
const save = useCallback(() => {
  const state = useSleepScoringStore.getState();
  api.saveMarkers(state.sleepMarkers);
}, []);
```

**Applies to:** `useMarkerAutoSave.ts`, `activity-plot.tsx` uPlot plugin callbacks, any callback reading store state.

#### Type Annotations

All new/modified function signatures must have explicit types. Avoid `any` and `unknown` where specific types exist.

#### Constants Over Magic Strings

Use existing constants from `api/types.ts` (e.g., `MarkerType`, `AlgorithmType`) instead of hardcoded strings.

### Backend (Python)

#### StrEnums for ALL String Constants

```python
from sleep_scoring_web.constants import AlgorithmType, MarkerType
algorithm = AlgorithmType.SADEH_1994_ACTILIFE  # NOT "sadeh_1994"
```

#### Type Annotations on All Function Signatures

```python
def calculate_metrics(period: SleepPeriod, results: list[int]) -> SleepMetrics | None: ...
```

---

## Data Hierarchy

```
Study → Participant → Date → (Sleep + Nonwear Markers) → Period → Metrics
```

- **Metrics** belong to each **SleepPeriod**, NOT to the date
- **Nonwear** is a first-class citizen

### No-Sleep Date Semantics

A date marked `isNoSleep = true` means **no main sleep occurred**, but **NAP markers are allowed**. When toggling no-sleep:
- **MAIN_SLEEP markers are deleted** (irrecoverable)
- **NAP markers are preserved**
- Metrics are still computed for NAP periods on no-sleep dates
- Export emits a no-sleep sentinel row AND any NAP marker rows for that date

---

## Automated Marker Placement Rules

These rules govern how sleep periods should be automatically detected and marked.

### Base Algorithm Requirements

- **Onset**: First epoch of 3+ consecutive sleep epochs
- **Offset**: Ends with 5+ consecutive minutes of sleep
- **Diary tolerance**: 15 minutes for choosing between multiple candidates
- **Nonwear**: No Choi + diary nonwear overlap during the period

### Detailed Placement Rules

1. **Activity in Middle of Sleep Period**: Include activity within diary-reported sleep if continuous sleep epochs follow (any 5 consecutive sleep epochs qualify)
2. **Small Periods Near Onset**: Consider duration, wake duration, spike magnitude. At least 3 sleep epochs required
3. **Extended Sleep Before Diary Marker**: Extend to typical nap period if continuous sleep epochs precede diary marker
4. **Variation in Nap Timing**: Mark continuous >=10 sleep epoch periods as naps
5. **Choi-Only Nonwear with Spike**: Can be ignored if activity spike exists within sleep period
6. **Equidistant Candidates**: Choose the one with fewer potential issues (nonwear, spikes)
7. **Cross-Day Nonwear Patterns**: Assume diary nonwear at similar times applies to other days
8. **Sleep Onset Before In-Bed Time**: Use in-bed time instead

### Visual Features for Selection (NOT metrics-based)

Use only features visible on the actogram: activity spikes, transitions, max activity. Do NOT use statistical aggregates (sleep efficiency, mean activity, wake bout counts).

---

## Known Issues / Technical Debt

### 1. Silent Failures Need Better Logging

Data loading that returns empty/None when data was expected should log at WARNING level with context.

### 2. Docker Build: bun.lock Sync

When adding npm packages via `npm install` on the host (because bun isn't in PATH), `bun.lock` must also be updated for the Docker build (which uses `bun install`). Either:
- Run `docker run --rm -v "$(pwd)/frontend:/app" -w /app oven/bun:1-alpine bun install` to update bun.lock
- Or update the Dockerfile to use npm

---

## Archived: Desktop Application

The PyQt6 desktop application in `sleep_scoring_app/` and its tests in `tests/` are **archived**. Do not modify this code. The algorithms have been ported to Rust WASM (`packages/sleep-scoring-wasm/`) for the web app.
