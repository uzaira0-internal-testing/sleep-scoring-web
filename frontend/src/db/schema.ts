import Dexie, { type EntityTable } from "dexie";
import type { MarkerType } from "@/api/types";

/**
 * Local file record stored in IndexedDB.
 */
export interface FileRecord {
  id?: number;
  filename: string;
  devicePreset: string;
  epochLengthSeconds: number;
  availableDates: string[];
  fileHash: string; // SHA-256 of first 64KB for dedup
  source: "local" | "server";
  serverFileId?: number;
  createdAt: string;
}

/**
 * Per-date activity data stored in IndexedDB.
 * Uses ArrayBuffer for efficient storage of typed arrays.
 * All timestamps are Unix seconds (Float64Array).
 */
export interface ActivityDay {
  id?: number;
  fileId: number;
  date: string; // "YYYY-MM-DD"
  timestamps: ArrayBuffer; // Float64Array of Unix seconds
  axisY: ArrayBuffer; // Float64Array
  vectorMagnitude: ArrayBuffer; // Float64Array
  algorithmResults: Record<string, ArrayBuffer>; // Keyed by algorithm name, Uint8Array
  nonwearResults: ArrayBuffer | null; // Uint8Array
}

/**
 * Sleep marker stored locally for sync.
 * onsetTimestamp/offsetTimestamp are Unix seconds.
 */
export interface SleepMarkerJson {
  onsetTimestamp: number | null; // Unix seconds
  offsetTimestamp: number | null; // Unix seconds
  markerIndex: number;
  markerType: MarkerType;
}

/**
 * Nonwear marker stored locally for sync.
 * startTimestamp/endTimestamp are Unix seconds.
 */
export interface NonwearMarkerJson {
  startTimestamp: number | null; // Unix seconds
  endTimestamp: number | null; // Unix seconds
  markerIndex: number;
}

/**
 * Marker record with sync status tracking.
 */
export interface MarkerRecord {
  id?: number;
  fileId: number;
  date: string;
  username: string;
  sleepMarkers: SleepMarkerJson[];
  nonwearMarkers: NonwearMarkerJson[];
  isNoSleep: boolean;
  needsConsensus: boolean;
  notes: string;
  contentHash: string; // SHA-256 for sync dedup
  syncStatus: "pending" | "synced" | "conflict";
  lastModifiedAt: string;
}

/**
 * Study settings record stored locally in IndexedDB.
 */
export interface StudySettingsRecord {
  id?: number;
  key: "study";
  sleepDetectionRule: string;
  nightStartHour: string;
  nightEndHour: string;
  defaultAlgorithm: string;
  extraSettings: Record<string, unknown>;
  contentHash: string;
  lastModifiedAt: string;
}

/**
 * Sensor nonwear period stored in IndexedDB.
 * Timestamps are in seconds (matching backend convention).
 */
export interface SensorNonwearRecord {
  id?: number;
  fileId: number;
  analysisDate: string; // "YYYY-MM-DD"
  startTimestamp: number; // seconds
  endTimestamp: number; // seconds
  periodIndex: number;
}

/**
 * Diary entry stored in IndexedDB.
 * Field names match DiaryEntryData in data-source.ts.
 */
export interface DiaryEntryRecord {
  id?: number;
  fileId: number;
  analysisDate: string; // "YYYY-MM-DD"
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
  importedAt: string;
}

/**
 * Audit log event stored in IndexedDB.
 * IndexedDB is the durable commit point — events are written here FIRST,
 * then replicated to the server. No event is lost on crash/tab kill/power loss.
 */
export interface AuditLogRecord {
  id?: number;
  fileId: number;
  analysisDate: string; // "YYYY-MM-DD"
  username: string;
  action: string;
  clientTimestamp: number; // Unix seconds
  sessionId: string;
  sequence: number;
  payload?: Record<string, unknown>;
}

/**
 * Dexie database for local-first sleep scoring data.
 */
export class SleepScoringDB extends Dexie {
  files!: EntityTable<FileRecord, "id">;
  activityDays!: EntityTable<ActivityDay, "id">;
  markers!: EntityTable<MarkerRecord, "id">;
  studySettings!: EntityTable<StudySettingsRecord, "id">;
  sensorNonwear!: EntityTable<SensorNonwearRecord, "id">;
  diaryEntries!: EntityTable<DiaryEntryRecord, "id">;
  auditLog!: EntityTable<AuditLogRecord, "id">;

