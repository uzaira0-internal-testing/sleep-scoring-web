/**
 * Tests for useAppCapabilities — tests the buildCapabilities function
 * and capabilities store state that the hook depends on.
 */
import { describe, it, expect, beforeEach } from "bun:test";
import { buildCapabilities } from "@/lib/app-capabilities";
import { useCapabilitiesStore } from "@/store/capabilities-store";

describe("buildCapabilities", () => {
  it("should return server=true when serverAvailable is true", () => {
    const caps = buildCapabilities(true, false);
    expect(caps.server).toBe(true);
  });

  it("should return server=false when serverAvailable is false", () => {
    const caps = buildCapabilities(false, false);
    expect(caps.server).toBe(false);
  });

  it("should return tauri=false in browser environment", () => {
    // In test environment, isTauri() returns false (no __TAURI_INTERNALS__)
    const caps = buildCapabilities(true, true);
    expect(caps.tauri).toBe(false);
  });

  it("should return peerSync=false when not in Tauri", () => {
    const caps = buildCapabilities(true, true);
    // peerSync requires tauri && groupConfigured — tauri is false in tests
    expect(caps.peerSync).toBe(false);
  });

  it("should return peerSync=false when groupConfigured is false", () => {
    const caps = buildCapabilities(true, false);
    expect(caps.peerSync).toBe(false);
  });
});

describe("Capabilities Store state for useAppCapabilities", () => {
  beforeEach(() => {
    useCapabilitiesStore.setState({
      serverAvailable: false,
      serverChecked: false,
      groupConfigured: false,
      lastSuccessAt: 0,
    });
  });

  it("should start unchecked with server unavailable", () => {
    const state = useCapabilitiesStore.getState();
    expect(state.serverAvailable).toBe(false);
    expect(state.serverChecked).toBe(false);
  });

  it("should reflect server available after setServerAvailable(true)", () => {
    useCapabilitiesStore.getState().setServerAvailable(true);

    const caps = buildCapabilities(
      useCapabilitiesStore.getState().serverAvailable,
      useCapabilitiesStore.getState().groupConfigured,
    );
    expect(caps.server).toBe(true);
  });

  it("should reflect group configured in capabilities", () => {
    useCapabilitiesStore.getState().setServerAvailable(true);
    useCapabilitiesStore.getState().setGroupConfigured(true);

    const state = useCapabilitiesStore.getState();
    expect(state.groupConfigured).toBe(true);
  });

  it("should allow probe cache reset", () => {
    useCapabilitiesStore.setState({ lastSuccessAt: 12345 });
    useCapabilitiesStore.getState().resetProbeCache();
    expect(useCapabilitiesStore.getState().lastSuccessAt).toBe(0);
  });
});
