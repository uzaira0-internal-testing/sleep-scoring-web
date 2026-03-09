# Color Theme & Colorblind Presets Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a color theme system with colorblind presets and per-element color pickers, accessible from the scoring toolbar.

**Architecture:** New `colorTheme` object in Zustand store holds 7 hex color values + preset name. Colors are read via `getState()` in canvas render callbacks and via reactive hooks in React components. Persisted to localStorage via Zustand persist middleware and synced to server via `extra_settings_json`. A popover on the toolbar provides preset selection and individual color pickers.

**Tech Stack:** React, Zustand, Tailwind CSS, uPlot (canvas), shadcn/ui Popover

---

### Task 1: Create color-themes.ts (types, presets, utilities)

**Files:**
- Create: `frontend/src/lib/color-themes.ts`

**Step 1: Create the color themes module**

```typescript
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

  // Protanopia (red-blind): avoid red-green axis
  // Uses blue/yellow/cyan/gray — all distinguishable without red cones
  protanopia: {
    preset: "protanopia",
    onset: "#0072B2",          // blue (Wong palette)
    offset: "#E69F00",         // orange/yellow (Wong palette)
    sleepOverlay: "#56B4E9",   // sky blue (Wong palette)
    nonwear: "#999999",        // gray (avoids red)
    sensorNonwear: "#F0E442",  // yellow (Wong palette)
    choiNonwear: "#CC79A7",    // pink (Wong palette)
    activityLine: "#009E73",   // teal (Wong palette)
  },

  // Deuteranopia (green-blind): avoid red-green axis
  // Similar to protanopia but tuned for deuteranopes
  deuteranopia: {
    preset: "deuteranopia",
    onset: "#0072B2",          // blue
    offset: "#E69F00",         // amber
    sleepOverlay: "#CC79A7",   // rose pink
    nonwear: "#882255",        // wine (Paul Tol palette)
    sensorNonwear: "#DDCC77",  // sand (Paul Tol palette)
    choiNonwear: "#AA4499",    // magenta (Paul Tol palette)
    activityLine: "#44AA99",   // teal (Paul Tol palette)
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
```

**Step 2: Verify no TypeScript errors**

Run: `cd /opt/sleep-scoring-web/monorepo/apps/sleep-scoring-demo/frontend && bunx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors related to color-themes.ts

---

### Task 2: Add ColorTheme state to Zustand store

**Files:**
- Modify: `frontend/src/store/index.ts`

**Step 1: Add import at top of file**

After existing imports, add:
```typescript
import { type ColorTheme, DEFAULT_COLOR_THEME, COLOR_PRESETS } from "@/lib/color-themes";
```

**Step 2: Add ColorThemeState interface**

After `UploadState` interface (around line 156), add:
```typescript
/**
 * Color theme state — per-user plot color preferences
 */
interface ColorThemeState {
  colorTheme: ColorTheme;
}
```

**Step 3: Extend SleepScoringState**

Add `ColorThemeState` to the extends list (line 161):
```typescript
interface SleepScoringState
  extends AuthState,
    FileState,
    ActivityState,
    MarkerState,
    UndoRedoState,
    PreferencesState,
    StudySettingsState,
    DataSettingsState,
    UploadState,
    ColorThemeState {
```

**Step 4: Add action declarations**

In the SleepScoringState interface action declarations section, add:
```typescript
  // Color theme actions
  setColorTheme: (updates: Partial<ColorTheme>) => void;
  applyColorPreset: (presetName: string) => void;
  resetColorTheme: () => void;
```

**Step 5: Add initial state + action implementations**

In the store creator, before the closing `}),` of the store (around line 903), add initial state:
```typescript
  // Color theme state
  colorTheme: { ...DEFAULT_COLOR_THEME },
