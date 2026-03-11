import { describe, it, expect } from "bun:test";

import { resolveEditedTimeToTimestamp } from "./time-edit";

/** Helper: Date.UTC returns ms, divide by 1000 for seconds. */
const utcSec = (...args: Parameters<typeof Date.UTC>) => Date.UTC(...args) / 1000;

describe("resolveEditedTimeToTimestamp", () => {
  it("maps early-morning onset to current scoring day in 48h context", () => {
    // User is scoring 2025-04-05 and enters 01:13 onset, 10:34 offset.
    // Existing onset may still be on previous day from earlier edits.
    const offsetTs = utcSec(2025, 3, 5, 10, 34, 0, 0);
    const staleOnsetReferenceTs = utcSec(2025, 3, 4, 23, 30, 0, 0);

    const resolved = resolveEditedTimeToTimestamp({
      timeStr: "01:13",
      currentDate: "2025-04-05",
      referenceTimestamp: staleOnsetReferenceTs,
      otherBoundaryTimestamp: offsetTs,
      field: "onset",
    });

    expect(resolved).toBe(utcSec(2025, 3, 5, 1, 13, 0, 0));
  });

  it("maps late-evening onset to previous day when offset is next morning", () => {
    const offsetTs = utcSec(2025, 3, 5, 7, 0, 0, 0);
    const onsetReferenceTs = utcSec(2025, 3, 5, 0, 30, 0, 0);

    const resolved = resolveEditedTimeToTimestamp({
      timeStr: "23:45",
      currentDate: "2025-04-05",
      referenceTimestamp: onsetReferenceTs,
      otherBoundaryTimestamp: offsetTs,
      field: "onset",
    });

    expect(resolved).toBe(utcSec(2025, 3, 4, 23, 45, 0, 0));
  });

  it("maps offset to the earliest valid time after onset", () => {
    const onsetTs = utcSec(2025, 3, 4, 23, 15, 0, 0);
    const offsetReferenceTs = utcSec(2025, 3, 4, 6, 0, 0, 0);

    const resolved = resolveEditedTimeToTimestamp({
      timeStr: "10:34",
      currentDate: "2025-04-05",
      referenceTimestamp: offsetReferenceTs,
      otherBoundaryTimestamp: onsetTs,
      field: "offset",
    });

    expect(resolved).toBe(utcSec(2025, 3, 5, 10, 34, 0, 0));
  });

  it("returns null for invalid time strings", () => {
    const resolved = resolveEditedTimeToTimestamp({
      timeStr: "25:99",
      currentDate: "2025-04-05",
      referenceTimestamp: utcSec(2025, 3, 5, 1, 0, 0, 0),
      otherBoundaryTimestamp: null,
      field: "onset",
    });

    expect(resolved).toBeNull();
  });
});
