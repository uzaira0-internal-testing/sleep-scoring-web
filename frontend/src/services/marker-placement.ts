/**
 * Automated marker placement service.
 *
 * Port of sleep_scoring_web/services/marker_placement.py.
 *
 * Diary-centric approach: uses diary onset/offset as reference points,
 * finds the closest valid sleep boundaries that satisfy the N-epoch onset
 * and M-minute offset rules, and creates the largest inclusive sleep period.
 */

import type { AutoScoreResult, AutoNonwearResult } from "@/services/data-source";

export type { AutoScoreResult };
export type NonwearPlacementResult = AutoNonwearResult;

// =============================================================================
// Configuration
// =============================================================================

interface PlacementConfig {
  onsetMinConsecutiveSleep: number;
  offsetMinConsecutiveMinutes: number;
  diaryToleranceMinutes: number;
  napMinConsecutiveEpochs: number;
  epochLengthSeconds: number;
}

const DEFAULT_CONFIG: PlacementConfig = {
  onsetMinConsecutiveSleep: 3,
  offsetMinConsecutiveMinutes: 5,
  diaryToleranceMinutes: 15,
  napMinConsecutiveEpochs: 10,
  epochLengthSeconds: 60,
};

// =============================================================================
// Data Models
// =============================================================================

interface EpochData {
  index: number;
  /** Unix timestamp in seconds */
  timestamp: number;
  sleepScore: number; // 0=wake, 1=sleep
  activity: number;
  isChoiNonwear: boolean;
}

interface DiaryPeriod {
  /** Unix timestamp in seconds */
  startTime: number | null;
  /** Unix timestamp in seconds */
  endTime: number | null;
  periodType: "sleep" | "nap" | "nonwear";
}

interface DiaryDay {
  inBedTime: number | null;
  sleepOnset: number | null;
  wakeTime: number | null;
  napPeriods: DiaryPeriod[];
  nonwearPeriods: DiaryPeriod[];
}

// =============================================================================
// Core Diary-Centric Placement
// =============================================================================

function nearestEpochIndex(epochs: EpochData[], targetTs: number): number | null {
  if (epochs.length === 0) return null;
  let lo = 0;
  let hi = epochs.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (epochs[mid]!.timestamp < targetTs) lo = mid + 1;
    else hi = mid;
  }
  if (lo > 0) {
    const dLo = Math.abs(epochs[lo]!.timestamp - targetTs);
    const dPrev = Math.abs(epochs[lo - 1]!.timestamp - targetTs);
    if (dPrev < dLo) return lo - 1;
  }
  return lo;
}

/** Find sleep runs: returns array of [runStart, runEnd, runLength]. */
function findSleepRuns(epochs: EpochData[]): Array<[number, number, number]> {
  const runs: Array<[number, number, number]> = [];
  let i = 0;
  while (i < epochs.length) {
    if (epochs[i]!.sleepScore === 1) {
      const start = i;
      while (i < epochs.length && epochs[i]!.sleepScore === 1) i++;
      runs.push([start, i - 1, i - start]);
    } else {
      i++;
    }
  }
  return runs;
}

function findValidOnsetNear(
  epochs: EpochData[],
  targetTs: number,
  minConsecutive: number,
): number | null {
  const center = nearestEpochIndex(epochs, targetTs);
  if (center === null) return null;

  const validOnsets: number[] = [];
  for (const [start, , len] of findSleepRuns(epochs)) {
    if (len >= minConsecutive) validOnsets.push(start);
  }
  if (validOnsets.length === 0) return null;

  // Prefer onsets AT or BEFORE the diary time
  const before = validOnsets.filter((idx) => idx <= center);
  const after = validOnsets.filter((idx) => idx > center);
  const pool = before.length > 0 ? before : after;

  let best: number | null = null;
  let bestDist = Infinity;
  for (const idx of pool) {
    const dist = Math.abs(idx - center);
    if (dist < bestDist || (dist === bestDist && best !== null && idx < best)) {
      bestDist = dist;
      best = idx;
    }
  }
  return best;
}

