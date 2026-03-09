# Nonwear Auto-Score Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an "Auto Nonwear" button that auto-detects nonwear periods using diary anchors, zero-activity detection, and Choi/sensor confirmation.

**Architecture:** New `place_nonwear_markers()` function in marker_placement.py implements the detection algorithm. New backend endpoint `POST /markers/{file_id}/{date}/auto-nonwear` mirrors the existing auto-score pattern. Frontend adds a second auto-score button + review dialog for nonwear alongside the renamed "Auto Sleep" button.

**Tech Stack:** Python/FastAPI backend, React/Zustand frontend, same patterns as existing sleep auto-score

---

### Task 1: Backend — `place_nonwear_markers()` in marker_placement.py

**Files:**
- Modify: `sleep_scoring_web/services/marker_placement.py`

**Step 1: Add the nonwear placement function**

Add at the end of `marker_placement.py`, before any if `__name__` block:

```python
# =============================================================================
# Nonwear Auto-Placement
# =============================================================================

@dataclass(frozen=True)
class NonwearPlacementResult:
    """Result of nonwear auto-placement."""
    nonwear_markers: list[dict[str, Any]]
    notes: list[str]


def place_nonwear_markers(
    *,
    timestamps: list[float],
    activity_counts: list[float],
    diary_nonwear: list[tuple[str | None, str | None]],
    choi_nonwear: list[int] | None,
    sensor_nonwear_periods: list[tuple[float, float]],
    existing_sleep_markers: list[tuple[float, float]],
    analysis_date: str,
    epoch_length_seconds: int = 60,
    threshold: int = 0,
    max_extension_minutes: int = 30,
    min_duration_minutes: int = 10,
) -> NonwearPlacementResult:
    """
    Auto-place nonwear markers using diary anchors with zero-activity detection.

    Algorithm:
    1. Parse diary nonwear start/end as anchor windows
    2. Extend outward while activity <= threshold
    3. Cap extensions at Choi/sensor boundaries (or max_extension_minutes if neither)
    4. Skip periods < min_duration_minutes of qualifying activity
    5. Skip periods overlapping with sleep markers
    """
    if not timestamps or not activity_counts:
        return NonwearPlacementResult(nonwear_markers=[], notes=["No activity data"])

    # Parse diary nonwear periods into epoch indices
    date_obj = datetime.strptime(analysis_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    epoch_times = [datetime.fromtimestamp(ts, tz=timezone.utc) for ts in timestamps]
    notes: list[str] = []
    markers: list[dict[str, Any]] = []
    min_epochs = max(1, (min_duration_minutes * 60) // epoch_length_seconds)

    valid_diary_periods: list[tuple[datetime, datetime, int]] = []
    for i, (nw_start_str, nw_end_str) in enumerate(diary_nonwear):
        if not nw_start_str or not nw_end_str:
            continue
        if not _diary_time_present(nw_start_str) or not _diary_time_present(nw_end_str):
            continue
        nw_start_dt = _parse_diary_time(nw_start_str, date_obj)
        nw_end_dt = _parse_diary_time(nw_end_str, date_obj)
        if nw_end_dt <= nw_start_dt:
            nw_end_dt += timedelta(days=1)
        valid_diary_periods.append((nw_start_dt, nw_end_dt, i + 1))

    if not valid_diary_periods:
        return NonwearPlacementResult(
            nonwear_markers=[],
            notes=["No diary nonwear periods found for this date"],
        )

    # Build Choi nonwear set for fast lookup
    choi_nw_set: set[int] = set()
    if choi_nonwear:
        for idx, val in enumerate(choi_nonwear):
            if val == 1:
                choi_nw_set.add(idx)

    # Build sensor nonwear intervals as epoch index ranges
    sensor_nw_ranges: list[tuple[int, int]] = []
    for snw_start, snw_end in sensor_nonwear_periods:
        si = _find_nearest_epoch(timestamps, snw_start)
        ei = _find_nearest_epoch(timestamps, snw_end)
        if si is not None and ei is not None:
            sensor_nw_ranges.append((si, ei))

    # Build sleep marker intervals as timestamp ranges for overlap check
    sleep_intervals: list[tuple[float, float]] = []
    for sm_start, sm_end in existing_sleep_markers:
        sleep_intervals.append((sm_start, sm_end))

    has_external_signals = bool(choi_nw_set) or bool(sensor_nw_ranges)

    for diary_start_dt, diary_end_dt, diary_idx in valid_diary_periods:
        # Find epoch indices for diary window
        start_idx = _find_nearest_epoch_dt(epoch_times, diary_start_dt)
        end_idx = _find_nearest_epoch_dt(epoch_times, diary_end_dt)
        if start_idx is None or end_idx is None:
            notes.append(f"Nonwear {diary_idx}: diary times outside data range, skipped")
            continue

        # Extend backward from start while activity <= threshold
        ext_start = start_idx
        max_ext_epochs = (max_extension_minutes * 60) // epoch_length_seconds
        while ext_start > 0:
            candidate = ext_start - 1
            if activity_counts[candidate] > threshold:
                break
            # Check extension cap
            if has_external_signals:
                if not _epoch_in_nonwear_signal(candidate, choi_nw_set, sensor_nw_ranges):
                    break
            elif (start_idx - candidate) >= max_ext_epochs:
                break
            ext_start = candidate

        # Extend forward from end while activity <= threshold
        ext_end = end_idx
        while ext_end < len(timestamps) - 1:
            candidate = ext_end + 1
            if activity_counts[candidate] > threshold:
                break
            if has_external_signals:
                if not _epoch_in_nonwear_signal(candidate, choi_nw_set, sensor_nw_ranges):
                    break
            elif (candidate - end_idx) >= max_ext_epochs:
                break
            ext_end = candidate

        # Check minimum duration
        duration_epochs = ext_end - ext_start + 1
        if duration_epochs < min_epochs:
            notes.append(
                f"Nonwear {diary_idx}: only {duration_epochs} epochs "
                f"({duration_epochs * epoch_length_seconds // 60} min) of zero activity, "
                f"need {min_duration_minutes} min minimum, skipped"
            )
            continue

        # Check overlap with sleep markers
        nw_start_ts = timestamps[ext_start]
        nw_end_ts = timestamps[ext_end]
        overlaps_sleep = any(
            nw_start_ts < sm_end and nw_end_ts > sm_start
            for sm_start, sm_end in sleep_intervals
        )
        if overlaps_sleep:
            notes.append(f"Nonwear {diary_idx}: overlaps with sleep marker, skipped")
            continue

        # Build extension note
        ext_note_parts = []
        if ext_start < start_idx:
            ext_min = (start_idx - ext_start) * epoch_length_seconds // 60
            ext_note_parts.append(f"extended {ext_min}min before diary start")
        if ext_end > end_idx:
            ext_min = (ext_end - end_idx) * epoch_length_seconds // 60
            ext_note_parts.append(f"extended {ext_min}min after diary end")

        confirmed_by = []
        if choi_nw_set and any(i in choi_nw_set for i in range(ext_start, ext_end + 1)):
            confirmed_by.append("Choi")
        if sensor_nw_ranges and any(
            si <= ext_start and ext_end <= ei for si, ei in sensor_nw_ranges
        ):
            confirmed_by.append("sensor")

        note = f"Nonwear {diary_idx}: diary {diary_start_dt.strftime('%H:%M')}-{diary_end_dt.strftime('%H:%M')}"
        if ext_note_parts:
            note += f" ({', '.join(ext_note_parts)})"
        if confirmed_by:
            note += f" [confirmed by {', '.join(confirmed_by)}]"
        notes.append(note)

        markers.append({
            "start_timestamp": nw_start_ts,
            "end_timestamp": nw_end_ts,
            "marker_index": len(markers) + 1,
        })

    if not markers:
        notes.append("No valid nonwear periods detected")

    return NonwearPlacementResult(nonwear_markers=markers, notes=notes)


def _find_nearest_epoch(timestamps: list[float], target_ts: float) -> int | None:
    """Find index of epoch nearest to target timestamp."""
    if not timestamps:
        return None
    best_idx = 0
    best_diff = abs(timestamps[0] - target_ts)
    for i, ts in enumerate(timestamps):
        diff = abs(ts - target_ts)
        if diff < best_diff:
            best_diff = diff
            best_idx = i
    return best_idx


def _find_nearest_epoch_dt(
    epoch_times: list[datetime], target: datetime
) -> int | None:
    """Find index of epoch nearest to target datetime."""
    if not epoch_times:
        return None
    best_idx = 0
    best_diff = abs((epoch_times[0] - target).total_seconds())
    for i, et in enumerate(epoch_times):
        diff = abs((et - target).total_seconds())
        if diff < best_diff:
            best_diff = diff
            best_idx = i
    return best_idx


def _epoch_in_nonwear_signal(
    idx: int,
    choi_set: set[int],
    sensor_ranges: list[tuple[int, int]],
) -> bool:
    """Check if epoch index falls within any Choi or sensor nonwear region."""
    if idx in choi_set:
        return True
    return any(si <= idx <= ei for si, ei in sensor_ranges)
```

