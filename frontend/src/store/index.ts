import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";
import { useShallow } from "zustand/react/shallow";
import { MARKER_TYPES, ALGORITHM_TYPES, SLEEP_DETECTION_RULES, type MarkerType } from "@/api/types";
import { MARKER_LIMITS } from "@/constants/options";
import { queryClient } from "@/query-client";
import { saveUserPreferences, restoreUserPreferences } from "@/lib/user-state";
import { type ColorTheme, DEFAULT_COLOR_THEME, COLOR_PRESETS } from "@/lib/color-themes";
import { getActiveWorkspaceId } from "@/store/workspace-store";

/**
 * User authentication state (site password model)
 */
interface AuthState {
  sitePassword: string | null;
  username: string;  // Honor system - for audit logging
  isAuthenticated: boolean;
  isAdmin: boolean;
}

/**
 * File and date selection state
 */
interface FileState {
  currentFileId: number | null;
  currentFilename: string | null;
  currentDateIndex: number;
  availableDates: string[];
  availableFiles: Array<{
    id: number;
    filename: string;
    status: string;
    rowCount: number | null;
  }>;
  /** Whether current file is local (IndexedDB) or server-backed */
  currentFileSource: "local" | "server";
}

/**
 * Activity data state (columnar format)
 */
interface SensorNonwearPeriod {
  startTimestamp: number;  // seconds
  endTimestamp: number;    // seconds
}

interface ActivityState {
  timestamps: number[];
  axisX: number[];
  axisY: number[];
  axisZ: number[];
  vectorMagnitude: number[];
  algorithmResults: number[] | null;  // Sleep scoring (1=sleep, 0=wake)
  nonwearResults: number[] | null;  // Choi nonwear (1=nonwear, 0=wear)
  sensorNonwearPeriods: SensorNonwearPeriod[];  // Uploaded sensor nonwear (read-only overlays)
  isLoading: boolean;
  // Expected view range (for setting axis bounds even if data is missing)
  viewStart: number | null;
  viewEnd: number | null;
}

/**
 * Marker creation state machine
 */
type MarkerCreationMode = "idle" | "placing_onset" | "placing_offset";
type MarkerMode = "sleep" | "nonwear";

/**
 * Marker state
 */
interface MarkerState {
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
  isDirty: boolean;
  isSaving: boolean;
  lastSavedAt: number | null;
  saveError: string | null;
  selectedPeriodIndex: number | null;
  isNoSleep: boolean;  // True if this date is marked as having no sleep
  needsConsensus: boolean;  // True if flagged for consensus review
  notes: string;  // Free-text annotation notes

  // Two-click marker creation state
  markerMode: MarkerMode;
  creationMode: MarkerCreationMode;
  pendingOnsetTimestamp: number | null;
}

/**
 * Marker history snapshot for undo/redo
 */
interface MarkerSnapshot {
  sleepMarkers: MarkerState["sleepMarkers"];
  nonwearMarkers: MarkerState["nonwearMarkers"];
  isNoSleep: boolean;
  needsConsensus: boolean;
  notes: string;
  selectedPeriodIndex: number | null;
  timestamp: number;
}

/**
 * Undo/redo state
 */
interface UndoRedoState {
  markerHistory: MarkerSnapshot[];
  markerHistoryIndex: number;
}

const MAX_HISTORY = 50;

/**
 * Display preferences state
 */
interface PreferencesState {
  preferredDisplayColumn: "axis_x" | "axis_y" | "axis_z" | "vector_magnitude";
  viewModeHours: 24 | 48;
  currentAlgorithm: string;
  showAdjacentMarkers: boolean;
  showNonwearOverlays: boolean;
  autoScoreOnNavigate: boolean;
  autoNonwearOnNavigate: boolean;
}

/**
 * Study settings state (mirrors PyQt study_settings_tab.py)
 * Note: Only epoch-based paradigm for now, no raw/GT3X support
 */
interface StudySettingsState {
  sleepDetectionRule: "consecutive_onset3s_offset5s" | "consecutive_onset5s_offset10s" | "tudor_locke_2014";
  nightStartHour: string; // "21:00" format
  nightEndHour: string;   // "09:00" format
  // Note: nonwearAlgorithm is always "choi_2011" for epoch data (no van_hees)
}

/**
 * Data settings state (mirrors PyQt data_settings_tab.py)
 * Note: Only CSV/epoch-based for now, no GT3X/raw support
 */
interface DataSettingsState {
  devicePreset: "actigraph" | "actiwatch" | "motionwatch" | "geneactiv" | "generic";
  epochLengthSeconds: number;
  skipRows: number;
}

/**
 * Upload state — lives in store so uploads survive page navigation
 */
interface UploadState {
  uploadProgress: string | null;  // e.g. "Uploading 3/52: file.csv"
  uploadResult: { message: string; type: "success" | "error" } | null;
  isUploading: boolean;
}

/**
 * Color theme state — per-user plot color preferences
 */
interface ColorThemeState {
  colorTheme: ColorTheme;
}

/**
 * Combined store state
 */
