/**
 * Night complexity (scoring difficulty) computation.
 *
 * Port of sleep_scoring_web/services/complexity.py.
 *
 * Pure computation — takes arrays of data and returns a score.
 * Score is 0–100, higher = easier to score. -1 = no diary (infinite complexity).
 */

// =============================================================================
// Helpers
// =============================================================================

function linearPenalty(value: number, low: number, high: number, maxPenalty: number): number {
  if (value <= low) return 0;
  if (value >= high) return maxPenalty;
  return maxPenalty * (value - low) / (high - low);
}

function nightWindowIndices(
  timestamps: number[],
  analysisDate: string,
  nightStartHour: number = 21,
  nightEndHour: number = 9,
): [number, number] {
  const d = new Date(analysisDate + "T00:00:00Z");
  const nightStartTs = d.getTime() / 1000 + nightStartHour * 3600;
  // Calculate duration: if end < start, it wraps past midnight
  const durationHours = nightEndHour <= nightStartHour
    ? (24 - nightStartHour + nightEndHour)
    : (nightEndHour - nightStartHour);
  const nightEndTs = nightStartTs + durationHours * 3600;

  let startIdx = 0;
  let endIdx = timestamps.length;
  for (let i = 0; i < timestamps.length; i++) {
    if (timestamps[i]! >= nightStartTs) { startIdx = i; break; }
  }
  for (let i = timestamps.length - 1; i >= 0; i--) {
    if (timestamps[i]! <= nightEndTs) { endIdx = i + 1; break; }
  }
  return [startIdx, endIdx];
}

function countTransitions(sleepScores: number[], start: number, end: number): number {
  let transitions = 0;
  const limit = Math.min(end, sleepScores.length);
  for (let i = start + 1; i < limit; i++) {
    if (sleepScores[i] !== sleepScores[i - 1]) transitions++;
  }
  return transitions;
}

function countSleepRuns(sleepScores: number[], start: number, end: number, minRun: number = 3): number {
  let runs = 0;
  let currentRun = 0;
  const limit = Math.min(end, sleepScores.length);
  for (let i = start; i < limit; i++) {
    if (sleepScores[i] === 1) {
      currentRun++;
    } else {
      if (currentRun >= minRun) runs++;
      currentRun = 0;
    }
  }
  if (currentRun >= minRun) runs++;
  return runs;
}

function totalSleepPeriodHours(
  sleepScores: number[],
  timestamps: number[],
  start: number,
  end: number,
  minRun: number = 3,
): number {
  let firstOnsetTs: number | null = null;
  let lastOffsetTs: number | null = null;
  const n = Math.min(end, sleepScores.length);
  let currentRun = 0;
  let runStart = start;

  for (let i = start; i < n; i++) {
    if (sleepScores[i] === 1) {
      if (currentRun === 0) runStart = i;
      currentRun++;
    } else {
      if (currentRun >= minRun) {
        if (firstOnsetTs === null) firstOnsetTs = timestamps[runStart]!;
        lastOffsetTs = timestamps[i - 1]!;
      }
      currentRun = 0;
    }
  }
  if (currentRun >= minRun) {
    if (firstOnsetTs === null) firstOnsetTs = timestamps[runStart]!;
    lastOffsetTs = timestamps[Math.min(n - 1, timestamps.length - 1)]!;
  }

  if (firstOnsetTs === null || lastOffsetTs === null) return 0;
  return (lastOffsetTs - firstOnsetTs) / 3600;
}

function countActivitySpikes(
  activityCounts: number[],
  start: number,
  end: number,
  threshold: number = 50,
): number {
  let spikes = 0;
  let inSpike = false;
  const limit = Math.min(end, activityCounts.length);
  for (let i = start; i < limit; i++) {
    if (activityCounts[i]! >= threshold) {
      if (!inSpike) { spikes++; inSpike = true; }
    } else {
      inSpike = false;
    }
  }
  return spikes;
}

