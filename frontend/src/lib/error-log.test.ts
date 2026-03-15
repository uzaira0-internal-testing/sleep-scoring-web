/**
 * Tests for error-log.ts — persistent error log in localStorage.
 */
import { describe, it, expect, beforeEach, mock } from "bun:test";

// Mock localStorage and window
const storage = new Map<string, string>();
const mockLocalStorage = {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => { storage.set(key, value); },
  removeItem: (key: string) => { storage.delete(key); },
  clear: () => { storage.clear(); },
};

// Set up globals before importing
Object.defineProperty(globalThis, "localStorage", {
  value: mockLocalStorage,
  writable: true,
});

if (typeof globalThis.window === "undefined") {
  (globalThis as Record<string, unknown>).window = {
    location: { href: "http://localhost:8501/scoring" },
  };
} else {
  // window exists, ensure location.href
  try {
    Object.defineProperty(window, "location", {
      value: { href: "http://localhost:8501/scoring" },
      writable: true,
    });
  } catch {
    // Ignore if already defined
  }
}

import { appendErrorLog } from "./error-log";

const STORAGE_KEY = "sleep-scoring-error-log";

describe("appendErrorLog", () => {
  beforeEach(() => {
    storage.clear();
  });

  it("appends an error entry", () => {
    appendErrorLog({ message: "Test error" });
    const log = JSON.parse(storage.get(STORAGE_KEY)!);
    expect(log).toHaveLength(1);
    expect(log[0].message).toBe("Test error");
    expect(log[0].timestamp).toBeDefined();
    expect(log[0].url).toBeDefined();
  });

  it("includes stack trace when provided", () => {
    appendErrorLog({ message: "Error", stack: "Error: stack trace here" });
    const log = JSON.parse(storage.get(STORAGE_KEY)!);
    expect(log[0].stack).toBe("Error: stack trace here");
  });

  it("includes componentStack when provided", () => {
    appendErrorLog({ message: "Error", componentStack: "at MyComponent" });
    const log = JSON.parse(storage.get(STORAGE_KEY)!);
    expect(log[0].componentStack).toBe("at MyComponent");
  });

  it("appends multiple entries", () => {
    appendErrorLog({ message: "Error 1" });
    appendErrorLog({ message: "Error 2" });
    appendErrorLog({ message: "Error 3" });
    const log = JSON.parse(storage.get(STORAGE_KEY)!);
    expect(log).toHaveLength(3);
    expect(log[0].message).toBe("Error 1");
    expect(log[2].message).toBe("Error 3");
  });

  it("caps log at 20 entries", () => {
    for (let i = 0; i < 25; i++) {
      appendErrorLog({ message: `Error ${i}` });
    }
    const log = JSON.parse(storage.get(STORAGE_KEY)!);
    expect(log).toHaveLength(20);
    // Should keep most recent
    expect(log[19].message).toBe("Error 24");
    expect(log[0].message).toBe("Error 5");
  });

  it("does not throw when localStorage is unavailable", () => {
    const origGetItem = mockLocalStorage.getItem;
    mockLocalStorage.getItem = () => { throw new Error("Storage full"); };
    expect(() => appendErrorLog({ message: "test" })).not.toThrow();
    mockLocalStorage.getItem = origGetItem;
  });
});
