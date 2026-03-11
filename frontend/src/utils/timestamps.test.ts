/**
 * Tests for timestamp conversion utilities.
 */

import { describe, it, expect } from "bun:test";
import {
  snapToEpoch,
  dateToSeconds,
  secondsToDate,
  EPOCH_DURATION_SECONDS,
} from "./timestamps";

describe("timestamps utilities", () => {
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
