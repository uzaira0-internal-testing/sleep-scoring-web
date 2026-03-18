# Autoresearch: IndexedDB Performance

## Objective
Reduce wall-clock time of `listDatesStatus` and other IndexedDB-heavy operations. Currently loads ALL ActivityDay ArrayBuffers (24MB for 30 days) just to compute complexity scores. Cache complexity separately.

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `dates_status_ms` (ms, lower is better) — time for listDatesStatus on a multi-day file
- **Secondary**: memory usage during the operation

## How to Run
`./auto/indexeddb-perf/autoresearch.sh`

## Files in Scope
- `frontend/src/services/data-source.ts` — LocalDataSource.listDatesStatus
- `frontend/src/db/schema.ts` — Dexie schema, tables
- `frontend/src/db/index.ts` — CRUD layer
- `frontend/src/services/local-processing.ts` — Processing pipeline
- `frontend/src/lib/content-hash.ts` — Hashing utilities

## Off Limits
- `tests/` — Do not modify tests
- Backend code — This is frontend-only
- `auto/` — Autoresearch infrastructure

## Constraints
- Existing vitest tests must pass (`cd frontend && npx vitest run`)
- TypeScript must compile (`cd frontend && npx tsc --noEmit`)
- No breaking changes to DataSource interface

## What's Been Tried
(nothing yet)
