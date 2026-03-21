/**
 * Convenient type re-exports from generated OpenAPI schema.
 *
 * Import from here instead of directly from schema.ts for cleaner imports.
 * All types are auto-generated from backend Pydantic models.
 *
 * To regenerate: bun run generate:types
 */

import type { components, paths } from "./schema";

// =============================================================================
// Schema Types (from Pydantic models)
// =============================================================================

/** Sleep period with onset/offset timestamps */
export type SleepPeriod = components["schemas"]["SleepPeriod"];

/** Manual nonwear period with start/end timestamps */
export type ManualNonwearPeriod = components["schemas"]["ManualNonwearPeriod"];

/** Request to update markers for a file/date */
export type MarkerUpdateRequest = components["schemas"]["MarkerUpdateRequest"];

/** Response with markers and their calculated metrics */
export type MarkersWithMetricsResponse = components["schemas"]["MarkersWithMetricsResponse"];

/** Response after saving markers */
export type SaveStatusResponse = components["schemas"]["SaveStatusResponse"];

/** Complete sleep metrics for a single sleep period */
export type SleepMetrics = components["schemas"]["SleepMetrics"];

/** Activity data in columnar format */
export type ActivityDataColumnar = components["schemas"]["ActivityDataColumnar"];

/** Response for activity data endpoint */
export type ActivityDataResponse = components["schemas"]["ActivityDataResponse"];

/** File metadata */
export type FileInfo = components["schemas"]["FileInfo"];

/** File list response (not in generated schema — defined manually) */
export interface FileListResponse {
  items: FileInfo[];
  total: number;
}

/** File upload response */
export type FileUploadResponse = components["schemas"]["FileUploadResponse"];

/** User info (not in generated schema — defined manually) */
export interface UserRead {
  username: string;
  is_admin: boolean;
}

/** User settings response */
export type UserSettingsResponse = components["schemas"]["UserSettingsResponse"];

/** User settings update request */
export type UserSettingsUpdate = components["schemas"]["UserSettingsUpdate"];

/** Diary entry response */
export type DiaryEntryResponse = components["schemas"]["DiaryEntryResponse"];

/** Diary entry create request */
export type DiaryEntryCreate = components["schemas"]["DiaryEntryCreate"];

/** Diary upload response */
export type DiaryUploadResponse = components["schemas"]["DiaryUploadResponse"];

/** JWT token response (not in generated schema — defined manually) */
export interface Token {
  access_token: string;
  token_type: string;
}

/** Data point for onset/offset tables */
export type OnsetOffsetDataPoint = components["schemas"]["OnsetOffsetDataPoint"];

/** Response with data points around a marker */
export type OnsetOffsetTableResponse = components["schemas"]["OnsetOffsetTableResponse"];

/** Data point for full table view */
export type FullTableDataPoint = components["schemas"]["FullTableDataPoint"];

/** Response with full table data */
export type FullTableResponse = components["schemas"]["FullTableResponse"];

/** Columnar data for onset/offset tables (smaller payload) */
export interface OnsetOffsetColumnar {
  timestamps: number[];
  axis_y: number[];
  vector_magnitude: number[];
  algorithm_result: (number | null)[];
  choi_result: (number | null)[];
  is_nonwear: boolean[];
}

/** Columnar response for onset/offset tables */
export interface OnsetOffsetColumnarResponse {
  onset_data: OnsetOffsetColumnar;
  offset_data: OnsetOffsetColumnar;
  period_index: number;
}

/** Columnar full table data (smaller payload) */
export interface FullTableColumnar {
  timestamps: number[];
  axis_y: number[];
  vector_magnitude: number[];
  algorithm_result: (number | null)[];
  choi_result: (number | null)[];
  is_nonwear: boolean[];
  total_rows: number;
  start_time: string | null;
  end_time: string | null;
}

/** Date annotation status with complexity scores (from /files/{id}/dates/status) */
export type DateStatus = components["schemas"]["DateStatus"];

/** File assignment (admin feature) */
export interface FileAssignment {
  id: number;
  file_id: number;
  filename: string;
  username: string;
  assigned_by: string;
  assigned_at: string | null;
}

/** Per-file progress for a user's assignment */
export interface UserFileProgress {
  file_id: number;
  filename: string;
  total_dates: number;
  scored_dates: number;
  assigned_at: string | null;
}

/** User assignment progress (admin feature) */
export interface AssignmentProgress {
  username: string;
  files: UserFileProgress[];
  total_files: number;
  total_dates: number;
  scored_dates: number;
}

/** Auth me response */
export interface AuthMeResponse {
  username: string;
  is_admin: boolean;
}

/** Consensus ballot sleep marker payload */
export interface ConsensusBallotSleepMarker {
  onset_timestamp: number | null;
  offset_timestamp: number | null;
  marker_type: string | null;
  marker_index: number | null;
}

/** Consensus ballot nonwear marker payload */
export interface ConsensusBallotNonwearMarker {
  start_timestamp: number | null;
  end_timestamp: number | null;
  marker_index: number | null;
}