function findValidOffsetNearBounded(
  epochs: EpochData[],
  targetTs: number,
  minConsecutiveMinutes: number,
  epochLengthSeconds: number,
  maxForwardEpochs: number = 60,
): number | null {
  const center = nearestEpochIndex(epochs, targetTs);
  if (center === null) return null;

  const minEpochs = Math.max(1, (minConsecutiveMinutes * 60) / epochLengthSeconds);
  const maxIdx = Math.min(center + maxForwardEpochs, epochs.length - 1);

  const validOffsets: number[] = [];
  for (const [, end, len] of findSleepRuns(epochs)) {
    if (len >= minEpochs && end <= maxIdx) validOffsets.push(end);
  }
  if (validOffsets.length === 0) return null;

  // Prefer offsets AT or AFTER the diary time
  const after = validOffsets.filter((idx) => idx >= center);
  const before = validOffsets.filter((idx) => idx < center);
  const pool = after.length > 0 ? after : before;

  let best: number | null = null;
  let bestDist = Infinity;
  for (const idx of pool) {
    const dist = Math.abs(idx - center);
    if (dist < bestDist || (dist === bestDist && best !== null && idx > best)) {
      bestDist = dist;
      best = idx;
    }
  }
  return best;
}

function findValidOnsetAtOrAfter(
  epochs: EpochData[],
  targetTs: number,
  minConsecutive: number,
): number | null {
  let i = nearestEpochIndex(epochs, targetTs);
  if (i === null) return null;

  // If in the middle of a sleep run, skip past it
  if (i > 0 && epochs[i]!.sleepScore === 1 && epochs[i - 1]!.sleepScore === 1) {
    while (i < epochs.length && epochs[i]!.sleepScore === 1) i++;
  }

  // Search forward for next valid W→S onset
  while (i < epochs.length) {
    if (epochs[i]!.sleepScore === 1) {
      const runStart = i;
      while (i < epochs.length && epochs[i]!.sleepScore === 1) i++;
      if (i - runStart >= minConsecutive) return runStart;
    } else {
      i++;
    }
  }
  return null;
}

function findValidOnsetNearBounded(
  epochs: EpochData[],
  targetTs: number,
  minConsecutive: number,
  maxDistanceEpochs: number = 60,
): number | null {
  const center = nearestEpochIndex(epochs, targetTs);
  if (center === null) return null;

  const lo = Math.max(0, center - maxDistanceEpochs);
  const hi = Math.min(epochs.length - 1, center + maxDistanceEpochs);

  const validOnsets: number[] = [];
  for (const [start, , len] of findSleepRuns(epochs)) {
    if (len >= minConsecutive && start >= lo && start <= hi) {
      validOnsets.push(start);
    }
  }
  if (validOnsets.length === 0) return null;

  let best: number | null = null;
  let bestDist = Infinity;
  for (const idx of validOnsets) {
    const dist = Math.abs(idx - center);
    if (dist < bestDist) { bestDist = dist; best = idx; }
  }
  return best;
}

function placeMainSleep(
  epochs: EpochData[],
  diary: DiaryDay,
  config: PlacementConfig,
): [number, number] | null {
  if (diary.sleepOnset === null || diary.wakeTime === null) return null;

  const onsetIdx = findValidOnsetNear(
    epochs, diary.sleepOnset, config.onsetMinConsecutiveSleep,
  );

  const maxForwardEpochs = 60;
  const offsetIdx = findValidOffsetNearBounded(
    epochs, diary.wakeTime, config.offsetMinConsecutiveMinutes,
    config.epochLengthSeconds, maxForwardEpochs,
  );

  if (onsetIdx === null || offsetIdx === null) return null;
  if (onsetIdx >= offsetIdx) return null;

  let finalOnset = onsetIdx;

  // Rule 8: if onset is before in-bed time, clamp to in-bed time
  if (diary.inBedTime !== null && epochs[finalOnset]!.timestamp < diary.inBedTime) {
    const clamped = findValidOnsetAtOrAfter(
      epochs, diary.inBedTime, config.onsetMinConsecutiveSleep,
    );
    if (clamped !== null && clamped < offsetIdx) {
      finalOnset = clamped;
    }
  }

  return [finalOnset, offsetIdx];
}

