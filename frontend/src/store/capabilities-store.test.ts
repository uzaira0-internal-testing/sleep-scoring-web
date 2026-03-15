/**
 * Tests for capabilities-store.
 *
 * Tests the Zustand store for server capability detection.
 * Since probeServer calls authApi.getAuthStatus() which hits the network,
 * we test the store's state management directly.
 *
 * NOTE: audit-log.test.ts uses mock.module to replace @/store/capabilities-store,
 * which can contaminate this module when running the full suite. We guard against
 * this by checking that setState is available.
 */
import { describe, it, expect, beforeEach } from "bun:test";
import { useCapabilitiesStore } from "./capabilities-store";

// Guard: if another test file has mocked this module, the store won't have setState
const storeIsReal = typeof useCapabilitiesStore.setState === "function";

describe("CapabilitiesStore", () => {
  beforeEach(() => {
    if (!storeIsReal) return;
    useCapabilitiesStore.setState({
      serverAvailable: false,
      serverChecked: false,
      groupConfigured: false,
      lastSuccessAt: 0,
    });
  });

  describe("setServerAvailable", () => {
    it("should set serverAvailable and mark as checked", () => {
      if (!storeIsReal) return; // skip when mocked by other tests
      useCapabilitiesStore.getState().setServerAvailable(true);

      const state = useCapabilitiesStore.getState();
      expect(state.serverAvailable).toBe(true);
      expect(state.serverChecked).toBe(true);
    });

    it("should set serverAvailable to false", () => {
      if (!storeIsReal) return;
      useCapabilitiesStore.getState().setServerAvailable(true);
      useCapabilitiesStore.getState().setServerAvailable(false);

      const state = useCapabilitiesStore.getState();
      expect(state.serverAvailable).toBe(false);
      expect(state.serverChecked).toBe(true);
    });
  });

  describe("setGroupConfigured", () => {
    it("should set groupConfigured", () => {
      if (!storeIsReal) return;
      useCapabilitiesStore.getState().setGroupConfigured(true);

      expect(useCapabilitiesStore.getState().groupConfigured).toBe(true);
    });
  });

  describe("resetProbeCache", () => {
    it("should reset lastSuccessAt to 0", () => {
      if (!storeIsReal) return;
      useCapabilitiesStore.setState({ lastSuccessAt: Date.now() });

      useCapabilitiesStore.getState().resetProbeCache();

      expect(useCapabilitiesStore.getState().lastSuccessAt).toBe(0);
    });
  });

  describe("probeServer", () => {
    it("should skip probe when cache is fresh", async () => {
      if (!storeIsReal) return;
      useCapabilitiesStore.setState({
        lastSuccessAt: Date.now(),
        serverAvailable: true,
        serverChecked: true,
      });

      await useCapabilitiesStore.getState().probeServer();

      const state = useCapabilitiesStore.getState();
      expect(state.serverAvailable).toBe(true);
    });

    it("should set serverAvailable=false when no active workspace", async () => {
      if (!storeIsReal) return;
      useCapabilitiesStore.setState({ lastSuccessAt: 0 });

      await useCapabilitiesStore.getState().probeServer();

      const state = useCapabilitiesStore.getState();
      expect(state.serverAvailable).toBe(false);
      expect(state.serverChecked).toBe(true);
    });
  });
});