interface SleepScoringState
  extends AuthState,
    FileState,
    ActivityState,
    MarkerState,
    UndoRedoState,
    PreferencesState,
    StudySettingsState,
    DataSettingsState,
    UploadState,
    ColorThemeState {
  // Auth actions
  setAuth: (sitePassword: string, username: string, isAdmin?: boolean) => void;
  setIsAdmin: (isAdmin: boolean) => void;
  clearAuth: () => void;

  // File actions
  setCurrentFile: (fileId: number, filename: string, source?: "local" | "server") => void;
  setAvailableFiles: (files: FileState["availableFiles"]) => void;
  setAvailableDates: (dates: string[]) => void;
  setCurrentDateIndex: (index: number) => void;
  navigateDate: (direction: 1 | -1) => void;

  // Activity data actions
  setActivityData: (data: {
    timestamps: number[];
    axisX: number[];
    axisY: number[];
    axisZ: number[];
    vectorMagnitude: number[];
    algorithmResults?: number[] | null;
    nonwearResults?: number[] | null;
    sensorNonwearPeriods?: SensorNonwearPeriod[];
    viewStart?: number | null;
    viewEnd?: number | null;
  }) => void;
  setLoading: (loading: boolean) => void;
  clearActivityData: () => void;

  // Marker actions (server-load variants skip undo history + isDirty)
  _loadSleepMarkersFromServer: (markers: MarkerState["sleepMarkers"]) => void;
  _loadNonwearMarkersFromServer: (markers: MarkerState["nonwearMarkers"]) => void;
  setSleepMarkers: (markers: MarkerState["sleepMarkers"]) => void;
  setNonwearMarkers: (markers: MarkerState["nonwearMarkers"]) => void;
  setMarkersDirty: (dirty: boolean) => void;
  setSelectedPeriod: (index: number | null) => void;

  // Two-click marker creation actions
  setMarkerMode: (mode: MarkerMode) => void;
  handlePlotClick: (timestamp: number) => void;
  cancelMarkerCreation: () => void;
  addSleepMarker: (
    onsetTimestamp: number,
    offsetTimestamp: number,
    markerType?: MarkerType
  ) => void;
  addNonwearMarker: (startTimestamp: number, endTimestamp: number) => void;
  updateMarker: (
    category: "sleep" | "nonwear",
    index: number,
    updates: Partial<{
      onsetTimestamp: number;
      offsetTimestamp: number;
      startTimestamp: number;
      endTimestamp: number;
      markerType: MarkerType;
    }>
  ) => void;
  deleteMarker: (category: "sleep" | "nonwear", index: number) => void;
  setIsNoSleep: (isNoSleep: boolean) => void;
  setNeedsConsensus: (needsConsensus: boolean) => void;
  setNotes: (notes: string) => void;

  // Save status actions
  setSaving: (saving: boolean) => void;
  setSaveError: (error: string | null) => void;
  markSaved: () => void;
  /** Registered by useMarkerAutoSave — flushes pending debounced save immediately */
  _flushSave: (() => Promise<boolean>) | null;
  registerFlushSave: (fn: (() => Promise<boolean>) | null) => void;

  // Undo/redo actions
  pushMarkerSnapshot: () => void;
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  // Drag transaction (atomic undo for drags)
  _isDragTransaction: boolean;
  beginDragTransaction: () => void;
  commitDragTransaction: () => void;

  // Atomic clear
  clearAllMarkers: () => void;

  // Preferences actions
  setPreferredDisplayColumn: (
    column: PreferencesState["preferredDisplayColumn"]
  ) => void;
  setViewModeHours: (hours: PreferencesState["viewModeHours"]) => void;
  setCurrentAlgorithm: (algorithm: string) => void;
  setShowAdjacentMarkers: (show: boolean) => void;
  setShowNonwearOverlays: (show: boolean) => void;
  setAutoScoreOnNavigate: (enabled: boolean) => void;
  setAutoNonwearOnNavigate: (enabled: boolean) => void;

  // Study settings actions
  setSleepDetectionRule: (rule: StudySettingsState["sleepDetectionRule"]) => void;
  setNightHours: (startHour: string, endHour: string) => void;

  // Data settings actions
  setDevicePreset: (preset: DataSettingsState["devicePreset"]) => void;
  setEpochLengthSeconds: (seconds: number) => void;
  setSkipRows: (rows: number) => void;

  // Upload actions
  setUploadProgress: (progress: string | null) => void;
  setUploadResult: (result: UploadState["uploadResult"]) => void;
  setIsUploading: (uploading: boolean) => void;

  // Color theme actions
  setColorTheme: (updates: Partial<ColorTheme>) => void;
  applyColorPreset: (presetName: string) => void;
  resetColorTheme: () => void;
}

/** Navigation lock — prevents concurrent navigateDate calls from skipping dates */
let _isNavigating = false;

/**
 * Main Zustand store for Sleep Scoring application.
 * Mirrors the desktop app's Redux store pattern.
 */
