/**
 * Shared helpers for extracting typed arrays from IndexedDB ActivityDay records.
 */
import type { ActivityDay } from "@/db";

/**
 * Extract timestamps and first algorithm results from an ActivityDay record.
 * Returns empty arrays if no data available.
 */
export function loadActivityForMetrics(actDay: ActivityDay | undefined): {
  timestamps: number[];
  algorithmResults: Uint8Array | null;
} {
  if (!actDay) return { timestamps: [], algorithmResults: null };

  // IndexedDB stores timestamps in seconds (converted from WASM ms at storage time).
  const timestamps = Array.from(new Float64Array(actDay.timestamps));

  if (!actDay.algorithmResults || typeof actDay.algorithmResults !== "object") {
    console.warn(`[loadActivityForMetrics] Missing algorithmResults for activity day id=${actDay.id}`);
    return { timestamps, algorithmResults: null };
  }

  const firstKey = Object.keys(actDay.algorithmResults)[0];
  const algorithmResults = firstKey ? new Uint8Array(actDay.algorithmResults[firstKey]!) : null;

  return { timestamps, algorithmResults };
}