/** One consensus candidate with aggregate vote state */
export interface ConsensusBallotCandidate {
  candidate_id: number;
  label: string;
  source_type: "auto" | "user";
  sleep_markers_json: ConsensusBallotSleepMarker[] | null;
  nonwear_markers_json: ConsensusBallotNonwearMarker[] | null;
  is_no_sleep: boolean;
  vote_count: number;
  selected_by_me: boolean;
  created_at: string | null;
}

/** Ballot response for a file/date */
export interface ConsensusBallotResponse {
  file_id: number;
  analysis_date: string;
  candidates: ConsensusBallotCandidate[];
  total_votes: number;
  leading_candidate_id: number | null;
  my_vote_candidate_id: number | null;
  updated_at: string | null;
}

// =============================================================================
// Enums (from Pydantic StrEnums)
// =============================================================================

/** Sleep marker type: MAIN_SLEEP or NAP */
export type MarkerType = components["schemas"]["MarkerType"];

/** Marker category: sleep or nonwear */
export type MarkerCategory = components["schemas"]["MarkerCategory"];

/** Sleep scoring algorithm type */
export type AlgorithmType = components["schemas"]["AlgorithmType"];

/** File processing status */
export type FileStatus = components["schemas"]["FileStatus"];

/** Verification status for annotations */
export type VerificationStatus = components["schemas"]["VerificationStatus"];

/** Nonwear data source type (not in OpenAPI schema — defined manually) */
export type NonwearDataSource = "choi_algorithm" | "manual";

// =============================================================================
// API Path Types (for type-safe fetch)
// =============================================================================

export type { paths, components };

// =============================================================================
// Enum Constants (for comparisons and defaults)
// =============================================================================

export const MARKER_TYPES = {
  MAIN_SLEEP: "MAIN_SLEEP" as const,
  NAP: "NAP" as const,
} satisfies Record<string, MarkerType>;

export const MARKER_CATEGORIES = {
  SLEEP: "sleep" as const,
  NONWEAR: "nonwear" as const,
} satisfies Record<string, MarkerCategory>;

export const VERIFICATION_STATUSES = {
  DRAFT: "draft" as const,
  SUBMITTED: "submitted" as const,
  VERIFIED: "verified" as const,
  DISPUTED: "disputed" as const,
  RESOLVED: "resolved" as const,
} satisfies Record<string, VerificationStatus>;

export const FILE_STATUSES = {
  PENDING: "pending" as const,
  UPLOADING: "uploading" as const,
  PROCESSING: "processing" as const,
  READY: "ready" as const,
  FAILED: "failed" as const,
};

export const ALGORITHM_TYPES = {
  SADEH_1994_ORIGINAL: "sadeh_1994_original" as const,
  SADEH_1994_ACTILIFE: "sadeh_1994_actilife" as const,
  COLE_KRIPKE_1992_ORIGINAL: "cole_kripke_1992_original" as const,
  COLE_KRIPKE_1992_ACTILIFE: "cole_kripke_1992_actilife" as const,
  MANUAL: "manual" as const,
} satisfies Record<string, AlgorithmType>;

export const SLEEP_DETECTION_RULES = {
  CONSECUTIVE_3S_5S: "consecutive_onset3s_offset5s" as const,
  CONSECUTIVE_5S_10S: "consecutive_onset5s_offset10s" as const,
  TUDOR_LOCKE_2014: "tudor_locke_2014" as const,
} as const;

/** Period guider types — mirrors backend PeriodGuiderType StrEnum */
export type PeriodGuiderType = "diary" | "l5" | "smart" | "longest_bout" | "none";

export const PERIOD_GUIDERS = {
  DIARY: "diary" as const,
  L5: "l5" as const,
  SMART: "smart" as const,
  LONGEST_BOUT: "longest_bout" as const,
  NONE: "none" as const,
} satisfies Record<string, PeriodGuiderType>;

/** Options for the period guider select dropdown */
export const PERIOD_GUIDER_OPTIONS: { value: PeriodGuiderType; label: string }[] = [
  { value: PERIOD_GUIDERS.DIARY, label: "Diary" },
  { value: PERIOD_GUIDERS.L5, label: "L5 (5h)" },
  { value: PERIOD_GUIDERS.LONGEST_BOUT, label: "Longest Bout" },
  { value: PERIOD_GUIDERS.SMART, label: "Smart" },
];

// =============================================================================
// Pipeline Discovery (from /pipeline/discover)
// =============================================================================

/** JSON Schema for a single parameter field */
export interface ParamSchemaProperty {
  type?: string;
  default?: unknown;
  description?: string;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
}

/** JSON Schema for a component's parameter set */
export interface ParamSchema {
  type: string;
  title?: string;
  description?: string;
  properties?: Record<string, ParamSchemaProperty>;
  required?: string[];
}

/** Response from the pipeline discovery endpoint */
export interface PipelineDiscoveryResponse {
  roles: Record<string, string[]>;
  param_schemas?: Record<string, ParamSchema>;
}