export const useSleepScoringStore = create<SleepScoringState>()(
  devtools(
    persist(
      (set, get) => ({
        // Initial auth state (site password model)
        sitePassword: null,
        username: "anonymous",
        isAuthenticated: false,
        isAdmin: false,

        // Initial file state
        currentFileId: null,
        currentFilename: null,
        currentDateIndex: 0,
        availableDates: [],
        availableFiles: [],
        currentFileSource: "server",

        // Initial activity state
        timestamps: [],
        axisX: [],
        axisY: [],
        axisZ: [],
        vectorMagnitude: [],
        algorithmResults: null,
        nonwearResults: null,
        sensorNonwearPeriods: [],
        isLoading: false,
        viewStart: null,
        viewEnd: null,

        // Initial marker state
        sleepMarkers: [],
        nonwearMarkers: [],
        isDirty: false,
        isSaving: false,
        lastSavedAt: null,
        saveError: null,
        selectedPeriodIndex: null,
        isNoSleep: false,
        needsConsensus: false,
        notes: "",

        // Two-click marker creation state
        markerMode: "sleep",
        creationMode: "idle",
        pendingOnsetTimestamp: null,

        // Undo/redo state
        markerHistory: [],
        markerHistoryIndex: -1,
        _isDragTransaction: false,

        // Initial preferences
        preferredDisplayColumn: "axis_y",
        viewModeHours: 24,
        currentAlgorithm: ALGORITHM_TYPES.SADEH_1994_ACTILIFE,
        showAdjacentMarkers: true,
        showNonwearOverlays: true,
        autoScoreOnNavigate: false,
        autoNonwearOnNavigate: false,

        // Initial study settings
        sleepDetectionRule: SLEEP_DETECTION_RULES.CONSECUTIVE_3S_5S,
        nightStartHour: "21:00",
        nightEndHour: "09:00",

        // Initial data settings
        devicePreset: "actigraph",
        epochLengthSeconds: 60,
        skipRows: 10,

        // Upload state
        uploadProgress: null,
        uploadResult: null,
        isUploading: false,

        // Auth actions
        setAuth: (sitePassword, username, isAdmin) => {
          set({
            sitePassword,
            username,
            isAuthenticated: true,
            isAdmin: isAdmin ?? false,
          });
          // Restore this user's previously saved preferences (file/date position, display settings)
          const restored = restoreUserPreferences(username);
          if (restored) set(restored as Partial<SleepScoringState>);
        },

        setIsAdmin: (isAdmin) => set({ isAdmin }),

        clearAuth: () => {
          // Save current user's preferences before clearing
          const state = get();
          saveUserPreferences(state.username, state as unknown as Record<string, unknown>);

          // Clear React Query cache so new user doesn't see old data
          queryClient.clear();

          set({
            // Auth
            sitePassword: null,
            username: "anonymous",
            isAuthenticated: false,
            isAdmin: false,
            // File/date selection
            currentFileId: null,
            currentFilename: null,
            currentDateIndex: 0,
            availableDates: [],
            availableFiles: [],
            currentFileSource: "server",
            // Activity data
            timestamps: [],
            axisX: [],
            axisY: [],
            axisZ: [],
            vectorMagnitude: [],
            algorithmResults: null,
            nonwearResults: null,
            sensorNonwearPeriods: [],
            isLoading: false,
            viewStart: null,
            viewEnd: null,
            // Markers
            sleepMarkers: [],
            nonwearMarkers: [],
            isDirty: false,
            isSaving: false,
            lastSavedAt: null,
            saveError: null,
            selectedPeriodIndex: null,
            isNoSleep: false,
            needsConsensus: false,
            notes: "",
            // Creation state
            markerMode: "sleep",
            creationMode: "idle",
            pendingOnsetTimestamp: null,
            // Undo/redo
            markerHistory: [],
            markerHistoryIndex: -1,
            // Upload
            uploadProgress: null,
            uploadResult: null,
            isUploading: false,
          });
        },

        // File actions
        setCurrentFile: (fileId, filename, source) =>
          set({
            currentFileId: fileId,
            currentFilename: filename,
            currentFileSource: source ?? "server",
            currentDateIndex: 0,
            timestamps: [],
            axisX: [],
            axisY: [],
            axisZ: [],
            vectorMagnitude: [],
            algorithmResults: null,
            nonwearResults: null,
            viewStart: null,
            viewEnd: null,
          }),

        setAvailableFiles: (files) => set({ availableFiles: files }),

        setAvailableDates: (dates) => {
          const { currentDateIndex } = get();
          // Clamp date index to valid range when dates are loaded (e.g., after page refresh)
          const clampedIndex = dates.length > 0 ? Math.min(currentDateIndex, dates.length - 1) : 0;
          set({ availableDates: dates, currentDateIndex: clampedIndex });
        },

        setCurrentDateIndex: (index) => {
          if (_isNavigating) return;
          _isNavigating = true;
          void (async () => {
            try {
              const { currentDateIndex, isDirty, _flushSave } = get();
              if (index === currentDateIndex) {
                return;  // Note: finally block still runs
              }

              // Flush pending save and block navigation on failure.
              // Race against a 10s timeout so a hung save doesn't lock navigation forever.
              if (isDirty && _flushSave) {
                const saved = await Promise.race([
                  _flushSave(),
                  new Promise<boolean>((resolve) => setTimeout(() => resolve(false), 10_000)),
                ]);
                if (!saved) return;
              }

              // Clear marker state when switching dates (same as navigateDate)
              set({
                currentDateIndex: index,
                sleepMarkers: [],
                nonwearMarkers: [],
                selectedPeriodIndex: null,
                isNoSleep: false,
                needsConsensus: false,
                notes: "",
                isDirty: false,
                creationMode: "idle",
                pendingOnsetTimestamp: null,
                markerHistory: [],
                markerHistoryIndex: -1,
              });
            } finally {
              _isNavigating = false;
            }
          })();
        },

        navigateDate: (direction) => {
          if (_isNavigating) return; // Prevent double-nav from rapid clicks
          _isNavigating = true;
          void (async () => {
            try {
              const pre = get();
              const targetIndex = pre.currentDateIndex + direction;
              if (targetIndex < 0 || targetIndex >= pre.availableDates.length) return;

              // Flush pending save and block navigation on failure.
              // Race against a 10s timeout so a hung save doesn't lock navigation forever.
              if (pre.isDirty && pre._flushSave) {
                const saved = await Promise.race([
                  pre._flushSave(),
                  new Promise<boolean>((resolve) => setTimeout(() => resolve(false), 10_000)),
                ]);
                if (!saved) return;
              }

              // Re-check bounds after await in case file/date list changed.
              const post = get();
              const newIndex = post.currentDateIndex + direction;
              if (newIndex < 0 || newIndex >= post.availableDates.length) return;

              // Clear all marker state so the new date starts fresh.
              // Without this, old markers persist during the API fetch window,
              // causing new markers to be typed as NAP instead of MAIN_SLEEP.
              set({
                currentDateIndex: newIndex,
                sleepMarkers: [],
                nonwearMarkers: [],
                selectedPeriodIndex: null,
                isNoSleep: false,
                needsConsensus: false,
                notes: "",
                isDirty: false,
                creationMode: "idle",
                pendingOnsetTimestamp: null,
                markerHistory: [],
                markerHistoryIndex: -1,
              });
            } finally {
              _isNavigating = false;
            }
          })();
        },

        // Activity data actions
        setActivityData: (data) =>
          set({
            timestamps: data.timestamps,
            axisX: data.axisX,
            axisY: data.axisY,
            axisZ: data.axisZ,
            vectorMagnitude: data.vectorMagnitude,
            algorithmResults: data.algorithmResults ?? null,
            nonwearResults: data.nonwearResults ?? null,
            sensorNonwearPeriods: data.sensorNonwearPeriods ?? [],
            viewStart: data.viewStart ?? null,
            viewEnd: data.viewEnd ?? null,
            isLoading: false,
          }),

        setLoading: (loading) => set({ isLoading: loading }),

        clearActivityData: () =>
          set({
            timestamps: [],
            axisX: [],
            axisY: [],
            axisZ: [],
            vectorMagnitude: [],
            algorithmResults: null,
            nonwearResults: null,
            sensorNonwearPeriods: [],
            viewStart: null,
            viewEnd: null,
          }),

        // Marker actions — server-load variants (no undo, no isDirty)
        _loadSleepMarkersFromServer: (markers) => set({ sleepMarkers: markers }),
        _loadNonwearMarkersFromServer: (markers) => set({ nonwearMarkers: markers }),

        // User-initiated marker actions (push undo + mark dirty)
        setSleepMarkers: (markers) => {
          get().pushMarkerSnapshot();
          set({ sleepMarkers: markers, isDirty: true });
        },

        setNonwearMarkers: (markers) => {
          get().pushMarkerSnapshot();
          set({ nonwearMarkers: markers, isDirty: true });
        },

        setMarkersDirty: (dirty) => set({ isDirty: dirty }),

        setSelectedPeriod: (index) => set({ selectedPeriodIndex: index }),

        // Two-click marker creation actions
        setMarkerMode: (mode) =>
          set({ markerMode: mode, creationMode: "idle", pendingOnsetTimestamp: null }),

        handlePlotClick: (timestamp) => {
          const { markerMode, creationMode, pendingOnsetTimestamp, sleepMarkers, nonwearMarkers, isNoSleep, pushMarkerSnapshot, timestamps } = get();

          // Clamp to actual data range (both timestamp and timestamps[] are seconds)
          let ts = timestamp;
          if (timestamps.length > 0) {
            ts = Math.max(timestamps[0], Math.min(timestamps[timestamps.length - 1], ts));
          }

          if (creationMode === "idle") {
            // Check marker limits before starting creation
            if (markerMode === "sleep" && sleepMarkers.length >= MARKER_LIMITS.MAX_SLEEP_PERIODS_PER_DAY) {
              console.warn(`Cannot create more than ${MARKER_LIMITS.MAX_SLEEP_PERIODS_PER_DAY} sleep periods per day`);
              return;
            }
            if (markerMode === "nonwear" && nonwearMarkers.length >= MARKER_LIMITS.MAX_NONWEAR_PERIODS_PER_DAY) {
              console.warn(`Cannot create more than ${MARKER_LIMITS.MAX_NONWEAR_PERIODS_PER_DAY} nonwear periods per day`);
              return;
            }
            // First click: set onset/start
            set({ creationMode: "placing_onset", pendingOnsetTimestamp: ts });
          } else if (creationMode === "placing_onset" && pendingOnsetTimestamp !== null) {
            // Second click: complete the marker
            const onset = Math.min(pendingOnsetTimestamp, ts);
            const offset = Math.max(pendingOnsetTimestamp, ts);

            // Snapshot before mutation so plot-click markers are undoable
            pushMarkerSnapshot();

            if (markerMode === "sleep") {
              // Determine marker type: force NAP when isNoSleep, otherwise first is MAIN_SLEEP
              const markerType = isNoSleep
                ? MARKER_TYPES.NAP
                : (sleepMarkers.length === 0 ? MARKER_TYPES.MAIN_SLEEP : MARKER_TYPES.NAP);
              const newArrayIndex = sleepMarkers.length;
              const newMarker = {
                onsetTimestamp: onset,
                offsetTimestamp: offset,
                markerIndex: newArrayIndex + 1,  // 1-indexed to match backend period_index
                markerType,
              };
              set({
                sleepMarkers: [...sleepMarkers, newMarker],
                isDirty: true,
                creationMode: "idle",
                pendingOnsetTimestamp: null,
                selectedPeriodIndex: newArrayIndex, // Array index (0-based) for UI selection
              });
            } else {
              // Nonwear marker
              const newArrayIndex = nonwearMarkers.length;
              const newMarker = {
                startTimestamp: onset,
                endTimestamp: offset,
                markerIndex: newArrayIndex + 1,  // 1-indexed to match backend period_index
              };
              set({
                nonwearMarkers: [...nonwearMarkers, newMarker],
                isDirty: true,
                creationMode: "idle",
                pendingOnsetTimestamp: null,
                selectedPeriodIndex: newArrayIndex, // Array index (0-based) for UI selection
              });
            }
          }
        },

        cancelMarkerCreation: () =>
          set({ creationMode: "idle", pendingOnsetTimestamp: null }),

        addSleepMarker: (onsetTimestamp, offsetTimestamp, markerType) => {
          const { sleepMarkers, pushMarkerSnapshot, isNoSleep } = get();
          // Validate marker limit
          if (sleepMarkers.length >= MARKER_LIMITS.MAX_SLEEP_PERIODS_PER_DAY) {
            console.warn(`Cannot create more than ${MARKER_LIMITS.MAX_SLEEP_PERIODS_PER_DAY} sleep periods per day`);
            return;
          }
          pushMarkerSnapshot();
          const newMarker = {
            onsetTimestamp,
            offsetTimestamp,
            markerIndex: sleepMarkers.length + 1,  // 1-indexed to match backend
            markerType: markerType ?? (
              isNoSleep
                ? MARKER_TYPES.NAP
                : (sleepMarkers.length === 0 ? MARKER_TYPES.MAIN_SLEEP : MARKER_TYPES.NAP)
            ),
          };
          set({
            sleepMarkers: [...sleepMarkers, newMarker],
            isDirty: true,
            selectedPeriodIndex: sleepMarkers.length,
            markerMode: "sleep" as const,
          });
        },

        addNonwearMarker: (startTimestamp, endTimestamp) => {
          const { nonwearMarkers, pushMarkerSnapshot } = get();
          // Validate marker limit
          if (nonwearMarkers.length >= MARKER_LIMITS.MAX_NONWEAR_PERIODS_PER_DAY) {
            console.warn(`Cannot create more than ${MARKER_LIMITS.MAX_NONWEAR_PERIODS_PER_DAY} nonwear periods per day`);
            return;
          }
          pushMarkerSnapshot();
          const newMarker = {
            startTimestamp,
            endTimestamp,
            markerIndex: nonwearMarkers.length + 1,  // 1-indexed to match backend
          };
          set({
            nonwearMarkers: [...nonwearMarkers, newMarker],
            isDirty: true,
            selectedPeriodIndex: nonwearMarkers.length,
            markerMode: "nonwear" as const,
          });
        },

        updateMarker: (category, index, updates) => {
          if (!get()._isDragTransaction) {
            get().pushMarkerSnapshot();
          }
          // Clamp timestamp fields to actual data range (both timestamps and markers are seconds)
          const { timestamps } = get();
          const clamped = { ...updates };
          if (timestamps.length > 0) {
            const minSec = timestamps[0];
            const maxSec = timestamps[timestamps.length - 1];
            if (clamped.onsetTimestamp !== undefined) clamped.onsetTimestamp = Math.max(minSec, Math.min(maxSec, clamped.onsetTimestamp));
            if (clamped.offsetTimestamp !== undefined) clamped.offsetTimestamp = Math.max(minSec, Math.min(maxSec, clamped.offsetTimestamp));
            if (clamped.startTimestamp !== undefined) clamped.startTimestamp = Math.max(minSec, Math.min(maxSec, clamped.startTimestamp));
            if (clamped.endTimestamp !== undefined) clamped.endTimestamp = Math.max(minSec, Math.min(maxSec, clamped.endTimestamp));
          }
          if (category === "sleep") {
            const { sleepMarkers } = get();
            const updated = sleepMarkers.map((m, i) =>
              i === index ? { ...m, ...clamped } : m
            );
            set({ sleepMarkers: updated, isDirty: true });
          } else {
            const { nonwearMarkers } = get();
            const updated = nonwearMarkers.map((m, i) =>
              i === index ? { ...m, ...clamped } : m
            );
            set({ nonwearMarkers: updated, isDirty: true });
          }
        },

        deleteMarker: (category, index) => {
          get().pushMarkerSnapshot();
          if (category === "sleep") {
            const { sleepMarkers } = get();
            const updated = sleepMarkers
              .filter((_, i) => i !== index)
              .map((m, i) => ({ ...m, markerIndex: i + 1 }));  // 1-indexed
            set({ sleepMarkers: updated, isDirty: true, selectedPeriodIndex: null });
          } else {
            const { nonwearMarkers } = get();
            const updated = nonwearMarkers
              .filter((_, i) => i !== index)
              .map((m, i) => ({ ...m, markerIndex: i + 1 }));  // 1-indexed
            set({ nonwearMarkers: updated, isDirty: true, selectedPeriodIndex: null });
          }
        },

        setIsNoSleep: (isNoSleep) => {
          get().pushMarkerSnapshot();
          if (isNoSleep) {
            // When marking as "no sleep", only clear MAIN_SLEEP markers; preserve NAPs
            const { sleepMarkers } = get();
            const napsOnly = sleepMarkers
              .filter(m => m.markerType !== MARKER_TYPES.MAIN_SLEEP)
              .map((m, i) => ({ ...m, markerIndex: i + 1 }));
            set({
              isNoSleep: true,
              sleepMarkers: napsOnly,
              isDirty: true,
              selectedPeriodIndex: napsOnly.length > 0 ? 0 : null,
            });
          } else {
            set({ isNoSleep: false, isDirty: true });
          }
        },

        setNeedsConsensus: (needsConsensus) => {
          get().pushMarkerSnapshot();
          set({ needsConsensus, isDirty: true });
        },

        setNotes: (notes) => {
          get().pushMarkerSnapshot();
          set({ notes, isDirty: true });
        },

        // Save status actions
        setSaving: (saving) => set({ isSaving: saving }),
        setSaveError: (error) => set({ saveError: error }),
        markSaved: () => set({ isDirty: false, isSaving: false, lastSavedAt: Date.now() }),
        _flushSave: null,
        registerFlushSave: (fn) => set({ _flushSave: fn }),

        // Undo/redo actions
        pushMarkerSnapshot: () => {
          const { sleepMarkers, nonwearMarkers, isNoSleep, needsConsensus, notes, selectedPeriodIndex, markerHistory, markerHistoryIndex } = get();
          const snapshot: MarkerSnapshot = {
            sleepMarkers: structuredClone(sleepMarkers),
            nonwearMarkers: structuredClone(nonwearMarkers),
            isNoSleep,
            needsConsensus,
            notes,
            selectedPeriodIndex,
            timestamp: Date.now(),
          };
          // Truncate any future history (if we undid and now making new changes)
          const newHistory = markerHistory.slice(0, markerHistoryIndex + 1);
          newHistory.push(snapshot);
          // Limit history size
          if (newHistory.length > MAX_HISTORY) {
            newHistory.shift();
          }
          set({ markerHistory: newHistory, markerHistoryIndex: newHistory.length - 1 });
        },

        undo: () => {
          const { markerHistory, markerHistoryIndex, sleepMarkers, nonwearMarkers, isNoSleep, needsConsensus, notes, selectedPeriodIndex } = get();
          if (markerHistoryIndex < 0) return;

          // If at the end and haven't saved current state, push current first
          if (markerHistoryIndex === markerHistory.length - 1) {
            const currentSnapshot: MarkerSnapshot = {
              sleepMarkers: structuredClone(sleepMarkers),
              nonwearMarkers: structuredClone(nonwearMarkers),
              isNoSleep,
              needsConsensus,
              notes,
              selectedPeriodIndex,
              timestamp: Date.now(),
            };
            // Only push if different from last snapshot
            const last = markerHistory[markerHistoryIndex];
            if (JSON.stringify(last?.sleepMarkers) !== JSON.stringify(currentSnapshot.sleepMarkers) ||
                JSON.stringify(last?.nonwearMarkers) !== JSON.stringify(currentSnapshot.nonwearMarkers)) {
              const newHistory = [...markerHistory, currentSnapshot];
              set({ markerHistory: newHistory, markerHistoryIndex: newHistory.length - 1 });
              // Now undo from the newly pushed position
              const snapshot = newHistory[newHistory.length - 2];
              if (snapshot) {
                set({
                  sleepMarkers: structuredClone(snapshot.sleepMarkers),
                  nonwearMarkers: structuredClone(snapshot.nonwearMarkers),
                  isNoSleep: snapshot.isNoSleep,
                  needsConsensus: snapshot.needsConsensus,
                  notes: snapshot.notes,
                  selectedPeriodIndex: snapshot.selectedPeriodIndex,
                  isDirty: true,
                  markerHistoryIndex: newHistory.length - 2,
                });
              }
              return;
            }
          }

          const newIndex = markerHistoryIndex - 1;
          if (newIndex < 0) return;
          const snapshot = markerHistory[newIndex];
          set({
            sleepMarkers: structuredClone(snapshot.sleepMarkers),
            nonwearMarkers: structuredClone(snapshot.nonwearMarkers),
            isNoSleep: snapshot.isNoSleep,
            needsConsensus: snapshot.needsConsensus,
            notes: snapshot.notes,
            selectedPeriodIndex: snapshot.selectedPeriodIndex,
            isDirty: true,
            markerHistoryIndex: newIndex,
          });
        },

        redo: () => {
          const { markerHistory, markerHistoryIndex } = get();
          const newIndex = markerHistoryIndex + 1;
          if (newIndex >= markerHistory.length) return;
          const snapshot = markerHistory[newIndex];
          set({
            sleepMarkers: structuredClone(snapshot.sleepMarkers),
            nonwearMarkers: structuredClone(snapshot.nonwearMarkers),
            isNoSleep: snapshot.isNoSleep,
            needsConsensus: snapshot.needsConsensus,
            notes: snapshot.notes,
            selectedPeriodIndex: snapshot.selectedPeriodIndex,
            isDirty: true,
            markerHistoryIndex: newIndex,
          });
        },

        canUndo: () => {
          const { markerHistoryIndex } = get();
          return markerHistoryIndex > 0;
        },

        canRedo: () => {
          const { markerHistory, markerHistoryIndex } = get();
          return markerHistoryIndex < markerHistory.length - 1;
        },

        beginDragTransaction: () => {
          get().pushMarkerSnapshot();
          set({ _isDragTransaction: true });
        },

        commitDragTransaction: () => {
          set({ _isDragTransaction: false });
        },

        clearAllMarkers: () => {
          get().pushMarkerSnapshot();
          set({
            sleepMarkers: [],
            nonwearMarkers: [],
            isDirty: true,
            selectedPeriodIndex: null,
          });
        },

        // Preferences actions
        setPreferredDisplayColumn: (column) =>
          set({ preferredDisplayColumn: column }),

        setViewModeHours: (hours) => set({ viewModeHours: hours }),

        setCurrentAlgorithm: (algorithm) =>
          set({ currentAlgorithm: algorithm }),

        setShowAdjacentMarkers: (show) => set({ showAdjacentMarkers: show }),

        setShowNonwearOverlays: (show) => set({ showNonwearOverlays: show }),

        setAutoScoreOnNavigate: (enabled) => set({ autoScoreOnNavigate: enabled }),

        setAutoNonwearOnNavigate: (enabled) => set({ autoNonwearOnNavigate: enabled }),

        // Study settings actions
        setSleepDetectionRule: (rule) => set({ sleepDetectionRule: rule }),

        setNightHours: (startHour, endHour) =>
          set({ nightStartHour: startHour, nightEndHour: endHour }),

        // Data settings actions
        setDevicePreset: (preset) => set({ devicePreset: preset }),

        setEpochLengthSeconds: (seconds) => set({ epochLengthSeconds: seconds }),

        setSkipRows: (rows) => set({ skipRows: rows }),

        // Upload actions
        setUploadProgress: (progress) => set({ uploadProgress: progress }),
        setUploadResult: (result) => set({ uploadResult: result }),
        setIsUploading: (uploading) => set({ isUploading: uploading }),

        // Color theme state
        colorTheme: { ...DEFAULT_COLOR_THEME },

        // Color theme actions
        setColorTheme: (updates) =>
          set((state) => ({
            colorTheme: { ...state.colorTheme, ...updates, preset: "custom" },
          })),

        applyColorPreset: (presetName) => {
          const preset = COLOR_PRESETS[presetName];
          if (preset) set({ colorTheme: { ...preset } });
        },

        resetColorTheme: () => set({ colorTheme: { ...DEFAULT_COLOR_THEME } }),
      }),
      {
        name: "sleep-scoring-storage", // fallback key; overridden by dynamic storage below
        storage: {
          getItem: (name) => {
            const wsId = getActiveWorkspaceId();
            const key = wsId ? `sleep-scoring-storage-${wsId}` : name;
            const str = localStorage.getItem(key);
            return str ? JSON.parse(str) : null;
          },
          setItem: (name, value) => {
            const wsId = getActiveWorkspaceId();
            const key = wsId ? `sleep-scoring-storage-${wsId}` : name;
            localStorage.setItem(key, JSON.stringify(value));
          },
          removeItem: (name) => {
            const wsId = getActiveWorkspaceId();
            const key = wsId ? `sleep-scoring-storage-${wsId}` : name;
            localStorage.removeItem(key);
          },
        },
        partialize: (state) => ({
          // Only persist these fields
          sitePassword: state.sitePassword,
          username: state.username,
          isAuthenticated: state.isAuthenticated,
          // isAdmin intentionally NOT persisted — re-fetched from /auth/me on login
          // Current file/date selection (restored on page refresh)
          currentFileId: state.currentFileId,
          currentFilename: state.currentFilename,
          currentFileSource: state.currentFileSource,
          currentDateIndex: state.currentDateIndex,
          // Preferences
          preferredDisplayColumn: state.preferredDisplayColumn,
          viewModeHours: state.viewModeHours,
          currentAlgorithm: state.currentAlgorithm,
          showAdjacentMarkers: state.showAdjacentMarkers,
          showNonwearOverlays: state.showNonwearOverlays,
          autoScoreOnNavigate: state.autoScoreOnNavigate,
          autoNonwearOnNavigate: state.autoNonwearOnNavigate,
          // Study settings
          sleepDetectionRule: state.sleepDetectionRule,
          nightStartHour: state.nightStartHour,
          nightEndHour: state.nightEndHour,
          // Data settings
          devicePreset: state.devicePreset,
          epochLengthSeconds: state.epochLengthSeconds,
          skipRows: state.skipRows,
          // Color theme
          colorTheme: state.colorTheme,
        }),
      }
    ),
    { name: "SleepScoringStore" }
  )
);

