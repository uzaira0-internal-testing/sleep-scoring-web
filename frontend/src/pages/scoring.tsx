import { useEffect, useCallback, useRef, useState } from "react";
import { useQuery, useQueries, useMutation } from "@tanstack/react-query";
import { Panel, Group, Separator, useDefaultLayout } from "react-resizable-panels";
import { ChevronLeft, ChevronRight, Loader2, Moon, Watch, Trash2, FileText, X, Ban, Check, CircleDot, GripVertical, GripHorizontal, Wand2, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useConfirmDialog, useAlertDialog } from "@/components/ui/confirm-dialog";
import { Select } from "@/components/ui/select";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { useSleepScoringStore, useMarkers } from "@/store";
import { ActivityPlot } from "@/components/activity-plot";
import { ConsensusVoteSidebar } from "@/components/consensus-vote-sidebar";
import { MarkerDataTable } from "@/components/marker-data-table";
import { PopoutTableDialog } from "@/components/popout-table-dialog";
import { ColorLegendDialog, ColorLegendButton } from "@/components/color-legend-dialog";
import { KeyboardShortcutsDialog, KeyboardShortcutsButton } from "@/components/keyboard-shortcuts-dialog";
import { DiaryPanel } from "@/components/diary-panel";
import { ColorThemePopover } from "@/components/color-theme-popover";
// MetricsPanel and ConsensusPanel hidden by default — available via popout if needed
import { useKeyboardShortcuts, useMarkerAutoSave, useMarkerLoad, useColorThemeSync } from "@/hooks";
import { getApiBase, fetchWithAuth, settingsApi } from "@/api/client";
import { studySettingsQueryOptions } from "@/api/query-options";
import { MARKER_TYPES, type DateStatus, type ConsensusBallotCandidate } from "@/api/types";
import { formatTime, formatDuration } from "@/utils/formatters";
import { resolveEditedTimeToTimestamp } from "@/utils/time-edit";
import {
  ACTIVITY_SOURCE_OPTIONS,
  VIEW_MODE_OPTIONS,
} from "@/constants/options";
import { useDataSource } from "@/contexts/data-source-context";
import type { AutoScoreResult, AutoNonwearResult } from "@/services/data-source";
import { getLocalStudySettings } from "@/db";

/**
 * Main scoring page with activity plot and marker controls
 * Includes integrated file selection dropdown
 */
