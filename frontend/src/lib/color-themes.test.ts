/**
 * Tests for color-themes.ts — color theme utilities and presets.
 */
import { describe, it, expect } from "bun:test";
import {
  hexToRgba,
  markerColorPair,
  overlayBorderColor,
  DEFAULT_COLOR_THEME,
  COLOR_PRESETS,
  PRESET_LABELS,
} from "./color-themes";

describe("hexToRgba", () => {
  it("converts white with full opacity", () => {
    expect(hexToRgba("#FFFFFF", 1)).toBe("rgba(255, 255, 255, 1)");
  });

  it("converts black with half opacity", () => {
    expect(hexToRgba("#000000", 0.5)).toBe("rgba(0, 0, 0, 0.5)");
  });

  it("converts arbitrary color", () => {
    expect(hexToRgba("#0080FF", 0.3)).toBe("rgba(0, 128, 255, 0.3)");
  });

  it("handles zero alpha", () => {
    expect(hexToRgba("#FF0000", 0)).toBe("rgba(255, 0, 0, 0)");
  });
});

describe("markerColorPair", () => {
  it("returns original color as selected", () => {
    const pair = markerColorPair("#0080FF");
    expect(pair.selected).toBe("#0080FF");
  });

  it("returns darkened color as unselected", () => {
    const pair = markerColorPair("#FF8000");
    expect(pair.unselected).not.toBe("#FF8000");
    // Unselected should be darker (lower values)
    const r = parseInt(pair.unselected.slice(1, 3), 16);
    const g = parseInt(pair.unselected.slice(3, 5), 16);
    const b = parseInt(pair.unselected.slice(5, 7), 16);
    expect(r).toBeLessThanOrEqual(255);
    expect(r).toBeLessThan(0xff);
  });

  it("darkens to ~50%", () => {
    const pair = markerColorPair("#FFFFFF");
    // 255 * 0.5 = 128 = 0x80
    expect(pair.unselected).toBe("#808080");
  });

  it("darkens pure red", () => {
    const pair = markerColorPair("#FF0000");
    expect(pair.unselected).toBe("#800000");
  });
});

describe("overlayBorderColor", () => {
  it("darkens by 15%", () => {
    const result = overlayBorderColor("#FFFFFF", 1);
    // 255 * 0.85 = 217 = 0xd9
    expect(result).toBe("rgba(217, 217, 217, 1)");
  });

  it("applies alpha", () => {
    const result = overlayBorderColor("#000000", 0.5);
    expect(result).toBe("rgba(0, 0, 0, 0.5)");
  });
});

describe("COLOR_PRESETS", () => {
  it("includes default preset", () => {
    expect(COLOR_PRESETS.default).toEqual(DEFAULT_COLOR_THEME);
  });

  it("includes all accessibility presets", () => {
    expect(COLOR_PRESETS.protanopia).toBeDefined();
    expect(COLOR_PRESETS.deuteranopia).toBeDefined();
    expect(COLOR_PRESETS.tritanopia).toBeDefined();
    expect(COLOR_PRESETS["high-contrast"]).toBeDefined();
  });

  it("all presets have required color fields", () => {
    const requiredKeys = [
      "preset", "onset", "offset", "sleepOverlay",
      "nonwear", "sensorNonwear", "choiNonwear", "activityLine",
    ];
    for (const [name, preset] of Object.entries(COLOR_PRESETS)) {
      for (const key of requiredKeys) {
        expect(preset).toHaveProperty(key);
      }
      // All color values should be valid hex
      for (const key of requiredKeys.filter((k) => k !== "preset")) {
        const val = preset[key as keyof typeof preset];
        expect(val).toMatch(/^#[0-9A-Fa-f]{6}$/);
      }
    }
  });

  it("PRESET_LABELS has an entry for each preset", () => {
    for (const key of Object.keys(COLOR_PRESETS)) {
      expect(PRESET_LABELS[key]).toBeDefined();
      expect(typeof PRESET_LABELS[key]).toBe("string");
    }
  });
});
