"""
Automated marker placement service.

Diary-centric approach: uses diary onset/offset as reference points,
finds the closest valid sleep boundaries that satisfy the 3-epoch onset
and 5-minute offset rules, and creates the largest inclusive sleep period.

Rules (from CLAUDE.md):
- Onset: First epoch of 3+ consecutive sleep epochs nearest diary onset
- Offset: End of 5+ consecutive minutes of sleep nearest diary wake
- Rule 1: Include wake activity in the middle of the sleep period
- Rule 8: If onset is BEFORE in-bed time, use in-bed time instead
- Diary tolerance: 15 minutes for choosing between candidates
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta, timezone
from typing import Any

from sleep_scoring_web.schemas.enums import MarkerCategory, MarkerType

# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class PlacementConfig:
    """Configuration for marker placement rules."""

    onset_min_consecutive_sleep: int = 3
    offset_min_consecutive_minutes: int = 5
    diary_tolerance_minutes: int = 15
    nap_min_consecutive_epochs: int = 10
    epoch_length_seconds: int = 60
    max_forward_offset_epochs: int = 60
    nap_max_search_epochs: int = 60
    enable_rule_8_clamping: bool = True


# =============================================================================
# Data Models
# =============================================================================


@dataclass(frozen=True)
class EpochData:
    """Features for a single epoch."""

    index: int
    timestamp: datetime
    sleep_score: int  # 0=wake, 1=sleep
    activity: float
    is_choi_nonwear: bool
    is_sensor_nonwear: bool = False


@dataclass
class DiaryPeriod:
    """A diary-reported period (sleep, nap, or nonwear)."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    period_type: str = MarkerCategory.SLEEP


@dataclass
class DiaryDay:
    """Diary data for a single day."""

    in_bed_time: datetime | None = None
    out_bed_time: datetime | None = None
    sleep_onset: datetime | None = None
    wake_time: datetime | None = None
    nap_periods: list[DiaryPeriod] = field(default_factory=list)
    nonwear_periods: list[DiaryPeriod] = field(default_factory=list)


@dataclass
class PlacementResult:
    """Result of automated marker placement."""

    sleep_markers: list[dict[str, Any]] = field(default_factory=list)
    nap_markers: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# =============================================================================
# Core Diary-Centric Placement
# =============================================================================


def _find_valid_onset_near(
    epochs: list[EpochData],
    target_ts: datetime,
    min_consecutive: int,
    before_tolerance_epochs: int = 15,
) -> int | None:
    """
    Find the nearest valid onset point to a target timestamp.

    A valid onset is the start of min_consecutive (3) or more consecutive
    sleep epochs. Searches outward from target in both directions.

    before_tolerance_epochs: how many extra epochs a before-diary onset may be
    farther than the nearest after-diary onset and still be preferred.  Defaults
    to 15 (= diary_tolerance_minutes).  Prevents a distant before-onset from
    winning over a much closer after-onset.

    Returns the epoch index, or None if no valid onset found.
    """
    # Find epoch index closest to target timestamp
    center = _nearest_epoch_index(epochs, target_ts)
    if center is None:
        return None

    # Precompute all valid onset positions (start of 3+ consecutive sleep)
    # Skip runs that start in a Choi-confirmed nonwear epoch.
    valid_onsets: list[int] = []
    i = 0
    while i < len(epochs):
        if epochs[i].sleep_score == 1:
            run_start = i
            while i < len(epochs) and epochs[i].sleep_score == 1:
                i += 1
            run_len = i - run_start
            if run_len >= min_consecutive and not (epochs[run_start].is_choi_nonwear and epochs[run_start].is_sensor_nonwear):
                valid_onsets.append(run_start)
        else:
            i += 1

    if not valid_onsets:
        return None

    # Prefer onset AT or BEFORE diary time (more inclusive — person may have
    # fallen asleep slightly earlier than reported).  But only when the nearest
    # before-onset is within 2× the diary tolerance of the nearest after-onset;
    # a candidate 4 hours before diary should never beat one 12 minutes after.
    before = [idx for idx in valid_onsets if idx <= center]
    after  = [idx for idx in valid_onsets if idx > center]

    def _nearest(pool: list[int]) -> tuple[int | None, float]:
        best: int | None = None
        best_dist = float("inf")
        for idx in pool:
            dist = abs(idx - center)
            if dist < best_dist or (dist == best_dist and best is not None and idx < best):
                best_dist = dist
                best = idx
        return best, best_dist

    best_before, dist_before = _nearest(before)
    best_after,  dist_after  = _nearest(after)

    if best_before is None:
        return best_after
    if best_after is None:
        return best_before

    # Use before-candidate only when it is not more than before_tolerance_epochs
    # farther than the after-candidate.
    if dist_before <= dist_after + before_tolerance_epochs:
        return best_before
    return best_after


