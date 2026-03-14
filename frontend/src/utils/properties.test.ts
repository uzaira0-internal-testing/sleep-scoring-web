/**
 * Property-based tests using fast-check.
 *
 * These tests verify algebraic properties and invariants of common
 * sleep-scoring operations. All helper functions are defined inline
 * so the tests are self-contained and independent of the build environment.
 */

import { describe, it, expect } from "bun:test";
import * as fc from "fast-check";

// ---------------------------------------------------------------------------
// Inline helpers (mirrors of real logic, kept self-contained)
// ---------------------------------------------------------------------------

/** Count sleep epochs (1s) in a score array. */
function computeTST(epochs: number[]): number {
  return epochs.filter((e) => e === 1).length;
}

/** Format a unix timestamp (seconds) as HH:MM:SS in UTC. */
function formatTimestamp(unixSeconds: number): string {
  const date = new Date(unixSeconds * 1000);
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");
  const ss = String(date.getUTCSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

/** Convert a time string "HH:MM" to total minutes since midnight. */
function parseTimeToMinutes(timeStr: string): number {
  const [hh, mm] = timeStr.split(":").map(Number);
  return hh! * 60 + mm!;
}

/** Convert total minutes since midnight back to "HH:MM". */
function minutesToTime(totalMinutes: number): string {
  const h = Math.floor(totalMinutes / 60) % 24;
  const m = totalMinutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** Compute sleep efficiency as TST / TIB. */
function sleepEfficiency(tst: number, tib: number): number {
  if (tib === 0) return 0;
  return tst / tib;
}

interface Marker {
  id: string;
  onset_timestamp: number;
  offset_timestamp: number;
}

/** Sort markers by onset_timestamp ascending. */
function sortMarkers(markers: Marker[]): Marker[] {
  return [...markers].sort((a, b) => a.onset_timestamp - b.onset_timestamp);
}

// ---------------------------------------------------------------------------
// Property tests
// ---------------------------------------------------------------------------

describe("Property-based tests", () => {
  // 1. TST is always non-negative and at most the epoch count
  describe("computeTST", () => {
    it("TST is always non-negative and <= epoch count", () => {
      fc.assert(
        fc.property(
          fc.array(fc.constantFrom(0, 1), { minLength: 1, maxLength: 1440 }),
          (epochs) => {
            const tst = computeTST(epochs);
            return tst >= 0 && tst <= epochs.length;
          },
        ),
      );
    });

    it("TST equals array length when all epochs are sleep", () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 1, max: 1440 }),
          (n) => {
            const allSleep = Array.from({ length: n }, () => 1);
            return computeTST(allSleep) === n;
          },
        ),
      );
    });

    it("TST is zero when all epochs are wake", () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 1, max: 1440 }),
          (n) => {
            const allWake = Array.from({ length: n }, () => 0);
            return computeTST(allWake) === 0;
          },
        ),
      );
    });
  });

  // 2. formatTimestamp always produces HH:MM:SS
  describe("formatTimestamp", () => {
    it("output always matches HH:MM:SS pattern", () => {
      fc.assert(
        fc.property(
          // Unix timestamps roughly between 2000-01-01 and 2040-01-01
          fc.integer({ min: 946684800, max: 2208988800 }),
          (ts) => {
            const result = formatTimestamp(ts);
            return /^\d{2}:\d{2}:\d{2}$/.test(result);
          },
        ),
      );
    });

    it("hours are in [00, 23], minutes and seconds in [00, 59]", () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 0, max: 2_000_000_000 }),
          (ts) => {
            const result = formatTimestamp(ts);
            const [hh, mm, ss] = result.split(":").map(Number);
            return (
              hh! >= 0 && hh! <= 23 &&
              mm! >= 0 && mm! <= 59 &&
              ss! >= 0 && ss! <= 59
            );
          },
        ),
      );
    });

    it("formatting is deterministic", () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 0, max: 2_000_000_000 }),
          (ts) => {
            return formatTimestamp(ts) === formatTimestamp(ts);
          },
        ),
      );
    });
  });

  // 3. parseTimeToMinutes / minutesToTime round-trip
  describe("parseTimeToMinutes <-> minutesToTime round-trip", () => {
    /** Arbitrary for valid HH:MM strings */
    const validTimeArb = fc
      .record({
        h: fc.integer({ min: 0, max: 23 }),
        m: fc.integer({ min: 0, max: 59 }),
      })
      .map(({ h, m }) => ({
        str: `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`,
        totalMinutes: h * 60 + m,
      }));

    it("parseTimeToMinutes then minutesToTime returns original string", () => {
      fc.assert(
        fc.property(validTimeArb, ({ str }) => {
          const minutes = parseTimeToMinutes(str);
          const roundTripped = minutesToTime(minutes);
          return roundTripped === str;
        }),
      );
    });

    it("minutesToTime then parseTimeToMinutes returns original minutes", () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 0, max: 23 * 60 + 59 }),
          (totalMinutes) => {
            const str = minutesToTime(totalMinutes);
            const roundTripped = parseTimeToMinutes(str);
            return roundTripped === totalMinutes;
          },
        ),
      );
    });

    it("parseTimeToMinutes returns value in [0, 1439]", () => {
      fc.assert(
        fc.property(validTimeArb, ({ str }) => {
          const minutes = parseTimeToMinutes(str);
          return minutes >= 0 && minutes <= 1439;
        }),
      );
    });
  });

  // 4. Sleep efficiency is in [0, 1] for valid inputs
  describe("sleepEfficiency", () => {
    it("efficiency is in [0, 1] when TST <= TIB", () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 0, max: 1440 }),
          fc.integer({ min: 1, max: 1440 }),
          (tst, tib) => {
            fc.pre(tst <= tib);
            const eff = sleepEfficiency(tst, tib);
            return eff >= 0 && eff <= 1;
          },
        ),
      );
    });

    it("efficiency is 1 when TST equals TIB", () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 1, max: 1440 }),
          (n) => {
            return sleepEfficiency(n, n) === 1;
          },
        ),
      );
    });

    it("efficiency is 0 when TST is 0", () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 1, max: 1440 }),
          (tib) => {
            return sleepEfficiency(0, tib) === 0;
          },
        ),
      );
    });

    it("efficiency is 0 when TIB is 0 (guarded division)", () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 0, max: 1440 }),
          (tst) => {
            return sleepEfficiency(tst, 0) === 0;
          },
        ),
      );
    });
  });

  // 5. Marker sort: sorted markers have ascending onset_timestamp
  describe("marker sort", () => {
    const markerArb: fc.Arbitrary<Marker> = fc.record({
      id: fc.uuid(),
      onset_timestamp: fc.integer({ min: 1_000_000_000, max: 2_000_000_000 }),
      offset_timestamp: fc.integer({ min: 1_000_000_000, max: 2_000_000_000 }),
    });

    it("sorted markers are in ascending onset_timestamp order", () => {
      fc.assert(
        fc.property(
          fc.array(markerArb, { minLength: 0, maxLength: 100 }),
          (markers) => {
            const sorted = sortMarkers(markers);
            for (let i = 1; i < sorted.length; i++) {
              if (sorted[i]!.onset_timestamp < sorted[i - 1]!.onset_timestamp) {
                return false;
              }
            }
            return true;
          },
        ),
      );
    });

    it("sorting preserves array length", () => {
      fc.assert(
        fc.property(
          fc.array(markerArb, { minLength: 0, maxLength: 100 }),
          (markers) => {
            return sortMarkers(markers).length === markers.length;
          },
        ),
      );
    });

    it("sorting is idempotent", () => {
      fc.assert(
        fc.property(
          fc.array(markerArb, { minLength: 0, maxLength: 100 }),
          (markers) => {
            const once = sortMarkers(markers);
            const twice = sortMarkers(once);
            return JSON.stringify(once) === JSON.stringify(twice);
          },
        ),
      );
    });

    it("sorting does not mutate the original array", () => {
      fc.assert(
        fc.property(
          fc.array(markerArb, { minLength: 1, maxLength: 50 }),
          (markers) => {
            const copy = JSON.stringify(markers);
            sortMarkers(markers);
            return JSON.stringify(markers) === copy;
          },
        ),
      );
    });
  });

  // 6. Undo/redo invariant: applying an action then undoing restores state
  describe("undo/redo invariant", () => {
    interface UndoableState {
      items: number[];
      undoStack: number[][];
      redoStack: number[][];
    }

    function createState(items: number[]): UndoableState {
      return { items: [...items], undoStack: [], redoStack: [] };
    }

    function applyAction(state: UndoableState, item: number): UndoableState {
      return {
        items: [...state.items, item],
        undoStack: [...state.undoStack, [...state.items]],
        redoStack: [],
      };
    }

    function undo(state: UndoableState): UndoableState {
      if (state.undoStack.length === 0) return state;
      const previousItems = state.undoStack[state.undoStack.length - 1]!;
      return {
        items: [...previousItems],
        undoStack: state.undoStack.slice(0, -1),
        redoStack: [...state.redoStack, [...state.items]],
      };
    }

    function redo(state: UndoableState): UndoableState {
      if (state.redoStack.length === 0) return state;
      const nextItems = state.redoStack[state.redoStack.length - 1]!;
      return {
        items: [...nextItems],
        undoStack: [...state.undoStack, [...state.items]],
        redoStack: state.redoStack.slice(0, -1),
      };
    }

    it("apply then undo restores original items", () => {
      fc.assert(
        fc.property(
          fc.array(fc.integer(), { minLength: 0, maxLength: 50 }),
          fc.integer(),
          (initialItems, newItem) => {
            const state = createState(initialItems);
            const afterAction = applyAction(state, newItem);
            const afterUndo = undo(afterAction);
            return JSON.stringify(afterUndo.items) === JSON.stringify(initialItems);
          },
        ),
      );
    });

    it("apply then undo then redo restores the applied state", () => {
      fc.assert(
        fc.property(
          fc.array(fc.integer(), { minLength: 0, maxLength: 50 }),
          fc.integer(),
          (initialItems, newItem) => {
            const state = createState(initialItems);
            const afterAction = applyAction(state, newItem);
            const afterUndo = undo(afterAction);
            const afterRedo = redo(afterUndo);
            return JSON.stringify(afterRedo.items) === JSON.stringify(afterAction.items);
          },
        ),
      );
    });

    it("multiple applies then undos restore each prior state in order", () => {
      fc.assert(
        fc.property(
          fc.array(fc.integer(), { minLength: 0, maxLength: 20 }),
          fc.array(fc.integer(), { minLength: 1, maxLength: 10 }),
          (initialItems, actions) => {
            let state = createState(initialItems);
            const snapshots: string[] = [JSON.stringify(state.items)];

            // Apply all actions, recording each intermediate state
            for (const action of actions) {
              state = applyAction(state, action);
              snapshots.push(JSON.stringify(state.items));
            }

            // Undo all actions and verify each restored state matches
            for (let i = snapshots.length - 2; i >= 0; i--) {
              state = undo(state);
              if (JSON.stringify(state.items) !== snapshots[i]) {
                return false;
              }
            }
            return true;
          },
        ),
      );
    });

    it("undo on empty undo stack is a no-op", () => {
      fc.assert(
        fc.property(
          fc.array(fc.integer(), { minLength: 0, maxLength: 20 }),
          (items) => {
            const state = createState(items);
            const afterUndo = undo(state);
            return (
              JSON.stringify(afterUndo.items) === JSON.stringify(state.items) &&
              afterUndo.undoStack.length === 0
            );
          },
        ),
      );
    });

    it("redo on empty redo stack is a no-op", () => {
      fc.assert(
        fc.property(
          fc.array(fc.integer(), { minLength: 0, maxLength: 20 }),
          (items) => {
            const state = createState(items);
            const afterRedo = redo(state);
            return (
              JSON.stringify(afterRedo.items) === JSON.stringify(state.items) &&
              afterRedo.redoStack.length === 0
            );
          },
        ),
      );
    });

    it("applying a new action clears the redo stack", () => {
      fc.assert(
        fc.property(
          fc.array(fc.integer(), { minLength: 0, maxLength: 20 }),
          fc.integer(),
          fc.integer(),
          (initialItems, firstAction, secondAction) => {
            const state = createState(initialItems);
            const afterFirst = applyAction(state, firstAction);
            const afterUndo = undo(afterFirst);
            // Redo stack should have one entry
            if (afterUndo.redoStack.length !== 1) return false;
            // Applying a new action should clear the redo stack
            const afterSecond = applyAction(afterUndo, secondAction);
            return afterSecond.redoStack.length === 0;
          },
        ),
      );
    });
  });
});