function boundarySpikeScore(
  activityCounts: number[],
  idx: number,
  start: number,
  end: number,
  window: number = 10,
): number {
  const n = Math.min(end, activityCounts.length);
  if (idx < start || idx >= n) return 0;

  const beforeStart = Math.max(start, idx - window);
  const afterEnd = Math.min(n, idx + window);

  const before = activityCounts.slice(beforeStart, idx);
  const after = activityCounts.slice(idx, afterEnd);

  if (before.length === 0 || after.length === 0) return 0;

  const beforeMean = before.reduce((a, b) => a + b, 0) / before.length;
  const afterMean = after.reduce((a, b) => a + b, 0) / after.length;

  if (beforeMean < 1 && afterMean < 1) return 0;

  const high = Math.max(beforeMean, afterMean);
  const low = Math.min(beforeMean, afterMean);
  const ratio = high / Math.max(low, 0.1);

  if (ratio >= 3) return 1;
  if (ratio >= 1.5) return 0.5;
  return 0;
}

function boundaryClarityPenalty(
  activityCounts: number[],
  sleepScores: number[],
  start: number,
  end: number,
): number {
  if (end <= start || activityCounts.length === 0) return -10;

  let onsetIdx: number | null = null;
  let offsetIdx: number | null = null;
  const limit = Math.min(end, sleepScores.length);
  for (let i = start; i < limit; i++) {
    if (sleepScores[i] === 1) {
      if (onsetIdx === null) onsetIdx = i;
      offsetIdx = i;
    }
  }

  if (onsetIdx === null) return -10;

  const onsetScore = boundarySpikeScore(activityCounts, onsetIdx, start, end);
  const offsetScore = boundarySpikeScore(activityCounts, offsetIdx!, start, end);
  const avgClarity = (onsetScore + offsetScore) / 2;
  return -Math.round((1 - avgClarity) * 10 * 10) / 10;
}

function buildConfirmedNonwearMask(
  choiNonwear: number[],
  sensorNonwearPeriods: Array<[number, number]>,
  timestamps: number[],
): number[] {
  if (sensorNonwearPeriods.length === 0) {
    return new Array(choiNonwear.length).fill(0);
  }

  const sensorMask: number[] = new Array(timestamps.length).fill(0) as number[];
  for (const [nwStart, nwEnd] of sensorNonwearPeriods) {
    for (let i = 0; i < timestamps.length; i++) {
      if (nwStart <= timestamps[i]! && timestamps[i]! <= nwEnd) {
        sensorMask[i] = 1;
      }
    }
  }

  return choiNonwear.map((c, i) => c & (sensorMask[i] ?? 0));
}

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
  if (isPM && h !== 12) h += 12;
  else if (isAM && h === 12) h = 0;
  if (h < 0 || h > 23 || m < 0 || m > 59) return null;
  return [h, m];
}

function findSleepRunBoundaries(
  sleepScores: number[],
  timestamps: number[],
  start: number,
  end: number,
  minRun: number = 3,
): { onsets: number[]; offsets: number[] } {
  const onsets: number[] = [];
  const offsets: number[] = [];
  let inRun = false;
  let runStart = start;
  let runLength = 0;
  const limit = Math.min(end, sleepScores.length);

  for (let i = start; i < limit; i++) {
    if (sleepScores[i] === 1) {
      if (!inRun) { runStart = i; runLength = 0; inRun = true; }
      runLength++;
    } else {
      if (inRun && runLength >= minRun) {
        onsets.push(timestamps[runStart]!);
        offsets.push(timestamps[i - 1]!);
      }
      inRun = false;
      runLength = 0;
    }
  }
  if (inRun && runLength >= minRun) {
    onsets.push(timestamps[runStart]!);
    const last = Math.min(end, timestamps.length) - 1;
    offsets.push(timestamps[last]!);
  }
  return { onsets, offsets };
}

function nearestSleepBoundaryTs(
  timestamps: number[],
  sleepScores: number[],
  diaryTs: number,
  boundaryType: "onset" | "offset",
  searchWindowSec: number = 7200,
  minRun: number = 3,
): number | null {
  const windowStart = diaryTs - searchWindowSec;
  const windowEnd = diaryTs + searchWindowSec;
  const candidates: number[] = [];

  let i = 0;
  const n = sleepScores.length;
  while (i < n) {
    if (sleepScores[i] === 1) {
      const runStart = i;
      while (i < n && sleepScores[i] === 1) i++;
      if (i - runStart >= minRun) {
        const ts = boundaryType === "onset" ? timestamps[runStart]! : timestamps[i - 1]!;
        if (windowStart <= ts && ts <= windowEnd) candidates.push(ts);
      }
    } else {
      i++;
    }
  }

  if (candidates.length === 0) return null;
  return candidates.reduce((best, t) =>
    Math.abs(t - diaryTs) < Math.abs(best - diaryTs) ? t : best,
  );
}

