/**
 * Tests for sleep period onset/offset detection.
 *
 * Mirrors desktop Python tests in tests/unit/core/test_consecutive_epochs.py.
 * Ensures the TypeScript port produces identical results to the desktop
 * ConsecutiveEpochsSleepPeriodDetector with default 3S/5S config.
 */

import { describe, it, expect } from "bun:test";
import {
  findMarkerIndexRange,
  findSleepOnset,
  findSleepOffset,
  findWakeOffset,
  detectSleepOnsetOffset,
} from "./sleep-rules";

// =============================================================================
// Test helpers
// =============================================================================

/** Create timestamps at 60-second intervals starting from a base */
function makeTimestamps(count: number, baseSec: number = 1705359600): number[] {
  return Array.from({ length: count }, (_, i) => baseSec + i * 60);
}

// =============================================================================
// findMarkerIndexRange
// =============================================================================

describe("findMarkerIndexRange", () => {
  const ts = makeTimestamps(20); // indices 0..19

  it("should find full range when marker covers all timestamps", () => {
    const result = findMarkerIndexRange(ts, ts[0]!, ts[19]!);
    expect(result).toEqual({ startIdx: 0, endIdx: 19 });
  });

  it("should find subset range", () => {
    const result = findMarkerIndexRange(ts, ts[5]!, ts[14]!);
    expect(result).toEqual({ startIdx: 5, endIdx: 14 });
  });

  it("should return null when marker is entirely before timestamps", () => {
    const result = findMarkerIndexRange(ts, ts[0]! - 200, ts[0]! - 100);
    expect(result).toBeNull();
  });

  it("should return null when marker is entirely after timestamps", () => {
    const result = findMarkerIndexRange(ts, ts[19]! + 100, ts[19]! + 200);
    // startIdx found but endIdx is null because no timestamps <= markerEnd
    // Actually: all timestamps are <= markerEnd here, so endIdx = 19
    // But startIdx would be null since no timestamp >= markerStart
    expect(result).toBeNull();
  });

  it("should handle empty timestamps", () => {
    const result = findMarkerIndexRange([], 100, 200);
    expect(result).toBeNull();
  });

  it("should snap to nearest epoch when marker falls between timestamps", () => {
    // Marker start between ts[2] and ts[3], marker end between ts[7] and ts[8]
    const result = findMarkerIndexRange(ts, ts[2]! + 30, ts[7]! + 30);
    // startIdx = 3 (first ts >= markerStart), endIdx = 7 (last ts <= markerEnd)
    expect(result).toEqual({ startIdx: 3, endIdx: 7 });
  });
});

// =============================================================================
// findSleepOnset
// =============================================================================

describe("findSleepOnset", () => {
  it("should find first 3 consecutive sleep epochs", () => {
    // Pattern: W W W S S S W W W W
    const scores = [0, 0, 0, 1, 1, 1, 0, 0, 0, 0];
    expect(findSleepOnset(scores, 0, 9)).toBe(3);
  });

  it("should skip runs shorter than onset_n", () => {
    // Pattern: W S S W S S S W W W  (first run is only 2)
    const scores = [0, 1, 1, 0, 1, 1, 1, 0, 0, 0];
    expect(findSleepOnset(scores, 0, 9)).toBe(4);
  });

  it("should return null when no consecutive run found", () => {
    // Pattern: W S W S W S W S W S  (alternating, never 3 consecutive)
    const scores = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1];
    expect(findSleepOnset(scores, 0, 9)).toBeNull();
  });

  it("should return null for all-wake data", () => {
    const scores = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    expect(findSleepOnset(scores, 0, 9)).toBeNull();
  });

  it("should find onset at start of range", () => {
    // Sleep starts right at startIdx
    const scores = [1, 1, 1, 0, 0, 0, 0, 0, 0, 0];
    expect(findSleepOnset(scores, 0, 9)).toBe(0);
  });

  it("should find onset at end of range when just enough room", () => {
    // 3 sleep epochs at indices 7,8,9
    const scores = [0, 0, 0, 0, 0, 0, 0, 1, 1, 1];
    expect(findSleepOnset(scores, 0, 9)).toBe(7);
  });

  it("should respect startIdx boundary", () => {
    // Sleep at 1,2,3 but startIdx=3, so not enough from startIdx
    // Sleep at 5,6,7 is the first valid run from startIdx=3
    const scores = [0, 1, 1, 1, 0, 1, 1, 1, 0, 0];
    expect(findSleepOnset(scores, 3, 9)).toBe(5);
  });

  it("should handle custom onset_n", () => {
    const scores = [0, 1, 1, 1, 1, 1, 0, 0, 0, 0];
    // With onset_n=5, need 5 consecutive
    expect(findSleepOnset(scores, 0, 9, 5)).toBe(1);
    // With onset_n=6, not enough
    expect(findSleepOnset(scores, 0, 9, 6)).toBeNull();
  });

  it("should return null for empty scores", () => {
    expect(findSleepOnset([], 0, 0)).toBeNull();
  });
});

