/**
 * Shared CSV parsing utilities used by nonwear-csv-parser and diary-parser.
 */
import type { FileRecord } from "@/db/schema";

// ---------------------------------------------------------------------------
// Shared column alias constants
// ---------------------------------------------------------------------------

export const DATE_ALIASES = new Set([
  "date", "startdate", "analysis_date", "diary_date", "date_of_last_night",
]);

export const FILENAME_ALIASES = new Set(["filename", "file", "file_name"]);

export const PARTICIPANT_ID_ALIASES = new Set([
  "participant_id", "participantid", "pid", "subject_id", "id",
]);

// ---------------------------------------------------------------------------
// Date parsing (5 formats matching backend)
// ---------------------------------------------------------------------------

export function parseDate(dateStr: string): string | null {
  const s = dateStr.trim();
  let m: RegExpMatchArray | null;
  // YYYY-MM-DD
  m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  // MM/DD/YYYY
  m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (m) return `${m[3]}-${m[1]}-${m[2]}`;
  // MM/DD/YY
  m = s.match(/^(\d{2})\/(\d{2})\/(\d{2})$/);
  if (m) {
    const y = parseInt(m[3], 10);
    return `${y >= 50 ? 1900 + y : 2000 + y}-${m[1]}-${m[2]}`;
  }
  // YYYY/MM/DD
  m = s.match(/^(\d{4})\/(\d{2})\/(\d{2})$/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  return null;
}

// ---------------------------------------------------------------------------
// Filename normalization (mirrors backend file_identity.py)
// ---------------------------------------------------------------------------

export function normalizeFilename(name: string): string {
  const parts = name.replace(/\\/g, "/").split("/");
  return (parts[parts.length - 1] ?? name).toLowerCase();
}

export function filenameStem(name: string): string {
  const n = normalizeFilename(name);
  const dot = n.lastIndexOf(".");
  return dot > 0 ? n.slice(0, dot) : n;
}

// ---------------------------------------------------------------------------
// File lookup index builder
// ---------------------------------------------------------------------------

export function buildFileLookup(localFiles: FileRecord[]): {
  byFilename: Map<string, FileRecord>;
  byStem: Map<string, FileRecord>;
} {
  const byFilename = new Map<string, FileRecord>();
  const byStem = new Map<string, FileRecord>();
  for (const f of localFiles) {
    byFilename.set(normalizeFilename(f.filename), f);
    byStem.set(filenameStem(f.filename), f);
  }
  return { byFilename, byStem };
}

// ---------------------------------------------------------------------------
// Null token check
// ---------------------------------------------------------------------------

const NULL_TOKENS = new Set(["", "nan", "none", "null", "nat"]);

export function isNullToken(v: string): boolean {
  return NULL_TOKENS.has(v.trim().toLowerCase());
}

// ---------------------------------------------------------------------------
// CSV line parser (handles quoted fields)
// ---------------------------------------------------------------------------

export function parseCsvLine(line: string): string[] {
  const result: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === "," && !inQuotes) {
      result.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  result.push(current.trim());
  return result;
}
