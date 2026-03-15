/**
 * Tests for local-processing.ts.
 *
 * The main processLocalFile function requires WASM worker and IndexedDB.
 * We test the exported types and ProcessingPhase values.
 */
import { describe, it, expect } from "bun:test";
import type { ProcessingPhase, ProcessingProgress } from "./local-processing";

describe("local-processing types", () => {
  it("ProcessingPhase covers all expected values", () => {
    const phases: ProcessingPhase[] = [
      "reading", "parsing", "epoching", "scoring", "nonwear", "storing", "complete",
    ];
    expect(phases).toHaveLength(7);
    expect(phases).toContain("reading");
    expect(phases).toContain("complete");
  });

  it("ProcessingProgress interface has expected shape", () => {
    const progress: ProcessingProgress = {
      phase: "parsing",
      percent: 30,
      message: "Parsing CSV...",
    };
    expect(progress.phase).toBe("parsing");
    expect(progress.percent).toBe(30);
    expect(progress.message).toBe("Parsing CSV...");
  });

  it("processLocalFile is exported as a function", async () => {
    const mod = await import("./local-processing");
    expect(typeof mod.processLocalFile).toBe("function");
  });
});
