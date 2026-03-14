/**
 * Tests for useMarkerAutoSave hook — store-level behavior.
 *
 * Since useMarkerAutoSave is a React hook that depends on useEffect, useMutation,
 * and react-query, we test the underlying store interactions it relies on:
 *
 * 1. isDirty flag management (set on edits, cleared by markSaved)
 * 2. _editGeneration tracking (monotonic counter for concurrent-edit detection)
 * 3. markSaved with edit-generation gating (stale save doesn't clear dirty)
 * 4. buildMarkerData-equivalent state shape
 * 5. Flush callback registration/deregistration
 * 6. setSaving / setSaveError state management
 *
 * Uses Bun's built-in test runner.
 */

import { describe, it, expect, beforeEach } from "bun:test";
import { useSleepScoringStore } from "../store/index";
import { MARKER_TYPES } from "../api/types";

/** Reset store to a clean baseline before each test. */
function resetStore() {
  useSleepScoringStore.setState({
    sitePassword: null,
    username: "anonymous",
    isAuthenticated: false,
    currentFileId: null,
    currentFilename: null,
    currentFileSource: "server",
    currentDateIndex: 0,
    availableDates: ["2024-01-01", "2024-01-02"],
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
    isSaving: false,
    lastSavedAt: null,
    saveError: null,
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
    _flushSave: null,
  });
}