// Selector hooks for specific state slices
// Using useShallow to prevent infinite re-renders from object selectors
export const useAuth = () =>
  useSleepScoringStore(
    useShallow((state) => ({
      sitePassword: state.sitePassword,
      username: state.username,
      isAuthenticated: state.isAuthenticated,
      isAdmin: state.isAdmin,
      setAuth: state.setAuth,
      setIsAdmin: state.setIsAdmin,
      clearAuth: state.clearAuth,
    }))
  );

export const useFiles = () =>
  useSleepScoringStore(
    useShallow((state) => ({
      currentFileId: state.currentFileId,
      currentFilename: state.currentFilename,
      availableFiles: state.availableFiles,
      setCurrentFile: state.setCurrentFile,
      setAvailableFiles: state.setAvailableFiles,
    }))
  );

export const useActivityData = () =>
  useSleepScoringStore(
    useShallow((state) => ({
      timestamps: state.timestamps,
      axisX: state.axisX,
      axisY: state.axisY,
      axisZ: state.axisZ,
      vectorMagnitude: state.vectorMagnitude,
      algorithmResults: state.algorithmResults,
      nonwearResults: state.nonwearResults,
      sensorNonwearPeriods: state.sensorNonwearPeriods,
      isLoading: state.isLoading,
      preferredDisplayColumn: state.preferredDisplayColumn,
      viewStart: state.viewStart,
      viewEnd: state.viewEnd,
      setActivityData: state.setActivityData,
      setLoading: state.setLoading,
    }))
  );

