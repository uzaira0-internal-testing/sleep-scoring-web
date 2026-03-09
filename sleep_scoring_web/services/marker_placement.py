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
from datetime import datetime, time, timedelta, timezone
from typing import Any


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


@dataclass
class DiaryPeriod:
    """A diary-reported period (sleep, nap, or nonwear)."""
    start_time: datetime | None = None
    end_time: datetime | None = None
    period_type: str = "sleep"


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
) -> int | None:
    """Find the nearest valid onset point to a target timestamp.

    A valid onset is the start of min_consecutive (3) or more consecutive
    sleep epochs. Searches outward from target in both directions.

    Returns the epoch index, or None if no valid onset found.
    """
    # Find epoch index closest to target timestamp
    center = _nearest_epoch_index(epochs, target_ts)
    if center is None:
        return None

    # Precompute all valid onset positions (start of 3+ consecutive sleep)
    valid_onsets: list[int] = []
    i = 0
    while i < len(epochs):
        if epochs[i].sleep_score == 1:
            run_start = i
            while i < len(epochs) and epochs[i].sleep_score == 1:
                i += 1
            run_len = i - run_start
            if run_len >= min_consecutive:
                valid_onsets.append(run_start)
        else:
            i += 1

    if not valid_onsets:
        return None

    # Onset should be AT or BEFORE the diary time (more inclusive).
    # Only fall back to after-target candidates if none exist before.
    before = [idx for idx in valid_onsets if idx <= center]
    after = [idx for idx in valid_onsets if idx > center]

    pool = before if before else after
    best: int | None = None
    best_dist = float("inf")
    for idx in pool:
        dist = abs(idx - center)
        if dist < best_dist:
            best_dist = dist
            best = idx
        elif dist == best_dist and best is not None and idx < best:
            best = idx

    return best


def _find_valid_offset_near(
    epochs: list[EpochData],
    target_ts: datetime,
    min_consecutive_minutes: int,
    epoch_length_seconds: int,
) -> int | None:
    """Find the nearest valid offset point to a target timestamp.

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

    pool = after if after else before
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
    max_forward_epochs: int = 60,
) -> int | None:
    """Find the nearest valid offset near a target, with a bounded forward look.

    Like _find_valid_offset_near but limits how far PAST the target the offset
    can land.  Offsets are ALWAYS placed at actual sleep→wake transitions (the
    last sleep epoch before wake), never in the middle of a continuous sleep
    run.  Runs whose natural end exceeds the forward bound are skipped.

    Returns the epoch index, or None if no valid offset found.
    """
    center = _nearest_epoch_index(epochs, target_ts)
    if center is None:
        return None

    min_epochs = max(1, min_consecutive_minutes * 60 // epoch_length_seconds)
    max_idx = min(center + max_forward_epochs, len(epochs) - 1)

    # Precompute all valid offset positions — only at REAL run ends (sleep→wake)
    valid_offsets: list[int] = []
    i = 0
    while i < len(epochs):
        if epochs[i].sleep_score == 1:
            run_start = i
            while i < len(epochs) and epochs[i].sleep_score == 1:
                i += 1
            run_end = i - 1  # Last sleep epoch — always a real transition
            run_len = i - run_start
            if run_len >= min_epochs and run_end <= max_idx:
                valid_offsets.append(run_end)
        else:
            i += 1

    if not valid_offsets:
        return None

    # Offset should be AT or AFTER the diary time (more inclusive).
    # Only fall back to before-target candidates if none exist after.
    after = [idx for idx in valid_offsets if idx >= center]
    before = [idx for idx in valid_offsets if idx < center]

    pool = after if after else before
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
) -> tuple[int, int] | None:
    """Place main sleep period using diary onset/offset as reference.

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
        epochs, diary.sleep_onset, config.onset_min_consecutive_sleep
    )

    # Bounded offset search: look within a window around diary wake.
    # Allow looking up to 60 epochs (1 hour) past wake — but no further.
    # This prevents offsets landing hours past diary wake when there's a
    # long continuous sleep run, while still allowing reasonable forward look.
    max_forward_epochs = 60  # 1 hour at 1-min epochs
    offset_idx = _find_valid_offset_near_bounded(
        epochs, diary.wake_time, config.offset_min_consecutive_minutes,
        config.epoch_length_seconds, max_forward_epochs,
    )

    if onset_idx is None or offset_idx is None:
        return None
    if onset_idx >= offset_idx:
        return None

    # Rule 8: if onset is before in-bed time, clamp to in-bed time
    if diary.in_bed_time and epochs[onset_idx].timestamp < diary.in_bed_time:
        # Find nearest valid onset AT or AFTER in-bed time
        clamped = _find_valid_onset_at_or_after(
            epochs, diary.in_bed_time, config.onset_min_consecutive_sleep
        )
        if clamped is not None and clamped < offset_idx:
            onset_idx = clamped

    return (onset_idx, offset_idx)


