/**
 * Tests for useColorThemeSync hook.
 *
 * This hook uses React effects and the Zustand store. We test the
 * exported function signature and verify it is a valid hook.
 */
import { describe, it, expect } from "bun:test";
import { useColorThemeSync } from "./useColorThemeSync";

describe("useColorThemeSync", () => {
  it("is exported as a function", () => {
    expect(typeof useColorThemeSync).toBe("function");
  });

  it("has zero parameters (a React hook)", () => {
    expect(useColorThemeSync.length).toBe(0);
  });
});
