import { useEffect, useCallback } from "react";
import { useSleepScoringStore, useMarkers, useDates } from "@/store";

/** Epoch duration for fine adjustments (60 seconds in ms) */
const EPOCH_DURATION_MS = 60 * 1000;

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
    markerMode,
    creationMode,
    selectedPeriodIndex,
    sleepMarkers,
    nonwearMarkers,
    cancelMarkerCreation,
    deleteMarker,
    updateMarker,
    setSleepMarkers,
    setNonwearMarkers,
    undo,
    redo,
  } = useMarkers();

  const { navigateDate } = useDates();

  // Get view mode toggle from store
  const viewModeHours = useSleepScoringStore((state) => state.viewModeHours);
  const setViewModeHours = useSleepScoringStore((state) => state.setViewModeHours);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      // Ignore if user is typing in an input field
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }

      switch (e.key) {
        case "Escape":
          // Cancel marker creation if in progress
          if (creationMode !== "idle") {
            e.preventDefault();
            cancelMarkerCreation();
          }
          break;

        case "Delete":
        case "Backspace":
          // Delete selected marker
          if (selectedPeriodIndex !== null) {
            e.preventDefault();
            deleteMarker(markerMode, selectedPeriodIndex);
          }
          break;

        case "q":
        case "Q":
          // Move onset/start left by 1 epoch
          if (selectedPeriodIndex !== null) {
            e.preventDefault();
            if (markerMode === "sleep") {
              const marker = sleepMarkers[selectedPeriodIndex];
              if (marker?.onsetTimestamp != null) {
                updateMarker("sleep", selectedPeriodIndex, {
                  onsetTimestamp: marker.onsetTimestamp - EPOCH_DURATION_MS,
                });
              }
            } else {
              const marker = nonwearMarkers[selectedPeriodIndex];
              if (marker?.startTimestamp != null) {
                updateMarker("nonwear", selectedPeriodIndex, {
                  startTimestamp: marker.startTimestamp - EPOCH_DURATION_MS,
                });
              }
            }
          }
          break;

        case "e":
        case "E":
          // Move onset/start right by 1 epoch
          if (selectedPeriodIndex !== null) {
            e.preventDefault();
            if (markerMode === "sleep") {
              const marker = sleepMarkers[selectedPeriodIndex];
              if (
                marker?.onsetTimestamp != null &&
                marker?.offsetTimestamp != null
              ) {
                const newOnset = marker.onsetTimestamp + EPOCH_DURATION_MS;
                // Don't allow onset to go past offset
                if (newOnset < marker.offsetTimestamp) {
                  updateMarker("sleep", selectedPeriodIndex, {
                    onsetTimestamp: newOnset,
                  });
                }
              }
            } else {
              const marker = nonwearMarkers[selectedPeriodIndex];
              if (
                marker?.startTimestamp != null &&
                marker?.endTimestamp != null
              ) {
                const newStart = marker.startTimestamp + EPOCH_DURATION_MS;
                if (newStart < marker.endTimestamp) {
                  updateMarker("nonwear", selectedPeriodIndex, {
                    startTimestamp: newStart,
                  });
                }
              }
            }
          }
          break;

        case "a":
        case "A":
          // Move offset/end left by 1 epoch
          if (selectedPeriodIndex !== null) {
            e.preventDefault();
            if (markerMode === "sleep") {
              const marker = sleepMarkers[selectedPeriodIndex];
              if (
                marker?.onsetTimestamp != null &&
                marker?.offsetTimestamp != null
              ) {
                const newOffset = marker.offsetTimestamp - EPOCH_DURATION_MS;
                // Don't allow offset to go before onset
                if (newOffset > marker.onsetTimestamp) {
                  updateMarker("sleep", selectedPeriodIndex, {
                    offsetTimestamp: newOffset,
                  });
                }
              }
            } else {
              const marker = nonwearMarkers[selectedPeriodIndex];
              if (
                marker?.startTimestamp != null &&
                marker?.endTimestamp != null
              ) {
                const newEnd = marker.endTimestamp - EPOCH_DURATION_MS;
                if (newEnd > marker.startTimestamp) {
                  updateMarker("nonwear", selectedPeriodIndex, {
                    endTimestamp: newEnd,
                  });
                }
              }
            }
          }
          break;

        case "d":
        case "D":
          // Move offset/end right by 1 epoch
          if (selectedPeriodIndex !== null) {
            e.preventDefault();
            if (markerMode === "sleep") {
              const marker = sleepMarkers[selectedPeriodIndex];
              if (marker?.offsetTimestamp != null) {
                updateMarker("sleep", selectedPeriodIndex, {
                  offsetTimestamp: marker.offsetTimestamp + EPOCH_DURATION_MS,
                });
              }
            } else {
              const marker = nonwearMarkers[selectedPeriodIndex];
              if (marker?.endTimestamp != null) {
                updateMarker("nonwear", selectedPeriodIndex, {
                  endTimestamp: marker.endTimestamp + EPOCH_DURATION_MS,
                });
              }
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
            setViewModeHours(viewModeHours === 24 ? 48 : 24);
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
            if (selectedPeriodIndex !== null) {
              e.preventDefault();
              deleteMarker(markerMode, selectedPeriodIndex);
            }
          }
          break;
      }
    },
    [
      markerMode,
      creationMode,
      selectedPeriodIndex,
      sleepMarkers,
      nonwearMarkers,
      cancelMarkerCreation,
      deleteMarker,
      updateMarker,
      navigateDate,
      viewModeHours,
      setViewModeHours,
      setSleepMarkers,
      setNonwearMarkers,
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
