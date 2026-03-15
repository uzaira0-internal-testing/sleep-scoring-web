import { describe, it, expect, beforeEach } from "bun:test";
import { isTauri, computeGroupHash } from "./tauri";

describe("isTauri", () => {
  beforeEach(() => {
    delete (globalThis as Record<string, unknown>).isTauri;
  });

  it("returns false when not in Tauri environment", () => {
    expect(isTauri()).toBe(false);
  });

  it("returns true when globalThis.isTauri is set", () => {
    (globalThis as Record<string, unknown>).isTauri = true;
    expect(isTauri()).toBe(true);
  });

  it("returns true for truthy non-boolean values", () => {
    (globalThis as Record<string, unknown>).isTauri = 1;
    expect(isTauri()).toBe(true);
  });

  it("returns false when globalThis.isTauri is falsy", () => {
    (globalThis as Record<string, unknown>).isTauri = 0;
    expect(isTauri()).toBe(false);
  });
});

describe("computeGroupHash", () => {
  it("returns a hex string", async () => {
    const hash = await computeGroupHash("test-password");
    expect(hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it("returns consistent results for the same input", async () => {
    const hash1 = await computeGroupHash("password123");
    const hash2 = await computeGroupHash("password123");
    expect(hash1).toBe(hash2);
  });

  it("returns different results for different inputs", async () => {
    const hash1 = await computeGroupHash("password-a");
    const hash2 = await computeGroupHash("password-b");
    expect(hash1).not.toBe(hash2);
  });

  it("produces 64-character hex (SHA-256)", async () => {
    const hash = await computeGroupHash("any-input");
    expect(hash).toHaveLength(64);
  });
});
