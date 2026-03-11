import type { MarkerType, DateStatus } from "@/api/types";
import { getApiBase, fetchWithAuth } from "@/api/client";
import * as localDb from "@/db";
import type { SleepMarkerJson, NonwearMarkerJson, ActivityDay } from "@/db/schema";
import { runAutoScoring, placeNonwearMarkers } from "@/services/marker-placement";
import { computePreComplexity, computePostComplexity } from "@/services/complexity";
import { getDetectionRuleParams } from "@/constants/options";

// =============================================================================
// Diary field extraction helpers (used by LocalDataSource)
// =============================================================================

function extractNaps(diary: DiaryEntryData): Array<[string | null, string | null]> {
  const naps: Array<[string | null, string | null]> = [];
  if (diary.nap1Start || diary.nap1End) naps.push([diary.nap1Start ?? null, diary.nap1End ?? null]);
  if (diary.nap2Start || diary.nap2End) naps.push([diary.nap2Start ?? null, diary.nap2End ?? null]);
  if (diary.nap3Start || diary.nap3End) naps.push([diary.nap3Start ?? null, diary.nap3End ?? null]);
  return naps;
}

function extractNonwear(diary: DiaryEntryData): Array<[string | null, string | null]> {
  const nw: Array<[string | null, string | null]> = [];
  if (diary.nonwear1Start || diary.nonwear1End) nw.push([diary.nonwear1Start ?? null, diary.nonwear1End ?? null]);
  if (diary.nonwear2Start || diary.nonwear2End) nw.push([diary.nonwear2Start ?? null, diary.nonwear2End ?? null]);
  if (diary.nonwear3Start || diary.nonwear3End) nw.push([diary.nonwear3Start ?? null, diary.nonwear3End ?? null]);
  return nw;
}

/**
 * Unified activity data structure returned by both data sources.
 */
export interface ActivityData {
  timestamps: number[];
  axisX: number[];
  axisY: number[];
  axisZ: number[];
  vectorMagnitude: number[];
  algorithmResults: number[] | null;
  nonwearResults: number[] | null;
  viewStart: number | null;
  viewEnd: number | null;
  sensorNonwearPeriods: Array<{ startTimestamp: number; endTimestamp: number }>;
}

/**
 * Unified marker data structure.
 */
export interface MarkerData {
  sleepMarkers: Array<{
    onsetTimestamp: number | null;
    offsetTimestamp: number | null;
    markerIndex: number;
    markerType: MarkerType;
  }>;
  nonwearMarkers: Array<{
    startTimestamp: number | null;
    endTimestamp: number | null;
    markerIndex: number;
  }>;
  isNoSleep: boolean;
  notes: string;
  needsConsensus?: boolean;
}

/**
 * Diary entry data structure for auto-score/complexity.
 */
export interface DiaryEntryData {
  fileId: number;
  analysisDate: string;
  bedTime?: string | null;
  wakeTime?: string | null;
  lightsOut?: string | null;
  gotUp?: string | null;
  sleepQuality?: number | null;
  timeToFallAsleepMinutes?: number | null;
  numberOfAwakenings?: number | null;
  notes?: string | null;
  nap1Start?: string | null;
  nap1End?: string | null;
  nap2Start?: string | null;
  nap2End?: string | null;
  nap3Start?: string | null;
  nap3End?: string | null;
  nonwear1Start?: string | null;
  nonwear1End?: string | null;
  nonwear1Reason?: string | null;
  nonwear2Start?: string | null;
  nonwear2End?: string | null;
  nonwear2Reason?: string | null;
  nonwear3Start?: string | null;
  nonwear3End?: string | null;
  nonwear3Reason?: string | null;
}

/**
 * File info for listing.
 */
export interface FileInfo {
  id: number;
  filename: string;
  source: "local" | "server";
  status?: string;
  available_dates?: string[];
}

/**
 * Auto-score result — canonical shape used by both data sources.
 */
export interface AutoScoreResult {
  sleep_markers: Array<{ onset_timestamp: number; offset_timestamp: number; marker_type: string; marker_index: number }>;
  nap_markers: Array<{ onset_timestamp: number; offset_timestamp: number; marker_type: string; marker_index: number }>;
  notes: string[];
}

/**
 * Auto-nonwear result — canonical shape used by both data sources.
 */
