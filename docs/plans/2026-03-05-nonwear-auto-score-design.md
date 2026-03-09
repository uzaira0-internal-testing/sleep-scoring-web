# Nonwear Auto-Score Design

**Date:** 2026-03-05
**Updated:** 2026-03-06
**Status:** Implemented

## Overview

"Auto Nonwear" button alongside "Auto Sleep" on the scoring toolbar. Two-pass detection algorithm: (1) diary-anchored with zero-activity extension, and (2) Choi + sensor overlap with zero activity (no diary needed). Combined review dialog with sleep auto-score. Configurable threshold in Study Settings.

## Algorithm

### Pass 1: Diary-Anchored Detection

For each diary nonwear period (up to 3 per date):

1. Parse diary `nonwear_N_start` / `nonwear_N_end` as the anchor window
2. From anchor start, extend backward while `max(axis_y, vector_magnitude) <= threshold`
3. From anchor end, extend forward while `max(axis_y, vector_magnitude) <= threshold`
4. Cap extensions at Choi/sensor nonwear boundaries (whichever is available). If neither exists, cap at 30 minutes beyond diary times
5. Validate the detected region:
   - **80% of epochs must have activity <= threshold** — skip if too much activity in the range
   - **Minimum 10 minutes** of zero/near-zero activity epochs — skip if shorter
   - **No overlap with sleep markers** — check existing saved markers
6. Return suggested nonwear marker with notes explaining: diary window, detected extension, which signals confirmed it

### Pass 2: Choi + Sensor Overlap (No Diary Needed)

After diary-anchored detection (or when no diary exists):

1. Find all epochs where **both** Choi nonwear AND sensor nonwear agree
2. Filter to only epochs where `max(axis_y, vector_magnitude) <= threshold`
3. Extract contiguous runs from the overlap set
4. Apply same validation:
   - Minimum 10 minutes duration
   - No overlap with sleep markers
   - No overlap with markers already placed by Pass 1
5. Return with note: "confirmed by Choi + sensor, zero activity"

### Activity Measurement

Activity is measured as `max(axis_y, vector_magnitude)` per epoch — an epoch is only "zero activity" if **both** Y-axis and vector magnitude are at or below threshold.

## Configuration

- `threshold`: integer, default 0. Stored in Study Settings → Nonwear Detection → "Auto-Nonwear Activity Threshold" (`extra_settings.nonwear_threshold`). Shared across all users.
- `max_extension_minutes`: 30 (hardcoded, applies to diary-anchored when no Choi/sensor)
- `min_duration_minutes`: 10 (hardcoded)

## Frontend

### Toolbar
- "Auto Sleep" button (renamed from "Auto-Score")
- "Auto Nonwear" button — always enabled when file/date selected (no diary requirement since Pass 2 works without diary)
- Both have separate "Auto" checkbox toggles for auto-on-navigate

### Combined Review Dialog
- Single dialog shown when either auto-sleep or auto-nonwear results are present
- **Sleep section** (top): notes, marker list, "Apply Sleep" button
- **Nonwear section** (bottom): notes, marker list, "Apply Nonwear" button
- Horizontal divider between sections when both present
- "Dismiss" button to close
- Dialog is **not shown** when nonwear detection returns zero markers (silently skipped)

### Auto-Navigate Toggle
- `autoNonwearOnNavigate` preference (separate from `autoScoreOnNavigate`)
- Guard conditions: only runs if no existing nonwear markers, mutation not running
- 800ms debounce (slightly longer than sleep's 500ms to avoid race)

### Store
- `autoNonwearOnNavigate: boolean` in PreferencesState
- Persisted to localStorage via `partialize` and `user-state.ts`

## Backend

### Endpoint
`POST /markers/{file_id}/{analysis_date}/auto-nonwear`

Query params:
- `threshold` (int, default 0, ge=0, le=1000)

Response: `AutoNonwearResponse` with:
- `nonwear_markers`: list of `{start_timestamp, end_timestamp, marker_index}`
- `notes`: list of strings explaining decisions

### Service Function
`place_nonwear_markers()` in `services/marker_placement.py`

Inputs:
- `timestamps`, `activity_counts` (max of Y and VM)
- `diary_nonwear` (list of start/end string tuples, may be empty)
- `choi_nonwear` (mask), `sensor_nonwear_periods`
- `existing_sleep_markers`, `analysis_date`, `threshold`

Outputs: `NonwearPlacementResult` with markers list + notes list

## Rules Summary

1. Diary nonwear anchors Pass 1 — extend outward while activity <= threshold
2. Extensions bounded by Choi/sensor nonwear (never extend beyond what they support)
3. If no Choi/sensor, max extension is 30 minutes beyond diary
4. 80% of epochs in detected range must have activity <= threshold
5. Minimum 10 minutes of qualifying activity epochs
6. Never overlap with sleep markers
7. Pass 2: Choi + sensor overlap with zero activity works WITHOUT diary
8. Activity uses max(axis_y, vector_magnitude) — both must be zero
9. Threshold is configurable in Study Settings (default 0)
10. Review dialog silently skips when no markers found

## Bug Fixes Applied

1. **Diary assumed 100% correct** (2026-03-06): Added 80% zero-activity validation within detected range. Previously diary window epochs were accepted unconditionally.
2. **Only checked axis_y** (2026-03-06): Changed to `max(axis_y, vector_magnitude)` per user requirement "Y and/or VM".
3. **Early return blocked Choi+sensor pass** (2026-03-06): Three layers of early returns prevented Pass 2 from running when no diary existed:
   - Service function returned early on empty diary periods
   - API endpoint returned early before loading Choi/sensor data
   - Frontend button was disabled when `hasNoDiary`
4. **Empty results showed dialog** (2026-03-06): Dialog now silently skips when zero markers detected.
