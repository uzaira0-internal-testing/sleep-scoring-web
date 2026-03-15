/**
 * Tests for useConnectivity — store-level behavior.
 *
 * Since useConnectivity is a React hook with useEffect and intervals,
 * we test the underlying sync store it manages.
 */
import { describe, it, expect, beforeEach } from "bun:test";
import { useSyncStore } from "@/store/sync-store";

describe("SyncStore (used by useConnectivity)", () => {
  beforeEach(() => {
    useSyncStore.setState({
      isOnline: false,
      lastSyncAt: null,
      pendingCount: 0,
      syncStatus: "idle",
      syncError: null,
    });
  });

  describe("setOnline", () => {
    it("should set online to true", () => {
      useSyncStore.getState().setOnline(true);
      expect(useSyncStore.getState().isOnline).toBe(true);
    });

    it("should set online to false", () => {
      useSyncStore.getState().setOnline(true);
      useSyncStore.getState().setOnline(false);
      expect(useSyncStore.getState().isOnline).toBe(false);
    });
  });

  describe("setSyncing", () => {
    it("should set sync status to syncing and clear error", () => {
      useSyncStore.setState({ syncError: "previous error" });

      useSyncStore.getState().setSyncing();

      const state = useSyncStore.getState();
      expect(state.syncStatus).toBe("syncing");
      expect(state.syncError).toBeNull();
    });
  });

  describe("setSyncComplete", () => {
    it("should set status to idle with pending count and timestamp", () => {
      useSyncStore.getState().setSyncing();
      useSyncStore.getState().setSyncComplete(3);

      const state = useSyncStore.getState();
      expect(state.syncStatus).toBe("idle");
      expect(state.pendingCount).toBe(3);
      expect(state.lastSyncAt).toBeTruthy();
    });

    it("should set pending count to 0 when all synced", () => {
      useSyncStore.getState().setSyncComplete(0);

      expect(useSyncStore.getState().pendingCount).toBe(0);
    });
  });

  describe("setSyncError", () => {
    it("should set error status and message", () => {
      useSyncStore.getState().setSyncError("Network failed");

      const state = useSyncStore.getState();
      expect(state.syncStatus).toBe("error");
      expect(state.syncError).toBe("Network failed");
    });
  });

  describe("state transitions", () => {
    it("should handle full sync lifecycle: idle -> syncing -> complete", () => {
      expect(useSyncStore.getState().syncStatus).toBe("idle");

      useSyncStore.getState().setSyncing();
      expect(useSyncStore.getState().syncStatus).toBe("syncing");

      useSyncStore.getState().setSyncComplete(0);
      expect(useSyncStore.getState().syncStatus).toBe("idle");
      expect(useSyncStore.getState().lastSyncAt).toBeTruthy();
    });

    it("should handle sync error lifecycle: idle -> syncing -> error", () => {
      useSyncStore.getState().setSyncing();
      useSyncStore.getState().setSyncError("timeout");

      const state = useSyncStore.getState();
      expect(state.syncStatus).toBe("error");
      expect(state.syncError).toBe("timeout");
    });
  });
});
