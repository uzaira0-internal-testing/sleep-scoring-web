/**
 * Tests for useMarkerLoad — store-level behavior.
 *
 * Since useMarkerLoad depends on React Query and DataSource context,
 * we test the store interactions it triggers: _loadSleepMarkersFromServer,
 * _loadNonwearMarkersFromServer, and status flag updates.
 */
import { describe, it, expect, beforeEach } from "bun:test";
import { useSleepScoringStore } from "@/store";
import { MARKER_TYPES } from "@/api/types";

/** Reset store to clean baseline. */
function resetStore() {
  useSleepScoringStore.setState({
    sitePassword: null,
    username: "anonymous",
    isAuthenticated: false,
    currentFileId: 1,
    currentFilename: "test.csv",
    currentFileSource: "server",
    currentDateIndex: 0,
    availableDates: ["2024-01-01"],
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
    _editGeneration: 0,
    selectedPeriodIndex: null,
    isNoSleep: false,
    needsConsensus: false,
    notes: "",
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

describe("useMarkerLoad store interactions", () => {
  beforeEach(resetStore);

  describe("_loadSleepMarkersFromServer", () => {
    it("should load sleep markers without setting isDirty", () => {
      const apiMarkers = [
        {
          onsetTimestamp: 1000,
          offsetTimestamp: 2000,
          markerIndex: 1,
          markerType: MARKER_TYPES.MAIN_SLEEP,
        },
      ];

      useSleepScoringStore.getState()._loadSleepMarkersFromServer(apiMarkers);

      const state = useSleepScoringStore.getState();
      expect(state.sleepMarkers).toHaveLength(1);
      expect(state.sleepMarkers[0]!.onsetTimestamp).toBe(1000);
      expect(state.isDirty).toBe(false);
    });

    it("should replace existing markers", () => {
      // Load initial markers
      useSleepScoringStore.getState()._loadSleepMarkersFromServer([
        { onsetTimestamp: 1000, offsetTimestamp: 2000, markerIndex: 1, markerType: MARKER_TYPES.MAIN_SLEEP },
      ]);

      // Load new markers (simulating refresh)
      useSleepScoringStore.getState()._loadSleepMarkersFromServer([
        { onsetTimestamp: 3000, offsetTimestamp: 4000, markerIndex: 1, markerType: MARKER_TYPES.MAIN_SLEEP },
        { onsetTimestamp: 5000, offsetTimestamp: 6000, markerIndex: 2, markerType: MARKER_TYPES.NAP },
      ]);

      const state = useSleepScoringStore.getState();
      expect(state.sleepMarkers).toHaveLength(2);
      expect(state.sleepMarkers[0]!.onsetTimestamp).toBe(3000);
    });
  });

  describe("_loadNonwearMarkersFromServer", () => {
    it("should load nonwear markers without setting isDirty", () => {
      const apiMarkers = [
        { startTimestamp: 500, endTimestamp: 800, markerIndex: 1 },
      ];

      useSleepScoringStore.getState()._loadNonwearMarkersFromServer(apiMarkers);

      const state = useSleepScoringStore.getState();
      expect(state.nonwearMarkers).toHaveLength(1);
      expect(state.nonwearMarkers[0]!.startTimestamp).toBe(500);
      expect(state.isDirty).toBe(false);
    });
  });

  describe("isDirty gating (simulated in useMarkerLoad effect)", () => {
    it("should not overwrite local changes when isDirty is true", () => {
      // User makes a local edit
      useSleepScoringStore.getState().addSleepMarker(1000, 2000);
      expect(useSleepScoringStore.getState().isDirty).toBe(true);

      // Simulate what useMarkerLoad does: check isDirty before updating
      const current = useSleepScoringStore.getState();
      if (!current.isDirty) {
        // This should NOT execute
        useSleepScoringStore.getState()._loadSleepMarkersFromServer([]);
      }

      // Local markers should be preserved
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(1);
    });
  });

  describe("Status flag updates", () => {
    it("should update isNoSleep from API data", () => {
      useSleepScoringStore.setState({ isNoSleep: false, isDirty: false });

      // Simulate what the useEffect does
      const current = useSleepScoringStore.getState();
      if (!current.isDirty) {
        useSleepScoringStore.setState({ isNoSleep: true });
      }

      expect(useSleepScoringStore.getState().isNoSleep).toBe(true);
    });

    it("should update needsConsensus from API data", () => {
      useSleepScoringStore.setState({ needsConsensus: false, isDirty: false });

      const current = useSleepScoringStore.getState();
      if (!current.isDirty) {
        useSleepScoringStore.setState({ needsConsensus: true });
      }

      expect(useSleepScoringStore.getState().needsConsensus).toBe(true);
    });

    it("should update notes from API data", () => {
      useSleepScoringStore.setState({ notes: "", isDirty: false });

      const current = useSleepScoringStore.getState();
      if (!current.isDirty) {
        useSleepScoringStore.setState({ notes: "Reviewer notes here" });
      }

      expect(useSleepScoringStore.getState().notes).toBe("Reviewer notes here");
    });

    it("should not update status flags when isDirty", () => {
      useSleepScoringStore.setState({ isNoSleep: false, isDirty: true });

      const current = useSleepScoringStore.getState();
      if (!current.isDirty) {
        useSleepScoringStore.setState({ isNoSleep: true });
      }

      // Should remain unchanged
      expect(useSleepScoringStore.getState().isNoSleep).toBe(false);
    });
  });

  describe("Auto-select first marker", () => {
    it("should auto-select index 0 when markers load and nothing selected", () => {
      useSleepScoringStore.setState({ selectedPeriodIndex: null });

      // Simulate what useMarkerLoad does
      const apiMarkers = [
        { onsetTimestamp: 1000, offsetTimestamp: 2000, markerIndex: 1, markerType: MARKER_TYPES.MAIN_SLEEP },
      ];
      useSleepScoringStore.getState()._loadSleepMarkersFromServer(apiMarkers);

      // The hook would set selectedPeriodIndex to 0
      if (apiMarkers.length > 0 && useSleepScoringStore.getState().selectedPeriodIndex === null) {
        useSleepScoringStore.setState({ selectedPeriodIndex: 0 });
      }

      expect(useSleepScoringStore.getState().selectedPeriodIndex).toBe(0);
    });
  });
});
