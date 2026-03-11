/**
 * Local sensor nonwear CSV parser.
 *
 * Ports the column alias detection, date/time parsing, and file matching
 * from the backend (sleep_scoring_web/api/markers.py nonwear upload).
 *
 * Local mode matches by normalized filename/stem against IndexedDB files.
 */
import type { SensorNonwearEntry } from "@/db";
import type { FileRecord } from "@/db/schema";
import {
  parseDate,
  normalizeFilename,
  filenameStem,
  buildFileLookup,
  isNullToken,
  parseCsvLine,
  stripBom,
  DATE_ALIASES,
  FILENAME_ALIASES,
  PARTICIPANT_ID_ALIASES,
} from "@/lib/csv-utils";

// ---------------------------------------------------------------------------
// Column aliases (mirrors backend _NONWEAR_COLUMN_ALIASES)
// ---------------------------------------------------------------------------

const START_TIME_ALIASES = new Set([
  "start_time", "start", "nonwear_start", "nonwear_start_time",
  "nw_start", "start_datetime", "nonwear_start_datetime",
]);

const END_TIME_ALIASES = new Set([
  "end_time", "end", "nonwear_end", "nonwear_end_time",
  "nw_end", "end_datetime", "nonwear_end_datetime",
]);

// ---------------------------------------------------------------------------
// Time parsing
// ---------------------------------------------------------------------------

/**
 * Parse a time string from various formats to "HH:MM:SS" or "HH:MM".
 * Handles: "10:30", "10:30:00", "2025-08-01T10:30:00", "2025-08-01 10:30:00", "10:30 AM"
 */
function parseTime(timeStr: string): string | null {
  const s = timeStr.trim();
  if (!s || isNullToken(s)) return null;

  // ISO or space-separated datetime → extract time part
  const dtMatch = s.match(/^\d{4}[-/]\d{2}[-/]\d{2}[T ]([\d:]+)/);
  if (dtMatch) return dtMatch[1];

  // AM/PM → convert to 24h
  const ampmMatch = s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)$/i);
  if (ampmMatch) {
    let h = parseInt(ampmMatch[1], 10);
    const min = ampmMatch[2];
    const sec = ampmMatch[3] ?? "00";
    const period = ampmMatch[4].toUpperCase();
    if (period === "PM" && h < 12) h += 12;
    if (period === "AM" && h === 12) h = 0;
    return `${String(h).padStart(2, "0")}:${min}:${sec}`;
  }

  // Plain HH:MM or HH:MM:SS
  if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(s)) return s;

  return null;
}

/**
 * Combine an already-parsed ISO date + time string into a Unix timestamp (seconds).
 */
function dateTimeToTimestamp(isoDate: string, timeStr: string): number | null {
  const parsedTime = parseTime(timeStr);
  if (!parsedTime) return null;

  const dt = new Date(`${isoDate}T${parsedTime}Z`);
  if (isNaN(dt.getTime())) return null;
  return dt.getTime() / 1000;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface NonwearParseResult {
  matched: Array<{ fileId: number; entries: SensorNonwearEntry[] }>;
  totalRows: number;
  matchedRows: number;
  unmatchedRows: number;
  errors: string[];
}

/**
 * Parse a sensor nonwear CSV and match rows to local files.
 */
export function parseNonwearCsv(
  csvText: string,
  localFiles: FileRecord[],
): NonwearParseResult {
  const lines = stripBom(csvText).split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) {
    return { matched: [], totalRows: 0, matchedRows: 0, unmatchedRows: 0, errors: ["CSV has no data rows"] };
  }

  // Parse header (normalize spaces to underscores for alias matching)
  const headers = parseCsvLine(lines[0]).map((h) => h.toLowerCase().trim().replace(/\s+/g, "_"));
  const dateCol = headers.findIndex((h) => DATE_ALIASES.has(h));
  const startCol = headers.findIndex((h) => START_TIME_ALIASES.has(h));
  const endCol = headers.findIndex((h) => END_TIME_ALIASES.has(h));
  const filenameCol = headers.findIndex((h) => FILENAME_ALIASES.has(h));
  const pidCol = headers.findIndex((h) => PARTICIPANT_ID_ALIASES.has(h));

  if (dateCol < 0) return { matched: [], totalRows: 0, matchedRows: 0, unmatchedRows: 0, errors: ["No date column found"] };
  if (startCol < 0) return { matched: [], totalRows: 0, matchedRows: 0, unmatchedRows: 0, errors: ["No start_time column found"] };
  if (endCol < 0) return { matched: [], totalRows: 0, matchedRows: 0, unmatchedRows: 0, errors: ["No end_time column found"] };
  if (filenameCol < 0 && pidCol < 0) {
    return { matched: [], totalRows: 0, matchedRows: 0, unmatchedRows: 0, errors: ["No filename or participant_id column found for matching"] };
  }

  // Build file lookup index
  const { byFilename, byStem } = buildFileLookup(localFiles);

  // Parse rows — track periodIndex per file+date with a counter map
  const perFile = new Map<number, SensorNonwearEntry[]>();
  const periodCounters = new Map<string, number>(); // "fileId:date" → next index
  const errors: string[] = [];
  let matchedRows = 0;
  let unmatchedRows = 0;
  const totalRows = lines.length - 1;

  for (let i = 1; i < lines.length; i++) {
    const cols = parseCsvLine(lines[i]);
    const dateRaw = cols[dateCol] ?? "";
    const startRaw = cols[startCol] ?? "";
    const endRaw = cols[endCol] ?? "";

    if (!dateRaw || !startRaw || !endRaw) {
      errors.push(`Row ${i + 1}: missing date/start/end`);
      unmatchedRows++;
      continue;
    }

    // Parse date once, reuse for timestamps and entry
    const parsedDate = parseDate(dateRaw);
    if (!parsedDate) {
      errors.push(`Row ${i + 1}: could not parse date "${dateRaw}"`);
      unmatchedRows++;
      continue;
    }

    // Match to file
    let file: FileRecord | undefined;
    if (filenameCol >= 0 && cols[filenameCol]) {
      const rawFn = cols[filenameCol];
      file = byFilename.get(normalizeFilename(rawFn)) ?? byStem.get(filenameStem(rawFn));
    }
    if (!file && pidCol >= 0 && cols[pidCol]) {
      const pid = cols[pidCol].trim().toLowerCase();
      for (const f of localFiles) {
        if (filenameStem(f.filename).includes(pid)) {
          file = f;
          break;
        }
      }
    }

    if (!file || !file.id) {
      unmatchedRows++;
      continue;
    }

    // Parse timestamps using the already-parsed ISO date
    const startTs = dateTimeToTimestamp(parsedDate, startRaw);
    const endTs = dateTimeToTimestamp(parsedDate, endRaw);
    if (startTs == null || endTs == null) {
      errors.push(`Row ${i + 1}: could not parse date/time`);
      unmatchedRows++;
      continue;
    }

    // O(1) periodIndex via counter map
    const counterKey = `${file.id}:${parsedDate}`;
    const periodIndex = periodCounters.get(counterKey) ?? 0;
    periodCounters.set(counterKey, periodIndex + 1);

    const entries = perFile.get(file.id) ?? [];
    entries.push({
      fileId: file.id,
      analysisDate: parsedDate,
      startTimestamp: startTs,
      endTimestamp: endTs,
      periodIndex,
    });
    perFile.set(file.id, entries);
    matchedRows++;
  }

  const matched = Array.from(perFile.entries()).map(([fileId, entries]) => ({ fileId, entries }));
  return { matched, totalRows, matchedRows, unmatchedRows, errors };
}
