/**
 * Tests for formatting utilities.
 */
import { describe, it, expect } from "bun:test";
import {
  formatMinutes,
  formatPercent,
  formatNumber,
  formatTime,
  formatDuration,
  formatTimeDisplay,
} from "./formatters";

describe("formatMinutes", () => {
  it("should return '--' for null", () => {
    expect(formatMinutes(null)).toBe("--");
  });

  it("should return '--' for undefined", () => {
    expect(formatMinutes(undefined)).toBe("--");
  });

  it("should format minutes only when less than 60", () => {
    expect(formatMinutes(45)).toBe("45m");
  });

  it("should format hours and minutes", () => {
    expect(formatMinutes(90)).toBe("1h 30m");
  });

  it("should format exact hours", () => {
    expect(formatMinutes(120)).toBe("2h 0m");
  });

  it("should format zero minutes", () => {
    expect(formatMinutes(0)).toBe("0m");
  });

  it("should round fractional minutes", () => {
    expect(formatMinutes(45.7)).toBe("46m");
  });
});

describe("formatPercent", () => {
  it("should return '--' for null", () => {
    expect(formatPercent(null)).toBe("--");
  });

  it("should return '--' for undefined", () => {
    expect(formatPercent(undefined)).toBe("--");
  });

  it("should format percentage with one decimal", () => {
    expect(formatPercent(85.5)).toBe("85.5%");
  });

  it("should format zero percent", () => {
    expect(formatPercent(0)).toBe("0.0%");
  });

  it("should format 100 percent", () => {
    expect(formatPercent(100)).toBe("100.0%");
  });
});

describe("formatNumber", () => {
  it("should return '--' for null", () => {
    expect(formatNumber(null)).toBe("--");
  });

  it("should return '--' for undefined", () => {
    expect(formatNumber(undefined)).toBe("--");
  });

  it("should format with default 1 decimal", () => {
    expect(formatNumber(3.14159)).toBe("3.1");
  });

  it("should format with specified decimals", () => {
    expect(formatNumber(3.14159, 3)).toBe("3.142");
  });

  it("should format zero", () => {
    expect(formatNumber(0, 2)).toBe("0.00");
  });
});

describe("formatTime", () => {
  it("should return '--:--' for null", () => {
    expect(formatTime(null)).toBe("--:--");
  });

  it("should format Unix timestamp as HH:MM in UTC", () => {
    // 2024-01-01 12:10:00 UTC = 1704111000
    const result = formatTime(1704111000);
    expect(result).toContain("12");
    expect(result).toContain("10");
  });

  it("should format midnight", () => {
    // 2024-01-01 00:00:00 UTC = 1704067200
    const result = formatTime(1704067200);
    expect(result).toContain("00");
  });
});

describe("formatDuration", () => {
  it("should return '--' when start is null", () => {
    expect(formatDuration(null, 1000)).toBe("--");
  });

  it("should return '--' when end is null", () => {
    expect(formatDuration(1000, null)).toBe("--");
  });

  it("should format duration as hours and minutes", () => {
    // 1.5 hours = 5400 seconds
    expect(formatDuration(0, 5400)).toBe("1h 30m");
  });

  it("should handle zero duration", () => {
    expect(formatDuration(1000, 1000)).toBe("0h 0m");
  });

  it("should handle negative duration as zero", () => {
    expect(formatDuration(2000, 1000)).toBe("0h 0m");
  });
});

describe("formatTimeDisplay", () => {
  it("should return '--:--' for null", () => {
    expect(formatTimeDisplay(null)).toBe("--:--");
  });

  it("should return '--:--' for undefined", () => {
    expect(formatTimeDisplay(undefined)).toBe("--:--");
  });

  it("should return '--:--' for empty string", () => {
    expect(formatTimeDisplay("")).toBe("--:--");
  });

  it("should pass through valid time strings", () => {
    expect(formatTimeDisplay("14:30")).toBe("14:30");
  });
});
