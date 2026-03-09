import { type FileRecord, type ActivityDay, type MarkerRecord, type SleepMarkerJson, type NonwearMarkerJson, type StudySettingsRecord, type SensorNonwearRecord, type DiaryEntryRecord } from "./schema";
import { getDb } from "@/lib/workspace-db";
import { computeMarkerHash, sha256Hex } from "@/lib/content-hash";
import type { DiaryEntryData } from "@/services/data-source";

export type { FileRecord, ActivityDay, MarkerRecord, SleepMarkerJson, NonwearMarkerJson, StudySettingsRecord, SensorNonwearRecord, DiaryEntryRecord };

/**
 * Save or update a file record in IndexedDB (upsert by filename).
 */
export async function saveFileRecord(record: Omit<FileRecord, "id">): Promise<number> {
  const db = getDb();
  const existing = await db.files.where("filename").equals(record.filename).first();
  if (existing?.id) {
    await db.files.update(existing.id, record);
    return existing.id;
  }
  return db.files.add(record as FileRecord);
}

/**
 * Get all local file records.
 */
export async function getLocalFiles(): Promise<FileRecord[]> {
  return getDb().files.where("source").equals("local").toArray();
}

/**
 * Get a file record by filename.
 */
export async function getFileByFilename(filename: string): Promise<FileRecord | undefined> {
  return getDb().files.where("filename").equals(filename).first();
}

/**
 * Get a file record by ID.
 */
export async function getFileById(id: number): Promise<FileRecord | undefined> {
  return getDb().files.get(id);
}

/**
 * Delete a file record and all associated data.
 */
export async function deleteFileRecord(fileId: number): Promise<void> {
  const db = getDb();
  await db.transaction("rw", [db.files, db.activityDays, db.markers, db.sensorNonwear, db.diaryEntries], async () => {
    await db.activityDays.where("fileId").equals(fileId).delete();
    await db.markers.where("fileId").equals(fileId).delete();
    await db.sensorNonwear.where("fileId").equals(fileId).delete();
    await db.diaryEntries.where("fileId").equals(fileId).delete();
    await db.files.delete(fileId);
  });
}

/**
 * Save activity data for a specific date.
 */
export async function saveActivityDay(day: Omit<ActivityDay, "id">): Promise<number> {
  const db = getDb();
  return db.transaction("rw", db.activityDays, async () => {
    await db.activityDays.where("[fileId+date]").equals([day.fileId, day.date]).delete();
    return db.activityDays.add(day as ActivityDay);
  });
}

/**
 * Get activity data for a specific file+date.
 */
export async function getActivityDay(fileId: number, date: string): Promise<ActivityDay | undefined> {
  return getDb().activityDays.where("[fileId+date]").equals([fileId, date]).first();
}

/**
 * Get all available dates for a file.
 */
export async function getAvailableDates(fileId: number): Promise<string[]> {
  const days = await getDb().activityDays.where("fileId").equals(fileId).toArray();
  return days.map((d) => d.date).sort();
}

/**
 * Save markers to IndexedDB with sync tracking.
 */
export async function saveMarkers(
  fileId: number,
  date: string,
  username: string,
  sleepMarkers: SleepMarkerJson[],
  nonwearMarkers: NonwearMarkerJson[],
  isNoSleep: boolean,
  notes: string,
): Promise<void> {
  const db = getDb();
  const contentHash = await computeMarkerHash({ sleepMarkers, nonwearMarkers, isNoSleep, notes });

  const existing = await db.markers
    .where("[fileId+date+username]")
    .equals([fileId, date, username])
    .first();

  const record: Omit<MarkerRecord, "id"> = {
    fileId,
    date,
    username,
    sleepMarkers,
    nonwearMarkers,
    isNoSleep,
    notes,
    contentHash,
    syncStatus: "pending",
    lastModifiedAt: new Date().toISOString(),
  };

  if (existing?.id) {
    await db.markers.update(existing.id, record);
  } else {
    await db.markers.add(record as MarkerRecord);
  }
}

/**
 * Get markers for a specific file+date+username.
 */
export async function getMarkers(
  fileId: number,
  date: string,
  username: string,
): Promise<MarkerRecord | undefined> {
  return getDb().markers.where("[fileId+date+username]").equals([fileId, date, username]).first();
}

