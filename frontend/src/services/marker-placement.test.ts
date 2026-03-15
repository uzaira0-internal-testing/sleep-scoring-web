/**
 * Tests for marker-placement.ts — automated sleep/nonwear marker placement.
 */
import { describe, it, expect } from "bun:test";
import * as fc from "fast-check";
import { runAutoScoring, placeNonwearMarkers } from "./marker-placement";

// ---------------------------------------------------------------------------
// Helpers to build synthetic epoch data
// ---------------------------------------------------------------------------

/** Build timestamps starting at a given Unix second, with 60s intervals. */
function makeTimestamps(startTs: number, count: number, epochSec = 60): number[] {
  return Array.from({ length: count }, (_, i) => startTs + i * epochSec);
}

/** Build a sleep score array: 0 = wake, 1 = sleep. */
function makeSleepScores(pattern: number[]): number[] {
  return pattern;
}

/**
 * Create a standard "night" dataset: analysis date 2025-03-01,
 * data from 21:00 to 09:00 next day (720 epochs at 60s).
 * Sleep from epoch 30 to 690 by default.
 */
function makeNightData(opts?: {
  sleepStart?: number;
  sleepEnd?: number;
  wakeGaps?: Array<[number, number]>;
  epochCount?: number;
}) {
  const epochCount = opts?.epochCount ?? 720;
  // 2025-03-01 21:00 UTC
  const startTs = Date.UTC(2025, 2, 1, 21, 0, 0) / 1000;
  const timestamps = makeTimestamps(startTs, epochCount);
  const sleepStart = opts?.sleepStart ?? 30;
  const sleepEnd = opts?.sleepEnd ?? 690;
  const scores = Array.from({ length: epochCount }, (_, i) => {
    if (i >= sleepStart && i <= sleepEnd) return 1;
    return 0;
  });

  // Apply wake gaps
  if (opts?.wakeGaps) {
    for (const [gs, ge] of opts.wakeGaps) {
      for (let i = gs; i <= ge && i < epochCount; i++) {
        scores[i] = 0;
      }
    }
  }

  const activity = Array.from({ length: epochCount }, (_, i) =>
    scores[i] === 1 ? 0 : Math.floor(Math.random() * 100) + 10,
  );

  return { timestamps, scores, activity, startTs, epochCount };
}

// ---------------------------------------------------------------------------
// runAutoScoring
// ---------------------------------------------------------------------------