function diaryAlgorithmGapPenalty(
  timestamps: number[],
  sleepScores: number[],
  diaryOnsetTime: string | null,
  diaryWakeTime: string | null,
  analysisDate: string,
): { penalty: number; onsetGap: number | null; offsetGap: number | null } {
  if (diaryOnsetTime === null && diaryWakeTime === null) {
    return { penalty: 0, onsetGap: null, offsetGap: null };
  }

  const d = new Date(analysisDate + "T00:00:00Z");
  let onsetGap: number | null = null;
  let offsetGap: number | null = null;
  let totalPenalty = 0;

  if (diaryOnsetTime) {
    const parsed = parseTimeTo24h(diaryOnsetTime);
    if (parsed) {
      const [h, m] = parsed;
      const onsetD = new Date(d.getTime());
      if (h < 12) onsetD.setUTCDate(onsetD.getUTCDate() + 1);
      onsetD.setUTCHours(h, m, 0, 0);
      const diaryTs = onsetD.getTime() / 1000;
      const nearest = nearestSleepBoundaryTs(timestamps, sleepScores, diaryTs, "onset");
      if (nearest !== null) {
        onsetGap = Math.abs(diaryTs - nearest) / 60;
        totalPenalty += linearPenalty(onsetGap, 10, 60, 7.5);
      }
    }
  }

  if (diaryWakeTime) {
    const parsed = parseTimeTo24h(diaryWakeTime);
    if (parsed) {
      const [h, m] = parsed;
      const wakeD = new Date(d.getTime());
      if (h < 12) wakeD.setUTCDate(wakeD.getUTCDate() + 1);
      wakeD.setUTCHours(h, m, 0, 0);
      const diaryTs = wakeD.getTime() / 1000;
      const nearest = nearestSleepBoundaryTs(timestamps, sleepScores, diaryTs, "offset");
      if (nearest !== null) {
        offsetGap = Math.abs(diaryTs - nearest) / 60;
        totalPenalty += linearPenalty(offsetGap, 10, 60, 7.5);
      }
    }
  }

  return { penalty: -totalPenalty, onsetGap, offsetGap };
}

function candidateAmbiguityPenalty(
  timestamps: number[],
  sleepScores: number[],
  choiNonwear: number[],
  diaryOnsetTs: number,
  diaryWakeTs: number,
  nightStart: number,
  nightEnd: number,
): number {
  let penalty = 0;
  const windowSec = 30 * 60;

  const { onsets, offsets } = findSleepRunBoundaries(sleepScores, timestamps, nightStart, nightEnd);

  const onsetNear = onsets.filter((t) => Math.abs(t - diaryOnsetTs) <= windowSec);
  const offsetNear = offsets.filter((t) => Math.abs(t - diaryWakeTs) <= windowSec);

  if (onsetNear.length === 0 || onsetNear.length >= 3) penalty += 5;
  else if (onsetNear.length === 2) penalty += 3;

  if (offsetNear.length === 0 || offsetNear.length >= 3) penalty += 5;
  else if (offsetNear.length === 2) penalty += 3;

  // Rule 8 check
  const candidatesForR8 = onsetNear.length > 0 ? onsetNear : onsets;
  if (candidatesForR8.some((t) => t < diaryOnsetTs - 60)) penalty += 3;

  // Rule 6: nonwear near candidate
  const candidatesToCheck = [...onsetNear, ...offsetNear];
  let nonwearNearCandidate = false;
  if (candidatesToCheck.length > 0) {
    for (const t of candidatesToCheck) {
      let bestIdx = 0;
      let bestDiff = Infinity;
      for (let i = 0; i < timestamps.length; i++) {
        const diff = Math.abs(timestamps[i]! - t);
        if (diff < bestDiff) { bestDiff = diff; bestIdx = i; }
      }
      const checkStart = Math.max(nightStart, bestIdx - 10);
      const checkEnd = Math.min(nightEnd, bestIdx + 10);
      for (let j = checkStart; j < Math.min(checkEnd, choiNonwear.length); j++) {
        if (choiNonwear[j] === 1) { nonwearNearCandidate = true; break; }
      }
      if (nonwearNearCandidate) break;
    }
  }

  if (nonwearNearCandidate && (onsetNear.length >= 2 || offsetNear.length >= 2)) {
    penalty += 2;
  }

  return Math.min(penalty, 15);
}