function placeNaps(
  epochs: EpochData[],
  diary: DiaryDay,
  mainOnset: number | null,
  mainOffset: number | null,
  config: PlacementConfig,
): Array<[number, number]> {
  const naps: Array<[number, number]> = [];
  const minEpochs = config.napMinConsecutiveEpochs;
  const maxSearchEpochs = 60;

  for (const napPeriod of diary.napPeriods) {
    if (napPeriod.startTime === null || napPeriod.endTime === null) continue;

    const onsetIdx = findValidOnsetNearBounded(
      epochs, napPeriod.startTime,
      config.onsetMinConsecutiveSleep,
      maxSearchEpochs,
    );
    const offsetIdx = findValidOffsetNearBounded(
      epochs, napPeriod.endTime,
      config.offsetMinConsecutiveMinutes,
      config.epochLengthSeconds,
      maxSearchEpochs,
    );

    if (onsetIdx === null || offsetIdx === null) continue;
    if (onsetIdx >= offsetIdx) continue;
    if (offsetIdx - onsetIdx + 1 < minEpochs) continue;

    // Must not overlap with main sleep
    if (mainOnset !== null && mainOffset !== null) {
      if (onsetIdx <= mainOffset && offsetIdx >= mainOnset) continue;
    }

    naps.push([onsetIdx, offsetIdx]);
  }

  return naps;
}

// =============================================================================
// AM/PM Correction
// =============================================================================

function flipAmPm(timeStr: string): string | null {
  const s = timeStr.trim();
  const upper = s.toUpperCase();
  if (upper.includes("PM")) {
    const idx = upper.indexOf("PM");
    return s.substring(0, idx) + "AM" + s.substring(idx + 2);
  } else if (upper.includes("AM")) {
    const idx = upper.indexOf("AM");
    return s.substring(0, idx) + "PM" + s.substring(idx + 2);
  }
  return null;
}

function diaryTimesPlausible(
  onsetTs: number | null,
  wakeTs: number | null,
  dataStartTs: number,
  dataEndTs: number,
): boolean {
  if (onsetTs === null || wakeTs === null) return false;
  if (wakeTs <= onsetTs) return false;
  const gapHours = (wakeTs - onsetTs) / 3600;
  if (gapHours < 2 || gapHours > 18) return false;
  const margin = 2 * 3600; // 2 hours in seconds
  if (onsetTs < dataStartTs - margin || onsetTs > dataEndTs + margin) return false;
  if (wakeTs < dataStartTs - margin || wakeTs > dataEndTs + margin) return false;
  return true;
}

// =============================================================================
// Time Parsing
// =============================================================================

function parseTimeTo24h(timeStr: string): [number, number] | null {
  const s = timeStr.trim().toUpperCase();
  const isPM = s.includes("PM");
  const isAM = s.includes("AM");
  const clean = s.replace(/PM/g, "").replace(/AM/g, "").trim();

  const parts = clean.split(":");
  if (parts.length < 2) return null;
  let h = parseInt(parts[0]!, 10);
  const m = parseInt(parts[1]!, 10);
  if (isNaN(h) || isNaN(m)) return null;

  if (isAM || isPM) {
    if (h === 12) h = isAM ? 0 : 12;
    else if (isPM) h += 12;
  }
  if (h < 0 || h > 23 || m < 0 || m > 59) return null;
  return [h, m];
}

/**
 * Parse a time string to Unix timestamp (seconds).
 * @param isEvening If true, times < 12:00 are treated as next day (overnight onset).
 *                  If false, times < 18:00 are treated as next day (wake/end times).
 */
