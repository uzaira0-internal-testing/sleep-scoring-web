/**
 * Tests for updater.ts.
 *
 * The functions depend on @tauri-apps/* dynamic imports, so we test
 * the exported types and the downloadAndInstall guard logic.
 */
import { describe, it, expect } from "bun:test";
import type { UpdateInfo, UpdateProgress } from "./updater";

describe("updater types", () => {
  it("UpdateInfo has expected shape", () => {
    const info: UpdateInfo = {
      version: "1.2.0",
      currentVersion: "1.1.0",
      body: "Bug fixes",
      date: "2024-01-01",
    };
    expect(info.version).toBe("1.2.0");
    expect(info.currentVersion).toBe("1.1.0");
    expect(info.body).toBe("Bug fixes");
  });

  it("UpdateInfo allows optional fields", () => {
    const info: UpdateInfo = {
      version: "2.0.0",
      currentVersion: "1.0.0",
    };
    expect(info.body).toBeUndefined();
    expect(info.date).toBeUndefined();
  });

  it("UpdateProgress has expected shape", () => {
    const progress: UpdateProgress = {
      chunkSize: 1024,
      total: 10240,
    };
    expect(progress.chunkSize).toBe(1024);
    expect(progress.total).toBe(10240);
  });
});

describe("downloadAndInstall", () => {
  it("throws when no pending update exists", async () => {
    const { downloadAndInstall } = await import("./updater");
    // No checkForUpdate was called, so pendingUpdate is null
    await expect(downloadAndInstall()).rejects.toThrow("No pending update");
  });
});

describe("updater exports", () => {
  it("exports checkForUpdate and downloadAndInstall", async () => {
    const mod = await import("./updater");
    expect(typeof mod.checkForUpdate).toBe("function");
    expect(typeof mod.downloadAndInstall).toBe("function");
    expect(typeof mod.relaunchApp).toBe("function");
  });
});
