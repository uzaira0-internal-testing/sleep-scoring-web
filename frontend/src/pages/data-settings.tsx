import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Database, FileText, Trash2, RefreshCw, Info, Loader2, Save, Check, Columns, Upload, CircleOff, AlertTriangle, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useConfirmDialog, useAlertDialog } from "@/components/ui/confirm-dialog";
import { useSleepScoringStore } from "@/store";
import { settingsApi, nonwearApi, importApi, autoScoreApi } from "@/api/client";
import type { FileInfo } from "@/api/types";
import { useAppCapabilities } from "@/hooks/useAppCapabilities";
import { getLocalFiles, saveSensorNonwear, type FileRecord } from "@/db";
import { parseNonwearCsv } from "@/services/nonwear-csv-parser";
import { studySettingsQueryOptions, filesQueryOptions, autoScoreBatchStatusQueryOptions } from "@/api/query-options";
import { ActionResult } from "@/components/action-result";
import { FileUploadSection } from "@/components/file-upload-section";
import { LocalFileSection } from "@/components/local-file-section";
import { ServerDiaryImportSection, LocalDiaryImportSection } from "@/components/diary-import-section";


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
// Local Nonwear Import Component
// =============================================================================

function LocalNonwearImport({ localFiles }: { localFiles: FileRecord[] }) {
  const [isImporting, setIsImporting] = useState(false);
  const [result, setResult] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>): Promise<void> => {
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
// Main Component
// =============================================================================

export function DataSettingsPage() {
  const queryClient = useQueryClient();
  const isAuthenticated = useSleepScoringStore((state) => state.isAuthenticated);
  const caps = useAppCapabilities();
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

  // Upload refs and state (for nonwear + marker import sections that remain here)
  const nonwearFileRef = useRef<HTMLInputElement>(null);
  const nonwearFolderRef = useRef<HTMLInputElement>(null);
  const sleepImportRef = useRef<HTMLInputElement>(null);
  const [sleepImportResult, setSleepImportResult] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [sleepImportLoading, setSleepImportLoading] = useState(false);
  const [autoScoreBatchResult, setAutoScoreBatchResult] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [autoScoreOnlyMissing, setAutoScoreOnlyMissing] = useState(true);
  // Upload progress lives in store so it survives page navigation
  const uploadProgress = useSleepScoringStore((state) => state.uploadProgress);
  const isUploading = useSleepScoringStore((state) => state.isUploading);
  const uploadResult = useSleepScoringStore((state) => state.uploadResult);

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
    ...studySettingsQueryOptions(),
    enabled: isAuthenticated && caps.server,
  });

  // Load file list (server only)
  const { data: filesData } = useQuery({
    ...filesQueryOptions(),
    enabled: isAuthenticated && caps.server,
  });

  const files: FileInfo[] = filesData?.items ?? [];

  const { data: autoScoreBatchStatus } = useQuery({
    ...autoScoreBatchStatusQueryOptions(),
    enabled: isAuthenticated && caps.server,
    refetchInterval: (query) => (query.state.data?.is_running ? 1500 : false),
    refetchIntervalInBackground: true,
  });

  // Load local files from IndexedDB (for nonwear import)
  useEffect(() => {
    getLocalFiles().then(setLocalFiles).catch((err) => {
      console.error("Failed to load local files from IndexedDB:", err);
    });
  }, []);


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
      queryClient.invalidateQueries({ queryKey: studySettingsQueryOptions().queryKey });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setHasChanges(false);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    },
    onError: (error: Error) => {
      alert({ title: "Save Failed", description: error.message });
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
      queryClient.invalidateQueries({ queryKey: autoScoreBatchStatusQueryOptions().queryKey });
      setAutoScoreBatchResult({
        type: "success",
        message: `Batch started: ${status.total_dates} date${status.total_dates !== 1 ? "s" : ""} queued`,
      });
    },
    onError: (error: Error) => {
      setAutoScoreBatchResult({ message: error.message, type: "error" });
    },
  });

  const handleSave = (): void => {
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

  const handleColumnMappingChange = (key: string, value: string): void => {
    setColumnMapping((prev) => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleClearSleepMarkers = async (): Promise<void> => {
    const ok = await confirm({ title: "Clear Sleep Markers", description: "Clear all sleep markers for the current date?", variant: "destructive", confirmLabel: "Clear" });
    if (ok) setSleepMarkers([]);
  };

  const handleClearNonwearMarkers = async (): Promise<void> => {
    const ok = await confirm({ title: "Clear Nonwear Markers", description: "Clear all nonwear markers for the current date?", variant: "destructive", confirmLabel: "Clear" });
    if (ok) setNonwearMarkers([]);
  };

  const handleClearAllMarkers = async (): Promise<void> => {
    const ok = await confirm({ title: "Clear All Markers", description: "Clear ALL markers for the current date?", variant: "destructive", confirmLabel: "Clear All" });
    if (ok) {
      useSleepScoringStore.getState().clearAllMarkers();
    }
  };

  const handleApplyPreset = (preset: string): void => {
    const defaults = PRESET_DEFAULTS[preset] ?? PRESET_DEFAULTS["generic"]!;
    setEpochLengthSeconds(defaults.epochLengthSeconds);
    setSkipRows(defaults.skipRows);
    setHasChanges(true);
  };

  /** Upload multiple nonwear CSVs sequentially with progress. */
  const handleNonwearUpload = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;
    const csvFiles = Array.from(fileList).filter((f) => f.name.toLowerCase().endsWith(".csv"));
    if (csvFiles.length === 0) {
      useSleepScoringStore.getState().setUploadResult({ message: "No CSV files found", type: "error" });
      return;
    }
    if (nonwearFileRef.current) nonwearFileRef.current.value = "";
    if (nonwearFolderRef.current) nonwearFolderRef.current.value = "";

    const store = useSleepScoringStore.getState();
    store.setIsUploading(true);
    store.setUploadResult(null);

    (async () => {
      let totalDates = 0;
      let totalMarkers = 0;
      let failed = 0;
      for (let fileIdx = 0; fileIdx < csvFiles.length; fileIdx++) {
        const file = csvFiles[fileIdx]!;
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

  const handleSleepImportUpload = async (e: React.ChangeEvent<HTMLInputElement>): Promise<void> => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSleepImportResult(null);
    setSleepImportLoading(true);
    try {
      const result = await importApi.uploadSleepCsv(file);
      const errMsg = result.errors?.length ? `. ${result.errors[0]}` : "";
      const noSleepMsg = result.no_sleep_dates > 0 ? `, ${result.no_sleep_dates} no-sleep` : "";
      const matchMsg = ` (${result.matched_rows}/${result.total_rows} rows matched)`;
      const nwMsg = result.nonwear_markers_created > 0 ? `, ${result.nonwear_markers_created} nonwear markers` : "";
      const unresolvedCount = (result.unmatched_identifiers?.length ?? 0) + (result.ambiguous_identifiers?.length ?? 0);
      const unresolvedMsg = unresolvedCount > 0 ? `, ${unresolvedCount} unresolved identifier${unresolvedCount === 1 ? "" : "s"}` : "";
      setSleepImportResult({
        message: `${result.dates_imported} dates, ${result.markers_created} markers imported${nwMsg}${noSleepMsg}${result.dates_skipped > 0 ? `, ${result.dates_skipped} skipped` : ""}${matchMsg}${unresolvedMsg}${errMsg}`,
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

  const handleStartAutoScoreBatch = (): void => {
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

      {/* Server uploads */}
      {caps.server && (
        <FileUploadSection files={files} confirm={confirm} />
      )}

      {/* Diary CSV Upload (server only) */}
      {caps.server && <ServerDiaryImportSection />}

      {/* Local Diary Import (local mode only) */}
      {!caps.server && <LocalDiaryImportSection />}

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
          <input
            ref={nonwearFolderRef}
            type="file"
            {...{ webkitdirectory: "" } as React.InputHTMLAttributes<HTMLInputElement>}
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

      {/* Import Marker Exports (server only) */}
      {caps.server && (<Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Import Marker Exports
          </CardTitle>
          <CardDescription>
            Upload a marker CSV exported from the <strong>desktop app</strong> or the <strong>web app&apos;s export page</strong>. Both formats are auto-detected. Rows with <code>Marker Type = &quot;Manual Nonwear&quot;</code> are imported as nonwear markers.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Irreversibility warning */}
          <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-3 text-sm">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-destructive mt-0.5 flex-shrink-0" />
              <div>
                <strong className="text-destructive">This action is irreversible.</strong> Existing sleep and manual nonwear markers for each imported date are <strong>permanently replaced</strong>. Metrics are recalculated automatically from the imported markers. Only import if the corresponding activity files have already been uploaded.
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
                <div><strong>Optional:</strong> marker_type (including &quot;Manual Nonwear&quot; for nonwear rows), marker_index, onset_date, offset_date, needs_consensus</div>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div className="space-y-1">
                <div className="font-medium">Web app exports</div>
                <div><strong>File matching:</strong> Filename column or Participant ID</div>
                <div><strong>Required:</strong> Study Date, plus Onset/Offset Time or Onset/Offset Datetime</div>
                <div><strong>Optional:</strong> Marker Type (including &quot;Manual Nonwear&quot; for nonwear rows), Period Index, Is No Sleep, Needs Consensus</div>
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

      {/* ================================================================ */}
      {/* Local / Browser Processing (bottom of page)                      */}
      {/* ================================================================ */}
      <LocalFileSection isServerMode={caps.server} confirm={confirm} alert={alert} />

      {confirmDialog}
      {alertDialog}
    </div>
  );
}
