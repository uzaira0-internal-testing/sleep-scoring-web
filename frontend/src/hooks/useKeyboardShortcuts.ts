import { useEffect, useCallback } from "react";
import { useSleepScoringStore, useMarkers, useDates } from "@/store";

/** Epoch duration for fine adjustments (60 seconds) */
const EPOCH_DURATION_SEC = 60;

/**
 * Keyboard shortcuts for the scoring page.
 *
 * Shortcuts:
 * - Escape: Cancel marker creation in progress
 * - Delete/Backspace/C: Delete selected marker
 * - Q: Move selected marker onset left by 1 epoch
 * - E: Move selected marker onset right by 1 epoch
 * - A: Move selected marker offset left by 1 epoch
 * - D: Move selected marker offset right by 1 epoch
 * - ArrowLeft: Navigate to previous date
 * - ArrowRight: Navigate to next date
 * - Ctrl+4: Toggle 24h/48h view mode
 * - Ctrl+Shift+C: Clear all markers for current date
 */
export function useKeyboardShortcuts(onSave?: () => void, onConfirmClear?: () => void) {
  const {
    cancelMarkerCreation,
    deleteMarker,
    updateMarker,
    undo,
    redo,
  } = useMarkers();

  const { navigateDate } = useDates();

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      // Ignore if user is typing in an input field
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }

      // Read all mutable state from store to avoid stale closures (per CLAUDE.md)
      const state = useSleepScoringStore.getState();
      const currentMarkerMode = state.markerMode;
      const currentSelectedIndex = state.selectedPeriodIndex;
      const getMarker = () => {
        if (currentMarkerMode === "sleep") return state.sleepMarkers[currentSelectedIndex ?? -1];
        return state.nonwearMarkers[currentSelectedIndex ?? -1];
      };

      switch (e.key) {
        case "Escape":
          // Cancel marker creation if in progress
          if (state.creationMode !== "idle") {
            e.preventDefault();
            cancelMarkerCreation();
          }
          break;

        case "Delete":
        case "Backspace":
          // Delete selected marker
          if (currentSelectedIndex !== null) {
            e.preventDefault();
            deleteMarker(currentMarkerMode, currentSelectedIndex);
          }
          break;

        case "q":
        case "Q":
          // Move onset/start left by 1 epoch
          if (currentSelectedIndex !== null) {
            e.preventDefault();
            const marker = getMarker();
            if (currentMarkerMode === "sleep" && marker && "onsetTimestamp" in marker && marker.onsetTimestamp != null) {
              updateMarker("sleep", currentSelectedIndex, { onsetTimestamp: marker.onsetTimestamp - EPOCH_DURATION_SEC });
            } else if (marker && "startTimestamp" in marker && marker.startTimestamp != null) {
              updateMarker("nonwear", currentSelectedIndex, { startTimestamp: marker.startTimestamp - EPOCH_DURATION_SEC });
            }
          }
          break;

        case "e":
        case "E":
          // Move onset/start right by 1 epoch
          if (currentSelectedIndex !== null) {
            e.preventDefault();
            const marker = getMarker();
            if (currentMarkerMode === "sleep" && marker && "onsetTimestamp" in marker && marker.onsetTimestamp != null && marker.offsetTimestamp != null) {
              const newOnset = marker.onsetTimestamp + EPOCH_DURATION_SEC;
              if (newOnset < marker.offsetTimestamp) {
                updateMarker("sleep", currentSelectedIndex, { onsetTimestamp: newOnset });
              }
            } else if (marker && "startTimestamp" in marker && marker.startTimestamp != null && marker.endTimestamp != null) {
              const newStart = marker.startTimestamp + EPOCH_DURATION_SEC;
              if (newStart < marker.endTimestamp) {
                updateMarker("nonwear", currentSelectedIndex, { startTimestamp: newStart });
              }
            }
          }
          break;

        case "a":
        case "A":
          // Move offset/end left by 1 epoch
          if (currentSelectedIndex !== null) {
            e.preventDefault();
            const marker = getMarker();
            if (currentMarkerMode === "sleep" && marker && "onsetTimestamp" in marker && marker.onsetTimestamp != null && marker.offsetTimestamp != null) {
              const newOffset = marker.offsetTimestamp - EPOCH_DURATION_SEC;
              if (newOffset > marker.onsetTimestamp) {
                updateMarker("sleep", currentSelectedIndex, { offsetTimestamp: newOffset });
              }
            } else if (marker && "startTimestamp" in marker && marker.startTimestamp != null && marker.endTimestamp != null) {
              const newEnd = marker.endTimestamp - EPOCH_DURATION_SEC;
              if (newEnd > marker.startTimestamp) {
                updateMarker("nonwear", currentSelectedIndex, { endTimestamp: newEnd });
              }
            }
          }
          break;

        case "d":
        case "D":
          // Move offset/end right by 1 epoch
          if (currentSelectedIndex !== null) {
            e.preventDefault();
            const marker = getMarker();
            if (currentMarkerMode === "sleep" && marker && "onsetTimestamp" in marker && marker.offsetTimestamp != null) {
              updateMarker("sleep", currentSelectedIndex, { offsetTimestamp: marker.offsetTimestamp + EPOCH_DURATION_SEC });
            } else if (marker && "startTimestamp" in marker && marker.endTimestamp != null) {
              updateMarker("nonwear", currentSelectedIndex, { endTimestamp: marker.endTimestamp + EPOCH_DURATION_SEC });
            }
          }
          break;

        case "ArrowLeft":
          // Previous date (only if no modifier keys)
          if (!e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey) {
            e.preventDefault();
            navigateDate(-1);
          }
          break;

        case "ArrowRight":
          // Next date (only if no modifier keys)
          if (!e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey) {
            e.preventDefault();
            navigateDate(1);
          }
          break;

        case "4":
          // Ctrl+4: Toggle 24h/48h view mode
          if (e.ctrlKey && !e.shiftKey && !e.altKey) {
            e.preventDefault();
            const currentViewMode = useSleepScoringStore.getState().viewModeHours;
            useSleepScoringStore.getState().setViewModeHours(currentViewMode === 24 ? 48 : 24);
          }
          break;

        case "s":
        case "S":
          // Ctrl+S: Force save markers immediately
          if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) {
            e.preventDefault();
            onSave?.();
          }
          break;

        case "z":
        case "Z":
          if ((e.ctrlKey || e.metaKey) && !e.altKey) {
            e.preventDefault();
            if (e.shiftKey) {
              // Ctrl+Shift+Z: Redo
              redo();
            } else {
              // Ctrl+Z: Undo
              undo();
            }
          }
          break;

        case "y":
        case "Y":
          // Ctrl+Y: Redo (alternative)
          if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) {
            e.preventDefault();
            redo();
          }
          break;

        case "C":
        case "c":
          if (e.ctrlKey && e.shiftKey && !e.altKey) {
            // Ctrl+Shift+C: Clear all markers (with confirmation)
            e.preventDefault();
            if (onConfirmClear) {
              onConfirmClear();
            }
          } else if (!e.ctrlKey && !e.shiftKey && !e.altKey && !e.metaKey) {
            // C without modifiers: Delete selected marker (like desktop app)
            if (currentSelectedIndex !== null) {
              e.preventDefault();
              deleteMarker(currentMarkerMode, currentSelectedIndex);
            }
          }
          break;
      }
    },
    [
      cancelMarkerCreation,
      deleteMarker,
      updateMarker,
      navigateDate,
      undo,
      redo,
      onSave,
      onConfirmClear,
    ]
  );

  // Attach global keyboard listener
  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleKeyDown]);
}
