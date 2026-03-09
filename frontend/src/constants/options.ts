/**
 * Shared UI options and constants
 * Single source of truth to avoid duplication across pages.
 */
import { ALGORITHM_TYPES, SLEEP_DETECTION_RULES, MARKER_TYPES } from "@/api/types";

/**
 * Marker limits (matches backend MarkerLimits in schemas/enums.py)
 */
export const MARKER_LIMITS = {
  MAX_SLEEP_PERIODS_PER_DAY: 4,
  MAX_NONWEAR_PERIODS_PER_DAY: 10,
  EPOCH_DURATION_SECONDS: 60,
} as const;

/**
 * Activity data source options
 */
export const ACTIVITY_SOURCE_OPTIONS = [
  { value: "axis_y", label: "Y-Axis (Vertical)" },
  { value: "axis_x", label: "X-Axis (Lateral)" },
  { value: "axis_z", label: "Z-Axis (Forward)" },
  { value: "vector_magnitude", label: "Vector Magnitude" },
] as const;

/**
 * Algorithm options for sleep scoring
 */
export const ALGORITHM_OPTIONS = [
  { value: ALGORITHM_TYPES.SADEH_1994_ACTILIFE, label: "Sadeh (1994) ActiLife - Recommended" },
  { value: ALGORITHM_TYPES.SADEH_1994_ORIGINAL, label: "Sadeh (1994) Original" },
  { value: ALGORITHM_TYPES.COLE_KRIPKE_1992_ACTILIFE, label: "Cole-Kripke (1992) ActiLife" },
  { value: ALGORITHM_TYPES.COLE_KRIPKE_1992_ORIGINAL, label: "Cole-Kripke (1992) Original" },
] as const;

/**
 * Sleep detection rule parameters.
 *
 * Matches desktop ConsecutiveEpochsSleepPeriodDetectorConfig.
 *
 * - offsetState "sleep": offset = end of the latest run of N consecutive
 *   SLEEP epochs within the marker range (3S/5S and 5S/10S rules).
 *
 * - offsetState "wake": offset = the latest SLEEP epoch within the marker
 *   range that is immediately followed by N consecutive WAKE epochs.
 *   The wake validation may extend beyond the marker boundary.
 *   (Tudor-Locke 2014 — detects when the person wakes up for good.)
 */
export interface DetectionRuleParams {
  onsetN: number;
  offsetN: number;
  /** What epoch state the offset detector scans for */
  offsetState: "sleep" | "wake";
  label: string;
}

export const DETECTION_RULE_PARAMS: Record<string, DetectionRuleParams> = {
  [SLEEP_DETECTION_RULES.CONSECUTIVE_3S_5S]: { onsetN: 3, offsetN: 5, offsetState: "sleep", label: "3-min Onset / 5-min Offset (Default)" },
  [SLEEP_DETECTION_RULES.CONSECUTIVE_5S_10S]: { onsetN: 5, offsetN: 10, offsetState: "sleep", label: "5-min Onset / 10-min Offset" },
  [SLEEP_DETECTION_RULES.TUDOR_LOCKE_2014]: { onsetN: 5, offsetN: 10, offsetState: "wake", label: "Tudor-Locke (2014)" },
};

const DEFAULT_RULE_PARAMS: DetectionRuleParams = { onsetN: 3, offsetN: 5, offsetState: "sleep", label: "3S/5S" };

/** Look up onset/offset thresholds for a given rule string */
export function getDetectionRuleParams(rule: string): DetectionRuleParams {
  return DETECTION_RULE_PARAMS[rule] ?? DEFAULT_RULE_PARAMS;
}

/**
 * Sleep detection rule options (for dropdowns)
 */
export const SLEEP_DETECTION_OPTIONS = Object.entries(DETECTION_RULE_PARAMS).map(
  ([value, { label }]) => ({ value, label })
);

/**
 * Marker type options for sleep periods
 */
export const MARKER_TYPE_OPTIONS = [
  { value: MARKER_TYPES.MAIN_SLEEP, label: "Main Sleep" },
  { value: MARKER_TYPES.NAP, label: "Nap" },
] as const;

/**
 * View mode options (hours)
 */
export const VIEW_MODE_OPTIONS = [
  { value: "24", label: "24h" },
  { value: "48", label: "48h" },
] as const;