def _find_valid_offset_near(
    epochs: list[EpochData],
    target_ts: datetime,
    min_consecutive_minutes: int,
    epoch_length_seconds: int,
) -> int | None:
    """
    Find the nearest valid offset point to a target timestamp.

    A valid offset is the end of a sleep run with min_consecutive_minutes (5)
    or more minutes of consecutive sleep. Searches outward from target.

    Returns the epoch index, or None if no valid offset found.
    """
    center = _nearest_epoch_index(epochs, target_ts)
    if center is None:
        return None

    min_epochs = max(1, min_consecutive_minutes * 60 // epoch_length_seconds)

    # Precompute all valid offset positions (end of 5+ minute sleep runs)
    valid_offsets: list[int] = []
    i = 0
    while i < len(epochs):
        if epochs[i].sleep_score == 1:
            run_start = i
            while i < len(epochs) and epochs[i].sleep_score == 1:
                i += 1
            run_end = i - 1
            run_len = i - run_start
            if run_len >= min_epochs:
                valid_offsets.append(run_end)
        else:
            i += 1

    if not valid_offsets:
        return None

    # Offset should be AT or AFTER the diary time (more inclusive).
    # Only fall back to before-target candidates if none exist after.
    after = [idx for idx in valid_offsets if idx >= center]
    before = [idx for idx in valid_offsets if idx < center]

    pool = after or before
    best: int | None = None
    best_dist = float("inf")
    for idx in pool:
        dist = abs(idx - center)
        if dist < best_dist:
            best_dist = dist
            best = idx
        elif dist == best_dist and best is not None and idx > best:
            best = idx

    return best


def _find_valid_offset_near_bounded(
    epochs: list[EpochData],
    target_ts: datetime,
    min_consecutive_minutes: int,
    epoch_length_seconds: int,
    max_forward_epochs: int | None = None,
    diary_tolerance_epochs: int | None = None,
) -> int | None:
    """
    Find the nearest valid offset near a target, with an optional bounded forward look.

    Like _find_valid_offset_near but optionally limits how far PAST the target
    the offset can land.  Offsets are ALWAYS placed at actual sleep→wake
    transitions (the last sleep epoch before wake), never in the middle of a
    continuous sleep run.  Runs whose natural end exceeds the forward bound are
    skipped (when max_forward_epochs is set).

    max_forward_epochs=None means no forward cap (offset may land anywhere past
    the target).  Pass an integer to cap how far past the target is allowed —
    useful for nap placement to prevent grabbing the main sleep endpoint.

    Returns the epoch index, or None if no valid offset found.
    """
    center = _nearest_epoch_index(epochs, target_ts)
    if center is None:
        return None

    min_epochs = max(1, min_consecutive_minutes * 60 // epoch_length_seconds)
    max_idx = (center + max_forward_epochs) if max_forward_epochs is not None else len(epochs) - 1

    # Precompute all valid offset positions — only at REAL run ends (sleep→wake)
    # Skip runs that end in a Choi-confirmed nonwear epoch.
    valid_offsets: list[int] = []
    i = 0
    while i < len(epochs):
        if epochs[i].sleep_score == 1:
            run_start = i
            while i < len(epochs) and epochs[i].sleep_score == 1:
                i += 1
            run_end = i - 1  # Last sleep epoch — always a real transition
            run_len = i - run_start
            if run_len >= min_epochs and run_end <= max_idx and not (epochs[run_end].is_choi_nonwear and epochs[run_end].is_sensor_nonwear):
                valid_offsets.append(run_end)
        else:
            i += 1

    if not valid_offsets:
        return None

    # With a diary: apply tolerance band — prefer the latest offset within
    # diary_tolerance_epochs of the nearest candidate (stays close to diary wake).
    # Without a diary: just pick the most inclusive (latest) offset.
    if diary_tolerance_epochs is not None:
        min_dist = min(abs(idx - center) for idx in valid_offsets)
        band = [idx for idx in valid_offsets if abs(idx - center) <= min_dist + diary_tolerance_epochs]
        return max(band)
    return max(valid_offsets)


def _nearest_epoch_index(epochs: list[EpochData], target: datetime) -> int | None:
    """Binary search for the epoch closest to target timestamp."""
    if not epochs:
        return None
    lo, hi = 0, len(epochs) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if epochs[mid].timestamp < target:
            lo = mid + 1
        else:
            hi = mid
    # Check lo and lo-1 for closest
    if lo > 0:
        d_lo = abs((epochs[lo].timestamp - target).total_seconds())
        d_prev = abs((epochs[lo - 1].timestamp - target).total_seconds())
        if d_prev < d_lo:
            return lo - 1
    return lo


def place_main_sleep(
    epochs: list[EpochData],
    diary: DiaryDay,
    config: PlacementConfig,
    diary_tolerance_epochs: int | None = None,
    onset_before_tolerance_epochs: int | None = None,
) -> tuple[int, int] | None:
    """
    Place main sleep period using diary onset/offset as reference.

    Strategy:
    1. Find nearest valid onset to diary sleep_onset (N+ consecutive sleep)
    2. Find nearest valid offset to diary wake_time (M+ consecutive sleep minutes)
       within a bounded search window (60 epochs / 1 hour past diary wake max).
       The offset search CAN look forward past diary wake, but not more than
       60 wake epochs past it — prevents offsets hours past reported wake.
    3. Onset → offset is the full inclusive period (Rule 1: include wake gaps)
    4. Rule 8: if onset is before in-bed time, use in-bed time

    Returns (onset_idx, offset_idx) or None.
    """
    if not diary.sleep_onset or not diary.wake_time:
        return None

    onset_idx = _find_valid_onset_near(
        epochs,
        diary.sleep_onset,
        config.onset_min_consecutive_sleep,
        before_tolerance_epochs=onset_before_tolerance_epochs if onset_before_tolerance_epochs is not None else config.diary_tolerance_minutes,
    )

    # Bounded offset search: look within a window around diary wake.
    # Allow looking up to 60 epochs (1 hour) past wake — but no further.
    # This prevents offsets landing hours past diary wake when there's a
    # long continuous sleep run, while still allowing reasonable forward look.
    offset_idx = _find_valid_offset_near_bounded(
        epochs,
        diary.wake_time,
        config.offset_min_consecutive_minutes,
        config.epoch_length_seconds,
        max_forward_epochs=None,  # No forward cap for main sleep
        diary_tolerance_epochs=diary_tolerance_epochs,
    )

    if onset_idx is None or offset_idx is None:
        return None
    if onset_idx >= offset_idx:
        return None

    # Rule 8: if DIARY onset (lights_out) is before DIARY in-bed time — a data-entry
    # inconsistency where someone reported falling asleep before getting into bed —
    # use in-bed time as the placement reference instead of the diary onset.
    # This compares diary times only; the scored onset position is irrelevant here.
    if (
        config.enable_rule_8_clamping
        and diary.in_bed_time
        and diary.sleep_onset
        and diary.sleep_onset < diary.in_bed_time
    ):
        clamped = _find_valid_onset_at_or_after(epochs, diary.in_bed_time, config.onset_min_consecutive_sleep)
        if clamped is not None and clamped < offset_idx:
            onset_idx = clamped

    return (onset_idx, offset_idx)


def _find_valid_onset_at_or_after(
    epochs: list[EpochData],
    target: datetime,
    min_consecutive: int,
) -> int | None:
    """
    Find the first valid onset at or after a target time.

    Only returns onsets at real W→S boundaries (the first S after a W or
    start of data).  If the target lands in the middle of a sleep run,
    that run is skipped — its real start is before the target, so it
    cannot be used.
    """
    start_idx = _nearest_epoch_index(epochs, target)
    if start_idx is None:
        return None

    i = start_idx

    # If we landed in the middle of a sleep run, skip past it.
    # A mid-run position has S at i AND S at i-1.
    if i > 0 and epochs[i].sleep_score == 1 and epochs[i - 1].sleep_score == 1:
        while i < len(epochs) and epochs[i].sleep_score == 1:
            i += 1

    # Now search forward for the next valid W→S onset
    while i < len(epochs):
        if epochs[i].sleep_score == 1:
            run_start = i
            while i < len(epochs) and epochs[i].sleep_score == 1:
                i += 1
            if (i - run_start) >= min_consecutive:
                return run_start
        else:
            i += 1
    return None


def _find_valid_offset_at_or_before(
    epochs: list[EpochData],
    max_idx: int,
    min_consecutive_minutes: int,
    epoch_length_seconds: int,
    min_idx: int = 0,
) -> int | None:
    """
    Find the nearest valid offset at or before max_idx.

    Scans all sleep runs in [min_idx, max_idx] and returns the end of the
    run whose end is closest to (but not after) max_idx, provided the run
    has at least min_consecutive_minutes of consecutive sleep.

    Returns the epoch index, or None if no valid offset found.
    """
    min_epochs = max(1, min_consecutive_minutes * 60 // epoch_length_seconds)

    best: int | None = None
    i = min_idx
    while i <= max_idx:
        if epochs[i].sleep_score == 1:
            run_start = i
            while i < len(epochs) and epochs[i].sleep_score == 1:
                i += 1
            run_end = i - 1  # Last sleep epoch — real S→W transition
            run_len = i - run_start
            # Only accept runs whose NATURAL end is at or before max_idx.
            # Never cap mid-run — offsets must be at real transitions.
            if run_len >= min_epochs and run_end <= max_idx:
                if best is None or run_end > best:
                    best = run_end
        else:
            i += 1

    return best


def _find_valid_onset_near_bounded(
    epochs: list[EpochData],
    target_ts: datetime,
    min_consecutive: int,
    max_distance_epochs: int = 60,
) -> int | None:
    """
    Find the nearest valid onset near a target, bounded by max distance.

    Like _find_valid_onset_near but only considers onsets within
    max_distance_epochs of the target. Prevents nap onsets from landing
    hours away from the diary time.
    """
    center = _nearest_epoch_index(epochs, target_ts)
    if center is None:
        return None

    lo = max(0, center - max_distance_epochs)
    hi = min(len(epochs) - 1, center + max_distance_epochs)

    valid_onsets: list[int] = []
    i = 0
    while i < len(epochs):
        if epochs[i].sleep_score == 1:
            run_start = i
            while i < len(epochs) and epochs[i].sleep_score == 1:
                i += 1
            run_len = i - run_start
            if run_len >= min_consecutive and lo <= run_start <= hi and not (epochs[run_start].is_choi_nonwear and epochs[run_start].is_sensor_nonwear):
                valid_onsets.append(run_start)
        else:
            i += 1

    if not valid_onsets:
        return None

    best: int | None = None
    best_dist = float("inf")
    for idx in valid_onsets:
        dist = abs(idx - center)
        if dist < best_dist:
            best_dist = dist
            best = idx
    return best


def place_naps(
    epochs: list[EpochData],
    diary: DiaryDay,
    main_onset: int | None,
    main_offset: int | None,
    config: PlacementConfig,
) -> list[tuple[int, int]]:
    """
    Place nap markers from diary nap periods.

    For each diary nap period, find the nearest valid sleep run within
    a bounded window (60 epochs / 1 hour) of the diary times.
    Naps must not overlap with main sleep.
    """
    naps: list[tuple[int, int]] = []
    min_epochs = config.nap_min_consecutive_epochs
    max_search_epochs = config.nap_max_search_epochs

    for nap_period in diary.nap_periods:
        if not nap_period.start_time or not nap_period.end_time:
            continue

        onset_idx = _find_valid_onset_near_bounded(
            epochs,
            nap_period.start_time,
            min_consecutive=config.onset_min_consecutive_sleep,
            max_distance_epochs=len(epochs),  # unbounded — diary is anchor
        )
        offset_idx = _find_valid_offset_near_bounded(
            epochs,
            nap_period.end_time,
            min_consecutive_minutes=config.offset_min_consecutive_minutes,
            epoch_length_seconds=config.epoch_length_seconds,
            max_forward_epochs=max_search_epochs,
        )

        if onset_idx is None or offset_idx is None:
            continue
        if onset_idx >= offset_idx:
            continue
        if (offset_idx - onset_idx + 1) < min_epochs:
            continue

        # Must not overlap with main sleep
        if main_onset is not None and main_offset is not None:
            if onset_idx <= main_offset and offset_idx >= main_onset:
                continue

        naps.append((onset_idx, offset_idx))

    return naps


def place_without_diary(
    epochs: list[EpochData],
    config: PlacementConfig,
) -> tuple[int, int] | None:
    """
    Fallback: find longest sleep period when no diary data.

    Finds the longest contiguous sleep block (may include brief wake gaps
    if bounded by substantial sleep runs).
    """
    # Find all sleep runs
    sleep_runs: list[tuple[int, int, int]] = []  # (start, end, length)
    i = 0
    while i < len(epochs):
        if epochs[i].sleep_score == 1:
            start = i
            while i < len(epochs) and epochs[i].sleep_score == 1:
                i += 1
            length = i - start
            sleep_runs.append((start, i - 1, length))
        else:
            i += 1

    if not sleep_runs:
        return None

    # Find pairs with valid onset (3+) and offset (5min+)
    min_offset_epochs = max(1, config.offset_min_consecutive_minutes * 60 // config.epoch_length_seconds)

    best: tuple[int, int] | None = None
    best_duration = 0

    for onset_run in sleep_runs:
        if onset_run[2] < config.onset_min_consecutive_sleep:
            continue
        for offset_run in sleep_runs:
            if offset_run[2] < min_offset_epochs:
                continue
            if offset_run[1] < onset_run[0]:
                continue
            duration = offset_run[1] - onset_run[0] + 1
            if duration > best_duration:
                best_duration = duration
                best = (onset_run[0], offset_run[1])

    return best


# =============================================================================
# AM/PM Correction
# =============================================================================


def _flip_ampm(time_str: str) -> str | None:
    """Flip AM↔PM in a 12-hour time string. Returns None for 24h format."""
    s = time_str.strip()
    upper = s.upper()
    if "PM" in upper:
        idx = upper.index("PM")
        return s[:idx] + "AM" + s[idx + 2 :]
    if "AM" in upper:
        idx = upper.index("AM")
        return s[:idx] + "PM" + s[idx + 2 :]
    return None


def _diary_times_plausible(
    onset_dt: datetime | None,
    wake_dt: datetime | None,
    data_start: datetime,
    data_end: datetime,
) -> bool:
    """
    Check if diary onset/wake times are physiologically plausible.

    Checks:
    1. Both must exist
    2. onset < wake
    3. Sleep duration between 2 and 18 hours
    4. Both within the data window (±2 hours margin)
    """
    if not onset_dt or not wake_dt:
        return False
    if wake_dt <= onset_dt:
        return False
    gap_hours = (wake_dt - onset_dt).total_seconds() / 3600
    if gap_hours < 2 or gap_hours > 18:
        return False
    margin = timedelta(hours=2)
    if onset_dt < data_start - margin or onset_dt > data_end + margin:
        return False
    if wake_dt < data_start - margin or wake_dt > data_end + margin:
        return False
    return True


def _try_ampm_corrections(
    onset_str: str | None,
    wake_str: str | None,
    bed_str: str | None,
    base_date: Any,
    data_start: datetime,
    data_end: datetime,
) -> tuple[datetime | None, datetime | None, datetime | None, list[str]]:
    """
    Try AM/PM flips on diary onset/wake if original parse is implausible.

    Returns (onset_dt, wake_dt, bed_dt, correction_notes).
    """
    corrections: list[str] = []

    # Parse originals
    onset_dt = _parse_diary_time(onset_str, base_date, is_evening=True) if onset_str else None
    wake_dt = _parse_diary_time(wake_str, base_date, is_evening=False) if wake_str else None
    bed_dt = _parse_diary_time(bed_str, base_date, is_evening=True) if bed_str else None

    # Fix wake < onset by adding a day (standard overnight handling)
    if wake_dt and onset_dt and wake_dt <= onset_dt:
        wake_dt += timedelta(days=1)

    # If original parse is plausible, use it
    if _diary_times_plausible(onset_dt, wake_dt, data_start, data_end):
        return onset_dt, wake_dt, bed_dt, corrections

    # Try flip combinations in order of likelihood:
    # 1. Flip wake only (most common: "7:00 PM" should be "7:00 AM")
    # 2. Flip onset only ("10:30 AM" should be "10:30 PM")
    # 3. Flip both
    flip_attempts: list[tuple[str | None, str | None, str, str]] = []

    flipped_wake = _flip_ampm(wake_str) if wake_str else None
    flipped_onset = _flip_ampm(onset_str) if onset_str else None

    if flipped_wake:
        flip_attempts.append((onset_str, flipped_wake, "", f"wake {wake_str} → {flipped_wake}"))
    if flipped_onset:
        flip_attempts.append((flipped_onset, wake_str, f"onset {onset_str} → {flipped_onset}", ""))
    if flipped_onset and flipped_wake:
        flip_attempts.append(
            (
                flipped_onset,
                flipped_wake,
                f"onset {onset_str} → {flipped_onset}",
                f"wake {wake_str} → {flipped_wake}",
            )
        )

    for alt_onset_str, alt_wake_str, onset_note, wake_note in flip_attempts:
        alt_onset = _parse_diary_time(alt_onset_str, base_date, is_evening=True) if alt_onset_str else None
        alt_wake = _parse_diary_time(alt_wake_str, base_date, is_evening=False) if alt_wake_str else None
        if alt_wake and alt_onset and alt_wake <= alt_onset:
            alt_wake += timedelta(days=1)

        if _diary_times_plausible(alt_onset, alt_wake, data_start, data_end):
            notes: list[str] = []
            if onset_note:
                notes.append(onset_note)
            if wake_note:
                notes.append(wake_note)
            correction_msg = "Corrected diary AM/PM: " + ", ".join(notes)
            # Also flip bed_dt if onset was flipped and bed was the source
            alt_bed = bed_dt
            if onset_note and bed_str:
                flipped_bed = _flip_ampm(bed_str)
                if flipped_bed:
                    alt_bed = _parse_diary_time(flipped_bed, base_date, is_evening=True)
            return alt_onset, alt_wake, alt_bed, [correction_msg]

    # No flip worked — return originals as-is
    return onset_dt, wake_dt, bed_dt, corrections


# =============================================================================
# API Helper
# =============================================================================


def _parse_time_to_24h(time_str: str) -> tuple[int, int] | None:
    """
    Parse a time string to (hour, minute) in 24-hour format.

    Supports:
      - "23:30" (24-hour)
      - "11:30 PM" / "11:30PM" (12-hour with AM/PM)
      - "9:27 AM" / "9:27AM"
      - "12:45 AM" → 00:45
      - "12:00 PM" → 12:00
    """
    s = time_str.strip().upper()
    is_pm = "PM" in s
    is_am = "AM" in s
    s = s.replace("PM", "").replace("AM", "").strip()

    try:
        parts = s.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return None

    if is_am or is_pm:
        if h == 12:
            h = 0 if is_am else 12
        elif is_pm:
            h += 12

    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return (h, m)


def _parse_diary_time(
    time_str: str,
    base_date: Any,
    is_evening: bool = True,
) -> datetime | None:
    """
    Parse time string to datetime, handling overnight logic.

    Supports both "HH:MM" (24h) and "H:MM AM/PM" (12h) formats.

    Args:
        time_str: Time string
        base_date: Analysis date (date object)
        is_evening: If True, times < 12:00 are treated as next day (overnight)
                    If False, times < 18:00 are treated as next day (wake/end times)

    """
    parsed = _parse_time_to_24h(time_str)
    if parsed is None:
        return None
    h, m = parsed
    try:
        dt = datetime(base_date.year, base_date.month, base_date.day, h, m, tzinfo=UTC)
        if (is_evening and h < 12) or (not is_evening and h < 18):
            dt += timedelta(days=1)
        return dt
    except (ValueError, TypeError):
        return None


def _parse_nap_time(
    time_str: str,
    base_date: Any,
) -> datetime | None:
    """
    Parse a nap time string to datetime on the analysis date.

    Naps happen during the day, so no overnight day-shifting is applied.
    The time is placed on the analysis date as-is.
    """
    parsed = _parse_time_to_24h(time_str)
    if parsed is None:
        return None
    h, m = parsed
    try:
        return datetime(base_date.year, base_date.month, base_date.day, h, m, tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def run_auto_scoring(
    timestamps: list[float],
    activity_counts: list[float],
    sleep_scores: list[int],
    choi_nonwear: list[int] | None = None,
    sensor_nonwear_periods: list[tuple[float, float]] | None = None,
    diary_bed_time: str | None = None,
    diary_onset_time: str | None = None,
    diary_wake_time: str | None = None,
    diary_naps: list[tuple[str | None, str | None]] | None = None,
    diary_nonwear: list[tuple[str | None, str | None]] | None = None,
    analysis_date: str | None = None,
    epoch_length_seconds: int = 60,
    onset_min_consecutive_sleep: int = 3,
    offset_min_consecutive_minutes: int = 5,
) -> dict[str, Any]:
    """
    Diary-centric marker placement.

    1. Parse diary times into datetimes
    2. Find nearest valid onset to diary onset (N+ consecutive sleep epochs)
    3. Find nearest valid offset to diary wake (M+ consecutive minutes of sleep)
    4. Onset → offset is the full inclusive sleep period
    5. Apply Rule 8 (onset before in-bed → clamp to in-bed time)
    6. Find nap markers from diary nap periods

    onset_min_consecutive_sleep and offset_min_consecutive_minutes are
    configurable to support different detection rules (3S/5S, 5S/10S, etc.).

    Returns dict with sleep_markers, nap_markers, and notes.
    """
    config = PlacementConfig(
        epoch_length_seconds=epoch_length_seconds,
        onset_min_consecutive_sleep=onset_min_consecutive_sleep,
        offset_min_consecutive_minutes=offset_min_consecutive_minutes,
    )

    # Build epoch data
    nonwear_bools = [bool(nw) for nw in choi_nonwear] if choi_nonwear else [False] * len(timestamps)
    epochs: list[EpochData] = []
    for i, ts in enumerate(timestamps):
        sensor_nw = False
        if sensor_nonwear_periods:
            sensor_nw = any(si <= ts <= ei for si, ei in sensor_nonwear_periods)
        epochs.append(
            EpochData(
                index=i,
                timestamp=datetime.fromtimestamp(ts, tz=UTC),
                sleep_score=sleep_scores[i],
                activity=activity_counts[i],
                is_choi_nonwear=nonwear_bools[i] if i < len(nonwear_bools) else False,
                is_sensor_nonwear=sensor_nw,
            )
        )

    if not epochs:
        return {"sleep_markers": [], "nap_markers": [], "notes": ["No activity data"]}

    # Build diary
    diary: DiaryDay | None = None
    ampm_notes: list[str] = []
    if analysis_date:
        from datetime import date as date_type

        d = date_type.fromisoformat(analysis_date)

        onset_str = diary_onset_time or diary_bed_time
        data_start = epochs[0].timestamp
        data_end = epochs[-1].timestamp

        # Parse with intelligent AM/PM correction
        onset_dt, wake_dt, bed_dt, ampm_notes = _try_ampm_corrections(
            onset_str=onset_str,
            wake_str=diary_wake_time,
            bed_str=diary_bed_time,
            base_date=d,
            data_start=data_start,
            data_end=data_end,
        )

        # Parse nap periods — naps happen during the day on the analysis date.
        # No day shifting needed (unlike evening onset or next-morning wake).
        nap_periods: list[DiaryPeriod] = []
        for nap_start, nap_end in diary_naps or []:
            if nap_start and nap_end:
                ns = _parse_nap_time(nap_start, d)
                ne = _parse_nap_time(nap_end, d)
                if ns and ne and ne <= ns:
                    ne += timedelta(days=1)
                if ns and ne:
                    nap_periods.append(DiaryPeriod(start_time=ns, end_time=ne, period_type="nap"))

        # Parse nonwear periods
        nw_periods: list[DiaryPeriod] = []
        for nw_start, nw_end in diary_nonwear or []:
            if nw_start and nw_end:
                ns = _parse_diary_time(nw_start, d, is_evening=False)
                ne = _parse_diary_time(nw_end, d, is_evening=False)
                if ns and ne:
                    nw_periods.append(DiaryPeriod(start_time=ns, end_time=ne, period_type=MarkerCategory.NONWEAR))

        if onset_dt or wake_dt:
            diary = DiaryDay(
                in_bed_time=bed_dt or onset_dt,
                sleep_onset=onset_dt,
                wake_time=wake_dt,
                nap_periods=nap_periods,
                nonwear_periods=nw_periods,
            )

    notes: list[str] = ampm_notes.copy() if ampm_notes else []
    if config.onset_min_consecutive_sleep != 3 or config.offset_min_consecutive_minutes != 5:
        notes.append(f"Detection rule: {config.onset_min_consecutive_sleep}S/{config.offset_min_consecutive_minutes}S")
    sleep_markers: list[dict[str, Any]] = []
    nap_markers: list[dict[str, Any]] = []

    # Main sleep placement
    main_result: tuple[int, int] | None = None
    # True when diary was present and valid but algorithm found no scoreable period
    # (e.g. entire window is nonwear, or no sleep signal near diary times).
    # False means either no diary supplied, or sleep was found successfully.
    algorithm_ran_no_sleep = False

    if diary and diary.sleep_onset and diary.wake_time:
        main_result = place_main_sleep(epochs, diary, config)
        if main_result:
            onset_idx, offset_idx = main_result
            onset_time = epochs[onset_idx].timestamp
            offset_time = epochs[offset_idx].timestamp
            duration_min = (offset_idx - onset_idx + 1) * epoch_length_seconds / 60

            notes.append(
                f"Main sleep: {onset_time.strftime('%H:%M')} - {offset_time.strftime('%H:%M')} "
                f"({duration_min:.0f} min) — "
                f"diary onset {diary.sleep_onset.strftime('%H:%M')}, "
                f"diary wake {diary.wake_time.strftime('%H:%M')}"
            )
            sleep_markers.append(
                {
                    "onset_timestamp": onset_time.timestamp(),
                    "offset_timestamp": offset_time.timestamp(),
                    "marker_type": MarkerType.MAIN_SLEEP,
                    "marker_index": 1,
                }
            )
        else:
            notes.append(
                f"No valid sleep period found near diary times "
                f"(onset {diary.sleep_onset.strftime('%H:%M')}, "
                f"wake {diary.wake_time.strftime('%H:%M')})"
            )
            algorithm_ran_no_sleep = True
    elif diary and not diary.sleep_onset and not diary.wake_time:
        notes.append("Diary exists but no onset/wake times — auto-score requires diary times")
    else:
        # No diary at all — do NOT auto-score. Manual scoring required.
        notes.append("No diary data for this date — auto-score requires diary")

    if not main_result:
        notes.append("No main sleep period detected")

    # Nap placement from diary nap periods
    if diary and diary.nap_periods:
        main_onset = main_result[0] if main_result else None
        main_offset = main_result[1] if main_result else None

        nap_results = place_naps(epochs, diary, main_onset, main_offset, config)
        for i, (nap_on, nap_off) in enumerate(nap_results):
            nap_onset_time = epochs[nap_on].timestamp
            nap_offset_time = epochs[nap_off].timestamp
            duration_min = (nap_off - nap_on + 1) * epoch_length_seconds / 60
            notes.append(f"Nap {i + 1}: {nap_onset_time.strftime('%H:%M')} - {nap_offset_time.strftime('%H:%M')} ({duration_min:.0f} min)")
            nap_markers.append(
                {
                    "onset_timestamp": nap_onset_time.timestamp(),
                    "offset_timestamp": nap_offset_time.timestamp(),
                    "marker_type": MarkerType.NAP,
                    "marker_index": len(sleep_markers) + i + 1,
                }
            )

    return {
        "sleep_markers": sleep_markers,
        "nap_markers": nap_markers,
        "notes": notes,
        "no_sleep": algorithm_ran_no_sleep,
    }


# =============================================================================
# Nonwear Auto-Placement
# =============================================================================


def _diary_time_present(value: str | None) -> bool:
    """Return True when diary time strings are present and non-null-like."""
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized not in {"", "nan", "none", "null"}


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
    min_duration_minutes: int = 10,
    zero_activity_ratio: float = 0.65,
) -> NonwearPlacementResult:
    """
    Auto-place nonwear markers using diary anchors with zero-activity detection.

    Algorithm:
    1. Parse diary nonwear start/end as anchor windows
    2. Extend outward greedily while activity <= threshold (stops at first non-zero epoch)
    3. Skip periods < min_duration_minutes of qualifying activity
    4. Skip periods overlapping with sleep markers
    """
    if not timestamps or not activity_counts:
        return NonwearPlacementResult(nonwear_markers=[], notes=["No activity data"])

    # Parse diary nonwear periods into epoch indices
    date_obj = datetime.strptime(analysis_date, "%Y-%m-%d").replace(tzinfo=UTC)
    epoch_times = [datetime.fromtimestamp(ts, tz=UTC) for ts in timestamps]
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
        notes.append("No diary nonwear periods found for this date")

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

    for diary_start_dt, diary_end_dt, diary_idx in valid_diary_periods:
        # Find epoch indices for diary window
        start_idx = _find_nearest_epoch_dt(epoch_times, diary_start_dt)
        end_idx = _find_nearest_epoch_dt(epoch_times, diary_end_dt)
        if start_idx is None or end_idx is None:
            notes.append(f"Nonwear {diary_idx}: diary times outside data range, skipped")
            continue

        # Step 1 — Contract: if the diary boundary lands on a non-zero epoch,
        # move inward to the first zero within the diary window.  This handles
        # cases where the reported nonwear time includes a few minutes of
        # activity at the edges before the actual nonwear run begins.
        diary_start_idx = start_idx
        diary_end_idx = end_idx

        ext_start = start_idx
        while ext_start < end_idx and activity_counts[ext_start] > threshold:
            ext_start += 1

        ext_end = end_idx
        while ext_end > ext_start and activity_counts[ext_end] > threshold:
            ext_end -= 1

        # If the diary window contains no zero-activity epochs at all, skip.
        if activity_counts[ext_start] > threshold:
            notes.append(
                f"Nonwear {diary_idx}: no zero-activity epochs within diary window "
                f"{diary_start_dt.strftime('%H:%M')}-{diary_end_dt.strftime('%H:%M')}, skipped"
            )
            continue

        # Step 2 — Extend: once anchored on consecutive zeros, expand greedily
        # in both directions as far as zeros continue.  Diary alignment is the
        # primary confirmation; Choi/sensor signals are used for notes only
        # (Choi requires 90+ min and misses short zero runs at period edges).

        # Simple greedy extension (guaranteed all-zero boundary).
        simple_start = ext_start
        while simple_start > 0 and activity_counts[simple_start - 1] <= threshold:
            simple_start -= 1
        simple_end = ext_end
        while simple_end < len(timestamps) - 1 and activity_counts[simple_end + 1] <= threshold:
            simple_end += 1

        # Spike-tolerant extension: also cross isolated spikes (non-zero epoch
        # flanked by zeros) that fall within a Choi/sensor nonwear region.
        spike_start = ext_start
        while spike_start > 0:
            candidate = spike_start - 1
            if activity_counts[candidate] <= threshold:
                spike_start = candidate
            elif (
                _epoch_in_nonwear_signal(candidate, choi_nw_set, sensor_nw_ranges)
                and candidate > 0
                and activity_counts[candidate - 1] <= threshold
            ):
                spike_start = candidate
            else:
                break

        spike_end = ext_end
        while spike_end < len(timestamps) - 1:
            candidate = spike_end + 1
            if activity_counts[candidate] <= threshold:
                spike_end = candidate
            elif (
                _epoch_in_nonwear_signal(candidate, choi_nw_set, sensor_nw_ranges)
                and candidate < len(timestamps) - 1
                and activity_counts[candidate + 1] <= threshold
            ):
                spike_end = candidate
            else:
                break

        # Use spike-tolerant range only if it still satisfies the zero ratio.
        # If it doesn't, fall back to the conservative simple range rather than
        # rejecting the period entirely.
        spike_zeros = sum(1 for i in range(spike_start, spike_end + 1) if activity_counts[i] <= threshold)
        spike_total = spike_end - spike_start + 1
        if spike_total > 0 and (spike_zeros / spike_total) >= zero_activity_ratio:
            ext_start, ext_end = spike_start, spike_end
        else:
            ext_start, ext_end = simple_start, simple_end

        # Count zero-activity epochs within the entire detected range
        zero_epochs = sum(1 for i in range(ext_start, ext_end + 1) if activity_counts[i] <= threshold)
        total_epochs = ext_end - ext_start + 1

        # Require at least 80% of epochs in the range to be zero/near-zero
        if total_epochs > 0 and (zero_epochs / total_epochs) < zero_activity_ratio:
            notes.append(
                f"Nonwear {diary_idx}: diary {diary_start_dt.strftime('%H:%M')}-{diary_end_dt.strftime('%H:%M')} "
                f"has too much activity ({total_epochs - zero_epochs}/{total_epochs} epochs above threshold), skipped"
            )
            continue

        # Check minimum duration of zero-activity epochs
        if zero_epochs < min_epochs:
            notes.append(
                f"Nonwear {diary_idx}: only {zero_epochs} epochs "
                f"({zero_epochs * epoch_length_seconds // 60} min) of zero activity, "
                f"need {min_duration_minutes} min minimum, skipped"
            )
            continue

        # Check overlap with sleep markers
        nw_start_ts = timestamps[ext_start]
        nw_end_ts = timestamps[ext_end]
        overlaps_sleep = any(nw_start_ts < sm_end and nw_end_ts > sm_start for sm_start, sm_end in sleep_intervals)
        if overlaps_sleep:
            notes.append(f"Nonwear {diary_idx}: overlaps with sleep marker, skipped")
            continue

        # Build adjustment note (extension or contraction relative to diary times)
        ext_note_parts = []
        if ext_start < diary_start_idx:
            ext_min = (diary_start_idx - ext_start) * epoch_length_seconds // 60
            ext_note_parts.append(f"extended {ext_min}min before diary start")
        elif ext_start > diary_start_idx:
            ext_min = (ext_start - diary_start_idx) * epoch_length_seconds // 60
            ext_note_parts.append(f"contracted {ext_min}min after diary start")
        if ext_end > diary_end_idx:
            ext_min = (ext_end - diary_end_idx) * epoch_length_seconds // 60
            ext_note_parts.append(f"extended {ext_min}min after diary end")
        elif ext_end < diary_end_idx:
            ext_min = (diary_end_idx - ext_end) * epoch_length_seconds // 60
            ext_note_parts.append(f"contracted {ext_min}min before diary end")

        confirmed_by = []
        if choi_nw_set and any(i in choi_nw_set for i in range(ext_start, ext_end + 1)):
            confirmed_by.append("Choi")
        if sensor_nw_ranges and any(si <= ext_end and ext_start <= ei for si, ei in sensor_nw_ranges):
            confirmed_by.append("sensor")

        note = f"Nonwear {diary_idx}: diary {diary_start_dt.strftime('%H:%M')}-{diary_end_dt.strftime('%H:%M')}"
        if ext_note_parts:
            note += f" ({', '.join(ext_note_parts)})"
        if confirmed_by:
            note += f" [confirmed by {', '.join(confirmed_by)}]"
        notes.append(note)

        markers.append(
            {
                "start_timestamp": nw_start_ts,
                "end_timestamp": nw_end_ts,
                "marker_index": len(markers) + 1,
            }
        )

    # Signal-based detection (no diary needed).
    # Uses Choi+sensor when both are available (higher confidence),
    # or Choi-only when sensor data is absent.
    #
    # Algorithm: scan zero-activity runs first (greedy expansion is automatic),
    # then check whether each run contains enough signal epochs to be valid.
    # This produces one marker per contiguous zero region regardless of whether
    # the underlying signal (Choi/sensor) has internal gaps.
    if choi_nw_set:
        sensor_nw_set: set[int] = set()
        for si, ei in sensor_nw_ranges:
            sensor_nw_set.update(range(si, ei + 1))

        has_sensor = bool(sensor_nw_set)
        label = "Choi+sensor" if has_sensor else "Choi"

        def _is_signal(i: int) -> bool:
            """True when epoch has a nonwear signal (Choi alone or Choi+sensor)."""
            if not has_sensor:
                return i in choi_nw_set
            return i in choi_nw_set and i in sensor_nw_set

        placed_ts_ranges = [(m["start_timestamp"], m["end_timestamp"]) for m in markers]

        # Walk through epochs, find each contiguous zero-activity run, check signal.
        i = 0
        while i < len(timestamps):
            if activity_counts[i] > threshold:
                i += 1
                continue

            # Found start of a zero-activity run — extend to its full end.
            run_start_idx = i
            while i < len(timestamps) and activity_counts[i] <= threshold:
                i += 1
            run_end_idx = i - 1

            # Require enough signal epochs within this zero run to be valid.
            signal_count = sum(1 for j in range(run_start_idx, run_end_idx + 1) if _is_signal(j))
            if signal_count < min_epochs:
                continue

            # Extend start backward through any leading signal epochs even if
            # activity > 0 (e.g. sensor marks nonwear from 11:56 but zeros only
            # begin at 12:06 — the marker should start at 11:56, not 12:06).
            while run_start_idx > 0 and _is_signal(run_start_idx - 1):
                run_start_idx -= 1
            # Extend end forward symmetrically.
            while run_end_idx < len(timestamps) - 1 and _is_signal(run_end_idx + 1):
                run_end_idx += 1

            run_start_ts = timestamps[run_start_idx]
            run_end_ts = timestamps[run_end_idx]

            if any(run_start_ts < sm_end and run_end_ts > sm_start for sm_start, sm_end in sleep_intervals):
                continue

            if any(run_start_ts < pm_end and run_end_ts > pm_start for pm_start, pm_end in placed_ts_ranges):
                continue

            dur_min = (run_end_idx - run_start_idx + 1) * epoch_length_seconds // 60
            notes.append(
                f"Nonwear ({label}): "
                f"{epoch_times[run_start_idx].strftime('%H:%M')}-{epoch_times[run_end_idx].strftime('%H:%M')} "
                f"({dur_min}min, confirmed by {label}, zero activity)"
            )
            markers.append(
                {
                    "start_timestamp": run_start_ts,
                    "end_timestamp": run_end_ts,
                    "marker_index": len(markers) + 1,
                }
            )
            placed_ts_ranges.append((run_start_ts, run_end_ts))

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


def _find_nearest_epoch_dt(epoch_times: list[datetime], target: datetime) -> int | None:
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
