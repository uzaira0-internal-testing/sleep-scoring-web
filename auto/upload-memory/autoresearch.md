# Autoresearch: Upload Peak Memory

## Objective
Reduce peak RSS during file upload processing. Currently holds 3 copies of the DataFrame during COPY: original, export_df copy, and itertuples list. Stream rows directly instead.

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `peak_rss_mb` (MB, lower is better) during upload
- **Secondary**: upload latency

## How to Run
`./auto/upload-memory/autoresearch.sh`

## Files in Scope
- `sleep_scoring_web/api/files.py` — `bulk_insert_activity_data`, upload processing
- `sleep_scoring_web/services/upload_processor.py` — File processing pipeline
- `sleep_scoring_web/services/loaders/` — CSV loaders

## Off Limits
- `tests/` — Do not modify tests
- `frontend/` — Frontend code
- `auto/` — Autoresearch infrastructure

## Constraints
- All existing tests must pass
- Upload must still produce correct data
- No breaking API changes

## What's Been Tried
(nothing yet)
