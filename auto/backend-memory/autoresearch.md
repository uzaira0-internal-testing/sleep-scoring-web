# Autoresearch: Backend Memory Usage

## Objective
Reduce per-request memory allocations. Key target: Sadeh algorithm creates a full pandas DataFrame for a pure-numeric 11-window computation. Replace with numpy-only or pure Python.

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `rss_kb` (KB delta per scoring request, lower is better)
- **Secondary**: scoring latency

## How to Run
`./auto/backend-memory/autoresearch.sh`

## Files in Scope
- `sleep_scoring_web/services/algorithms/sadeh.py` — Sadeh scoring (pandas-heavy)
- `sleep_scoring_web/services/algorithms/cole_kripke.py` — Cole-Kripke scoring
- `sleep_scoring_web/services/algorithms/base.py` — Algorithm base class
- `sleep_scoring_web/api/activity.py` — Scoring endpoint
- `sleep_scoring_web/services/activity_data.py` — Activity data service

## Off Limits
- `tests/` — Do not modify tests
- `frontend/` — Frontend code
- `auto/` — Autoresearch infrastructure
- Algorithm correctness (output must not change)

## Constraints
- All existing tests must pass
- Scoring results must be identical
- No new heavy dependencies

## What's Been Tried
(nothing yet)