export interface AutoNonwearResult {
  nonwear_markers: Array<{ start_timestamp: number; end_timestamp: number; marker_index: number }>;
  notes: string[];
}

/**
 * Options for auto-score.
 */
export interface AutoScoreOptions {
  algorithm: string;
  detectionRule: string;
}

/**
 * Options for auto-nonwear.
 * `existingSleepMarkers` are onset/offset pairs in Unix seconds.
 */
export interface AutoNonwearOptions {
  threshold: number;
  existingSleepMarkers: Array<[number, number]>;
}

/**
 * Adjacent day markers for continuity display on the activity plot.
 */
export interface AdjacentMarkersData {
  previous_day_markers: Array<{ onset_timestamp: number | null; offset_timestamp: number | null; marker_index: number }>;
  next_day_markers: Array<{ onset_timestamp: number | null; offset_timestamp: number | null; marker_index: number }>;
  previous_date: string | null;
  next_date: string | null;
}

/**
 * Data source interface for dual-mode operation.
 * Mode is per-file: FileRecord.source determines which DataSource handles it.
 */
export interface DataSource {
  loadActivityData(fileId: number, date: string, options?: { algorithm?: string; viewHours?: number }): Promise<ActivityData>;
  loadMarkers(fileId: number, date: string, username: string): Promise<MarkerData | null>;
  saveMarkers(fileId: number, date: string, username: string, data: MarkerData): Promise<void>;
  listFiles(): Promise<FileInfo[]>;
  listDates(fileId: number): Promise<string[]>;
  getDiaryEntry(fileId: number, date: string): Promise<DiaryEntryData | null>;
  listDiaryEntries(fileId: number): Promise<DiaryEntryData[]>;
  autoScore(fileId: number, date: string, options: AutoScoreOptions): Promise<AutoScoreResult>;
  autoNonwear(fileId: number, date: string, options: AutoNonwearOptions): Promise<AutoNonwearResult>;
  listDatesStatus(fileId: number, dates: string[], username: string): Promise<DateStatus[]>;
  loadAdjacentMarkers(fileId: number, date: string, username: string): Promise<AdjacentMarkersData | null>;
}

/**
 * Server-backed data source (existing behavior).
 */
export class ServerDataSource implements DataSource {
  private sitePassword: string | null;
  private username: string;

  constructor(
    sitePassword: string | null,
    username: string,
  ) {
    this.sitePassword = sitePassword;
    this.username = username;
  }

  async loadActivityData(fileId: number, date: string, options?: { algorithm?: string; viewHours?: number }): Promise<ActivityData> {
    const params = new URLSearchParams();
    if (options?.viewHours) params.set("view_hours", String(options.viewHours));
    if (options?.algorithm) params.set("algorithm", options.algorithm);
    const qs = params.toString();
    const url = `${getApiBase()}/activity/${fileId}/${date}/score${qs ? `?${qs}` : ""}`;
    const response = await fetch(url, {
      headers: this.getHeaders(),
    });
    if (!response.ok) throw new Error(`Failed to load activity: ${response.status}`);
    const data = await response.json();
    // Normalize: API wraps columnar data in `data` field (ActivityDataResponse.data)
    const d = data.data ?? data;
    return {
      timestamps: d.timestamps ?? [],
      axisX: d.axis_x ?? [],
      axisY: d.axis_y ?? [],
      axisZ: d.axis_z ?? [],
      vectorMagnitude: d.vector_magnitude ?? [],
      algorithmResults: data.algorithm_results ?? null,
      nonwearResults: data.nonwear_results ?? null,
      viewStart: data.view_start ?? null,
      viewEnd: data.view_end ?? null,
      sensorNonwearPeriods: (data.sensor_nonwear_periods ?? []).map((p: { start_timestamp: number; end_timestamp: number }) => ({
        startTimestamp: p.start_timestamp,
        endTimestamp: p.end_timestamp,
      })),
    };
  }

