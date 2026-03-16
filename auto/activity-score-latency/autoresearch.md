# Autoresearch: Activity Score Endpoint Latency

## Objective
Reduce latency of `GET /api/v1/activity/{file_id}/{date}/score`. This endpoint runs a redundant `available_dates` full-table scan on every request. Also optimize the scoring computation path.

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `p50_ms` (ms, lower is better)
- **Secondary**: response size

## How to Run
`./auto/activity-score-latency/autoresearch.sh`

## Files in Scope
- `sleep_scoring_web/api/activity.py` — Activity data + scoring endpoints
- `sleep_scoring_web/services/activity_data.py` — Activity data service
- `sleep_scoring_web/services/algorithms/` — Scoring algorithms
- `sleep_scoring_web/db/models.py` — Model indexes

## Off Limits
- `tests/` — Do not modify tests
- `frontend/` — Frontend code
- `auto/` — Autoresearch infrastructure

## Constraints
- All existing tests must pass
- Response data must remain correct
- No breaking API changes

## What's Been Tried

### Kept (improvements)

1. **Inline data fetch in score endpoint** (f06f8ec)
   - Eliminated redundant file-load + access-check queries by inlining get_activity_data()
   - Column projection instead of full ORM load
   - Skip available_dates when not in `fields` parameter
   - Baseline 195.7ms -> 135.6ms (31%)

2. **Derive available_dates from File metadata** (d22d331)
   - Replace SELECT DISTINCT date(timestamp) full-table scan (~8ms) with O(1) date range from file.start_time/end_time
   - 135.6ms -> 87.9ms (35%)

3. **Inline timegm in hot loop** (2900cc2)
   - Local variable binding for calendar.timegm
   - Small improvement

4. **Vectorized Sadeh algorithm** (9131d42)
   - Pure numpy implementation replacing pandas DataFrame wrapper
   - Eliminates DataFrame construction, column validation, df.copy()
   - Vectorized rolling SD and scoring (was Python for-loops)
   - 68x faster (0.24ms vs 16.5ms for 1440 epochs)
   - ~44ms -> ~21ms (52%)

5. **Combined file + user settings query** (31a0529)
   - Single outerjoin query loads File + UserSettings in one DB round-trip
   - Replaces 2 sequential queries
   - ~21ms -> ~15ms (26%)

6. **Use total_seconds() instead of timegm** (2c46419)
   - (dt - EPOCH).total_seconds() is 5x faster than calendar.timegm(dt.timetuple())
   - ~15ms -> ~9ms (40%)

7. **Raw SQL for activity + sensor nonwear queries** (b5184b6)
   - text() bypasses SQLAlchemy query compilation overhead
   - Remove unused Marker ORM import

7. **Bypass Pydantic serialization** (b9e15f8)
   - Build response dict directly + json.dumps with compact separators
   - Eliminates ActivityDataResponse/ActivityDataColumnar model construction

8. **Server-side epoch conversion** (0a8981f)
   - EXTRACT(EPOCH FROM timestamp)::float in PostgreSQL
   - Eliminates 1440 Python datetime operations

9. **Optimized Choi nonwear detection** (5f5644a)
   - Direct numpy implementation, skips 1440 dummy datetime creation
   - 4.2x faster: 0.17ms vs 0.72ms

### Current State
- Server-side p50: ~8ms (quiet) / 33-35ms (under contention from other agents)
- Total improvement from baseline: ~195ms -> ~8ms (96%)

### Ideas Not Yet Tried
- Batch activity data + sensor nonwear into single CTE query
- Connection pooling optimization
- Response compression (gzip)
- In-memory LRU cache for file+settings (avoid DB on repeated requests)
