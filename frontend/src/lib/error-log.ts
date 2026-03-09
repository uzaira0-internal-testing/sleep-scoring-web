const STORAGE_KEY = "sleep-scoring-error-log";
const MAX_ENTRIES = 20;

interface ErrorLogEntry {
  message: string;
  stack?: string;
  componentStack?: string;
  timestamp: string;
  url: string;
}

/**
 * Append an error entry to the persistent error log in localStorage.
 * Silently ignores failures (localStorage full, unavailable, etc.)
 */
export function appendErrorLog(entry: Omit<ErrorLogEntry, "timestamp" | "url">): void {
  try {
    const log: ErrorLogEntry[] = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    log.push({ ...entry, timestamp: new Date().toISOString(), url: window.location.href });
    if (log.length > MAX_ENTRIES) log.splice(0, log.length - MAX_ENTRIES);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(log));
  } catch { /* ignore */ }
}