function parseDiaryTime(
  timeStr: string,
  analysisDateStr: string,
  isEvening: boolean,
): number | null {
  const parsed = parseTimeTo24h(timeStr);
  if (parsed === null) return null;
  const [h, m] = parsed;

  // Build UTC date from analysis date
  const d = new Date(analysisDateStr + "T00:00:00Z");
  if (isEvening && h < 12) d.setUTCDate(d.getUTCDate() + 1);
  else if (!isEvening && h < 18) d.setUTCDate(d.getUTCDate() + 1);
  d.setUTCHours(h, m, 0, 0);
  return d.getTime() / 1000; // seconds
}

/**
 * Parse nap time: no overnight shifting. Placed on analysis date as-is.
 */
function parseNapTime(timeStr: string, analysisDateStr: string): number | null {
  const parsed = parseTimeTo24h(timeStr);
  if (parsed === null) return null;
  const [h, m] = parsed;
  const d = new Date(analysisDateStr + "T00:00:00Z");
  d.setUTCHours(h, m, 0, 0);
  return d.getTime() / 1000;
}

function tryAmPmCorrections(
  onsetStr: string | null,
  wakeStr: string | null,
  bedStr: string | null,
  analysisDate: string,
  dataStartTs: number,
  dataEndTs: number,
): {
  onsetTs: number | null;
  wakeTs: number | null;
  bedTs: number | null;
  notes: string[];
} {
  const onsetTs = onsetStr ? parseDiaryTime(onsetStr, analysisDate, true) : null;
  let wakeTs = wakeStr ? parseDiaryTime(wakeStr, analysisDate, false) : null;
  const bedTs = bedStr ? parseDiaryTime(bedStr, analysisDate, true) : null;

  // Standard overnight fix
  if (wakeTs !== null && onsetTs !== null && wakeTs <= onsetTs) {
    wakeTs += 86400;
  }

  if (diaryTimesPlausible(onsetTs, wakeTs, dataStartTs, dataEndTs)) {
    return { onsetTs, wakeTs, bedTs, notes: [] };
  }

  // Try flip combinations
  const flippedWake = wakeStr ? flipAmPm(wakeStr) : null;
  const flippedOnset = onsetStr ? flipAmPm(onsetStr) : null;

  interface Attempt {
    altOnsetStr: string | null;
    altWakeStr: string | null;
    onsetNote: string;
    wakeNote: string;
  }
  const attempts: Attempt[] = [];

  if (flippedWake) {
    attempts.push({ altOnsetStr: onsetStr, altWakeStr: flippedWake, onsetNote: "", wakeNote: `wake ${wakeStr} → ${flippedWake}` });
  }
  if (flippedOnset) {
    attempts.push({ altOnsetStr: flippedOnset, altWakeStr: wakeStr, onsetNote: `onset ${onsetStr} → ${flippedOnset}`, wakeNote: "" });
  }
  if (flippedOnset && flippedWake) {
    attempts.push({ altOnsetStr: flippedOnset, altWakeStr: flippedWake, onsetNote: `onset ${onsetStr} → ${flippedOnset}`, wakeNote: `wake ${wakeStr} → ${flippedWake}` });
  }

  for (const att of attempts) {
    const altOnset = att.altOnsetStr ? parseDiaryTime(att.altOnsetStr, analysisDate, true) : null;
    let altWake = att.altWakeStr ? parseDiaryTime(att.altWakeStr, analysisDate, false) : null;
    if (altWake !== null && altOnset !== null && altWake <= altOnset) altWake += 86400;

    if (diaryTimesPlausible(altOnset, altWake, dataStartTs, dataEndTs)) {
      const notesParts: string[] = [];
      if (att.onsetNote) notesParts.push(att.onsetNote);
      if (att.wakeNote) notesParts.push(att.wakeNote);

      let altBed = bedTs;
      if (att.onsetNote && bedStr) {
        const flippedBed = flipAmPm(bedStr);
        if (flippedBed) altBed = parseDiaryTime(flippedBed, analysisDate, true);
      }

      return {
        onsetTs: altOnset,
        wakeTs: altWake,
        bedTs: altBed,
        notes: ["Corrected diary AM/PM: " + notesParts.join(", ")],
      };
    }
  }

  return { onsetTs, wakeTs, bedTs, notes: [] };
}

