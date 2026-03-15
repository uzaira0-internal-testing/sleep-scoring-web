/**
 * Tests for complexity.ts — night scoring difficulty computation.
 */
import { describe, it, expect } from "bun:test";
import * as fc from "fast-check";
import { computePreComplexity, computePostComplexity } from "./complexity";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeTimestamps(startTs: number, count: number, epochSec = 60): number[] {
  return Array.from({ length: count }, (_, i) => startTs + i * epochSec);
}

/** Build a standard night: 21:00 to 09:00 next day = 720 epochs at 60s. */
function makeNight(opts?: {
  sleepStart?: number;
  sleepEnd?: number;
  wakeGaps?: Array<[number, number]>;
  activityBase?: number;
}) {
  const epochCount = 720;
  // 2025-03-01 21:00 UTC
  const startTs = Date.UTC(2025, 2, 1, 21, 0, 0) / 1000;
  const timestamps = makeTimestamps(startTs, epochCount);
  const sleepStart = opts?.sleepStart ?? 30;
  const sleepEnd = opts?.sleepEnd ?? 690;
  const sleepScores = Array.from({ length: epochCount }, (_, i) => {
    if (i >= sleepStart && i <= sleepEnd) return 1;
    return 0;
  });

  if (opts?.wakeGaps) {
    for (const [gs, ge] of opts.wakeGaps) {
      for (let i = gs; i <= ge && i < epochCount; i++) {
        sleepScores[i] = 0;
      }
    }
  }

  const base = opts?.activityBase ?? 5;
  const activityCounts = sleepScores.map((s) => (s === 1 ? 0 : base + Math.floor(Math.random() * 10)));
  const choiNonwear = new Array(epochCount).fill(0);

  return { timestamps, sleepScores, activityCounts, choiNonwear, epochCount };
}

// ---------------------------------------------------------------------------
// computePreComplexity
// ---------------------------------------------------------------------------

