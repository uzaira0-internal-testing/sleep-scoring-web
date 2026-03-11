/**
 * Shared formatting utilities
 * Centralized formatting functions to avoid duplication across components.
 */

/**
 * Format minutes as hours and minutes (e.g., "1h 30m" or "45m")
 */
export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "--";
  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  if (hours === 0) return `${mins}m`;
  return `${hours}h ${mins}m`;
}

/**
 * Format a decimal as a percentage (e.g., "85.5%")
 */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "--";
  return `${value.toFixed(1)}%`;
}

/**
 * Format a number with specified decimal places
 */
export function formatNumber(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) return "--";
  return value.toFixed(decimals);
}

/**
 * Format timestamp as HH:MM (timestamps are in Unix seconds)
 */
export function formatTime(timestampSec: number | null): string {
  if (timestampSec === null) return "--:--";
  const date = new Date(timestampSec * 1000);
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
}

/**
 * Calculate and format duration between two timestamps (in Unix seconds)
 */
export function formatDuration(startSec: number | null, endSec: number | null): string {
  if (startSec === null || endSec === null) return "--";
  const durationSec = Math.max(0, endSec - startSec);
  const hours = Math.floor(durationSec / 3600);
  const minutes = Math.floor((durationSec % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

/**
 * Format time string for display (HH:MM)
 */
export function formatTimeDisplay(time: string | null | undefined): string {
  if (!time) return "--:--";
  return time;
}
