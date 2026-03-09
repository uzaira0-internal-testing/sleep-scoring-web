import { useEffect } from "react";
import { useSleepScoringStore } from "@/store";
import { settingsApi } from "@/api/client";

/**
 * Syncs the color theme to the server (debounced) and updates CSS custom
 * properties so that Tailwind utility classes like `text-sleep` and
 * `text-nonwear` reflect the current theme.
 *
 * Primary persistence is localStorage (via Zustand persist middleware).
 * The server save is a nice-to-have for cross-device continuity.
 */
export function useColorThemeSync() {
  const colorTheme = useSleepScoringStore((state) => state.colorTheme);

  // --- Task 10: debounced save to server ---
  useEffect(() => {
    const timer = setTimeout(() => {
      settingsApi
        .updateSettings({ extra_settings: { color_theme: colorTheme } })
        .catch(() => {
          // Silently ignore — localStorage is the primary persistence layer
        });
    }, 2000);
    return () => clearTimeout(timer);
  }, [colorTheme]);

  // --- Task 11: sync CSS custom properties for text-sleep / text-nonwear ---
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--color-sleep", colorTheme.sleepOverlay);
    root.style.setProperty("--color-nonwear", colorTheme.nonwear);
  }, [colorTheme.sleepOverlay, colorTheme.nonwear]);
}