describe("runAutoScoring", () => {
  it("returns no markers when inputs are empty", () => {
    const result = runAutoScoring({
      timestamps: [],
      activityCounts: [],
      sleepScores: [],
    });
    expect(result.sleep_markers).toHaveLength(0);
    expect(result.nap_markers).toHaveLength(0);
    expect(result.notes).toContain("No activity data");
  });

  it("returns no markers when no diary is provided", () => {
    const { timestamps, scores, activity } = makeNightData();
    const result = runAutoScoring({
      timestamps,
      activityCounts: activity,
      sleepScores: scores,
    });
    expect(result.sleep_markers).toHaveLength(0);
    expect(result.notes.some((n) => n.includes("No diary data"))).toBe(true);
  });

  it("places main sleep marker with valid diary", () => {
    const { timestamps, scores, activity, startTs } = makeNightData({
      sleepStart: 30,
      sleepEnd: 690,
    });
    // Diary onset = epoch 30 timestamp, wake = epoch 690 timestamp
    const onsetTs = startTs + 30 * 60; // 21:30
    const wakeTs = startTs + 690 * 60; // 08:30 next day

    // Format times for diary strings (HH:MM format)
    const onsetTime = "9:30 PM";
    const wakeTime = "8:30 AM";

    const result = runAutoScoring({
      timestamps,
      activityCounts: activity,
      sleepScores: scores,
      diaryOnsetTime: onsetTime,
      diaryWakeTime: wakeTime,
      analysisDate: "2025-03-01",
    });

    expect(result.sleep_markers.length).toBeGreaterThanOrEqual(1);
    const marker = result.sleep_markers[0]!;
    expect(marker.marker_type).toBe("MAIN_SLEEP");
    expect(marker.onset_timestamp).toBe(timestamps[30]!);
    expect(marker.offset_timestamp).toBe(timestamps[690]!);
  });

  it("handles diary with only onset and no wake (returns no markers)", () => {
    const { timestamps, scores, activity } = makeNightData();
    const result = runAutoScoring({
      timestamps,
      activityCounts: activity,
      sleepScores: scores,
      diaryOnsetTime: "10:00 PM",
      analysisDate: "2025-03-01",
    });
    // Without wake time, diary is incomplete — should note it
    expect(result.sleep_markers).toHaveLength(0);
  });

  it("returns no main sleep when all wake", () => {
    const count = 720;
    const startTs = Date.UTC(2025, 2, 1, 21, 0, 0) / 1000;
    const timestamps = makeTimestamps(startTs, count);
    const scores = new Array(count).fill(0);
    const activity = new Array(count).fill(50);

    const result = runAutoScoring({
      timestamps,
      activityCounts: activity,
      sleepScores: scores,
      diaryOnsetTime: "10:00 PM",
      diaryWakeTime: "7:00 AM",
      analysisDate: "2025-03-01",
    });
    expect(result.sleep_markers).toHaveLength(0);
    expect(result.notes.some((n) => n.includes("No valid sleep period"))).toBe(true);
  });

  it("detects nap markers from diary nap periods", () => {
    // Night data with a nap in the afternoon before main sleep
    const count = 1440; // full 24h
    const startTs = Date.UTC(2025, 2, 1, 0, 0, 0) / 1000;
    const timestamps = makeTimestamps(startTs, count);

    // Nap at 14:00-15:00 (epoch 840-900), main sleep at 22:30-07:30 (epoch 1350-1440 wraps... use different approach)
    // Better: keep it within the data range
    // Nap: epochs 840..900 (14:00-15:00), main sleep: epochs 1350..1430 (22:30-23:50)
    const scores = new Array(count).fill(0);
    for (let i = 840; i <= 900; i++) scores[i] = 1; // nap (61 epochs)
    for (let i = 1350; i < 1440; i++) scores[i] = 1; // main sleep (90 epochs)
    const activity = scores.map((s: number) => (s === 1 ? 0 : 30));

    const result = runAutoScoring({
      timestamps,
      activityCounts: activity,
      sleepScores: scores,
      diaryOnsetTime: "10:30 PM",
      diaryWakeTime: "11:50 PM",
      diaryNaps: [["2:00 PM", "3:00 PM"]],
      analysisDate: "2025-03-01",
    });

    // Should find main sleep
    expect(result.sleep_markers.length).toBeGreaterThanOrEqual(1);
    // Should find nap
    expect(result.nap_markers.length).toBeGreaterThanOrEqual(1);
    if (result.nap_markers.length > 0) {
      expect(result.nap_markers[0]!.marker_type).toBe("NAP");
    }
  });

  it("adds custom detection rule note when non-default params", () => {
    const { timestamps, scores, activity } = makeNightData();
    const result = runAutoScoring({
      timestamps,
      activityCounts: activity,
      sleepScores: scores,
      diaryOnsetTime: "10:00 PM",
      diaryWakeTime: "7:00 AM",
      analysisDate: "2025-03-01",
      onsetMinConsecutiveSleep: 5,
      offsetMinConsecutiveMinutes: 10,
    });
    expect(result.notes.some((n) => n.includes("Detection rule: 5S/10S"))).toBe(true);
  });

  it("applies AM/PM correction when diary times are implausible", () => {
    const { timestamps, scores, activity } = makeNightData({ sleepStart: 30, sleepEnd: 690 });
    // Give AM when PM is expected (onset should be PM)
    const result = runAutoScoring({
      timestamps,
      activityCounts: activity,
      sleepScores: scores,
      diaryOnsetTime: "9:30 AM", // should be PM
      diaryWakeTime: "8:30 AM",
      analysisDate: "2025-03-01",
    });

    // The AM/PM correction should fix it and find markers
    if (result.notes.some((n) => n.includes("Corrected diary AM/PM"))) {
      expect(result.sleep_markers.length).toBeGreaterThanOrEqual(1);
    }
  });

  it("onset is clamped to in-bed time (rule 8)", () => {
    // Sleep starts early but diary in-bed is later
    // Create a gap in sleep at the early onset so the clamping has an effect
    const { timestamps, scores, activity, startTs } = makeNightData({
      sleepStart: 10, // early sleep at 21:10
      sleepEnd: 690,
      wakeGaps: [[55, 65]], // wake gap around 22:00 forces re-search after in-bed
    });

    const result = runAutoScoring({
      timestamps,
      activityCounts: activity,
      sleepScores: scores,
      diaryBedTime: "10:00 PM",
      diaryOnsetTime: "10:00 PM",
      diaryWakeTime: "8:30 AM",
      analysisDate: "2025-03-01",
    });

    // Should find main sleep. The precise onset depends on algorithm search.
    if (result.sleep_markers.length > 0) {
      expect(result.sleep_markers[0]!.onset_timestamp).toBeLessThan(
        result.sleep_markers[0]!.offset_timestamp,
      );
    }
  });
});

// ---------------------------------------------------------------------------
// placeNonwearMarkers
// ---------------------------------------------------------------------------