  async loadMarkers(fileId: number, date: string, username: string): Promise<MarkerData | null> {
    const response = await fetch(`${getApiBase()}/markers/${fileId}/${date}`, {
      headers: {
        ...this.getHeaders(),
        "X-Username": username || "anonymous",
      },
    });
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`Failed to load markers: ${response.status}`);
    const data = await response.json();
    return {
      sleepMarkers: (data.sleep_markers ?? []).map((m: Record<string, unknown>) => ({
        onsetTimestamp: (m.onset_timestamp as number | null),
        offsetTimestamp: (m.offset_timestamp as number | null),
        markerIndex: m.marker_index as number,
        markerType: m.marker_type as MarkerType,
      })),
      nonwearMarkers: (data.nonwear_markers ?? []).map((m: Record<string, unknown>) => ({
        startTimestamp: (m.start_timestamp as number | null),
        endTimestamp: (m.end_timestamp as number | null),
        markerIndex: m.marker_index as number,
      })),
      isNoSleep: data.is_no_sleep ?? false,
      needsConsensus: data.needs_consensus ?? false,
      notes: data.notes ?? "",
    };
  }

  async saveMarkers(fileId: number, date: string, username: string, data: MarkerData): Promise<void> {
    const payload: Record<string, unknown> = {
      sleep_markers: data.sleepMarkers.map((m) => ({
        onset_timestamp: m.onsetTimestamp,
        offset_timestamp: m.offsetTimestamp,
        marker_index: m.markerIndex,
        marker_type: m.markerType,
      })),
      nonwear_markers: data.nonwearMarkers.map((m) => ({
        start_timestamp: m.startTimestamp,
        end_timestamp: m.endTimestamp,
        marker_index: m.markerIndex,
      })),
      is_no_sleep: data.isNoSleep,
      notes: data.notes,
      needs_consensus: data.needsConsensus ?? false,
    };

    const response = await fetch(`${getApiBase()}/markers/${fileId}/${date}`, {
      method: "PUT",
      headers: {
        ...this.getHeaders(),
        "Content-Type": "application/json",
        "X-Username": username || "anonymous",
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`Failed to save markers: ${response.status}`);
  }

  async listFiles(): Promise<FileInfo[]> {
    const response = await fetch(`${getApiBase()}/files`, {
      headers: this.getHeaders(),
    });
    if (!response.ok) return [];
    const data = await response.json();
    return ((data?.items ?? data) as Record<string, unknown>[]).map((f: Record<string, unknown>) => ({
      id: f.id as number,
      filename: f.filename as string,
      source: "server" as const,
      status: f.status as string,
    }));
  }

  async listDates(fileId: number): Promise<string[]> {
    const response = await fetch(`${getApiBase()}/files/${fileId}/dates`, {
      headers: this.getHeaders(),
    });
    if (!response.ok) return [];
    const data = await response.json();
    return data ?? [];
  }

  async listDiaryEntries(fileId: number): Promise<DiaryEntryData[]> {
    const response = await fetch(`${getApiBase()}/diary/${fileId}`, {
      headers: this.getHeaders(),
    });
    if (!response.ok) return [];
    const entries = await response.json();
    return (entries ?? []).map((entry: Record<string, unknown>) => this.mapDiaryEntry(fileId, entry));
  }

  async getDiaryEntry(fileId: number, date: string): Promise<DiaryEntryData | null> {
    const all = await this.listDiaryEntries(fileId);
    return all.find((e) => e.analysisDate === date) ?? null;
  }

  async autoScore(fileId: number, date: string, options: AutoScoreOptions): Promise<AutoScoreResult> {
    const rule = getDetectionRuleParams(options.detectionRule);
    const params = new URLSearchParams({
      algorithm: options.algorithm,
      onset_epochs: String(rule.onsetN),
      offset_minutes: String(rule.offsetN),
      detection_rule: options.detectionRule,
    });
    return fetchWithAuth<AutoScoreResult>(
      `${getApiBase()}/markers/${fileId}/${date}/auto-score?${params}`,
      { method: "POST" },
    );
  }

  async autoNonwear(fileId: number, date: string, options: AutoNonwearOptions): Promise<AutoNonwearResult> {
    // Server handles sleep-marker overlap checking internally; existingSleepMarkers unused here.
    const params = new URLSearchParams({ threshold: String(options.threshold) });
    return fetchWithAuth<AutoNonwearResult>(
      `${getApiBase()}/markers/${fileId}/${date}/auto-nonwear?${params}`,
      { method: "POST" },
    );
  }

  async listDatesStatus(fileId: number, _dates: string[], _username: string): Promise<DateStatus[]> {
    return fetchWithAuth<DateStatus[]>(`${getApiBase()}/files/${fileId}/dates/status`);
  }

  private mapDiaryEntry(fileId: number, entry: Record<string, unknown>): DiaryEntryData {
    return {
      fileId,
      analysisDate: String(entry.analysis_date),
      bedTime: (entry.bed_time as string) ?? null,
      wakeTime: (entry.wake_time as string) ?? null,
      lightsOut: (entry.lights_out as string) ?? null,
      gotUp: (entry.got_up as string) ?? null,
      sleepQuality: (entry.sleep_quality as number) ?? null,
      timeToFallAsleepMinutes: (entry.time_to_fall_asleep_minutes as number) ?? null,
      numberOfAwakenings: (entry.number_of_awakenings as number) ?? null,
      notes: (entry.notes as string) ?? null,
      nap1Start: (entry.nap_1_start as string) ?? null,
      nap1End: (entry.nap_1_end as string) ?? null,
      nap2Start: (entry.nap_2_start as string) ?? null,
      nap2End: (entry.nap_2_end as string) ?? null,
      nap3Start: (entry.nap_3_start as string) ?? null,
      nap3End: (entry.nap_3_end as string) ?? null,
      nonwear1Start: (entry.nonwear_1_start as string) ?? null,
      nonwear1End: (entry.nonwear_1_end as string) ?? null,
      nonwear1Reason: (entry.nonwear_1_reason as string) ?? null,
      nonwear2Start: (entry.nonwear_2_start as string) ?? null,
      nonwear2End: (entry.nonwear_2_end as string) ?? null,
      nonwear2Reason: (entry.nonwear_2_reason as string) ?? null,
      nonwear3Start: (entry.nonwear_3_start as string) ?? null,
      nonwear3End: (entry.nonwear_3_end as string) ?? null,
      nonwear3Reason: (entry.nonwear_3_reason as string) ?? null,
    };
  }

  async loadAdjacentMarkers(fileId: number, date: string, username: string): Promise<AdjacentMarkersData | null> {
    const response = await fetch(
      `${getApiBase()}/markers/${fileId}/${date}/adjacent`,
      { headers: { ...this.getHeaders(), "X-Username": username || "anonymous" } },
    );
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`Failed to load adjacent markers: ${response.status}`);
    return response.json() as Promise<AdjacentMarkersData>;
  }

  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {};
    if (this.sitePassword) headers["X-Site-Password"] = this.sitePassword;
    if (this.username) headers["X-Username"] = this.username;
    return headers;
  }
}