// =============================================================================
// findSleepOffset
// =============================================================================

describe("findSleepOffset", () => {
  it("should find last 5 consecutive sleep epochs after onset", () => {
    // Pattern: S S S S S S S S S S  (all sleep, onset at 0)
    const scores = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1];
    const result = findSleepOffset(scores, 0, 9);
    expect(result).not.toBeNull();
    // Searching from 0+3=3, last run of 5 consecutive starting at 5 -> end at 9
    expect(result).toBe(9);
  });

  it("should return the LAST valid offset (latest time)", () => {
    // Two separate runs of 5 sleep after onset
    // Onset at 0, onset_n=3, so search from 3
    // Run 1: indices 3-7 (5 consecutive sleep)
    // Run 2: indices 10-14 (5 consecutive sleep)
    const scores = [1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0];
    const result = findSleepOffset(scores, 0, 19);
    // Last run ends at index 14 (10+5-1)
    expect(result).toBe(14);
  });

  it("should return null when no 5 consecutive sleep after onset", () => {
    // Only 4 sleep after onset
    const scores = [1, 1, 1, 1, 1, 1, 1, 0, 0, 0];
    // Onset=0, search from 3, need 5 consecutive from index 3+
    // indices 3,4,5,6 are sleep (4 epochs), then wake at 7 - not enough
    const result = findSleepOffset(scores, 0, 9);
    expect(result).toBeNull();
  });

  it("should not include onset epochs in offset search", () => {
    // Exactly 3+5=8 sleep epochs, onset at 0
    const scores = [1, 1, 1, 1, 1, 1, 1, 1, 0, 0];
    const result = findSleepOffset(scores, 0, 9);
    // Search from 3, run at 3-7 (5 epochs), end anchor = 7
    expect(result).toBe(7);
  });

  it("should handle custom offset_n", () => {
    const scores = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1];
    // offset_n=7, onset at 0, onset_n=3, search from 3
    // 7 consecutive needed from index 3: indices 3-9 (7 epochs)
    expect(findSleepOffset(scores, 0, 9, 3, 7)).toBe(9);
  });

  it("should return null for empty scores", () => {
    expect(findSleepOffset([], 0, 0)).toBeNull();
  });
});

// =============================================================================
// findWakeOffset (Tudor-Locke 2014 mode)
// =============================================================================

