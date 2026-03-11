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

  const rawTs = Array.from(new Float64Array(actDay.timestamps));
  // Convert ms→seconds if needed (WASM stores ms, frontend expects seconds)
  const timestamps = rawTs.length > 0 && rawTs[0] > 1e12 ? rawTs.map((t) => t / 1000) : rawTs;

  if (!actDay.algorithmResults || typeof actDay.algorithmResults !== "object") {
    console.warn(`[loadActivityForMetrics] Missing algorithmResults for activity day id=${actDay.id}`);
    return { timestamps, algorithmResults: null };
  }

  const firstKey = Object.keys(actDay.algorithmResults)[0];
  const algorithmResults = firstKey ? new Uint8Array(actDay.algorithmResults[firstKey]) : null;

  return { timestamps, algorithmResults };
}
