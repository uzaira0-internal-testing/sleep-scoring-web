import { describe, test, expect } from "bun:test";
import { rowsToCsv } from "./local-export";
import { MARKER_TYPES } from "@/api/types";

describe("rowsToCsv", () => {
  test("produces correct headers", () => {
    const csv = rowsToCsv([]);
    const headers = csv.split("\n")[0];
    expect(headers).toBe(
      "Filename,Study Date,Period Index,Marker Type,Onset Time,Offset Time," +
      "Total Sleep Time (min),Sleep Efficiency (%),WASO (min)," +
      "Sleep Onset Latency (min),Number of Awakenings,Is No Sleep,Notes"
    );
  });

  test("formats a complete row", () => {
    const csv = rowsToCsv([{
      filename: "test.csv",
      studyDate: "2026-01-15",
      periodIndex: 0,
      markerType: MARKER_TYPES.MAIN_SLEEP,
      onsetTime: "2026-01-15T22:00:00.000Z",
      offsetTime: "2026-01-16T06:00:00.000Z",
      tst: 420.5,
      sleepEfficiency: 87.6,
      waso: 30.2,
      sol: 15.3,
      awakenings: 3,
      isNoSleep: false,
      notes: "",
    }]);
    const lines = csv.split("\n");
    expect(lines).toHaveLength(2);
    const values = lines[1]!.split(",");
    expect(values[0]).toBe("test.csv");
    expect(values[1]).toBe("2026-01-15");
    expect(values[2]).toBe("0");
    expect(values[3]).toBe(MARKER_TYPES.MAIN_SLEEP);
    expect(values[6]).toBe("420.5");
    expect(values[7]).toBe("87.6");
    expect(values[11]).toBe("FALSE");
  });

  test("handles null metrics", () => {
    const csv = rowsToCsv([{
      filename: "test.csv",
      studyDate: "2026-01-15",
      periodIndex: 0,
      markerType: "NO_SLEEP",
      onsetTime: null,
      offsetTime: null,
      tst: null,
      sleepEfficiency: null,
      waso: null,
      sol: null,
      awakenings: null,
      isNoSleep: true,
      notes: "",
    }]);
    const values = csv.split("\n")[1]!.split(",");
    expect(values[4]).toBe(""); // onset
    expect(values[5]).toBe(""); // offset
    expect(values[6]).toBe(""); // tst
    expect(values[11]).toBe("TRUE");
  });

  test("escapes filenames with commas (RFC 4180)", () => {
    const csv = rowsToCsv([{
      filename: "file,with,commas.csv",
      studyDate: "2026-01-15",
      periodIndex: 0,
      markerType: MARKER_TYPES.MAIN_SLEEP,
      onsetTime: null,
      offsetTime: null,
      tst: null,
      sleepEfficiency: null,
      waso: null,
      sol: null,
      awakenings: null,
      isNoSleep: false,
      notes: "",
    }]);
    // The escaped field starts with a quote
    expect(csv.split("\n")[1]).toContain('"file,with,commas.csv"');
  });

  test("escapes notes with quotes", () => {
    const csv = rowsToCsv([{
      filename: "test.csv",
      studyDate: "2026-01-15",
      periodIndex: 0,
      markerType: MARKER_TYPES.MAIN_SLEEP,
      onsetTime: null,
      offsetTime: null,
      tst: null,
      sleepEfficiency: null,
      waso: null,
      sol: null,
      awakenings: null,
      isNoSleep: false,
      notes: 'said "hello"',
    }]);
    // Double-quoting per RFC 4180
    expect(csv.split("\n")[1]).toContain('"said ""hello"""');
  });

  test("escapes notes with newlines", () => {
    const csv = rowsToCsv([{
      filename: "test.csv",
      studyDate: "2026-01-15",
      periodIndex: 0,
      markerType: MARKER_TYPES.MAIN_SLEEP,
      onsetTime: null,
      offsetTime: null,
      tst: null,
      sleepEfficiency: null,
      waso: null,
      sol: null,
      awakenings: null,
      isNoSleep: false,
      notes: "line1\nline2",
    }]);
    expect(csv).toContain('"line1\nline2"');
  });

  test("handles multiple rows", () => {
    const csv = rowsToCsv([
      {
        filename: "a.csv", studyDate: "2026-01-15", periodIndex: 0,
        markerType: MARKER_TYPES.MAIN_SLEEP, onsetTime: null, offsetTime: null,
        tst: 100, sleepEfficiency: 90, waso: 5, sol: 5, awakenings: 1,
        isNoSleep: false, notes: "",
      },
      {
        filename: "b.csv", studyDate: "2026-01-16", periodIndex: 1,
        markerType: MARKER_TYPES.NAP, onsetTime: null, offsetTime: null,
        tst: 30, sleepEfficiency: 95, waso: 1, sol: 2, awakenings: 0,
        isNoSleep: false, notes: "afternoon nap",
      },
    ]);
    const lines = csv.split("\n");
    expect(lines).toHaveLength(3); // header + 2 rows
  });
});
