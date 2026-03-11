/**
 * Tests for the undo/redo system in the Zustand store (Phase 6).
 *
 * Validates:
 * - Snapshot creation on marker mutations
 * - Undo restores previous state
 * - Redo restores forward state
 * - History truncation at MAX_HISTORY
 * - History cleared on date navigation
 * - canUndo/canRedo flags
 */

import { describe, it, expect, beforeEach } from "bun:test";
import { useSleepScoringStore } from "./index";

describe("Undo/Redo System", () => {
  beforeEach(() => {
    useSleepScoringStore.setState({
      sitePassword: null,
      username: "anonymous",
      isAuthenticated: false,
      currentFileId: null,
      currentFilename: null,
      currentDateIndex: 0,
      availableDates: ["2024-01-01", "2024-01-02", "2024-01-03"],
      availableFiles: [],
      timestamps: [],
      axisX: [],
      axisY: [],
      axisZ: [],
      vectorMagnitude: [],
      algorithmResults: null,
      isLoading: false,
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
  });

  describe("canUndo / canRedo", () => {
    it("should start with canUndo=false and canRedo=false", () => {
      const state = useSleepScoringStore.getState();
      expect(state.canUndo()).toBe(false);
      expect(state.canRedo()).toBe(false);
    });

    it("should have canUndo=true after two mutations (need 2+ snapshots)", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();
      // First mutation creates snapshot at index 0
      addSleepMarker(1000, 2000);
      // Second mutation creates snapshot at index 1 → canUndo since index > 0
      addSleepMarker(3000, 4000);

      const state = useSleepScoringStore.getState();
      expect(state.canUndo()).toBe(true);
      expect(state.canRedo()).toBe(false);
    });

    it("should have canRedo=true after undoing", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();
      addSleepMarker(1000, 2000);

      const { undo } = useSleepScoringStore.getState();
      undo();

      const state = useSleepScoringStore.getState();
      expect(state.canUndo()).toBe(false);
      expect(state.canRedo()).toBe(true);
    });
  });

  describe("Undo", () => {
    it("should restore previous marker state", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();

      // Add a marker
      addSleepMarker(1000, 2000);
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(1);

      // Undo
      const { undo } = useSleepScoringStore.getState();
      undo();

      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(0);
    });

    it("should handle multiple undos", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();

      addSleepMarker(1000, 2000);
      addSleepMarker(3000, 4000);
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(2);

      // Undo once - back to 1 marker
      useSleepScoringStore.getState().undo();
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(1);

      // Undo again - back to 0 markers
      useSleepScoringStore.getState().undo();
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(0);
    });

    it("should be a no-op when nothing to undo", () => {
      const { undo } = useSleepScoringStore.getState();
      undo(); // Should not throw

      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(0);
    });
  });

  describe("Redo", () => {
    it("should restore forward state after undo", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();

      addSleepMarker(1000, 2000);
      useSleepScoringStore.getState().undo();
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(0);

      useSleepScoringStore.getState().redo();
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(1);
    });

    it("should be a no-op when nothing to redo", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();
      addSleepMarker(1000, 2000);

      useSleepScoringStore.getState().redo(); // Should not throw
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(1);
    });

    it("should clear redo history when a new action is performed after undo", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();

      addSleepMarker(1000, 2000);
      addSleepMarker(3000, 4000);

      // Undo
      useSleepScoringStore.getState().undo();
      expect(useSleepScoringStore.getState().canRedo()).toBe(true);

      // New action should clear redo history
      useSleepScoringStore.getState().addSleepMarker(5000, 6000);
      expect(useSleepScoringStore.getState().canRedo()).toBe(false);
    });
  });

  describe("Snapshot triggers", () => {
    it("should push snapshot when adding sleep markers", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();
      addSleepMarker(1000, 2000);

      expect(useSleepScoringStore.getState().markerHistory.length).toBeGreaterThan(0);
    });

    it("should push snapshot when adding nonwear markers", () => {
      const { addNonwearMarker } = useSleepScoringStore.getState();
      addNonwearMarker(1000, 2000);

      expect(useSleepScoringStore.getState().markerHistory.length).toBeGreaterThan(0);
    });

    it("should push snapshot when deleting markers", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();
      addSleepMarker(1000, 2000);

      const historyBefore = useSleepScoringStore.getState().markerHistory.length;
      useSleepScoringStore.getState().deleteMarker("sleep", 0);
      const historyAfter = useSleepScoringStore.getState().markerHistory.length;

      expect(historyAfter).toBeGreaterThan(historyBefore);
    });

    it("should push snapshot when setting No Sleep", () => {
      const { setIsNoSleep } = useSleepScoringStore.getState();
      setIsNoSleep(true);

      expect(useSleepScoringStore.getState().markerHistory.length).toBeGreaterThan(0);
    });
  });

  describe("History limits", () => {
    it("should not exceed MAX_HISTORY (50) entries", () => {
      // Use setSleepMarkers (not addSleepMarker) to avoid the 4-marker-per-day limit
      // Each call pushes a snapshot
      for (let i = 0; i < 60; i++) {
        useSleepScoringStore.getState().setSleepMarkers([
          { onsetTimestamp: i * 1000, offsetTimestamp: i * 1000 + 500, markerIndex: 1, markerType: "MAIN_SLEEP" as const },
        ]);
      }

      // History should be capped at 50
      const state = useSleepScoringStore.getState();
      expect(state.markerHistory.length).toBeLessThanOrEqual(50);
    });
  });

  describe("Date navigation clears history", () => {
    it("should clear undo history when navigating dates", () => {
      const { addSleepMarker, navigateDate } = useSleepScoringStore.getState();

      addSleepMarker(1000, 2000);
      addSleepMarker(3000, 4000);
      expect(useSleepScoringStore.getState().canUndo()).toBe(true);

      // Navigate to next date
      navigateDate(1);

      const state = useSleepScoringStore.getState();
      expect(state.markerHistory).toHaveLength(0);
      expect(state.markerHistoryIndex).toBe(-1);
      expect(state.canUndo()).toBe(false);
      expect(state.canRedo()).toBe(false);
    });
  });

  describe("Undo preserves marker types", () => {
    it("should preserve NAP marker type through undo/redo cycle", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();

      // Add a NAP marker
      addSleepMarker(1000, 2000, "NAP");
      expect(useSleepScoringStore.getState().sleepMarkers[0]!.markerType).toBe("NAP");

      // Add another marker
      addSleepMarker(3000, 4000);

      // Undo back to just the NAP
      useSleepScoringStore.getState().undo();
      const markers = useSleepScoringStore.getState().sleepMarkers;
      expect(markers).toHaveLength(1);
      expect(markers[0]!.markerType).toBe("NAP");
    });
  });
});