**Step 2: Verify it doesn't break existing code**

Run: `cd /opt/sleep-scoring-web/monorepo/apps/sleep-scoring-demo && python -c "from sleep_scoring_web.services.marker_placement import place_nonwear_markers; print('OK')"`
Expected: OK

---

### Task 2: Backend — Auto-nonwear endpoint

**Files:**
- Modify: `sleep_scoring_web/api/markers.py`

**Step 1: Add AutoNonwearResponse model**

After `AutoScoreResponse` (around line 2467), add:

```python
class AutoNonwearResponse(BaseModel):
    """Response with suggested nonwear marker placements."""
    nonwear_markers: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
```

**Step 2: Add the endpoint**

After the `auto_score_markers` endpoint (after line 2960), add:

```python
@router.post("/{file_id}/{analysis_date}/auto-nonwear")
async def auto_nonwear_markers(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    threshold: Annotated[int, Query(description="Max activity count to consider as zero", ge=0, le=1000)] = 0,
) -> AutoNonwearResponse:
    """
    Automatically detect nonwear periods using diary anchors and zero-activity detection.
    Returns suggestions for user to accept/reject.
    """
    await require_file_access(db, username, file_id)

    from sleep_scoring_web.db.models import DiaryEntry as DiaryEntryModel
    from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
    from sleep_scoring_web.services.choi_helpers import extract_choi_input, get_choi_column
    from sleep_scoring_web.services.marker_placement import place_nonwear_markers

    # Load file
    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = file_result.scalar_one_or_none()
    if not file or is_excluded_file_obj(file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Load activity data (noon-to-noon window)
    start_dt = datetime.combine(analysis_date, datetime.min.time()) + timedelta(hours=12)
    end_dt = start_dt + timedelta(hours=24)

    data_result = await db.execute(
        select(RawActivityData)
        .where(
            and_(
                RawActivityData.file_id == file_id,
                RawActivityData.timestamp >= start_dt,
                RawActivityData.timestamp < end_dt,
            )
        )
        .order_by(RawActivityData.timestamp)
    )
    rows = data_result.scalars().all()
    if not rows:
        return AutoNonwearResponse(notes=["No activity data found for this date"])

    timestamps = [naive_to_unix(row.timestamp) for row in rows]
    activity_counts = [float(row.axis_y or 0) for row in rows]

    # Run Choi nonwear
    choi_column = await get_choi_column(db, username)
    choi = ChoiAlgorithm()
    nonwear_results = choi.detect_mask(extract_choi_input(rows, choi_column))

    # Load diary
    diary_result = await db.execute(
        select(DiaryEntryModel).where(
            and_(
                DiaryEntryModel.file_id == file_id,
                DiaryEntryModel.analysis_date == analysis_date,
            )
        )
    )
    diary = diary_result.scalar_one_or_none()
    diary_nonwear: list[tuple[str | None, str | None]] = []
    if diary:
        for i in range(1, 4):
            nw_start = getattr(diary, f"nonwear_{i}_start", None)
            nw_end = getattr(diary, f"nonwear_{i}_end", None)
            if nw_start and nw_end:
                diary_nonwear.append((nw_start, nw_end))

    if not diary_nonwear:
        return AutoNonwearResponse(notes=["No diary nonwear periods found for this date"])

    # Load sensor nonwear periods
    sensor_nw_result = await db.execute(
        select(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.marker_category == "nonwear",
                Marker.marker_type == "sensor",
            )
        )
    )
    sensor_nw_markers = sensor_nw_result.scalars().all()
    sensor_periods = [
        (m.start_timestamp, m.end_timestamp)
        for m in sensor_nw_markers
        if m.end_timestamp is not None
    ]

    # Load existing sleep markers for this user+date (to avoid overlap)
    from sleep_scoring_web.db.models import UserAnnotation
    ann_result = await db.execute(
        select(UserAnnotation).where(
            and_(
                UserAnnotation.file_id == file_id,
                UserAnnotation.analysis_date == analysis_date,
                UserAnnotation.username == username,
            )
        )
    )
    annotation = ann_result.scalar_one_or_none()
    existing_sleep: list[tuple[float, float]] = []
    if annotation and annotation.sleep_markers_json:
        for sm in annotation.sleep_markers_json:
            onset = sm.get("onset_timestamp")
            offset = sm.get("offset_timestamp")
            if onset is not None and offset is not None:
                existing_sleep.append((float(onset), float(offset)))

    # Also check saved markers in Marker table
    saved_sleep_result = await db.execute(
        select(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.analysis_date == analysis_date,
                Marker.marker_category == "sleep",
                Marker.created_by == username,
            )
        )
    )
    for sm in saved_sleep_result.scalars().all():
        if sm.start_timestamp and sm.end_timestamp:
            existing_sleep.append((sm.start_timestamp, sm.end_timestamp))

    result = place_nonwear_markers(
        timestamps=timestamps,
        activity_counts=activity_counts,
        diary_nonwear=diary_nonwear,
        choi_nonwear=nonwear_results,
        sensor_nonwear_periods=sensor_periods,
        existing_sleep_markers=existing_sleep,
        analysis_date=analysis_date.isoformat(),
        threshold=threshold,
    )

    return AutoNonwearResponse(
        nonwear_markers=result.nonwear_markers,
        notes=result.notes,
    )
```

