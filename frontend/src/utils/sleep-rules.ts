/**
 * Sleep period onset/offset detection using consecutive epochs.
 *
 * Port of desktop app's ConsecutiveEpochsSleepPeriodDetector (consecutive_epochs.py).
 * Finds sleep onset and offset within a marker's time range by scanning
 * algorithm results (Sadeh sleep/wake scores) for consecutive epoch runs.
 *
 * Three detection rules (matching desktop config.py):
 *
 * 1. **3S/5S** (default):
 *    - Onset: first 3 consecutive SLEEP epochs within the marker range.
 *    - Offset: last epoch of the latest run of 5 consecutive SLEEP epochs.
 *    - Both onset and offset are constrained within the marker boundaries.
 *
 * 2. **5S/10S**:
 *    - Same as 3S/5S but with onset=5 and offset=10 thresholds.
 *
 * 3. **Tudor-Locke 2014** (wake-based offset):
 *    - Onset: first 5 consecutive SLEEP epochs within the marker range.
 *    - Offset: the latest SLEEP epoch within the marker range that is
 *      immediately followed by 10 consecutive WAKE epochs.
 *    - The offset itself must fall within the marker boundaries, but the
 *      10-wake validation is allowed to extend beyond the marker end
 *      (because the wake run inherently starts after the offset point).
 *    - If no sleep epoch within the marker has 10 consecutive wake after
 *      it, offset is null.
 *
 * Rule parameters are configured in constants/options.ts via DETECTION_RULE_PARAMS.
 */

/** Result of sleep onset/offset detection */
export interface SleepRuleResult {
  onsetIndex: number | null;
  offsetIndex: number | null;
}

/**
 * Find the index range within timestamps that falls between markerStartSec and markerEndSec.
 *
 * Matches desktop's apply_rules() index search:
 * - startIdx: first timestamp >= markerStartSec
 * - endIdx: last timestamp <= markerEndSec
 */
export function findMarkerIndexRange(
  timestamps: number[],
  markerStartSec: number,
  markerEndSec: number,
): { startIdx: number; endIdx: number } | null {
  let startIdx: number | null = null;
  let endIdx: number | null = null;

  for (let i = 0; i < timestamps.length; i++) {
    if (startIdx === null && timestamps[i] >= markerStartSec) startIdx = i;
    if (timestamps[i] <= markerEndSec) endIdx = i;
  }

  if (startIdx === null || endIdx === null) return null;
  return { startIdx, endIdx };
}

/**
 * Find sleep onset: first epoch of `onsetN` consecutive sleep epochs.
 *
 * Searches from startIdx to endIdx within algorithmResults.
 * Returns the index of the FIRST epoch in the consecutive run (START anchor).
 *
 * Matches desktop's _find_onset() with onset_anchor=START, onset_state=SLEEP.
 */
export function findSleepOnset(
  algorithmResults: number[],
  startIdx: number,
  endIdx: number,
  onsetN: number = 3,
): number | null {
  const safeEnd = Math.min(endIdx, algorithmResults.length - onsetN);

  for (let i = startIdx; i <= safeEnd; i++) {
    let allSleep = true;
    for (let j = 0; j < onsetN; j++) {
      if (algorithmResults[i + j] !== 1) {
        allSleep = false;
        break;
      }
    }
    if (allSleep) return i;
  }

  return null;
}

/**
 * Find sleep offset: LAST epoch of `offsetN` consecutive SLEEP epochs.
 *
 * Searches after onsetIdx + onsetN to endIdx within algorithmResults.
 * Returns the index of the LAST epoch in the consecutive run (END anchor).
 * Takes the LAST valid candidate (latest time), matching desktop behavior.
 *
 * Matches desktop's _find_offset() with offset_state=SLEEP, offset_anchor=END.
 */
export function findSleepOffset(
  algorithmResults: number[],
  onsetIdx: number,
  endIdx: number,
  onsetN: number = 3,
  offsetN: number = 5,
): number | null {
  const searchStart = onsetIdx + onsetN;
  const safeEnd = Math.min(endIdx, algorithmResults.length - offsetN);
  let offsetIdx: number | null = null;

  for (let i = searchStart; i <= safeEnd; i++) {
    let allSleep = true;
    for (let j = 0; j < offsetN; j++) {
      if (algorithmResults[i + j] !== 1) {
        allSleep = false;
        break;
      }
    }
    if (allSleep) {
      // Anchor at END of run (last epoch of the consecutive block)
      offsetIdx = i + offsetN - 1;
    }
  }

  return offsetIdx;
}

