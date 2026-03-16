/**
 * Zod schemas for runtime validation at system boundaries.
 *
 * Enum values are derived from the canonical constants in api/types.ts
 * so they stay in sync with the OpenAPI-generated types.
 */

import { z } from "zod";
import {
  MARKER_TYPES,
  ALGORITHM_TYPES,
  FILE_STATUSES,
  VERIFICATION_STATUSES,
} from "@/api/types";

// =============================================================================
// Enum Schemas (derived from OpenAPI-generated constants — never hardcode here)
// =============================================================================

const vals = <T extends Record<string, string>>(obj: T) =>
  Object.values(obj) as [string, ...string[]];

export const MarkerTypeSchema = z.enum(vals(MARKER_TYPES));
export const AlgorithmTypeSchema = z.enum(vals(ALGORITHM_TYPES));
export const FileStatusSchema = z.enum(vals(FILE_STATUSES));
export const VerificationStatusSchema = z.enum(vals(VERIFICATION_STATUSES));
// =============================================================================
// Form Schemas (user input validation)
// =============================================================================

/** Login form — site password + username */
export const LoginFormSchema = z.object({
  password: z.string(),
  username: z.string().max(100, "Username must be 100 characters or fewer"),
});
export type LoginFormValues = z.infer<typeof LoginFormSchema>;

// =============================================================================
// API Response Schemas (runtime validation for critical data paths)
// =============================================================================

/** Sleep period (onset/offset pair) */
const SleepPeriodSchema = z.object({
  onset_timestamp: z.number().nullable().optional(),
  offset_timestamp: z.number().nullable().optional(),
  marker_index: z.number().int().default(1),
  marker_type: MarkerTypeSchema.default("MAIN_SLEEP"),
});

/** Manual nonwear period */
const ManualNonwearPeriodSchema = z.object({
  start_timestamp: z.number().nullable().optional(),
  end_timestamp: z.number().nullable().optional(),
  marker_index: z.number().int().default(1),
});

/** Markers with metrics response (what loadMarkers returns from server) */
export const MarkersResponseSchema = z.object({
  sleep_markers: z.array(SleepPeriodSchema).optional().default([]),
  nonwear_markers: z.array(ManualNonwearPeriodSchema).optional().default([]),
  is_no_sleep: z.boolean().optional().default(false),
  needs_consensus: z.boolean().optional().default(false),
  notes: z.string().nullable().optional(),
});

/** Activity data columnar response */
export const ActivityDataResponseSchema = z.object({
  data: z
    .object({
      timestamps: z.array(z.number()).optional().default([]),
      axis_x: z.array(z.number()).optional().default([]),
      axis_y: z.array(z.number()).optional().default([]),
      axis_z: z.array(z.number()).optional().default([]),
      vector_magnitude: z.array(z.number()).optional().default([]),
    })
    .optional(),
  // Top-level fields (may also appear at root instead of nested in `data`)
  timestamps: z.array(z.number()).optional(),
  axis_x: z.array(z.number()).optional(),
  axis_y: z.array(z.number()).optional(),
  axis_z: z.array(z.number()).optional(),
  vector_magnitude: z.array(z.number()).optional(),
  algorithm_results: z.array(z.number()).nullable().optional(),
  nonwear_results: z.array(z.number()).nullable().optional(),
  view_start: z.number().nullable().optional(),
  view_end: z.number().nullable().optional(),
  sensor_nonwear_periods: z
    .array(
      z.object({
        start_timestamp: z.number(),
        end_timestamp: z.number(),
      }),
    )
    .optional()
    .default([]),
});
