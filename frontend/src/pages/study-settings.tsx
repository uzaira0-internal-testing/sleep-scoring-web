import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useConfirmDialog, useAlertDialog } from "@/components/ui/confirm-dialog";
import { EditableList } from "@/components/ui/editable-list";
import { Database, Cpu, Clock, Settings, FlaskConical, FileCode, TestTube, Info, Loader2, Save, RotateCcw, Users, CalendarDays, HelpCircle, Activity } from "lucide-react";
import { useSleepScoringStore } from "@/store";
import { useState, useEffect, useMemo, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { settingsApi } from "@/api/client";
import { studySettingsQueryOptions, pipelineDiscoverQueryOptions } from "@/api/query-options";
import { SLEEP_DETECTION_RULES } from "@/api/types";
import { ALGORITHM_OPTIONS, SLEEP_DETECTION_OPTIONS } from "@/constants/options";
import { useAppCapabilities } from "@/hooks/useAppCapabilities";
import { getLocalStudySettings, saveLocalStudySettings } from "@/db";

/** Build a label lookup from ALGORITHM_OPTIONS, falling back to title-casing */
const _ALGO_LABELS: Record<string, string> = Object.fromEntries(
  ALGORITHM_OPTIONS.map((o) => [o.value, o.label])
);

function formatComponentId(id: string): string {
  return _ALGO_LABELS[id] ?? id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

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

export function StudySettingsPage() {
  const queryClient = useQueryClient();
  const isAuthenticated = useSleepScoringStore((state) => state.isAuthenticated);
  const caps = useAppCapabilities();
  const { confirm, confirmDialog } = useConfirmDialog();
  const { alert, alertDialog } = useAlertDialog();

  const {
    currentAlgorithm,
    setCurrentAlgorithm,
    sleepDetectionRule,
    setSleepDetectionRule,
    nightStartHour,
    nightEndHour,
    setNightHours,
  } = useSleepScoringStore();

  // Track if settings have been modified since last save
  const [hasChanges, setHasChanges] = useState(false);

  // Display & detection axis preferences
  const [choiAxis, setChoiAxis] = useState("vector_magnitude");
  const [preferredActivityColumn, setPreferredActivityColumn] = useState("axis_y");
  const axesSyncedRef = useRef(false);

  // Load study-wide settings (shared across all users) - server only
  const { data: backendSettings, isLoading: isLoadingServer } = useQuery({
    ...studySettingsQueryOptions(),
    enabled: isAuthenticated && caps.server,
  });

  // Discover available pipeline components from backend
  const { data: pipelineDiscovery } = useQuery({
    ...pipelineDiscoverQueryOptions(),
    enabled: isAuthenticated && caps.server,
  });

  // Build algorithm options from discovery endpoint (fallback to hardcoded)
  const algorithmOptions = useMemo(() => {
    const classifiers = pipelineDiscovery?.roles?.epoch_classifier;
    if (!classifiers?.length) return ALGORITHM_OPTIONS as readonly { value: string; label: string }[];
    return classifiers.map((id) => ({
      value: id,
      label: formatComponentId(id),
    }));
  }, [pipelineDiscovery]);

  // Load local study settings from IndexedDB when no server
  const [localSettings, setLocalSettings] = useState<Awaited<ReturnType<typeof getLocalStudySettings>> | null>(null);
  const [isLoadingLocal, setIsLoadingLocal] = useState(true);
  useEffect(() => {
    if (caps.server) return;
    let cancelled = false;
    const load = async () => {
      try {
        const s = await getLocalStudySettings();
        if (!cancelled) setLocalSettings(s ?? null);
      } catch (err) {
        console.error("Failed to load local study settings:", err);
      } finally {
        if (!cancelled) setIsLoadingLocal(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [caps.server]);

  // Sync local settings to store
  useEffect(() => {
    if (caps.server || !localSettings) return;
    if (localSettings.defaultAlgorithm) setCurrentAlgorithm(localSettings.defaultAlgorithm);
    if (localSettings.sleepDetectionRule) setSleepDetectionRule(localSettings.sleepDetectionRule as typeof sleepDetectionRule);
    if (localSettings.nightStartHour != null && localSettings.nightEndHour != null) {
      setNightHours(localSettings.nightStartHour, localSettings.nightEndHour);
    }
  }, [localSettings, caps.server, setCurrentAlgorithm, setSleepDetectionRule, setNightHours]);

  const isLoading = caps.server ? isLoadingServer : isLoadingLocal;

  // Sync backend settings to store on load
  useEffect(() => {
    if (backendSettings) {
      if (backendSettings.default_algorithm) {
        setCurrentAlgorithm(backendSettings.default_algorithm);
      }
      if (backendSettings.sleep_detection_rule) {
        setSleepDetectionRule(backendSettings.sleep_detection_rule as typeof sleepDetectionRule);
      }
      if (backendSettings.night_start_hour != null && backendSettings.night_end_hour != null) {
        setNightHours(backendSettings.night_start_hour, backendSettings.night_end_hour);
      }
    }
  }, [backendSettings, setCurrentAlgorithm, setSleepDetectionRule, setNightHours]);

  // Save study settings mutation
  const saveMutation = useMutation({
    mutationFn: settingsApi.updateStudySettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: studySettingsQueryOptions().queryKey });
      // Also invalidate per-user settings since they merge study settings
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setHasChanges(false);
    },
    onError: (error: Error) => {
      alert({ title: "Save Failed", description: error.message });
    },
  });

  // Reset study settings mutation
  const resetMutation = useMutation({
    mutationFn: settingsApi.resetStudySettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: studySettingsQueryOptions().queryKey });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setHasChanges(false);
    },
    onError: (error: Error) => {
      alert({ title: "Reset Failed", description: error.message });
    },
  });

  // Handlers that track changes
  const handleAlgorithmChange = (value: string) => {
    setCurrentAlgorithm(value);
    setHasChanges(true);
  };

  const handleSleepDetectionChange = (value: string) => {
    setSleepDetectionRule(value as typeof sleepDetectionRule);
    setHasChanges(true);
  };

  const handleNightStartChange = (value: string) => {
    setNightHours(value, nightEndHour);
    setHasChanges(true);
  };

  const handleNightEndChange = (value: string) => {
    setNightHours(nightStartHour, value);
    setHasChanges(true);
  };

  // Regex pattern defaults and state (must be declared before handlers that reference them)
  const DEFAULT_ID_PATTERN = "([A-Z]+-\\d+)";
  const DEFAULT_TIMEPOINT_PATTERN = "_(T\\d+)_";
  const DEFAULT_GROUP_PATTERN = "^([A-Z]+)-";

  const [testFilename, setTestFilename] = useState("TECH-001_T1_20240115.csv");
  const [idPattern, setIdPattern] = useState(DEFAULT_ID_PATTERN);
  const [timepointPattern, setTimepointPattern] = useState(DEFAULT_TIMEPOINT_PATTERN);
  const [groupPattern, setGroupPattern] = useState(DEFAULT_GROUP_PATTERN);
  const regexSyncedRef = useRef(false);

  // Phase 1: Valid groups/timepoints lists, defaults, and unknown value
  const [validGroups, setValidGroups] = useState<string[]>([]);
  const [validTimepoints, setValidTimepoints] = useState<string[]>([]);
  const [defaultGroup, setDefaultGroup] = useState("");
  const [defaultTimepoint, setDefaultTimepoint] = useState("");
  const [unknownValue, setUnknownValue] = useState("UNKNOWN");

  // Auto-nonwear threshold
  const [nonwearThreshold, setNonwearThreshold] = useState(0);

  // Sync axis preferences from backend extra_settings on initial load
  useEffect(() => {
    if (backendSettings?.extra_settings && !axesSyncedRef.current) {
      axesSyncedRef.current = true;
      const extra = backendSettings.extra_settings;
      if (extra.choi_axis) setChoiAxis(extra.choi_axis as string);
      if (extra.preferred_activity_column) setPreferredActivityColumn(extra.preferred_activity_column as string);
      if (extra.nonwear_threshold != null) setNonwearThreshold(extra.nonwear_threshold as number);
    }
  }, [backendSettings]);

  // Sync regex patterns and new fields from backend extra_settings on initial load
  useEffect(() => {
    if (backendSettings?.extra_settings && !regexSyncedRef.current) {
      regexSyncedRef.current = true;
      const extra = backendSettings.extra_settings;
      if (extra.id_pattern) setIdPattern(extra.id_pattern as string);
      if (extra.timepoint_pattern) setTimepointPattern(extra.timepoint_pattern as string);
      if (extra.group_pattern) setGroupPattern(extra.group_pattern as string);
      if (Array.isArray(extra.valid_groups)) setValidGroups(extra.valid_groups as string[]);
      if (Array.isArray(extra.valid_timepoints)) setValidTimepoints(extra.valid_timepoints as string[]);
      if (extra.default_group) setDefaultGroup(extra.default_group as string);
      if (extra.default_timepoint) setDefaultTimepoint(extra.default_timepoint as string);
      if (extra.unknown_value) setUnknownValue(extra.unknown_value as string);
    }
  }, [backendSettings]);

  // Save study-wide settings
  const handleSave = () => {
    const extraSettings = {
      id_pattern: idPattern,
      timepoint_pattern: timepointPattern,
      group_pattern: groupPattern,
      valid_groups: validGroups,
      valid_timepoints: validTimepoints,
      default_group: defaultGroup,
      default_timepoint: defaultTimepoint,
      unknown_value: unknownValue,
      choi_axis: choiAxis,
      preferred_activity_column: preferredActivityColumn,
      nonwear_threshold: nonwearThreshold,
    };

    if (caps.server) {
      saveMutation.mutate({
        default_algorithm: currentAlgorithm,
        sleep_detection_rule: sleepDetectionRule,
        night_start_hour: nightStartHour,
        night_end_hour: nightEndHour,
        extra_settings: extraSettings,
      });
    } else {
      // Save to IndexedDB
      saveLocalStudySettings({
        defaultAlgorithm: currentAlgorithm,
        sleepDetectionRule,
        nightStartHour,
        nightEndHour,
        extraSettings,
      })
        .then(() => setHasChanges(false))
        .catch((err) => alert({ title: "Save Failed", description: err instanceof Error ? err.message : "Failed to save" }));
    }
  };

  // Reset to defaults (local state cleared in onSuccess to avoid desync)
  const handleReset = async () => {
    const ok = await confirm({ title: "Reset Settings", description: "Reset all settings to defaults?" });
    if (ok) {
      resetMutation.mutate(undefined, {
        onSuccess: () => {
          setIdPattern(DEFAULT_ID_PATTERN);
          setTimepointPattern(DEFAULT_TIMEPOINT_PATTERN);
          setGroupPattern(DEFAULT_GROUP_PATTERN);
          setValidGroups([]);
          setValidTimepoints([]);
          setDefaultGroup("");
          setDefaultTimepoint("");
          setUnknownValue("UNKNOWN");
          regexSyncedRef.current = false;
        },
      });
    }
  };

  // Parse test results
  const parseTestResults = () => {
    const results: { field: string; pattern: string; match: string | null }[] = [];

    try {
      const idMatch = testFilename.match(new RegExp(idPattern));
      results.push({ field: "Participant ID", pattern: idPattern, match: idMatch?.[1] ?? null });
    } catch {
      results.push({ field: "Participant ID", pattern: idPattern, match: null });
    }

    try {
      const tpMatch = testFilename.match(new RegExp(timepointPattern));
      results.push({ field: "Timepoint", pattern: timepointPattern, match: tpMatch?.[1] ?? null });
    } catch {
      results.push({ field: "Timepoint", pattern: timepointPattern, match: null });
    }

    try {
      const grpMatch = testFilename.match(new RegExp(groupPattern));
      results.push({ field: "Group", pattern: groupPattern, match: grpMatch?.[1] ?? null });
    } catch {
      results.push({ field: "Group", pattern: groupPattern, match: null });
    }

    return results;
  };

  const testResults = parseTestResults();

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
          <h1 className="text-2xl font-bold">Study Settings</h1>
          <p className="text-muted-foreground">
            Configure study parameters and processing algorithms
          </p>
        </div>
        <div className="flex items-center gap-2">
          {hasChanges && (
            <span className="text-sm text-amber-600 dark:text-amber-400">Unsaved changes</span>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={resetMutation.isPending}
          >
            {resetMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <RotateCcw className="h-4 w-4 mr-1" />
            )}
            Reset
          </Button>
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

      {/* Data Paradigm Info - Epoch-based only for now */}
      <Card className="border-green-500/50 bg-green-500/5">
        <CardContent className="py-4">
          <div className="flex items-start gap-3">
            <Database className="h-5 w-5 text-green-600 mt-0.5" />
            <div>
              <div className="font-medium">Data Paradigm: Epoch-Based</div>
              <div className="text-sm text-muted-foreground">
                CSV files with pre-calculated 60-second activity counts. Compatible with ActiGraph, Actiwatch, and MotionWatch CSV exports.
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Regex Patterns */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileCode className="h-5 w-5" />
            Filename Patterns
          </CardTitle>
          <CardDescription>
            Configure regex patterns to extract participant information from filenames
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="id-pattern">Participant ID Pattern</Label>
              <Input
                id="id-pattern"
                value={idPattern}
                onChange={(e) => { setIdPattern(e.target.value); setHasChanges(true); }}
                placeholder="([A-Z]+-\d+)"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="timepoint-pattern">Timepoint Pattern</Label>
              <Input
                id="timepoint-pattern"
                value={timepointPattern}
                onChange={(e) => { setTimepointPattern(e.target.value); setHasChanges(true); }}
                placeholder="_(T\d+)_"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="group-pattern">Group Pattern</Label>
              <Input
                id="group-pattern"
                value={groupPattern}
                onChange={(e) => { setGroupPattern(e.target.value); setHasChanges(true); }}
                placeholder="^([A-Z]+)-"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Live Pattern Testing */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TestTube className="h-5 w-5" />
            Test Patterns
          </CardTitle>
          <CardDescription>
            Test your regex patterns against a sample filename
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="test-filename">Test Filename</Label>
            <Input
              id="test-filename"
              value={testFilename}
              onChange={(e) => setTestFilename(e.target.value)}
              placeholder="TECH-001_T1_20240115.csv"
            />
          </div>
          <div className="rounded-lg border p-4 bg-muted/50">
            <div className="text-sm font-medium mb-2">Extraction Results:</div>
            <div className="space-y-1 text-sm">
              {testResults.map((result) => (
                <div key={result.field} className="flex items-center gap-2">
                  <span className="font-medium w-32">{result.field}:</span>
                  {result.match ? (
                    <span className="text-green-600 dark:text-green-400 font-mono">{result.match}</span>
                  ) : (
                    <span className="text-red-600 dark:text-red-400">No match</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Sleep/Wake Algorithm */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-5 w-5" />
            Sleep/Wake Algorithm
          </CardTitle>
          <CardDescription>
            Select the algorithm used to classify sleep and wake epochs
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="algorithm">Algorithm</Label>
            <Select
              id="algorithm"
              value={currentAlgorithm}
              onChange={(e) => handleAlgorithmChange(e.target.value)}
              options={algorithmOptions}
            />
          </div>
          <div className="rounded-lg border p-3 bg-muted/30 text-sm">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div>
                {currentAlgorithm.includes("sadeh") ? (
                  <>
                    <strong>Sadeh Algorithm:</strong> Uses Y-axis activity counts with a weighted moving average. The ActiLife variant matches ActiGraph's ActiLife software output.
                  </>
                ) : (
                  <>
                    <strong>Cole-Kripke Algorithm:</strong> Alternative scoring method using different weighting coefficients. The ActiLife variant matches ActiGraph's ActiLife software output.
                  </>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Sleep Period Detection */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5" />
            Sleep Period Detection
          </CardTitle>
          <CardDescription>
            Configure how sleep onset and offset are detected from algorithm results
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="sleep-detection">Detection Rule</Label>
            <Select
              id="sleep-detection"
              value={sleepDetectionRule}
              onChange={(e) => handleSleepDetectionChange(e.target.value)}
              options={SLEEP_DETECTION_OPTIONS}
            />
          </div>
          <div className="rounded-lg border p-3 bg-muted/30 text-sm">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div>
                {sleepDetectionRule === SLEEP_DETECTION_RULES.CONSECUTIVE_3S_5S && (
                  <>Sleep onset after 3 consecutive minutes of sleep. Sleep offset after 5 consecutive minutes of wake.</>
                )}
                {sleepDetectionRule === SLEEP_DETECTION_RULES.CONSECUTIVE_5S_10S && (
                  <>Sleep onset after 5 consecutive minutes of sleep. Sleep offset after 10 consecutive minutes of wake.</>
                )}
                {sleepDetectionRule === SLEEP_DETECTION_RULES.TUDOR_LOCKE_2014 && (
                  <>Tudor-Locke (2014) algorithm for sleep period detection with validated parameters.</>
                )}
                {![SLEEP_DETECTION_RULES.CONSECUTIVE_3S_5S, SLEEP_DETECTION_RULES.CONSECUTIVE_5S_10S, SLEEP_DETECTION_RULES.TUDOR_LOCKE_2014].includes(sleepDetectionRule) && (
                  <>Select a detection rule above.</>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Night Hours Window */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Night Hours Window
          </CardTitle>
          <CardDescription>
            Define the time window for detecting main sleep periods
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4 max-w-md">
            <div className="space-y-2">
              <Label htmlFor="night-start">Night Start</Label>
              <Input
                id="night-start"
                type="time"
                value={nightStartHour}
                onChange={(e) => handleNightStartChange(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="night-end">Night End</Label>
              <Input
                id="night-end"
                type="time"
                value={nightEndHour}
                onChange={(e) => handleNightEndChange(e.target.value)}
              />
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            Main sleep periods are expected to start within this window. Used for automatic sleep detection.
          </p>
        </CardContent>
      </Card>

      {/* Valid Groups */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            Valid Groups
          </CardTitle>
          <CardDescription>
            Define the valid group labels for your study. Used to validate extracted groups from filenames.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <EditableList
            items={validGroups}
            onChange={(items) => { setValidGroups(items); setHasChanges(true); }}
            placeholder="Add group (e.g., TECH, CTRL)..."
          />
          {validGroups.length > 0 && (
            <div className="space-y-2">
              <Label htmlFor="default-group">Default Group</Label>
              <Select
                id="default-group"
                value={defaultGroup}
                onChange={(e) => { setDefaultGroup(e.target.value); setHasChanges(true); }}
                options={[
                  { value: "", label: "None" },
                  ...validGroups.map((g) => ({ value: g, label: g })),
                ]}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Valid Timepoints */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CalendarDays className="h-5 w-5" />
            Valid Timepoints
          </CardTitle>
          <CardDescription>
            Define the valid timepoint labels for your study. Used to validate extracted timepoints from filenames.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <EditableList
            items={validTimepoints}
            onChange={(items) => { setValidTimepoints(items); setHasChanges(true); }}
            placeholder="Add timepoint (e.g., T1, T2)..."
          />
          {validTimepoints.length > 0 && (
            <div className="space-y-2">
              <Label htmlFor="default-timepoint">Default Timepoint</Label>
              <Select
                id="default-timepoint"
                value={defaultTimepoint}
                onChange={(e) => { setDefaultTimepoint(e.target.value); setHasChanges(true); }}
                options={[
                  { value: "", label: "None" },
                  ...validTimepoints.map((t) => ({ value: t, label: t })),
                ]}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Unknown Value */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HelpCircle className="h-5 w-5" />
            Unknown Value Placeholder
          </CardTitle>
          <CardDescription>
            The value used when a group or timepoint cannot be determined from the filename
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 max-w-xs">
            <Label htmlFor="unknown-value">Unknown Value</Label>
            <Input
              id="unknown-value"
              value={unknownValue}
              onChange={(e) => { setUnknownValue(e.target.value); setHasChanges(true); }}
              placeholder="UNKNOWN"
            />
          </div>
        </CardContent>
      </Card>

      {/* Display & Detection Axes */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Display &amp; Detection Axes
          </CardTitle>
          <CardDescription>
            Configure which activity axis to display on the scoring plot and use for nonwear detection
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="preferred-activity">Preferred Display Column</Label>
              <Select
                id="preferred-activity"
                value={preferredActivityColumn}
                onChange={(e) => { setPreferredActivityColumn(e.target.value); setHasChanges(true); }}
                options={ACTIVITY_COLUMN_OPTIONS}
              />
              <p className="text-xs text-muted-foreground">
                The activity axis shown by default on the scoring plot
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="choi-axis">Choi Nonwear Detection Axis</Label>
              <Select
                id="choi-axis"
                value={choiAxis}
                onChange={(e) => { setChoiAxis(e.target.value); setHasChanges(true); }}
                options={CHOI_AXIS_OPTIONS}
              />
              <p className="text-xs text-muted-foreground">
                The axis used for the Choi nonwear algorithm
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Nonwear Detection */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Nonwear Detection
          </CardTitle>
          <CardDescription>
            Algorithm for detecting device non-wear periods
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border p-3 bg-muted/30 text-sm">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
              <div>
                <strong>Choi Algorithm (2011):</strong> Uses 90-minute window with 2-minute spike tolerance. Standard algorithm for epoch-based actigraphy data.
              </div>
            </div>
          </div>
          <div className="space-y-2 max-w-xs">
            <Label htmlFor="nonwear-threshold">Auto-Nonwear Activity Threshold</Label>
            <Input
              id="nonwear-threshold"
              type="number"
              min={0}
              max={1000}
              value={nonwearThreshold}
              onChange={(e) => { setNonwearThreshold(parseInt(e.target.value) || 0); setHasChanges(true); }}
            />
            <p className="text-xs text-muted-foreground">
              Epochs with activity counts (max of Y-axis and VM) at or below this value are considered &ldquo;zero activity&rdquo; for auto-nonwear detection. Default: 0.
            </p>
          </div>
        </CardContent>
      </Card>
      {confirmDialog}
      {alertDialog}
    </div>
  );
}