describe("findWakeOffset", () => {
  it("should find latest sleep epoch within marker that has 10 wake after it", () => {
    // Pattern: S S S S S S S S W W W W W W W W W W W W
    //          0 1 2 3 4 5 6 7 8 9 ...                 19
    // onset=0, onset_n=5, endIdx=19
    // Scan back from 19: epoch 7 is sleep, epochs 8-17 are 10 wake → return 7
    const scores = [1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    const result = findWakeOffset(scores, 0, 19, 5, 10);
    expect(result).toBe(7);
  });

  it("should return null when no 10 consecutive wake epochs exist", () => {
    const scores = Array(20).fill(1);
    expect(findWakeOffset(scores, 0, 19, 5, 10)).toBeNull();
  });

  it("should return null when wake runs are shorter than offsetN", () => {
    // Pattern: S S S S S S S W W W W W S S S S S S S S (only 5 wake, not 10)
    const scores = [1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1];
    expect(findWakeOffset(scores, 0, 19, 5, 10)).toBeNull();
  });

  it("should find the latest qualifying sleep epoch within marker range", () => {
    // Two sleep-then-wake transitions within marker
    // Pattern: S S S S S W(x10) S S S S S W(x10)
    const scores = [
      1, 1, 1, 1, 1,       // 0-4: sleep (onset region)
      0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // 5-14: first 10 wake
      1, 1, 1, 1, 1,       // 15-19: sleep
      0, 0, 0, 0, 0, 0, 0, 0, 0, 0, // 20-29: second 10 wake
    ];
    // onset=0, onset_n=5, endIdx=29
    // Scan back: epoch 19 is S, epochs 20-29 are 10 W → return 19
    const result = findWakeOffset(scores, 0, 29, 5, 10);
    expect(result).toBe(19);
  });

  it("should find offset when marker ends right on the last sleep epoch", () => {
    // User places marker offset on the last sleep epoch (endIdx=7)
    // Wake validation extends beyond marker into epochs 8-17
    // Pattern: S S S S S S S S W W W W W W W W W W W W
    //          0 1 2 3 4 5 6 7 8 ...                   19
    const scores = [1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    const result = findWakeOffset(scores, 0, 7, 5, 10);
    expect(result).toBe(7);
  });

  it("should return null when no sleep epoch in search range has 10 wake after", () => {
    // All wake — no sleep epoch after onset_n to return
    const scores = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    const result = findWakeOffset(scores, 0, 19, 3, 10);
    expect(result).toBeNull();
  });

  it("should pick the isolated sleep epoch right before a wake run", () => {
    // Pattern: S S S S S W S W W W W W W W W W W W
    //          0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17
    // onset=0, onset_n=5, endIdx=17
    // Scan back: epoch 6 is S, epochs 7-16 are 10 W → return 6
    const scores = [1, 1, 1, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    const result = findWakeOffset(scores, 0, 17, 5, 10);
    expect(result).toBe(6);
  });

  it("should handle wake starting right after onset region", () => {
    // Pattern: S S S S S W W W W W W W W W W W W W W W
    //          0 1 2 3 4 5 ...                          19
    // onset=0, onset_n=5, search from 5
    // No sleep epoch at index >= 5, so nothing qualifies → null
    const scores = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    const result = findWakeOffset(scores, 0, 19, 5, 10);
    expect(result).toBeNull();
  });

  it("should find sleep epoch at searchStart boundary", () => {
    // Pattern: S S S S S S W W W W W W W W W W W W W W
    //          0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19
    // onset=0, onset_n=5, search from 5, endIdx=19
    // Epoch 5 is S, epochs 6-15 are 10 W → return 5
    const scores = [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    const result = findWakeOffset(scores, 0, 19, 5, 10);
    expect(result).toBe(5);
  });
});

// =============================================================================
// detectSleepOnsetOffset (integration - matches desktop apply_rules)
// =============================================================================

describe("detectSleepOnsetOffset", () => {
  it("should find onset and offset for typical sleep pattern", () => {
    // Matches desktop test: sleep_pattern fixture
    // Pattern: 0,0,0,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0
    const scores = [0, 0, 0, ...Array(11).fill(1), ...Array(6).fill(0)];
    const ts = makeTimestamps(20);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[19]!);

    expect(result.onsetIndex).toBe(3); // First of 3 consecutive sleep
    expect(result.offsetIndex).not.toBeNull();
    expect(result.onsetIndex!).toBeLessThan(result.offsetIndex!);
  });

  it("should match desktop: onset at index 3 for [0,0,0,1,1,1...]", () => {
    const scores = [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0];
    const ts = makeTimestamps(20);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[19]!);
    expect(result.onsetIndex).toBe(3);
  });

  it("should match desktop: offset is LAST run end for default 5S config", () => {
    // 11 consecutive sleep from index 3 to 13
    // Offset search from 3+3=6, finding runs of 5:
    // Run at 6: 6,7,8,9,10 -> end=10
    // Run at 7: 7,8,9,10,11 -> end=11
    // Run at 8: 8,9,10,11,12 -> end=12
    // Run at 9: 9,10,11,12,13 -> end=13
    // LAST valid = 13
    const scores = [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0];
    const ts = makeTimestamps(20);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[19]!);
    expect(result.offsetIndex).toBe(13);
  });

  it("should restrict search to marker range", () => {
    // Sleep everywhere but marker only covers indices 5-14
    const scores = Array(20).fill(1);
    const ts = makeTimestamps(20);

    const result = detectSleepOnsetOffset(scores, ts, ts[5]!, ts[14]!);
    // Onset should be at index 5 (first in range), not 0
    expect(result.onsetIndex).toBe(5);
  });

  it("should return both null for all-wake data", () => {
    const scores = Array(20).fill(0);
    const ts = makeTimestamps(20);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[19]!);
    expect(result.onsetIndex).toBeNull();
    expect(result.offsetIndex).toBeNull();
  });

  it("should return both null for empty input", () => {
    const result = detectSleepOnsetOffset([], [], 0, 100);
    expect(result.onsetIndex).toBeNull();
    expect(result.offsetIndex).toBeNull();
  });

  it("should return onset but null offset when not enough sleep after onset", () => {
    // Only 3+3=6 sleep epochs total - enough for onset but not offset
    const scores = [0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    const ts = makeTimestamps(20);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[19]!);
    expect(result.onsetIndex).toBe(2);
    // After onset (2) + onset_n (3) = search from 5, only 5,6,7 are sleep (3 epochs) - not enough for 5
    expect(result.offsetIndex).toBeNull();
  });

  it("should handle marker range that falls between timestamps", () => {
    const ts = makeTimestamps(20);
    const scores = [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0];

    // Marker starts at ts[2]+30 (between index 2 and 3), ends at ts[15]+30
    const result = detectSleepOnsetOffset(scores, ts, ts[2]! + 30, ts[15]! + 30);
    // startIdx = 3 (first ts >= markerStart), endIdx = 15
    expect(result.onsetIndex).toBe(3);
  });

  it("should handle single sleep epoch (not enough for onset)", () => {
    const scores = [0, 0, 0, 1, 0, 0, 0, 0, 0, 0];
    const ts = makeTimestamps(10);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[9]!);
    expect(result.onsetIndex).toBeNull();
    expect(result.offsetIndex).toBeNull();
  });

  it("should handle two sleep epochs (not enough for onset=3)", () => {
    const scores = [0, 0, 0, 1, 1, 0, 0, 0, 0, 0];
    const ts = makeTimestamps(10);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[9]!);
    expect(result.onsetIndex).toBeNull();
  });

  it("should handle exactly 3 sleep epochs (onset only, no offset)", () => {
    const scores = [0, 0, 0, 1, 1, 1, 0, 0, 0, 0];
    const ts = makeTimestamps(10);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[9]!);
    expect(result.onsetIndex).toBe(3);
    // Need 5 consecutive after onset+3=6, but 6,7,8,9 are all wake
    expect(result.offsetIndex).toBeNull();
  });

  it("should handle fragmented sleep (multiple short runs)", () => {
    // Two short runs of 3 sleep separated by wake
    const scores = [0, 1, 1, 1, 0, 0, 1, 1, 1, 0];
    const ts = makeTimestamps(10);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[9]!);
    expect(result.onsetIndex).toBe(1); // First run of 3
    expect(result.offsetIndex).toBeNull(); // No 5-consecutive after onset
  });

  it("should handle all-sleep data", () => {
    const scores = Array(20).fill(1);
    const ts = makeTimestamps(20);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[19]!);
    expect(result.onsetIndex).toBe(0);
    // Last run of 5: starts at max valid position, anchored at end
    expect(result.offsetIndex).toBe(19);
  });

  it("should support custom onset/offset N values", () => {
    const scores = [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0];
    const ts = makeTimestamps(20);

    // onset_n=5, offset_n=7
    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[19]!, 5, 7);
    expect(result.onsetIndex).toBe(1); // First 5 consecutive at 1
    // Search from 1+5=6, last 7 consecutive: 6..12, 7..13, 8..14 -> last end=14
    expect(result.offsetIndex).toBe(14);
  });

  it("should handle wake-sleep-wake-sleep pattern", () => {
    // W W S S S W W S S S S S S S S W W W W W
    const scores = [0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0];
    const ts = makeTimestamps(20);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[19]!);
    // Onset at first 3-consecutive: index 2
    expect(result.onsetIndex).toBe(2);
    // Offset search from 2+3=5, runs of 5 consecutive sleep:
    // 7,8,9,10,11 -> end=11; 8,9,10,11,12 -> end=12; 9,10,11,12,13 -> end=13; 10,11,12,13,14 -> end=14
    // LAST = 14
    expect(result.offsetIndex).toBe(14);
  });

  it("should produce onset before offset", () => {
    const scores = [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0];
    const ts = makeTimestamps(20);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[19]!);
    expect(result.onsetIndex).not.toBeNull();
    expect(result.offsetIndex).not.toBeNull();
    expect(result.onsetIndex!).toBeLessThan(result.offsetIndex!);
  });
});

