# Autoresearch: Database Index Optimization

## Objective
Add missing indexes and optimize existing ones. Key targets:
- Missing composite index on `markers(file_id, analysis_date, created_by)`
- `available_dates` scan doing full-table `SELECT DISTINCT date(timestamp)` on every load
- Any other N+1 or full-scan patterns

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `query_ms` (ms, lower is better) — worst-case query time across key endpoints
- **Secondary**: EXPLAIN ANALYZE output

## How to Run
`./auto/db-indexes/autoresearch.sh`

## Files in Scope
- `sleep_scoring_web/db/models.py` — SQLAlchemy models with indexes
- `sleep_scoring_web/api/files.py` — File/dates queries
- `sleep_scoring_web/api/markers.py` — Marker queries
- `sleep_scoring_web/api/activity.py` — Activity data queries
- `sleep_scoring_web/services/` — Service layer queries

## Off Limits
- `tests/` — Do not modify tests
- `frontend/` — Frontend code
- `auto/` — Autoresearch infrastructure

## Constraints
- Indexes must be added via SQLAlchemy model `__table_args__` (Alembic will pick them up)
- All existing tests must pass
- No breaking schema changes

## What's Been Tried
(nothing yet)
