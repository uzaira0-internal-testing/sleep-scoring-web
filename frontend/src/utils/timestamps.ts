/**
 * Timestamp conversion utilities.
 *
 * The backend stores timestamps as Unix seconds, while the frontend store
 * uses milliseconds for compatibility with JavaScript Date.
 *
 * Cutoff value: 10000000000 (year ~2286 in seconds, year ~1970 in ms)
 * - Values less than cutoff are assumed to be seconds
 * - Values greater than cutoff are assumed to be milliseconds
 */

/** Cutoff to distinguish seconds from milliseconds */
const SECONDS_MS_CUTOFF = 10000000000;

/**
 * Convert a timestamp to milliseconds.
 * Handles both seconds and milliseconds input.
 */
export function toMilliseconds(timestamp: number | null | undefined): number | null {
  if (timestamp === null || timestamp === undefined) return null;

  // If less than cutoff, it's in seconds - convert to milliseconds
  if (timestamp < SECONDS_MS_CUTOFF) {
    return timestamp * 1000;
  }
  // Already in milliseconds
  return timestamp;
}

/**
 * Convert a timestamp to seconds.
 * Handles both seconds and milliseconds input.
 */
export function toSeconds(timestamp: number | null | undefined): number | null {
  if (timestamp === null || timestamp === undefined) return null;

  // If greater than cutoff, it's in milliseconds - convert to seconds
  if (timestamp > SECONDS_MS_CUTOFF) {
    return timestamp / 1000;
  }
  // Already in seconds
  return timestamp;
}

/**
 * Check if a timestamp appears to be in seconds.
 */
export function isSeconds(timestamp: number): boolean {
  return timestamp < SECONDS_MS_CUTOFF;
}

/**
 * Check if a timestamp appears to be in milliseconds.
 */
export function isMilliseconds(timestamp: number): boolean {
  return timestamp > SECONDS_MS_CUTOFF;
}

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
