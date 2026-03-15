/**
 * Tests for csv-utils.ts — shared CSV parsing utilities.
 */
import { describe, it, expect } from "bun:test";
import {
  parseDate,
  normalizeFilename,
  filenameStem,
  buildFileLookup,
  isNullToken,
  parseCsvLine,
  stripBom,
} from "./csv-utils";
import type { FileRecord } from "@/db/schema";

// ---------------------------------------------------------------------------
// parseDate
// ---------------------------------------------------------------------------

describe("parseDate", () => {
  it("parses YYYY-MM-DD", () => {
    expect(parseDate("2025-03-01")).toBe("2025-03-01");
  });

  it("parses YYYY-M-D (single digit)", () => {
    expect(parseDate("2025-3-1")).toBe("2025-03-01");
  });

  it("parses MM/DD/YYYY", () => {
    expect(parseDate("03/01/2025")).toBe("2025-03-01");
  });

  it("parses M/D/YYYY (single digit)", () => {
    expect(parseDate("3/1/2025")).toBe("2025-03-01");
  });

  it("parses MM/DD/YY (20xx)", () => {
    expect(parseDate("03/01/25")).toBe("2025-03-01");
  });

  it("parses MM/DD/YY (19xx for year >= 50)", () => {
    expect(parseDate("03/01/99")).toBe("1999-03-01");
  });

  it("parses YYYY/MM/DD", () => {
    expect(parseDate("2025/03/01")).toBe("2025-03-01");
  });

  it("returns null for invalid format", () => {
    expect(parseDate("not-a-date")).toBeNull();
    expect(parseDate("01-Mar-2025")).toBeNull();
    expect(parseDate("")).toBeNull();
  });

  it("trims whitespace", () => {
    expect(parseDate("  2025-03-01  ")).toBe("2025-03-01");
  });
});

// ---------------------------------------------------------------------------
// normalizeFilename
// ---------------------------------------------------------------------------

describe("normalizeFilename", () => {
  it("lowercases filename", () => {
    expect(normalizeFilename("MyFile.CSV")).toBe("myfile.csv");
  });

  it("strips directory path with forward slashes", () => {
    expect(normalizeFilename("path/to/file.csv")).toBe("file.csv");
  });

  it("strips directory path with backslashes", () => {
    expect(normalizeFilename("C:\\Users\\data\\file.csv")).toBe("file.csv");
  });

  it("handles plain filename", () => {
    expect(normalizeFilename("simple.txt")).toBe("simple.txt");
  });
});

// ---------------------------------------------------------------------------
// filenameStem
// ---------------------------------------------------------------------------

describe("filenameStem", () => {
  it("removes extension", () => {
    expect(filenameStem("data.csv")).toBe("data");
  });

  it("removes only last extension", () => {
    expect(filenameStem("data.backup.csv")).toBe("data.backup");
  });

  it("handles no extension", () => {
    expect(filenameStem("noext")).toBe("noext");
  });

  it("lowercases", () => {
    expect(filenameStem("MyFile.CSV")).toBe("myfile");
  });

  it("handles path + extension", () => {
    expect(filenameStem("path/to/File.CSV")).toBe("file");
  });
});

// ---------------------------------------------------------------------------
// buildFileLookup
// ---------------------------------------------------------------------------

describe("buildFileLookup", () => {
  function mkFile(id: number, filename: string): FileRecord {
    return {
      id,
      filename,
      devicePreset: "actigraph",
      epochLengthSeconds: 60,
      availableDates: [],
      fileHash: "",
      source: "local",
      createdAt: "",
    };
  }

  it("builds lookup by filename and stem", () => {
    const files = [mkFile(1, "data.csv"), mkFile(2, "other.csv")];
    const { byFilename, byStem } = buildFileLookup(files);
    expect(byFilename.get("data.csv")?.id).toBe(1);
    expect(byStem.get("data")?.id).toBe(1);
    expect(byFilename.get("other.csv")?.id).toBe(2);
    expect(byStem.get("other")?.id).toBe(2);
  });

  it("handles empty file list", () => {
    const { byFilename, byStem } = buildFileLookup([]);
    expect(byFilename.size).toBe(0);
    expect(byStem.size).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// isNullToken
// ---------------------------------------------------------------------------

describe("isNullToken", () => {
  it("recognizes empty string", () => {
    expect(isNullToken("")).toBe(true);
    expect(isNullToken("  ")).toBe(true);
  });

  it("recognizes nan/none/null/nat (case insensitive)", () => {
    expect(isNullToken("nan")).toBe(true);
    expect(isNullToken("NaN")).toBe(true);
    expect(isNullToken("none")).toBe(true);
    expect(isNullToken("None")).toBe(true);
    expect(isNullToken("null")).toBe(true);
    expect(isNullToken("NULL")).toBe(true);
    expect(isNullToken("nat")).toBe(true);
    expect(isNullToken("NaT")).toBe(true);
  });

  it("rejects non-null values", () => {
    expect(isNullToken("hello")).toBe(false);
    expect(isNullToken("0")).toBe(false);
    expect(isNullToken("false")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// parseCsvLine
// ---------------------------------------------------------------------------

describe("parseCsvLine", () => {
  it("parses simple comma-separated values", () => {
    expect(parseCsvLine("a,b,c")).toEqual(["a", "b", "c"]);
  });

  it("trims whitespace from fields", () => {
    expect(parseCsvLine("  a , b , c  ")).toEqual(["a", "b", "c"]);
  });

  it("handles quoted fields", () => {
    expect(parseCsvLine('"hello","world"')).toEqual(["hello", "world"]);
  });

  it("handles commas inside quotes", () => {
    expect(parseCsvLine('"a,b",c')).toEqual(["a,b", "c"]);
  });

  it("handles escaped quotes (doubled)", () => {
    expect(parseCsvLine('"say ""hello""",world')).toEqual(['say "hello"', "world"]);
  });

  it("handles empty fields", () => {
    expect(parseCsvLine("a,,c")).toEqual(["a", "", "c"]);
  });

  it("handles single field", () => {
    expect(parseCsvLine("only")).toEqual(["only"]);
  });

  it("handles empty string", () => {
    expect(parseCsvLine("")).toEqual([""]);
  });
});

// ---------------------------------------------------------------------------
// stripBom
// ---------------------------------------------------------------------------

describe("stripBom", () => {
  it("strips UTF-8 BOM", () => {
    expect(stripBom("\uFEFFhello")).toBe("hello");
  });

  it("leaves non-BOM string unchanged", () => {
    expect(stripBom("hello")).toBe("hello");
  });

  it("handles empty string", () => {
    expect(stripBom("")).toBe("");
  });
});
