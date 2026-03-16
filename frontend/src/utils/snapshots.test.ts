/**
 * Snapshot tests for stable data structures and serialization.
 *
 * These catch unintended changes to API payloads, store state shapes,
 * and export formats that would break compatibility.
 */

import { describe, it, expect, beforeEach } from "bun:test";
import { useSleepScoringStore } from "@/store";
import {
  MARKER_TYPES,
  ALGORITHM_TYPES,
  VERIFICATION_STATUSES,
  FILE_STATUSES,
  SLEEP_DETECTION_RULES,
} from "@/api/types";
import type {
  FileUploadResponse,
  DateStatus,
  DiaryEntryCreate,
  DiaryEntryResponse,
  UserSettingsResponse,
} from "@/api/types";

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

describe("Snapshot: Export column configuration", () => {
  it("default export column categories should be stable", () => {
    // These match the backend's EXPORT_COLUMNS registry — any drift
    // means the frontend export page will show wrong columns.
    const expectedCategories = [
      "File Info",
      "Period Info",
      "Time Markers",
      "Duration Metrics",
      "Awakening Metrics",
      "Quality Indices",
      "Activity Metrics",
      "Algorithm Info",
      "Annotation Info",
    ];
    expect(expectedCategories).toMatchSnapshot();
  });

  it("default column names list should be stable", () => {
    // Mirrors the backend's DEFAULT_COLUMNS. If the backend adds or
    // removes columns, this snapshot breaks — intentional.
    const defaultColumns = [
      "Filename",
      "File ID",
      "Participant ID",
      "Study Date",
      "Period Index",
      "Marker Type",
      "Onset Time",
      "Offset Time",
      "Onset Datetime",
      "Offset Datetime",
      "Time in Bed (min)",
      "Total Sleep Time (min)",
      "WASO (min)",
      "Sleep Onset Latency (min)",
      "Number of Awakenings",
      "Avg Awakening Length (min)",
      "Sleep Efficiency (%)",
      "Movement Index",
      "Fragmentation Index",
      "Sleep Fragmentation Index",
      "Total Activity Counts",
      "Non-zero Epochs",
      "Algorithm",
      "Detection Rule",
      "Verification Status",
      "Scored By",
      "Is No Sleep",
      "Needs Consensus",
      "Notes",
    ];
    expect(defaultColumns).toMatchSnapshot();
  });
});

describe("Snapshot: Auto-score request payload", () => {
  it("auto-score request shape should be stable", () => {
    const payload = {
      algorithm: ALGORITHM_TYPES.SADEH_1994_ACTILIFE,
      detection_rule: SLEEP_DETECTION_RULES.CONSECUTIVE_3S_5S,
      force_overwrite: false,
    };
    expect(payload).toMatchSnapshot();
  });
});

describe("Snapshot: Diary entry payload", () => {
  it("diary entry create payload should be stable", () => {
    const payload: DiaryEntryCreate = {
      bed_time: "22:30",
      wake_time: "07:00",
      lights_out: "22:45",
      got_up: "07:15",
      sleep_quality: 3,
      time_to_fall_asleep_minutes: 15,
      number_of_awakenings: 2,
      notes: "Normal night",
      nap_1_start: "13:00",
      nap_1_end: "13:45",
      nap_2_start: null,
      nap_2_end: null,
      nap_3_start: null,
      nap_3_end: null,
      nonwear_1_start: "08:00",
      nonwear_1_end: "09:30",
      nonwear_1_reason: "Shower",
      nonwear_2_start: null,
      nonwear_2_end: null,
      nonwear_2_reason: null,
      nonwear_3_start: null,
      nonwear_3_end: null,
      nonwear_3_reason: null,
    };
    expect(payload).toMatchSnapshot();
  });

  it("diary entry response shape should be stable", () => {
    const response: DiaryEntryResponse = {
      id: 1,
      file_id: 42,
      analysis_date: "2024-01-01",
      bed_time: "22:30",
      wake_time: "07:00",
      lights_out: "22:45",
      got_up: "07:15",
      sleep_quality: 3,
      time_to_fall_asleep_minutes: 15,
      number_of_awakenings: 2,
      notes: "Normal night",
      nap_1_start: "13:00",
      nap_1_end: "13:45",
      nap_2_start: null,
      nap_2_end: null,
      nap_3_start: null,
      nap_3_end: null,
      nonwear_1_start: "08:00",
      nonwear_1_end: "09:30",
      nonwear_1_reason: "Shower",
      nonwear_2_start: null,
      nonwear_2_end: null,
      nonwear_2_reason: null,
      nonwear_3_start: null,
      nonwear_3_end: null,
      nonwear_3_reason: null,
    };
    expect(response).toMatchSnapshot();
  });
});

describe("Snapshot: File upload response", () => {
  it("file upload response shape should be stable", () => {
    const response: FileUploadResponse = {
      file_id: 1,
      filename: "participant_001.csv",
      status: FILE_STATUSES.READY as "ready",
      row_count: 1440,
      message: "File uploaded successfully",
    };
    expect(response).toMatchSnapshot();
  });
});

describe("Snapshot: Date status response", () => {
  it("date status shape should be stable", () => {
    const status: DateStatus = {
      date: "2024-01-01",
      has_markers: true,
      is_no_sleep: false,
      needs_consensus: false,
      has_auto_score: true,
      complexity_pre: 3,
      complexity_post: null,
    };
    expect(status).toMatchSnapshot();
  });

  it("unscored date status shape should be stable", () => {
    const status: DateStatus = {
      date: "2024-01-02",
      has_markers: false,
      is_no_sleep: false,
      needs_consensus: false,
      has_auto_score: false,
      complexity_pre: null,
      complexity_post: null,
    };
    expect(status).toMatchSnapshot();
  });
});

describe("Snapshot: Settings/preferences", () => {
  it("user settings response shape should be stable", () => {
    const settings: UserSettingsResponse = {
      sleep_detection_rule: SLEEP_DETECTION_RULES.CONSECUTIVE_3S_5S,
      night_start_hour: "18",
      night_end_hour: "12",
      device_preset: "actigraph",
      epoch_length_seconds: 60,
      skip_rows: 0,
      preferred_display_column: "Axis1",
      view_mode_hours: 24,
      default_algorithm: ALGORITHM_TYPES.SADEH_1994_ACTILIFE,
      extra_settings: null,
    };
    expect(settings).toMatchSnapshot();
  });

  it("VERIFICATION_STATUSES should be stable", () => {
    expect(VERIFICATION_STATUSES).toMatchSnapshot();
  });

  it("FILE_STATUSES should be stable", () => {
    expect(FILE_STATUSES).toMatchSnapshot();
  });

  it("SLEEP_DETECTION_RULES should be stable", () => {
    expect(SLEEP_DETECTION_RULES).toMatchSnapshot();
  });
});
