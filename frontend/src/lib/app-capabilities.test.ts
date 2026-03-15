import { describe, it, expect, beforeEach } from "bun:test";
import { buildCapabilities } from "./app-capabilities";

describe("buildCapabilities", () => {
  beforeEach(() => {
    // Ensure not in Tauri mode
    delete (globalThis as Record<string, unknown>).isTauri;
  });

  it("returns server=true when serverAvailable is true", () => {
    const caps = buildCapabilities(true, false);
    expect(caps.server).toBe(true);
  });

  it("returns server=false when serverAvailable is false", () => {
    const caps = buildCapabilities(false, false);
    expect(caps.server).toBe(false);
  });

  it("returns tauri=false when not in Tauri", () => {
    const caps = buildCapabilities(true, true);
    expect(caps.tauri).toBe(false);
  });

  it("returns peerSync=false when not in Tauri even if group configured", () => {
    const caps = buildCapabilities(true, true);
    expect(caps.peerSync).toBe(false);
  });

  it("returns tauri=true when isTauri is set", () => {
    (globalThis as Record<string, unknown>).isTauri = true;
    const caps = buildCapabilities(false, false);
    expect(caps.tauri).toBe(true);
  });

  it("returns peerSync=true only when tauri AND groupConfigured", () => {
    (globalThis as Record<string, unknown>).isTauri = true;
    const caps = buildCapabilities(false, true);
    expect(caps.peerSync).toBe(true);
  });

  it("returns peerSync=false when tauri but group not configured", () => {
    (globalThis as Record<string, unknown>).isTauri = true;
    const caps = buildCapabilities(false, false);
    expect(caps.peerSync).toBe(false);
  });
});