/**
 * Get all markers with pending sync status.
 */
export async function getPendingMarkers(): Promise<MarkerRecord[]> {
  return getDb().markers.where("syncStatus").equals("pending").toArray();
}

/**
 * Mark a marker record as synced.
 */
export async function markSynced(id: number): Promise<void> {
  await getDb().markers.update(id, { syncStatus: "synced" });
}

/**
 * Mark a marker record as having a conflict.
 */
export async function markConflict(id: number): Promise<void> {
  await getDb().markers.update(id, { syncStatus: "conflict" });
}

/**
 * Count markers with conflict status.
 */
export async function getConflictCount(): Promise<number> {
  return getDb().markers.where("syncStatus").equals("conflict").count();
}

/**
 * Get all markers for a file, indexed by "date:username" key.
 */
export async function getAllMarkersForFile(
  fileId: number,
  username: string,
): Promise<Map<string, MarkerRecord>> {
  const all = await getDb().markers.where("fileId").equals(fileId).toArray();
  const map = new Map<string, MarkerRecord>();
  for (const m of all) {
    if (m.username === username) map.set(m.date, m);
  }
  return map;
}

/**
 * Get all activity days for a file, indexed by date.
 */
export async function getAllActivityDaysForFile(
  fileId: number,
): Promise<Map<string, ActivityDay>> {
  const all = await getDb().activityDays.where("fileId").equals(fileId).toArray();
  const map = new Map<string, ActivityDay>();
  for (const d of all) map.set(d.date, d);
  return map;
}

/**
 * Get local study settings from IndexedDB.
 */
export async function getLocalStudySettings(): Promise<StudySettingsRecord | undefined> {
  return getDb().studySettings.where("key").equals("study").first();
}

/**
 * Save study settings to IndexedDB (upsert by key="study").
 */
export async function saveLocalStudySettings(settings: {
  sleepDetectionRule: string;
  nightStartHour: string;
  nightEndHour: string;
  defaultAlgorithm: string;
  extraSettings: Record<string, unknown>;
}): Promise<void> {
  const db = getDb();
  const contentHash = await sha256Hex(JSON.stringify(settings));
  const existing = await db.studySettings.where("key").equals("study").first();
  const record: Omit<StudySettingsRecord, "id"> = {
    key: "study",
    ...settings,
    contentHash,
    lastModifiedAt: new Date().toISOString(),
  };
  if (existing?.id) {
    await db.studySettings.update(existing.id, record);
  } else {
    await db.studySettings.add(record as StudySettingsRecord);
  }
}

// =============================================================================
// Sensor Nonwear
// =============================================================================

export type SensorNonwearEntry = Omit<SensorNonwearRecord, "id">;

/**
 * Get sensor nonwear periods for a file+date.
 */
export async function getSensorNonwear(
  fileId: number,
  analysisDate: string,
): Promise<SensorNonwearEntry[]> {
  return getDb().sensorNonwear
    .where("[fileId+analysisDate]")
    .equals([fileId, analysisDate])
    .toArray();
}

/**
 * Save sensor nonwear periods (replace all for file+date).
 */
export async function saveSensorNonwear(
  fileId: number,
  analysisDate: string,
  periods: SensorNonwearEntry[],
): Promise<void> {
  const db = getDb();
  await db.transaction("rw", db.sensorNonwear, async () => {
    await db.sensorNonwear.where("[fileId+analysisDate]").equals([fileId, analysisDate]).delete();
    if (periods.length > 0) {
      await db.sensorNonwear.bulkAdd(
        periods.map((p, i) => ({ ...p, fileId, analysisDate, periodIndex: i })) as SensorNonwearRecord[],
      );
    }
  });
}

/**
 * Get all sensor nonwear periods for a file.
 */
export async function getSensorNonwearForFile(
  fileId: number,
): Promise<SensorNonwearEntry[]> {
  return getDb().sensorNonwear.where("fileId").equals(fileId).toArray();
}

/**
 * Delete all sensor nonwear periods for a file.
 */
export async function deleteSensorNonwear(fileId: number): Promise<void> {
  await getDb().sensorNonwear.where("fileId").equals(fileId).delete();
}

// =============================================================================
// Diary Entries
// =============================================================================

