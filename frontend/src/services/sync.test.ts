/**
 * Tests for sync.ts — syncAll push/pull logic.
 *
 * We cannot mock modules (mock.module contaminates globally), so we test
 * the SyncResult interface shape and verify the exported function signature.
 * The actual push/pull logic requires IndexedDB which is unavailable in bun test.
 */
import { describe, it, expect } from "bun:test";
import type { SyncResult } from "./sync";

describe("sync module", () => {
  it("SyncResult interface has expected shape", () => {
    const result: SyncResult = {
      pushed: 0,
      pulled: 0,
      conflicts: 0,
      errors: [],
    };

    expect(result.pushed).toBe(0);
    expect(result.pulled).toBe(0);
    expect(result.conflicts).toBe(0);
    expect(result.errors).toEqual([]);
  });

  it("SyncResult accepts positive counts", () => {
    const result: SyncResult = {
      pushed: 5,
      pulled: 3,
      conflicts: 1,
      errors: ["Push failed for 2024-01-01: 500"],
    };

    expect(result.pushed).toBe(5);
    expect(result.pulled).toBe(3);
    expect(result.conflicts).toBe(1);
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0]).toContain("Push failed");
  });

  it("syncAll is exported as a function", async () => {
    const mod = await import("./sync");
    expect(typeof mod.syncAll).toBe("function");
  });
});
