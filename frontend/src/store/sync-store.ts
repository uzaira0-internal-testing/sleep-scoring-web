import { create } from "zustand";

interface SyncState {
  isOnline: boolean;
  lastSyncAt: string | null;
  pendingCount: number;
  syncStatus: "idle" | "syncing" | "error";
  syncError: string | null;

  setOnline: (online: boolean) => void;
  setSyncing: () => void;
  setSyncComplete: (pendingCount: number) => void;
  setSyncError: (error: string) => void;
}

export const useSyncStore = create<SyncState>()((set) => ({
  isOnline: typeof navigator !== "undefined" ? navigator.onLine : true,
  lastSyncAt: null,
  pendingCount: 0,
  syncStatus: "idle",
  syncError: null,

  setOnline: (online) => set({ isOnline: online }),
  setSyncing: () => set({ syncStatus: "syncing", syncError: null }),
  setSyncComplete: (pendingCount) =>
    set({
      syncStatus: "idle",
      lastSyncAt: new Date().toISOString(),
      pendingCount,
    }),
  setSyncError: (error) => set({ syncStatus: "error", syncError: error }),
}));
