import { describe, test, expect } from "bun:test";
import {
  computeTST,
  computeSleepEfficiency,
  computeSOL,
  countAwakenings,
  computePeriodMetrics,
} from "./sleep-metrics";

describe("computeTST", () => {
  test("counts sleep epochs", () => {
    expect(computeTST([1, 1, 0, 1, 0])).toBe(3);
  });

  test("applies epoch duration", () => {
    expect(computeTST([1, 1, 0, 1, 0], 2)).toBe(6);
  });

  test("returns 0 for all-wake", () => {
    expect(computeTST([0, 0, 0])).toBe(0);
  });

  test("works with Uint8Array", () => {
    expect(computeTST(new Uint8Array([1, 0, 1]))).toBe(2);
  });

  test("returns 0 for empty array", () => {
    expect(computeTST([])).toBe(0);
  });
});

describe("computeSleepEfficiency", () => {
  test("computes percentage", () => {
    expect(computeSleepEfficiency(6, 8)).toBeCloseTo(75.0);
  });

  test("returns 0 for zero TIB", () => {
    expect(computeSleepEfficiency(5, 0)).toBe(0);
  });

  test("returns 100 for perfect sleep", () => {
    expect(computeSleepEfficiency(8, 8)).toBeCloseTo(100.0);
  });

  test("returns 0 for negative TIB", () => {
    expect(computeSleepEfficiency(5, -1)).toBe(0);
  });
});

describe("computeSOL", () => {
  test("counts wake epochs before first sleep", () => {
    expect(computeSOL([0, 0, 1, 1, 0])).toBe(2);
  });

  test("returns 0 when sleep is first epoch", () => {
    expect(computeSOL([1, 0, 0])).toBe(0);
  });

  test("returns full period when no sleep", () => {
    expect(computeSOL([0, 0, 0])).toBe(3);
  });

  test("applies epoch duration", () => {
    expect(computeSOL([0, 0, 1], 2)).toBe(4);
  });

  test("returns 0 for empty array", () => {
    expect(computeSOL([])).toBe(0);
  });

  test("returns full period with epoch duration when no sleep", () => {
    expect(computeSOL([0, 0, 0, 0], 0.5)).toBeCloseTo(2.0);
  });
});

describe("countAwakenings", () => {
  test("counts wake blocks after first sleep", () => {
    // S W W S W S
    expect(countAwakenings([1, 0, 0, 1, 0, 1])).toBe(2);
  });

  test("returns 0 for all-sleep", () => {
    expect(countAwakenings([1, 1, 1])).toBe(0);
  });

  test("returns 0 for all-wake (no sleep onset)", () => {
    expect(countAwakenings([0, 0, 0])).toBe(0);
  });

  test("single awakening", () => {
    // W S S W W S
    expect(countAwakenings([0, 1, 1, 0, 0, 1])).toBe(1);
  });

  test("trailing wake counts as awakening", () => {
    // S W
    expect(countAwakenings([1, 0])).toBe(1);
  });

  test("works with Uint8Array", () => {
    expect(countAwakenings(new Uint8Array([1, 0, 1, 0, 1]))).toBe(2);
  });
});

describe("computePeriodMetrics", () => {
  // Helper: create timestamps at 60s intervals starting from a base
  function makeTimestamps(count: number, startMs = 0, intervalMs = 60000): number[] {
    return Array.from({ length: count }, (_, i) => startMs + i * intervalMs);
  }

  test("computes correct metrics for a typical period", () => {
    // 10 epochs: W W S S S W S S S S
    const scores = new Uint8Array([0, 0, 1, 1, 1, 0, 1, 1, 1, 1]);
    const timestamps = makeTimestamps(10, 1000);
    const onset = 1000;  // first timestamp
    const offset = 1000 + 9 * 60000; // last timestamp

    const m = computePeriodMetrics(scores, timestamps, onset, offset);
    expect(m).not.toBeNull();
    expect(m!.totalSleepTimeMinutes).toBe(7); // 7 sleep epochs
    expect(m!.sleepOnsetLatencyMinutes).toBe(2); // 2 wake epochs before first sleep
    expect(m!.wasoMinutes).toBe(1); // TIB(10) - TST(7) - SOL(2) = 1
    expect(m!.sleepEfficiency).toBeCloseTo(70.0); // 7/10 * 100
    expect(m!.numberOfAwakenings).toBe(1); // one wake block after first sleep
    expect(m!.timeInBedMinutes).toBe(10);
  });

  test("returns null for empty algorithm results", () => {
    expect(computePeriodMetrics(new Uint8Array([]), [1, 2, 3], 1, 3)).toBeNull();
  });

  test("returns null for empty timestamps", () => {
    expect(computePeriodMetrics(new Uint8Array([1, 0, 1]), [], 0, 100)).toBeNull();
  });

  test("returns null when onset >= offset", () => {
    const ts = makeTimestamps(5);
    expect(computePeriodMetrics(new Uint8Array([1, 0, 1, 0, 1]), ts, 100, 100)).toBeNull();
    expect(computePeriodMetrics(new Uint8Array([1, 0, 1, 0, 1]), ts, 200, 100)).toBeNull();
  });

  test("returns null for null inputs", () => {
    expect(computePeriodMetrics(null as unknown as Uint8Array, [1], 0, 1)).toBeNull();
  });

  test("handles all-wake period", () => {
    const scores = new Uint8Array([0, 0, 0, 0, 0]);
    const timestamps = makeTimestamps(5, 0);
    const m = computePeriodMetrics(scores, timestamps, 0, 4 * 60000);
    expect(m).not.toBeNull();
    expect(m!.totalSleepTimeMinutes).toBe(0);
    expect(m!.sleepOnsetLatencyMinutes).toBe(5); // full period
    expect(m!.wasoMinutes).toBe(0); // max(0, 5 - 0 - 5) = 0
    expect(m!.sleepEfficiency).toBeCloseTo(0);
    expect(m!.numberOfAwakenings).toBe(0);
  });

  test("handles all-sleep period", () => {
    const scores = new Uint8Array([1, 1, 1, 1, 1]);
    const timestamps = makeTimestamps(5, 0);
    const m = computePeriodMetrics(scores, timestamps, 0, 4 * 60000);
    expect(m).not.toBeNull();
    expect(m!.totalSleepTimeMinutes).toBe(5);
    expect(m!.sleepOnsetLatencyMinutes).toBe(0);
    expect(m!.wasoMinutes).toBe(0);
    expect(m!.sleepEfficiency).toBeCloseTo(100.0);
    expect(m!.numberOfAwakenings).toBe(0);
  });

  test("uses correct epoch duration", () => {
    const scores = new Uint8Array([0, 1, 1, 0, 1]);
    const timestamps = makeTimestamps(5, 0, 30000); // 30s epochs
    const m = computePeriodMetrics(scores, timestamps, 0, 4 * 30000, 30);
    expect(m).not.toBeNull();
    expect(m!.totalSleepTimeMinutes).toBeCloseTo(1.5); // 3 * 0.5
    expect(m!.sleepOnsetLatencyMinutes).toBeCloseTo(0.5); // 1 * 0.5
    expect(m!.timeInBedMinutes).toBeCloseTo(2.5); // 5 * 0.5
  });
});
