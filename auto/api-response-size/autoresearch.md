# Autoresearch: API Response Size

## Objective
Reduce compressed API response sizes. JSON float arrays are verbose — explore binary encoding, delta-encoding timestamps, base64 for algorithm results.

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `response_kb` (KB compressed, lower is better)
- **Secondary**: uncompressed size

## How to Run
`./auto/api-response-size/autoresearch.sh`

## Files in Scope
- `sleep_scoring_web/api/activity.py` — Activity data serialization
- `sleep_scoring_web/api/markers_tables.py` — Table data serialization
- `sleep_scoring_web/api/schemas.py` — Response schemas
- `sleep_scoring_web/main.py` — Middleware (compression)
- `frontend/src/api/types.ts` — Frontend type definitions (must stay in sync)
- `frontend/src/services/data-source.ts` — Response parsing

## Off Limits
- `tests/` — Do not modify tests
- `auto/` — Autoresearch infrastructure

## Constraints
- Frontend must still parse responses correctly
- All existing tests must pass
- API backwards compatibility (or update frontend in same commit)

## What's Been Tried
(nothing yet)