```

Add action implementations:
```typescript
  // Color theme actions
  setColorTheme: (updates) =>
    set((state) => ({
      colorTheme: { ...state.colorTheme, ...updates, preset: "custom" },
    })),

  applyColorPreset: (presetName) => {
    const preset = COLOR_PRESETS[presetName];
    if (preset) set({ colorTheme: { ...preset } });
  },

  resetColorTheme: () => set({ colorTheme: { ...DEFAULT_COLOR_THEME } }),
```

**Step 6: Add to partialize for localStorage persistence**

In the `partialize` function (around line 930), add:
```typescript
  // Color theme
  colorTheme: state.colorTheme,
```

**Step 7: Add selector hook**

After existing selector hooks (end of file), add:
```typescript
export const useColorTheme = () =>
  useSleepScoringStore(
    useShallow((state) => ({
      colorTheme: state.colorTheme,
      setColorTheme: state.setColorTheme,
      applyColorPreset: state.applyColorPreset,
      resetColorTheme: state.resetColorTheme,
    }))
  );
```

**Step 8: Verify no TypeScript errors**

Run: `cd /opt/sleep-scoring-web/monorepo/apps/sleep-scoring-demo/frontend && bunx tsc --noEmit --pretty 2>&1 | head -20`
Expected: Clean

---

### Task 3: Add color theme to user-state.ts persistence

**Files:**
- Modify: `frontend/src/lib/user-state.ts`

**Step 1: Add "colorTheme" to PERSISTED_KEYS**

Add `"colorTheme"` to the end of the `PERSISTED_KEYS` array (line 18):
```typescript
const PERSISTED_KEYS = [
  "currentFileId",
  "currentFilename",
  "currentDateIndex",
  "preferredDisplayColumn",
  "viewModeHours",
  "currentAlgorithm",
  "showAdjacentMarkers",
  "showNonwearOverlays",
  "autoScoreOnNavigate",
  "sleepDetectionRule",
  "nightStartHour",
  "nightEndHour",
  "devicePreset",
  "epochLengthSeconds",
  "skipRows",
  "colorTheme",
] as const;
```

---

### Task 4: Replace hardcoded colors in activity-plot.tsx

**Files:**
- Modify: `frontend/src/components/activity-plot.tsx`

This is the most critical task. The plot uses hardcoded hex/rgba colors throughout. We need to read from the store instead.

**Step 1: Add import**

At the top of activity-plot.tsx, add:
```typescript
import { hexToRgba, markerColorPair, overlayBorderColor } from "@/lib/color-themes";
```

**Step 2: Read color theme in renderMarkers function**

Inside the `renderMarkers` callback (around line 247, after `getMarkerState()` call), add:
```typescript
    const { colorTheme } = useSleepScoringStore.getState();
```

**Step 3: Replace sleep marker colors (lines 278-279)**

Replace:
```typescript
      const onsetColor = isSelected ? "#0080FF" : "#004080";
      const offsetColor = isSelected ? "#FF8000" : "#CC4000";
```
With:
```typescript
      const { selected: onsetSel, unselected: onsetUnsel } = markerColorPair(colorTheme.onset);
      const { selected: offsetSel, unselected: offsetUnsel } = markerColorPair(colorTheme.offset);
      const onsetColor = isSelected ? onsetSel : onsetUnsel;
      const offsetColor = isSelected ? offsetSel : offsetUnsel;
```

**Step 4: Replace nonwear marker colors (lines 306-307)**

Replace:
```typescript
      const startColor = isSelected ? "#DC143C" : "#8B0000";
      const endColor = isSelected ? "#B22222" : "#660000";
```
With:
```typescript
      const { selected: nwStartSel, unselected: nwStartUnsel } = markerColorPair(colorTheme.nonwear);
      const startColor = isSelected ? nwStartSel : nwStartUnsel;
      // End line is slightly different shade — darken further
      const { selected: nwEndSel, unselected: nwEndUnsel } = markerColorPair(
        markerColorPair(colorTheme.nonwear).unselected
      );
      const endColor = isSelected ? nwStartUnsel : nwEndUnsel;
