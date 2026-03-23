/**
 * Tests for useKeyboardShortcuts — store-level behavior.
 *
 * Since useKeyboardShortcuts is a React hook, we test the underlying
 * store actions it calls: marker manipulation, date navigation, view mode toggle.
 */
import { describe, it, expect, beforeEach } from "bun:test";
import { useSleepScoringStore } from "@/store";
import { MARKER_TYPES } from "@/api/types";

const EPOCH_DURATION_SEC = 60;

/** Reset store to clean state before each test. */
function resetStore() {
  useSleepScoringStore.setState({
    sitePassword: null,
    username: "anonymous",
    isAuthenticated: false,
    currentFileId: null,
    currentFilename: null,
    currentDateIndex: 0,
    availableDates: ["2024-01-01", "2024-01-02", "2024-01-03"],
    availableFiles: [],
    sleepMarkers: [],
    nonwearMarkers: [],
    isDirty: false,
    selectedPeriodIndex: null,
    isNoSleep: false,
    markerMode: "sleep",
    creationMode: "idle",
    pendingOnsetTimestamp: null,
    preferredDisplayColumn: "axis_y",
    viewModeHours: 24,
    currentAlgorithm: "sadeh_1994_actilife",
    markerHistory: [],
    markerHistoryIndex: -1,
  });
}