describe("computePreComplexity", () => {
  it("returns score 0 with empty data", () => {
    const result = computePreComplexity({
      timestamps: [],
      activityCounts: [],
      sleepScores: [],
      choiNonwear: [],
      diaryOnsetTime: "10:00 PM",
      diaryWakeTime: "7:00 AM",
      diaryNapCount: 0,
      analysisDate: "2025-03-01",
    });
    expect(result.score).toBe(0);
    expect(result.features.error).toBe("insufficient_data");
  });

  it("returns -1 when diary is missing", () => {
    const { timestamps, sleepScores, activityCounts, choiNonwear } = makeNight();
    const result = computePreComplexity({
      timestamps,
      activityCounts,
      sleepScores,
      choiNonwear,
      diaryOnsetTime: null,
      diaryWakeTime: null,
      diaryNapCount: 0,
      analysisDate: "2025-03-01",
    });
    expect(result.score).toBe(-1);
    expect(result.features.no_diary).toBe(true);
  });

  it("returns -1 when only onset is missing", () => {
    const { timestamps, sleepScores, activityCounts, choiNonwear } = makeNight();
    const result = computePreComplexity({
      timestamps,
      activityCounts,
      sleepScores,
      choiNonwear,
      diaryOnsetTime: null,
      diaryWakeTime: "7:00 AM",
      diaryNapCount: 0,
      analysisDate: "2025-03-01",
    });
    expect(result.score).toBe(-1);
    expect(result.features.missing_onset).toBe(true);
  });

  it("returns 0-100 score for valid night with diary", () => {
    const { timestamps, sleepScores, activityCounts, choiNonwear } = makeNight();
    const result = computePreComplexity({
      timestamps,
      activityCounts,
      sleepScores,
      choiNonwear,
      diaryOnsetTime: "9:30 PM",
      diaryWakeTime: "8:30 AM",
      diaryNapCount: 0,
      analysisDate: "2025-03-01",
    });
    expect(result.score).toBeGreaterThanOrEqual(0);
    expect(result.score).toBeLessThanOrEqual(100);
  });

  it("penalizes high transition density", () => {
    // Create a night with many transitions (alternating sleep/wake)
    const epochCount = 720;
    const startTs = Date.UTC(2025, 2, 1, 21, 0, 0) / 1000;
    const timestamps = makeTimestamps(startTs, epochCount);
    // Alternating every 3 epochs to create many transitions
    const sleepScores = Array.from({ length: epochCount }, (_, i) =>
      Math.floor(i / 3) % 2 === 0 ? 1 : 0,
    );
    const activityCounts = sleepScores.map((s) => (s === 1 ? 0 : 20));
    const choiNonwear = new Array(epochCount).fill(0);

    const resultHigh = computePreComplexity({
      timestamps,
      activityCounts,
      sleepScores,
      choiNonwear,
      diaryOnsetTime: "9:30 PM",
      diaryWakeTime: "8:30 AM",
      diaryNapCount: 0,
      analysisDate: "2025-03-01",
    });

    // Compare with clean night (few transitions)
    const cleanData = makeNight();
    const resultClean = computePreComplexity({
      timestamps: cleanData.timestamps,
      activityCounts: cleanData.activityCounts,
      sleepScores: cleanData.sleepScores,
      choiNonwear: cleanData.choiNonwear,
      diaryOnsetTime: "9:30 PM",
      diaryWakeTime: "8:30 AM",
      diaryNapCount: 0,
      analysisDate: "2025-03-01",
    });

    // Noisy night should score lower (harder)
    if (resultHigh.score >= 0 && resultClean.score >= 0) {
      expect(resultHigh.score).toBeLessThanOrEqual(resultClean.score);
    }
  });

  it("penalizes naps", () => {
    const { timestamps, sleepScores, activityCounts, choiNonwear } = makeNight();

    const result0 = computePreComplexity({
      timestamps, activityCounts, sleepScores, choiNonwear,
      diaryOnsetTime: "9:30 PM", diaryWakeTime: "8:30 AM",
      diaryNapCount: 0, analysisDate: "2025-03-01",
    });
    const result3 = computePreComplexity({
      timestamps, activityCounts, sleepScores, choiNonwear,
      diaryOnsetTime: "9:30 PM", diaryWakeTime: "8:30 AM",
      diaryNapCount: 3, analysisDate: "2025-03-01",
    });

    if (result0.score >= 0 && result3.score >= 0) {
      expect(result3.score).toBeLessThanOrEqual(result0.score);
    }
  });

  it("returns -1 for diary nonwear overlapping sleep", () => {
    const { timestamps, sleepScores, activityCounts, choiNonwear } = makeNight();
    const result = computePreComplexity({
      timestamps, activityCounts, sleepScores, choiNonwear,
      diaryOnsetTime: "10:00 PM",
      diaryWakeTime: "7:00 AM",
      diaryNapCount: 0,
      analysisDate: "2025-03-01",
      diaryNonwearTimes: [["11:00 PM", "2:00 AM"]], // overlaps sleep
    });
    expect(result.score).toBe(-1);
    expect(result.features.diary_nonwear_overlaps_sleep).toBe(true);
  });

  it("returns -1 when nonwear exceeds threshold with no spikes", () => {
    const epochCount = 720;
    const startTs = Date.UTC(2025, 2, 1, 21, 0, 0) / 1000;
    const timestamps = makeTimestamps(startTs, epochCount);
    // All sleep, all zero activity, lots of Choi nonwear
    const sleepScores = new Array(epochCount).fill(1);
    const activityCounts = new Array(epochCount).fill(0);
    const choiNonwear = new Array(epochCount).fill(1); // all nonwear

    const result = computePreComplexity({
      timestamps, activityCounts, sleepScores, choiNonwear,
      diaryOnsetTime: "9:30 PM",
      diaryWakeTime: "8:30 AM",
      diaryNapCount: 0,
      analysisDate: "2025-03-01",
    });
    expect(result.score).toBe(-1);
  });

  it("includes expected feature keys", () => {
    const { timestamps, sleepScores, activityCounts, choiNonwear } = makeNight();
    const result = computePreComplexity({
      timestamps, activityCounts, sleepScores, choiNonwear,
      diaryOnsetTime: "9:30 PM",
      diaryWakeTime: "8:30 AM",
      diaryNapCount: 0,
      analysisDate: "2025-03-01",
    });

    expect("transition_density" in result.features).toBe(true);
    expect("sleep_run_count" in result.features).toBe(true);
    expect("nap_count" in result.features).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// computePostComplexity
// ---------------------------------------------------------------------------

describe("computePostComplexity", () => {
  it("returns clamped score with empty inputs", () => {
    const result = computePostComplexity(50, {}, [], [], []);
    expect(result.score).toBe(50);
    expect(result.features.post_adjustment).toBe(0);
  });

  it("boosts score when markers align closely with algorithm", () => {
    const epochCount = 720;
    const startTs = Date.UTC(2025, 2, 1, 21, 0, 0) / 1000;
    const timestamps = makeTimestamps(startTs, epochCount);
    const sleepScores = Array.from({ length: epochCount }, (_, i) =>
      i >= 30 && i <= 690 ? 1 : 0,
    );

    // Markers align exactly with algorithm boundaries
    const sleepMarkers: Array<[number, number]> = [[timestamps[30]!, timestamps[690]!]];

    const result = computePostComplexity(50, {}, sleepMarkers, sleepScores, timestamps);
    expect(result.features.marker_alignment).toBe("close");
    expect(result.score).toBeGreaterThanOrEqual(50);
  });

  it("penalizes when markers are far from algorithm boundaries", () => {
    const epochCount = 720;
    const startTs = Date.UTC(2025, 2, 1, 21, 0, 0) / 1000;
    const timestamps = makeTimestamps(startTs, epochCount);
    const sleepScores = Array.from({ length: epochCount }, (_, i) =>
      i >= 30 && i <= 690 ? 1 : 0,
    );

    // Markers placed far from algorithm boundaries
    const sleepMarkers: Array<[number, number]> = [[timestamps[200]!, timestamps[400]!]];

    const result = computePostComplexity(50, {}, sleepMarkers, sleepScores, timestamps);
    expect(result.features.marker_alignment).toBe("far");
    expect(result.score).toBeLessThanOrEqual(50);
  });

  it("clamps score between 0 and 100", () => {
    const result1 = computePostComplexity(5, {}, [], [], []);
    expect(result1.score).toBeGreaterThanOrEqual(0);
    expect(result1.score).toBeLessThanOrEqual(100);

    const result2 = computePostComplexity(99, {}, [], [], []);
    expect(result2.score).toBeGreaterThanOrEqual(0);
    expect(result2.score).toBeLessThanOrEqual(100);
  });

  it("penalizes period count mismatch", () => {
    const epochCount = 720;
    const startTs = Date.UTC(2025, 2, 1, 21, 0, 0) / 1000;
    const timestamps = makeTimestamps(startTs, epochCount);

    // Two sleep runs in algorithm
    const sleepScores = Array.from({ length: epochCount }, (_, i) => {
      if (i >= 30 && i <= 200) return 1;
      if (i >= 400 && i <= 600) return 1;
      return 0;
    });

    // But only 1 marker placed
    const sleepMarkers: Array<[number, number]> = [[timestamps[30]!, timestamps[200]!]];

    const result = computePostComplexity(50, {}, sleepMarkers, sleepScores, timestamps);
    expect(result.features.period_count_penalty).toBe(-5);
  });
});

// ---------------------------------------------------------------------------
// Property-based tests
// ---------------------------------------------------------------------------

describe("complexity property tests", () => {
  it("computePreComplexity score is always -1, 0, or in [0, 100]", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 50, max: 300 }),
        fc.boolean(),
        (epochCount, hasDiary) => {
          const startTs = Date.UTC(2025, 2, 1, 21, 0, 0) / 1000;
          const timestamps = makeTimestamps(startTs, epochCount);
          const sleepScores = Array.from({ length: epochCount }, () =>
            Math.random() > 0.5 ? 1 : 0,
          );
          const activityCounts = Array.from({ length: epochCount }, () =>
            Math.floor(Math.random() * 100),
          );
          const choiNonwear = new Array(epochCount).fill(0);

          const result = computePreComplexity({
            timestamps,
            activityCounts,
            sleepScores,
            choiNonwear,
            diaryOnsetTime: hasDiary ? "10:00 PM" : null,
            diaryWakeTime: hasDiary ? "7:00 AM" : null,
            diaryNapCount: 0,
            analysisDate: "2025-03-01",
          });

          expect(result.score === -1 || (result.score >= 0 && result.score <= 100)).toBe(true);
        },
      ),
      { numRuns: 50 },
    );
  });

  it("computePostComplexity always returns score in [0, 100]", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100 }),
        (preScore) => {
          const result = computePostComplexity(preScore, {}, [], [], []);
          expect(result.score).toBeGreaterThanOrEqual(0);
          expect(result.score).toBeLessThanOrEqual(100);
        },
      ),
      { numRuns: 50 },
    );
  });

  it("more naps never increase complexity score", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 3 }),
        (napCount) => {
          const data = makeNight();
          const result0 = computePreComplexity({
            ...data,
            diaryOnsetTime: "9:30 PM",
            diaryWakeTime: "8:30 AM",
            diaryNapCount: 0,
            analysisDate: "2025-03-01",
          });
          const resultN = computePreComplexity({
            ...data,
            diaryOnsetTime: "9:30 PM",
            diaryWakeTime: "8:30 AM",
            diaryNapCount: napCount,
            analysisDate: "2025-03-01",
          });
          if (result0.score >= 0 && resultN.score >= 0) {
            expect(resultN.score).toBeLessThanOrEqual(result0.score);
          }
        },
      ),
      { numRuns: 20 },
    );
  });
});