// =============================================================================
// Public API
// =============================================================================

export interface ComplexityResult {
  score: number; // 0-100 or -1
  features: Record<string, unknown>;
}

export function computePreComplexity(opts: {
  timestamps: number[];
  activityCounts: number[];
  sleepScores: number[];
  choiNonwear: number[];
  diaryOnsetTime: string | null;
  diaryWakeTime: string | null;
  diaryNapCount: number;
  analysisDate: string;
  sensorNonwearPeriods?: Array<[number, number]>;
  diaryNonwearTimes?: Array<[string, string]>;
  nightStartHour?: number;
  nightEndHour?: number;
}): ComplexityResult {
  const features: Record<string, unknown> = {};

  if (!opts.timestamps.length || !opts.sleepScores.length) {
    return { score: 0, features: { error: "insufficient_data" } };
  }

  // No diary = -1
  if (opts.diaryOnsetTime === null || opts.diaryWakeTime === null) {
    features.no_diary = opts.diaryOnsetTime === null && opts.diaryWakeTime === null;
    features.missing_onset = opts.diaryOnsetTime === null;
    features.missing_wake = opts.diaryWakeTime === null;
    return { score: -1, features };
  }

  // Diary nonwear overlapping diary sleep = -1
  if (opts.diaryNonwearTimes && opts.diaryOnsetTime && opts.diaryWakeTime) {
    const oh = parseTimeTo24h(opts.diaryOnsetTime);
    const wh = parseTimeTo24h(opts.diaryWakeTime);
    if (oh && wh) {
      const onsetMinFromNoon = oh[0] >= 12 ? (oh[0] - 12) * 60 + oh[1] : (oh[0] + 12) * 60 + oh[1];
      const wakeMinFromNoon = wh[0] < 12 ? (wh[0] + 12) * 60 + wh[1] : (wh[0] - 12) * 60 + wh[1];

      for (const [nwStartStr, nwEndStr] of opts.diaryNonwearTimes) {
        const ns = parseTimeTo24h(nwStartStr);
        const ne = parseTimeTo24h(nwEndStr);
        if (ns && ne) {
          const nwStartFromNoon = ns[0] >= 12 ? (ns[0] - 12) * 60 + ns[1] : (ns[0] + 12) * 60 + ns[1];
          const nwEndFromNoon = ne[0] >= 12 ? (ne[0] - 12) * 60 + ne[1] : (ne[0] + 12) * 60 + ne[1];
          if (nwStartFromNoon < wakeMinFromNoon && nwEndFromNoon > onsetMinFromNoon) {
            features.diary_nonwear_overlaps_sleep = true;
            return { score: -1, features };
          }
        }
      }
      features.diary_nonwear_overlaps_sleep = false;
    }
  }

  let totalPenalty = 0;
  const [nightStart, nightEnd] = nightWindowIndices(opts.timestamps, opts.analysisDate, opts.nightStartHour, opts.nightEndHour);
  const nightHours = Math.max((nightEnd - nightStart) / 60, 1);

  // 1. Transition density (-25 max)
  const transitions = countTransitions(opts.sleepScores, nightStart, nightEnd);
  const transitionRate = transitions / nightHours;
  const transP = linearPenalty(transitionRate, 2, 6, 25);
  features.transition_density = Math.round(transitionRate * 100) / 100;
  features.transition_density_penalty = Math.round(-transP * 10) / 10;
  totalPenalty += transP;

  // 3. Diary-algorithm gap (-15 max)
  const gap = diaryAlgorithmGapPenalty(
    opts.timestamps, opts.sleepScores,
    opts.diaryOnsetTime, opts.diaryWakeTime, opts.analysisDate,
  );
  features.diary_algorithm_gap_penalty = Math.round(gap.penalty * 10) / 10;
  if (gap.onsetGap !== null) features.diary_onset_gap_min = Math.round(gap.onsetGap * 10) / 10;
  if (gap.offsetGap !== null) features.diary_offset_gap_min = Math.round(gap.offsetGap * 10) / 10;
  totalPenalty += Math.abs(gap.penalty);

  // 4. Nonwear during night (-15 max or infinite)
  const confirmed = buildConfirmedNonwearMask(
    opts.choiNonwear, opts.sensorNonwearPeriods ?? [], opts.timestamps,
  );
  const choiNightEpochs = opts.choiNonwear.slice(nightStart, nightEnd).reduce((a, b) => a + b, 0);
  const confirmedEpochs = confirmed.slice(nightStart, nightEnd).reduce((a, b) => a + b, 0);
  const choiOnlyEpochs = choiNightEpochs - confirmedEpochs;
  const sleepNightEpochs = opts.sleepScores.slice(nightStart, nightEnd).reduce((a, b) => a + b, 0);
  const choiProportion = choiNightEpochs / Math.max(sleepNightEpochs, 1);

  features.confirmed_nonwear_night_epochs = confirmedEpochs;
  features.choi_only_nonwear_night_epochs = choiOnlyEpochs;
  features.choi_night_epochs = choiNightEpochs;
  features.sleep_night_epochs = sleepNightEpochs;
  features.choi_sleep_proportion = Math.round(choiProportion * 1000) / 1000;

  const nightSpikes = countActivitySpikes(opts.activityCounts, nightStart, nightEnd, 50);
  features.night_activity_spikes = nightSpikes;

  if (choiProportion >= 0.5 && choiNightEpochs >= 30) {
    if (nightSpikes === 0) {
      features.nonwear_exceeds_threshold = true;
      return { score: -1, features };
    }
    features.nonwear_exceeds_threshold = false;
  } else if (nightSpikes === 0 && choiNightEpochs >= 60) {
    features.flatline_suspicious = true;
    features.nonwear_exceeds_threshold = true;
    return { score: -1, features };
  } else {
    features.nonwear_exceeds_threshold = false;
    features.flatline_suspicious = false;
  }

  const effectiveNonwear = confirmedEpochs + choiOnlyEpochs * 0.5;
  let nwPenalty: number;
  if (effectiveNonwear === 0) nwPenalty = 0;
  else if (effectiveNonwear <= 30) nwPenalty = linearPenalty(effectiveNonwear, 0, 30, 10);
  else nwPenalty = 15;
  features.effective_nonwear_epochs = Math.round(effectiveNonwear * 10) / 10;
  features.nonwear_night_penalty = Math.round(-nwPenalty * 10) / 10;
  totalPenalty += nwPenalty;

  // 5. Sleep run count (-5 max)
  const runCount = countSleepRuns(opts.sleepScores, nightStart, nightEnd);
  let runPenalty: number;
  if (runCount <= 10) runPenalty = 0;
  else if (runCount <= 15) runPenalty = 2;
  else if (runCount <= 20) runPenalty = 3;
  else runPenalty = 5;
  features.sleep_run_count = runCount;
  features.sleep_run_penalty = -runPenalty;
  totalPenalty += runPenalty;

  // 6. Duration typicality (-10 max)
  const sleepPeriodHours = totalSleepPeriodHours(opts.sleepScores, opts.timestamps, nightStart, nightEnd);
  let durPenalty: number;
  if (sleepPeriodHours >= 6 && sleepPeriodHours <= 9) durPenalty = 0;
  else if ((sleepPeriodHours >= 4 && sleepPeriodHours < 6) || (sleepPeriodHours > 9 && sleepPeriodHours <= 11)) durPenalty = 5;
  else durPenalty = 10;
  features.sleep_period_hours = Math.round(sleepPeriodHours * 10) / 10;
  features.duration_typicality_penalty = -durPenalty;
  totalPenalty += durPenalty;

  // 7. Nap complexity (-5 max)
  const naps = Math.max(0, Math.min(opts.diaryNapCount, 3));
  const napPenalties: Record<number, number> = { 0: 0, 1: 2, 2: 3, 3: 5 };
  const napPenalty = napPenalties[naps] ?? 5;
  features.nap_count = naps;
  features.nap_complexity_penalty = -napPenalty;
  totalPenalty += napPenalty;

  // 8. Boundary clarity (-10 max)
  const bcPenalty = boundaryClarityPenalty(opts.activityCounts, opts.sleepScores, nightStart, nightEnd);
  features.boundary_clarity_penalty = Math.round(bcPenalty * 10) / 10;
  totalPenalty += Math.abs(bcPenalty);

  // 9. Candidate ambiguity (-15 max)
  const oh = parseTimeTo24h(opts.diaryOnsetTime);
  const wh = parseTimeTo24h(opts.diaryWakeTime);
  if (!oh || !wh) {
    // Malformed diary times — skip candidate ambiguity penalty
    features.candidate_ambiguity_penalty = 0;
    features.total_penalty = Math.round(-totalPenalty * 10) / 10;
    return { score: Math.max(0, Math.round(100 - totalPenalty)), features };
  }
  const onsetD = new Date(opts.analysisDate + "T00:00:00Z");
  if (oh[0] < 12) onsetD.setUTCDate(onsetD.getUTCDate() + 1);
  onsetD.setUTCHours(oh[0], oh[1], 0, 0);
  const diaryOnsetTs = onsetD.getTime() / 1000;

  const wakeD = new Date(opts.analysisDate + "T00:00:00Z");
  if (wh[0] < 12) wakeD.setUTCDate(wakeD.getUTCDate() + 1);
  wakeD.setUTCHours(wh[0], wh[1], 0, 0);
  const diaryWakeTs = wakeD.getTime() / 1000;

  const caPenalty = candidateAmbiguityPenalty(
    opts.timestamps, opts.sleepScores, opts.choiNonwear,
    diaryOnsetTs, diaryWakeTs, nightStart, nightEnd,
  );
  features.candidate_ambiguity_penalty = Math.round(-caPenalty * 10) / 10;
  totalPenalty += caPenalty;

  const score = Math.max(0, Math.round(100 - totalPenalty));
  features.total_penalty = Math.round(-totalPenalty * 10) / 10;
  return { score, features };
}

