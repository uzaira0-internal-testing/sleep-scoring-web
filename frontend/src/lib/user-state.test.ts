/**
 * Tests for user-state.ts — user preference persistence.
 *
 * Avoids mock.module to prevent contaminating other test files in the suite.
 * Instead, we test the exported functions after ensuring workspace store returns
 * a known value (the functions use getActiveWorkspaceId internally).
 */
import { describe, it, expect, beforeEach } from "bun:test";
import { saveUserPreferences, restoreUserPreferences } from "./user-state";

// Mock localStorage
const storage = new Map<string, string>();
const mockLocalStorage = {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => { storage.set(key, value); },
  removeItem: (key: string) => { storage.delete(key); },
  clear: () => { storage.clear(); },
};

Object.defineProperty(globalThis, "localStorage", {
  value: mockLocalStorage,
  writable: true,
});

describe("saveUserPreferences", () => {
  beforeEach(() => {
    storage.clear();
  });

  it("saves known persisted keys to localStorage", () => {
    saveUserPreferences("alice", {
      currentFileId: 42,
      currentFilename: "data.csv",
      viewModeHours: 24,
    });

    // Find the key that was saved (format depends on workspace ID)
    const keys = Array.from(storage.keys());
    expect(keys.length).toBe(1);
    const raw = storage.get(keys[0]!)!;
    const parsed = JSON.parse(raw);
    expect(parsed.currentFileId).toBe(42);
    expect(parsed.currentFilename).toBe("data.csv");
    expect(parsed.viewModeHours).toBe(24);
  });

  it("ignores unknown keys", () => {
    saveUserPreferences("bob", {
      currentFileId: 1,
      unknownProperty: "should-not-be-saved",
      anotherRandom: true,
    });

    const keys = Array.from(storage.keys());
    const parsed = JSON.parse(storage.get(keys[0]!)!);
    expect(parsed.currentFileId).toBe(1);
    expect("unknownProperty" in parsed).toBe(false);
    expect("anotherRandom" in parsed).toBe(false);
  });

  it("does not throw when localStorage is unavailable", () => {
    const origSetItem = mockLocalStorage.setItem;
    mockLocalStorage.setItem = () => { throw new Error("QuotaExceeded"); };
    expect(() => saveUserPreferences("user", { currentFileId: 1 })).not.toThrow();
    mockLocalStorage.setItem = origSetItem;
  });
});

describe("restoreUserPreferences", () => {
  beforeEach(() => {
    storage.clear();
  });

  it("returns null when no prefs saved", () => {
    expect(restoreUserPreferences("noone")).toBeNull();
  });

  it("restores saved preferences", () => {
    saveUserPreferences("carol", {
      currentFileId: 10,
      currentAlgorithm: "sadeh_1994",
      showNonwearOverlays: true,
    });

    const result = restoreUserPreferences("carol");
    expect(result).not.toBeNull();
    expect(result!.currentFileId).toBe(10);
    expect(result!.currentAlgorithm).toBe("sadeh_1994");
    expect(result!.showNonwearOverlays).toBe(true);
  });

  it("only returns known keys", () => {
    // First save valid prefs to know the key format
    saveUserPreferences("dan", { currentFileId: 1 });
    const keys = Array.from(storage.keys());
    // Now overwrite with unknown keys too
    storage.set(keys[0]!, JSON.stringify({
      currentFileId: 1,
      unknownKey: "should-not-appear",
    }));

    const result = restoreUserPreferences("dan");
    expect(result).not.toBeNull();
    expect(result!.currentFileId).toBe(1);
    expect("unknownKey" in result!).toBe(false);
  });

  it("returns null for invalid JSON", () => {
    // Save valid first to get key, then corrupt
    saveUserPreferences("eve", { currentFileId: 1 });
    const keys = Array.from(storage.keys());
    storage.set(keys[0]!, "not valid json {{{{");
    expect(restoreUserPreferences("eve")).toBeNull();
  });

  it("returns null when stored data has no known keys", () => {
    saveUserPreferences("frank", { currentFileId: 1 });
    const keys = Array.from(storage.keys());
    storage.set(keys[0]!, JSON.stringify({ unknownKey: "value" }));
    expect(restoreUserPreferences("frank")).toBeNull();
  });
});