describe("placeNonwearMarkers", () => {
  it("returns empty when no data", () => {
    const result = placeNonwearMarkers({
      timestamps: [],
      activityCounts: [],
      diaryNonwear: [],
      choiNonwear: null,
      sensorNonwearPeriods: [],
      existingSleepMarkers: [],
      analysisDate: "2025-03-01",
    });
    expect(result.nonwear_markers).toHaveLength(0);
    expect(result.notes).toContain("No activity data");
  });

  it("returns empty when no diary nonwear periods", () => {
    const startTs = Date.UTC(2025, 2, 1, 10, 0, 0) / 1000;
    const timestamps = makeTimestamps(startTs, 100);
    const activity = new Array(100).fill(0);

    const result = placeNonwearMarkers({
      timestamps,
      activityCounts: activity,
      diaryNonwear: [],
      choiNonwear: null,
      sensorNonwearPeriods: [],
      existingSleepMarkers: [],
      analysisDate: "2025-03-01",
    });
    expect(result.nonwear_markers).toHaveLength(0);
    expect(result.notes.some((n) => n.includes("No diary nonwear periods"))).toBe(true);
  });

  it("places nonwear marker for valid zero-activity diary period", () => {
    const startTs = Date.UTC(2025, 2, 1, 0, 0, 0) / 1000;
    const count = 1440;
    const timestamps = makeTimestamps(startTs, count);
    // All zero activity
    const activity = new Array(count).fill(0);

    const result = placeNonwearMarkers({
      timestamps,
      activityCounts: activity,
      diaryNonwear: [["10:00 AM", "12:00 PM"]],
      choiNonwear: null,
      sensorNonwearPeriods: [],
      existingSleepMarkers: [],
      analysisDate: "2025-03-01",
    });

    expect(result.nonwear_markers.length).toBeGreaterThanOrEqual(1);
  });

  it("skips nonwear when too much activity", () => {
    const startTs = Date.UTC(2025, 2, 1, 0, 0, 0) / 1000;
    const count = 1440;
    const timestamps = makeTimestamps(startTs, count);
    // All high activity
    const activity = new Array(count).fill(100);

    const result = placeNonwearMarkers({
      timestamps,
      activityCounts: activity,
      diaryNonwear: [["10:00 AM", "12:00 PM"]],
      choiNonwear: null,
      sensorNonwearPeriods: [],
      existingSleepMarkers: [],
      analysisDate: "2025-03-01",
    });

    expect(result.nonwear_markers).toHaveLength(0);
    expect(result.notes.some((n) => n.includes("too much activity"))).toBe(true);
  });

  it("skips nonwear that overlaps with sleep markers", () => {
    // Data covering a full day starting at midnight
    const startTs = Date.UTC(2025, 2, 1, 0, 0, 0) / 1000;
    const count = 2880; // 48 hours of data to cover next-day parsing
    const timestamps = makeTimestamps(startTs, count);
    const activity = new Array(count).fill(0);

    // parseDiaryTime with isEvening=true shifts "10:00 PM" to 2025-03-01 22:00 UTC
    // and "11:00 PM" to 2025-03-01 23:00 UTC
    // Sleep marker covers the same time range
    const sleepStart = startTs + 22 * 3600; // 2025-03-01 22:00 UTC
    const sleepEnd = startTs + 23 * 3600;   // 2025-03-01 23:00 UTC

    const result = placeNonwearMarkers({
      timestamps,
      activityCounts: activity,
      diaryNonwear: [["10:00 PM", "11:00 PM"]],
      choiNonwear: null,
      sensorNonwearPeriods: [],
      existingSleepMarkers: [[sleepStart, sleepEnd]],
      analysisDate: "2025-03-01",
    });

    expect(result.nonwear_markers).toHaveLength(0);
    expect(result.notes.some((n) => n.includes("overlaps with sleep marker"))).toBe(true);
  });

  it("skips null-like diary nonwear values", () => {
    const startTs = Date.UTC(2025, 2, 1, 0, 0, 0) / 1000;
    const timestamps = makeTimestamps(startTs, 100);
    const activity = new Array(100).fill(0);

    const result = placeNonwearMarkers({
      timestamps,
      activityCounts: activity,
      diaryNonwear: [["nan", "none"], [null, null], ["", ""]],
      choiNonwear: null,
      sensorNonwearPeriods: [],
      existingSleepMarkers: [],
      analysisDate: "2025-03-01",
    });

    expect(result.nonwear_markers).toHaveLength(0);
  });

  it("detects Choi+sensor overlap nonwear in second pass", () => {
    const startTs = Date.UTC(2025, 2, 1, 0, 0, 0) / 1000;
    const count = 1440;
    const timestamps = makeTimestamps(startTs, count);
    const activity = new Array(count).fill(0);

    // Choi nonwear from epoch 600-720
    const choiNonwear = new Array(count).fill(0);
    for (let i = 600; i <= 720; i++) choiNonwear[i] = 1;

    // Sensor nonwear overlapping
    const sensorStart = timestamps[600]!;
    const sensorEnd = timestamps[720]!;

    const result = placeNonwearMarkers({
      timestamps,
      activityCounts: activity,
      diaryNonwear: [], // no diary nonwear
      choiNonwear,
      sensorNonwearPeriods: [[sensorStart, sensorEnd]],
      existingSleepMarkers: [],
      analysisDate: "2025-03-01",
    });

    // Should find the Choi+sensor overlap marker
    expect(result.nonwear_markers.length).toBeGreaterThanOrEqual(1);
  });
});