/**
 * Find sleep offset via WAKE detection (Tudor-Locke 2014 mode).
 *
 * Searches backward from endIdx (the marker boundary) to find the LATEST
 * sleep epoch that is immediately followed by `offsetN` consecutive WAKE
 * epochs.
 *
 * Key constraint: the offset epoch itself must be within the marker range
 * (between searchStart and endIdx), but the wake validation is allowed to
 * read up to `offsetN` epochs beyond endIdx. This is necessary because the
 * wake run that qualifies the offset inherently starts after the offset
 * epoch itself.
 *
 * Example with offsetN=10:
 *   Marker covers epochs 0–20. Epoch 20 is SLEEP, epochs 21–30 are WAKE.
 *   → Epoch 20 qualifies: it's within the marker, and the 10-wake check
 *     reads epochs 21–30 (beyond the marker end) to confirm.
 *
 * @returns Index of the latest qualifying sleep epoch, or null if none found.
 */
export function findWakeOffset(
  algorithmResults: number[],
  onsetIdx: number,
  endIdx: number,
  onsetN: number,
  offsetN: number,
): number | null {
  const searchStart = onsetIdx + onsetN;

  // Walk backward from the marker end to find the latest sleep epoch
  // that has offsetN consecutive wake epochs immediately after it.
  for (let i = endIdx; i >= searchStart; i--) {
    if (algorithmResults[i] !== 1) continue; // must be a sleep epoch

    // Check if the next offsetN epochs are all wake (may extend beyond endIdx)
    if (i + offsetN >= algorithmResults.length) continue; // not enough data after
    let allWake = true;
    for (let j = 1; j <= offsetN; j++) {
      if (algorithmResults[i + j] !== 0) {
        allWake = false;
        break;
      }
    }
    if (allWake) return i;
  }

  return null;
}

/**
 * Detect sleep onset and offset within a marker's time range.
 *
 * Main entry point — equivalent to desktop's
 * ConsecutiveEpochsSleepPeriodDetector.apply_rules().
 *
 * 1. Converts marker timestamps to index range via findMarkerIndexRange().
 * 2. Finds onset within that range via findSleepOnset().
 * 3. Finds offset via findSleepOffset() (sleep modes) or findWakeOffset()
 *    (Tudor-Locke wake mode), depending on offsetState.
 *
 * @param algorithmResults - Sadeh sleep/wake scores (1=sleep, 0=wake)
 * @param timestamps - Epoch timestamps in seconds, parallel to algorithmResults
 * @param markerStartSec - Marker onset timestamp in seconds
 * @param markerEndSec - Marker offset timestamp in seconds
 * @param onsetN - Consecutive sleep epochs required for onset (default: 3)
 * @param offsetN - Consecutive epochs required for offset (default: 5)
 * @param offsetState - "sleep": offset scans for consecutive sleep runs.
 *                      "wake": offset finds the last sleep epoch before
 *                      consecutive wake (Tudor-Locke). Default: "sleep".
 */
export function detectSleepOnsetOffset(
  algorithmResults: number[],
  timestamps: number[],
  markerStartSec: number,
  markerEndSec: number,
  onsetN: number = 3,
  offsetN: number = 5,
  offsetState: "sleep" | "wake" = "sleep",
): SleepRuleResult {
  if (algorithmResults.length === 0 || timestamps.length === 0) {
    return { onsetIndex: null, offsetIndex: null };
  }

  const range = findMarkerIndexRange(timestamps, markerStartSec, markerEndSec);
  if (!range) {
    return { onsetIndex: null, offsetIndex: null };
  }

  const onsetIndex = findSleepOnset(algorithmResults, range.startIdx, range.endIdx, onsetN);
  if (onsetIndex === null) {
    return { onsetIndex: null, offsetIndex: null };
  }

  const offsetIndex = offsetState === "wake"
    ? findWakeOffset(algorithmResults, onsetIndex, range.endIdx, onsetN, offsetN)
    : findSleepOffset(algorithmResults, onsetIndex, range.endIdx, onsetN, offsetN);

  return { onsetIndex, offsetIndex };
}
