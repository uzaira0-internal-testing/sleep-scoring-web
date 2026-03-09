import { getActiveWorkspaceId } from "@/store/workspace-store";

const PERSISTED_KEYS = [
  "currentFileId",
  "currentFilename",
  "currentDateIndex",
  "preferredDisplayColumn",
  "viewModeHours",
  "currentAlgorithm",
  "showAdjacentMarkers",
  "showNonwearOverlays",
  "autoScoreOnNavigate",
  "autoNonwearOnNavigate",
  "sleepDetectionRule",
  "nightStartHour",
  "nightEndHour",
  "devicePreset",
  "epochLengthSeconds",
  "skipRows",
  "colorTheme",
] as const;

function getStorageKey(username: string): string {
  const wsId = getActiveWorkspaceId();
  if (wsId) {
    return `sleep-scoring-prefs-${wsId}-${username}`;
  }
  // Legacy fallback (pre-workspace migration)
  return `sleep-scoring-user-prefs-${username}`;
}

export function saveUserPreferences(
  username: string,
  state: Record<string, unknown>,
): void {
  try {
    const prefs: Record<string, unknown> = {};
    for (const key of PERSISTED_KEYS) {
      if (key in state) prefs[key] = state[key];
    }
    localStorage.setItem(
      getStorageKey(username),
      JSON.stringify(prefs),
    );
  } catch {
    // localStorage may be unavailable
  }
}

export function restoreUserPreferences(
  username: string,
): Record<string, unknown> | null {
  try {
    const raw = localStorage.getItem(getStorageKey(username));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    // Only return known keys
    const result: Record<string, unknown> = {};
    for (const key of PERSISTED_KEYS) {
      if (key in parsed) result[key] = parsed[key];
    }
    return Object.keys(result).length > 0 ? result : null;
  } catch {
    return null;
  }
}
