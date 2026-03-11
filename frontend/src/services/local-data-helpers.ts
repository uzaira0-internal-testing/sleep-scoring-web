/**
 * Shared helpers for extracting typed arrays from IndexedDB ActivityDay records.
 */
import type { ActivityDay } from "@/db";
import { isMilliseconds } from "@/utils/timestamps";

/**
 * Extract timestamps and first algorithm results from an ActivityDay record.
 * Returns empty arrays if no data available.
 */
export function loadActivityForMetrics(actDay: ActivityDay | undefined): {
  timestamps: number[];
  algorithmResults: Uint8Array | null;
} {
  if (!actDay) return { timestamps: [], algorithmResults: null };

  // WASM stores timestamps in ms; frontend expects seconds. Single-pass convert.
  const rawF64 = new Float64Array(actDay.timestamps);
  const timestamps = rawF64.length > 0 && isMilliseconds(rawF64[0])
    ? Array.from(rawF64, (t) => t / 1000)
    : Array.from(rawF64);

  if (!actDay.algorithmResults || typeof actDay.algorithmResults !== "object") {
    console.warn(`[loadActivityForMetrics] Missing algorithmResults for activity day id=${actDay.id}`);
    return { timestamps, algorithmResults: null };
  }

  const firstKey = Object.keys(actDay.algorithmResults)[0];
  const algorithmResults = firstKey ? new Uint8Array(actDay.algorithmResults[firstKey]) : null;

  return { timestamps, algorithmResults };
}
