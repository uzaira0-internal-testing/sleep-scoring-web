import { describe, it, expect, beforeEach } from "bun:test";
import { useSyncStore } from "./sync-store";

describe("SyncStore", () => {
  beforeEach(() => {
    useSyncStore.setState({
      isOnline: true,
      lastSyncAt: null,
      pendingCount: 0,
      syncStatus: "idle",
      syncError: null,
    });
  });

  describe("initial state", () => {
    it("has expected defaults", () => {
      const state = useSyncStore.getState();
      expect(state.isOnline).toBe(true);
      expect(state.lastSyncAt).toBeNull();
      expect(state.pendingCount).toBe(0);
      expect(state.syncStatus).toBe("idle");
      expect(state.syncError).toBeNull();
    });
  });

  describe("setOnline", () => {
    it("sets online to true", () => {
      useSyncStore.getState().setOnline(true);
      expect(useSyncStore.getState().isOnline).toBe(true);
    });

    it("sets online to false", () => {
      useSyncStore.getState().setOnline(false);
      expect(useSyncStore.getState().isOnline).toBe(false);
    });
  });

  describe("setSyncing", () => {
    it("sets status to syncing and clears error", () => {
      useSyncStore.setState({ syncError: "old error" });
      useSyncStore.getState().setSyncing();

      const state = useSyncStore.getState();
      expect(state.syncStatus).toBe("syncing");
      expect(state.syncError).toBeNull();
    });
  });

  describe("setSyncComplete", () => {
    it("sets status to idle, updates lastSyncAt and pendingCount", () => {
      useSyncStore.getState().setSyncing();
      useSyncStore.getState().setSyncComplete(3);

      const state = useSyncStore.getState();
      expect(state.syncStatus).toBe("idle");
      expect(state.pendingCount).toBe(3);
      expect(state.lastSyncAt).toBeTruthy();
      // lastSyncAt should be a valid ISO string
      expect(new Date(state.lastSyncAt!).getTime()).toBeGreaterThan(0);
    });

    it("sets pending count to 0 when all synced", () => {
      useSyncStore.getState().setSyncComplete(0);
      expect(useSyncStore.getState().pendingCount).toBe(0);
    });
  });

  describe("setSyncError", () => {
    it("sets status to error with message", () => {
      useSyncStore.getState().setSyncError("Network timeout");

      const state = useSyncStore.getState();
      expect(state.syncStatus).toBe("error");
      expect(state.syncError).toBe("Network timeout");
    });
  });

  describe("state transitions", () => {
    it("handles idle -> syncing -> complete flow", () => {
      const store = useSyncStore.getState();
      expect(useSyncStore.getState().syncStatus).toBe("idle");

      store.setSyncing();
      expect(useSyncStore.getState().syncStatus).toBe("syncing");

      store.setSyncComplete(0);
      expect(useSyncStore.getState().syncStatus).toBe("idle");
    });

    it("handles idle -> syncing -> error flow", () => {
      const store = useSyncStore.getState();

      store.setSyncing();
      expect(useSyncStore.getState().syncStatus).toBe("syncing");

      store.setSyncError("Failed");
      expect(useSyncStore.getState().syncStatus).toBe("error");
    });
  });
});
