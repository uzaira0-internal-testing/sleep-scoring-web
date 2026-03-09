/**
 * Zustand store for server availability state (not persisted).
 */
import { create } from "zustand";
import { authApi } from "@/api/client";
import { getActiveWorkspaceId } from "@/store/workspace-store";

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
    if (!getActiveWorkspaceId()) {
      set({ serverAvailable: false, serverChecked: true });
      return;
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