// =============================================================================
// Public API: Auto-Score
// =============================================================================

export function runAutoScoring(opts: {
  timestamps: number[];
  activityCounts: number[];
  sleepScores: number[];
  choiNonwear?: number[] | null;
  diaryBedTime?: string | null;
  diaryOnsetTime?: string | null;
  diaryWakeTime?: string | null;
  diaryNaps?: Array<[string | null, string | null]> | null;
  diaryNonwear?: Array<[string | null, string | null]> | null;
  analysisDate?: string | null;
  epochLengthSeconds?: number;
  onsetMinConsecutiveSleep?: number;
  offsetMinConsecutiveMinutes?: number;
}): AutoScoreResult {
  const config: PlacementConfig = {
    ...DEFAULT_CONFIG,
    epochLengthSeconds: opts.epochLengthSeconds ?? 60,
    onsetMinConsecutiveSleep: opts.onsetMinConsecutiveSleep ?? 3,
    offsetMinConsecutiveMinutes: opts.offsetMinConsecutiveMinutes ?? 5,
  };

  // Build epoch data
  const nonwearBools = opts.choiNonwear
    ? opts.choiNonwear.map((v) => v === 1)
    : new Array(opts.timestamps.length).fill(false);

  const epochs: EpochData[] = opts.timestamps.map((ts, i) => ({
    index: i,
    timestamp: ts,
    sleepScore: opts.sleepScores[i] ?? 0,
    activity: opts.activityCounts[i] ?? 0,
    isChoiNonwear: nonwearBools[i] ?? false,
  }));

  if (epochs.length === 0) {
    return { sleep_markers: [], nap_markers: [], notes: ["No activity data"] };
  }

  // Build diary
  let diary: DiaryDay | null = null;
  let ampmNotes: string[] = [];
  const analysisDate = opts.analysisDate;

  if (analysisDate) {
    const onsetStr = opts.diaryOnsetTime || opts.diaryBedTime || null;
    const dataStartTs = epochs[0]!.timestamp;
    const dataEndTs = epochs[epochs.length - 1]!.timestamp;

    const corrected = tryAmPmCorrections(
      onsetStr, opts.diaryWakeTime ?? null, opts.diaryBedTime ?? null,
      analysisDate, dataStartTs, dataEndTs,
    );
    ampmNotes = corrected.notes;

    // Parse nap periods
    const napPeriods: DiaryPeriod[] = [];
    for (const [napStart, napEnd] of opts.diaryNaps ?? []) {
      if (napStart && napEnd) {
        const ns = parseNapTime(napStart, analysisDate);
        let ne = parseNapTime(napEnd, analysisDate);
        if (ns !== null && ne !== null && ne <= ns) ne += 86400;
        if (ns !== null && ne !== null) {
          napPeriods.push({ startTime: ns, endTime: ne, periodType: "nap" });
        }
      }
    }

    // Parse nonwear periods
    const nwPeriods: DiaryPeriod[] = [];
    for (const [nwStart, nwEnd] of opts.diaryNonwear ?? []) {
      if (nwStart && nwEnd) {
        const ns = parseDiaryTime(nwStart, analysisDate, false);
        const ne = parseDiaryTime(nwEnd, analysisDate, false);
        if (ns !== null && ne !== null) {
          nwPeriods.push({ startTime: ns, endTime: ne, periodType: "nonwear" });
        }
      }
    }

    if (corrected.onsetTs !== null || corrected.wakeTs !== null) {
      diary = {
        inBedTime: corrected.bedTs ?? corrected.onsetTs,
        sleepOnset: corrected.onsetTs,
        wakeTime: corrected.wakeTs,
        napPeriods,
        nonwearPeriods: nwPeriods,
      };
    }
  }

  const notes: string[] = [...ampmNotes];
  if (config.onsetMinConsecutiveSleep !== 3 || config.offsetMinConsecutiveMinutes !== 5) {
    notes.push(`Detection rule: ${config.onsetMinConsecutiveSleep}S/${config.offsetMinConsecutiveMinutes}S`);
  }

  const sleepMarkers: AutoScoreResult["sleep_markers"] = [];
  const napMarkers: AutoScoreResult["nap_markers"] = [];

  // Main sleep placement
  let mainResult: [number, number] | null = null;

  if (diary && diary.sleepOnset !== null && diary.wakeTime !== null) {
    mainResult = placeMainSleep(epochs, diary, config);
    if (mainResult) {
      const [onsetIdx, offsetIdx] = mainResult;
      const onsetTime = epochs[onsetIdx]!.timestamp;
      const offsetTime = epochs[offsetIdx]!.timestamp;
      const durationMin = (offsetIdx - onsetIdx + 1) * config.epochLengthSeconds / 60;

      notes.push(
        `Main sleep: ${formatTime(onsetTime)} - ${formatTime(offsetTime)} ` +
        `(${durationMin.toFixed(0)} min) — ` +
        `diary onset ${formatTime(diary.sleepOnset!)}, ` +
        `diary wake ${formatTime(diary.wakeTime!)}`,
      );

      sleepMarkers.push({
        onset_timestamp: onsetTime,
        offset_timestamp: offsetTime,
        marker_type: "MAIN_SLEEP",
        marker_index: 1,
      });
    } else {
      notes.push(
        `No valid sleep period found near diary times ` +
        `(onset ${formatTime(diary.sleepOnset!)}, wake ${formatTime(diary.wakeTime!)})`,
      );
    }
  } else if (diary && diary.sleepOnset === null && diary.wakeTime === null) {
    notes.push("Diary exists but no onset/wake times — auto-score requires diary times");
  } else {
    notes.push("No diary data for this date — auto-score requires diary");
  }

  if (!mainResult) {
    notes.push("No main sleep period detected");
  }

  // Nap placement
  if (diary && diary.napPeriods.length > 0) {
    const mainOnset = mainResult ? mainResult[0] : null;
    const mainOffset = mainResult ? mainResult[1] : null;
    const napResults = placeNaps(epochs, diary, mainOnset, mainOffset, config);

    for (let i = 0; i < napResults.length; i++) {
      const [napOn, napOff] = napResults[i]!;
      const napOnsetTime = epochs[napOn]!.timestamp;
      const napOffsetTime = epochs[napOff]!.timestamp;
      const durationMin = (napOff - napOn + 1) * config.epochLengthSeconds / 60;

      notes.push(
        `Nap ${i + 1}: ${formatTime(napOnsetTime)} - ${formatTime(napOffsetTime)} (${durationMin.toFixed(0)} min)`,
      );

      napMarkers.push({
        onset_timestamp: napOnsetTime,
        offset_timestamp: napOffsetTime,
        marker_type: "NAP",
        marker_index: sleepMarkers.length + i + 1,
      });
    }
  }

  return { sleep_markers: sleepMarkers, nap_markers: napMarkers, notes };
}

