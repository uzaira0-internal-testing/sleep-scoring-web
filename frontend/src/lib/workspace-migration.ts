/**
 * Backward-compatibility migration from pre-workspace layout.
 * Runs once on first load when no workspace registry exists.
 */
import { useWorkspaceStore, setActiveWorkspaceId, type WorkspaceEntry } from "@/store/workspace-store";

const MIGRATION_DONE_KEY = "sleep-scoring-workspace-migration-done";

export function migrateFromLegacy(): void {
  // Already migrated or already has workspaces
  if (localStorage.getItem(MIGRATION_DONE_KEY)) return;
  if (useWorkspaceStore.getState().workspaces.length > 0) {
    localStorage.setItem(MIGRATION_DONE_KEY, "1");
    return;
  }

  // Check for legacy data
  const legacyStore = localStorage.getItem("sleep-scoring-storage");
  if (!legacyStore) {
    // No legacy data — clean slate
    localStorage.setItem(MIGRATION_DONE_KEY, "1");
    return;
  }

  // Read legacy server URL
  let serverUrl = "";
  try {
    const serverSettings = localStorage.getItem("sleep-scoring-server-settings");
    if (serverSettings) {
      const parsed = JSON.parse(serverSettings);
      serverUrl = parsed?.state?.serverUrl || "";
    }
  } catch { /* ignore */ }

  // Create workspace that adopts the existing DB (no data move needed)
  const id = crypto.randomUUID();
  const entry: WorkspaceEntry = {
    id,
    displayName: serverUrl ? "Default Server" : "Default",
    serverUrl,
    dbName: "SleepScoringDB", // Legacy name — adopts existing DB without moving data
    createdAt: new Date().toISOString(),
    lastAccessedAt: new Date().toISOString(),
  };

  useWorkspaceStore.getState().createWorkspaceWithId(entry);

  // Copy zustand persist store to workspace-scoped key
  localStorage.setItem(`sleep-scoring-storage-${id}`, legacyStore);

  // Migrate user preference keys
  const prefPrefix = "sleep-scoring-user-prefs-";
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && key.startsWith(prefPrefix)) {
      const username = key.slice(prefPrefix.length);
      const value = localStorage.getItem(key);
      if (value) {
        localStorage.setItem(`sleep-scoring-prefs-${id}-${username}`, value);
      }
    }
  }

  localStorage.setItem(MIGRATION_DONE_KEY, "1");
}
