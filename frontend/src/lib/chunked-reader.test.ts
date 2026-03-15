/**
 * Tests for chunked-reader.ts — chunked file reading utilities.
 */
import { describe, it, expect } from "bun:test";
import { readFileAsText, readFileLines } from "./chunked-reader";

// ---------------------------------------------------------------------------
// Helper: create a File-like object from a string
// ---------------------------------------------------------------------------
function makeFile(content: string, name = "test.csv"): File {
  return new File([content], name, { type: "text/plain" });
}

// ---------------------------------------------------------------------------
// readFileAsText
// ---------------------------------------------------------------------------

describe("readFileAsText", () => {
  it("reads a small file completely", async () => {
    const content = "hello world\nsecond line\nthird line";
    const file = makeFile(content);
    const result = await readFileAsText(file);
    expect(result).toBe(content);
  });

  it("reads an empty file", async () => {
    const file = makeFile("");
    const result = await readFileAsText(file);
    expect(result).toBe("");
  });

  it("reports progress", async () => {
    const content = "x".repeat(1000);
    const file = makeFile(content);
    const progressUpdates: number[] = [];

    await readFileAsText(file, (p) => progressUpdates.push(p.percent), 200);

    // Should have multiple progress updates for small chunk size
    expect(progressUpdates.length).toBeGreaterThan(0);
    // Last progress should be 100%
    expect(progressUpdates[progressUpdates.length - 1]).toBe(100);
  });

  it("handles chunk boundaries correctly", async () => {
    // Create content that spans multiple chunks
    const content = "abcdefghij".repeat(100); // 1000 bytes
    const file = makeFile(content);
    const result = await readFileAsText(file, undefined, 300); // 300 byte chunks
    expect(result).toBe(content);
  });

  it("reads UTF-8 content", async () => {
    const content = "Hello, world!";
    const file = makeFile(content);
    const result = await readFileAsText(file);
    expect(result).toBe(content);
  });
});

// ---------------------------------------------------------------------------
// readFileLines
// ---------------------------------------------------------------------------

describe("readFileLines", () => {
  it("yields lines from a file", async () => {
    const content = "line1\nline2\nline3";
    const file = makeFile(content);
    const lines: string[] = [];
    for await (const line of readFileLines(file)) {
      lines.push(line);
    }
    expect(lines).toEqual(["line1", "line2", "line3"]);
  });

  it("handles empty file", async () => {
    const file = makeFile("");
    const lines: string[] = [];
    for await (const line of readFileLines(file)) {
      lines.push(line);
    }
    expect(lines).toEqual([]);
  });

  it("handles trailing newline", async () => {
    const content = "line1\nline2\n";
    const file = makeFile(content);
    const lines: string[] = [];
    for await (const line of readFileLines(file)) {
      lines.push(line);
    }
    // Trailing newline leaves empty leftover which is not yielded (empty string is falsy)
    expect(lines).toEqual(["line1", "line2"]);
  });

  it("handles single line without newline", async () => {
    const content = "single line";
    const file = makeFile(content);
    const lines: string[] = [];
    for await (const line of readFileLines(file)) {
      lines.push(line);
    }
    expect(lines).toEqual(["single line"]);
  });

  it("handles lines split across chunk boundaries", async () => {
    const content = "short\nthis is a longer line that will span chunks\nend";
    const file = makeFile(content);
    const lines: string[] = [];
    for await (const line of readFileLines(file, 10)) { // tiny chunks
      lines.push(line);
    }
    expect(lines).toEqual(["short", "this is a longer line that will span chunks", "end"]);
  });
});
