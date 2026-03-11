import { describe, test, expect, spyOn } from "bun:test";
import { loadActivityForMetrics } from "./local-data-helpers";
import type { ActivityDay } from "@/db";

function makeActivityDay(overrides: Partial<ActivityDay> = {}): ActivityDay {
  const defaultTimestamps = new Float64Array([1000, 2000, 3000]).buffer;
  const defaultAlgoResults = {
    sadeh: new Uint8Array([1, 0, 1]).buffer,
  };
  return {
    id: 1,
    fileId: 1,
    date: "2026-01-15",
    timestamps: defaultTimestamps,
    activityCounts: { axis_y: new Float64Array([10, 20, 30]).buffer },
    algorithmResults: defaultAlgoResults,
    ...overrides,
  } as ActivityDay;
}

describe("loadActivityForMetrics", () => {
  test("returns empty for undefined input", () => {
    const result = loadActivityForMetrics(undefined);
    expect(result.timestamps).toEqual([]);
    expect(result.algorithmResults).toBeNull();
  });

  test("extracts timestamps and first algorithm result", () => {
    const actDay = makeActivityDay();
    const result = loadActivityForMetrics(actDay);
    expect(result.timestamps).toEqual([1000, 2000, 3000]);
    expect(result.algorithmResults).toEqual(new Uint8Array([1, 0, 1]));
  });

  test("returns null algorithmResults for empty results object", () => {
    const actDay = makeActivityDay({ algorithmResults: {} });
    const result = loadActivityForMetrics(actDay);
    expect(result.timestamps).toEqual([1000, 2000, 3000]);
    expect(result.algorithmResults).toBeNull();
  });

  test("warns and returns null for missing algorithmResults", () => {
    const warnSpy = spyOn(console, "warn").mockImplementation(() => {});
    const actDay = makeActivityDay();
    // Force undefined algorithmResults
    (actDay as unknown as Record<string, unknown>).algorithmResults = undefined;

    const result = loadActivityForMetrics(actDay);
    expect(result.algorithmResults).toBeNull();
    expect(result.timestamps).toEqual([1000, 2000, 3000]);
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  test("warns and returns null for non-object algorithmResults", () => {
    const warnSpy = spyOn(console, "warn").mockImplementation(() => {});
    const actDay = makeActivityDay();
    (actDay as unknown as Record<string, unknown>).algorithmResults = "invalid";

    const result = loadActivityForMetrics(actDay);
    expect(result.algorithmResults).toBeNull();
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  test("uses first available algorithm key", () => {
    const actDay = makeActivityDay({
      algorithmResults: {
        cole_kripke: new Uint8Array([0, 0, 1]).buffer,
        sadeh: new Uint8Array([1, 1, 0]).buffer,
      },
    });
    const result = loadActivityForMetrics(actDay);
    // Object.keys returns insertion order — first key should be used
    expect(result.algorithmResults).not.toBeNull();
    expect(result.algorithmResults!.length).toBe(3);
  });
});