describe("useMarkerAutoSave — store interactions", () => {
  beforeEach(resetStore);

  // ─── isDirty flag management ─────────────────────────────────────────

  describe("isDirty flag", () => {
    it("should be false initially", () => {
      expect(useSleepScoringStore.getState().isDirty).toBe(false);
    });

    it("should become true when sleep markers are set", () => {
      const { setSleepMarkers } = useSleepScoringStore.getState();
      setSleepMarkers([
        { onsetTimestamp: 1000, offsetTimestamp: 2000, markerIndex: 0, markerType: MARKER_TYPES.MAIN_SLEEP },
      ]);

      expect(useSleepScoringStore.getState().isDirty).toBe(true);
    });

    it("should become true when nonwear markers are set", () => {
      const { setNonwearMarkers } = useSleepScoringStore.getState();
      setNonwearMarkers([
        { startTimestamp: 1000, endTimestamp: 2000, markerIndex: 0 },
      ]);

      expect(useSleepScoringStore.getState().isDirty).toBe(true);
    });

    it("should become true when isNoSleep is toggled", () => {
      const { setIsNoSleep } = useSleepScoringStore.getState();
      setIsNoSleep(true);

      expect(useSleepScoringStore.getState().isDirty).toBe(true);
    });

    it("should become true when needsConsensus is set", () => {
      const { setNeedsConsensus } = useSleepScoringStore.getState();
      setNeedsConsensus(true);

      expect(useSleepScoringStore.getState().isDirty).toBe(true);
    });

    it("should become true when notes are set", () => {
      const { setNotes } = useSleepScoringStore.getState();
      setNotes("observation about sleep quality");

      expect(useSleepScoringStore.getState().isDirty).toBe(true);
    });
  });

  // ─── _editGeneration tracking ────────────────────────────────────────

  describe("_editGeneration counter", () => {
    it("should start at 0", () => {
      expect(useSleepScoringStore.getState()._editGeneration).toBe(0);
    });

    it("should increment on each sleep marker mutation", () => {
      const { setSleepMarkers } = useSleepScoringStore.getState();

      setSleepMarkers([
        { onsetTimestamp: 1000, offsetTimestamp: 2000, markerIndex: 0, markerType: MARKER_TYPES.MAIN_SLEEP },
      ]);
      expect(useSleepScoringStore.getState()._editGeneration).toBe(1);

      useSleepScoringStore.getState().setSleepMarkers([
        { onsetTimestamp: 1000, offsetTimestamp: 2500, markerIndex: 0, markerType: MARKER_TYPES.MAIN_SLEEP },
      ]);
      expect(useSleepScoringStore.getState()._editGeneration).toBe(2);
    });

    it("should increment on nonwear marker mutation", () => {
      const { setNonwearMarkers } = useSleepScoringStore.getState();

      setNonwearMarkers([
        { startTimestamp: 500, endTimestamp: 1500, markerIndex: 0 },
      ]);
      expect(useSleepScoringStore.getState()._editGeneration).toBe(1);
    });

    it("should increment on isNoSleep, needsConsensus, and notes changes", () => {
      const { setIsNoSleep, setNeedsConsensus, setNotes } = useSleepScoringStore.getState();

      setIsNoSleep(true);
      expect(useSleepScoringStore.getState()._editGeneration).toBe(1);

      useSleepScoringStore.getState().setNeedsConsensus(true);
      expect(useSleepScoringStore.getState()._editGeneration).toBe(2);

      useSleepScoringStore.getState().setNotes("test note");
      expect(useSleepScoringStore.getState()._editGeneration).toBe(3);
    });

    it("should NOT increment when server-load variants set markers", () => {
      const { _loadSleepMarkersFromServer, _loadNonwearMarkersFromServer } = useSleepScoringStore.getState();

      _loadSleepMarkersFromServer([
        { onsetTimestamp: 1000, offsetTimestamp: 2000, markerIndex: 0, markerType: MARKER_TYPES.MAIN_SLEEP },
      ]);
      expect(useSleepScoringStore.getState()._editGeneration).toBe(0);

      _loadNonwearMarkersFromServer([
        { startTimestamp: 500, endTimestamp: 1500, markerIndex: 0 },
      ]);
      expect(useSleepScoringStore.getState()._editGeneration).toBe(0);
    });
  });

  // ─── markSaved with edit-generation gating ───────────────────────────

  describe("markSaved", () => {
    it("should clear isDirty when editGeneration matches", () => {
      const { setSleepMarkers } = useSleepScoringStore.getState();

      // Make a single edit — generation goes to 1
      setSleepMarkers([
        { onsetTimestamp: 1000, offsetTimestamp: 2000, markerIndex: 0, markerType: MARKER_TYPES.MAIN_SLEEP },
      ]);
      expect(useSleepScoringStore.getState().isDirty).toBe(true);
      expect(useSleepScoringStore.getState()._editGeneration).toBe(1);

      // Simulate save completing with matching generation
      useSleepScoringStore.getState().markSaved(1);

      const state = useSleepScoringStore.getState();
      expect(state.isDirty).toBe(false);
      expect(state.isSaving).toBe(false);
      expect(state.lastSavedAt).not.toBeNull();
    });

    it("should keep isDirty=true when editGeneration does NOT match (concurrent edit)", () => {
      const { setSleepMarkers } = useSleepScoringStore.getState();

      // First edit — generation = 1
      setSleepMarkers([
        { onsetTimestamp: 1000, offsetTimestamp: 2000, markerIndex: 0, markerType: MARKER_TYPES.MAIN_SLEEP },
      ]);

      // Simulate: save started at generation 1, but user edited again (generation = 2)
      useSleepScoringStore.getState().setSleepMarkers([
        { onsetTimestamp: 1000, offsetTimestamp: 2500, markerIndex: 0, markerType: MARKER_TYPES.MAIN_SLEEP },
      ]);
      expect(useSleepScoringStore.getState()._editGeneration).toBe(2);

      // Save completes with stale generation 1 — should NOT clear dirty
      useSleepScoringStore.getState().markSaved(1);

      expect(useSleepScoringStore.getState().isDirty).toBe(true);
    });

    it("should clear isDirty when called without editGeneration (legacy path)", () => {
      const { setSleepMarkers } = useSleepScoringStore.getState();

      setSleepMarkers([
        { onsetTimestamp: 1000, offsetTimestamp: 2000, markerIndex: 0, markerType: MARKER_TYPES.MAIN_SLEEP },
      ]);
      expect(useSleepScoringStore.getState().isDirty).toBe(true);

      // markSaved() with no argument — always clears
      useSleepScoringStore.getState().markSaved();

      expect(useSleepScoringStore.getState().isDirty).toBe(false);
    });

    it("should set lastSavedAt to a recent timestamp", () => {
      const before = Date.now();
      useSleepScoringStore.getState().markSaved();
      const after = Date.now();

      const lastSaved = useSleepScoringStore.getState().lastSavedAt;
      expect(lastSaved).not.toBeNull();
      expect(lastSaved!).toBeGreaterThanOrEqual(before);
      expect(lastSaved!).toBeLessThanOrEqual(after);
    });
  });

  // ─── Store state shape for buildMarkerData ───────────────────────────

  describe("store state shape (buildMarkerData contract)", () => {
    it("should expose all fields that buildMarkerData reads", () => {
      // Set up state with representative data
      const { setSleepMarkers, setNonwearMarkers, setIsNoSleep, setNeedsConsensus, setNotes } =
        useSleepScoringStore.getState();

      setSleepMarkers([
        { onsetTimestamp: 100, offsetTimestamp: 200, markerIndex: 0, markerType: MARKER_TYPES.MAIN_SLEEP },
        { onsetTimestamp: 300, offsetTimestamp: 400, markerIndex: 1, markerType: MARKER_TYPES.NAP },
      ]);
      useSleepScoringStore.getState().setNonwearMarkers([
        { startTimestamp: 500, endTimestamp: 600, markerIndex: 0 },
      ]);
      useSleepScoringStore.getState().setIsNoSleep(false);
      useSleepScoringStore.getState().setNeedsConsensus(true);
      useSleepScoringStore.getState().setNotes("test note");

      const state = useSleepScoringStore.getState();

      // Reconstruct what buildMarkerData() would produce
      const markerData = {
        sleepMarkers: state.sleepMarkers.map((m) => ({
          onsetTimestamp: m.onsetTimestamp,
          offsetTimestamp: m.offsetTimestamp,
          markerIndex: m.markerIndex,
          markerType: m.markerType,
        })),
        nonwearMarkers: state.nonwearMarkers.map((m) => ({
          startTimestamp: m.startTimestamp,
          endTimestamp: m.endTimestamp,
          markerIndex: m.markerIndex,
        })),
        isNoSleep: state.isNoSleep,
        notes: state.notes || "",
        needsConsensus: state.needsConsensus,
      };

      // Verify shape matches MarkerData interface
      expect(markerData.sleepMarkers).toHaveLength(2);
      expect(markerData.sleepMarkers[0]).toEqual({
        onsetTimestamp: 100,
        offsetTimestamp: 200,
        markerIndex: 0,
        markerType: "MAIN_SLEEP",
      });
      expect(markerData.sleepMarkers[1]).toEqual({
        onsetTimestamp: 300,
        offsetTimestamp: 400,
        markerIndex: 1,
        markerType: "NAP",
      });
      expect(markerData.nonwearMarkers).toHaveLength(1);
      expect(markerData.nonwearMarkers[0]).toEqual({
        startTimestamp: 500,
        endTimestamp: 600,
        markerIndex: 0,
      });
      expect(markerData.isNoSleep).toBe(false);
      expect(markerData.notes).toBe("test note");
      expect(markerData.needsConsensus).toBe(true);
    });

    it("should default notes to empty string when undefined", () => {
      // notes defaults to "" in the store, but verify the || "" fallback
      const state = useSleepScoringStore.getState();
      const notes = state.notes || "";
      expect(notes).toBe("");
    });
  });

  // ─── Flush callback registration ────────────────────────────────────

  describe("flush callback registration", () => {
    it("should start with _flushSave as null", () => {
      expect(useSleepScoringStore.getState()._flushSave).toBeNull();
    });

    it("should register a flush callback", () => {
      const flush = async (): Promise<boolean> => true;
      useSleepScoringStore.getState().registerFlushSave(flush);

      expect(useSleepScoringStore.getState()._flushSave).toBe(flush);
    });

    it("should deregister flush callback by setting null", () => {
      const flush = async (): Promise<boolean> => true;
      useSleepScoringStore.getState().registerFlushSave(flush);
      expect(useSleepScoringStore.getState()._flushSave).not.toBeNull();

      useSleepScoringStore.getState().registerFlushSave(null);
      expect(useSleepScoringStore.getState()._flushSave).toBeNull();
    });

    it("should only deregister if current callback matches (cleanup guard)", () => {
      // This mirrors the useEffect cleanup logic in useMarkerAutoSave:
      //   const current = useSleepScoringStore.getState()._flushSave;
      //   if (current === flush) { registerFlushSave(null); }
      const flush1 = async (): Promise<boolean> => true;
      const flush2 = async (): Promise<boolean> => false;

      // Register flush1
      useSleepScoringStore.getState().registerFlushSave(flush1);

      // A new hook instance registers flush2 (e.g., after re-render)
      useSleepScoringStore.getState().registerFlushSave(flush2);

      // Old cleanup fires for flush1 — should NOT deregister since current is flush2
      const current = useSleepScoringStore.getState()._flushSave;
      if (current === flush1) {
        useSleepScoringStore.getState().registerFlushSave(null);
      }

      // flush2 should still be registered
      expect(useSleepScoringStore.getState()._flushSave).toBe(flush2);
    });
  });

  // ─── setSaving / setSaveError ────────────────────────────────────────

  describe("save status management", () => {
    it("should set and clear saving state", () => {
      const { setSaving } = useSleepScoringStore.getState();

      setSaving(true);
      expect(useSleepScoringStore.getState().isSaving).toBe(true);

      setSaving(false);
      expect(useSleepScoringStore.getState().isSaving).toBe(false);
    });

    it("should set and clear save error", () => {
      const { setSaveError } = useSleepScoringStore.getState();

      setSaveError("Network error: connection refused");
      expect(useSleepScoringStore.getState().saveError).toBe("Network error: connection refused");

      setSaveError(null);
      expect(useSleepScoringStore.getState().saveError).toBeNull();
    });

    it("should clear isSaving when markSaved is called", () => {
      const { setSaving, markSaved } = useSleepScoringStore.getState();

      setSaving(true);
      expect(useSleepScoringStore.getState().isSaving).toBe(true);

      markSaved();
      expect(useSleepScoringStore.getState().isSaving).toBe(false);
    });
  });
});