```

Note: The original has 4 distinct nonwear colors (crimson/darkred/firebrick/verydarkred). We simplify to derive from a single base color using `markerColorPair` applied once for start and twice-darkened for end.

**Step 5: Replace sensor nonwear overlay colors (lines 253-254)**

Replace:
```typescript
    const sensorNwFill = "rgba(255, 215, 0, 0.24)";
    const sensorNwBorder = "rgba(218, 165, 32, 0.47)";
```
With:
```typescript
    const sensorNwFill = hexToRgba(colorTheme.sensorNonwear, 0.24);
    const sensorNwBorder = overlayBorderColor(colorTheme.sensorNonwear, 0.47);
```

**Step 6: Replace Choi nonwear overlay colors (lines 257-258)**

Replace:
```typescript
    const choiFill = "rgba(147, 112, 219, 0.24)";
    const choiBorder = "rgba(138, 43, 226, 0.47)";
```
With:
```typescript
    const choiFill = hexToRgba(colorTheme.choiNonwear, 0.24);
    const choiBorder = overlayBorderColor(colorTheme.choiNonwear, 0.47);
```

**Step 7: Replace sleep rule arrow colors (lines 427, 439)**

Replace `'#0066CC'` with `colorTheme.onset` and `'#FFA500'` with `colorTheme.offset`:

Line 427:
```typescript
            createSleepRuleArrow(wrapper, plotLeft, onsetPx, arrowY, colorTheme.onset, 'onset', selIdx,
```

Line 439:
```typescript
            createSleepRuleArrow(wrapper, plotLeft, offsetPx, arrowY, colorTheme.offset, 'offset', selIdx,
```

**Step 8: Replace uPlot series colors (lines 1237-1239)**

The activity line color. Replace:
```typescript
          stroke: isDark ? '#4fc3f7' : '#0ea5e9',
          width: 1,
          fill: isDark ? 'rgba(79, 195, 247, 0.1)' : 'rgba(14, 165, 233, 0.1)',
```
With:
```typescript
          stroke: colorTheme.activityLine,
          width: 1,
          fill: hexToRgba(colorTheme.activityLine, 0.1),
```

Note: This reads `colorTheme` from the store at uPlot initialization time. Since uPlot options are memoized and only recreated when dependencies change, add `colorTheme` to the uPlot options `useMemo` dependency array to trigger re-creation on color changes.

**Step 9: Replace cursor point colors (lines 1249-1250)**

Replace:
```typescript
          fill: isDark ? '#4fc3f7' : '#0ea5e9',
```
With:
```typescript
          fill: colorTheme.activityLine,
```

**Step 10: Add colorTheme to uPlot options dependency**

Find the `useMemo` that creates the uPlot options object. Add `colorTheme` to its dependency array. The store read needs to be done at the component level:

Near the top of the component, add:
```typescript
  const colorTheme = useSleepScoringStore((state) => state.colorTheme);
```

Then add `colorTheme` to the `useMemo` dependency array for the uPlot `opts` object.

**Step 11: Verify no TypeScript errors**

Run: `cd /opt/sleep-scoring-web/monorepo/apps/sleep-scoring-demo/frontend && bunx tsc --noEmit --pretty 2>&1 | head -20`
Expected: Clean

---

### Task 5: Replace hardcoded colors in marker-data-table.tsx

**Files:**
- Modify: `frontend/src/components/marker-data-table.tsx`

**Step 1: Add import and read color theme**

```typescript
import { hexToRgba } from "@/lib/color-themes";
import { useSleepScoringStore } from "@/store";
```

In the component body:
```typescript
  const colorTheme = useSleepScoringStore((state) => state.colorTheme);
```

**Step 2: Replace hardcoded OKLCH inline styles (lines 186-189)**

Replace:
```typescript
                  style={isMarkerRow ? {
                    backgroundColor: isSleepMode ? 'oklch(0.55 0.2 290 / 0.25)' : 'oklch(0.65 0.18 65 / 0.25)',
                    borderLeft: `3px solid ${isSleepMode ? 'oklch(0.55 0.2 290)' : 'oklch(0.65 0.18 65)'}`,
                    boxShadow: `inset 0 0 0 1px ${isSleepMode ? 'oklch(0.55 0.2 290 / 0.3)' : 'oklch(0.65 0.18 65 / 0.3)'}`,
                  } : undefined}
```
With:
```typescript
                  style={isMarkerRow ? {
                    backgroundColor: hexToRgba(isSleepMode ? colorTheme.sleepOverlay : colorTheme.nonwear, 0.25),
                    borderLeft: `3px solid ${isSleepMode ? colorTheme.sleepOverlay : colorTheme.nonwear}`,
                    boxShadow: `inset 0 0 0 1px ${hexToRgba(isSleepMode ? colorTheme.sleepOverlay : colorTheme.nonwear, 0.3)}`,
                  } : undefined}
```

---

### Task 6: Replace hardcoded colors in popout-table-dialog.tsx

**Files:**
- Modify: `frontend/src/components/popout-table-dialog.tsx`

**Step 1: Add import and read color theme**

Same pattern as marker-data-table:
```typescript
import { hexToRgba } from "@/lib/color-themes";
import { useSleepScoringStore } from "@/store";
```

In the component body:
```typescript
  const colorTheme = useSleepScoringStore((state) => state.colorTheme);
```

**Step 2: Replace hardcoded OKLCH inline styles (lines 212-214)**

Replace:
```typescript
                      style={isMarkerRow ? {
                        backgroundColor: isSleepMode ? 'oklch(0.55 0.2 290 / 0.25)' : 'oklch(0.65 0.18 65 / 0.25)',
                        borderLeftColor: isSleepMode ? 'oklch(0.55 0.2 290)' : 'oklch(0.65 0.18 65)',
                      } : undefined}
```
With:
```typescript
                      style={isMarkerRow ? {
                        backgroundColor: hexToRgba(isSleepMode ? colorTheme.sleepOverlay : colorTheme.nonwear, 0.25),
                        borderLeftColor: isSleepMode ? colorTheme.sleepOverlay : colorTheme.nonwear,
                      } : undefined}
```

---

### Task 7: Update color-legend-dialog.tsx

**Files:**
- Modify: `frontend/src/components/color-legend-dialog.tsx`

**Step 1: Add imports**

```typescript
import { useSleepScoringStore } from "@/store";
```

**Step 2: Read color theme in component**

```typescript
  const colorTheme = useSleepScoringStore((state) => state.colorTheme);
```

**Step 3: Replace all hardcoded swatches with dynamic colors**

Replace the entire content of the Dialog (the `<div className="space-y-6">` block) with swatches that read from `colorTheme`. Key changes:

- `bg-purple-500` → `style={{ backgroundColor: colorTheme.sleepOverlay }}`
- `bg-purple-600` (onset line) → `style={{ backgroundColor: colorTheme.onset }}`
- `bg-purple-400` (offset line) → `style={{ backgroundColor: colorTheme.offset }}`
- `bg-orange-500` (nonwear sensor) → `style={{ backgroundColor: colorTheme.sensorNonwear }}`
- `bg-red-500/30 border border-red-500` (choi) → `style={{ backgroundColor: hexToRgba(colorTheme.choiNonwear, 0.3), border: \`1px solid ${colorTheme.choiNonwear}\` }}`

**Step 4: Fix incorrect descriptions**

- Line 61: Change `"Diary-reported nonwear periods"` to `"Sensor-detected nonwear (from uploaded CSV data)"`
- Line 37-38: The onset line is blue, not purple — update description color to match

**Step 5: Remove duplicate keyboard shortcuts section**

Delete the entire keyboard shortcuts `<section>` (lines 112-137). This is already in the separate `keyboard-shortcuts-dialog.tsx`.

---

### Task 8: Create color-theme-popover.tsx

**Files:**
- Create: `frontend/src/components/color-theme-popover.tsx`

**Step 1: Create the popover component**

```typescript
import { Palette, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useColorTheme } from "@/store";
import { COLOR_PRESETS, PRESET_LABELS } from "@/lib/color-themes";

const COLOR_FIELDS: Array<{ key: string; label: string }> = [
  { key: "onset", label: "Onset" },
  { key: "offset", label: "Offset" },
  { key: "sleepOverlay", label: "Sleep Overlay" },
  { key: "nonwear", label: "Nonwear" },
  { key: "sensorNonwear", label: "Sensor Nonwear" },
  { key: "choiNonwear", label: "Choi Nonwear" },
  { key: "activityLine", label: "Activity Line" },
];

export function ColorThemePopover() {
  const { colorTheme, setColorTheme, applyColorPreset, resetColorTheme } =
    useColorTheme();

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          title="Color theme"
          data-testid="color-theme-btn"
        >
          <Palette className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64" align="end">
        <div className="space-y-3">
          <div className="text-sm font-medium">Color Theme</div>

          {/* Preset selector */}
          <div>
            <label className="text-xs text-muted-foreground">Preset</label>
            <select
              className="w-full mt-1 h-8 rounded-md border border-border bg-background px-2 text-sm"
              value={colorTheme.preset}
              onChange={(e) => applyColorPreset(e.target.value)}
            >
              {Object.entries(PRESET_LABELS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
              {!PRESET_LABELS[colorTheme.preset] && (
                <option value="custom" disabled>
                  Custom
                </option>
              )}
            </select>
          </div>

          {/* Individual color pickers */}
          <div className="space-y-1.5">
            {COLOR_FIELDS.map(({ key, label }) => (
              <div key={key} className="flex items-center gap-2">
                <input
                  type="color"
                  value={colorTheme[key as keyof typeof colorTheme] as string}
                  onChange={(e) =>
                    setColorTheme({ [key]: e.target.value })
                  }
                  className="h-6 w-6 rounded border border-border cursor-pointer bg-transparent"
                />
                <span className="text-xs">{label}</span>
              </div>
            ))}
          </div>

          {/* Reset button */}
          <Button
            variant="outline"
            size="sm"
            className="w-full h-7 text-xs gap-1"
            onClick={resetColorTheme}
          >
            <RotateCcw className="h-3 w-3" />
            Reset to Default
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
```

**Step 2: Verify no TypeScript errors**

Run: `cd /opt/sleep-scoring-web/monorepo/apps/sleep-scoring-demo/frontend && bunx tsc --noEmit --pretty 2>&1 | head -20`

---

### Task 9: Add ColorThemePopover to scoring.tsx toolbar

**Files:**
- Modify: `frontend/src/pages/scoring.tsx`

**Step 1: Add import**

```typescript
import { ColorThemePopover } from "@/components/color-theme-popover";
```

**Step 2: Add to toolbar Row 1, before help buttons**

Find the help buttons section (around line 566):
```tsx
        <div className="flex items-center gap-1 flex-none">
          <KeyboardShortcutsButton onClick={() => setShortcutsOpen(true)} />
          <ColorLegendButton onClick={() => setColorLegendOpen(true)} />
        </div>
```

Add `<ColorThemePopover />` before `KeyboardShortcutsButton`:
```tsx
        <div className="flex items-center gap-1 flex-none">
          <ColorThemePopover />
          <KeyboardShortcutsButton onClick={() => setShortcutsOpen(true)} />
          <ColorLegendButton onClick={() => setColorLegendOpen(true)} />
        </div>
```

---

### Task 10: Sync color theme to/from server

**Files:**
- Modify: `frontend/src/pages/scoring.tsx` (or a new hook)

**Step 1: Load color theme from server settings on initial fetch**

In the settings query effect in scoring.tsx (or wherever `GET /settings` response is processed), check for `color_theme` in `extra_settings`:

```typescript
// After settings are fetched, sync color theme if present
useEffect(() => {
  if (backendSettings?.extra_settings?.color_theme) {
    const serverTheme = backendSettings.extra_settings.color_theme;
    const currentTheme = useSleepScoringStore.getState().colorTheme;
    // Only apply server theme if it differs (avoid unnecessary re-renders)
    if (JSON.stringify(serverTheme) !== JSON.stringify(currentTheme)) {
      useSleepScoringStore.getState().setColorTheme(serverTheme);
    }
  }
}, [backendSettings]);
```

Note: Since localStorage persistence via Zustand is already faster (loads before React renders), this server sync is only needed for cross-device scenarios where localStorage is empty.

**Step 2: Save color theme to server on change (debounced)**

Create a small effect that saves color theme changes to the server:

```typescript
// In scoring.tsx or a new useColorThemeSync hook
useEffect(() => {
  const timer = setTimeout(() => {
    if (!currentFileId) return;
    settingsApi.updateSettings({
      extra_settings: { color_theme: colorTheme },
    }).catch(() => {
      // Silent fail — localStorage is the primary persistence
    });
  }, 2000); // 2 second debounce
  return () => clearTimeout(timer);
}, [colorTheme, currentFileId]);
```

---

### Task 11: Update CSS variables for text colors

**Files:**
- Modify: `frontend/src/index.css` (or via JS)

The CSS variables `--color-sleep` and `--color-nonwear` are used by Tailwind classes like `text-sleep` and `text-nonwear` in the side tables. These need to stay in sync with the color theme.

**Step 1: Add a CSS variable sync effect**

In the main App component or scoring.tsx, add an effect that updates CSS custom properties when the color theme changes:

```typescript
useEffect(() => {
  const root = document.documentElement;
  // Convert hex to oklch would be complex; instead just use hex directly
  root.style.setProperty("--color-sleep", colorTheme.sleepOverlay);
  root.style.setProperty("--color-nonwear", colorTheme.nonwear);
}, [colorTheme.sleepOverlay, colorTheme.nonwear]);
```

Note: The CSS variables are currently in oklch format. Setting them to hex will work because CSS `color` accepts hex. The Tailwind `text-sleep` class reads from `--color-sleep` which will now be a hex value instead of oklch — this is fine for `color` property usage.

---

### Task 12: Build and verify

**Step 1: Run typecheck**

```bash
cd /opt/sleep-scoring-web/monorepo/apps/sleep-scoring-demo/frontend && bun run typecheck
```
Expected: No errors

**Step 2: Rebuild containers**

```bash
cd /opt/sleep-scoring-web/monorepo/apps/sleep-scoring-demo/docker
docker compose -f docker-compose.local.yml up -d --build backend frontend
```

**Step 3: Verify containers are healthy**

```bash
docker compose -f docker-compose.local.yml ps
docker compose -f docker-compose.local.yml logs --tail=20 backend
docker compose -f docker-compose.local.yml logs --tail=20 frontend
```

**Step 4: Manual verification checklist**

- [ ] Palette button appears in toolbar next to shortcuts/help buttons
- [ ] Clicking palette opens a popover with preset dropdown and 7 color pickers
- [ ] Selecting a preset changes all 7 colors
- [ ] Individual color pickers work and set preset to "Custom"
- [ ] Reset button restores default colors
- [ ] Plot onset/offset lines reflect chosen colors
- [ ] Plot overlay regions (sensor nonwear, choi) reflect chosen colors
- [ ] Activity line color changes
- [ ] Side table row highlighting reflects chosen sleep/nonwear colors
- [ ] Color legend dialog shows dynamic swatches matching current theme
- [ ] Colors persist across page refresh (localStorage)
- [ ] Nonwear sensor description says "Sensor-detected nonwear" not "Diary-reported"
- [ ] Keyboard shortcuts section removed from color legend (only in shortcuts dialog)