**Step 3: Verify backend starts**

Run: `cd /opt/sleep-scoring-web/monorepo/apps/sleep-scoring-demo/docker && docker compose -f docker-compose.local.yml up -d --build backend && docker compose -f docker-compose.local.yml logs --tail=20 backend`
Expected: Backend starts without import errors

---

### Task 3: Frontend — Add `autoNonwearOnNavigate` to store

**Files:**
- Modify: `frontend/src/store/index.ts`
- Modify: `frontend/src/lib/user-state.ts`

**Step 1: Add to PreferencesState interface**

In `PreferencesState` (around line 119-126), add:
```typescript
  autoNonwearOnNavigate: boolean;
```

**Step 2: Add action declaration**

In `SleepScoringState`, add alongside existing preference setters:
```typescript
  setAutoNonwearOnNavigate: (value: boolean) => void;
```

**Step 3: Add initial state + implementation**

In the store creator, add initial value:
```typescript
  autoNonwearOnNavigate: false,
```

Add action:
```typescript
  setAutoNonwearOnNavigate: (value) => set({ autoNonwearOnNavigate: value }),
```

**Step 4: Add to partialize**

In the `partialize` function, add:
```typescript
  autoNonwearOnNavigate: state.autoNonwearOnNavigate,
```

**Step 5: Add to usePreferences selector hook (if exists) or expose it**

