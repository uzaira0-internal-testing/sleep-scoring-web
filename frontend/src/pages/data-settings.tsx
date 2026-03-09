import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Database, FileText, Trash2, RefreshCw, Info, Loader2, Save, Check, Columns, Activity, Upload, Book, CircleOff, X, AlertTriangle, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useConfirmDialog, useAlertDialog } from "@/components/ui/confirm-dialog";
import { useSleepScoringStore } from "@/store";
import { settingsApi, filesApi, diaryApi, nonwearApi, importApi, assignmentApi, autoScoreApi } from "@/api/client";
import type { FileInfo, FileAssignment } from "@/api/types";
import { useTusUpload, TUS_SIZE_THRESHOLD } from "@/hooks/useTusUpload";
import { UploadProgress } from "@/components/upload-progress";
import { useAppCapabilities } from "@/hooks/useAppCapabilities";
import { useLocalFile } from "@/hooks/useLocalFile";
import { LocalProcessingProgress } from "@/components/local-processing-progress";
import { getLocalFiles, deleteFileRecord, saveSensorNonwear, saveDiaryEntry, type FileRecord } from "@/db";
import { parseNonwearCsv } from "@/services/nonwear-csv-parser";
import { parseDiaryCsv } from "@/services/diary-parser";

const ACTIVITY_COLUMN_OPTIONS = [
  { value: "axis_y", label: "Y-Axis (default)" },
  { value: "axis_x", label: "X-Axis" },
  { value: "axis_z", label: "Z-Axis" },
  { value: "vector_magnitude", label: "Vector Magnitude" },
];

const CHOI_AXIS_OPTIONS = [
  { value: "vector_magnitude", label: "Vector Magnitude (default)" },
  { value: "axis_y", label: "Y-Axis" },
  { value: "axis_x", label: "X-Axis" },
  { value: "axis_z", label: "Z-Axis" },
];

const DEVICE_PRESET_OPTIONS = [
  { value: "actigraph", label: "ActiGraph (ActiLife CSV Export)" },
  { value: "actiwatch", label: "Actiwatch" },
  { value: "motionwatch", label: "MotionWatch" },
  { value: "geneactiv", label: "GENEActiv" },
  { value: "generic", label: "Generic CSV" },
];

/** Preset defaults for each device type */
const PRESET_DEFAULTS: Record<string, { epochLengthSeconds: number; skipRows: number }> = {
  actigraph: { epochLengthSeconds: 60, skipRows: 10 },
  actiwatch: { epochLengthSeconds: 60, skipRows: 7 },
  motionwatch: { epochLengthSeconds: 60, skipRows: 8 },
  geneactiv: { epochLengthSeconds: 60, skipRows: 100 },
  generic: { epochLengthSeconds: 60, skipRows: 0 },
};

// =============================================================================
// Action Result Component (used by both local import and server upload)
// =============================================================================

