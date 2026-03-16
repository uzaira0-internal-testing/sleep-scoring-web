"""
Night complexity (scoring difficulty) computation.

Pure computation - no DB or async. Takes arrays of data and returns a score.
Score is 0-100, higher = easier to score. -1 = no diary (infinite complexity).

Key rules:
- No diary = score -1 (infinite complexity, cannot score without reference)
- Nonwear only counts when BOTH Choi AND sensor/diary report overlap
- Boundary clarity checks activity spikes at both onset and offset
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta


def _linear_penalty(value: float, low: float, high: float, max_penalty: float) -> float:
    """Linearly interpolate penalty between low (0) and high (max_penalty)."""
    if value <= low:
        return 0.0
    if value >= high:
        return max_penalty
    return max_penalty * (value - low) / (high - low)


def _night_window_indices(
    timestamps: list[float],
    analysis_date: str,
) -> tuple[int, int]:
    """Return (start_idx, end_idx) for night window (21:00 to 09:00 next day)."""
    date_obj = datetime.strptime(analysis_date, "%Y-%m-%d").date()
    night_start = datetime.combine(date_obj, datetime.min.time()) + timedelta(hours=21)
    night_end = night_start + timedelta(hours=12)  # 09:00 next day

    night_start_ts = float(calendar.timegm(night_start.timetuple()))
    night_end_ts = float(calendar.timegm(night_end.timetuple()))

    start_idx = 0
    end_idx = len(timestamps)
    for i, ts in enumerate(timestamps):
        if ts >= night_start_ts:
            start_idx = i
            break
    for i in range(len(timestamps) - 1, -1, -1):
        if timestamps[i] <= night_end_ts:
            end_idx = i + 1
            break
    return start_idx, end_idx


def _count_transitions(sleep_scores: list[int], start: int, end: int) -> int:
    """Count sleep/wake transitions in a slice."""
    transitions = 0
    for i in range(start + 1, min(end, len(sleep_scores))):
        if sleep_scores[i] != sleep_scores[i - 1]:
            transitions += 1
    return transitions


def _count_sleep_runs(sleep_scores: list[int], start: int, end: int, min_run: int = 3) -> int:
    """Count distinct sleep runs (>= min_run consecutive sleep epochs)."""
    runs = 0
    current_run = 0
    for i in range(start, min(end, len(sleep_scores))):
        if sleep_scores[i] == 1:
            current_run += 1
        else:
            if current_run >= min_run:
                runs += 1
            current_run = 0
    if current_run >= min_run:
        runs += 1
    return runs


def _total_sleep_period_hours(
    sleep_scores: list[int],
    timestamps: list[float],
    start: int,
    end: int,
    min_run: int = 3,
) -> float:
    """
    Duration of total sleep period (first valid onset to last valid offset) in hours.

    Uses first-to-last sleep run boundaries (runs >= min_run epochs) to measure
    the overall sleep period span. This reflects total sleep duration rather than
    the longest single unbroken run, which is misleadingly short in normal
    fragmented actigraphy data (10-20 transitions per night is typical).
    """
    first_onset_ts: float | None = None
    last_offset_ts: float | None = None
    n = min(end, len(sleep_scores))

    current_run = 0
    run_start = start
    for i in range(start, n):
        if sleep_scores[i] == 1:
            if current_run == 0:
                run_start = i
            current_run += 1
        else:
            if current_run >= min_run:
                if first_onset_ts is None:
                    first_onset_ts = timestamps[run_start]
                last_offset_ts = timestamps[i - 1]
            current_run = 0
    # Close trailing run
    if current_run >= min_run:
        if first_onset_ts is None:
            first_onset_ts = timestamps[run_start]
        last_offset_ts = timestamps[min(start + n - 1, len(timestamps) - 1)]

    if first_onset_ts is None or last_offset_ts is None:
        return 0.0
    return (last_offset_ts - first_onset_ts) / 3600.0


def _count_activity_spikes(
    activity_counts: list[float],
    start: int,
    end: int,
    threshold: float = 50.0,
) -> int:
    """Count distinct activity spikes above threshold in a window."""
    spikes = 0
    in_spike = False
    for i in range(start, min(end, len(activity_counts))):
        if activity_counts[i] >= threshold:
            if not in_spike:
                spikes += 1
                in_spike = True
        else:
            in_spike = False
    return spikes


def _diary_nap_count(diary_nap_count: int) -> int:
    """Clamp nap count."""
    return max(0, min(diary_nap_count, 3))


def _boundary_spike_score(
    activity_counts: list[float],
    idx: int,
    start: int,
    end: int,
    window: int = 10,
) -> float:
    """
    Measure activity spike magnitude near a boundary index.

    Returns a clarity score 0.0 (ambiguous) to 1.0 (clear spike).
    A clear spike means there's a visible activity contrast at the boundary,
    which is what scorers look for when identifying onset/offset.
    """
    n = min(end, len(activity_counts))
    if idx < start or idx >= n:
        return 0.0

    # Activity in the window on each side of the boundary
    before_start = max(start, idx - window)
    after_end = min(n, idx + window)

    before = activity_counts[before_start:idx] if idx > before_start else []
    after = activity_counts[idx:after_end] if after_end > idx else []

    if not before or not after:
        return 0.0

    before_mean = sum(before) / len(before)
    after_mean = sum(after) / len(after)

    # Check for clear contrast (spike on one side, low on the other)
    if before_mean < 1.0 and after_mean < 1.0:
        return 0.0  # Both low - no visible boundary

    # For onset: expect high activity before (getting into bed), low after (sleeping)
    # For offset: expect low activity before (sleeping), high after (waking up)
    # We just measure the contrast ratio regardless of direction
    high = max(before_mean, after_mean)
    low = min(before_mean, after_mean)
    ratio = high / max(low, 0.1)

    if ratio >= 3.0:
        return 1.0  # Clear spike
    if ratio >= 1.5:
        return 0.5  # Moderate
    return 0.0  # Ambiguous


def _boundary_clarity_penalty(
    activity_counts: list[float],
    sleep_scores: list[int],
    start: int,
    end: int,
) -> float:
    """
    Measure activity spikes at algorithm sleep onset AND offset boundaries.

    Scorers look for:
    - Activity spike before onset (getting into bed)
    - Activity spike after offset (waking up)

    Returns penalty 0 to -10.
    """
    if end <= start or len(activity_counts) == 0:
        return -10.0

    # Find first sleep onset and last sleep offset
    onset_idx = None
    offset_idx = None
    for i in range(start, min(end, len(sleep_scores))):
        if sleep_scores[i] == 1:
            if onset_idx is None:
                onset_idx = i
            offset_idx = i

    if onset_idx is None:
        return -10.0  # No sleep found at all

    # Score onset clarity (spike before first sleep)
    onset_score = _boundary_spike_score(activity_counts, onset_idx, start, end)

    # Score offset clarity (spike after last sleep)
    offset_score = _boundary_spike_score(activity_counts, offset_idx, start, end)

    # Average: both clear = 0 penalty, both ambiguous = -10
    avg_clarity = (onset_score + offset_score) / 2.0
    return -round((1.0 - avg_clarity) * 10.0, 1)


def _build_confirmed_nonwear_mask(
    choi_nonwear: list[int],
    sensor_nonwear_periods: list[tuple[float, float]],
    timestamps: list[float],
) -> list[int]:
    """
    Build nonwear mask where BOTH Choi AND sensor/diary agree.

    Only epochs where Choi detects nonwear AND a sensor/diary-reported
    nonwear period overlaps are marked as confirmed nonwear.
    Choi alone or sensor alone do not count.
    """
    if not sensor_nonwear_periods:
        return [0] * len(choi_nonwear)

    # Build sensor mask from time periods
    sensor_mask = [0] * len(timestamps)
    for nw_start, nw_end in sensor_nonwear_periods:
        for i, ts in enumerate(timestamps):
            if nw_start <= ts <= nw_end:
                sensor_mask[i] = 1

    # Intersection: both must agree
    return [c & s for c, s in zip(choi_nonwear, sensor_mask, strict=False)]


def _parse_time_to_24h(time_str: str) -> tuple[int, int]:
    """Parse a time string like "22:04", "10:04 PM", or "7:30 AM" to (hour, minute) in 24h."""
    s = time_str.strip().upper()
    is_pm = "PM" in s
    is_am = "AM" in s
    s = s.replace("PM", "").replace("AM", "").strip()
    parts = s.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    if is_pm and h != 12:
        h += 12
    elif is_am and h == 12:
        h = 0
    return h, m


def _find_sleep_run_boundaries(
    sleep_scores: list[int],
    timestamps: list[float],
    start: int,
    end: int,
    min_run: int = 3,
) -> tuple[list[float], list[float]]:
    """
    Find all sleep run onset and offset timestamps during the night window.

    A sleep run is >= min_run consecutive sleep epochs.
    Returns (onset_timestamps, offset_timestamps).
    """
    onsets: list[float] = []
    offsets: list[float] = []
    in_run = False
    run_start = start
    run_length = 0

    for i in range(start, min(end, len(sleep_scores))):
        if sleep_scores[i] == 1:
            if not in_run:
                run_start = i
                run_length = 0
                in_run = True
            run_length += 1
        else:
            if in_run and run_length >= min_run:
                onsets.append(timestamps[run_start])
                offsets.append(timestamps[i - 1])
            in_run = False
            run_length = 0

    # Close final run
    if in_run and run_length >= min_run:
        onsets.append(timestamps[run_start])
        last = min(end, len(timestamps)) - 1
        offsets.append(timestamps[last])

    return onsets, offsets


def _candidate_ambiguity_penalty(
    timestamps: list[float],
    sleep_scores: list[int],
    choi_nonwear: list[int],
    diary_onset_ts: float,
    diary_wake_ts: float,
    night_start: int,
    night_end: int,
) -> tuple[float, dict]:
    """
    Measure how many plausible onset/offset candidates exist near diary times.

    Rules captured:
    - Multiple candidates within 30 min of diary = scorer must choose (rules 2, 6)
    - Candidate with nonwear nearby vs without = harder choice (rule 6)
    - Algorithm onset before diary onset = scorer must override (rule 8)

    Returns (penalty 0 to -15, details_dict).
    """
    details: dict = {}
    penalty = 0.0

    onsets, offsets = _find_sleep_run_boundaries(sleep_scores, timestamps, night_start, night_end)
    details["onset_candidates_total"] = len(onsets)
    details["offset_candidates_total"] = len(offsets)

    # Count candidates within 30 min of diary times
    window_sec = 30 * 60  # 30 minutes

    onset_near = [t for t in onsets if abs(t - diary_onset_ts) <= window_sec]
    offset_near = [t for t in offsets if abs(t - diary_wake_ts) <= window_sec]
    details["onset_candidates_near_diary"] = len(onset_near)
    details["offset_candidates_near_diary"] = len(offset_near)

    # Onset candidates near diary (-5 max)
    # 0 = no boundary near diary at all → worst (scorer has nothing to anchor to)
    # 1 = clear single candidate → no penalty
    # 2+ = multiple choices → scorer must pick
    if len(onset_near) == 0 or len(onset_near) >= 3:
        penalty += 5.0
    elif len(onset_near) == 2:
        penalty += 3.0

    # Offset candidates near diary (-5 max), same logic
    if len(offset_near) == 0 or len(offset_near) >= 3:
        penalty += 5.0
    elif len(offset_near) == 2:
        penalty += 3.0

    # Rule 8: algorithm onset before diary onset → scorer must use in-bed time instead
    # Check nearest onset candidate (even outside 30 min window)
    candidates_for_r8 = onset_near or onsets
    algo_before_diary = any(t < diary_onset_ts - 60 for t in candidates_for_r8)
    if algo_before_diary:
        penalty += 3.0
        details["algo_onset_before_diary"] = True
    else:
        details["algo_onset_before_diary"] = False

    # Rule 6: if any candidate near diary has nonwear nearby, that's extra ambiguity
    nonwear_near_candidate = False
    candidates_to_check = onset_near + offset_near
    if candidates_to_check:
        for t in candidates_to_check:
            # Find index closest to this timestamp
            idx = min(range(len(timestamps)), key=lambda i: abs(timestamps[i] - t))
            # Check for Choi nonwear within ±10 epochs of the candidate
            check_start = max(night_start, idx - 10)
            check_end = min(night_end, idx + 10)
            if any(choi_nonwear[j] == 1 for j in range(check_start, min(check_end, len(choi_nonwear)))):
                nonwear_near_candidate = True
                break

    if nonwear_near_candidate and (len(onset_near) >= 2 or len(offset_near) >= 2):
        penalty += 2.0
        details["nonwear_near_candidate"] = True
    else:
        details["nonwear_near_candidate"] = False

    capped = min(penalty, 15.0)
    details["candidate_ambiguity_penalty"] = round(-capped, 1)
    return capped, details


def _nearest_sleep_boundary_ts(
    timestamps: list[float],
    sleep_scores: list[int],
    diary_ts: float,
    boundary_type: str,
    search_window_sec: float = 7200.0,
    min_run: int = 3,
) -> float | None:
    """
    Find the nearest sleep run boundary (onset or offset) within ±search_window of diary_ts.

    boundary_type: 'onset' returns start-of-run timestamps,
                   'offset' returns end-of-run timestamps.
    Only considers runs of >= min_run consecutive sleep epochs.
    Returns the boundary timestamp closest to diary_ts, or None.
    """
    window_start = diary_ts - search_window_sec
    window_end = diary_ts + search_window_sec
    candidates: list[float] = []

    n = len(sleep_scores)
    i = 0
    while i < n:
        if sleep_scores[i] == 1:
            run_start = i
            while i < n and sleep_scores[i] == 1:
                i += 1
            run_end = i - 1
            if (i - run_start) >= min_run:
                if boundary_type == "onset":
                    ts = timestamps[run_start]
                else:
                    ts = timestamps[run_end]
                if window_start <= ts <= window_end:
                    candidates.append(ts)
        else:
            i += 1

    if not candidates:
        return None
    return min(candidates, key=lambda t: abs(t - diary_ts))


def _diary_algorithm_gap_penalty(
    timestamps: list[float],
    sleep_scores: list[int],
    diary_onset_time: str | None,
    diary_wake_time: str | None,
    analysis_date: str,
) -> tuple[float, float | None, float | None]:
    """
    Penalty for gap between diary times and nearest algorithm sleep boundary.

    Finds the nearest valid sleep run boundary (onset or offset) within ±2 hours
    of each diary time, rather than the global first/last sleep epoch. This avoids
    inflated gaps when naps or early sleep exist far from the main sleep period.

    Returns (penalty, onset_gap_minutes, offset_gap_minutes).
    """
    if diary_onset_time is None and diary_wake_time is None:
        return 0.0, None, None  # No diary - handled separately

    date_obj = datetime.strptime(analysis_date, "%Y-%m-%d").date()

    onset_gap_min: float | None = None
    offset_gap_min: float | None = None
    total_penalty = 0.0

    if diary_onset_time:
        h, m = _parse_time_to_24h(diary_onset_time)
        onset_day = date_obj if h >= 12 else date_obj + timedelta(days=1)
        onset_dt = datetime.combine(onset_day, datetime.min.time()) + timedelta(hours=h, minutes=m)
        diary_ts = float(calendar.timegm(onset_dt.timetuple()))
        nearest = _nearest_sleep_boundary_ts(timestamps, sleep_scores, diary_ts, "onset")
        if nearest is not None:
            onset_gap_min = abs(diary_ts - nearest) / 60.0
            total_penalty += _linear_penalty(onset_gap_min, 10, 60, 7.5)

    if diary_wake_time:
        h, m = _parse_time_to_24h(diary_wake_time)
        wake_day = date_obj + timedelta(days=1) if h < 12 else date_obj
        wake_dt = datetime.combine(wake_day, datetime.min.time()) + timedelta(hours=h, minutes=m)
        diary_ts = float(calendar.timegm(wake_dt.timetuple()))
        nearest = _nearest_sleep_boundary_ts(timestamps, sleep_scores, diary_ts, "offset")
        if nearest is not None:
            offset_gap_min = abs(diary_ts - nearest) / 60.0
            total_penalty += _linear_penalty(offset_gap_min, 10, 60, 7.5)

    return -total_penalty, onset_gap_min, offset_gap_min


def compute_pre_complexity(
    timestamps: list[float],
    activity_counts: list[float],
    sleep_scores: list[int],
    choi_nonwear: list[int],
    diary_onset_time: str | None,
    diary_wake_time: str | None,
    diary_nap_count: int,
    analysis_date: str,
    sensor_nonwear_periods: list[tuple[float, float]] | None = None,
    diary_nonwear_times: list[tuple[str, str]] | None = None,
) -> tuple[int, dict]:
    """
    Compute pre-scoring complexity score.

    Returns (score 0-100 or -1, features_dict with breakdown).

    If no diary is available (both onset and wake are None), returns -1
    (infinite complexity) because scoring without diary reference is impossible.
    """
    features: dict = {}

    if not timestamps or not sleep_scores:
        return 0, {"error": "insufficient_data"}

    # Incomplete diary = -1 (infinite complexity). Need BOTH onset and wake to score.
    if diary_onset_time is None or diary_wake_time is None:
        features["no_diary"] = diary_onset_time is None and diary_wake_time is None
        features["missing_onset"] = diary_onset_time is None
        features["missing_wake"] = diary_wake_time is None
        features["diary_completeness_penalty"] = "N/A"
        features["total_penalty"] = "N/A"
        return -1, features

    # Diary-reported nonwear overlapping diary-reported sleep = infinite complexity.
    # If someone reported nonwear during their reported sleep, the data is unusable.
    # NOTE: This checks DIARY nonwear (user-reported), NOT sensor nonwear markers.
    # Sensor nonwear during sleep is normal (low movement looks like nonwear to devices).
    if diary_nonwear_times and diary_onset_time and diary_wake_time:
        date_obj_check = datetime.strptime(analysis_date, "%Y-%m-%d").date()
        oh, om = _parse_time_to_24h(diary_onset_time)
        onset_day = date_obj_check if oh >= 12 else date_obj_check + timedelta(days=1)
        diary_onset_ts_min = oh * 60 + om
        wh, wm = _parse_time_to_24h(diary_wake_time)
        diary_wake_ts_min = wh * 60 + wm
        # Convert to minutes-since-noon for simple overlap check
        onset_min_from_noon = (oh - 12) * 60 + om if oh >= 12 else (oh + 12) * 60 + om
        wake_min_from_noon = (wh + 12) * 60 + wm if wh < 12 else (wh - 12) * 60 + wm

        for nw_start_str, nw_end_str in diary_nonwear_times:
            nsh, nsm = _parse_time_to_24h(nw_start_str)
            neh, nem = _parse_time_to_24h(nw_end_str)
            nw_start_from_noon = (nsh - 12) * 60 + nsm if nsh >= 12 else (nsh + 12) * 60 + nsm
            nw_end_from_noon = (neh - 12) * 60 + nem if neh >= 12 else (neh + 12) * 60 + nem
            # Overlap: nonwear starts before wake AND ends after onset
            if nw_start_from_noon < wake_min_from_noon and nw_end_from_noon > onset_min_from_noon:
                features["diary_nonwear_overlaps_sleep"] = True
                features["total_penalty"] = "N/A"
                return -1, features
        features["diary_nonwear_overlaps_sleep"] = False

    total_penalty = 0.0

    night_start, night_end = _night_window_indices(timestamps, analysis_date)
    night_hours = max((night_end - night_start) / 60.0, 1.0)

    # 1. Transition density (-25 max)
    transitions = _count_transitions(sleep_scores, night_start, night_end)
    transition_rate = transitions / night_hours
    penalty = _linear_penalty(transition_rate, 2, 6, 25)
    features["transition_density"] = round(transition_rate, 2)
    features["transition_density_penalty"] = round(-penalty, 1)
    total_penalty += penalty

    # 2. Diary completeness — both onset and wake guaranteed present at this point
    # (incomplete diary already returned -1 above)

    # 3. Diary-algorithm gap (-15 max)
    gap_penalty, onset_gap, offset_gap = _diary_algorithm_gap_penalty(timestamps, sleep_scores, diary_onset_time, diary_wake_time, analysis_date)
    features["diary_algorithm_gap_penalty"] = round(gap_penalty, 1)
    if onset_gap is not None:
        features["diary_onset_gap_min"] = round(onset_gap, 1)
    if offset_gap is not None:
        features["diary_offset_gap_min"] = round(offset_gap, 1)
    total_penalty += abs(gap_penalty)

    # 4. Nonwear during night (-15 max, or infinite if >= 50% of sleep period)
    # Choi + sensor overlap = confirmed nonwear (full penalty weight).
    # Choi alone = still adds complexity (scorer must decide if real).
    # Sensor alone = no penalty (no algorithmic evidence to confuse scorer).
    confirmed = _build_confirmed_nonwear_mask(choi_nonwear, sensor_nonwear_periods or [], timestamps)
    choi_night_epochs = sum(choi_nonwear[night_start:night_end])
    confirmed_epochs = sum(confirmed[night_start:night_end])
    choi_only_epochs = choi_night_epochs - confirmed_epochs

    # Check if Choi nonwear covers >= 50% of the sleep period → maybe infinite complexity
    sleep_night_epochs = sum(sleep_scores[night_start:night_end])
    choi_proportion = choi_night_epochs / max(sleep_night_epochs, 1)

    features["confirmed_nonwear_night_epochs"] = confirmed_epochs
    features["choi_only_nonwear_night_epochs"] = choi_only_epochs
    features["choi_night_epochs"] = choi_night_epochs
    features["sleep_night_epochs"] = sleep_night_epochs
    features["choi_sleep_proportion"] = round(choi_proportion, 3)

    # Activity spikes tell us if the night has real data or is truly flat/nonwear.
    # Sadeh scores zero-activity (nonwear) as sleep, so choi_proportion alone
    # cannot distinguish "device off all night" from "Choi over-detecting on a
    # night with real activity". Check for actual activity before declaring
    # infinite complexity.
    night_spikes = _count_activity_spikes(activity_counts, night_start, night_end, threshold=50.0)
    features["night_activity_spikes"] = night_spikes

    if choi_proportion >= 0.5 and choi_night_epochs >= 30:
        if night_spikes == 0:
            # Choi covers most of the night AND no real activity → truly nonwear
            features["nonwear_night_penalty"] = "N/A"
            features["total_penalty"] = "N/A"
            features["nonwear_exceeds_threshold"] = True
            features["flatline_suspicious"] = False
            return -1, features
        # Choi covers a lot but there IS real activity → Choi is over-detecting.
        # Don't return -1; fall through to penalty-based scoring.
        features["nonwear_exceeds_threshold"] = False
        features["flatline_suspicious"] = False
    elif night_spikes == 0 and choi_night_epochs >= 60:
        # Flatline with some Choi nonwear = almost certainly nonwear
        features["flatline_suspicious"] = True
        features["nonwear_night_penalty"] = "N/A"
        features["total_penalty"] = "N/A"
        features["nonwear_exceeds_threshold"] = True
        return -1, features
    else:
        features["nonwear_exceeds_threshold"] = False
        features["flatline_suspicious"] = False

    # Confirmed nonwear: full weight. Choi-only: half weight (ambiguous).
    effective_nonwear = confirmed_epochs + choi_only_epochs * 0.5
    if effective_nonwear == 0:
        nw_penalty = 0.0
    elif effective_nonwear <= 30:
        nw_penalty = _linear_penalty(effective_nonwear, 0, 30, 10)
    else:
        nw_penalty = 15.0
    features["effective_nonwear_epochs"] = round(effective_nonwear, 1)
    features["nonwear_night_penalty"] = round(-nw_penalty, 1)
    features["nonwear_exceeds_threshold"] = False
    total_penalty += nw_penalty

    # 5. Sleep run count (-5 max)
    # Normal actigraphy data has 8-20 sleep runs per night due to brief arousals.
    # Multiple runs don't make scoring harder if onset/offset boundaries are clear
    # (captured by candidate_ambiguity and boundary_clarity). Only penalize when
    # the night is genuinely fragmented beyond the normal range.
    run_count = _count_sleep_runs(sleep_scores, night_start, night_end)
    if run_count <= 10:
        run_penalty = 0
    elif run_count <= 15:
        run_penalty = 2
    elif run_count <= 20:
        run_penalty = 3
    else:
        run_penalty = 5
    features["sleep_run_count"] = run_count
    features["sleep_run_penalty"] = -run_penalty
    total_penalty += run_penalty

    # 6. Duration typicality (-10 max)
    # Uses total sleep period span (first valid onset to last valid offset) rather
    # than longest single continuous run. With normal fragmentation (10-20
    # transitions/night), the longest single run is misleadingly short (~1-3h)
    # even when total sleep period is a healthy 7-8h.
    sleep_period_hours = _total_sleep_period_hours(sleep_scores, timestamps, night_start, night_end)
    if 6 <= sleep_period_hours <= 9:
        dur_penalty = 0
    elif 4 <= sleep_period_hours < 6 or 9 < sleep_period_hours <= 11:
        dur_penalty = 5
    else:
        dur_penalty = 10
    features["sleep_period_hours"] = round(sleep_period_hours, 1)
    features["duration_typicality_penalty"] = -dur_penalty
    total_penalty += dur_penalty

    # 7. Nap complexity (-5 max)
    naps = _diary_nap_count(diary_nap_count)
    nap_penalties = {0: 0, 1: 2, 2: 3, 3: 5}
    nap_penalty = nap_penalties.get(naps, 5)
    features["nap_count"] = naps
    features["nap_complexity_penalty"] = -nap_penalty
    total_penalty += nap_penalty

    # 8. Boundary clarity - spikes at both onset AND offset (-10 max)
    bc_penalty = _boundary_clarity_penalty(activity_counts, sleep_scores, night_start, night_end)
    features["boundary_clarity_penalty"] = round(bc_penalty, 1)
    total_penalty += abs(bc_penalty)

    # 9. Candidate ambiguity (-15 max)
    # Multiple plausible onset/offset boundaries near diary = scorer must choose
    date_obj = datetime.strptime(analysis_date, "%Y-%m-%d").date()
    # diary_onset_time and diary_wake_time are guaranteed non-None here
    oh, om = _parse_time_to_24h(diary_onset_time)  # type: ignore[arg-type]
    onset_day = date_obj if oh >= 12 else date_obj + timedelta(days=1)
    diary_onset_dt = datetime.combine(onset_day, datetime.min.time()) + timedelta(hours=oh, minutes=om)
    diary_onset_ts = float(calendar.timegm(diary_onset_dt.timetuple()))

    wh, wm = _parse_time_to_24h(diary_wake_time)  # type: ignore[arg-type]
    wake_day = date_obj + timedelta(days=1) if wh < 12 else date_obj
    diary_wake_dt = datetime.combine(wake_day, datetime.min.time()) + timedelta(hours=wh, minutes=wm)
    diary_wake_ts = float(calendar.timegm(diary_wake_dt.timetuple()))

    ca_penalty, ca_details = _candidate_ambiguity_penalty(
        timestamps,
        sleep_scores,
        choi_nonwear,
        diary_onset_ts,
        diary_wake_ts,
        night_start,
        night_end,
    )
    features.update(ca_details)
    total_penalty += ca_penalty

    score = max(0, round(100 - total_penalty))
    features["total_penalty"] = round(-total_penalty, 1)

    return score, features


def compute_post_complexity(
    complexity_pre: int,
    features: dict,
    sleep_markers: list[tuple[float, float]],
    sleep_scores: list[int],
    timestamps: list[float],
) -> tuple[int, dict]:
    """
    Compute post-scoring complexity adjustments.

    Applied on top of pre-score after markers are placed.
    Returns (score 0-100, updated_features_dict).
    """
    updated = dict(features)
    adjustment = 0

    if not sleep_markers or not timestamps or not sleep_scores:
        updated["post_adjustment"] = 0
        return max(0, min(100, complexity_pre)), updated

    # 1. Marker-algorithm alignment: are placed markers close to algorithm boundaries?
    algo_onset_ts: float | None = None
    algo_offset_ts: float | None = None
    for i, score in enumerate(sleep_scores):
        if score == 1:
            if algo_onset_ts is None:
                algo_onset_ts = timestamps[i]
            algo_offset_ts = timestamps[i]

    if algo_onset_ts is not None and algo_offset_ts is not None:
        closest_onset_dist = min(abs(m[0] - algo_onset_ts) for m in sleep_markers)
        closest_offset_dist = min(abs(m[1] - algo_offset_ts) for m in sleep_markers)

        onset_epochs = closest_onset_dist / 60.0
        offset_epochs = closest_offset_dist / 60.0
        avg_epochs = (onset_epochs + offset_epochs) / 2.0

        if avg_epochs <= 5:
            adjustment += 5
            updated["marker_alignment"] = "close"
        elif avg_epochs > 30:
            adjustment -= 5
            updated["marker_alignment"] = "far"
        else:
            updated["marker_alignment"] = "moderate"

        updated["marker_alignment_epochs"] = round(avg_epochs, 1)

    # 2. Period count unexpected
    runs = 0
    current_run = 0
    for s in sleep_scores:
        if s == 1:
            current_run += 1
        else:
            if current_run >= 3:
                runs += 1
            current_run = 0
    if current_run >= 3:
        runs += 1

    actual_periods = len(sleep_markers)
    if actual_periods != runs and runs > 0:
        adjustment -= 5
        updated["period_count_expected"] = runs
        updated["period_count_actual"] = actual_periods
        updated["period_count_penalty"] = -5
    else:
        updated["period_count_penalty"] = 0

    updated["post_adjustment"] = adjustment
    score = max(0, min(100, complexity_pre + adjustment))
    return score, updated
