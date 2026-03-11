/**
 * Timestamp utilities.
 * All timestamps in the app are Unix seconds.
 */

/**
 * Epoch duration in seconds (for marker snapping)
 */
export const EPOCH_DURATION_SECONDS = 60;

/**
 * Snap a timestamp (in seconds) to the nearest epoch boundary.
 */
export function snapToEpoch(timestampSec: number): number {
  return Math.round(timestampSec / EPOCH_DURATION_SECONDS) * EPOCH_DURATION_SECONDS;
}

/**
 * Convert a Date or ISO string to Unix seconds.
 */
export function dateToSeconds(date: Date | string | null | undefined): number | null {
  if (!date) return null;
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.getTime() / 1000;
}

/**
 * Convert Unix seconds to Date.
 */
export function secondsToDate(seconds: number | null | undefined): Date | null {
  if (seconds === null || seconds === undefined) return null;
  return new Date(seconds * 1000);
}
