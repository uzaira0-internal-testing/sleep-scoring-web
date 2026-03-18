# Autoresearch: Improve Frame Rate

## Objective
Achieve 60fps+ (p10) during all user interactions — scroll, drag, zoom, pan on the scoring page chart.
Higher is better. Stop when 3 consecutive experiments yield less than 5% improvement.

## Metrics
- **Primary**: `fps_p10` (10th percentile FPS — worst-case frames, higher is better)
- **Secondary**: `drag_fps_p10`, `zoom_fps_p10`, `dropped_frames`

## How to Run
`./auto/frame-rate/autoresearch.sh`

## Files in Scope
- `frontend/src/components/activity-plot.tsx` — Main chart component (1,404 lines, most issues here)
- `frontend/src/components/marker-data-table.tsx` — Data table with drag-updated queries
- `frontend/src/store/index.ts` — Zustand store selectors
- `frontend/src/hooks/` — Custom hooks

## Off Limits
- `frontend/src/wasm/` — WASM bindings
- `frontend/src/workers/` — Worker thread (already good)
- `frontend/src/api/` — API client layer
- `tests/` — Test files
- Backend code

## Known Issues (from audit)

### HIGH IMPACT
1. **renderMarkers() destroys & rebuilds ALL marker DOM elements on every call** (line 224-225)
   - Fix: Diff-update — reposition existing elements instead of remove+recreate
2. **renderMarkers not wrapped in useCallback** (line 215-612)
   - Fix: Wrap in useCallback with proper dependency array
3. **getBoundingClientRect() on every mousemove during drag** (line 743-745)
   - Fix: Cache rect at drag start, use cached value during drag
4. **20-item dependency array on marker rendering effect** (line 1336-1359)
   - Fix: Use refs for values that change but shouldn't trigger re-render

### MEDIUM IMPACT
5. **DOM querySelector on every mousemove** (line 743-756)
   - Fix: Cache element references at drag start
6. **No throttle on wheel zoom** (line 961-988)
   - Fix: rAF-gate the setScale calls
7. **backdrop-blur on sticky table header** (marker-data-table.tsx:250)
   - Fix: Replace with solid background
8. **Inline style objects per table row** (marker-data-table.tsx:282-286)
   - Fix: CSS classes or memoized style objects
9. **Array.from() copies on every query** (marker-data-table.tsx:23-28)
   - Fix: Work with TypedArrays directly

## Strategic Direction
- Use CSS `transform: translateX/Y()` instead of `left`/`top` for marker positioning — transforms skip layout
- Add `will-change: transform` to dragged elements to promote to GPU layer
- Batch all DOM writes inside `requestAnimationFrame`
- Cache DOM references (querySelector results) at drag-start, not per-frame
- Prefer updating element positions over destroying/creating elements

## Baseline
- **Commit**: (fill after first run)
- **fps_p10**: (fill after first run)

## What's Been Tried

## Current Best
- **fps_p10**: (updated by loop)