function recordToDiaryData(r: DiaryEntryRecord): DiaryEntryData {
  return {
    fileId: r.fileId,
    analysisDate: r.analysisDate,
    bedTime: r.bedTime ?? null,
    wakeTime: r.wakeTime ?? null,
    lightsOut: r.lightsOut ?? null,
    gotUp: r.gotUp ?? null,
    sleepQuality: r.sleepQuality ?? null,
    timeToFallAsleepMinutes: r.timeToFallAsleepMinutes ?? null,
    numberOfAwakenings: r.numberOfAwakenings ?? null,
    notes: r.notes ?? null,
    nap1Start: r.nap1Start ?? null,
    nap1End: r.nap1End ?? null,
    nap2Start: r.nap2Start ?? null,
    nap2End: r.nap2End ?? null,
    nap3Start: r.nap3Start ?? null,
    nap3End: r.nap3End ?? null,
    nonwear1Start: r.nonwear1Start ?? null,
    nonwear1End: r.nonwear1End ?? null,
    nonwear1Reason: r.nonwear1Reason ?? null,
    nonwear2Start: r.nonwear2Start ?? null,
    nonwear2End: r.nonwear2End ?? null,
    nonwear2Reason: r.nonwear2Reason ?? null,
    nonwear3Start: r.nonwear3Start ?? null,
    nonwear3End: r.nonwear3End ?? null,
    nonwear3Reason: r.nonwear3Reason ?? null,
  };
}

/**
 * Get diary entry for a file+date.
 */
export async function getDiaryEntry(
  fileId: number,
  date: string,
): Promise<DiaryEntryData | null> {
  const r = await getDb().diaryEntries
    .where("[fileId+analysisDate]")
    .equals([fileId, date])
    .first();
  return r ? recordToDiaryData(r) : null;
}

/**
 * Get all diary entries for a file.
 */
export async function getDiaryEntries(
  fileId: number,
): Promise<DiaryEntryData[]> {
  const records = await getDb().diaryEntries.where("fileId").equals(fileId).toArray();
  return records.map(recordToDiaryData);
}

/**
 * Save a diary entry (upsert by fileId+analysisDate).
 */
export async function saveDiaryEntry(
  fileId: number,
  analysisDate: string,
  entry: Partial<DiaryEntryData>,
): Promise<void> {
  const db = getDb();
  const record: Omit<DiaryEntryRecord, "id"> = {
    fileId,
    analysisDate,
    bedTime: entry.bedTime ?? null,
    wakeTime: entry.wakeTime ?? null,
    lightsOut: entry.lightsOut ?? null,
    gotUp: entry.gotUp ?? null,
    sleepQuality: entry.sleepQuality ?? null,
    timeToFallAsleepMinutes: entry.timeToFallAsleepMinutes ?? null,
    numberOfAwakenings: entry.numberOfAwakenings ?? null,
    notes: entry.notes ?? null,
    nap1Start: entry.nap1Start ?? null,
    nap1End: entry.nap1End ?? null,
    nap2Start: entry.nap2Start ?? null,
    nap2End: entry.nap2End ?? null,
    nap3Start: entry.nap3Start ?? null,
    nap3End: entry.nap3End ?? null,
    nonwear1Start: entry.nonwear1Start ?? null,
    nonwear1End: entry.nonwear1End ?? null,
    nonwear1Reason: entry.nonwear1Reason ?? null,
    nonwear2Start: entry.nonwear2Start ?? null,
    nonwear2End: entry.nonwear2End ?? null,
    nonwear2Reason: entry.nonwear2Reason ?? null,
    nonwear3Start: entry.nonwear3Start ?? null,
    nonwear3End: entry.nonwear3End ?? null,
    nonwear3Reason: entry.nonwear3Reason ?? null,
    importedAt: new Date().toISOString(),
  };

  await db.transaction("rw", db.diaryEntries, async () => {
    const existing = await db.diaryEntries
      .where("[fileId+analysisDate]")
      .equals([fileId, analysisDate])
      .first();
    if (existing?.id) {
      await db.diaryEntries.update(existing.id, record);
    } else {
      await db.diaryEntries.add(record as DiaryEntryRecord);
    }
  });
}

/**
 * Delete all diary entries for a file.
 */
export async function deleteDiaryEntries(fileId: number): Promise<void> {
  await getDb().diaryEntries.where("fileId").equals(fileId).delete();
}