def _find_valid_onset_at_or_after(
    epochs: list[EpochData],
    target: datetime,
    min_consecutive: int,
) -> int | None:
    """Find the first valid onset at or after a target time.

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
    """Find the nearest valid offset at or before max_idx.

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
    """Find the nearest valid onset near a target, bounded by max distance.

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
            if run_len >= min_consecutive and lo <= run_start <= hi:
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
    """Place nap markers from diary nap periods.

    For each diary nap period, find the nearest valid sleep run within
    a bounded window (60 epochs / 1 hour) of the diary times.
    Naps must not overlap with main sleep.
    """
    naps: list[tuple[int, int]] = []
    min_epochs = config.nap_min_consecutive_epochs
    max_search_epochs = 60  # 1 hour at 1-min epochs

    for nap_period in diary.nap_periods:
        if not nap_period.start_time or not nap_period.end_time:
            continue

        onset_idx = _find_valid_onset_near_bounded(
            epochs, nap_period.start_time,
            min_consecutive=config.onset_min_consecutive_sleep,
            max_distance_epochs=max_search_epochs,
        )
        offset_idx = _find_valid_offset_near_bounded(
            epochs, nap_period.end_time,
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
    """Fallback: find longest sleep period when no diary data.

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
        return s[:idx] + "AM" + s[idx + 2:]
    elif "AM" in upper:
        idx = upper.index("AM")
        return s[:idx] + "PM" + s[idx + 2:]
    return None


def _diary_times_plausible(
    onset_dt: datetime | None,
    wake_dt: datetime | None,
    data_start: datetime,
    data_end: datetime,
) -> bool:
    """Check if diary onset/wake times are physiologically plausible.

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
    """Try AM/PM flips on diary onset/wake if original parse is implausible.

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
        flip_attempts.append((
            flipped_onset, flipped_wake,
            f"onset {onset_str} → {flipped_onset}",
            f"wake {wake_str} → {flipped_wake}",
        ))

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
    """Parse a time string to (hour, minute) in 24-hour format.

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
    """Parse time string to datetime, handling overnight logic.

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
        dt = datetime(base_date.year, base_date.month, base_date.day, h, m, tzinfo=timezone.utc)
        if is_evening and h < 12:
            dt += timedelta(days=1)
        elif not is_evening and h < 18:
            dt += timedelta(days=1)
        return dt
    except (ValueError, TypeError):
        return None