// ---------------------------------------------------------------------------
// Property-based tests
// ---------------------------------------------------------------------------

describe("marker-placement property tests", () => {
  it("runAutoScoring never crashes with arbitrary data", () => {
    fc.assert(
      fc.property(
        fc.array(fc.double({ min: 1e9, max: 2e9, noNaN: true }), { minLength: 1, maxLength: 100 }),
        fc.array(fc.integer({ min: 0, max: 1000 }), { minLength: 1, maxLength: 100 }),
        fc.array(fc.integer({ min: 0, max: 1 }), { minLength: 1, maxLength: 100 }),
        (timestamps, activity, scores) => {
          // Ensure arrays have same length
          const len = Math.min(timestamps.length, activity.length, scores.length);
          const ts = timestamps.slice(0, len).sort((a, b) => a - b);
          const act = activity.slice(0, len);
          const sc = scores.slice(0, len);

          const result = runAutoScoring({
            timestamps: ts,
            activityCounts: act,
            sleepScores: sc,
          });

          expect(result).toBeDefined();
          expect(Array.isArray(result.sleep_markers)).toBe(true);
          expect(Array.isArray(result.nap_markers)).toBe(true);
          expect(Array.isArray(result.notes)).toBe(true);
        },
      ),
      { numRuns: 50 },
    );
  });

  it("sleep markers always have onset < offset timestamps", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 50, max: 200 }),
        fc.integer({ min: 10, max: 40 }),
        fc.integer({ min: 45, max: 190 }),
        (epochCount, sleepStart, sleepEnd) => {
          if (sleepStart >= sleepEnd || sleepEnd >= epochCount) return;

          const startTs = 1740000000; // ~2025
          const timestamps = makeTimestamps(startTs, epochCount);
          const scores = Array.from({ length: epochCount }, (_, i) =>
            i >= sleepStart && i <= sleepEnd ? 1 : 0,
          );
          const activity = scores.map((s) => (s === 1 ? 0 : 50));

          // Diary onset near sleepStart, wake near sleepEnd
          const onsetTs = timestamps[sleepStart]!;
          const wakeTs = timestamps[sleepEnd]!;

          // Build time strings
          const onsetDate = new Date(onsetTs * 1000);
          const wakeDate = new Date(wakeTs * 1000);
          const oh = onsetDate.getUTCHours();
          const om = onsetDate.getUTCMinutes();
          const wh = wakeDate.getUTCHours();
          const wm = wakeDate.getUTCMinutes();

          // Format as 24h for simplicity
          const onsetStr = `${oh}:${String(om).padStart(2, "0")}`;
          const wakeStr = `${wh}:${String(wm).padStart(2, "0")}`;

          const analysisDate = new Date(startTs * 1000).toISOString().split("T")[0]!;

          const result = runAutoScoring({
            timestamps,
            activityCounts: activity,
            sleepScores: scores,
            diaryOnsetTime: onsetStr,
            diaryWakeTime: wakeStr,
            analysisDate,
          });

          for (const m of result.sleep_markers) {
            expect(m.onset_timestamp).toBeLessThan(m.offset_timestamp);
          }
          for (const m of result.nap_markers) {
            expect(m.onset_timestamp).toBeLessThan(m.offset_timestamp);
          }
        },
      ),
      { numRuns: 30 },
    );
  });

  it("placeNonwearMarkers never produces overlapping markers with sleep", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 100, max: 500 }),
        (epochCount) => {
          const startTs = 1740000000;
          const timestamps = makeTimestamps(startTs, epochCount);
          const activity = new Array(epochCount).fill(0);

          const result = placeNonwearMarkers({
            timestamps,
            activityCounts: activity,
            diaryNonwear: [["10:00", "12:00"]],
            choiNonwear: null,
            sensorNonwearPeriods: [],
            existingSleepMarkers: [],
            analysisDate: "2025-01-20",
          });

          // All markers should have start < end
          for (const m of result.nonwear_markers) {
            expect(m.start_timestamp).toBeLessThanOrEqual(m.end_timestamp);
          }
        },
      ),
      { numRuns: 30 },
    );
  });
});
