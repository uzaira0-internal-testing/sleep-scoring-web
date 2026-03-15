/**
 * Tests for usePeerDiscovery hook.
 *
 * This hook uses React effects and Tauri IPC. We test the
 * exported function signature.
 */
import { describe, it, expect } from "bun:test";
import { usePeerDiscovery } from "./usePeerDiscovery";

describe("usePeerDiscovery", () => {
  it("is exported as a function", () => {
    expect(typeof usePeerDiscovery).toBe("function");
  });

  it("has zero parameters", () => {
    expect(usePeerDiscovery.length).toBe(0);
  });
});