def _parse_nap_time(
    time_str: str,
    base_date: Any,
) -> datetime | None:
    """Parse a nap time string to datetime on the analysis date.

    Naps happen during the day, so no overnight day-shifting is applied.
    The time is placed on the analysis date as-is.
    """
    parsed = _parse_time_to_24h(time_str)
    if parsed is None:
        return None
    h, m = parsed
    try:
        return datetime(base_date.year, base_date.month, base_date.day, h, m, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def run_auto_scoring(
    timestamps: list[float],
    activity_counts: list[float],
    sleep_scores: list[int],
    choi_nonwear: list[int] | None = None,
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
        epochs.append(EpochData(
            index=i,
            timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
            sleep_score=sleep_scores[i],
            activity=activity_counts[i],
            is_choi_nonwear=nonwear_bools[i] if i < len(nonwear_bools) else False,
        ))

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
        for nap_start, nap_end in (diary_naps or []):
            if nap_start and nap_end:
                ns = _parse_nap_time(nap_start, d)
                ne = _parse_nap_time(nap_end, d)
                if ns and ne and ne <= ns:
                    ne += timedelta(days=1)
                if ns and ne:
                    nap_periods.append(DiaryPeriod(start_time=ns, end_time=ne, period_type="nap"))

        # Parse nonwear periods
        nw_periods: list[DiaryPeriod] = []
        for nw_start, nw_end in (diary_nonwear or []):
            if nw_start and nw_end:
                ns = _parse_diary_time(nw_start, d, is_evening=False)
                ne = _parse_diary_time(nw_end, d, is_evening=False)
                if ns and ne:
                    nw_periods.append(DiaryPeriod(start_time=ns, end_time=ne, period_type="nonwear"))

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
        notes.append(
            f"Detection rule: {config.onset_min_consecutive_sleep}S/{config.offset_min_consecutive_minutes}S"
        )
    sleep_markers: list[dict[str, Any]] = []
    nap_markers: list[dict[str, Any]] = []

    # Main sleep placement
    main_result: tuple[int, int] | None = None

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
            sleep_markers.append({
                "onset_timestamp": onset_time.timestamp(),
                "offset_timestamp": offset_time.timestamp(),
                "marker_type": "MAIN_SLEEP",
                "marker_index": 1,
            })
        else:
            notes.append(
                f"No valid sleep period found near diary times "
                f"(onset {diary.sleep_onset.strftime('%H:%M')}, "
                f"wake {diary.wake_time.strftime('%H:%M')})"
            )
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
            notes.append(
                f"Nap {i + 1}: {nap_onset_time.strftime('%H:%M')} - "
                f"{nap_offset_time.strftime('%H:%M')} ({duration_min:.0f} min)"
            )
            nap_markers.append({
                "onset_timestamp": nap_onset_time.timestamp(),
                "offset_timestamp": nap_offset_time.timestamp(),
                "marker_type": "NAP",
                "marker_index": len(sleep_markers) + i + 1,
            })

    return {
        "sleep_markers": sleep_markers,
        "nap_markers": nap_markers,
        "notes": notes,
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

        # Count zero-activity epochs within the entire detected range
        zero_epochs = sum(
            1 for i in range(ext_start, ext_end + 1)
            if activity_counts[i] <= threshold
        )
        total_epochs = ext_end - ext_start + 1

        # Require at least 80% of epochs in the range to be zero/near-zero
        if total_epochs > 0 and (zero_epochs / total_epochs) < 0.8:
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

    # Second pass: Choi + sensor overlap with zero activity (no diary needed)
    # Find epochs where both Choi and sensor agree on nonwear AND activity <= threshold
    if choi_nw_set and sensor_nw_ranges:
        # Build set of epochs covered by sensor nonwear
        sensor_nw_set: set[int] = set()
        for si, ei in sensor_nw_ranges:
            sensor_nw_set.update(range(si, ei + 1))

        # Find epochs where Choi + sensor + zero activity all agree
        both_nw = sorted(
            i for i in choi_nw_set & sensor_nw_set
            if i < len(activity_counts) and activity_counts[i] <= threshold
        )

        # Extract contiguous runs
        if both_nw:
            runs: list[tuple[int, int]] = []
            run_start = both_nw[0]
            prev = both_nw[0]
            for idx in both_nw[1:]:
                if idx == prev + 1:
                    prev = idx
                else:
                    runs.append((run_start, prev))
                    run_start = idx
                    prev = idx
            runs.append((run_start, prev))

            # Build set of already-placed marker epoch ranges to avoid duplicates
            placed_ts_ranges = [
                (m["start_timestamp"], m["end_timestamp"]) for m in markers
            ]

            for run_start_idx, run_end_idx in runs:
                duration_epochs = run_end_idx - run_start_idx + 1
                if duration_epochs < min_epochs:
                    continue

                run_start_ts = timestamps[run_start_idx]
                run_end_ts = timestamps[run_end_idx]

                # Skip if overlapping with sleep markers
                overlaps_sleep = any(
                    run_start_ts < sm_end and run_end_ts > sm_start
                    for sm_start, sm_end in sleep_intervals
                )
                if overlaps_sleep:
                    continue

                # Skip if overlapping with already-placed nonwear markers
                overlaps_placed = any(
                    run_start_ts < pm_end and run_end_ts > pm_start
                    for pm_start, pm_end in placed_ts_ranges
                )
                if overlaps_placed:
                    continue

                dur_min = duration_epochs * epoch_length_seconds // 60
                notes.append(
                    f"Nonwear (Choi+sensor): "
                    f"{epoch_times[run_start_idx].strftime('%H:%M')}-{epoch_times[run_end_idx].strftime('%H:%M')} "
                    f"({dur_min}min, confirmed by Choi + sensor, zero activity)"
                )
                markers.append({
                    "start_timestamp": run_start_ts,
                    "end_timestamp": run_end_ts,
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