// =============================================================================
// ActivityDay unpacking helper (avoids repeated ArrayBuffer-to-array conversion)
// =============================================================================

interface UnpackedActivityDay {
  timestamps: number[];
  axisY: number[];
  vectorMagnitude: number[];
  sleepScores: number[];
  nonwearResults: number[] | null;
}

function unpackActivityDay(
  day: ActivityDay,
  preferredAlgorithm?: string,
): UnpackedActivityDay {
  // IndexedDB stores timestamps in seconds (converted from WASM ms at storage time).
  const timestamps = Array.from(new Float64Array(day.timestamps));
  const axisY = Array.from(new Float64Array(day.axisY));
  const vectorMagnitude = Array.from(new Float64Array(day.vectorMagnitude));

  // Validate array lengths match — mismatched lengths indicate corrupt data
  if (timestamps.length !== axisY.length || timestamps.length !== vectorMagnitude.length) {
    console.error(
      `[unpackActivityDay] Array length mismatch: timestamps=${timestamps.length} axisY=${axisY.length} vectorMagnitude=${vectorMagnitude.length}`,
    );
    throw new Error("Corrupt activity data: array lengths do not match");
  }

  const algoKeys = Object.keys(day.algorithmResults);
  const algoKey = (preferredAlgorithm && day.algorithmResults[preferredAlgorithm])
    ? preferredAlgorithm
    : algoKeys[0] ?? null;
  const sleepScores = algoKey
    ? Array.from(new Uint8Array(day.algorithmResults[algoKey]))
    : [];

  const nonwearResults = day.nonwearResults
    ? Array.from(new Uint8Array(day.nonwearResults))
    : null;

  return { timestamps, axisY, vectorMagnitude, sleepScores, nonwearResults };
}

