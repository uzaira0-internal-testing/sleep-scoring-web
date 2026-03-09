// frontend/src/lib/color-themes.ts

/** Shape of a color theme — all values are solid hex (#RRGGBB). */
export interface ColorTheme {
  preset: string;
  onset: string;
  offset: string;
  sleepOverlay: string;
  nonwear: string;
  sensorNonwear: string;
  choiNonwear: string;
  activityLine: string;
}

/** Convert "#RRGGBB" to "rgba(r, g, b, alpha)". */
export function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Derive selected/unselected color pair from a base hex.
 * Selected = full color, Unselected = darkened by mixing toward black.
 */
export function markerColorPair(hex: string): { selected: string; unselected: string } {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  // Darken to ~50% for unselected
  const dr = Math.round(r * 0.5);
  const dg = Math.round(g * 0.5);
  const db = Math.round(b * 0.5);
  return {
    selected: hex,
    unselected: `#${dr.toString(16).padStart(2, "0")}${dg.toString(16).padStart(2, "0")}${db.toString(16).padStart(2, "0")}`,
  };
}

/** Derive a border color from a fill color (slightly darker/more opaque). */
export function overlayBorderColor(hex: string, alpha: number): string {
  const r = Math.round(parseInt(hex.slice(1, 3), 16) * 0.85);
  const g = Math.round(parseInt(hex.slice(3, 5), 16) * 0.85);
  const b = Math.round(parseInt(hex.slice(5, 7), 16) * 0.85);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// =============================================================================
// Presets
// =============================================================================

export const DEFAULT_COLOR_THEME: ColorTheme = {
  preset: "default",
  onset: "#0080FF",
  offset: "#FF8000",
  sleepOverlay: "#7C3AED",   // violet-600
  nonwear: "#DC143C",         // crimson
  sensorNonwear: "#FFD700",   // gold
  choiNonwear: "#9370DB",     // medium purple
  activityLine: "#0EA5E9",    // sky-500
};

export const COLOR_PRESETS: Record<string, ColorTheme> = {
  default: DEFAULT_COLOR_THEME,

  // Protanopia (no red cones): red appears BLACK/very dark.
  // Avoid red entirely. Use blue/yellow axis + cyan/gray/pink secondaries.
  // Based on Wong 2011 colorblind-safe palette.
  protanopia: {
    preset: "protanopia",
    onset: "#0072B2",          // strong blue (Wong)
    offset: "#E69F00",         // golden yellow (Wong) — high luminance contrast vs blue
    sleepOverlay: "#56B4E9",   // sky blue (Wong) — lighter than onset, distinguishable
    nonwear: "#888888",        // neutral gray — red would appear black to protanopes
    sensorNonwear: "#F0E442",  // bright yellow (Wong)
    choiNonwear: "#CC79A7",    // muted pink (Wong) — visible without red cones
    activityLine: "#009E73",   // bluish teal (Wong)
  },

  // Deuteranopia (no green cones): red and green MERGE but red stays bright.
  // Can use warm colors (magenta, orange) — just avoid green.
  // Based on Paul Tol's qualitative palette + Okabe-Ito.
  deuteranopia: {
    preset: "deuteranopia",
    onset: "#CC6677",          // rose (Paul Tol) — warm, distinct from offset
    offset: "#DDCC77",         // sand/gold (Paul Tol) — yellow-shifted, no green
    sleepOverlay: "#332288",   // indigo (Paul Tol) — deep blue, high contrast
    nonwear: "#EE7733",        // bright orange (distinct from rose onset)
    sensorNonwear: "#FFDD44",  // warm yellow
    choiNonwear: "#AA3377",    // magenta-wine (Paul Tol)
    activityLine: "#66CCEE",   // light cyan (Paul Tol) — no green component
  },

  // Tritanopia (blue-yellow-blind): avoid blue-yellow axis
  // Uses red/green/magenta/cyan
  tritanopia: {
    preset: "tritanopia",
    onset: "#D55E00",          // vermillion (Wong palette)
    offset: "#009E73",         // green (Wong palette)
    sleepOverlay: "#CC79A7",   // pink
    nonwear: "#E63946",        // red
    sensorNonwear: "#2A9D8F",  // teal
    choiNonwear: "#E9C46A",    // sand
    activityLine: "#264653",   // dark teal
  },

  // High contrast: maximum luminance separation between all elements
  "high-contrast": {
    preset: "high-contrast",
    onset: "#0000FF",          // pure blue
    offset: "#FF6600",         // bright orange
    sleepOverlay: "#FF00FF",   // magenta
    nonwear: "#FF0000",        // pure red
    sensorNonwear: "#FFFF00",  // pure yellow
    choiNonwear: "#00FFFF",    // cyan
    activityLine: "#00FF00",   // pure green
  },
};

export const PRESET_LABELS: Record<string, string> = {
  default: "Default",
  protanopia: "Protanopia (red-blind)",
  deuteranopia: "Deuteranopia (green-blind)",
  tritanopia: "Tritanopia (blue-yellow-blind)",
  "high-contrast": "High Contrast",
};
