/**
 * Client-side sleep metric computation.
 * Ported from backend sleep_scoring_web/services/metrics.py (TudorLockeSleepMetricsCalculator).
 *
 * Operates on Uint8Array algorithm results (1=sleep, 0=wake) and marker timestamps.
 */
import { findMarkerIndexRange } from "@/utils/sleep-rules";

export interface SleepPeriodMetrics {
  totalSleepTimeMinutes: number;
  sleepEfficiency: number;
  wasoMinutes: number;
  sleepOnsetLatencyMinutes: number;
  numberOfAwakenings: number;
  timeInBedMinutes: number;
}

/**
 * Compute TST (total sleep time) in minutes for a sleep period.
 * @param scores - 1=sleep, 0=wake array for the period
 * @param epochMinutes - duration of each epoch in minutes (default 1)
 */
export function computeTST(scores: Uint8Array | number[], epochMinutes = 1): number {
  let sleepEpochs = 0;
  for (let i = 0; i < scores.length; i++) {
    if (scores[i] === 1) sleepEpochs++;
  }
  return sleepEpochs * epochMinutes;
}

/**
 * Compute sleep efficiency percentage.
 * SE = TST / TIB * 100
 */
export function computeSleepEfficiency(tst: number, timeInBedMinutes: number): number {
  if (timeInBedMinutes <= 0) return 0;
  return (tst / timeInBedMinutes) * 100;
}

/**
 * Compute SOL (sleep onset latency) in minutes.
 * SOL = number of wake epochs before the first sleep epoch.
 */
export function computeSOL(scores: Uint8Array | number[], epochMinutes = 1): number {
  for (let i = 0; i < scores.length; i++) {
    if (scores[i] === 1) return i * epochMinutes;
  }
  return scores.length * epochMinutes;
}

/**
 * Count number of awakening episodes within the period.
 * An awakening is a contiguous block of wake epochs after the first sleep epoch.
 */
export function countAwakenings(scores: Uint8Array | number[]): number {
  let firstSleep = -1;
  for (let i = 0; i < scores.length; i++) {
    if (scores[i] === 1) { firstSleep = i; break; }
  }
  if (firstSleep < 0) return 0;

  let awakenings = 0;
  let inWake = false;
  for (let i = firstSleep; i < scores.length; i++) {
    if (scores[i] === 0 && !inWake) {
      awakenings++;
      inWake = true;
    } else if (scores[i] === 1) {
      inWake = false;
    }
  }
  return awakenings;
}

/**
 * Compute full sleep period metrics from algorithm results within a marker range.
 *
 * @param algorithmResults - Full-day algorithm results array (1=sleep, 0=wake)
 * @param timestamps - Full-day epoch timestamps (must be in same units as onset/offset)
 * @param onset - Onset timestamp
 * @param offset - Offset timestamp
 * @param epochSeconds - Epoch duration in seconds (default 60)
 */
export function computePeriodMetrics(
  algorithmResults: Uint8Array | number[],
  timestamps: number[],
  onset: number,
  offset: number,
  epochSeconds = 60,
): SleepPeriodMetrics | null {
  if (!algorithmResults || algorithmResults.length === 0 || timestamps.length === 0) return null;
  if (onset == null || offset == null || onset >= offset) return null;

  // Find indices for the period (reuse existing index range utility)
  const range = findMarkerIndexRange(timestamps, onset, offset);
  if (!range || range.startIdx >= range.endIdx) return null;

  // Extract period scores
  const periodScores = algorithmResults.slice(range.startIdx, range.endIdx + 1);
  const epochMinutes = epochSeconds / 60;
  const tib = periodScores.length * epochMinutes;
  const tst = computeTST(periodScores, epochMinutes);
  const sol = computeSOL(periodScores, epochMinutes);
  const waso = Math.max(0, tib - tst - sol);
  const se = computeSleepEfficiency(tst, tib);
  const awakenings = countAwakenings(periodScores);

  return {
    totalSleepTimeMinutes: tst,
    sleepEfficiency: se,
    wasoMinutes: waso,
    sleepOnsetLatencyMinutes: sol,
    numberOfAwakenings: awakenings,
    timeInBedMinutes: tib,
  };
}
