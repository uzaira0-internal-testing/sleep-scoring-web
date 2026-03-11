/**
 * Local diary CSV parser.
 *
 * Ports column alias detection and row parsing from backend (sleep_scoring_web/api/diary.py).
 * Local mode matches by normalized filename/stem against IndexedDB files.
 */
import type { DiaryEntryData } from "@/services/data-source";
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
} from "@/lib/csv-utils";

// ---------------------------------------------------------------------------
// Column aliases (mirrors backend _DESKTOP_COLUMN_ALIASES)
// ---------------------------------------------------------------------------

const COLUMN_ALIASES: Record<string, string[]> = {
  bed_time: ["in_bed_time", "bedtime", "in_bed_time_auto", "inbed_time", "bed_time", "time_to_bed"],
  wake_time: ["sleep_offset_time", "sleep_offset_time_auto", "wake_time", "waketime", "time_woke"],
  lights_out: ["sleep_onset_time", "sleep_onset_time_auto", "asleep_time", "lights_out", "lightsout"],
  got_up: ["got_up", "gotup", "out_of_bed"],
  sleep_quality: ["sleep_quality", "quality"],
  time_to_fall_asleep_minutes: ["time_to_fall_asleep", "sol", "sleep_latency"],
  number_of_awakenings: ["awakenings", "number_of_awakenings", "waso_count"],
  notes: ["notes", "comments"],
  nap_1_start: ["napstart_1_time", "nap_onset_time", "nap_onset_time_auto", "nap_1_start", "nap1_start"],
  nap_1_end: ["napend_1_time", "nap_offset_time", "nap_offset_time_auto", "nap_1_end", "nap1_end"],
  nap_2_start: ["nap_onset_time_2", "nap_2_start", "nap2_start"],
  nap_2_end: ["nap_offset_time_2", "nap_2_end", "nap2_end"],
  nap_3_start: ["nap_onset_time_3", "nap_3_start", "nap3_start"],
  nap_3_end: ["nap_offset_time_3", "nap_3_end", "nap3_end"],
  nonwear_1_start: ["nonwear_start_time", "nonwear_1_start", "nw_1_start"],
  nonwear_1_end: ["nonwear_end_time", "nonwear_1_end", "nw_1_end"],
  nonwear_1_reason: ["nonwear_reason", "nonwear_1_reason", "nw_1_reason"],
  nonwear_2_start: ["nonwear_start_time_2", "nonwear_2_start", "nw_2_start"],
  nonwear_2_end: ["nonwear_end_time_2", "nonwear_2_end", "nw_2_end"],
  nonwear_2_reason: ["nonwear_reason_2", "nonwear_2_reason", "nw_2_reason"],
  nonwear_3_start: ["nonwear_start_time_3", "nonwear_3_start", "nw_3_start"],
  nonwear_3_end: ["nonwear_end_time_3", "nonwear_3_end", "nw_3_end"],
  nonwear_3_reason: ["nonwear_reason_3", "nonwear_3_reason", "nw_3_reason"],
};

const NONWEAR_REASON_CODES: Record<string, string> = {
  "1": "Bath/Shower", "1.0": "Bath/Shower",
  "2": "Swimming", "2.0": "Swimming",
  "3": "Other", "3.0": "Other",
};

// ---------------------------------------------------------------------------
// Parsing helpers
// ---------------------------------------------------------------------------

function parseTimeField(value: string): string | null {
  const s = value.trim();
  if (!s || isNullToken(s)) return null;
  // HH:MM or HH:MM:SS → normalize to HH:MM
  if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(s)) {
    const parts = s.split(":");
    return `${parts[0].padStart(2, "0")}:${parts[1]}`;
  }
  return s;
}

function parseIntField(value: string): number | null {
  const s = value.trim();
  if (!s || isNullToken(s)) return null;
  const n = parseFloat(s);
  return isNaN(n) ? null : Math.round(n);
}

// ---------------------------------------------------------------------------
// Column name to DiaryEntryData field mapping
// ---------------------------------------------------------------------------

const SNAKE_TO_CAMEL: Record<string, keyof DiaryEntryData> = {
  bed_time: "bedTime",
  wake_time: "wakeTime",
  lights_out: "lightsOut",
  got_up: "gotUp",
  sleep_quality: "sleepQuality",
  time_to_fall_asleep_minutes: "timeToFallAsleepMinutes",
  number_of_awakenings: "numberOfAwakenings",
  notes: "notes",
  nap_1_start: "nap1Start",
  nap_1_end: "nap1End",
  nap_2_start: "nap2Start",
  nap_2_end: "nap2End",
  nap_3_start: "nap3Start",
  nap_3_end: "nap3End",
  nonwear_1_start: "nonwear1Start",
  nonwear_1_end: "nonwear1End",
  nonwear_1_reason: "nonwear1Reason",
  nonwear_2_start: "nonwear2Start",
  nonwear_2_end: "nonwear2End",
  nonwear_2_reason: "nonwear2Reason",
  nonwear_3_start: "nonwear3Start",
  nonwear_3_end: "nonwear3End",
  nonwear_3_reason: "nonwear3Reason",
};