export const useDates = () =>
  useSleepScoringStore(
    useShallow((state) => ({
      currentDateIndex: state.currentDateIndex,
      availableDates: state.availableDates,
      currentDate: state.availableDates[state.currentDateIndex] ?? null,
      setAvailableDates: state.setAvailableDates,
      setCurrentDateIndex: state.setCurrentDateIndex,
      navigateDate: state.navigateDate,
    }))
  );

export const useMarkers = () =>
  useSleepScoringStore(
    useShallow((state) => ({
      // Marker data
      sleepMarkers: state.sleepMarkers,
      nonwearMarkers: state.nonwearMarkers,
      isDirty: state.isDirty,
      selectedPeriodIndex: state.selectedPeriodIndex,
      isNoSleep: state.isNoSleep,
      needsConsensus: state.needsConsensus,
      notes: state.notes,

      // Two-click creation state
      markerMode: state.markerMode,
      creationMode: state.creationMode,
      pendingOnsetTimestamp: state.pendingOnsetTimestamp,

      // Save status
      isSaving: state.isSaving,
      lastSavedAt: state.lastSavedAt,
      saveError: state.saveError,

      // Basic marker actions
      setSleepMarkers: state.setSleepMarkers,
      setNonwearMarkers: state.setNonwearMarkers,
      setMarkersDirty: state.setMarkersDirty,
      setSelectedPeriod: state.setSelectedPeriod,
      setIsNoSleep: state.setIsNoSleep,
      setNeedsConsensus: state.setNeedsConsensus,
      setNotes: state.setNotes,

      // Two-click creation actions
      setMarkerMode: state.setMarkerMode,
      handlePlotClick: state.handlePlotClick,
      cancelMarkerCreation: state.cancelMarkerCreation,
      addSleepMarker: state.addSleepMarker,
      addNonwearMarker: state.addNonwearMarker,
      updateMarker: state.updateMarker,
      deleteMarker: state.deleteMarker,

      // Save status actions
      setSaving: state.setSaving,
      setSaveError: state.setSaveError,
      markSaved: state.markSaved,

      // Undo/redo
      undo: state.undo,
      redo: state.redo,
      canUndo: state.canUndo,
      canRedo: state.canRedo,
    }))
  );

export const useColorTheme = () =>
  useSleepScoringStore(
    useShallow((state) => ({
      colorTheme: state.colorTheme,
      setColorTheme: state.setColorTheme,
      applyColorPreset: state.applyColorPreset,
      resetColorTheme: state.resetColorTheme,
    }))
  );
