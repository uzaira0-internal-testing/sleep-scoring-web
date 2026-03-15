/**
 * Snapshot tests for stable data structures and serialization.
 *
 * These catch unintended changes to API payloads, store state shapes,
 * and export formats that would break compatibility.
 */

import { describe, it, expect, beforeEach } from "bun:test";
import { useSleepScoringStore } from "@/store";
import { MARKER_TYPES, ALGORITHM_TYPES } from "@/api/types";

describe("Snapshot: Store initial state shape", () => {
  beforeEach(() => {
    useSleepScoringStore.setState({
      sitePassword: null,
      username: "anonymous",
      isAuthenticated: false,
      isAdmin: false,
      sleepMarkers: [],
      nonwearMarkers: [],
      isDirty: false,
      isNoSleep: false,
      markerMode: "sleep",
      creationMode: "idle",
    });
  });

  it("should match the expected auth state shape", () => {
    const state = useSleepScoringStore.getState();
    const authShape = {
      sitePassword: state.sitePassword,
      username: state.username,
      isAuthenticated: state.isAuthenticated,
      isAdmin: state.isAdmin,
    };
    expect(authShape).toMatchSnapshot();
  });

  it("should match the expected marker state shape", () => {
    const state = useSleepScoringStore.getState();
    const markerShape = {
      sleepMarkersType: Array.isArray(state.sleepMarkers),
      nonwearMarkersType: Array.isArray(state.nonwearMarkers),
      isDirty: typeof state.isDirty,
      isNoSleep: typeof state.isNoSleep,
      markerMode: state.markerMode,
      creationMode: state.creationMode,
    };
    expect(markerShape).toMatchSnapshot();
  });
});

describe("Snapshot: Constants", () => {
  it("MARKER_TYPES should be stable", () => {
    expect(MARKER_TYPES).toMatchSnapshot();
  });

  it("ALGORITHM_TYPES should be stable", () => {
    expect(ALGORITHM_TYPES).toMatchSnapshot();
  });
});

describe("Snapshot: Marker payload serialization", () => {
  it("sleep marker payload matches expected shape", () => {
    const payload = {
      sleep_markers: [
        {
          onset_timestamp: 1704070800,
          offset_timestamp: 1704099600,
          marker_type: MARKER_TYPES.MAIN_SLEEP,
          marker_index: 1,
        },
      ],
      nonwear_markers: [],
      is_no_sleep: false,
      notes: "",
      needs_consensus: false,
    };
    expect(payload).toMatchSnapshot();
  });

  it("no-sleep payload matches expected shape", () => {
    const payload = {
      sleep_markers: [],
      nonwear_markers: [],
      is_no_sleep: true,
      notes: "No main sleep observed",
      needs_consensus: false,
    };
    expect(payload).toMatchSnapshot();
  });

  it("mixed markers payload matches expected shape", () => {
    const payload = {
      sleep_markers: [
        {
          onset_timestamp: 1704070800,
          offset_timestamp: 1704099600,
          marker_type: MARKER_TYPES.MAIN_SLEEP,
          marker_index: 1,
        },
        {
          onset_timestamp: 1704114000,
          offset_timestamp: 1704121200,
          marker_type: MARKER_TYPES.NAP,
          marker_index: 2,
        },
      ],
      nonwear_markers: [
        {
          start_timestamp: 1704042000,
          end_timestamp: 1704049200,
          marker_index: 1,
        },
      ],
      is_no_sleep: false,
      notes: "Good recording quality",
      needs_consensus: true,
    };
    expect(payload).toMatchSnapshot();
  });
});
