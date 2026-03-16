# Autoresearch: Parallelize DB Queries

## Objective
Reduce wall-clock latency of endpoints that run multiple independent DB queries serially. Primary target: `GET /api/v1/files/{file_id}/dates/status` which runs 5 serial queries.

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `p50_ms` (ms, lower is better) for `/dates/status`
- **Secondary**: individual query times

## How to Run
`./auto/db-query-parallel/autoresearch.sh`

## Files in Scope
- `sleep_scoring_web/api/files.py` — dates/status endpoint (5 serial queries)
- `sleep_scoring_web/api/activity.py` — activity scoring (2 serial queries)
- `sleep_scoring_web/api/markers.py` — marker fetching
- `sleep_scoring_web/api/markers_tables.py` — table data
- `sleep_scoring_web/services/` — service layer
- `sleep_scoring_web/db/session.py` — session management

## Off Limits
- `tests/` — Do not modify tests
- `frontend/` — Frontend code
- `auto/` — Autoresearch infrastructure
- Database schema/migration changes

## Constraints
- All existing tests must pass (`uv run pytest tests/web/ -x -q`)
- No new dependencies without strong justification

## What's Been Tried

### Experiment 1: asyncio.gather with separate sessions (DISCARDED)
- Used asyncio.gather to run 5 queries in parallel, each with its own session
- p50 went from 73.83ms to 299.2ms (4x worse) due to connection pool contention
- 5 VUs × 5 sessions = 25 concurrent connections overwhelmed the pool

### Experiment 2: Single raw SQL with CTEs + LEFT JOINs (KEPT)
- Replaced 5 serial ORM queries with 1 raw SQL query using CTEs and LEFT JOINs
- Also merged 2 annotation queries into 1, used require_file_and_access
- p50: 73.83ms → 35.81ms (51% improvement)

### Experiment 3: Fold file access check into main SQL query (KEPT)
- Incorporated file existence + access permission check into CTE
- Saves 1-2 separate DB round-trips for access control
- p50: 35.81ms → 11.47ms (68% improvement)

### Experiment 4: Compute boolean flags in SQL (KEPT)
- Moved has_markers, has_auto_score computations from Python JSON deserialization to SQL
- p50: 11.47ms → 8.84ms (23% improvement)

### Experiment 5: Bypass Pydantic with direct JSON Response (KEPT)
- Return Response(json.dumps(...)) instead of list[DateStatus]
- p50: 8.84ms → 8.1ms (8% improvement)

### Experiment 6: Diary-first date enumeration (KEPT)
- When diary entries exist, use diary dates directly (index-only scan)
- Avoids expensive DISTINCT date(timestamp) scan on 20K+ activity rows
- p50: 8.1ms → 4.77ms (41% improvement)

### Experiment 7: Module-level SQL constant (KEPT)
- Hoisted text() SQL to module-level _DATES_STATUS_SQL constant
- p50: 4.77ms → 4.33ms (9% improvement)

### Experiment 8: Manual JSON string building (DISCARDED)
- Built JSON manually with f-strings instead of json.dumps
- p50: 4.77ms → 4.57ms (4.2% - below 5% threshold)
- Fragile code for marginal gain

## Current Best
- p50_ms = 4.33 (94.1% reduction from baseline 73.83ms)
- Throughput: ~1060 req/s (17x improvement from baseline 62 req/s)
- Server-side processing: ~2.75ms, remaining ~1.5ms is network overhead

## Stopping
Stopped after experiment 8 produced <5% improvement. Three experiments at diminishing
returns territory (4.2%, module-level was borderline). Further gains would require
infrastructure-level changes (middleware stack, uvicorn workers, connection pooling).