// =============================================================================
// Public API: Nonwear Auto-Placement
// =============================================================================

function isNullLike(value: string | null | undefined): boolean {
  if (!value) return true;
  const normalized = value.trim().toLowerCase();
  return normalized === "" || normalized === "nan" || normalized === "none" || normalized === "null";
}

export function placeNonwearMarkers(opts: {
  timestamps: number[];
  activityCounts: number[];
  diaryNonwear: Array<[string | null, string | null]>;
  choiNonwear: number[] | null;
  sensorNonwearPeriods: Array<[number, number]>;
  existingSleepMarkers: Array<[number, number]>;
  analysisDate: string;
  epochLengthSeconds?: number;
  threshold?: number;
  maxExtensionMinutes?: number;
  minDurationMinutes?: number;
}): NonwearPlacementResult {
  const epochLen = opts.epochLengthSeconds ?? 60;
  const threshold = opts.threshold ?? 0;
  const maxExtMin = opts.maxExtensionMinutes ?? 30;
  const minDurMin = opts.minDurationMinutes ?? 10;
  const minEpochs = Math.max(1, (minDurMin * 60) / epochLen);

  if (!opts.timestamps.length || !opts.activityCounts.length) {
    return { nonwear_markers: [], notes: ["No activity data"] };
  }

  const notes: string[] = [];
  const markers: NonwearPlacementResult["nonwear_markers"] = [];

  // Parse diary nonwear periods
  const validDiaryPeriods: Array<{ startTs: number; endTs: number; idx: number }> = [];
  for (let i = 0; i < opts.diaryNonwear.length; i++) {
    const [nwStartStr, nwEndStr] = opts.diaryNonwear[i]!;
    if (isNullLike(nwStartStr) || isNullLike(nwEndStr)) continue;
    const nwStartTs = parseDiaryTime(nwStartStr!, opts.analysisDate, true);
    let nwEndTs = parseDiaryTime(nwEndStr!, opts.analysisDate, true);
    if (nwStartTs === null || nwEndTs === null) continue;
    if (nwEndTs <= nwStartTs) nwEndTs += 86400;
    validDiaryPeriods.push({ startTs: nwStartTs, endTs: nwEndTs, idx: i + 1 });
  }

  if (validDiaryPeriods.length === 0) {
    notes.push("No diary nonwear periods found for this date");
  }

  // Build Choi nonwear set
  const choiSet = new Set<number>();
  if (opts.choiNonwear) {
    for (let i = 0; i < opts.choiNonwear.length; i++) {
      if (opts.choiNonwear[i] === 1) choiSet.add(i);
    }
  }

  // Build sensor nonwear ranges as epoch indices
  const sensorRanges: Array<[number, number]> = [];
  for (const [snwStart, snwEnd] of opts.sensorNonwearPeriods) {
    const si = findNearestEpoch(opts.timestamps, snwStart);
    const ei = findNearestEpoch(opts.timestamps, snwEnd);
    if (si !== null && ei !== null) sensorRanges.push([si, ei]);
  }

  const hasExternalSignals = choiSet.size > 0 || sensorRanges.length > 0;

  for (const { startTs, endTs, idx: diaryIdx } of validDiaryPeriods) {
    const startIdx = findNearestEpoch(opts.timestamps, startTs);
    const endIdx = findNearestEpoch(opts.timestamps, endTs);
    if (startIdx === null || endIdx === null) {
      notes.push(`Nonwear ${diaryIdx}: diary times outside data range, skipped`);
      continue;
    }

    // Extend backward
    let extStart = startIdx;
    const maxExtEpochs = (maxExtMin * 60) / epochLen;
    while (extStart > 0) {
      const candidate = extStart - 1;
      if (opts.activityCounts[candidate]! > threshold) break;
      if (hasExternalSignals) {
        if (!epochInNonwearSignal(candidate, choiSet, sensorRanges)) break;
      } else if (startIdx - candidate >= maxExtEpochs) {
        break;
      }
      extStart = candidate;
    }

    // Extend forward
    let extEnd = endIdx;
    while (extEnd < opts.timestamps.length - 1) {
      const candidate = extEnd + 1;
      if (opts.activityCounts[candidate]! > threshold) break;
      if (hasExternalSignals) {
        if (!epochInNonwearSignal(candidate, choiSet, sensorRanges)) break;
      } else if (candidate - endIdx >= maxExtEpochs) {
        break;
      }
      extEnd = candidate;
    }

    // Count zero-activity epochs
    let zeroEpochs = 0;
    for (let i = extStart; i <= extEnd; i++) {
      if (opts.activityCounts[i]! <= threshold) zeroEpochs++;
    }
    const totalEpochs = extEnd - extStart + 1;

    // Require 80% zero
    if (totalEpochs > 0 && zeroEpochs / totalEpochs < 0.8) {
      notes.push(`Nonwear ${diaryIdx}: too much activity (${totalEpochs - zeroEpochs}/${totalEpochs} above threshold), skipped`);
      continue;
    }

    if (zeroEpochs < minEpochs) {
      notes.push(`Nonwear ${diaryIdx}: only ${zeroEpochs} epochs of zero activity, need ${minDurMin} min minimum, skipped`);
      continue;
    }

    // Check overlap with sleep markers
    const nwStartTs = opts.timestamps[extStart]!;
    const nwEndTs = opts.timestamps[extEnd]!;
    const overlapsSleepMarker = opts.existingSleepMarkers.some(
      ([smStart, smEnd]) => nwStartTs < smEnd && nwEndTs > smStart,
    );
    if (overlapsSleepMarker) {
      notes.push(`Nonwear ${diaryIdx}: overlaps with sleep marker, skipped`);
      continue;
    }

    notes.push(`Nonwear ${diaryIdx}: ${formatTime(startTs)}-${formatTime(endTs)}`);
    markers.push({
      start_timestamp: nwStartTs,
      end_timestamp: nwEndTs,
      marker_index: markers.length + 1,
    });
  }

  // Second pass: Choi + sensor overlap with zero activity
  if (choiSet.size > 0 && sensorRanges.length > 0) {
    const sensorSet = new Set<number>();
    for (const [si, ei] of sensorRanges) {
      for (let i = si; i <= ei; i++) sensorSet.add(i);
    }

    const bothNw: number[] = [];
    for (const i of choiSet) {
      if (sensorSet.has(i) && i < opts.activityCounts.length && opts.activityCounts[i]! <= threshold) {
        bothNw.push(i);
      }
    }
    bothNw.sort((a, b) => a - b);

    if (bothNw.length > 0) {
      // Extract contiguous runs
      const runs: Array<[number, number]> = [];
      let runStart = bothNw[0]!;
      let prev = bothNw[0]!;
      for (let j = 1; j < bothNw.length; j++) {
        if (bothNw[j]! === prev + 1) {
          prev = bothNw[j]!;
        } else {
          runs.push([runStart, prev]);
          runStart = bothNw[j]!;
          prev = bothNw[j]!;
        }
      }
      runs.push([runStart, prev]);

      const placedRanges = markers.map((m) => [m.start_timestamp, m.end_timestamp] as [number, number]);

      for (const [runStartIdx, runEndIdx] of runs) {
        const durEpochs = runEndIdx - runStartIdx + 1;
        if (durEpochs < minEpochs) continue;

        const runStartTs = opts.timestamps[runStartIdx]!;
        const runEndTs = opts.timestamps[runEndIdx]!;

        const overlapsSleep = opts.existingSleepMarkers.some(
          ([smStart, smEnd]) => runStartTs < smEnd && runEndTs > smStart,
        );
        if (overlapsSleep) continue;

        const overlapsPlaced = placedRanges.some(
          ([pmStart, pmEnd]) => runStartTs < pmEnd && runEndTs > pmStart,
        );
        if (overlapsPlaced) continue;

        const durMin = (durEpochs * epochLen) / 60;
        notes.push(`Nonwear (Choi+sensor): ${formatTime(runStartTs)}-${formatTime(runEndTs)} (${durMin.toFixed(0)}min)`);
        markers.push({
          start_timestamp: runStartTs,
          end_timestamp: runEndTs,
          marker_index: markers.length + 1,
        });
      }
    }
  }

  if (markers.length === 0) {
    notes.push("No valid nonwear periods detected");
  }

  return { nonwear_markers: markers, notes };
}

// =============================================================================
// Helpers
// =============================================================================

function findNearestEpoch(timestamps: number[], targetTs: number): number | null {
  if (timestamps.length === 0) return null;
  let bestIdx = 0;
  let bestDiff = Math.abs(timestamps[0]! - targetTs);
  for (let i = 1; i < timestamps.length; i++) {
    const diff = Math.abs(timestamps[i]! - targetTs);
    if (diff < bestDiff) { bestDiff = diff; bestIdx = i; }
  }
  return bestIdx;
}

function epochInNonwearSignal(
  idx: number,
  choiSet: Set<number>,
  sensorRanges: Array<[number, number]>,
): boolean {
  if (choiSet.has(idx)) return true;
  return sensorRanges.some(([si, ei]) => idx >= si && idx <= ei);
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}