function ActionResult({ message, type, onDismiss }: { message: string; type: "success" | "error"; onDismiss: () => void }) {
  return (
    <div className={`flex items-center gap-2 text-sm rounded-md px-3 py-2 ${
      type === "success" ? "bg-green-500/10 text-green-700 dark:text-green-400" : "bg-destructive/10 text-destructive"
    }`}>
      {type === "success" ? <Check className="h-3.5 w-3.5 flex-shrink-0" /> : <X className="h-3.5 w-3.5 flex-shrink-0" />}
      <span className="flex-1">{message}</span>
      <button onClick={onDismiss} className="hover:opacity-70">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

// =============================================================================
// Local Nonwear Import Component
// =============================================================================

function LocalNonwearImport({ localFiles }: { localFiles: FileRecord[] }) {
  const [isImporting, setIsImporting] = useState(false);
  const [result, setResult] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;

    setIsImporting(true);
    setResult(null);

    try {
      let totalMatched = 0;
      let totalUnmatched = 0;
      const allErrors: string[] = [];

      for (const file of files) {
        const text = await file.text();
        const parsed = parseNonwearCsv(text, localFiles);

        // Save to IndexedDB
        for (const { fileId, entries } of parsed.matched) {
          // Group by date
          const byDate = new Map<string, typeof entries>();
          for (const entry of entries) {
            const list = byDate.get(entry.analysisDate) ?? [];
            list.push(entry);
            byDate.set(entry.analysisDate, list);
          }
          for (const [date, periods] of byDate) {
            await saveSensorNonwear(fileId, date, periods);
          }
        }

        totalMatched += parsed.matchedRows;
        totalUnmatched += parsed.unmatchedRows;
        allErrors.push(...parsed.errors);
      }

      if (totalMatched > 0) {
        setResult({
          message: `Imported ${totalMatched} nonwear periods.${totalUnmatched > 0 ? ` ${totalUnmatched} rows unmatched.` : ""}`,
          type: "success",
        });
      } else {
        setResult({
          message: `No rows matched local files.${allErrors.length > 0 ? ` ${allErrors[0]}` : ""}`,
          type: "error",
        });
      }
    } catch (err) {
      setResult({
        message: err instanceof Error ? err.message : "Import failed",
        type: "error",
      });
    } finally {
      setIsImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CircleOff className="h-5 w-5" />
          Nonwear Sensor Data
        </CardTitle>
        <CardDescription>
          Import nonwear period CSVs. Rows are matched to files by <strong>filename</strong> or <strong>participant_id</strong> column.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <input
          ref={fileRef}
          type="file"
          accept=".csv"
          multiple
          onChange={handleImport}
          className="hidden"
        />
        <Button
          variant="outline"
          onClick={() => fileRef.current?.click()}
          disabled={isImporting}
          className="gap-2"
        >
          {isImporting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FolderOpen className="h-4 w-4" />
          )}
          Import CSV
        </Button>

        {result && (
          <ActionResult message={result.message} type={result.type} onDismiss={() => setResult(null)} />
        )}

        <div className="rounded-lg border p-3 bg-muted/30 text-sm">
          <div className="flex items-start gap-2">
            <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
            <div className="space-y-1">
              <div><strong>Required:</strong> filename (or participant_id), date, start_time, end_time</div>
              <div>Multiple nonwear periods per date supported (one row per period).</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Local Diary Import Component
// =============================================================================

function LocalDiaryImport({ localFiles }: { localFiles: FileRecord[] }) {
  const [isImporting, setIsImporting] = useState(false);
  const [result, setResult] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsImporting(true);
    setResult(null);

    try {
      const text = await file.text();
      const parsed = parseDiaryCsv(text, localFiles);

      // Save to IndexedDB
      for (const { entries } of parsed.matched) {
        for (const entry of entries) {
          await saveDiaryEntry(entry.fileId, entry.analysisDate, entry);
        }
      }

      if (parsed.matchedRows > 0) {
        setResult({
          message: `Imported ${parsed.matchedRows} diary entries across ${parsed.matched.length} file(s).${parsed.unmatchedRows > 0 ? ` ${parsed.unmatchedRows} rows unmatched.` : ""}`,
          type: "success",
        });
      } else {
        setResult({
          message: `No rows matched local files.${parsed.errors.length > 0 ? ` ${parsed.errors[0]}` : ""}`,
          type: "error",
        });
      }
    } catch (err) {
      setResult({
        message: err instanceof Error ? err.message : "Import failed",
        type: "error",
      });
    } finally {
      setIsImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Book className="h-5 w-5" />
          Sleep Diary Import
        </CardTitle>
        <CardDescription>
          Import a sleep diary CSV. Rows are matched to local files by <strong>filename</strong> column.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <input
          ref={fileRef}
          type="file"
          accept=".csv"
          onChange={handleImport}
          className="hidden"
        />
        <Button
          variant="outline"
          onClick={() => fileRef.current?.click()}
          disabled={isImporting}
          className="gap-2"
        >
          {isImporting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FolderOpen className="h-4 w-4" />
          )}
          Import Diary CSV
        </Button>

        {result && (
          <ActionResult message={result.message} type={result.type} onDismiss={() => setResult(null)} />
        )}

        <div className="rounded-lg border p-3 bg-muted/30 text-sm">
          <div className="flex items-start gap-2">
            <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
            <div className="space-y-1">
              <div><strong>Required:</strong> filename, date (or startdate)</div>
              <div><strong>Sleep:</strong> in_bed_time, sleep_offset_time, sleep_onset_time</div>
              <div><strong>Naps:</strong> napstart_1_time, napend_1_time (up to 3 naps)</div>
              <div><strong>Nonwear:</strong> nonwear_start_time, nonwear_end_time, nonwear_reason (up to 3)</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function DataSettingsPage() {
  const queryClient = useQueryClient();
  const isAuthenticated = useSleepScoringStore((state) => state.isAuthenticated);
  const caps = useAppCapabilities();
  const { openLocalFile, openLocalFiles, openLocalFolder, isProcessing, progress: localProgress } = useLocalFile();
  const [localFiles, setLocalFiles] = useState<FileRecord[]>([]);
  const { confirm, confirmDialog } = useConfirmDialog();
  const { alert, alertDialog } = useAlertDialog();
  const {
    devicePreset,
    setDevicePreset,
    epochLengthSeconds,
    setEpochLengthSeconds,
    skipRows,
    setSkipRows,
    sleepMarkers,
    nonwearMarkers,
    setSleepMarkers,
    setNonwearMarkers,
    currentFileId,
  } = useSleepScoringStore();

  const [hasChanges, setHasChanges] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Upload refs and state
  const activityFileRef = useRef<HTMLInputElement>(null);
  const activityFolderRef = useRef<HTMLInputElement>(null);
  const diaryFileRef = useRef<HTMLInputElement>(null);
  const nonwearFileRef = useRef<HTMLInputElement>(null);
  const nonwearFolderRef = useRef<HTMLInputElement>(null);
  const sleepImportRef = useRef<HTMLInputElement>(null);
  const [diaryResult, setDiaryResult] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [sleepImportResult, setSleepImportResult] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [sleepImportLoading, setSleepImportLoading] = useState(false);
  const [autoScoreBatchResult, setAutoScoreBatchResult] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [autoScoreOnlyMissing, setAutoScoreOnlyMissing] = useState(true);
  const [replaceOnUpload, setReplaceOnUpload] = useState(true);
  // Upload progress lives in store so it survives page navigation
  const uploadProgress = useSleepScoringStore((state) => state.uploadProgress);
  const isUploading = useSleepScoringStore((state) => state.isUploading);
  const uploadResult = useSleepScoringStore((state) => state.uploadResult);

  // TUS resumable upload hook (for large files >50MB)
  const { progress: tusProgress, upload: tusUpload, cancel: tusCancel, pause: tusPause, resume: tusResume, reset: tusReset } = useTusUpload();
  const [isPaused, setIsPaused] = useState(false);
  const isTusActive = tusProgress.phase !== "idle";

  // Column mapping state
  const [columnMapping, setColumnMapping] = useState<Record<string, string>>({
    date_column: "",
    time_column: "",
    datetime_column: "",
    activity_column: "",
    axis_x_column: "",
    axis_z_column: "",
    vector_magnitude_column: "",
  });
  const [choiAxis, setChoiAxis] = useState("vector_magnitude");
  const [preferredActivityColumn, setPreferredActivityColumn] = useState("axis_y");
  const [extraSynced, setExtraSynced] = useState(false);

  // Load study-wide settings (data settings are shared across all users)
  const { data: backendSettings, isLoading } = useQuery({
    queryKey: ["study-settings"],
    queryFn: settingsApi.getStudySettings,
    enabled: isAuthenticated && caps.server,
  });

  // Load file list (server only)
  const { data: filesData } = useQuery({
    queryKey: ["files"],
    queryFn: filesApi.listFiles,
    enabled: isAuthenticated && caps.server,
  });

  const files: FileInfo[] = filesData?.items ?? [];

  const { data: autoScoreBatchStatus } = useQuery({
    queryKey: ["auto-score-batch-status"],
    queryFn: autoScoreApi.getBatchStatus,
    enabled: isAuthenticated && caps.server,
    refetchInterval: (query) => (query.state.data?.is_running ? 1500 : false),
    refetchIntervalInBackground: true,
  });

  // Load local files from IndexedDB
  useEffect(() => {
    getLocalFiles().then(setLocalFiles).catch((err) => {
      console.error("Failed to load local files from IndexedDB:", err);
    });
  }, [isProcessing]); // Re-fetch after local file processing


  // Sync backend data settings to store on load
  useEffect(() => {
    if (backendSettings) {
      if (backendSettings.device_preset) {
        setDevicePreset(backendSettings.device_preset as typeof devicePreset);
      }
      if (backendSettings.epoch_length_seconds) {
        setEpochLengthSeconds(backendSettings.epoch_length_seconds);
      }
      if (backendSettings.skip_rows !== undefined && backendSettings.skip_rows !== null) {
        setSkipRows(backendSettings.skip_rows);
      }
    }
  }, [backendSettings, setDevicePreset, setEpochLengthSeconds, setSkipRows]);

  // Sync extra_settings on initial load (from study-wide settings)
  useEffect(() => {
    if (backendSettings?.extra_settings && !extraSynced) {
      const extra = backendSettings.extra_settings;
      if (extra.column_mapping && typeof extra.column_mapping === "object") {
        setColumnMapping((prev) => ({ ...prev, ...(extra.column_mapping as Record<string, string>) }));
      }
      if (extra.choi_axis) setChoiAxis(extra.choi_axis as string);
      if (extra.preferred_activity_column) setPreferredActivityColumn(extra.preferred_activity_column as string);
      setExtraSynced(true);
    }
  }, [backendSettings, extraSynced]);

  // Save data settings to study-wide endpoint (shared across all users)
  const saveMutation = useMutation({
    mutationFn: settingsApi.updateStudySettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["study-settings"] });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setHasChanges(false);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    },
    onError: (error: Error) => {
      alert({ title: "Save Failed", description: error.message });
    },
  });

  // Diary upload mutation (study-wide, no file_id needed)
  const diaryUploadMutation = useMutation({
    mutationFn: (file: File) => diaryApi.uploadDiaryCsv(file),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["diary"] });
      queryClient.invalidateQueries({ queryKey: ["dates-status"] });
      const msg = `Imported ${result.entries_imported} entries, skipped ${result.entries_skipped}`;
      const errMsg = result.errors?.length ? `. ${result.errors[0]}` : "";
      setDiaryResult({ message: msg + errMsg, type: result.entries_imported > 0 ? "success" : "error" });
    },
    onError: (error: Error) => {
      setDiaryResult({ message: error.message, type: "error" });
    },
  });

  const autoScoreBatchMutation = useMutation({
    mutationFn: () => {
      const { currentAlgorithm, sleepDetectionRule } = useSleepScoringStore.getState();
      return autoScoreApi.startBatch({
        only_missing: autoScoreOnlyMissing,
        algorithm: currentAlgorithm,
        detection_rule: sleepDetectionRule,
      });
    },
    onSuccess: (status) => {
      queryClient.invalidateQueries({ queryKey: ["auto-score-batch-status"] });
      setAutoScoreBatchResult({
        type: "success",
        message: `Batch started: ${status.total_dates} date${status.total_dates !== 1 ? "s" : ""} queued`,
      });
    },
    onError: (error: Error) => {
      setAutoScoreBatchResult({ message: error.message, type: "error" });
    },
  });

  // Delete file mutation
  const deleteFileMutation = useMutation({
    mutationFn: filesApi.deleteFile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["files"] });
    },
    onError: (error: Error) => {
      alert({ title: "Delete Failed", description: error.message });
    },
  });

  const handleSave = () => {
    saveMutation.mutate({
      device_preset: devicePreset,
      epoch_length_seconds: epochLengthSeconds,
      skip_rows: skipRows,
      extra_settings: {
        column_mapping: columnMapping,
        choi_axis: choiAxis,
        preferred_activity_column: preferredActivityColumn,
      },
    });
  };

  const handleColumnMappingChange = (key: string, value: string) => {
    setColumnMapping((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleClearSleepMarkers = async () => {
    const ok = await confirm({ title: "Clear Sleep Markers", description: "Clear all sleep markers for the current file?", variant: "destructive", confirmLabel: "Clear" });
    if (ok) setSleepMarkers([]);
  };

  const handleClearNonwearMarkers = async () => {
    const ok = await confirm({ title: "Clear Nonwear Markers", description: "Clear all nonwear markers for the current file?", variant: "destructive", confirmLabel: "Clear" });
    if (ok) setNonwearMarkers([]);
  };

  const handleClearAllMarkers = async () => {
    const ok = await confirm({ title: "Clear All Markers", description: "Clear ALL markers for the current file?", variant: "destructive", confirmLabel: "Clear All" });
    if (ok) {
      useSleepScoringStore.getState().clearAllMarkers();
    }
  };

  const handleApplyPreset = (preset: string) => {
    const defaults = PRESET_DEFAULTS[preset] ?? PRESET_DEFAULTS.generic;
    setEpochLengthSeconds(defaults.epochLengthSeconds);
    setSkipRows(defaults.skipRows);
    setHasChanges(true);
  };

  /** Upload multiple activity CSV files sequentially with progress.
   *  Uses store state so uploads survive page navigation. */
  const handleActivityUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;
    const csvFiles = Array.from(fileList).filter((f) => f.name.toLowerCase().endsWith(".csv") || f.name.toLowerCase().endsWith(".xlsx"));
    if (csvFiles.length === 0) {
      useSleepScoringStore.getState().setUploadResult({ message: "No CSV/XLSX files found", type: "error" });
      return;
    }
    // Clear refs immediately (before async starts)
    if (activityFileRef.current) activityFileRef.current.value = "";
    if (activityFolderRef.current) activityFolderRef.current.value = "";

    // Route large files to TUS upload path
    const hasLargeFile = csvFiles.some((f) => f.size > TUS_SIZE_THRESHOLD);
    if (hasLargeFile && csvFiles.length === 1) {
      // Single large file → use TUS resumable upload
      tusReset();
      tusUpload(csvFiles);
      return;
    }

    // Small files or batch → use existing simple upload path
    const store = useSleepScoringStore.getState();
    store.setIsUploading(true);
    store.setUploadResult(null);
    const replace = replaceOnUpload;

    (async () => {
      let uploaded = 0;
      let failed = 0;
      const failedNames: string[] = [];
      let lastError = "";

      // Separate large and small files
      const largeFiles = csvFiles.filter((f) => f.size > TUS_SIZE_THRESHOLD);
      const smallFiles = csvFiles.filter((f) => f.size <= TUS_SIZE_THRESHOLD);

      // Upload small files via simple path
      for (const file of smallFiles) {
        useSleepScoringStore.getState().setUploadProgress(
          `Uploading ${uploaded + failed + 1}/${csvFiles.length}: ${file.name}`
        );
        try {
          await filesApi.uploadFile(file, replace);
          uploaded++;
        } catch (err) {
          failed++;
          failedNames.push(file.name);
          if (err instanceof Error) lastError = err.message;
        }
      }

      // Upload large files via TUS (one at a time)
      for (const file of largeFiles) {
        useSleepScoringStore.getState().setUploadProgress(
          `Uploading (resumable) ${uploaded + failed + 1}/${csvFiles.length}: ${file.name}`
        );
        try {
          await tusUpload([file]);
          uploaded++;
        } catch (err) {
          failed++;
          failedNames.push(file.name);
          if (err instanceof Error) lastError = err.message;
        }
      }

      useSleepScoringStore.getState().setUploadProgress(null);
      useSleepScoringStore.getState().setIsUploading(false);
      let message = `Uploaded ${uploaded} file${uploaded !== 1 ? "s" : ""}`;
      if (failed > 0) {
        message += `, ${failed} failed`;
        if (failedNames.length <= 3) message += ` (${failedNames.join(", ")})`;
        if (lastError) message += `: ${lastError}`;
      }
      const result = {
        message,
        type: (failed > 0 ? "error" : "success") as "success" | "error",
      };
      useSleepScoringStore.getState().setUploadResult(result);
      queryClient.invalidateQueries({ queryKey: ["files"] });
      queryClient.invalidateQueries({ queryKey: ["dates-status"] });
    })();
  };

  const handleDiaryUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    diaryUploadMutation.mutate(file);
    if (diaryFileRef.current) diaryFileRef.current.value = "";
  };

  /** Upload multiple nonwear CSVs sequentially with progress.
   *  Uses store state so uploads survive page navigation. */
  const handleNonwearUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;
    const csvFiles = Array.from(fileList).filter((f) => f.name.toLowerCase().endsWith(".csv"));
    if (csvFiles.length === 0) {
      useSleepScoringStore.getState().setUploadResult({ message: "No CSV files found", type: "error" });
      return;
    }
    // Clear refs immediately (before async starts)
    if (nonwearFileRef.current) nonwearFileRef.current.value = "";
    if (nonwearFolderRef.current) nonwearFolderRef.current.value = "";

    // Run upload in a detached async — store state keeps progress alive across navigation
    const store = useSleepScoringStore.getState();
    store.setIsUploading(true);
    store.setUploadResult(null);

    (async () => {
      let totalDates = 0;
      let totalMarkers = 0;
      let failed = 0;
      for (let fileIdx = 0; fileIdx < csvFiles.length; fileIdx++) {
        const file = csvFiles[fileIdx];
        useSleepScoringStore.getState().setUploadProgress(
          `Uploading nonwear ${fileIdx + 1}/${csvFiles.length}: ${file.name}`
        );
        try {
          const result = await nonwearApi.uploadNonwearCsv(file);
          totalDates += result.dates_imported;
          totalMarkers += result.markers_created;
        } catch (err) {
          failed++;
          if (failed === 1) {
            const msg = err instanceof Error ? err.message : String(err);
            console.error(`Nonwear upload failed for ${file.name}: ${msg}`);
          }
        }
      }
      useSleepScoringStore.getState().setUploadProgress(null);
      useSleepScoringStore.getState().setIsUploading(false);
      const result = {
        message: `${csvFiles.length} file${csvFiles.length !== 1 ? "s" : ""}: ${totalDates} dates, ${totalMarkers} markers${failed > 0 ? `, ${failed} failed` : ""}`,
        type: (failed > 0 ? "error" : "success") as "success" | "error",
      };
      useSleepScoringStore.getState().setUploadResult(result);
      queryClient.invalidateQueries({ queryKey: ["markers"] });
      queryClient.invalidateQueries({ queryKey: ["dates-status"] });
    })();
  };

  const handleSleepImportUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSleepImportResult(null);
    setSleepImportLoading(true);
    try {
      const result = await importApi.uploadSleepCsv(file);
      const errMsg = result.errors?.length ? `. ${result.errors[0]}` : "";
      const noSleepMsg = result.no_sleep_dates > 0 ? `, ${result.no_sleep_dates} no-sleep` : "";
      const matchMsg = ` (${result.matched_rows}/${result.total_rows} rows matched)`;
      const unresolvedCount = (result.unmatched_identifiers?.length ?? 0) + (result.ambiguous_identifiers?.length ?? 0);
      const unresolvedMsg = unresolvedCount > 0 ? `, ${unresolvedCount} unresolved identifier${unresolvedCount === 1 ? "" : "s"}` : "";
      setSleepImportResult({
        message: `${result.dates_imported} dates, ${result.markers_created} markers imported${noSleepMsg}${result.dates_skipped > 0 ? `, ${result.dates_skipped} skipped` : ""}${matchMsg}${unresolvedMsg}${errMsg}`,
        type: (result.dates_imported > 0 || result.no_sleep_dates > 0) ? "success" : "error",
      });
      queryClient.invalidateQueries({ queryKey: ["markers"] });
      queryClient.invalidateQueries({ queryKey: ["dates-status"] });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setSleepImportResult({ message: msg, type: "error" });
    } finally {
      setSleepImportLoading(false);
      if (sleepImportRef.current) sleepImportRef.current.value = "";
    }
  };

  const handleStartAutoScoreBatch = () => {
    setAutoScoreBatchResult(null);
    autoScoreBatchMutation.mutate();
  };

  const hasFile = currentFileId !== null;
  const hasSleepMarkers = sleepMarkers.length > 0;
  const hasNonwearMarkers = nonwearMarkers.length > 0;
  const hasAnyMarkers = hasSleepMarkers || hasNonwearMarkers;

  if (isLoading) {
    return (
      <div className="p-6 max-w-4xl mx-auto flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Data Settings</h1>
          <p className="text-muted-foreground">
            {caps.server ? "Upload data files and configure settings" : "Import data files and configure settings"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {hasChanges && (
            <span className="text-sm text-amber-600 dark:text-amber-400">Unsaved changes</span>
          )}
          {saveSuccess && (
            <span className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1">
              <Check className="h-3 w-3" /> Saved
            </span>
          )}
          <Button
            size="sm"
            onClick={handleSave}
            disabled={saveMutation.isPending || !hasChanges}
          >
            {saveMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-1" />
            )}
            Save
          </Button>
        </div>
      </div>

      {/* ================================================================ */}
      {/* File Uploads / Open Files Section                                */}
      {/* ================================================================ */}

      {/* Local File Opening (always available) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FolderOpen className="h-5 w-5" />
            {caps.server ? "Open Local Files" : "Activity Data Files"}
          </CardTitle>
          <CardDescription>
            Open CSV files from your computer. Files are processed locally using WASM and stored in your browser.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="outline"
              onClick={openLocalFiles}
              disabled={isProcessing}
              className="gap-2"
            >
              {isProcessing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <FolderOpen className="h-4 w-4" />
              )}
              Open Files
            </Button>
            <Button
              variant="outline"
              onClick={openLocalFolder}
              disabled={isProcessing}
              className="gap-2"
            >
              <FolderOpen className="h-4 w-4" />
              Open Folder
            </Button>
          </div>

          {localProgress && <LocalProcessingProgress progress={localProgress} />}

          {/* Local files list */}
          {localFiles.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">
                Local files ({localFiles.length})
              </p>
              <div className="border rounded-md divide-y max-h-48 overflow-y-auto">
                {localFiles.map((f) => (
                  <div key={f.id} className="flex items-center justify-between px-3 py-2 text-sm">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                      <span className="truncate">{f.filename}</span>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-700 dark:text-blue-400">
                        local
                      </span>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                      <span className="text-xs text-muted-foreground">{f.availableDates.length} dates</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0"
                        onClick={async () => {
                          const ok = await confirm({ title: "Delete File", description: `Delete ${f.filename}?`, variant: "destructive", confirmLabel: "Delete" });
                          if (ok && f.id) {
                            try {
                              await deleteFileRecord(f.id);
                              setLocalFiles((prev) => prev.filter((lf) => lf.id !== f.id));
                            } catch (err) {
                              console.error("Failed to delete file:", err);
                              await alert({ title: "Delete Failed", description: `Could not delete ${f.filename}. Please try again.` });
                            }
                          }
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Activity Data Files Upload (server only) */}
      {caps.server && (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Upload to Server
          </CardTitle>
          <CardDescription>
            Upload epoch CSV files with activity counts. Re-uploading a file with the same name replaces the existing data.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <input
            ref={activityFileRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            multiple
            onChange={handleActivityUpload}
            className="hidden"
          />
          {/* @ts-expect-error webkitdirectory is a non-standard attribute */}
          <input
            ref={activityFolderRef}
            type="file"
            webkitdirectory=""
            onChange={handleActivityUpload}
            className="hidden"
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="outline"
              onClick={() => activityFileRef.current?.click()}
              disabled={!!uploadProgress}
              className="gap-2"
            >
              {uploadProgress && uploadProgress.includes("Uploading") ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              Upload Files
            </Button>
            <Button
              variant="outline"
              onClick={() => activityFolderRef.current?.click()}
              disabled={!!uploadProgress}
              className="gap-2"
            >
              <FileText className="h-4 w-4" />
              Upload Folder
            </Button>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={replaceOnUpload}
                onChange={(e) => setReplaceOnUpload(e.target.checked)}
                className="rounded"
              />
              Replace existing
            </label>
          </div>

          {/* TUS resumable upload progress */}
          {isTusActive && (
            <UploadProgress
              progress={tusProgress}
              onPause={() => { tusPause(); setIsPaused(true); }}
              onResume={() => { tusResume(); setIsPaused(false); }}
              onCancel={() => { tusCancel(); setIsPaused(false); }}
              onDismiss={tusReset}
              isPaused={isPaused}
            />
          )}

          {/* Simple upload progress (small files) */}
          {uploadProgress && !isTusActive && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin flex-shrink-0" />
              {uploadProgress}
            </div>
          )}

          {uploadResult && !isUploading && (
            <ActionResult message={uploadResult.message} type={uploadResult.type} onDismiss={() => useSleepScoringStore.getState().setUploadResult(null)} />
          )}

          {/* Current files list */}
          {files.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">
                Server files ({files.length})
              </p>
              <div className="border rounded-md divide-y max-h-48 overflow-y-auto">
                {files.map((f) => (
                  <div key={f.id} className="flex items-center justify-between px-3 py-2 text-sm">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                      <span className="truncate">{f.filename}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        f.status === "ready" ? "bg-green-500/10 text-green-700 dark:text-green-400" :
                        f.status === "failed" ? "bg-destructive/10 text-destructive" :
                        f.status === "uploading" || f.status === "processing" ? "bg-blue-500/10 text-blue-700 dark:text-blue-400" :
                        "bg-muted text-muted-foreground"
                      }`}>
                        {f.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                      {f.row_count && (
                        <span className="text-xs text-muted-foreground">{f.row_count.toLocaleString()} rows</span>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0"
                        onClick={async () => {
                          const ok = await confirm({ title: "Delete File", description: `Delete ${f.filename}?`, variant: "destructive", confirmLabel: "Delete" });
                          if (ok) deleteFileMutation.mutate(f.id);
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
      )}

      {/* Diary CSV Upload (server only) */}
      {caps.server && (<Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Book className="h-5 w-5" />
            Sleep Diary Import
          </CardTitle>
          <CardDescription>
            Upload a sleep diary CSV exported from REDCap or similar. Rows are automatically matched to activity files by the <strong>participant_id</strong> column.
            Existing entries for matching dates are updated (upsert).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <input
            ref={diaryFileRef}
            type="file"
            accept=".csv"
            onChange={handleDiaryUpload}
            className="hidden"
          />
          <Button
            variant="outline"
            onClick={() => diaryFileRef.current?.click()}
            disabled={diaryUploadMutation.isPending}
            className="gap-2"
          >
            {diaryUploadMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            Upload Diary CSV
          </Button>

          {diaryResult && (
            <ActionResult message={diaryResult.message} type={diaryResult.type} onDismiss={() => setDiaryResult(null)} />
          )}

          <div className="rounded-lg border p-3 bg-muted/30 text-sm">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div className="space-y-1">
                <div><strong>Required:</strong> participant_id, startdate (or date)</div>
                <div><strong>Sleep:</strong> in_bed_time (or bedtime), sleep_offset_time (or wake_time), sleep_onset_time</div>
                <div><strong>Naps:</strong> napstart_1_time, napend_1_time, nap_onset_time_2, nap_offset_time_2, nap_onset_time_3, nap_offset_time_3</div>
                <div><strong>Nonwear:</strong> nonwear_start_time, nonwear_end_time, nonwear_reason (up to 3 periods)</div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      )}

      {/* Local Diary Import (local mode only) */}
      {!caps.server && <LocalDiaryImport localFiles={localFiles} />}

      {/* Nonwear Sensor Data Upload (server only) */}
      {caps.server && (<Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CircleOff className="h-5 w-5" />
            Nonwear Sensor Data
          </CardTitle>
          <CardDescription>
            Upload nonwear period CSVs from external detection tools. Rows are matched to activity files by the <strong>participant_id</strong> column.
            Existing nonwear markers for matching dates are replaced.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <input
            ref={nonwearFileRef}
            type="file"
            accept=".csv"
            multiple
            onChange={handleNonwearUpload}
            className="hidden"
          />
          {/* @ts-expect-error webkitdirectory is a non-standard attribute */}
          <input
            ref={nonwearFolderRef}
            type="file"
            webkitdirectory=""
            onChange={handleNonwearUpload}
            className="hidden"
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="outline"
              onClick={() => nonwearFileRef.current?.click()}
              disabled={isUploading}
              className="gap-2"
            >
              {isUploading && uploadProgress?.includes("nonwear") ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              Upload Files
            </Button>
            <Button
              variant="outline"
              onClick={() => nonwearFolderRef.current?.click()}
              disabled={isUploading}
              className="gap-2"
            >
              <FileText className="h-4 w-4" />
              Upload Folder
            </Button>
          </div>

          {uploadProgress && uploadProgress.includes("nonwear") && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin flex-shrink-0" />
              {uploadProgress}
            </div>
          )}

          {uploadResult && !isUploading && uploadResult.message.includes("dates") && (
            <ActionResult message={uploadResult.message} type={uploadResult.type} onDismiss={() => useSleepScoringStore.getState().setUploadResult(null)} />
          )}

          <div className="rounded-lg border p-3 bg-muted/30 text-sm">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div className="space-y-1">
                <div><strong>Required:</strong> participant_id, date (or startdate), start_time, end_time</div>
                <div>Multiple nonwear periods per date supported (one row per period).</div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      )}

      {/* Local Nonwear Sensor Data Import (local mode only) */}
      {!caps.server && <LocalNonwearImport localFiles={localFiles} />}

      {/* Import Sleep Marker Exports (server only) */}
      {caps.server && (<Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Import Sleep Marker Exports
          </CardTitle>
          <CardDescription>
            Upload a sleep marker CSV exported from the <strong>desktop app</strong> or the <strong>web app&apos;s export page</strong>. Both formats are auto-detected.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Irreversibility warning */}
          <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-3 text-sm">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 flex-shrink-0" />
              <div>
                <strong className="text-destructive">This action is irreversible.</strong> Existing sleep markers for each imported date are <strong>permanently replaced</strong>. Metrics are recalculated automatically from the imported markers. Only import if the corresponding activity files have already been uploaded.
              </div>
            </div>
          </div>

          <input
            ref={sleepImportRef}
            type="file"
            accept=".csv"
            onChange={handleSleepImportUpload}
            className="hidden"
          />
          <Button
            variant="outline"
            onClick={() => sleepImportRef.current?.click()}
            disabled={sleepImportLoading}
            className="gap-2"
          >
            {sleepImportLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            Upload Sleep Marker CSV
          </Button>

          {sleepImportResult && (
            <ActionResult message={sleepImportResult.message} type={sleepImportResult.type} onDismiss={() => setSleepImportResult(null)} />
          )}

          <div className="rounded-lg border p-3 bg-muted/30 text-sm space-y-3">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div className="space-y-1">
                <div className="font-medium">Desktop app exports</div>
                <div><strong>File matching:</strong> filename column, or participant_id + timepoint</div>
                <div><strong>Required:</strong> sleep_date (or date), onset_time, offset_time</div>
                <div><strong>Optional:</strong> marker_type, marker_index, onset_date, offset_date, needs_consensus</div>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div className="space-y-1">
                <div className="font-medium">Web app exports</div>
                <div><strong>File matching:</strong> Filename column or Participant ID</div>
                <div><strong>Required:</strong> Study Date, plus Onset/Offset Time or Onset/Offset Datetime</div>
                <div><strong>Optional:</strong> Marker Type, Period Index, Is No Sleep, Needs Consensus</div>
              </div>
            </div>
            <div className="text-muted-foreground">
              NO_SLEEP rows and Is No Sleep = TRUE are imported as &quot;no sleep&quot; annotations. # comment lines and metadata rows are skipped. Recalculable columns (TST, efficiency, etc.) are ignored — metrics are recomputed from markers + activity data.
            </div>
          </div>
        </CardContent>
      </Card>

      )}

      {/* Batch Auto-Score Prepopulation (server only) */}
      {caps.server && (<Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="h-5 w-5" />
            Batch Auto-Score Prepopulation
          </CardTitle>
          <CardDescription>
            Run auto-scoring across all files for dates with complete diary data to prepopulate algorithm markers.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="outline"
              onClick={handleStartAutoScoreBatch}
              disabled={autoScoreBatchMutation.isPending || !!autoScoreBatchStatus?.is_running || files.length === 0}
              className="gap-2"
            >
              {autoScoreBatchMutation.isPending || autoScoreBatchStatus?.is_running ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              {autoScoreBatchStatus?.is_running ? "Running Batch..." : "Start Batch Auto-Score"}
            </Button>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={autoScoreOnlyMissing}
                onChange={(e) => setAutoScoreOnlyMissing(e.target.checked)}
                className="rounded"
              />
              Only fill missing auto-scores
            </label>
          </div>

          {autoScoreBatchResult && (
            <ActionResult
              message={autoScoreBatchResult.message}
              type={autoScoreBatchResult.type}
              onDismiss={() => setAutoScoreBatchResult(null)}
            />
          )}

          {autoScoreBatchStatus && (
            <div className="rounded-lg border p-3 bg-muted/30 text-sm space-y-1">
              <div className="font-medium">
                Progress: {autoScoreBatchStatus.processed_dates}/{autoScoreBatchStatus.total_dates}
              </div>
              <div>
                Scored {autoScoreBatchStatus.scored_dates}, skipped existing {autoScoreBatchStatus.skipped_existing},
                skipped incomplete diary {autoScoreBatchStatus.skipped_incomplete_diary}, skipped no activity {autoScoreBatchStatus.skipped_no_activity},
                skipped no markers {autoScoreBatchStatus.skipped_no_markers}, failed {autoScoreBatchStatus.failed_dates}
              </div>
              {autoScoreBatchStatus.current_file_id && autoScoreBatchStatus.current_date && (
                <div className="text-muted-foreground">
                  Current: file {autoScoreBatchStatus.current_file_id}, date {autoScoreBatchStatus.current_date}
                </div>
              )}
              {autoScoreBatchStatus.errors?.length > 0 && (
                <div className="text-destructive">
                  Last error: {autoScoreBatchStatus.errors[autoScoreBatchStatus.errors.length - 1]}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      )}

      {/* ================================================================ */}
      {/* Import Configuration Section                                     */}
      {/* ================================================================ */}

      {/* Data Paradigm Info */}
      <Card className="border-green-500/50 bg-green-500/5">
        <CardContent className="py-4">
          <div className="flex items-start gap-3">
            <Database className="h-5 w-5 text-green-600 mt-0.5" />
            <div>
              <div className="font-medium">Data Source: Epoch CSV Files</div>
              <div className="text-sm text-muted-foreground">
                Pre-processed CSV files with 60-second epoch activity counts. Standard format from ActiLife and similar software.
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* CSV Import Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            CSV Import Configuration
          </CardTitle>
          <CardDescription>
            Configure how CSV files are parsed during import.{caps.server ? " These settings are saved to the server and used when new files are uploaded." : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Device Preset */}
          <div className="space-y-2">
            <Label htmlFor="device-preset">Device Preset</Label>
            <div className="flex gap-2">
              <Select
                id="device-preset"
                value={devicePreset}
                onChange={(e) => {
                  const newPreset = e.target.value as typeof devicePreset;
                  setDevicePreset(newPreset);
                  handleApplyPreset(newPreset);
                }}
                options={DEVICE_PRESET_OPTIONS}
                className="flex-1"
              />
            </div>
            <p className="text-sm text-muted-foreground">
              Select your device type to auto-configure epoch length and header rows.
            </p>
          </div>

          {/* Epoch Length and Skip Rows */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="epoch-length">Epoch Length (seconds)</Label>
              <div className="flex gap-2">
                <Input
                  id="epoch-length"
                  type="number"
                  min={1}
                  max={300}
                  value={epochLengthSeconds}
                  onChange={(e) => {
                    setEpochLengthSeconds(Number(e.target.value));
                    setHasChanges(true);
                  }}
                  className="flex-1"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="skip-rows">Skip Header Rows</Label>
              <div className="flex gap-2">
                <Input
                  id="skip-rows"
                  type="number"
                  min={0}
                  max={200}
                  value={skipRows}
                  onChange={(e) => {
                    setSkipRows(Number(e.target.value));
                    setHasChanges(true);
                  }}
                  className="flex-1"
                />
              </div>
            </div>
          </div>

          {/* Auto-detect button */}
          <div className="flex justify-end">
            <Button variant="outline" onClick={() => handleApplyPreset(devicePreset)}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Apply Preset Defaults
            </Button>
          </div>

          {/* Info box */}
          <div className="rounded-lg border p-3 bg-muted/30 text-sm">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div>
                <strong>ActiGraph CSV:</strong> 60-second epochs, 10 header rows.
                <strong className="ml-3">Actiwatch:</strong> 60-second epochs, 7 header rows.
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Column Mapping */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Columns className="h-5 w-5" />
            Column Mapping
          </CardTitle>
          <CardDescription>
            Override default column names for CSV parsing. Leave blank to use device preset defaults.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              { key: "date_column", label: "Date Column" },
              { key: "time_column", label: "Time Column" },
              { key: "datetime_column", label: "DateTime Column" },
              { key: "activity_column", label: "Activity Column (Y-Axis)" },
              { key: "axis_x_column", label: "Axis X Column" },
              { key: "axis_z_column", label: "Axis Z Column" },
              { key: "vector_magnitude_column", label: "Vector Magnitude Column" },
            ].map(({ key, label }) => (
              <div key={key} className="space-y-1">
                <Label htmlFor={key} className="text-xs">{label}</Label>
                <Input
                  id={key}
                  value={columnMapping[key] || ""}
                  onChange={(e) => handleColumnMappingChange(key, e.target.value)}
                  placeholder="Auto-detect"
                  className="h-8 text-sm"
                />
              </div>
            ))}
          </div>
          <div className="rounded-lg border p-3 bg-muted/30 text-sm">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div>
                Column names are case-sensitive. Leave blank to use the default column names for the selected device preset.
              </div>
            </div>
          </div>
        </CardContent>
      </Card>


      {/* Data Management / Clear */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Trash2 className="h-5 w-5" />
            Data Management
          </CardTitle>
          <CardDescription>
            Clear markers for the current file
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <Button
              variant="outline"
              className="h-auto py-3 flex flex-col items-center gap-1"
              disabled={!hasFile || !hasSleepMarkers}
              onClick={handleClearSleepMarkers}
            >
              <span className="font-medium">Clear Sleep Markers</span>
              <span className="text-xs text-muted-foreground">
                {hasSleepMarkers ? `${sleepMarkers.length} markers` : "No markers"}
              </span>
            </Button>
            <Button
              variant="outline"
              className="h-auto py-3 flex flex-col items-center gap-1"
              disabled={!hasFile || !hasNonwearMarkers}
              onClick={handleClearNonwearMarkers}
            >
              <span className="font-medium">Clear Nonwear Markers</span>
              <span className="text-xs text-muted-foreground">
                {hasNonwearMarkers ? `${nonwearMarkers.length} markers` : "No markers"}
              </span>
            </Button>
            <Button
              variant="outline"
              className="h-auto py-3 flex flex-col items-center gap-1"
              disabled={!hasFile || !hasAnyMarkers}
              onClick={handleClearAllMarkers}
            >
              <span className="font-medium">Clear All Markers</span>
              <span className="text-xs text-muted-foreground">
                {hasAnyMarkers ? "Clear everything" : "No data"}
              </span>
            </Button>
          </div>
          {!hasFile && (
            <p className="text-sm text-muted-foreground">
              Select a file on the Scoring page to enable data management options.
            </p>
          )}
        </CardContent>
      </Card>

      {/* File Assignments (admin only, server only) */}
      {caps.server && <FileAssignmentPanel allFiles={filesData?.items ?? []} />}
      {confirmDialog}
      {alertDialog}
    </div>
  );
}

// =============================================================================
// File Assignment Panel (admin only)
// =============================================================================

function FileAssignmentPanel({ allFiles }: { allFiles: FileInfo[] }) {
  const isAdmin = useSleepScoringStore((state) => state.isAdmin);
  const [targetUsername, setTargetUsername] = useState("");
  const [selectedFileIds, setSelectedFileIds] = useState<Set<number>>(new Set());
  const [assignments, setAssignments] = useState<FileAssignment[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ message: string; type: "success" | "error" } | null>(null);

  // Load assignments on mount
  useEffect(() => {
    if (!isAdmin) return;
    assignmentApi.listAssignments()
      .then(setAssignments)
      .catch(() => {/* ignore if endpoint not available */});
  }, [isAdmin]);

  if (!isAdmin) return null;

  // Group assignments by username
  const byUser = new Map<string, FileAssignment[]>();
  for (const a of assignments) {
    const list = byUser.get(a.username) ?? [];
    list.push(a);
    byUser.set(a.username, list);
  }

  const handleAssign = async () => {
    if (!targetUsername.trim() || selectedFileIds.size === 0) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await assignmentApi.createAssignments(
        Array.from(selectedFileIds),
        targetUsername.trim()
      );
      setResult({ message: `Assigned ${res.created} files to ${targetUsername.trim()}`, type: "success" });
      setSelectedFileIds(new Set());
      // Refresh assignments
      const updated = await assignmentApi.listAssignments();
      setAssignments(updated);
    } catch (err) {
      setResult({ message: err instanceof Error ? err.message : "Failed to assign", type: "error" });
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveUser = async (username: string) => {
    try {
      await assignmentApi.deleteUserAssignments(username);
      setAssignments(prev => prev.filter(a => a.username !== username));
    } catch (err) {
      setResult({ message: err instanceof Error ? err.message : "Failed to remove assignments", type: "error" });
    }
  };

  const toggleAll = () => {
    if (selectedFileIds.size === allFiles.length) {
      setSelectedFileIds(new Set());
    } else {
      setSelectedFileIds(new Set(allFiles.map(f => f.id)));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Database className="h-5 w-5" />
          File Assignments
          <span className="text-xs font-normal text-muted-foreground">(Admin)</span>
        </CardTitle>
        <CardDescription>
          Assign files to users. Non-admin users will only see their assigned files.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Current assignments */}
        {byUser.size > 0 && (
          <div className="space-y-2">
            <Label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Current Assignments
            </Label>
            {Array.from(byUser.entries()).map(([username, userAssignments]) => (
              <div key={username} className="border rounded-md p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm">{username}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">{userAssignments.length} files</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0 text-destructive"
                      onClick={() => handleRemoveUser(username)}
                      title={`Remove all assignments for ${username}`}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground truncate">
                  {userAssignments.slice(0, 5).map(a => a.filename).join(", ")}
                  {userAssignments.length > 5 && ` ...and ${userAssignments.length - 5} more`}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* New assignment */}
        <div className="space-y-3 border-t pt-3">
          <Label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Assign Files
          </Label>
          <div className="flex gap-2">
            <Input
              placeholder="Username"
              value={targetUsername}
              onChange={(e) => setTargetUsername(e.target.value)}
              className="max-w-[200px]"
            />
            <Button
              size="sm"
              onClick={handleAssign}
              disabled={loading || !targetUsername.trim() || selectedFileIds.size === 0}
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Assign"}
              {selectedFileIds.size > 0 && ` (${selectedFileIds.size})`}
            </Button>
          </div>

          {result && (
            <ActionResult message={result.message} type={result.type} onDismiss={() => setResult(null)} />
          )}

          {/* File selection */}
          <div className="border rounded-md max-h-48 overflow-y-auto">
            <div className="sticky top-0 bg-background border-b px-3 py-1.5 flex items-center gap-2">
              <input
                type="checkbox"
                checked={selectedFileIds.size === allFiles.length && allFiles.length > 0}
                onChange={toggleAll}
                className="rounded border-input"
              />
              <span className="text-xs text-muted-foreground">
                {selectedFileIds.size > 0 ? `${selectedFileIds.size} selected` : "Select all"}
              </span>
            </div>
            {allFiles.map((f) => (
              <label
                key={f.id}
                className="flex items-center gap-2 px-3 py-1 hover:bg-muted/50 cursor-pointer text-xs"
              >
                <input
                  type="checkbox"
                  checked={selectedFileIds.has(f.id)}
                  onChange={() => {
                    setSelectedFileIds(prev => {
                      const next = new Set(prev);
                      if (next.has(f.id)) next.delete(f.id);
                      else next.add(f.id);
                      return next;
                    });
                  }}
                  className="rounded border-input"
                />
                {f.filename}
              </label>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