  constructor(dbName: string = "SleepScoringDB") {
    super(dbName);

    this.version(1).stores({
      files: "++id, &filename, fileHash",
      activityDays: "++id, [fileId+date], fileId",
      markers: "++id, [fileId+date+username], fileId, syncStatus",
    });

    this.version(2).stores({
      files: "++id, &filename, fileHash",
      activityDays: "++id, [fileId+date], fileId",
      markers: "++id, [fileId+date+username], fileId, syncStatus",
      studySettings: "++id, &key",
    });

    this.version(3).stores({
      files: "++id, &filename, fileHash",
      activityDays: "++id, [fileId+date], fileId",
      markers: "++id, [fileId+date+username], fileId, syncStatus",
      studySettings: "++id, &key",
      sensorNonwear: "++id, [fileId+analysisDate], fileId",
    });

    this.version(4).stores({
      files: "++id, &filename, fileHash",
      activityDays: "++id, [fileId+date], fileId",
      markers: "++id, [fileId+date+username], fileId, syncStatus",
      studySettings: "++id, &key",
      sensorNonwear: "++id, [fileId+analysisDate], fileId",
      diaryEntries: "++id, &[fileId+analysisDate], fileId",
    });

    this.version(5).stores({
      files: "++id, &filename, fileHash, source",
      activityDays: "++id, [fileId+date], fileId",
      markers: "++id, [fileId+date+username], fileId, syncStatus",
      studySettings: "++id, &key",
      sensorNonwear: "++id, [fileId+analysisDate], fileId",
      diaryEntries: "++id, &[fileId+analysisDate], fileId",
    });

    // v6: Convert activity timestamps from milliseconds to seconds.
    // No schema change — only data migration for existing IndexedDB entries.
    this.version(6).stores({
      files: "++id, &filename, fileHash, source",
      activityDays: "++id, [fileId+date], fileId",
      markers: "++id, [fileId+date+username], fileId, syncStatus",
      studySettings: "++id, &key",
      sensorNonwear: "++id, [fileId+analysisDate], fileId",
      diaryEntries: "++id, &[fileId+analysisDate], fileId",
    }).upgrade(async (tx) => {
      // Convert activity timestamps from ms to seconds (one-time migration)
      const days = await tx.table("activityDays").toArray();
      for (const day of days) {
        const ts = new Float64Array(day.timestamps);
        if (ts.length > 0 && ts[0]! > 1e10) {
          // Timestamps are in milliseconds — convert to seconds
          const converted = new Float64Array(ts.length);
          for (let i = 0; i < ts.length; i++) converted[i] = ts[i]! / 1000;
          await tx.table("activityDays").put({ ...day, timestamps: converted.buffer });
        }
      }

      // Convert marker timestamps from ms to seconds
      const markers = await tx.table("markers").toArray();
      for (const record of markers) {
        let changed = false;
        const sleepMarkers = record.sleepMarkers?.map((m: SleepMarkerJson) => {
          const needsOnset = m.onsetTimestamp != null && m.onsetTimestamp > 1e10;
          const needsOffset = m.offsetTimestamp != null && m.offsetTimestamp > 1e10;
          if (needsOnset || needsOffset) {
            changed = true;
            return {
              ...m,
              onsetTimestamp: needsOnset ? m.onsetTimestamp! / 1000 : m.onsetTimestamp,
              offsetTimestamp: needsOffset ? m.offsetTimestamp! / 1000 : m.offsetTimestamp,
            };
          }
          return m;
        }) ?? [];
        const nonwearMarkers = record.nonwearMarkers?.map((m: NonwearMarkerJson) => {
          const needsStart = m.startTimestamp != null && m.startTimestamp > 1e10;
          const needsEnd = m.endTimestamp != null && m.endTimestamp > 1e10;
          if (needsStart || needsEnd) {
            changed = true;
            return {
              ...m,
              startTimestamp: needsStart ? m.startTimestamp! / 1000 : m.startTimestamp,
              endTimestamp: needsEnd ? m.endTimestamp! / 1000 : m.endTimestamp,
            };
          }
          return m;
        }) ?? [];
        if (changed) {
          await tx.table("markers").put({ ...record, sleepMarkers, nonwearMarkers });
        }
      }
    });

    // v7: Add audit log table for ACID-compliant per-user action tracking.
    this.version(7).stores({
      files: "++id, &filename, fileHash, source",
      activityDays: "++id, [fileId+date], fileId",
      markers: "++id, [fileId+date+username], fileId, syncStatus",
      studySettings: "++id, &key",
      sensorNonwear: "++id, [fileId+analysisDate], fileId",
      diaryEntries: "++id, &[fileId+analysisDate], fileId",
      auditLog: "++id, [fileId+analysisDate+username], sessionId",
    });
  }
}

// Singleton removed — use getDb() from @/lib/workspace-db instead.
