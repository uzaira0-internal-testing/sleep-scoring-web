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
 * Format timestamp as HH:MM (marker timestamps are in milliseconds)
 */
export function formatTime(timestamp: number | null): string {
  if (timestamp === null) return "--:--";
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
}

/**
 * Calculate and format duration between two timestamps (in milliseconds)
 */
export function formatDuration(start: number | null, end: number | null): string {
  if (start === null || end === null) return "--";
  const durationMs = end - start;
  const hours = Math.floor(durationMs / (1000 * 60 * 60));
  const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));
  return `${hours}h ${minutes}m`;
}

/**
 * Format time string for display (HH:MM)
 */
export function formatTimeDisplay(time: string | null | undefined): string {
  if (!time) return "--:--";
  return time;
}