describe("Keyboard Shortcut Store Actions", () => {
  beforeEach(resetStore);

  describe("Escape — cancelMarkerCreation", () => {
    it("should cancel creation and reset to idle", () => {
      // Simulate starting marker creation
      useSleepScoringStore.getState().setMarkerMode("sleep");
      useSleepScoringStore.getState().handlePlotClick(1000); // enters placing_onset
      expect(useSleepScoringStore.getState().creationMode).toBe("placing_onset");

      useSleepScoringStore.getState().cancelMarkerCreation();

      const state = useSleepScoringStore.getState();
      expect(state.creationMode).toBe("idle");
      expect(state.pendingOnsetTimestamp).toBeNull();
    });
  });

  describe("Delete — deleteMarker", () => {
    it("should delete selected sleep marker", () => {
      useSleepScoringStore.getState().addSleepMarker(1000, 2000);
      useSleepScoringStore.setState({ selectedPeriodIndex: 0 });

      useSleepScoringStore.getState().deleteMarker("sleep", 0);

      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(0);
      expect(useSleepScoringStore.getState().selectedPeriodIndex).toBeNull();
    });

    it("should delete selected nonwear marker", () => {
      useSleepScoringStore.getState().addNonwearMarker(1000, 2000);
      useSleepScoringStore.setState({ selectedPeriodIndex: 0 });

      useSleepScoringStore.getState().deleteMarker("nonwear", 0);

      expect(useSleepScoringStore.getState().nonwearMarkers).toHaveLength(0);
    });
  });

  describe("Q/E — move onset/start by epoch", () => {
    it("Q should move sleep onset left by one epoch", () => {
      useSleepScoringStore.getState().addSleepMarker(1000, 2000);
      const originalOnset = 1000;

      useSleepScoringStore.getState().updateMarker("sleep", 0, {
        onsetTimestamp: originalOnset - EPOCH_DURATION_SEC,
      });

      expect(useSleepScoringStore.getState().sleepMarkers[0]!.onsetTimestamp).toBe(940);
    });

    it("E should move sleep onset right by one epoch (but not past offset)", () => {
      useSleepScoringStore.getState().addSleepMarker(1000, 2000);

      const marker = useSleepScoringStore.getState().sleepMarkers[0]!;
      const newOnset = marker.onsetTimestamp + EPOCH_DURATION_SEC;
      // newOnset (1060) < offset (2000), so it should be allowed
      expect(newOnset < marker.offsetTimestamp).toBe(true);

      useSleepScoringStore.getState().updateMarker("sleep", 0, {
        onsetTimestamp: newOnset,
      });

      expect(useSleepScoringStore.getState().sleepMarkers[0]!.onsetTimestamp).toBe(1060);
    });
  });

  describe("A/D — move offset/end by epoch", () => {
    it("A should move sleep offset left by one epoch (but not before onset)", () => {
      useSleepScoringStore.getState().addSleepMarker(1000, 2000);

      const marker = useSleepScoringStore.getState().sleepMarkers[0]!;
      const newOffset = marker.offsetTimestamp - EPOCH_DURATION_SEC;
      expect(newOffset > marker.onsetTimestamp).toBe(true);

      useSleepScoringStore.getState().updateMarker("sleep", 0, {
        offsetTimestamp: newOffset,
      });

      expect(useSleepScoringStore.getState().sleepMarkers[0]!.offsetTimestamp).toBe(1940);
    });

    it("D should move sleep offset right by one epoch", () => {
      useSleepScoringStore.getState().addSleepMarker(1000, 2000);

      useSleepScoringStore.getState().updateMarker("sleep", 0, {
        offsetTimestamp: 2000 + EPOCH_DURATION_SEC,
      });

      expect(useSleepScoringStore.getState().sleepMarkers[0]!.offsetTimestamp).toBe(2060);
    });
  });

  describe("ArrowLeft/Right — date navigation", () => {
    it("ArrowRight should navigate to next date", () => {
      useSleepScoringStore.getState().navigateDate(1);
      expect(useSleepScoringStore.getState().currentDateIndex).toBe(1);
    });

    it("ArrowLeft should navigate to previous date", () => {
      useSleepScoringStore.setState({ currentDateIndex: 2 });
      useSleepScoringStore.getState().navigateDate(-1);
      expect(useSleepScoringStore.getState().currentDateIndex).toBe(1);
    });

    it("should not go below 0", () => {
      useSleepScoringStore.getState().navigateDate(-1);
      expect(useSleepScoringStore.getState().currentDateIndex).toBe(0);
    });

    it("should not go past last date", () => {
      useSleepScoringStore.setState({ currentDateIndex: 2 });
      useSleepScoringStore.getState().navigateDate(1);
      expect(useSleepScoringStore.getState().currentDateIndex).toBe(2);
    });
  });

  describe("Ctrl+4 — toggle view mode", () => {
    it("should toggle from 24 to 48", () => {
      useSleepScoringStore.getState().setViewModeHours(48);
      expect(useSleepScoringStore.getState().viewModeHours).toBe(48);
    });

    it("should toggle from 48 to 24", () => {
      useSleepScoringStore.setState({ viewModeHours: 48 });
      useSleepScoringStore.getState().setViewModeHours(24);
      expect(useSleepScoringStore.getState().viewModeHours).toBe(24);
    });
  });

  describe("Ctrl+Z / Ctrl+Shift+Z — undo/redo", () => {
    it("should undo a marker addition", () => {
      useSleepScoringStore.getState().addSleepMarker(1000, 2000);
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(1);

      useSleepScoringStore.getState().undo();
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(0);
    });

    it("should redo after undo", () => {
      useSleepScoringStore.getState().addSleepMarker(1000, 2000);
      useSleepScoringStore.getState().undo();
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(0);

      useSleepScoringStore.getState().redo();
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(1);
    });
  });

  describe("Nonwear marker adjustments", () => {
    it("should move nonwear start left by one epoch", () => {
      useSleepScoringStore.getState().addNonwearMarker(1000, 2000);

      useSleepScoringStore.getState().updateMarker("nonwear", 0, {
        startTimestamp: 1000 - EPOCH_DURATION_SEC,
      });

      expect(useSleepScoringStore.getState().nonwearMarkers[0]!.startTimestamp).toBe(940);
    });

    it("should move nonwear end right by one epoch", () => {
      useSleepScoringStore.getState().addNonwearMarker(1000, 2000);

      useSleepScoringStore.getState().updateMarker("nonwear", 0, {
        endTimestamp: 2000 + EPOCH_DURATION_SEC,
      });

      expect(useSleepScoringStore.getState().nonwearMarkers[0]!.endTimestamp).toBe(2060);
    });
  });
});
