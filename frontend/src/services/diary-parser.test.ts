import { describe, it, expect } from "bun:test";
import { parseDiaryCsv } from "./diary-parser";
import type { FileRecord } from "@/db/schema";

const makeFile = (id: number, filename: string): FileRecord => ({
  id,
  filename,
  devicePreset: "actigraph",
  epochLengthSeconds: 60,
  availableDates: ["2024-01-01"],
  fileHash: "abc",
  source: "local",
  createdAt: "2024-01-01T00:00:00Z",
});

describe("parseDiaryCsv", () => {
  it("returns error for empty CSV", () => {
    const result = parseDiaryCsv("", []);
    expect(result.errors).toContain("CSV has no data rows");
    expect(result.totalRows).toBe(0);
  });

  it("returns error for header-only CSV", () => {
    const result = parseDiaryCsv("date,filename,bed_time\n", []);
    expect(result.errors).toContain("CSV has no data rows");
  });

  it("returns error when no date column found", () => {
    const csv = "foo,filename,bed_time\n1,test.csv,22:00\n";
    const result = parseDiaryCsv(csv, []);
    expect(result.errors).toContain("No date column found");
  });

  it("returns error when no filename column found", () => {
    const csv = "date,bar,bed_time\n2024-01-01,test.csv,22:00\n";
    const result = parseDiaryCsv(csv, []);
    expect(result.errors).toContain("No filename column found for matching");
  });

  it("parses basic CSV with date and filename columns", () => {
    const files = [makeFile(1, "participant_001.csv")];
    const csv = [
      "date,filename,bed_time,wake_time",
      "2024-01-01,participant_001.csv,22:30,07:00",
    ].join("\n");

    const result = parseDiaryCsv(csv, files);
    expect(result.totalRows).toBe(1);
    expect(result.matchedRows).toBe(1);
    expect(result.unmatchedRows).toBe(0);
    expect(result.matched).toHaveLength(1);
    expect(result.matched[0]!.fileId).toBe(1);
    expect(result.matched[0]!.entries[0]!.bedTime).toBe("22:30");
    expect(result.matched[0]!.entries[0]!.wakeTime).toBe("07:00");
  });

  it("normalizes time fields (single digit hour)", () => {
    const files = [makeFile(1, "test.csv")];
    const csv = "date,filename,bed_time\n2024-01-01,test.csv,9:30\n";
    const result = parseDiaryCsv(csv, files);
    expect(result.matched[0]!.entries[0]!.bedTime).toBe("09:30");
  });

  it("handles HH:MM:SS format", () => {
    const files = [makeFile(1, "test.csv")];
    const csv = "date,filename,bed_time\n2024-01-01,test.csv,22:30:00\n";
    const result = parseDiaryCsv(csv, files);
    expect(result.matched[0]!.entries[0]!.bedTime).toBe("22:30");
  });

  it("parses integer fields", () => {
    const files = [makeFile(1, "test.csv")];
    const csv = "date,filename,sleep_quality,awakenings\n2024-01-01,test.csv,3,5.2\n";
    const result = parseDiaryCsv(csv, files);
    expect(result.matched[0]!.entries[0]!.sleepQuality).toBe(3);
    expect(result.matched[0]!.entries[0]!.numberOfAwakenings).toBe(5);
  });

  it("handles null tokens (NaN, None)", () => {
    const files = [makeFile(1, "test.csv")];
    const csv = "date,filename,bed_time,sleep_quality\n2024-01-01,test.csv,NaN,None\n";
    const result = parseDiaryCsv(csv, files);
    expect(result.matched[0]!.entries[0]!.bedTime).toBeNull();
    expect(result.matched[0]!.entries[0]!.sleepQuality).toBeNull();
  });

  it("converts nonwear reason codes to labels", () => {
    const files = [makeFile(1, "test.csv")];
    const csv = "date,filename,nonwear_1_reason\n2024-01-01,test.csv,1\n";
    const result = parseDiaryCsv(csv, files);
    expect(result.matched[0]!.entries[0]!.nonwear1Reason).toBe("Bath/Shower");
  });

  it("matches files by stem when exact filename misses", () => {
    const files = [makeFile(1, "participant_001.csv")];
    const csv = "date,filename,bed_time\n2024-01-01,participant_001,22:00\n";
    const result = parseDiaryCsv(csv, files);
    expect(result.matchedRows).toBe(1);
  });

  it("counts unmatched rows correctly", () => {
    const csv = "date,filename,bed_time\n2024-01-01,unknown.csv,22:00\n";
    const result = parseDiaryCsv(csv, []);
    expect(result.unmatchedRows).toBe(1);
    expect(result.matchedRows).toBe(0);
  });

  it("reports unparseable dates as errors", () => {
    const files = [makeFile(1, "test.csv")];
    const csv = "date,filename,bed_time\nbaddate,test.csv,22:00\n";
    const result = parseDiaryCsv(csv, files);
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.errors[0]).toContain("could not parse date");
  });

  it("handles column aliases (in_bed_time -> bedTime)", () => {
    const files = [makeFile(1, "test.csv")];
    const csv = "date,filename,in_bed_time\n2024-01-01,test.csv,23:00\n";
    const result = parseDiaryCsv(csv, files);
    expect(result.matched[0]!.entries[0]!.bedTime).toBe("23:00");
  });

  it("handles BOM-prefixed CSV", () => {
    const files = [makeFile(1, "test.csv")];
    const csv = "\uFEFFdate,filename,bed_time\n2024-01-01,test.csv,22:00\n";
    const result = parseDiaryCsv(csv, files);
    expect(result.matchedRows).toBe(1);
  });

  it("handles MM/DD/YYYY date format", () => {
    const files = [makeFile(1, "test.csv")];
    const csv = "date,filename,bed_time\n01/15/2024,test.csv,22:00\n";
    const result = parseDiaryCsv(csv, files);
    expect(result.matched[0]!.entries[0]!.analysisDate).toBe("2024-01-15");
  });

  it("handles multiple rows for the same file", () => {
    const files = [makeFile(1, "test.csv")];
    const csv = [
      "date,filename,bed_time",
      "2024-01-01,test.csv,22:00",
      "2024-01-02,test.csv,23:00",
    ].join("\n");

    const result = parseDiaryCsv(csv, files);
    expect(result.matched).toHaveLength(1);
    expect(result.matched[0]!.entries).toHaveLength(2);
  });

  it("skips rows with empty date", () => {
    const files = [makeFile(1, "test.csv")];
    const csv = "date,filename,bed_time\n,test.csv,22:00\n";
    const result = parseDiaryCsv(csv, files);
    expect(result.unmatchedRows).toBe(1);
    expect(result.matchedRows).toBe(0);
  });
});
