/**
 * Client-side analysis summary computation from IndexedDB data.
 * Produces the same shape as the backend /analysis/summary response.
 */
import { getLocalFiles, getAllMarkersForFile, getAllActivityDaysForFile } from "@/db";
import { computePeriodMetrics } from "@/lib/sleep-metrics";
import { loadActivityForMetrics } from "@/services/local-data-helpers";
import { MARKER_TYPES } from "@/api/types";

interface FileSummary {
  file_id: number;
  filename: string;
  participant_id: string | null;
  total_dates: number;
  scored_dates: number;
  has_diary: boolean;
}

interface AggregateMetrics {
  mean_tst_minutes: number | null;
  mean_sleep_efficiency: number | null;
  mean_waso_minutes: number | null;
  mean_sleep_onset_latency: number | null;
  total_sleep_periods: number;
  total_nap_periods: number;
}

export interface LocalAnalysisSummary {
  total_files: number;
  total_dates: number;
  scored_dates: number;
  files_summary: FileSummary[];
  aggregate_metrics: AggregateMetrics;
}

export async function computeLocalAnalysis(username: string): Promise<LocalAnalysisSummary> {
  const files = await getLocalFiles();
  if (files.length === 0) {
    return {
      total_files: 0, total_dates: 0, scored_dates: 0, files_summary: [],
      aggregate_metrics: { mean_tst_minutes: null, mean_sleep_efficiency: null, mean_waso_minutes: null, mean_sleep_onset_latency: null, total_sleep_periods: 0, total_nap_periods: 0 },
    };
  }

  const filesSummary: FileSummary[] = [];
  let totalDates = 0;
  let scoredDates = 0;
  let totalSleepPeriods = 0;
  let totalNapPeriods = 0;
  const allTst: number[] = [];
  const allSe: number[] = [];
  const allWaso: number[] = [];
  const allSol: number[] = [];

  for (const file of files) {
    if (!file.id) continue;

    // Batch-load markers and activity in parallel (avoids N+1 and sequential await)
    const [markersMap, activityMap] = await Promise.all([
      getAllMarkersForFile(file.id, username),
      getAllActivityDaysForFile(file.id),
    ]);
    let fileScoredDates = 0;

    for (const date of file.availableDates) {
      totalDates++;
      const markers = markersMap.get(date);
      if (!markers || (markers.sleepMarkers.length === 0 && !markers.isNoSleep)) continue;

      fileScoredDates++;
      scoredDates++;
      // Skip metric computation only if there are no sleep markers at all.
      // No-sleep dates can still have NAP markers that need metrics.
      if (markers.sleepMarkers.length === 0) continue;

      const { timestamps, algorithmResults } = loadActivityForMetrics(activityMap.get(date));

      for (const sm of markers.sleepMarkers) {
        if (sm.markerType === MARKER_TYPES.NAP) totalNapPeriods++;
        else totalSleepPeriods++;

        if (algorithmResults && timestamps.length > 0 && sm.onsetTimestamp && sm.offsetTimestamp) {
          const m = computePeriodMetrics(algorithmResults, timestamps, sm.onsetTimestamp, sm.offsetTimestamp);
          if (m) {
            allTst.push(m.totalSleepTimeMinutes);
            allSe.push(m.sleepEfficiency);
            allWaso.push(m.wasoMinutes);
            allSol.push(m.sleepOnsetLatencyMinutes);
          }
        }
      }
    }

    filesSummary.push({
      file_id: file.id,
      filename: file.filename,
      participant_id: null,
      total_dates: file.availableDates.length,
      scored_dates: fileScoredDates,
      has_diary: false,
    });
  }

  const mean = (arr: number[]) => arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : null;

  return {
    total_files: files.length,
    total_dates: totalDates,
    scored_dates: scoredDates,
    files_summary: filesSummary,
    aggregate_metrics: {
      mean_tst_minutes: mean(allTst),
      mean_sleep_efficiency: mean(allSe),
      mean_waso_minutes: mean(allWaso),
      mean_sleep_onset_latency: mean(allSol),
      total_sleep_periods: totalSleepPeriods,
      total_nap_periods: totalNapPeriods,
    },
  };
}
