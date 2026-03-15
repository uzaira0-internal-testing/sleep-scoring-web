/**
 * Tests for nonwear-csv-parser.ts — sensor nonwear CSV parsing and file matching.
 */
import { describe, it, expect } from "bun:test";
import { parseNonwearCsv } from "./nonwear-csv-parser";
import type { FileRecord } from "@/db/schema";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeFileRecord(id: number, filename: string): FileRecord {
  return {
    id,
    filename,
    devicePreset: "actigraph",
    epochLengthSeconds: 60,
    availableDates: ["2025-03-01"],
    fileHash: "abc123",
    source: "local",
    createdAt: "2025-01-01T00:00:00Z",
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("parseNonwearCsv", () => {
  it("returns error for empty CSV", () => {
    const result = parseNonwearCsv("", []);
    expect(result.errors).toContain("CSV has no data rows");
    expect(result.matched).toHaveLength(0);
  });

  it("returns error for header-only CSV", () => {
    const result = parseNonwearCsv("date,start_time,end_time,filename", []);
    expect(result.errors).toContain("CSV has no data rows");
  });

  it("returns error when date column is missing", () => {
    const csv = "start_time,end_time,filename\n10:00,12:00,test.csv";
    const result = parseNonwearCsv(csv, []);
    expect(result.errors).toContain("No date column found");
  });

  it("returns error when start_time column is missing", () => {
    const csv = "date,end_time,filename\n2025-03-01,12:00,test.csv";
    const result = parseNonwearCsv(csv, []);
    expect(result.errors).toContain("No start_time column found");
  });

  it("returns error when end_time column is missing", () => {
    const csv = "date,start_time,filename\n2025-03-01,10:00,test.csv";
    const result = parseNonwearCsv(csv, []);
    expect(result.errors).toContain("No end_time column found");
  });

  it("returns error when no filename or pid column", () => {
    const csv = "date,start_time,end_time\n2025-03-01,10:00,12:00";
    const result = parseNonwearCsv(csv, []);
    expect(result.errors).toContain("No filename or participant_id column found for matching");
  });

  it("parses valid CSV and matches by filename", () => {
    const files = [makeFileRecord(1, "participant_001.csv")];
    const csv = [
      "date,start_time,end_time,filename",
      "2025-03-01,10:00,12:00,participant_001.csv",
      "2025-03-01,14:00,15:30,participant_001.csv",
    ].join("\n");

    const result = parseNonwearCsv(csv, files);
    expect(result.totalRows).toBe(2);
    expect(result.matchedRows).toBe(2);
    expect(result.unmatchedRows).toBe(0);
    expect(result.matched).toHaveLength(1);
    expect(result.matched[0]!.fileId).toBe(1);
    expect(result.matched[0]!.entries).toHaveLength(2);

    // Check period indices
    expect(result.matched[0]!.entries[0]!.periodIndex).toBe(0);
    expect(result.matched[0]!.entries[1]!.periodIndex).toBe(1);
  });

  it("matches by filename stem when extension differs", () => {
    const files = [makeFileRecord(1, "participant_001.csv")];
    const csv = [
      "date,start_time,end_time,filename",
      "2025-03-01,10:00,12:00,participant_001",
    ].join("\n");

    const result = parseNonwearCsv(csv, files);
    expect(result.matchedRows).toBe(1);
  });

  it("matches by participant_id", () => {
    const files = [makeFileRecord(1, "study_pid123_data.csv")];
    const csv = [
      "date,start_time,end_time,participant_id",
      "2025-03-01,10:00,12:00,pid123",
    ].join("\n");

    const result = parseNonwearCsv(csv, files);
    expect(result.matchedRows).toBe(1);
    expect(result.matched[0]!.fileId).toBe(1);
  });

  it("handles MM/DD/YYYY date format", () => {
    const files = [makeFileRecord(1, "data.csv")];
    const csv = [
      "date,start_time,end_time,filename",
      "03/01/2025,10:00,12:00,data.csv",
    ].join("\n");

    const result = parseNonwearCsv(csv, files);
    expect(result.matchedRows).toBe(1);
    expect(result.matched[0]!.entries[0]!.analysisDate).toBe("2025-03-01");
  });

  it("handles AM/PM time format", () => {
    const files = [makeFileRecord(1, "data.csv")];
    const csv = [
      "date,start_time,end_time,filename",
      "2025-03-01,10:00 AM,2:30 PM,data.csv",
    ].join("\n");

    const result = parseNonwearCsv(csv, files);
    expect(result.matchedRows).toBe(1);
    const entry = result.matched[0]!.entries[0]!;
    // 10:00 AM = 10:00 UTC, 2:30 PM = 14:30 UTC
    const expectedStart = Date.UTC(2025, 2, 1, 10, 0, 0) / 1000;
    const expectedEnd = Date.UTC(2025, 2, 1, 14, 30, 0) / 1000;
    expect(entry.startTimestamp).toBe(expectedStart);
    expect(entry.endTimestamp).toBe(expectedEnd);
  });

  it("handles column aliases (nonwear_start, nw_end)", () => {
    const files = [makeFileRecord(1, "data.csv")];
    const csv = [
      "analysis_date,nonwear_start,nonwear_end,file_name",
      "2025-03-01,10:00,12:00,data.csv",
    ].join("\n");

    const result = parseNonwearCsv(csv, files);
    expect(result.matchedRows).toBe(1);
  });

  it("reports unmatched rows", () => {
    const files = [makeFileRecord(1, "existing.csv")];
    const csv = [
      "date,start_time,end_time,filename",
      "2025-03-01,10:00,12:00,missing_file.csv",
    ].join("\n");

    const result = parseNonwearCsv(csv, files);
    expect(result.unmatchedRows).toBe(1);
    expect(result.matchedRows).toBe(0);
  });

  it("reports rows with missing fields", () => {
    const files = [makeFileRecord(1, "data.csv")];
    const csv = [
      "date,start_time,end_time,filename",
      ",10:00,12:00,data.csv",
    ].join("\n");

    const result = parseNonwearCsv(csv, files);
    expect(result.unmatchedRows).toBe(1);
    expect(result.errors.length).toBeGreaterThan(0);
  });

  it("handles BOM-prefixed CSV", () => {
    const files = [makeFileRecord(1, "data.csv")];
    const csv = "\uFEFF" + [
      "date,start_time,end_time,filename",
      "2025-03-01,10:00,12:00,data.csv",
    ].join("\n");

    const result = parseNonwearCsv(csv, files);
    expect(result.matchedRows).toBe(1);
  });

  it("handles ISO datetime in time fields", () => {
    const files = [makeFileRecord(1, "data.csv")];
    const csv = [
      "date,start_time,end_time,filename",
      "2025-03-01,2025-03-01T10:30:00,2025-03-01T12:00:00,data.csv",
    ].join("\n");

    const result = parseNonwearCsv(csv, files);
    expect(result.matchedRows).toBe(1);
    const entry = result.matched[0]!.entries[0]!;
    expect(entry.startTimestamp).toBe(Date.UTC(2025, 2, 1, 10, 30, 0) / 1000);
  });

  it("handles multiple files in one CSV", () => {
    const files = [
      makeFileRecord(1, "file_a.csv"),
      makeFileRecord(2, "file_b.csv"),
    ];
    const csv = [
      "date,start_time,end_time,filename",
      "2025-03-01,10:00,12:00,file_a.csv",
      "2025-03-01,14:00,16:00,file_b.csv",
      "2025-03-01,09:00,10:00,file_a.csv",
    ].join("\n");

    const result = parseNonwearCsv(csv, files);
    expect(result.matchedRows).toBe(3);
    expect(result.matched).toHaveLength(2);

    const fileA = result.matched.find((m) => m.fileId === 1)!;
    const fileB = result.matched.find((m) => m.fileId === 2)!;
    expect(fileA.entries).toHaveLength(2);
    expect(fileB.entries).toHaveLength(1);
  });
});