Check if there's a `usePreferences` hook — if not, ensure it's accessible via `useSleepScoringStore` directly.

**Step 6: Add to user-state.ts**

Add `"autoNonwearOnNavigate"` to the `PERSISTED_KEYS` array.

---

### Task 4: Frontend — Rename "Auto-Score" → "Auto Sleep", add "Auto Nonwear" button + mutation

**Files:**
- Modify: `frontend/src/pages/scoring.tsx`

**Step 1: Add auto-nonwear mutation**

After the existing `autoScoreMutation` (around line 211), add:

```typescript
  // Auto-nonwear mutation
  const [autoNonwearResult, setAutoNonwearResult] = useState<{
    nonwear_markers: Array<{ start_timestamp: number; end_timestamp: number; marker_index: number }>;
    notes: string[];
  } | null>(null);

  const autoNonwearMutation = useMutation({
    mutationFn: async () => {
      if (!currentFileId || !currentDate) throw new Error("No file/date selected");
      const params = new URLSearchParams({ threshold: "0" });
      return fetchWithAuth<{
        nonwear_markers: Array<{ start_timestamp: number; end_timestamp: number; marker_index: number }>;
        notes: string[];
      }>(`${getApiBase()}/markers/${currentFileId}/${currentDate}/auto-nonwear?${params}`, {
        method: "POST",
      });
    },
    onSuccess: (data) => {
      setAutoNonwearResult(data);
    },
    onError: (error: Error) => {
      alert({ title: "Auto-Nonwear Failed", description: error.message });
    },
  });
```

