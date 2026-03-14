/**
 * Tests for the Zustand store.
 *
 * Uses Bun's built-in test runner.
 */

import { describe, it, expect, beforeEach } from "bun:test";
import { useSleepScoringStore } from "./index";
import { MARKER_TYPES } from "../api/types";

describe("SleepScoringStore", () => {
  // Reset store before each test
  beforeEach(() => {
    useSleepScoringStore.setState({
      sitePassword: null,
      username: "anonymous",
      isAuthenticated: false,
      currentFileId: null,
      currentFilename: null,
      currentDateIndex: 0,
      availableDates: [],
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
    });
  });

  describe("Auth state (site password model)", () => {
    it("should start with unauthenticated state", () => {
      const state = useSleepScoringStore.getState();

      expect(state.isAuthenticated).toBe(false);
      expect(state.sitePassword).toBeNull();
      expect(state.username).toBe("anonymous");
    });

    it("should set auth state correctly", () => {
      const { setAuth } = useSleepScoringStore.getState();

      setAuth("test-password", "testuser");

      const state = useSleepScoringStore.getState();
      expect(state.isAuthenticated).toBe(true);
      expect(state.sitePassword).toBe("test-password");
      expect(state.username).toBe("testuser");
    });

    it("should clear auth state correctly", () => {
      const { setAuth, clearAuth } = useSleepScoringStore.getState();

      // First set auth
      setAuth("test-password", "testuser");

      // Then clear it
      clearAuth();

      const state = useSleepScoringStore.getState();
      expect(state.isAuthenticated).toBe(false);
      expect(state.sitePassword).toBeNull();
      expect(state.username).toBe("anonymous");
    });
  });

  describe("File state", () => {
    it("should set current file correctly", () => {
      const { setCurrentFile } = useSleepScoringStore.getState();

      setCurrentFile(123, "test-file.csv");

      const state = useSleepScoringStore.getState();
      expect(state.currentFileId).toBe(123);
      expect(state.currentFilename).toBe("test-file.csv");
      // Should reset date index when file changes
      expect(state.currentDateIndex).toBe(0);
    });

    it("should set available files correctly", () => {
      const { setAvailableFiles } = useSleepScoringStore.getState();

      const files = [
        { id: 1, filename: "file1.csv", status: "ready", rowCount: 100 },
        { id: 2, filename: "file2.csv", status: "ready", rowCount: 200 },
      ];

      setAvailableFiles(files);

      const state = useSleepScoringStore.getState();
      expect(state.availableFiles).toHaveLength(2);
      expect(state.availableFiles[0]!.filename).toBe("file1.csv");
    });

    it("should set available dates correctly", () => {
      const { setAvailableDates } = useSleepScoringStore.getState();

      setAvailableDates(["2024-01-01", "2024-01-02", "2024-01-03"]);

      const state = useSleepScoringStore.getState();
      expect(state.availableDates).toHaveLength(3);
      expect(state.availableDates[0]).toBe("2024-01-01");
    });
  });

  describe("Date navigation", () => {
    beforeEach(() => {
      const { setAvailableDates } = useSleepScoringStore.getState();
      setAvailableDates(["2024-01-01", "2024-01-02", "2024-01-03"]);
    });

    it("should navigate forward", () => {
      const { navigateDate } = useSleepScoringStore.getState();

      navigateDate(1);

      const state = useSleepScoringStore.getState();
      expect(state.currentDateIndex).toBe(1);
    });

    it("should navigate backward", () => {
      // Start at index 2
      useSleepScoringStore.setState({ currentDateIndex: 2 });

      const { navigateDate } = useSleepScoringStore.getState();
      navigateDate(-1);

      const state = useSleepScoringStore.getState();
      expect(state.currentDateIndex).toBe(1);
    });

    it("should not navigate past end", () => {
      useSleepScoringStore.setState({ currentDateIndex: 2 });

      const { navigateDate } = useSleepScoringStore.getState();
      navigateDate(1);

      const state = useSleepScoringStore.getState();
      expect(state.currentDateIndex).toBe(2); // Should stay at 2
    });

    it("should not navigate before start", () => {
      const { navigateDate } = useSleepScoringStore.getState();
      navigateDate(-1);

      const state = useSleepScoringStore.getState();
      expect(state.currentDateIndex).toBe(0); // Should stay at 0
    });
  });

  describe("Activity data state", () => {
    it("should set activity data correctly", () => {
      const { setActivityData } = useSleepScoringStore.getState();

      setActivityData({
        timestamps: [1000, 2000, 3000],
        axisX: [10, 20, 30],
        axisY: [15, 25, 35],
        axisZ: [5, 10, 15],
        vectorMagnitude: [100, 200, 300],
        algorithmResults: [0, 1, 0],
      });

      const state = useSleepScoringStore.getState();
      expect(state.timestamps).toHaveLength(3);
      expect(state.axisY[1]).toBe(25);
      expect(state.algorithmResults).toEqual([0, 1, 0]);
      expect(state.isLoading).toBe(false);
    });

    it("should clear activity data correctly", () => {
      // First set some data
      const { setActivityData, clearActivityData } =
        useSleepScoringStore.getState();

      setActivityData({
        timestamps: [1000, 2000],
        axisX: [10, 20],
        axisY: [15, 25],
        axisZ: [5, 10],
        vectorMagnitude: [100, 200],
      });

      clearActivityData();

      const state = useSleepScoringStore.getState();
      expect(state.timestamps).toHaveLength(0);
      expect(state.axisY).toHaveLength(0);
    });

    it("should set loading state correctly", () => {
      const { setLoading } = useSleepScoringStore.getState();

      setLoading(true);
      expect(useSleepScoringStore.getState().isLoading).toBe(true);

      setLoading(false);
      expect(useSleepScoringStore.getState().isLoading).toBe(false);
    });
  });

  describe("Marker state", () => {
    it("should set sleep markers and mark dirty", () => {
      const { setSleepMarkers } = useSleepScoringStore.getState();

      const markers = [
        {
          onsetTimestamp: 1000,
          offsetTimestamp: 2000,
          markerIndex: 0,
          markerType: MARKER_TYPES.MAIN_SLEEP,
        },
      ];

      setSleepMarkers(markers);

      const state = useSleepScoringStore.getState();
      expect(state.sleepMarkers).toHaveLength(1);
      expect(state.isDirty).toBe(true);
    });

    it("should set nonwear markers and mark dirty", () => {
      const { setNonwearMarkers } = useSleepScoringStore.getState();

      const markers = [
        {
          startTimestamp: 1000,
          endTimestamp: 2000,
          markerIndex: 0,
        },
      ];

      setNonwearMarkers(markers);

      const state = useSleepScoringStore.getState();
      expect(state.nonwearMarkers).toHaveLength(1);
      expect(state.isDirty).toBe(true);
    });

    it("should set selected period index", () => {
      const { setSelectedPeriod } = useSleepScoringStore.getState();

      setSelectedPeriod(2);
      expect(useSleepScoringStore.getState().selectedPeriodIndex).toBe(2);

      setSelectedPeriod(null);
      expect(useSleepScoringStore.getState().selectedPeriodIndex).toBeNull();
    });
  });

  describe("No Sleep state", () => {
    it("should start with isNoSleep as false", () => {
      const state = useSleepScoringStore.getState();
      expect(state.isNoSleep).toBe(false);
    });

    it("should set isNoSleep to true and clear sleep markers", () => {
      const { setSleepMarkers, setIsNoSleep } = useSleepScoringStore.getState();

      // First add some sleep markers
      const markers = [
        {
          onsetTimestamp: 1000,
          offsetTimestamp: 2000,
          markerIndex: 0,
          markerType: MARKER_TYPES.MAIN_SLEEP,
        },
      ];
      setSleepMarkers(markers);
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(1);

      // Now set isNoSleep to true
      setIsNoSleep(true);

      const state = useSleepScoringStore.getState();
      expect(state.isNoSleep).toBe(true);
      expect(state.sleepMarkers).toHaveLength(0); // Should clear MAIN_SLEEP markers
      expect(state.isDirty).toBe(true);
      expect(state.selectedPeriodIndex).toBeNull();
    });

    it("should allow unsetting isNoSleep", () => {
      const { setIsNoSleep } = useSleepScoringStore.getState();

      // Set to true first
      setIsNoSleep(true);
      expect(useSleepScoringStore.getState().isNoSleep).toBe(true);

      // Then unset
      setIsNoSleep(false);

      const state = useSleepScoringStore.getState();
      expect(state.isNoSleep).toBe(false);
      expect(state.isDirty).toBe(true);
    });

    it("should allow NAP marker creation when isNoSleep is true", () => {
      const { setIsNoSleep, handlePlotClick, setMarkerMode } = useSleepScoringStore.getState();

      // Set no sleep
      setIsNoSleep(true);
      setMarkerMode("sleep");

      // Create a marker via two clicks — should be allowed as NAP
      handlePlotClick(1000);
      expect(useSleepScoringStore.getState().creationMode).toBe("placing_onset");

      handlePlotClick(2000);

      const state = useSleepScoringStore.getState();
      expect(state.sleepMarkers).toHaveLength(1);
      expect(state.sleepMarkers[0]!.markerType).toBe("NAP");
    });

    it("should allow nonwear marker creation when isNoSleep is true", () => {
      const { setIsNoSleep, handlePlotClick, setMarkerMode } = useSleepScoringStore.getState();

      // Set no sleep
      setIsNoSleep(true);
      setMarkerMode("nonwear");

      // Create a nonwear marker
      handlePlotClick(1000); // First click
      handlePlotClick(2000); // Second click

      const state = useSleepScoringStore.getState();
      expect(state.nonwearMarkers).toHaveLength(1);
      expect(state.nonwearMarkers[0]!.startTimestamp).toBe(1000);
      expect(state.nonwearMarkers[0]!.endTimestamp).toBe(2000);
    });
  });

  describe("Preferences state", () => {
    it("should set preferred display column", () => {
      const { setPreferredDisplayColumn } = useSleepScoringStore.getState();

      setPreferredDisplayColumn("vector_magnitude");
      expect(useSleepScoringStore.getState().preferredDisplayColumn).toBe(
        "vector_magnitude"
      );
    });

    it("should set view mode hours", () => {
      const { setViewModeHours } = useSleepScoringStore.getState();

      setViewModeHours(48);
      expect(useSleepScoringStore.getState().viewModeHours).toBe(48);
    });

    it("should set current algorithm", () => {
      const { setCurrentAlgorithm } = useSleepScoringStore.getState();

      setCurrentAlgorithm("cole_kripke_1992");
      expect(useSleepScoringStore.getState().currentAlgorithm).toBe(
        "cole_kripke_1992"
      );
    });
  });

  describe("addSleepMarker", () => {
    it("should add a sleep marker with correct markerType and increment _editGeneration", () => {
      const genBefore = useSleepScoringStore.getState()._editGeneration;
      const { addSleepMarker } = useSleepScoringStore.getState();

      addSleepMarker(1000, 2000);

      const state = useSleepScoringStore.getState();
      expect(state.sleepMarkers).toHaveLength(1);
      expect(state.sleepMarkers[0]!.onsetTimestamp).toBe(1000);
      expect(state.sleepMarkers[0]!.offsetTimestamp).toBe(2000);
      // First marker when isNoSleep=false should be MAIN_SLEEP
      expect(state.sleepMarkers[0]!.markerType).toBe(MARKER_TYPES.MAIN_SLEEP);
      expect(state.sleepMarkers[0]!.markerIndex).toBe(1); // 1-indexed
      expect(state.isDirty).toBe(true);
      expect(state._editGeneration).toBe(genBefore + 1);
    });

    it("should default to NAP for the second marker when isNoSleep is false", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();

      addSleepMarker(1000, 2000); // MAIN_SLEEP (first)
      addSleepMarker(3000, 4000); // NAP (second)

      const state = useSleepScoringStore.getState();
      expect(state.sleepMarkers).toHaveLength(2);
      expect(state.sleepMarkers[0]!.markerType).toBe(MARKER_TYPES.MAIN_SLEEP);
      expect(state.sleepMarkers[1]!.markerType).toBe(MARKER_TYPES.NAP);
    });
  });

  describe("addNonwearMarker", () => {
    it("should add a nonwear marker with start/end and increment _editGeneration", () => {
      const genBefore = useSleepScoringStore.getState()._editGeneration;
      const { addNonwearMarker } = useSleepScoringStore.getState();

      addNonwearMarker(5000, 6000);

      const state = useSleepScoringStore.getState();
      expect(state.nonwearMarkers).toHaveLength(1);
      expect(state.nonwearMarkers[0]!.startTimestamp).toBe(5000);
      expect(state.nonwearMarkers[0]!.endTimestamp).toBe(6000);
      expect(state.nonwearMarkers[0]!.markerIndex).toBe(1); // 1-indexed
      expect(state.isDirty).toBe(true);
      expect(state._editGeneration).toBe(genBefore + 1);
    });
  });

  describe("deleteMarker", () => {
    it("should remove the correct sleep marker by index and re-index remaining", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();

      addSleepMarker(1000, 2000);
      addSleepMarker(3000, 4000);
      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(2);

      useSleepScoringStore.getState().deleteMarker("sleep", 0);

      const state = useSleepScoringStore.getState();
      expect(state.sleepMarkers).toHaveLength(1);
      // The remaining marker should be the second one (onset=3000)
      expect(state.sleepMarkers[0]!.onsetTimestamp).toBe(3000);
      // markerIndex should be re-indexed to 1
      expect(state.sleepMarkers[0]!.markerIndex).toBe(1);
      expect(state.selectedPeriodIndex).toBeNull();
    });

    it("should remove the correct nonwear marker by index", () => {
      const { addNonwearMarker } = useSleepScoringStore.getState();

      addNonwearMarker(1000, 2000);
      addNonwearMarker(3000, 4000);

      useSleepScoringStore.getState().deleteMarker("nonwear", 1);

      const state = useSleepScoringStore.getState();
      expect(state.nonwearMarkers).toHaveLength(1);
      expect(state.nonwearMarkers[0]!.startTimestamp).toBe(1000);
    });
  });

  describe("toggleNoSleep (setIsNoSleep)", () => {
    it("should delete MAIN_SLEEP markers but preserve NAP markers", () => {
      const { addSleepMarker, setIsNoSleep } = useSleepScoringStore.getState();

      // Add a MAIN_SLEEP and a NAP marker
      addSleepMarker(1000, 2000);       // MAIN_SLEEP (first)
      addSleepMarker(3000, 4000, "NAP"); // Explicit NAP

      expect(useSleepScoringStore.getState().sleepMarkers).toHaveLength(2);

      setIsNoSleep(true);

      const state = useSleepScoringStore.getState();
      expect(state.isNoSleep).toBe(true);
      // Only the NAP should remain
      expect(state.sleepMarkers).toHaveLength(1);
      expect(state.sleepMarkers[0]!.markerType).toBe(MARKER_TYPES.NAP);
      // Re-indexed to 1
      expect(state.sleepMarkers[0]!.markerIndex).toBe(1);
    });
  });

  describe("markSaved", () => {
    it("should reset isDirty when editGeneration matches", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();
      addSleepMarker(1000, 2000);
      expect(useSleepScoringStore.getState().isDirty).toBe(true);

      const gen = useSleepScoringStore.getState()._editGeneration;
      useSleepScoringStore.getState().markSaved(gen);

      const state = useSleepScoringStore.getState();
      expect(state.isDirty).toBe(false);
      expect(state.isSaving).toBe(false);
      expect(state.lastSavedAt).not.toBeNull();
    });

    it("should keep isDirty=true when editGeneration does not match (edit during save)", () => {
      const { addSleepMarker } = useSleepScoringStore.getState();
      addSleepMarker(1000, 2000);

      const genAtSaveStart = useSleepScoringStore.getState()._editGeneration;

      // Simulate another edit happening while the save was in flight
      addSleepMarker(3000, 4000);

      useSleepScoringStore.getState().markSaved(genAtSaveStart);

      // isDirty should remain true because another edit occurred
      expect(useSleepScoringStore.getState().isDirty).toBe(true);
    });
  });

  describe("registerFlushSave", () => {
    it("should store the flush callback", () => {
      const flushFn = async () => true;
      useSleepScoringStore.getState().registerFlushSave(flushFn);
      expect(useSleepScoringStore.getState()._flushSave).toBe(flushFn);
    });

    it("should allow clearing the callback with null", () => {
      const flushFn = async () => true;
      useSleepScoringStore.getState().registerFlushSave(flushFn);
      useSleepScoringStore.getState().registerFlushSave(null);
      expect(useSleepScoringStore.getState()._flushSave).toBeNull();
    });
  });

  describe("_editGeneration", () => {
    it("should increment on each marker mutation", () => {
      const gen0 = useSleepScoringStore.getState()._editGeneration;

      // Mutation 1: addSleepMarker
      useSleepScoringStore.getState().addSleepMarker(1000, 2000);
      const gen1 = useSleepScoringStore.getState()._editGeneration;
      expect(gen1).toBe(gen0 + 1);

      // Mutation 2: addNonwearMarker
      useSleepScoringStore.getState().addNonwearMarker(3000, 4000);
      const gen2 = useSleepScoringStore.getState()._editGeneration;
      expect(gen2).toBe(gen1 + 1);

      // Mutation 3: deleteMarker
      useSleepScoringStore.getState().deleteMarker("sleep", 0);
      const gen3 = useSleepScoringStore.getState()._editGeneration;
      expect(gen3).toBe(gen2 + 1);

      // Mutation 4: setIsNoSleep
      useSleepScoringStore.getState().setIsNoSleep(true);
      const gen4 = useSleepScoringStore.getState()._editGeneration;
      expect(gen4).toBe(gen3 + 1);
    });
  });
});