export function computePostComplexity(
  complexityPre: number,
  features: Record<string, unknown>,
  sleepMarkers: Array<[number, number]>,
  sleepScores: number[],
  timestamps: number[],
): ComplexityResult {
  const updated = { ...features };
  let adjustment = 0;

  if (!sleepMarkers.length || !timestamps.length || !sleepScores.length) {
    updated.post_adjustment = 0;
    return { score: Math.max(0, Math.min(100, complexityPre)), features: updated };
  }

  // 1. Marker-algorithm alignment
  let algoOnsetTs: number | null = null;
  let algoOffsetTs: number | null = null;
  for (let i = 0; i < sleepScores.length; i++) {
    if (sleepScores[i] === 1) {
      if (algoOnsetTs === null) algoOnsetTs = timestamps[i]!;
      algoOffsetTs = timestamps[i]!;
    }
  }

  if (algoOnsetTs !== null && algoOffsetTs !== null) {
    const closestOnsetDist = Math.min(...sleepMarkers.map(([on]) => Math.abs(on - algoOnsetTs!)));
    const closestOffsetDist = Math.min(...sleepMarkers.map(([, off]) => Math.abs(off - algoOffsetTs!)));

    const onsetEpochs = closestOnsetDist / 60;
    const offsetEpochs = closestOffsetDist / 60;
    const avgEpochs = (onsetEpochs + offsetEpochs) / 2;

    if (avgEpochs <= 5) {
      adjustment += 5;
      updated.marker_alignment = "close";
    } else if (avgEpochs > 30) {
      adjustment -= 5;
      updated.marker_alignment = "far";
    } else {
      updated.marker_alignment = "moderate";
    }
    updated.marker_alignment_epochs = Math.round(avgEpochs * 10) / 10;
  }

  // 2. Period count unexpected
  let runs = 0;
  let currentRun = 0;
  for (const s of sleepScores) {
    if (s === 1) currentRun++;
    else {
      if (currentRun >= 3) runs++;
      currentRun = 0;
    }
  }
  if (currentRun >= 3) runs++;

  if (sleepMarkers.length !== runs && runs > 0) {
    adjustment -= 5;
    updated.period_count_penalty = -5;
  } else {
    updated.period_count_penalty = 0;
  }

  updated.post_adjustment = adjustment;
  const score = Math.max(0, Math.min(100, complexityPre + adjustment));
  return { score, features: updated };
}
