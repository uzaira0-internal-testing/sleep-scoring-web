import { describe, it, expect } from "bun:test";

import { resolveEditedTimeToTimestamp } from "./time-edit";

describe("resolveEditedTimeToTimestamp", () => {
  it("maps early-morning onset to current scoring day in 48h context", () => {
    // User is scoring 2025-04-05 and enters 01:13 onset, 10:34 offset.
    // Existing onset may still be on previous day from earlier edits.
    const offsetTs = Date.UTC(2025, 3, 5, 10, 34, 0, 0);
    const staleOnsetReferenceTs = Date.UTC(2025, 3, 4, 23, 30, 0, 0);

    const resolved = resolveEditedTimeToTimestamp({
      timeStr: "01:13",
      currentDate: "2025-04-05",
      referenceTimestampMs: staleOnsetReferenceTs,
      otherBoundaryTimestampMs: offsetTs,
      field: "onset",
    });

    expect(resolved).toBe(Date.UTC(2025, 3, 5, 1, 13, 0, 0));
  });

  it("maps late-evening onset to previous day when offset is next morning", () => {
    const offsetTs = Date.UTC(2025, 3, 5, 7, 0, 0, 0);
    const onsetReferenceTs = Date.UTC(2025, 3, 5, 0, 30, 0, 0);

    const resolved = resolveEditedTimeToTimestamp({
      timeStr: "23:45",
      currentDate: "2025-04-05",
      referenceTimestampMs: onsetReferenceTs,
      otherBoundaryTimestampMs: offsetTs,
      field: "onset",
    });

    expect(resolved).toBe(Date.UTC(2025, 3, 4, 23, 45, 0, 0));
  });

  it("maps offset to the earliest valid time after onset", () => {
    const onsetTs = Date.UTC(2025, 3, 4, 23, 15, 0, 0);
    const offsetReferenceTs = Date.UTC(2025, 3, 4, 6, 0, 0, 0);

    const resolved = resolveEditedTimeToTimestamp({
      timeStr: "10:34",
      currentDate: "2025-04-05",
      referenceTimestampMs: offsetReferenceTs,
      otherBoundaryTimestampMs: onsetTs,
      field: "offset",
    });

    expect(resolved).toBe(Date.UTC(2025, 3, 5, 10, 34, 0, 0));
  });

  it("returns null for invalid time strings", () => {
    const resolved = resolveEditedTimeToTimestamp({
      timeStr: "25:99",
      currentDate: "2025-04-05",
      referenceTimestampMs: Date.UTC(2025, 3, 5, 1, 0, 0, 0),
      otherBoundaryTimestampMs: null,
      field: "onset",
    });

    expect(resolved).toBeNull();
  });
});