const INT_FIELDS = new Set(["sleep_quality", "time_to_fall_asleep_minutes", "number_of_awakenings"]);
const REASON_FIELDS = new Set(["nonwear_1_reason", "nonwear_2_reason", "nonwear_3_reason"]);
const STR_FIELDS = new Set(["notes"]);

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface DiaryParseResult {
  matched: Array<{ fileId: number; entries: DiaryEntryData[] }>;
  totalRows: number;
  matchedRows: number;
  unmatchedRows: number;
  errors: string[];
}

export function parseDiaryCsv(
  csvText: string,
  localFiles: FileRecord[],
): DiaryParseResult {
  const lines = stripBom(csvText).split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) {
    return { matched: [], totalRows: 0, matchedRows: 0, unmatchedRows: 0, errors: ["CSV has no data rows"] };
  }

  // Normalize headers: lowercase, spaces → underscores
  const rawHeaders = parseCsvLine(lines[0]);
  const headers = rawHeaders.map((h) => h.toLowerCase().replace(/\s+/g, "_"));

  // Find date and filename columns
  const dateCol = headers.findIndex((h) => DATE_ALIASES.has(h));
  const filenameCol = headers.findIndex((h) => FILENAME_ALIASES.has(h));
  if (dateCol < 0) return { matched: [], totalRows: 0, matchedRows: 0, unmatchedRows: 0, errors: ["No date column found"] };
  if (filenameCol < 0) {
    return { matched: [], totalRows: 0, matchedRows: 0, unmatchedRows: 0, errors: ["No filename column found for matching"] };
  }

  // Build column index: for each diary field, find which CSV column provides it
  const fieldColMap = new Map<string, number>(); // snake_case field → column index
  for (const [dbField, aliases] of Object.entries(COLUMN_ALIASES)) {
    for (const alias of aliases) {
      const idx = headers.indexOf(alias);
      if (idx >= 0) {
        fieldColMap.set(dbField, idx);
        break;
      }
    }
  }

  // Build file lookup
  const { byFilename, byStem } = buildFileLookup(localFiles);

  // Parse rows
  const perFile = new Map<number, DiaryEntryData[]>();
  const errors: string[] = [];
  let matchedRows = 0;
  let unmatchedRows = 0;
  const totalRows = lines.length - 1;

  for (let i = 1; i < lines.length; i++) {
    const cols = parseCsvLine(lines[i]);
    const dateRaw = cols[dateCol] ?? "";
    const fnRaw = cols[filenameCol] ?? "";

    if (!dateRaw) { unmatchedRows++; continue; }

    const analysisDate = parseDate(dateRaw);
    if (!analysisDate) {
      errors.push(`Row ${i + 1}: could not parse date "${dateRaw}"`);
      unmatchedRows++;
      continue;
    }

    // Match file
    let file: FileRecord | undefined;
    if (fnRaw) {
      file = byFilename.get(normalizeFilename(fnRaw)) ?? byStem.get(filenameStem(fnRaw));
    }
    if (!file || !file.id) { unmatchedRows++; continue; }

    // Extract fields
    const entry: Partial<DiaryEntryData> = { fileId: file.id, analysisDate };
    for (const [dbField, colIdx] of fieldColMap) {
      const raw = cols[colIdx] ?? "";
      const camelField = SNAKE_TO_CAMEL[dbField];
      if (!camelField) continue;

      if (INT_FIELDS.has(dbField)) {
        (entry as Record<string, unknown>)[camelField] = parseIntField(raw);
      } else if (REASON_FIELDS.has(dbField)) {
        let val = isNullToken(raw) ? null : raw.trim();
        if (val && NONWEAR_REASON_CODES[val]) val = NONWEAR_REASON_CODES[val];
        (entry as Record<string, unknown>)[camelField] = val;
      } else if (STR_FIELDS.has(dbField)) {
        (entry as Record<string, unknown>)[camelField] = isNullToken(raw) ? null : raw.trim();
      } else {
        (entry as Record<string, unknown>)[camelField] = parseTimeField(raw);
      }
    }

    const entries = perFile.get(file.id) ?? [];
    entries.push(entry as DiaryEntryData);
    perFile.set(file.id, entries);
    matchedRows++;
  }

  const matched = Array.from(perFile.entries()).map(([fileId, entries]) => ({ fileId, entries }));
  return { matched, totalRows, matchedRows, unmatchedRows, errors };
}