// =============================================================================
// detectSleepOnsetOffset with offsetState="wake" (Tudor-Locke 2014)
// =============================================================================

describe("detectSleepOnsetOffset (Tudor-Locke wake mode)", () => {
  it("should find offset as last sleep before 10 consecutive wake", () => {
    // Pattern: W W S S S S S S S S S S W W W W W W W W W W W W
    //          0 1 2 3 4 5 6 7 8 9 10 11 12 ...                23
    const scores = [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    const ts = makeTimestamps(24);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[23]!, 5, 10, "wake");
    expect(result.onsetIndex).toBe(2);
    // Wake run at 12..21 (10 consecutive), walk back from 11 → sleep at 11
    expect(result.offsetIndex).toBe(11);
  });

  it("should return null offset when no 10 consecutive wake exists", () => {
    // All sleep after onset
    const scores = [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1];
    const ts = makeTimestamps(20);

    const result = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[19]!, 5, 10, "wake");
    expect(result.onsetIndex).toBe(2);
    expect(result.offsetIndex).toBeNull();
  });

  it("should differ from sleep mode on the same data", () => {
    // Pattern with 10 consecutive wake at end
    const scores = [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    const ts = makeTimestamps(24);

    const sleepResult = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[23]!, 5, 10, "sleep");
    const wakeResult = detectSleepOnsetOffset(scores, ts, ts[0]!, ts[23]!, 5, 10, "wake");

    // Both should find onset at 2
    expect(sleepResult.onsetIndex).toBe(2);
    expect(wakeResult.onsetIndex).toBe(2);

    // Sleep mode: last 10 consecutive sleep, end anchor
    // Wake mode: last sleep before 10 consecutive wake
    // These should be different
    expect(sleepResult.offsetIndex).not.toEqual(wakeResult.offsetIndex);
  });
});