**Step 2: Add apply callback**

```typescript
  const applyAutoNonwear = useCallback(() => {
    if (!autoNonwearResult || autoNonwearResult.nonwear_markers.length === 0) return;
    if (nonwearMarkers.length > 0) return; // Don't overwrite existing
    const newMarkers = autoNonwearResult.nonwear_markers.map((m, i) => ({
      startTimestamp: m.start_timestamp * 1000,
      endTimestamp: m.end_timestamp * 1000,
      markerIndex: i + 1,
    }));
    setNonwearMarkers(newMarkers);
    setAutoNonwearResult(null);
  }, [autoNonwearResult, nonwearMarkers.length, setNonwearMarkers]);
```

**Step 3: Rename existing button and add new button**

Find the "Auto-Score" button (around line 645-658). Change its label:

Replace:
```tsx
            Auto-Score
```
With:
```tsx
            Auto Sleep
```

After the existing auto-score checkbox group (around line 668), add a separator and the new button + checkbox:

```tsx
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs px-2 shrink-0"
            onClick={() => { autoNonwearMutation.mutate(); }}
            disabled={!currentFileId || !currentDate || autoNonwearMutation.isPending || hasNoDiary}
            title={hasNoDiary ? "Cannot auto-nonwear: no diary data" : "Automatically detect nonwear periods from diary"}
          >
            {autoNonwearMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
            ) : (
              <Wand2 className="h-3.5 w-3.5 mr-1" />
            )}
            Auto Nonwear
          </Button>
          <div className="flex items-center gap-1 shrink-0">
            <Checkbox
              checked={autoNonwearOnNavigate}
              onCheckedChange={(checked) => setAutoNonwearOnNavigate(!!checked)}
            />
            <Label className="text-[11px] cursor-pointer" onClick={() => setAutoNonwearOnNavigate(!autoNonwearOnNavigate)}>
              Auto
            </Label>
          </div>
```

**Step 4: Destructure new store values**

Ensure `autoNonwearOnNavigate`, `setAutoNonwearOnNavigate`, `nonwearMarkers`, and `setNonwearMarkers` are destructured from the store hooks.

---

### Task 5: Frontend — Auto-nonwear review dialog

**Files:**
- Modify: `frontend/src/pages/scoring.tsx`

**Step 1: Add the review dialog**

Before `{confirmDialog}` near the end of the JSX (around line 1232), add:

