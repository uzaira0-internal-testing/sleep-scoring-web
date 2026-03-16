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
(nothing yet)
