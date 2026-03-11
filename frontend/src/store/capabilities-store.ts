/**
 * Zustand store for server availability state (not persisted).
 */
import { create } from "zustand";
import { authApi } from "@/api/client";
import { getActiveWorkspaceId, useWorkspaceStore } from "@/store/workspace-store";
import { isTauri } from "@/lib/tauri";

const CACHE_MS = 60_000;

interface CapabilitiesState {
  serverAvailable: boolean;
  serverChecked: boolean;
  groupConfigured: boolean;
  lastSuccessAt: number;
  setServerAvailable: (available: boolean) => void;
  setGroupConfigured: (configured: boolean) => void;
  probeServer: () => Promise<void>;
  resetProbeCache: () => void;
}

export const useCapabilitiesStore = create<CapabilitiesState>((set, get) => ({
  serverAvailable: false,
  serverChecked: false,
  groupConfigured: false,
  lastSuccessAt: 0,
  setServerAvailable: (available) => set({ serverAvailable: available, serverChecked: true }),
  setGroupConfigured: (configured) => set({ groupConfigured: configured }),
  resetProbeCache: () => set({ lastSuccessAt: 0 }),
  probeServer: async () => {
    const { lastSuccessAt } = get();
    if (Date.now() - lastSuccessAt < CACHE_MS) return;

    // Skip probe if no workspace is active
    const wsId = getActiveWorkspaceId();
    if (!wsId) {
      set({ serverAvailable: false, serverChecked: true });
      return;
    }

    // In Tauri with a local workspace (no serverUrl), there's no server to probe.
    // The Tauri asset server returns 200 HTML for API paths (SPA fallback), which
    // would cause a confusing JSON parse error. Skip the probe entirely.
    if (isTauri()) {
      const ws = useWorkspaceStore.getState().getWorkspace(wsId);
      if (ws && !ws.serverUrl) {
        set({ serverAvailable: false, serverChecked: true });
        return;
      }
    }

    try {
      await authApi.getAuthStatus();
      set({ serverAvailable: true, serverChecked: true, lastSuccessAt: Date.now() });
    } catch (e) {
      console.warn("[capabilities] Server probe failed:", e instanceof Error ? e.message : e);
      set({ serverAvailable: false, serverChecked: true });
    }
  },
}));