```tsx
      {/* Auto-Nonwear Confirmation Dialog */}
      {autoNonwearResult && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setAutoNonwearResult(null)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              if (autoNonwearResult.nonwear_markers.length > 0 && nonwearMarkers.length === 0) applyAutoNonwear();
            } else if (e.key === "Escape") {
              setAutoNonwearResult(null);
            }
          }}
          tabIndex={-1}
          ref={(el) => el?.focus()}
        >
          <div className="bg-background border rounded-lg shadow-xl p-6 max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
              <Wand2 className="h-5 w-5" />
              Review Auto-Nonwear Results
            </h3>
            <div className="space-y-2 mb-4">
              {autoNonwearResult.notes.map((note, i) => (
                <p key={i} className="text-sm text-muted-foreground">{note}</p>
              ))}
              {autoNonwearResult.nonwear_markers.length === 0 && (
                <p className="text-sm text-amber-600">No nonwear periods detected.</p>
              )}
              {nonwearMarkers.length > 0 && (
                <p className="text-sm text-amber-600 font-medium">
                  Nonwear markers already exist. Clear existing markers first.
                </p>
              )}
            </div>
            {autoNonwearResult.nonwear_markers.length > 0 && (
              <div className="mb-4 border rounded p-2 max-h-36 overflow-auto">
                {autoNonwearResult.nonwear_markers.map((m) => (
                  <div key={m.marker_index} className="text-xs flex items-center justify-between py-0.5">
                    <span className="font-medium">Nonwear {m.marker_index}</span>
                    <span className="tabular-nums">
                      {formatTime(m.start_timestamp * 1000)} - {formatTime(m.end_timestamp * 1000)}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div className="text-sm mb-4">
              <span className="font-medium">{autoNonwearResult.nonwear_markers.length}</span> nonwear period(s)
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setAutoNonwearResult(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={applyAutoNonwear}
                disabled={autoNonwearResult.nonwear_markers.length === 0 || nonwearMarkers.length > 0}
              >
                Apply To My Markers
              </Button>
            </div>
          </div>
        </div>
      )}
```

---

### Task 6: Frontend — Auto-nonwear on navigate

**Files:**
- Modify: `frontend/src/pages/scoring.tsx`

**Step 1: Add auto-nonwear on navigate effect**

After the existing auto-score on navigate effect (around line 399), add:

```typescript
  // Auto-nonwear on date navigate (when toggle is on and no existing nonwear markers)
  const autoNonwearMutationRef = useRef(autoNonwearMutation);
  autoNonwearMutationRef.current = autoNonwearMutation;
  const autoNonwearKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (!autoNonwearOnNavigate || !currentFileId || !currentDate || hasNoDiary) return;
    if (nonwearMarkers.length > 0 || autoNonwearMutation.isPending) return;
    const key = `nw-${currentFileId}-${currentDate}`;
    if (autoNonwearKeyRef.current === key) return;
    const timer = setTimeout(() => {
      const state = useSleepScoringStore.getState();
      if (state.nonwearMarkers.length > 0) return;
      if (autoNonwearMutationRef.current.isPending) return;
      autoNonwearKeyRef.current = key;
      autoNonwearMutationRef.current.mutate();
    }, 800); // Slightly longer delay than sleep auto-score to avoid race
    return () => clearTimeout(timer);
  }, [currentFileId, currentDate, autoNonwearOnNavigate, hasNoDiary, nonwearMarkers.length, autoNonwearMutation.isPending]);
```

---

### Task 7: Build and verify

**Step 1: Run typecheck**

```bash
cd /opt/sleep-scoring-web/monorepo/apps/sleep-scoring-demo/frontend && bun run typecheck
```
Expected: No errors

**Step 2: Rebuild containers**

```bash
cd /opt/sleep-scoring-web/monorepo/apps/sleep-scoring-demo/docker
docker compose -f docker-compose.local.yml up -d --build backend frontend
```

**Step 3: Verify containers are healthy**

```bash
docker compose -f docker-compose.local.yml ps
docker compose -f docker-compose.local.yml logs --tail=20 backend
docker compose -f docker-compose.local.yml logs --tail=20 frontend
```

**Step 4: Manual verification checklist**

- [ ] "Auto-Score" button now reads "Auto Sleep"
- [ ] "Auto Nonwear" button appears next to it with its own "Auto" checkbox
- [ ] Clicking "Auto Nonwear" on a date with diary nonwear shows review dialog with detected periods
- [ ] Review dialog shows notes explaining diary window, extensions, and signal confirmations
- [ ] "Apply To My Markers" places nonwear markers in the store (visible in plot)
- [ ] Nonwear markers don't overlap with existing sleep markers
- [ ] Periods with < 10 min of zero activity are skipped with explanation
- [ ] "Auto" checkbox for nonwear triggers auto-detection on date navigation
- [ ] Dates without diary nonwear show "No diary nonwear periods found" note
- [ ] Both auto-score buttons are disabled when no diary data exists