export function ScoringPage() {
  const [onsetPopoutOpen, setOnsetPopoutOpen] = useState(false);
  const [offsetPopoutOpen, setOffsetPopoutOpen] = useState(false);
  const [colorLegendOpen, setColorLegendOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [showComparisonMarkers, setShowComparisonMarkers] = useState(false);
  const [highlightedCandidateId, setHighlightedCandidateId] = useState<number | null>(null);
  const [isConsensusCollapsed, setIsConsensusCollapsed] = useState(false);
  const [autoScoreResult, setAutoScoreResult] = useState<AutoScoreResult | null>(null);
  const [autoNonwearResult, setAutoNonwearResult] = useState<AutoNonwearResult | null>(null);
  const [editingOnset, setEditingOnset] = useState<string | null>(null);
  const [editingOffset, setEditingOffset] = useState<string | null>(null);
  const [complexityBreakdown, setComplexityBreakdown] = useState<{
    complexity_pre: number | null;
    complexity_post: number | null;
    features: Record<string, unknown>;
  } | null>(null);

  // Styled dialog replacements for native confirm/alert
  const { confirm, confirmDialog } = useConfirmDialog();
  const { alert, alertDialog } = useAlertDialog();

  // Enable auto-save for markers
  const { saveNow } = useMarkerAutoSave();

  // Ctrl+Shift+C clear handler using styled confirm dialog
  const handleConfirmClear = useCallback(async () => {
    const ok = await confirm({ title: "Clear Markers", description: "Clear all markers for this date?", variant: "destructive", confirmLabel: "Clear All" });
    if (ok) {
      useSleepScoringStore.getState().clearAllMarkers();
    }
  }, [confirm]);

  // Enable keyboard shortcuts (pass save function for Ctrl+S)
  useKeyboardShortcuts(saveNow, handleConfirmClear);

  // Load markers from database when file/date changes
  useMarkerLoad();

  // Sync color theme to server (debounced) and update CSS variables
  useColorThemeSync();

  // DataSource DI — routes all data operations through local or server
  const { dataSource, isLocal } = useDataSource();

  // Use individual selectors to avoid object recreation
  const currentFileId = useSleepScoringStore((state) => state.currentFileId);
  const currentFilename = useSleepScoringStore((state) => state.currentFilename);
  const currentDateIndex = useSleepScoringStore((state) => state.currentDateIndex);
  const availableDates = useSleepScoringStore((state) => state.availableDates);
  const preferredDisplayColumn = useSleepScoringStore((state) => state.preferredDisplayColumn);
  const viewModeHours = useSleepScoringStore((state) => state.viewModeHours);
  const currentAlgorithm = useSleepScoringStore((state) => state.currentAlgorithm);
  const setPreferredDisplayColumn = useSleepScoringStore((state) => state.setPreferredDisplayColumn);
  const setViewModeHours = useSleepScoringStore((state) => state.setViewModeHours);
  const showAdjacentMarkers = useSleepScoringStore((state) => state.showAdjacentMarkers);
  const setShowAdjacentMarkers = useSleepScoringStore((state) => state.setShowAdjacentMarkers);
  const showNonwearOverlays = useSleepScoringStore((state) => state.showNonwearOverlays);
  const setShowNonwearOverlays = useSleepScoringStore((state) => state.setShowNonwearOverlays);
  const autoScoreOnNavigate = useSleepScoringStore((state) => state.autoScoreOnNavigate);
  const setAutoScoreOnNavigate = useSleepScoringStore((state) => state.setAutoScoreOnNavigate);
  const autoNonwearOnNavigate = useSleepScoringStore((state) => state.autoNonwearOnNavigate);
  const sleepDetectionRule = useSleepScoringStore((state) => state.sleepDetectionRule);
  // Sidebar panels (sleep markers, nonwear, metrics) are hidden by default
  const username = useSleepScoringStore((state) => state.username);

  // Persist panel layout per user + resolution bucket
  const resBucket = typeof window !== "undefined"
    ? `${Math.round(window.innerWidth / 100) * 100}x${Math.round(window.innerHeight / 100) * 100}`
    : "default";
  const layoutKey = `scoring-layout:${username || "anon"}:${resBucket}`;
  const verticalLayout = useDefaultLayout({ id: `${layoutKey}:v`, storage: localStorage });
  const horizontalLayout = useDefaultLayout({ id: `${layoutKey}:h`, storage: localStorage });
  const bottomLayout = useDefaultLayout({ id: `${layoutKey}:b`, storage: localStorage });

  const currentDate = availableDates[currentDateIndex] ?? null;
  const weekdayLabel = currentDate
    ? new Date(currentDate + "T12:00:00Z").toLocaleDateString("en-US", { weekday: "long", timeZone: "UTC" })
    : null;

  // Get stable action references
  const setAvailableDates = useSleepScoringStore((state) => state.setAvailableDates);
  const setActivityData = useSleepScoringStore((state) => state.setActivityData);
  const navigateDate = useSleepScoringStore((state) => state.navigateDate);
  const setCurrentFile = useSleepScoringStore((state) => state.setCurrentFile);
  const setAvailableFiles = useSleepScoringStore((state) => state.setAvailableFiles);

  // Marker state
  const {
    sleepMarkers,
    nonwearMarkers,
    markerMode,
    creationMode,
    selectedPeriodIndex,
    isDirty,
    isSaving,
    isNoSleep,
    needsConsensus,
    setMarkerMode,
    cancelMarkerCreation,
    updateMarker,
    notes,
    setNeedsConsensus,
    setNotes,
    setSleepMarkers,
    setNonwearMarkers,
  } = useMarkers();

  // Fetch files list via DataSource
  const { data: dsFiles, isLoading: filesLoading } = useQuery({
    queryKey: ["files", isLocal ? "local" : "server"],
    queryFn: () => dataSource.listFiles(),
  });

  // Study settings (for auto-nonwear threshold)
  const { data: studySettings } = useQuery({
    ...studySettingsQueryOptions(),
    queryFn: settingsApi.getStudySettings,
    enabled: !isLocal,
  });
  // Local study settings from IndexedDB
  const { data: localStudySettings } = useQuery({
    queryKey: ["local-study-settings"],
    queryFn: getLocalStudySettings,
    enabled: isLocal,
  });
  const nonwearThreshold = isLocal
    ? (localStudySettings?.extraSettings?.nonwear_threshold as number | undefined)
    : (studySettings?.extra_settings as Record<string, unknown>)?.nonwear_threshold as number | undefined;

  // Update available files when dsFiles changes
  useEffect(() => {
    if (dsFiles && dsFiles.length > 0) {
      setAvailableFiles(
        dsFiles.map((f) => ({
          id: f.id,
          filename: f.filename,
          status: f.status ?? "ready",
          rowCount: null,
        }))
      );

      // Auto-select first file if none selected
      if (!currentFileId) {
        const firstReadyFile = isLocal
          ? dsFiles[0]
          : dsFiles.find((f) => f.status === "ready");
        if (firstReadyFile) {
          setCurrentFile(firstReadyFile.id, firstReadyFile.filename, firstReadyFile.source);
        }
      }
    }
  }, [dsFiles, currentFileId, isLocal, setAvailableFiles, setCurrentFile]);

  // Auto-score mutation — unified via DataSource
  const autoScoreMutation = useMutation({
    mutationFn: async (): Promise<AutoScoreResult> => {
      if (!currentFileId || !currentDate) throw new Error("No file/date selected");
      return dataSource.autoScore(currentFileId, currentDate, {
        algorithm: currentAlgorithm,
        detectionRule: sleepDetectionRule,
      });
    },
  });
  useEffect(() => {
    if (!autoScoreMutation.data || !autoScoreMutation.isSuccess) return;
    const data = autoScoreMutation.data;
    setAutoScoreResult(data);
  }, [autoScoreMutation.data, autoScoreMutation.isSuccess]);
  useEffect(() => {
    if (autoScoreMutation.error) {
      alert({ title: "Auto-Score Failed", description: (autoScoreMutation.error as Error).message });
    }
  }, [autoScoreMutation.error, alert]);

  // Auto-nonwear mutation — unified via DataSource
  const autoNonwearMutation = useMutation({
    mutationFn: async (): Promise<AutoNonwearResult> => {
      if (!currentFileId || !currentDate) throw new Error("No file/date selected");
      const state = useSleepScoringStore.getState();
      const existingSleepMarkers: Array<[number, number]> = state.sleepMarkers
        .filter((m) => m.onsetTimestamp != null && m.offsetTimestamp != null)
        .map((m) => [m.onsetTimestamp!, m.offsetTimestamp!]);
      return dataSource.autoNonwear(currentFileId, currentDate, {
        threshold: nonwearThreshold ?? 0,
        existingSleepMarkers,
      });
    },
  });
  useEffect(() => {
    if (!autoNonwearMutation.data || !autoNonwearMutation.isSuccess) return;
    const data = autoNonwearMutation.data;
    if (data.nonwear_markers.length > 0) {
      setAutoNonwearResult(data);
    }
  }, [autoNonwearMutation.data, autoNonwearMutation.isSuccess]);
  useEffect(() => {
    if (autoNonwearMutation.error) {
      alert({ title: "Auto-Nonwear Failed", description: (autoNonwearMutation.error as Error).message });
    }
  }, [autoNonwearMutation.error, alert]);

  // Normalize saved auto-score payload (single marker list) into dialog shape.
  // Apply auto-scored markers (only if no existing markers)
  const applyAutoScore = useCallback(() => {
    if (!autoScoreResult) return;
    if (sleepMarkers.length > 0) return;
    const allMarkers = [...autoScoreResult.sleep_markers, ...autoScoreResult.nap_markers];
    const newMarkers = allMarkers.map((m, i) => ({
      onsetTimestamp: m.onset_timestamp,
      offsetTimestamp: m.offset_timestamp,
      markerIndex: i + 1,
      markerType: m.marker_type as "MAIN_SLEEP" | "NAP",
    }));
    setSleepMarkers(newMarkers);
    if (newMarkers.length > 0) {
      useSleepScoringStore.setState({ selectedPeriodIndex: 0, markerMode: "sleep" });
    }
    setAutoScoreResult(null);
  }, [autoScoreResult, setSleepMarkers, sleepMarkers.length]);

  const applyAutoNonwear = useCallback(() => {
    if (!autoNonwearResult || autoNonwearResult.nonwear_markers.length === 0) return;
    if (nonwearMarkers.length > 0) return; // Don't overwrite existing
    const newMarkers = autoNonwearResult.nonwear_markers.map((m, i) => ({
      startTimestamp: m.start_timestamp,
      endTimestamp: m.end_timestamp,
      markerIndex: i + 1,
    }));
    setNonwearMarkers(newMarkers);
    setAutoNonwearResult(null);
  }, [autoNonwearResult, nonwearMarkers.length, setNonwearMarkers]);

  useEffect(() => {
    if (showComparisonMarkers) return;
    setHighlightedCandidateId(null);
  }, [showComparisonMarkers]);

  useEffect(() => {
    setHighlightedCandidateId(null);
    setAutoScoreResult(null);
    setAutoNonwearResult(null);
  }, [currentFileId, currentDate]);

  const copyCandidateMarkers = useCallback(async (candidate: ConsensusBallotCandidate) => {
    // Read fresh state via getState() to avoid stale closure after await
    const preState = useSleepScoringStore.getState();
    const hasExisting = preState.sleepMarkers.length > 0 || preState.nonwearMarkers.length > 0 || preState.isNoSleep;
    if (hasExisting) {
      const ok = await confirm({ title: "Replace Markers", description: "Replace your current markers with this candidate set?" });
      if (!ok) return;
    }

    // Batch all state changes into a single atomic update to avoid
    // intermediate auto-saves with stale data (each individual setter
    // triggers isDirty + pushMarkerSnapshot separately).
    const store = useSleepScoringStore.getState();
    store.pushMarkerSnapshot();

    if (candidate.is_no_sleep) {
      const copiedNaps = (candidate.sleep_markers_json ?? [])
        .filter((m) => m.marker_type === "NAP" && m.onset_timestamp != null)
        .sort((a, b) => (a.marker_index ?? 9999) - (b.marker_index ?? 9999))
        .map((m, i) => ({
          onsetTimestamp: Number(m.onset_timestamp),
          offsetTimestamp: m.offset_timestamp != null ? Number(m.offset_timestamp) : null,
          markerIndex: i + 1,
          markerType: MARKER_TYPES.NAP,
        }));
      const copiedNonwear = (candidate.nonwear_markers_json ?? [])
        .filter((m) => m.start_timestamp != null)
        .sort((a, b) => (a.marker_index ?? 9999) - (b.marker_index ?? 9999))
        .map((m, i) => ({
          startTimestamp: Number(m.start_timestamp),
          endTimestamp: m.end_timestamp != null ? Number(m.end_timestamp) : null,
          markerIndex: i + 1,
        }));
      useSleepScoringStore.setState({
        isNoSleep: true,
        sleepMarkers: copiedNaps,
        nonwearMarkers: copiedNonwear,
        isDirty: true,
        selectedPeriodIndex: copiedNaps.length > 0 ? 0 : null,
        markerMode: "sleep",
      });
      return;
    }

    const copiedSleepMarkers = (candidate.sleep_markers_json ?? [])
      .filter((m) => m.onset_timestamp != null)
      .sort((a, b) => (a.marker_index ?? 9999) - (b.marker_index ?? 9999))
      .map((m, i) => ({
        onsetTimestamp: Number(m.onset_timestamp),
        offsetTimestamp: m.offset_timestamp != null ? Number(m.offset_timestamp) : null,
        markerIndex: m.marker_index != null ? Number(m.marker_index) : i + 1,
        markerType: (m.marker_type === "NAP" ? "NAP" : "MAIN_SLEEP") as "MAIN_SLEEP" | "NAP",
      }));

    const copiedNonwearMarkers = (candidate.nonwear_markers_json ?? [])
      .filter((m) => m.start_timestamp != null)
      .sort((a, b) => (a.marker_index ?? 9999) - (b.marker_index ?? 9999))
      .map((m, i) => ({
        startTimestamp: Number(m.start_timestamp),
        endTimestamp: m.end_timestamp != null ? Number(m.end_timestamp) : null,
        markerIndex: m.marker_index != null ? Number(m.marker_index) : i + 1,
      }));

    useSleepScoringStore.setState({
      isNoSleep: false,
      sleepMarkers: copiedSleepMarkers,
      nonwearMarkers: copiedNonwearMarkers,
      isDirty: true,
      selectedPeriodIndex: copiedSleepMarkers.length > 0 ? 0 : null,
      markerMode: "sleep",
    });
  }, [confirm]);

  const autoScoreRef = useRef(false);
  // Track which file+date already had auto-score attempted (prevents re-trigger after cancel)
  const autoScoredKeyRef = useRef<string | null>(null);

  // Handle file selection from dropdown
  const handleFileChange = useCallback(
    (value: string) => {
      const fileId = parseInt(value, 10);
      const file = dsFiles?.find((f) => f.id === fileId);
      if (file) {
        setCurrentFile(file.id, file.filename, file.source);
      }
    },
    [dsFiles, setCurrentFile]
  );

  // Fetch available dates for the file via DataSource
  const { data: datesData } = useQuery({
    queryKey: ["dates", currentFileId, isLocal ? "local" : "server"],
    queryFn: () => dataSource.listDates(currentFileId!),
    enabled: !!currentFileId,
  });

  // Update store when dates are fetched (only when datesData changes)
  useEffect(() => {
    if (datesData && datesData.length > 0) {
      setAvailableDates(datesData);
    }
  }, [datesData]); // eslint-disable-line react-hooks/exhaustive-deps

  // Dates-status: unified via DataSource
  const { data: datesStatus } = useQuery({
    queryKey: ["dates-status", currentFileId, username || "anonymous", isLocal ? "local" : "server"],
    queryFn: async (): Promise<DateStatus[]> => {
      if (!currentFileId || !availableDates.length) return [];
      return dataSource.listDatesStatus(currentFileId, availableDates, username || "anonymous");
    },
    enabled: !!currentFileId && availableDates.length > 0,
    staleTime: isLocal ? 30000 : 10000,
    refetchInterval: isLocal ? false : 30_000,
    refetchIntervalInBackground: false,
  });

  // Build a map for quick lookup
  const dateStatusMap = new Map(
    (datesStatus ?? []).map((d) => [d.date, d])
  );

  // Diary availability check for auto-score.
  // complexity_pre === -1 means no/incomplete diary for this date.
  // Use complexity_pre (not _post) because _post can be 0 after markers are saved,
  // masking the missing diary. undefined means status hasn't loaded yet.
  // Block auto-score in ALL these cases.
  const currentDateStatus = currentDate ? dateStatusMap.get(currentDate) : undefined;
  const hasNoDiary = !currentDateStatus || currentDateStatus.complexity_pre === -1;

  // Auto-score on date navigate (when toggle is on and no existing markers)
  // Skip dates with infinite complexity (no/incomplete diary)
  // NOTE: This useEffect MUST be below dateStatusMap/hasNoDiary to avoid TDZ errors.
  const autoScoreMutationRef = useRef(autoScoreMutation);
  autoScoreMutationRef.current = autoScoreMutation; // eslint-disable-line react-hooks/refs -- Direct assignment, not Zustand state
  useEffect(() => {
    if (!autoScoreOnNavigate || !currentFileId || !currentDate || isNoSleep || hasNoDiary) return;
    // Skip if markers already exist or mutation is already running
    if (sleepMarkers.length > 0 || autoScoreMutation.isPending) return;
    // Skip if already attempted for this file+date (e.g. user cancelled the dialog)
    const key = `${currentFileId}-${currentDate}`;
    if (autoScoredKeyRef.current === key) return;
    // Debounce: wait a tick for marker load to complete
    const timer = setTimeout(() => {
      const state = useSleepScoringStore.getState();
      if (state.sleepMarkers.length > 0) return; // Markers loaded from DB
      if (autoScoreMutationRef.current.isPending) return; // Already in-flight
      autoScoredKeyRef.current = key;
      autoScoreRef.current = true;
      autoScoreMutationRef.current.mutate();
    }, 500);
    return () => clearTimeout(timer);
  }, [currentFileId, currentDate, autoScoreOnNavigate, isNoSleep, hasNoDiary, sleepMarkers.length, autoScoreMutation.isPending]);

  // Auto-nonwear on date navigate (when toggle is on and no existing nonwear markers)
  const autoNonwearMutationRef = useRef(autoNonwearMutation);
  autoNonwearMutationRef.current = autoNonwearMutation; // eslint-disable-line react-hooks/refs -- Direct assignment, not Zustand state
  const autoNonwearKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (!autoNonwearOnNavigate || !currentFileId || !currentDate) return;
    if (nonwearMarkers.length > 0 || autoNonwearMutation.isPending) return;
    const key = `nw-${currentFileId}-${currentDate}`;
    if (autoNonwearKeyRef.current === key) return;
    const timer = setTimeout(() => {
      const state = useSleepScoringStore.getState();
      if (state.nonwearMarkers.length > 0) return;
      if (autoNonwearMutationRef.current.isPending) return;
      autoNonwearKeyRef.current = key;
      autoNonwearMutationRef.current.mutate();
    }, 800); // Slightly longer delay than sleep auto-score to avoid race
    return () => clearTimeout(timer);
  }, [currentFileId, currentDate, autoNonwearOnNavigate, nonwearMarkers.length, autoNonwearMutation.isPending]);

  // Auto-score review mode: show dialog instead of silent apply
  // User must confirm before markers are applied (prevents accidental corruption)
  useEffect(() => {
    if (!autoScoreRef.current || !autoScoreResult) return;
    autoScoreRef.current = false;
    // Dialog is already shown via autoScoreResult state — user must click Apply or Cancel
  }, [autoScoreResult]);

  // Fetch activity data for current date with selected algorithm via DataSource
  const { data: activityData, isLoading: activityLoading, error: activityError } = useQuery({
    queryKey: ["activity", currentFileId, currentDate, viewModeHours, currentAlgorithm, isLocal ? "local" : "server"],
    queryFn: () =>
      dataSource.loadActivityData(currentFileId!, currentDate!, {
        algorithm: currentAlgorithm,
        viewHours: viewModeHours,
      }),
    enabled: !!currentFileId && !!currentDate,
  });

  // Update store when activity data is fetched
  useEffect(() => {
    if (activityData) {
      setActivityData({
        timestamps: activityData.timestamps,
        axisX: activityData.axisX,
        axisY: activityData.axisY,
        axisZ: activityData.axisZ,
        vectorMagnitude: activityData.vectorMagnitude,
        algorithmResults: activityData.algorithmResults ?? null,
        nonwearResults: activityData.nonwearResults ?? null,
        sensorNonwearPeriods: activityData.sensorNonwearPeriods ?? [],
        viewStart: activityData.viewStart,
        viewEnd: activityData.viewEnd,
      });
    }
  }, [activityData]); // eslint-disable-line react-hooks/exhaustive-deps

  // Log activity query errors
  useEffect(() => {
    if (activityError) {
      console.error("Failed to load activity data:", activityError instanceof Error ? activityError.message : activityError);
    }
  }, [activityError]);

  const commitTimeEdit = useCallback((field: "onset" | "offset", value: string) => {
    if (markerMode !== "sleep" || selectedPeriodIndex === null || !sleepMarkers[selectedPeriodIndex]) return;
    const marker = sleepMarkers[selectedPeriodIndex];
    const refTs = field === "onset" ? marker.onsetTimestamp : marker.offsetTimestamp;
    if (refTs === null) return;
    const counterpartTs = field === "onset" ? marker.offsetTimestamp : marker.onsetTimestamp;
    const newTs = resolveEditedTimeToTimestamp({
      timeStr: value,
      currentDate,
      referenceTimestamp: refTs,
      otherBoundaryTimestamp: counterpartTs,
      field,
    });
    if (newTs === null) return;

    if (field === "onset") {
      updateMarker("sleep", selectedPeriodIndex, { onsetTimestamp: newTs });
    } else {
      updateMarker("sleep", selectedPeriodIndex, { offsetTimestamp: newTs });
    }
  }, [markerMode, selectedPeriodIndex, sleepMarkers, currentDate, updateMarker]);

  const canGoPrev = currentDateIndex > 0;
  const canGoNext = currentDateIndex < availableDates.length - 1;

  // Consensus-only filter toggle
  const [consensusOnly, _setConsensusOnly] = useState(false);
  void _setConsensusOnly;

  // Fetch scoring progress per file (both server and local modes)
  const readyFiles = (dsFiles ?? []).filter((f) => isLocal || f.status === "ready");
  const fileProgressQueries = useQueries({
    queries: readyFiles.map((f) => ({
      queryKey: ["dates-status", f.id, username || "anonymous", isLocal ? "local" : "server"],
      queryFn: () => dataSource.listDatesStatus(f.id, f.available_dates ?? [], username || "anonymous"),
      enabled: !!f.id,
      staleTime: 30000,
    })),
  });

  const fileProgressMap = new Map<number, string>();
  readyFiles.forEach((f, i) => {
    const data = fileProgressQueries[i]?.data;
    if (data) {
      const scored = data.filter(d => d.has_markers || d.is_no_sleep).length;
      const noDiaryCount = data.filter(d => (d.complexity_post ?? d.complexity_pre) === -1).length;
      const noDiaryStr = noDiaryCount > 0 ? `, ${noDiaryCount} no diary` : "";
      fileProgressMap.set(f.id, `${scored}/${data.length} scored${noDiaryStr}`);
    }
  });

  // Build file options for dropdown — sorted alphabetically ascending by filename
  const fileOptions = (dsFiles ?? [])
    .filter((f) => isLocal || f.status === "ready")
    .sort((a, b) => a.filename.localeCompare(b.filename))
    .map((f) => ({
      value: String(f.id),
      label: fileProgressMap.has(f.id)
        ? `${f.filename} (${fileProgressMap.get(f.id)})`
        : f.filename,
      disabled: !isLocal && f.status !== "ready",
    }));

  // Show empty state
  if (!filesLoading && (!dsFiles || dsFiles.length === 0)) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6">
        <FileText className="h-16 w-16 text-muted-foreground mb-4" />
        <h2 className="text-xl font-semibold mb-2">
          {isLocal ? "No local files" : "No files assigned"}
        </h2>
        <p className="text-muted-foreground mb-6 text-center max-w-md">
          {isLocal
            ? "Open a file from Settings to start scoring."
            : "Request an admin to assign files to your account."}
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Row 1: File selector + algorithm settings */}
      <div className="flex-none px-4 py-2 border-b flex flex-wrap items-center gap-4 overflow-visible relative z-30">
        {/* File selector */}
        <div className="flex items-center gap-2 flex-none">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <SearchableSelect
            options={fileOptions}
            value={currentFileId ? String(currentFileId) : ""}
            onChange={handleFileChange}
            className="w-[560px] max-w-[60vw] min-w-[360px]"
            placeholder="Select a file..."
          />
        </div>

        <div className="h-5 w-px bg-border" />

        {/* Source, View */}
        <div className="flex items-center gap-3 flex-none">
          <div className="flex items-center gap-1.5">
            <Label className="text-xs text-muted-foreground">Source:</Label>
            <Select
              options={isLocal
                ? ACTIVITY_SOURCE_OPTIONS.filter((o) => o.value === "axis_y" || o.value === "vector_magnitude")
                : ACTIVITY_SOURCE_OPTIONS}
              value={preferredDisplayColumn}
              onChange={(e) => setPreferredDisplayColumn(e.target.value as "axis_x" | "axis_y" | "axis_z" | "vector_magnitude")}
              className="w-[140px]"
            />
          </div>
          <div className="flex items-center gap-1.5">
            <Label className="text-xs text-muted-foreground">View:</Label>
            <Select
              options={VIEW_MODE_OPTIONS}
              value={String(viewModeHours)}
              onChange={(e) => setViewModeHours(Number(e.target.value) as 24 | 48)}
              className="w-[110px]"
            />
          </div>
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Help buttons */}
        <div className="flex items-center gap-1 flex-none">
          <ColorThemePopover />
          <KeyboardShortcutsButton onClick={() => setShortcutsOpen(true)} />
          <ColorLegendButton onClick={() => setColorLegendOpen(true)} />
        </div>
      </div>

      {/* Row 2: Mode controls | Date navigation (centered) | Save/Clear */}
      <div className="flex-none px-4 py-1.5 border-b bg-muted/30 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3">
        {/* Left: Mode + Auto-Score */}
        <div className="min-w-0 flex flex-wrap items-center gap-2 justify-self-start">
          <div className="flex gap-1">
            <Button
              variant={markerMode === "sleep" ? "default" : "outline"}
              size="sm"
              className="h-7 text-xs px-2 shrink-0"
              onClick={() => setMarkerMode("sleep")}
              title={isNoSleep ? "Place nap markers (no main sleep)" : undefined}
            >
              <Moon className="h-3.5 w-3.5 mr-1" />
              {isNoSleep ? "Nap" : "Sleep"}
            </Button>
            <Button
              variant={markerMode === "nonwear" ? "default" : "outline"}
              size="sm"
              className="h-7 text-xs px-2 shrink-0"
              onClick={() => setMarkerMode("nonwear")}
            >
              <Watch className="h-3.5 w-3.5 mr-1" />
              Nonwear
            </Button>
          </div>

          <Button
            variant={isNoSleep ? "default" : "outline"}
            size="sm"
            className={`h-7 text-xs px-2 shrink-0 ${isNoSleep ? "bg-amber-600 hover:bg-amber-700" : ""}`}
            onClick={async () => {
              const state = useSleepScoringStore.getState();
              if (!state.isNoSleep) {
                const hasMainSleep = state.sleepMarkers.some(m => m.markerType === MARKER_TYPES.MAIN_SLEEP);
                if (hasMainSleep) {
                  const ok = await confirm({ title: "No Sleep", description: "Marking as 'No Sleep' will clear main sleep markers. Nap markers will be preserved. Continue?", variant: "destructive", confirmLabel: "Clear & Mark" });
                  if (!ok) return;
                }
                useSleepScoringStore.getState().setIsNoSleep(true);
              } else {
                state.setIsNoSleep(false);
              }
            }}
            title={isNoSleep ? "Click to allow main sleep markers" : "Mark this date as having no main sleep"}
          >
            <Ban className="h-3.5 w-3.5 mr-1" />
            No Sleep
          </Button>

          <Button
            variant={needsConsensus ? "default" : "outline"}
            size="sm"
            className={`h-7 text-xs px-2 shrink-0 ${needsConsensus ? "bg-orange-600 hover:bg-orange-700" : ""}`}
            onClick={() => setNeedsConsensus(!needsConsensus)}
            title={needsConsensus ? "Remove consensus flag" : "Flag for consensus review"}
            disabled={!currentFileId || !currentDate}
          >
            <Users className="h-3.5 w-3.5 mr-1" />
            Consensus
          </Button>

          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Notes..."
            disabled={!currentFileId || !currentDate}
            className="h-7 text-xs px-2 rounded-md border border-border bg-background min-w-[120px] max-w-[200px] flex-shrink placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
            title="Annotation notes (auto-saved)"
          />

          <div className="h-4 w-px bg-border shrink-0" />

          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs px-2 shrink-0"
            onClick={() => { autoScoreRef.current = false; autoScoreMutation.mutate(); }}
            disabled={!currentFileId || !currentDate || autoScoreMutation.isPending || isNoSleep || hasNoDiary}
            title={hasNoDiary ? "Cannot auto-score: no diary data for this date" : "Automatically detect and suggest sleep marker placements"}
          >
            {autoScoreMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
            ) : (
              <Wand2 className="h-3.5 w-3.5 mr-1" />
            )}
            Auto Sleep
          </Button>
          <div className="flex items-center gap-1 shrink-0">
            <Checkbox
              checked={autoScoreOnNavigate}
              onCheckedChange={(checked) => setAutoScoreOnNavigate(!!checked)}
            />
            <Label className="text-[11px] cursor-pointer" onClick={() => setAutoScoreOnNavigate(!autoScoreOnNavigate)}>
              Auto
            </Label>
          </div>

          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs px-2 shrink-0"
            onClick={() => { autoNonwearMutation.mutate(); }}
            disabled={!currentFileId || !currentDate || autoNonwearMutation.isPending}
            title="Automatically detect nonwear periods from diary + Choi/sensor signals"
          >
            {autoNonwearMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
            ) : (
              <Wand2 className="h-3.5 w-3.5 mr-1" />
            )}
            Auto Nonwear
          </Button>
          <div className="flex items-center gap-1 shrink-0">
            <Checkbox
              checked={autoNonwearOnNavigate}
              onCheckedChange={(checked) => useSleepScoringStore.getState().setAutoNonwearOnNavigate(!!checked)}
            />
            <Label className="text-[11px] cursor-pointer" onClick={() => useSleepScoringStore.getState().setAutoNonwearOnNavigate(!autoNonwearOnNavigate)}>
              Auto
            </Label>
          </div>

          <div className="h-4 w-px bg-border shrink-0" />

          <div className="flex items-center gap-1 shrink-0">
            <Checkbox
              checked={showAdjacentMarkers}
              onCheckedChange={(checked) => setShowAdjacentMarkers(checked)}
            />
            <Label className="text-[11px] cursor-pointer" onClick={() => setShowAdjacentMarkers(!showAdjacentMarkers)}>
              Adjacent
            </Label>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Checkbox
              checked={showComparisonMarkers}
              onCheckedChange={(checked) => setShowComparisonMarkers(!!checked)}
            />
            <Label className="text-[11px] cursor-pointer" onClick={() => setShowComparisonMarkers(!showComparisonMarkers)}>
              Compare
            </Label>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Checkbox
              checked={showNonwearOverlays}
              onCheckedChange={(checked) => setShowNonwearOverlays(checked)}
            />
            <Label className="text-[11px] cursor-pointer" onClick={() => setShowNonwearOverlays(!showNonwearOverlays)}>
              NW Overlays
            </Label>
          </div>

          {creationMode !== "idle" && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-[11px] px-2 shrink-0 border-amber-400/40 text-amber-700 bg-amber-50 hover:bg-amber-100 dark:border-amber-500/40 dark:text-amber-300 dark:bg-amber-500/10"
              title={`Click plot to set ${creationMode === "placing_onset" ? "offset" : "onset"}. Click to cancel.`}
              onClick={cancelMarkerCreation}
            >
              <X className="h-3 w-3 mr-1" />
              {creationMode === "placing_onset" ? "Set Offset" : "Set Onset"}
            </Button>
          )}
        </div>

        {/* Center: Date navigation — takes remaining space, centered */}
        <div className="flex items-center justify-center gap-2 justify-self-center">
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={() => navigateDate(-1)}
            disabled={!canGoPrev || !currentFileId}
            data-testid="prev-date-btn"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="relative w-[min(420px,50vw)] min-w-[280px]">
            <select
              className="w-full h-7 px-3 pr-8 rounded-md border border-input bg-background text-sm font-medium appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring"
              value={currentDateIndex}
              onChange={(e) => {
                const idx = parseInt(e.target.value, 10);
                if (idx !== currentDateIndex) {
                  useSleepScoringStore.getState().setCurrentDateIndex(idx);
                }
              }}
              disabled={!currentFileId || availableDates.length === 0}
            >
              {availableDates.map((date, idx) => {
                const st = dateStatusMap.get(date);
                if (consensusOnly && !st?.needs_consensus) return null;
                const consensusFlag = st?.needs_consensus ? "\ud83d\udc65 " : "";
                const prefix = st?.is_no_sleep ? "\u26d4 " : st?.has_markers ? "\u2713 " : "\u25cb ";
                const weekday = new Date(date + "T12:00:00Z").toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
                return (
                  <option key={date} value={idx}>
                    {consensusFlag}{prefix}{date} {weekday} ({idx + 1}/{availableDates.length})
                  </option>
                );
              })}
            </select>
            {currentDate && (() => {
              const st = dateStatusMap.get(currentDate);
              // Dot intentionally reflects marker state only.
              if (st?.is_no_sleep) return <span className="absolute right-8 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-amber-500" title="No sleep" />;
              if (st?.has_markers) return <span className="absolute right-8 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-green-500" title="Has markers" />;
              return <span className="absolute right-8 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-muted-foreground/30" title="No markers" />;
            })()}
            <ChevronRight className="absolute right-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none rotate-90" />
          </div>
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={() => navigateDate(1)}
            disabled={!canGoNext || !currentFileId}
            data-testid="next-date-btn"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
          {currentDate && (() => {
            const st = dateStatusMap.get(currentDate);
            const complexity = st?.complexity_post ?? st?.complexity_pre;
            if (complexity == null) return null;
            if (complexity === -1) {
              return (
                <span className="text-xs font-medium px-1.5 py-0.5 rounded text-purple-600 dark:text-purple-400 bg-purple-500/10 tabular-nums cursor-help" title="Incomplete diary — need both onset and wake to score">
                  ∞
                </span>
              );
            }
            const color = complexity >= 70 ? "text-green-600 dark:text-green-400 bg-green-500/10" : complexity >= 40 ? "text-yellow-600 dark:text-yellow-400 bg-yellow-500/10" : "text-red-600 dark:text-red-400 bg-red-500/10";
            return (
              <button
                className={`text-xs font-medium px-1.5 py-0.5 rounded ${color} tabular-nums cursor-pointer hover:ring-1 hover:ring-current transition-shadow`}
                title={`Scoring difficulty: ${complexity}/100 (higher = easier)${isLocal ? "" : "\nClick for breakdown"}`}
                onClick={async () => {
                  if (!currentFileId || !currentDate || isLocal) return;
                  try {
                    const data = await fetchWithAuth<{ complexity_pre: number | null; complexity_post: number | null; features: Record<string, unknown> }>(
                      `${getApiBase()}/files/${currentFileId}/${currentDate}/complexity`
                    );
                    setComplexityBreakdown(data);
                  } catch {
                    setComplexityBreakdown({ complexity_pre: complexity, complexity_post: null, features: { error: "Failed to load breakdown" } });
                  }
                }}
              >
                {complexity}
              </button>
            );
          })()}
        </div>

        {/* Right: Marker editor + Save/Clear */}
        <div className="min-w-0 flex flex-wrap items-center gap-3 justify-self-end">
          {/* Marker times display */}
          {markerMode === "sleep" && selectedPeriodIndex !== null && sleepMarkers[selectedPeriodIndex] && (
            <>
              <div className="flex items-center gap-1.5">
                <Label className="text-xs font-semibold">Onset:</Label>
                <Input
                  type="text"
                  className="w-24 h-7 text-xs text-center"
                  value={editingOnset ?? formatTime(sleepMarkers[selectedPeriodIndex].onsetTimestamp)}
                  onChange={(e) => setEditingOnset(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      commitTimeEdit("onset", (e.target as HTMLInputElement).value);
                      setEditingOnset(null);
                    } else if (e.key === "Escape") {
                      setEditingOnset(null);
                    }
                  }}
                  onFocus={(e) => setEditingOnset(e.target.value)}
                  onBlur={(e) => {
                    commitTimeEdit("onset", e.target.value);
                    setEditingOnset(null);
                  }}
                />
              </div>
              <div className="flex items-center gap-1.5">
                <Label className="text-xs font-semibold">Offset:</Label>
                <Input
                  type="text"
                  className="w-24 h-7 text-xs text-center"
                  value={editingOffset ?? formatTime(sleepMarkers[selectedPeriodIndex].offsetTimestamp)}
                  onChange={(e) => setEditingOffset(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      commitTimeEdit("offset", (e.target as HTMLInputElement).value);
                      setEditingOffset(null);
                    } else if (e.key === "Escape") {
                      setEditingOffset(null);
                    }
                  }}
                  onFocus={(e) => setEditingOffset(e.target.value)}
                  onBlur={(e) => {
                    commitTimeEdit("offset", e.target.value);
                    setEditingOffset(null);
                  }}
                />
              </div>
              <span className="text-xs font-medium">
                {formatDuration(sleepMarkers[selectedPeriodIndex].onsetTimestamp, sleepMarkers[selectedPeriodIndex].offsetTimestamp)}
              </span>
            </>
          )}
          {markerMode === "nonwear" && selectedPeriodIndex !== null && nonwearMarkers[selectedPeriodIndex] && (
            <>
              <span className="text-xs">
                {formatTime(nonwearMarkers[selectedPeriodIndex].startTimestamp)}–{formatTime(nonwearMarkers[selectedPeriodIndex].endTimestamp)}
              </span>
              <span className="text-xs font-medium">
                {formatDuration(nonwearMarkers[selectedPeriodIndex].startTimestamp, nonwearMarkers[selectedPeriodIndex].endTimestamp)}
              </span>
              <div className="h-4 w-px bg-border" />
            </>
          )}

          {/* Save status */}
          {isSaving ? (
            <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-600 dark:text-amber-400">
              <Loader2 className="h-3 w-3 animate-spin" />
              Saving
            </span>
          ) : isDirty ? (
            <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded-full bg-muted border border-border text-muted-foreground">
              <CircleDot className="h-3 w-3" />
              Unsaved
            </span>
          ) : (sleepMarkers.length > 0 || nonwearMarkers.length > 0) ? (
            <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded-full bg-green-500/10 border border-green-500/30 text-green-600 dark:text-green-400">
              <Check className="h-3 w-3" />
              Saved
            </span>
          ) : null}

          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs text-destructive border-destructive/50 hover:bg-destructive/10"
            onClick={async () => {
              const ok = await confirm({ title: "Clear Markers", description: "Clear all markers for this date?", variant: "destructive", confirmLabel: "Clear All" });
              if (ok) {
                useSleepScoringStore.getState().clearAllMarkers();
              }
            }}
          >
            <Trash2 className="h-3.5 w-3.5 mr-1" />
            Clear
          </Button>
        </div>
      </div>

      {/* Main content: vertical split — top (plot + side tables) / bottom (diary full-width) */}
      <div className="flex-1 min-h-0 flex flex-col p-2 gap-1">
      <Group orientation="vertical" className="flex-1 min-h-0" defaultLayout={verticalLayout.defaultLayout} onLayoutChanged={verticalLayout.onLayoutChanged}>
        {/* Top: Plot flanked by onset/offset tables */}
        <Panel defaultSize="65%" minSize="30%" id="top-row">
          <Group orientation="horizontal" className="h-full" defaultLayout={horizontalLayout.defaultLayout} onLayoutChanged={horizontalLayout.onLayoutChanged}>
            {/* Left Data Table - Onset/Start */}
            <Panel defaultSize="10%" minSize="5%" maxSize="25%" id="left-table">
              <Card className="h-full flex flex-col overflow-hidden">
                <CardContent className="flex-1 p-0 overflow-hidden">
                  <MarkerDataTable
                    type="onset"
                    onOpenPopout={() => setOnsetPopoutOpen(true)}
                  />
                </CardContent>
              </Card>
            </Panel>

            <Separator className="w-1.5 mx-0.5 flex items-center justify-center group hover:bg-border/50 rounded transition-colors">
              <GripVertical className="h-4 w-4 text-muted-foreground/40 group-hover:text-muted-foreground" />
            </Separator>

            {/* Center - Plot */}
            <Panel defaultSize="65%" minSize="45%" id="center">
              <Card className="h-full flex flex-col min-h-0 min-w-0">
                <CardHeader className="flex-none py-2 px-3">
                  <CardTitle className="text-sm text-center">
                    {currentFilename ?? "No file selected"} - {currentDate ?? "No date"}{weekdayLabel ? ` (${weekdayLabel})` : ""}
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex-1 p-0 relative min-h-0">
                  {activityError ? (
                    <div className="absolute inset-0 flex items-center justify-center text-destructive">
                      <p>Failed to load activity data</p>
                    </div>
                  ) : (
                    <>
                      <div className={`h-full ${activityLoading ? "opacity-30 pointer-events-none transition-opacity duration-200" : "transition-opacity duration-200"}`}>
                        <ActivityPlot
                          showComparisonMarkers={showComparisonMarkers}
                          highlightedCandidateId={highlightedCandidateId}
                        />
                      </div>
                      {activityLoading && (
                        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                      )}
                    </>
                  )}
                </CardContent>
              </Card>
            </Panel>

            <Separator className="w-1.5 mx-0.5 flex items-center justify-center group hover:bg-border/50 rounded transition-colors">
              <GripVertical className="h-4 w-4 text-muted-foreground/40 group-hover:text-muted-foreground" />
            </Separator>

            {/* Right Data Table - Offset/End */}
            <Panel defaultSize="10%" minSize="5%" maxSize="25%" id="right-table">
              <Card className="h-full flex flex-col overflow-hidden">
                <CardContent className="flex-1 p-0 overflow-hidden">
                  <MarkerDataTable
                    type="offset"
                    onOpenPopout={() => setOffsetPopoutOpen(true)}
                  />
                </CardContent>
              </Card>
            </Panel>

          </Group>
        </Panel>

        <Separator className="h-1.5 my-0.5 flex items-center justify-center group hover:bg-border/50 rounded transition-colors">
          <GripHorizontal className="h-4 w-4 text-muted-foreground/40 group-hover:text-muted-foreground" />
        </Separator>

        {/* Bottom: Diary + consensus vote panel (consensus hidden for local) */}
        <Panel defaultSize="35%" minSize="15%" maxSize="55%" id="bottom">
          {isLocal || isConsensusCollapsed ? (
            <div className="h-full min-h-0 flex gap-1">
              <div className="flex-1 min-w-0">
                <DiaryPanel compact />
              </div>
              {!isLocal && (
                <Card className="w-8 h-full flex-none">
                  <CardContent className="h-full p-0 flex items-center justify-center">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => setIsConsensusCollapsed(false)}
                      title="Expand consensus panel"
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </Button>
                  </CardContent>
                </Card>
              )}
            </div>
          ) : (
            <Group
              orientation="horizontal"
              className="h-full"
              defaultLayout={bottomLayout.defaultLayout}
              onLayoutChanged={bottomLayout.onLayoutChanged}
            >
              <Panel defaultSize="72%" minSize="55%" id="bottom-diary">
                <DiaryPanel compact />
              </Panel>

              <Separator className="w-1.5 mx-0.5 flex items-center justify-center group hover:bg-border/50 rounded transition-colors">
                <GripVertical className="h-4 w-4 text-muted-foreground/40 group-hover:text-muted-foreground" />
              </Separator>

              <Panel defaultSize="28%" minSize="15%" maxSize="45%" id="bottom-consensus-vote">
                <div className="h-full min-h-0 relative">
                  <Button
                    variant="outline"
                    size="icon"
                    className="absolute right-2 top-2 z-10 h-6 w-6"
                    onClick={() => setIsConsensusCollapsed(true)}
                    title="Collapse consensus panel to the right"
                  >
                    <ChevronRight className="h-3.5 w-3.5" />
                  </Button>
                  <ConsensusVoteSidebar
                    highlightedCandidateId={highlightedCandidateId}
                    onHighlightCandidate={(candidateId) => {
                      setHighlightedCandidateId(candidateId);
                      if (candidateId !== null) {
                        setShowComparisonMarkers(true);
                      }
                    }}
                    onCopyCandidate={copyCandidateMarkers}
                  />
                </div>
              </Panel>
            </Group>
          )}
        </Panel>
      </Group>
      </div>

      {/* Popout Table Dialogs — independent onset and offset windows */}
      <PopoutTableDialog
        open={onsetPopoutOpen}
        onOpenChange={setOnsetPopoutOpen}
        highlightType="onset"
      />
      <PopoutTableDialog
        open={offsetPopoutOpen}
        onOpenChange={setOffsetPopoutOpen}
        highlightType="offset"
      />

      {/* Keyboard Shortcuts Dialog */}
      <KeyboardShortcutsDialog
        open={shortcutsOpen}
        onOpenChange={setShortcutsOpen}
      />

      {/* Color Legend Dialog */}
      <ColorLegendDialog
        open={colorLegendOpen}
        onOpenChange={setColorLegendOpen}
      />

      {/* Complexity Breakdown Dialog */}
      <Dialog open={complexityBreakdown !== null} onOpenChange={(open) => { if (!open) setComplexityBreakdown(null); }}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Scoring Difficulty Breakdown</DialogTitle>
            <DialogDescription>
              Score: {complexityBreakdown?.complexity_post ?? complexityBreakdown?.complexity_pre ?? "N/A"}/100 (higher = easier)
              {complexityBreakdown?.complexity_post != null && complexityBreakdown?.complexity_pre != null && complexityBreakdown.complexity_post !== complexityBreakdown.complexity_pre && (
                <span className="ml-1 text-muted-foreground">
                  (pre: {complexityBreakdown.complexity_pre}, post: {complexityBreakdown.complexity_post})
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          {complexityBreakdown?.features && (
            <div className="space-y-3 text-sm">
              {(() => {
                const f = complexityBreakdown.features;
                const rows: Array<{ label: string; value: string; penalty: number | string | null }> = [];

                if (f.error) return <p className="text-destructive">{String(f.error)}</p>;

                if (f.no_diary || f.missing_onset || f.missing_wake) {
                  return <p className="text-purple-600 dark:text-purple-400 font-medium">No complete diary for this night (need both onset and wake times).</p>;
                }
                if (f.diary_nonwear_overlaps_sleep) {
                  return <p className="text-purple-600 dark:text-purple-400 font-medium">Diary-reported nonwear overlaps diary-reported sleep period.</p>;
                }
                if (f.nonwear_exceeds_threshold) {
                  return <p className="text-purple-600 dark:text-purple-400 font-medium">Nonwear covers most of the sleep period — data may be unusable.</p>;
                }

                if (f.transition_density != null) rows.push({ label: "Transition density", value: `${f.transition_density}/hr`, penalty: f.transition_density_penalty as number });
                if (f.diary_onset_gap_min != null) rows.push({ label: "Diary-algorithm onset gap", value: `${f.diary_onset_gap_min} min`, penalty: null });
                if (f.diary_offset_gap_min != null) rows.push({ label: "Diary-algorithm offset gap", value: `${f.diary_offset_gap_min} min`, penalty: null });
                if (f.diary_algorithm_gap_penalty != null) rows.push({ label: "Diary-algorithm gap penalty", value: "", penalty: f.diary_algorithm_gap_penalty as number });
                if (f.confirmed_nonwear_night_epochs != null) rows.push({ label: "Confirmed nonwear (night)", value: `${f.confirmed_nonwear_night_epochs} epochs`, penalty: null });
                if (f.choi_only_nonwear_night_epochs != null) rows.push({ label: "Choi-only nonwear (night)", value: `${f.choi_only_nonwear_night_epochs} epochs`, penalty: null });
                if (f.nonwear_night_penalty != null) rows.push({ label: "Nonwear penalty", value: "", penalty: f.nonwear_night_penalty as number });
                if (f.sleep_run_count != null) rows.push({ label: "Sleep run count", value: String(f.sleep_run_count), penalty: f.sleep_run_penalty as number });
                if (f.sleep_period_hours != null) rows.push({ label: "Sleep period duration", value: `${f.sleep_period_hours} hrs`, penalty: f.duration_typicality_penalty as number });
                if (f.nap_count != null) rows.push({ label: "Nap count", value: String(f.nap_count), penalty: f.nap_complexity_penalty as number });
                if (f.boundary_clarity_penalty != null) rows.push({ label: "Boundary clarity", value: "", penalty: f.boundary_clarity_penalty as number });
                if (f.onset_candidates_near_diary != null) rows.push({ label: "Onset candidates near diary", value: String(f.onset_candidates_near_diary), penalty: null });
                if (f.offset_candidates_near_diary != null) rows.push({ label: "Offset candidates near diary", value: String(f.offset_candidates_near_diary), penalty: null });
                if (f.candidate_ambiguity_penalty != null) rows.push({ label: "Candidate ambiguity penalty", value: "", penalty: f.candidate_ambiguity_penalty as number });
                if (f.algo_onset_before_diary) rows.push({ label: "Algorithm onset before diary", value: "Yes", penalty: -3 });
                if (f.nonwear_near_candidate) rows.push({ label: "Nonwear near candidate", value: "Yes", penalty: -2 });
                if (f.marker_alignment != null) rows.push({ label: "Marker-algorithm alignment", value: `${f.marker_alignment} (${f.marker_alignment_epochs} epochs)`, penalty: f.post_adjustment as number });

                return (
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="py-1.5 font-medium">Feature</th>
                        <th className="py-1.5 font-medium text-right">Value</th>
                        <th className="py-1.5 font-medium text-right">Penalty</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr key={i} className="border-b border-border/40">
                          <td className="py-1.5">{r.label}</td>
                          <td className="py-1.5 text-right tabular-nums">{r.value}</td>
                          <td className={`py-1.5 text-right tabular-nums font-medium ${r.penalty != null && typeof r.penalty === "number" && r.penalty < 0 ? "text-red-500" : r.penalty != null && typeof r.penalty === "number" && r.penalty > 0 ? "text-green-500" : ""}`}>
                            {r.penalty != null ? (typeof r.penalty === "number" && r.penalty > 0 ? `+${r.penalty}` : String(r.penalty)) : "—"}
                          </td>
                        </tr>
                      ))}
                      {f.total_penalty != null && (
                        <tr className="font-medium">
                          <td className="py-1.5">Total penalty</td>
                          <td></td>
                          <td className="py-1.5 text-right tabular-nums text-red-500">{String(f.total_penalty)}</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                );
              })()}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Combined Auto-Score Review Dialog */}
      {(autoScoreResult || autoNonwearResult) && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => { setAutoScoreResult(null); setAutoNonwearResult(null); }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              if (autoScoreResult) {
                const canApply = (autoScoreResult.sleep_markers.length > 0 || autoScoreResult.nap_markers.length > 0) && sleepMarkers.length === 0;
                if (canApply) applyAutoScore();
              }
              if (autoNonwearResult) {
                if (autoNonwearResult.nonwear_markers.length > 0 && nonwearMarkers.length === 0) applyAutoNonwear();
              }
            } else if (e.key === "Escape") {
              setAutoScoreResult(null);
              setAutoNonwearResult(null);
            }
          }}
          tabIndex={-1}
          ref={(el) => el?.focus()}
        >
          <div className="bg-background border rounded-lg shadow-xl p-6 max-w-lg mx-4 max-h-[80vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Wand2 className="h-5 w-5" />
              Review Auto-Score Results
            </h3>

            {/* Sleep section */}
            {autoScoreResult && (
              <div className="mb-4">
                <h4 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">Sleep</h4>
                <div className="space-y-1.5 mb-3">
                  {autoScoreResult.notes.map((note, i) => (
                    <p key={i} className="text-sm text-muted-foreground">{note}</p>
                  ))}
                  {autoScoreResult.sleep_markers.length === 0 && autoScoreResult.nap_markers.length === 0 && (
                    <p className="text-sm text-amber-600">No sleep periods detected.</p>
                  )}
                  {sleepMarkers.length > 0 && (
                    <p className="text-sm text-amber-600 font-medium">
                      Sleep markers already exist. Clear existing markers first.
                    </p>
                  )}
                </div>
                {[...autoScoreResult.sleep_markers, ...autoScoreResult.nap_markers].length > 0 && (
                  <div className="border rounded p-2 max-h-32 overflow-auto mb-2">
                    {[...autoScoreResult.sleep_markers, ...autoScoreResult.nap_markers]
                      .sort((a, b) => a.marker_index - b.marker_index)
                      .map((m) => (
                        <div key={`${m.marker_index}-${m.onset_timestamp}-${m.offset_timestamp}`} className="text-xs flex items-center justify-between py-0.5">
                          <span className="font-medium">{m.marker_type === "NAP" ? "Nap" : "Main"} {m.marker_index}</span>
                          <span className="tabular-nums">
                            {formatTime(m.onset_timestamp)} - {formatTime(m.offset_timestamp)}
                          </span>
                        </div>
                      ))}
                  </div>
                )}
                <div className="flex items-center justify-between">
                  <span className="text-sm">
                    <span className="font-medium">{autoScoreResult.sleep_markers.length}</span> sleep,{" "}
                    <span className="font-medium">{autoScoreResult.nap_markers.length}</span> nap(s)
                  </span>
                  <Button
                    size="sm"
                    onClick={() => { applyAutoScore(); }}
                    disabled={
                      (autoScoreResult.sleep_markers.length === 0 && autoScoreResult.nap_markers.length === 0) ||
                      sleepMarkers.length > 0
                    }
                  >
                    Apply Sleep
                  </Button>
                </div>
              </div>
            )}

            {/* Separator when both present */}
            {autoScoreResult && autoNonwearResult && (
              <div className="border-t my-4" />
            )}

            {/* Nonwear section */}
            {autoNonwearResult && (
              <div className="mb-4">
                <h4 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">Nonwear</h4>
                <div className="space-y-1.5 mb-3">
                  {autoNonwearResult.notes.map((note, i) => (
                    <p key={i} className="text-sm text-muted-foreground">{note}</p>
                  ))}
                  {autoNonwearResult.nonwear_markers.length === 0 && (
                    <p className="text-sm text-amber-600">No nonwear periods detected.</p>
                  )}
                  {nonwearMarkers.length > 0 && (
                    <p className="text-sm text-amber-600 font-medium">
                      Nonwear markers already exist. Clear existing markers first.
                    </p>
                  )}
                </div>
                {autoNonwearResult.nonwear_markers.length > 0 && (
                  <div className="border rounded p-2 max-h-32 overflow-auto mb-2">
                    {autoNonwearResult.nonwear_markers.map((m) => (
                      <div key={m.marker_index} className="text-xs flex items-center justify-between py-0.5">
                        <span className="font-medium">Nonwear {m.marker_index}</span>
                        <span className="tabular-nums">
                          {formatTime(m.start_timestamp)} - {formatTime(m.end_timestamp)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex items-center justify-between">
                  <span className="text-sm">
                    <span className="font-medium">{autoNonwearResult.nonwear_markers.length}</span> nonwear period(s)
                  </span>
                  <Button
                    size="sm"
                    onClick={applyAutoNonwear}
                    disabled={autoNonwearResult.nonwear_markers.length === 0 || nonwearMarkers.length > 0}
                  >
                    Apply Nonwear
                  </Button>
                </div>
              </div>
            )}

            {/* Dismiss */}
            <div className="flex justify-end pt-2 border-t">
              <Button variant="outline" size="sm" onClick={() => { setAutoScoreResult(null); setAutoNonwearResult(null); }}>
                Dismiss
              </Button>
            </div>
          </div>
        </div>
      )}
      {confirmDialog}
      {alertDialog}
    </div>
  );
}