/** Get the next calendar date as YYYY-MM-DD string. */
function getNextDate(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

/**
 * Local-first data source backed by IndexedDB + WASM.
 */
export class LocalDataSource implements DataSource {
  async loadActivityData(fileId: number, date: string, options?: { algorithm?: string; viewHours?: number }): Promise<ActivityData> {
    const day = await localDb.getActivityDay(fileId, date);
    if (!day) {
      throw new Error(`No activity data found for fileId=${fileId} date=${date}. File may not be processed yet.`);
    }

    const unpacked = unpackActivityDay(day, options?.algorithm);

    // For 48h view, append next day's data
    if (options?.viewHours === 48) {
      const nextDate = getNextDate(date);
      const nextDay = await localDb.getActivityDay(fileId, nextDate);
      if (nextDay) {
        const nextUnpacked = unpackActivityDay(nextDay, options?.algorithm);
        // Capture lengths before merging timestamps
        const day1Len = unpacked.timestamps.length;
        const day2Len = nextUnpacked.timestamps.length;
        unpacked.timestamps.push(...nextUnpacked.timestamps);
        unpacked.axisY.push(...nextUnpacked.axisY);
        unpacked.vectorMagnitude.push(...nextUnpacked.vectorMagnitude);
        // Pad with zeros if one day has scores/nonwear and the other doesn't,
        // so arrays stay aligned with timestamps across the full 48h span.
        if (unpacked.sleepScores.length > 0 || nextUnpacked.sleepScores.length > 0) {
          if (unpacked.sleepScores.length === 0) unpacked.sleepScores = new Array(day1Len).fill(0);
          unpacked.sleepScores.push(...(nextUnpacked.sleepScores.length > 0 ? nextUnpacked.sleepScores : new Array(day2Len).fill(0)));
        }
        if (unpacked.nonwearResults || nextUnpacked.nonwearResults) {
          if (!unpacked.nonwearResults) unpacked.nonwearResults = new Array(day1Len).fill(0);
          unpacked.nonwearResults.push(...(nextUnpacked.nonwearResults ?? new Array(day2Len).fill(0)));
        }
      }
    }

    // Compute view bounds from timestamp array
    const viewStart = unpacked.timestamps.length > 0 ? unpacked.timestamps[0] : null;
    const viewEnd = unpacked.timestamps.length > 0 ? unpacked.timestamps[unpacked.timestamps.length - 1] : null;

    // Load sensor nonwear from IndexedDB (timestamps in seconds, matching store convention)
    const sensorNonwearPeriods = (await localDb.getSensorNonwear(fileId, date)).map((p) => ({
      startTimestamp: p.startTimestamp,
      endTimestamp: p.endTimestamp,
    }));

    return {
      timestamps: unpacked.timestamps,
      axisX: [],  // Not stored in IndexedDB for epoched data
      axisY: unpacked.axisY,
      axisZ: [],  // Not stored in IndexedDB for epoched data
      vectorMagnitude: unpacked.vectorMagnitude,
      algorithmResults: unpacked.sleepScores.length > 0 ? unpacked.sleepScores : null,
      nonwearResults: unpacked.nonwearResults,
      viewStart,
      viewEnd,
      sensorNonwearPeriods,
    };
  }

  async loadMarkers(fileId: number, date: string, username: string): Promise<MarkerData | null> {
    const record = await localDb.getMarkers(fileId, date, username);
    if (!record) return null;
    return {
      sleepMarkers: record.sleepMarkers,
      nonwearMarkers: record.nonwearMarkers,
      isNoSleep: record.isNoSleep,
      notes: record.notes,
      needsConsensus: record.needsConsensus ?? false,
    };
  }

  async saveMarkers(fileId: number, date: string, username: string, data: MarkerData): Promise<void> {
    await localDb.saveMarkers(
      fileId,
      date,
      username,
      data.sleepMarkers as SleepMarkerJson[],
      data.nonwearMarkers as NonwearMarkerJson[],
      data.isNoSleep,
      data.notes,
      data.needsConsensus ?? false,
    );
  }

  async listFiles(): Promise<FileInfo[]> {
    const files = await localDb.getLocalFiles();
    return files.map((f) => ({
      id: f.id!,
      filename: f.filename,
      source: "local" as const,
      available_dates: f.availableDates,
    }));
  }

  async listDates(fileId: number): Promise<string[]> {
    return localDb.getAvailableDates(fileId);
  }

  async getDiaryEntry(fileId: number, date: string): Promise<DiaryEntryData | null> {
    return localDb.getDiaryEntry(fileId, date);
  }

  async listDiaryEntries(fileId: number): Promise<DiaryEntryData[]> {
    return localDb.getDiaryEntries(fileId);
  }

  async autoScore(fileId: number, date: string, options: AutoScoreOptions): Promise<AutoScoreResult> {
    const day = await localDb.getActivityDay(fileId, date);
    if (!day) {
      return { sleep_markers: [], nap_markers: [], notes: ["No activity data in IndexedDB"] };
    }

    const { timestamps, axisY, sleepScores, nonwearResults } = unpackActivityDay(day, options.algorithm);

    if (sleepScores.length === 0) {
      return { sleep_markers: [], nap_markers: [], notes: ["No algorithm results available"] };
    }

    const diary = await localDb.getDiaryEntry(fileId, date);
    const rule = getDetectionRuleParams(options.detectionRule);

    return runAutoScoring({
      timestamps,
      activityCounts: axisY,
      sleepScores,
      choiNonwear: nonwearResults,
      diaryBedTime: diary?.bedTime ?? null,
      diaryOnsetTime: diary?.lightsOut ?? null,
      diaryWakeTime: diary?.wakeTime ?? null,
      diaryNaps: diary ? extractNaps(diary) : null,
      diaryNonwear: diary ? extractNonwear(diary) : null,
      analysisDate: date,
      onsetMinConsecutiveSleep: rule.onsetN,
      offsetMinConsecutiveMinutes: rule.offsetN,
    });
  }

  async autoNonwear(fileId: number, date: string, options: AutoNonwearOptions): Promise<AutoNonwearResult> {
    const day = await localDb.getActivityDay(fileId, date);
    if (!day) {
      return { nonwear_markers: [], notes: ["No activity data"] };
    }

    const { timestamps, axisY, nonwearResults } = unpackActivityDay(day);

    const diary = await localDb.getDiaryEntry(fileId, date);
    const diaryNonwear = diary ? extractNonwear(diary) : [];

    const sensorPeriods = await localDb.getSensorNonwear(fileId, date);
    const sensorNonwearPeriods: Array<[number, number]> = sensorPeriods.map((p) => [
      p.startTimestamp,
      p.endTimestamp,
    ]);

    // Store already uses seconds — pass through directly
    const existingSleepMarkersSec: Array<[number, number]> = options.existingSleepMarkers;

    const result = placeNonwearMarkers({
      timestamps,
      activityCounts: axisY,
      diaryNonwear,
      choiNonwear: nonwearResults,
      sensorNonwearPeriods,
      existingSleepMarkers: existingSleepMarkersSec,
      analysisDate: date,
      threshold: options.threshold,
    });

    return {
      nonwear_markers: result.nonwear_markers,
      notes: result.notes,
    };
  }

  async listDatesStatus(fileId: number, dates: string[], username: string): Promise<DateStatus[]> {
    // Bulk-load all data for the file (5 queries total instead of N per date)
    const [markersMap, daysMap, diaryEntries, sensorNonwearAll, studySettings] = await Promise.all([
      localDb.getAllMarkersForFile(fileId, username),
      localDb.getAllActivityDaysForFile(fileId),
      localDb.getDiaryEntries(fileId),
      localDb.getSensorNonwearForFile(fileId),
      localDb.getLocalStudySettings(),
    ]);

    // Index diary and sensor nonwear by date for O(1) lookup
    const diaryMap = new Map(diaryEntries.map((d) => [d.analysisDate, d]));
    const sensorByDate = new Map<string, Array<[number, number]>>();
    for (const p of sensorNonwearAll) {
      const key = p.analysisDate;
      if (!sensorByDate.has(key)) sensorByDate.set(key, []);
      sensorByDate.get(key)!.push([p.startTimestamp, p.endTimestamp]);
    }

    // Parse night hours from study settings (default 21:00-09:00)
    const rawStart = studySettings?.nightStartHour
      ? parseInt(studySettings.nightStartHour.split(":")[0], 10) : 21;
    const nightStartHour = Number.isNaN(rawStart) ? (console.warn(`[data-source] Invalid nightStartHour "${studySettings?.nightStartHour}", using default 21`), 21) : rawStart;
    const rawEnd = studySettings?.nightEndHour
      ? parseInt(studySettings.nightEndHour.split(":")[0], 10) : 9;
    const nightEndHour = Number.isNaN(rawEnd) ? (console.warn(`[data-source] Invalid nightEndHour "${studySettings?.nightEndHour}", using default 9`), 9) : rawEnd;

    return dates.map((date) => {
      const markers = markersMap.get(date);
      const day = daysMap.get(date);
      const diary = diaryMap.get(date);

      let complexityPre: number | null = null;
      let complexityPost: number | null = null;

      if (day) {
        const { timestamps, axisY, sleepScores, nonwearResults } = unpackActivityDay(day);
        const choiNonwear = nonwearResults ?? [];

        const sensorNonwearPeriods = sensorByDate.get(date) ?? [];

        const napCount = [diary?.nap1Start, diary?.nap2Start, diary?.nap3Start].filter(Boolean).length;
        const diaryNonwearTimes: Array<[string, string]> = diary
          ? extractNonwear(diary)
              .filter((p): p is [string, string] => p[0] != null && p[1] != null)
          : [];

        if (sleepScores.length > 0) {
          const pre = computePreComplexity({
            timestamps,
            activityCounts: axisY,
            sleepScores,
            choiNonwear,
            diaryOnsetTime: diary?.lightsOut ?? null,
            diaryWakeTime: diary?.wakeTime ?? null,
            diaryNapCount: napCount,
            analysisDate: date,
            sensorNonwearPeriods,
            ...(diaryNonwearTimes.length > 0 ? { diaryNonwearTimes } : {}),
            nightStartHour,
            nightEndHour,
          });
          complexityPre = pre.score;

          if (markers && complexityPre >= 0) {
            // MarkerRecord.sleepMarkers uses camelCase (onsetTimestamp/offsetTimestamp)
            // Both markers and timestamps are in seconds
            const sleepMarkerPairs: Array<[number, number]> = markers.sleepMarkers
              .filter((m) => m.onsetTimestamp != null && m.offsetTimestamp != null)
              .map((m) => [m.onsetTimestamp!, m.offsetTimestamp!]);
            const post = computePostComplexity(complexityPre, pre.features, sleepMarkerPairs, sleepScores, timestamps);
            complexityPost = post.score;
          }
        }
      }

      return {
        date,
        has_markers: !!markers,
        is_no_sleep: markers?.isNoSleep ?? false,
        needs_consensus: markers?.needsConsensus ?? false,
        has_auto_score: false,
        complexity_pre: complexityPre,
        complexity_post: complexityPost,
      };
    });
  }

  async loadAdjacentMarkers(fileId: number, date: string, username: string): Promise<AdjacentMarkersData | null> {
    // Get dates from FileRecord (avoids loading full ActivityDay records)
    const file = await localDb.getFileById(fileId);
    const allDates = file?.availableDates?.slice().sort() ?? [];
    const idx = allDates.indexOf(date);
    if (idx < 0) return null;

    const prevDate = idx > 0 ? allDates[idx - 1] : null;
    const nextDate = idx < allDates.length - 1 ? allDates[idx + 1] : null;

    const [prevMarkers, nextMarkers] = await Promise.all([
      prevDate ? localDb.getMarkers(fileId, prevDate, username) : null,
      nextDate ? localDb.getMarkers(fileId, nextDate, username) : null,
    ]);

    // Both server and local markers use seconds
    const mapMarkers = (record: localDb.MarkerRecord | null | undefined) =>
      (record?.sleepMarkers ?? []).map((m) => ({
        onset_timestamp: m.onsetTimestamp,
        offset_timestamp: m.offsetTimestamp,
        marker_index: m.markerIndex,
      }));

    return {
      previous_day_markers: mapMarkers(prevMarkers),
      next_day_markers: mapMarkers(nextMarkers),
      previous_date: prevDate,
      next_date: nextDate,
    };
  }
}

/**
 * Get the appropriate data source for a file.
 */
export function getDataSource(
  source: "local" | "server",
  sitePassword: string | null,
  username: string,
): DataSource {
  if (source === "local") {
    return new LocalDataSource();
  }
  return new ServerDataSource(sitePassword, username);
}
