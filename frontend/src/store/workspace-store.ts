/**
 * Workspace registry — global (not workspace-scoped).
 * Each workspace = server connection (or local-only) + isolated IndexedDB + preferences.
 */
import Dexie from "dexie";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { isTauri, deleteTauriWorkspace } from "@/lib/tauri";

import { generateId } from "@/lib/uuid";

export interface WorkspaceEntry {
  id: string;
  displayName: string;
  serverUrl: string; // "" for local-only
  dbName: string; // "SleepScoringDB-{id}"
  createdAt: string;
  lastAccessedAt: string;
}

interface WorkspaceStore {
  workspaces: WorkspaceEntry[];
  createWorkspace: (serverUrl: string, displayName: string) => WorkspaceEntry;
  /** Create workspace with specific ID and dbName (used by migration). */
  createWorkspaceWithId: (entry: WorkspaceEntry) => void;
  deleteWorkspace: (id: string) => void;
  updateLastAccessed: (id: string) => void;
  getWorkspace: (id: string) => WorkspaceEntry | undefined;
}

export const useWorkspaceStore = create<WorkspaceStore>()(
  persist(
    (set, get) => ({
      workspaces: [],

      createWorkspace: (serverUrl, displayName) => {
        const id = generateId();
        const entry: WorkspaceEntry = {
          id,
          displayName,
          serverUrl: serverUrl.replace(/\/+$/, ""),
          dbName: `SleepScoringDB-${id}`,
          createdAt: new Date().toISOString(),
          lastAccessedAt: new Date().toISOString(),
        };
        set((s) => ({ workspaces: [...s.workspaces, entry] }));
        return entry;
      },

      createWorkspaceWithId: (entry) => {
        set((s) => ({ workspaces: [...s.workspaces, entry] }));
      },

      deleteWorkspace: (id) => {
        // Refuse to delete the currently active workspace
        if (id === getActiveWorkspaceId()) {
          console.warn("Cannot delete the currently active workspace");
          return;
        }

        const ws = get().workspaces.find((w) => w.id === id);
        set((s) => ({ workspaces: s.workspaces.filter((w) => w.id !== id) }));

        // Clean up IndexedDB for the workspace (Dexie handles blocked connections)
        if (ws?.dbName) {
          Dexie.delete(ws.dbName).catch((e) => {
            console.warn("Failed to delete IndexedDB:", e);
          });
        }

        // Clean up workspace-scoped localStorage keys
        try {
          const storageKey = `sleep-scoring-storage-${id}`;
          localStorage.removeItem(storageKey);
          // Clean up user preference keys (sleep-scoring-prefs-{wsId}-*)
          const prefPrefix = `sleep-scoring-prefs-${id}-`;
          const keysToRemove: string[] = [];
          for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key?.startsWith(prefPrefix)) keysToRemove.push(key);
          }
          for (const key of keysToRemove) localStorage.removeItem(key);
        } catch (e) {
          console.warn("Failed to clean up localStorage:", e);
        }

        // Clean up Tauri workspace SQLite database
        if (isTauri()) {
          deleteTauriWorkspace(id).catch((e) => {
            console.warn("Failed to delete Tauri workspace DB:", e);
          });
        }
      },

      updateLastAccessed: (id) => {
        set((s) => ({
          workspaces: s.workspaces.map((w) =>
            w.id === id ? { ...w, lastAccessedAt: new Date().toISOString() } : w,
          ),
        }));
      },

      getWorkspace: (id) => {
        return get().workspaces.find((w) => w.id === id);
      },
    }),
    { name: "sleep-scoring-workspaces" },
  ),
);

// --- Active workspace ID (per-tab, reactive) ---
// Backed by sessionStorage for tab isolation, but wrapped in a tiny Zustand store
// so that React components re-render when the active workspace changes.

const ACTIVE_WS_KEY = "sleep-scoring-active-workspace";

interface ActiveWsStore {
  activeId: string | null;
}

const useActiveWsStore = create<ActiveWsStore>()(() => ({
  activeId: (() => { try { return sessionStorage.getItem(ACTIVE_WS_KEY); } catch { return null; } })(),
}));

export function getActiveWorkspaceId(): string | null {
  return useActiveWsStore.getState().activeId;
}

/** React hook — subscribe to the active workspace ID reactively. */
export function useActiveWorkspaceId(): string | null {
  return useActiveWsStore((s) => s.activeId);
}

export function setActiveWorkspaceId(id: string): void {
  try {
    sessionStorage.setItem(ACTIVE_WS_KEY, id);
  } catch {
    // sessionStorage unavailable
  }
  useActiveWsStore.setState({ activeId: id });
}

export function clearActiveWorkspaceId(): void {
  try {
    sessionStorage.removeItem(ACTIVE_WS_KEY);
  } catch {
    // sessionStorage unavailable
  }
  useActiveWsStore.setState({ activeId: null });
}
