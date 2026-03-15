/**
 * Tests for uuid.ts — UUID v4 generation.
 */
import { describe, it, expect } from "bun:test";
import { generateId } from "./uuid";

describe("generateId", () => {
  it("returns a string", () => {
    const id = generateId();
    expect(typeof id).toBe("string");
  });

  it("returns UUID v4 format", () => {
    const id = generateId();
    // UUID v4: 8-4-4-4-12 hex with version=4 and variant=8/9/a/b
    expect(id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
  });

  it("generates unique IDs", () => {
    const ids = new Set<string>();
    for (let i = 0; i < 100; i++) {
      ids.add(generateId());
    }
    expect(ids.size).toBe(100);
  });

  it("has correct length (36 chars including hyphens)", () => {
    const id = generateId();
    expect(id).toHaveLength(36);
  });

  it("has version 4 marker", () => {
    const id = generateId();
    // The 13th character (index 14 with hyphens) should be '4'
    expect(id[14]).toBe("4");
  });

  it("has correct variant bits", () => {
    const id = generateId();
    // The 17th character (index 19 with hyphens) should be 8, 9, a, or b
    expect("89ab").toContain(id[19]);
  });
});
