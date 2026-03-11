/**
 * Client-side CSV export for local files.
 * Generates the same column format as the backend export API.
 * Sleep and nonwear markers are exported as separate CSV files.
 */
import { getLocalFiles, getAllMarkersForFile, getAllActivityDaysForFile } from "@/db";
import { computePeriodMetrics } from "@/lib/sleep-metrics";
import { loadActivityForMetrics } from "@/services/local-data-helpers";

const NO_SLEEP_MARKER = "NO_SLEEP" as const;
const MANUAL_NONWEAR_MARKER = "Manual Nonwear" as const;

interface ExportRow {
  filename: string;
  studyDate: string;
  periodIndex: number;
  markerType: string;
  onsetTime: string | null;
  offsetTime: string | null;
  tst: number | null;
  sleepEfficiency: number | null;
  waso: number | null;
  sol: number | null;
  awakenings: number | null;
  isNoSleep: boolean;
  notes: string;
}

export interface LocalExportResult {
  sleepRows: ExportRow[];
  nonwearRows: ExportRow[];
}

function formatTimestamp(sec: number | null): string | null {
  if (sec == null) return null;
  return new Date(sec * 1000).toISOString();
}

/**
 * Generate separate sleep and nonwear CSV export rows for local files.
 */
export async function generateLocalExportRows(
  fileIds: number[],
  username: string,
): Promise<LocalExportResult> {
  const allFiles = await getLocalFiles();
  const targetFiles = fileIds.length > 0
    ? allFiles.filter((f) => f.id != null && fileIds.includes(f.id))
    : allFiles;

  const sleepRows: ExportRow[] = [];
  const nonwearRows: ExportRow[] = [];

  for (const file of targetFiles) {
    if (!file.id) continue;

    // Batch-load markers and activity in parallel (avoids N+1 and sequential await)
    const [markersMap, activityMap] = await Promise.all([
      getAllMarkersForFile(file.id, username),
      getAllActivityDaysForFile(file.id),
    ]);

    for (const date of file.availableDates) {
      const markers = markersMap.get(date);
      if (!markers) continue;

      if (markers.isNoSleep) {
        // Emit sentinel row for no-sleep dates
        sleepRows.push({
          filename: file.filename, studyDate: date, periodIndex: 0,
          markerType: NO_SLEEP_MARKER, onsetTime: null, offsetTime: null,
          tst: null, sleepEfficiency: null, waso: null, sol: null, awakenings: null,
          isNoSleep: true, notes: markers.notes,
        });

        // Also emit NAP markers on this no-sleep date
        if (markers.sleepMarkers.length > 0) {
          const { timestamps, algorithmResults } = loadActivityForMetrics(activityMap.get(date));
          for (const sm of markers.sleepMarkers) {
            let metrics: ReturnType<typeof computePeriodMetrics> = null;
            if (algorithmResults && timestamps.length > 0 && sm.onsetTimestamp && sm.offsetTimestamp) {
              metrics = computePeriodMetrics(algorithmResults, timestamps, sm.onsetTimestamp, sm.offsetTimestamp);
            }
            sleepRows.push({
              filename: file.filename, studyDate: date, periodIndex: sm.markerIndex,
              markerType: sm.markerType, onsetTime: formatTimestamp(sm.onsetTimestamp),
              offsetTime: formatTimestamp(sm.offsetTimestamp),
              tst: metrics?.totalSleepTimeMinutes ?? null,
              sleepEfficiency: metrics?.sleepEfficiency ?? null,
              waso: metrics?.wasoMinutes ?? null,
              sol: metrics?.sleepOnsetLatencyMinutes ?? null,
              awakenings: metrics?.numberOfAwakenings ?? null,
              isNoSleep: true, notes: markers.notes,
            });
          }
        }
        // Don't continue — let nonwear loop below run for no-sleep dates too
      } else {
        const { timestamps, algorithmResults } = loadActivityForMetrics(activityMap.get(date));

        for (const sm of markers.sleepMarkers) {
          let metrics: ReturnType<typeof computePeriodMetrics> = null;
          if (algorithmResults && timestamps.length > 0 && sm.onsetTimestamp && sm.offsetTimestamp) {
            metrics = computePeriodMetrics(algorithmResults, timestamps, sm.onsetTimestamp, sm.offsetTimestamp);
          }

          sleepRows.push({
            filename: file.filename, studyDate: date, periodIndex: sm.markerIndex,
            markerType: sm.markerType, onsetTime: formatTimestamp(sm.onsetTimestamp),
            offsetTime: formatTimestamp(sm.offsetTimestamp),
            tst: metrics?.totalSleepTimeMinutes ?? null,
            sleepEfficiency: metrics?.sleepEfficiency ?? null,
            waso: metrics?.wasoMinutes ?? null,
            sol: metrics?.sleepOnsetLatencyMinutes ?? null,
            awakenings: metrics?.numberOfAwakenings ?? null,
            isNoSleep: false, notes: markers.notes,
          });
        }
      }

      // Nonwear markers go to separate list
      for (const nw of markers.nonwearMarkers) {
        nonwearRows.push({
          filename: file.filename, studyDate: date, periodIndex: nw.markerIndex ?? 0,
          markerType: MANUAL_NONWEAR_MARKER,
          onsetTime: formatTimestamp(nw.startTimestamp),
          offsetTime: formatTimestamp(nw.endTimestamp),
          tst: null, sleepEfficiency: null, waso: null, sol: null, awakenings: null,
          isNoSleep: false, notes: markers.notes,
        });
      }
    }
  }

  return { sleepRows, nonwearRows };
}

/** Escape a CSV field value (RFC 4180). */
function escapeCsvField(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

/**
 * Convert export rows to CSV string.
 */
export function rowsToCsv(rows: ExportRow[]): string {
  const headers = [
    "Filename", "Study Date", "Period Index", "Marker Type",
    "Onset Time", "Offset Time", "Total Sleep Time (min)", "Sleep Efficiency (%)",
    "WASO (min)", "Sleep Onset Latency (min)", "Number of Awakenings",
    "Is No Sleep", "Notes",
  ];
  const lines = [headers.join(",")];

  for (const row of rows) {
    const values = [
      escapeCsvField(row.filename),
      row.studyDate,
      String(row.periodIndex),
      row.markerType,
      row.onsetTime ?? "",
      row.offsetTime ?? "",
      row.tst != null ? row.tst.toFixed(1) : "",
      row.sleepEfficiency != null ? row.sleepEfficiency.toFixed(1) : "",
      row.waso != null ? row.waso.toFixed(1) : "",
      row.sol != null ? row.sol.toFixed(1) : "",
      row.awakenings != null ? String(row.awakenings) : "",
      row.isNoSleep ? "TRUE" : "FALSE",
      escapeCsvField(row.notes),
    ];
    lines.push(values.join(","));
  }

  return lines.join("\n");
}

/** Trigger a browser download of a Blob. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Trigger a browser download of a CSV string. */
export function downloadCsv(csv: string, filename: string): void {
  downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8;" }), filename);
}

/** Trigger browser downloads for multiple CSV files sequentially. */
export function downloadMultipleCsvs(
  files: Array<{ csv: string; filename: string }>,
): void {
  for (const file of files) {
    downloadCsv(file.csv, file.filename);
  }
}
