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
 */
export interface ActivityDay {
  id?: number;
  fileId: number;
  date: string; // "YYYY-MM-DD"
  timestamps: ArrayBuffer; // Float64Array stored as ArrayBuffer
  axisY: ArrayBuffer; // Float64Array
  vectorMagnitude: ArrayBuffer; // Float64Array
  algorithmResults: Record<string, ArrayBuffer>; // Keyed by algorithm name, Uint8Array
  nonwearResults: ArrayBuffer | null; // Uint8Array
}

/**
 * Sleep marker stored locally for sync.
 */
export interface SleepMarkerJson {
  onsetTimestamp: number | null;
  offsetTimestamp: number | null;
  markerIndex: number;
  markerType: MarkerType;
}

/**
 * Nonwear marker stored locally for sync.
 */
export interface NonwearMarkerJson {
  startTimestamp: number | null;
  endTimestamp: number | null;
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
 * Dexie database for local-first sleep scoring data.
 */
export class SleepScoringDB extends Dexie {
  files!: EntityTable<FileRecord, "id">;
  activityDays!: EntityTable<ActivityDay, "id">;
  markers!: EntityTable<MarkerRecord, "id">;
  studySettings!: EntityTable<StudySettingsRecord, "id">;
  sensorNonwear!: EntityTable<SensorNonwearRecord, "id">;
  diaryEntries!: EntityTable<DiaryEntryRecord, "id">;

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
  }
}

// Singleton removed — use getDb() from @/lib/workspace-db instead.
