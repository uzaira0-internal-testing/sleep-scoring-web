/**
 * Tests for timestamp conversion utilities.
 */

import { describe, it, expect } from "bun:test";
import {
  toMilliseconds,
  toSeconds,
  isSeconds,
  isMilliseconds,
  snapToEpoch,
  dateToSeconds,
  secondsToDate,
  EPOCH_DURATION_SECONDS,
} from "./timestamps";

describe("timestamps utilities", () => {
  describe("toMilliseconds", () => {
    it("should return null for null input", () => {
      expect(toMilliseconds(null)).toBeNull();
    });

    it("should return null for undefined input", () => {
      expect(toMilliseconds(undefined)).toBeNull();
    });

    it("should convert seconds to milliseconds", () => {
      const seconds = 1704067200; // 2024-01-01 00:00:00 UTC
      expect(toMilliseconds(seconds)).toBe(1704067200000);
    });

    it("should keep milliseconds as-is", () => {
      const ms = 1704067200000; // Already milliseconds
      expect(toMilliseconds(ms)).toBe(1704067200000);
    });

    it("should handle boundary cases correctly", () => {
      // Just under cutoff - treated as seconds
      expect(toMilliseconds(9999999999)).toBe(9999999999000);
      // Just over cutoff - treated as milliseconds
      expect(toMilliseconds(10000000001)).toBe(10000000001);
    });
  });

  describe("toSeconds", () => {
    it("should return null for null input", () => {
      expect(toSeconds(null)).toBeNull();
    });

    it("should return null for undefined input", () => {
      expect(toSeconds(undefined)).toBeNull();
    });

    it("should convert milliseconds to seconds", () => {
      const ms = 1704067200000;
      expect(toSeconds(ms)).toBe(1704067200);
    });

    it("should keep seconds as-is", () => {
      const seconds = 1704067200;
      expect(toSeconds(seconds)).toBe(1704067200);
    });

    it("should handle boundary cases correctly", () => {
      // Just under cutoff - treated as seconds, kept as-is
      expect(toSeconds(9999999999)).toBe(9999999999);
      // Just over cutoff - treated as milliseconds, converted
      expect(toSeconds(10000000001)).toBe(10000000.001);
    });
  });

  describe("isSeconds", () => {
    it("should return true for typical Unix seconds", () => {
      expect(isSeconds(1704067200)).toBe(true);
    });

    it("should return false for milliseconds", () => {
      expect(isSeconds(1704067200000)).toBe(false);
    });
  });

  describe("isMilliseconds", () => {
    it("should return false for typical Unix seconds", () => {
      expect(isMilliseconds(1704067200)).toBe(false);
    });

    it("should return true for milliseconds", () => {
      expect(isMilliseconds(1704067200000)).toBe(true);
    });
  });

  describe("snapToEpoch", () => {
    it("should snap to nearest epoch boundary", () => {
      // Already on epoch boundary
      expect(snapToEpoch(60)).toBe(60);
      expect(snapToEpoch(120)).toBe(120);

      // Should round down
      expect(snapToEpoch(89)).toBe(60);

      // Should round up
      expect(snapToEpoch(91)).toBe(120);

      // Midpoint rounds to nearest (banker's rounding depends on impl)
      expect(snapToEpoch(90)).toBe(120); // Math.round(90/60) * 60 = 2 * 60 = 120
    });

    it("should use 60 second epochs", () => {
      expect(EPOCH_DURATION_SECONDS).toBe(60);
    });
  });

  describe("dateToSeconds", () => {
    it("should return null for null input", () => {
      expect(dateToSeconds(null)).toBeNull();
    });

    it("should return null for undefined input", () => {
      expect(dateToSeconds(undefined)).toBeNull();
    });

    it("should convert Date object to seconds", () => {
      const date = new Date(1704067200000);
      expect(dateToSeconds(date)).toBe(1704067200);
    });

    it("should convert ISO string to seconds", () => {
      // Note: This test may vary by timezone
      const isoString = "2024-01-01T00:00:00.000Z";
      expect(dateToSeconds(isoString)).toBe(1704067200);
    });
  });

  describe("secondsToDate", () => {
    it("should return null for null input", () => {
      expect(secondsToDate(null)).toBeNull();
    });

    it("should return null for undefined input", () => {
      expect(secondsToDate(undefined)).toBeNull();
    });

    it("should convert seconds to Date object", () => {
      const date = secondsToDate(1704067200);
      expect(date).not.toBeNull();
      expect(date!.getTime()).toBe(1704067200000);
    });
  });
});
