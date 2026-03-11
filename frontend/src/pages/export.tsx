/**
 * Export page for generating CSV exports of sleep scoring data.
 * Supports file selection, date range filtering, column presets, and column selection.
 */

import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAlertDialog } from "@/components/ui/confirm-dialog";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSleepScoringStore } from "@/store";
import { fetchWithAuth, getApiBase } from "@/api/client";
import { useAppCapabilities } from "@/hooks/useAppCapabilities";
import { getLocalFiles, type FileRecord } from "@/db";
import { generateLocalExportRows, rowsToCsv, downloadCsv, downloadBlob, downloadMultipleCsvs } from "@/services/local-export";
import { filesQueryOptions, exportColumnsQueryOptions } from "@/api/query-options";

interface ExportColumnInfo {
  name: string;
  category: string;
  description: string | null;
  data_type: string;
  is_default: boolean;
}

interface ExportColumnCategory {
  name: string;
  columns: string[];
}

interface ExportColumnsResponse {
  columns: ExportColumnInfo[];
  categories: ExportColumnCategory[];
}

interface FileInfo {
  id: number;
  filename: string;
  participant_id: string | null;
  status: string;
}

interface FileListResponse {
  items: FileInfo[];
  total: number;
}

interface ExportRequest {
  file_ids: number[];
  columns: string[] | null;
  include_header: boolean;
  include_metadata: boolean;
  date_range: [string, string] | null;
}

type ColumnPreset = "default" | "minimal" | "standard" | "full";

/** Column presets define which categories to include */
const COLUMN_PRESETS: Record<ColumnPreset, { label: string; description: string }> = {
  default: { label: "Default", description: "Columns marked as default by the system" },
  minimal: { label: "Minimal", description: "File info + onset/offset times + TST + SE" },
  standard: { label: "Standard", description: "Default columns + awakening + quality metrics" },
  full: { label: "Full", description: "All available columns" },
};

/** Minimal preset: only the essential columns (must match backend ColumnDefinition.name exactly) */
const MINIMAL_COLUMNS = [
  "Filename", "Participant ID", "Study Date", "Period Index", "Marker Type",
  "Onset Time", "Offset Time", "Total Sleep Time (min)", "Sleep Efficiency (%)",
];

export function ExportPage() {
  const navigate = useNavigate();
  const isAuthenticated = useSleepScoringStore((state) => state.isAuthenticated);
  const caps = useAppCapabilities();
  const username = useSleepScoringStore((state) => state.username);
  const { alert, alertDialog } = useAlertDialog();

  // Selected files and columns state
  const [selectedFileIds, setSelectedFileIds] = useState<number[]>([]);
  const [selectedLocalFileIds, setSelectedLocalFileIds] = useState<number[]>([]);
  const [selectedColumns, setSelectedColumns] = useState<string[] | null>(null);
  const [includeHeader, setIncludeHeader] = useState(true);
  const [includeMetadata, setIncludeMetadata] = useState(false);
  const [activePreset, setActivePreset] = useState<ColumnPreset>("default");
  const [localFiles, setLocalFiles] = useState<FileRecord[]>([]);
  const [isLocalExporting, setIsLocalExporting] = useState(false);

  // Date range state
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");

  // Load local files
  useEffect(() => {
    getLocalFiles().then(setLocalFiles).catch((err) => {
      console.error("Failed to load local files from IndexedDB:", err);
    });
  }, []);

  // Fetch available files (server only)
  const { data: filesData, isLoading: filesLoading } = useQuery({
    ...filesQueryOptions(),
    enabled: isAuthenticated && caps.server,
  });

  // Fetch available columns (server only)
  const { data: columnsData, isLoading: columnsLoading } = useQuery({
    ...exportColumnsQueryOptions(),
    enabled: isAuthenticated && caps.server,
  });

  const defaultSelectedColumns = columnsData?.columns
    ? columnsData.columns.filter((col) => col.is_default).map((col) => col.name)
    : [];
  const activeSelectedColumns = selectedColumns ?? defaultSelectedColumns;

  /** Download a single CSV from the given export endpoint. */
  const downloadFromEndpoint = async (endpoint: string, request: ExportRequest): Promise<boolean> => {
    const { sitePassword, username } = useSleepScoringStore.getState();
    const response = await fetch(`${getApiBase()}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(sitePassword ? { "X-Site-Password": sitePassword } : {}),
        "X-Username": username || "anonymous",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) return false;

    const disposition = response.headers.get("Content-Disposition");
    let filename = "export.csv";
    if (disposition) {
      const match = disposition.match(/filename="(.+)"/);
      if (match) filename = match[1];
    }

    // Backend returns error CSVs with this filename — skip download
    if (filename === "export_error.csv") return false;

    downloadBlob(await response.blob(), filename);
    return true;
  };

  // Export mutation — downloads sleep + nonwear as separate files
  const exportMutation = useMutation({
    mutationFn: async (request: ExportRequest) => {
      const [sleepOk, nonwearOk] = await Promise.all([
        downloadFromEndpoint("/export/csv/download", request),
        downloadFromEndpoint("/export/csv/download/nonwear", request).catch(() => false),
      ]);
      if (!sleepOk) throw new Error("Export failed");
      return { success: true, nonwearOk };
    },
    onSuccess: (data) => {
      if (!data.nonwearOk) {
        alert({ title: "Partial Export", description: "Sleep data exported successfully, but nonwear markers could not be exported. There may be no nonwear data for the selected files." });
      }
    },
    onError: (error: Error) => {
      alert({ title: "Export Failed", description: error.message });
    },
  });

  // Handle file selection toggle
  const toggleFileSelection = (fileId: number) => {
    setSelectedFileIds((prev) =>
      prev.includes(fileId) ? prev.filter((id) => id !== fileId) : [...prev, fileId]
    );
  };

  // Handle select all files
  const selectAllFiles = () => {
    if (filesData?.items) {
      setSelectedFileIds(filesData.items.map((f) => f.id));
    }
  };

  // Handle clear all files
  const clearAllFiles = () => {
    setSelectedFileIds([]);
  };

  // Handle column selection toggle
  const toggleColumnSelection = (columnName: string) => {
    const currentColumns = activeSelectedColumns;
    setSelectedColumns(
      currentColumns.includes(columnName)
        ? currentColumns.filter((name) => name !== columnName)
        : [...currentColumns, columnName]
    );
  };

  // Handle category selection (toggle all columns in category)
  const toggleCategorySelection = (category: ExportColumnCategory) => {
    const currentColumns = activeSelectedColumns;
    const allSelected = category.columns.every((col) =>
      currentColumns.includes(col)
    );
    if (allSelected) {
      // Deselect all in category
      setSelectedColumns(
        currentColumns.filter((col) => !category.columns.includes(col))
      );
    } else {
      // Select all in category
      setSelectedColumns([...new Set([...currentColumns, ...category.columns])]);
    }
  };

  // Handle column preset changes
  const applyPreset = (preset: ColumnPreset) => {
    setActivePreset(preset);
    if (!columnsData) return;

    switch (preset) {
      case "default":
        setSelectedColumns(null); // Falls back to defaultSelectedColumns
        break;
      case "minimal":
        setSelectedColumns(
          columnsData.columns
            .filter((col) => MINIMAL_COLUMNS.includes(col.name))
            .map((col) => col.name)
        );
        break;
      case "standard":
        setSelectedColumns(
          columnsData.columns
            .filter((col) => col.is_default)
            .map((col) => col.name)
        );
        break;
      case "full":
        setSelectedColumns(columnsData.columns.map((col) => col.name));
        break;
    }
  };

  // Handle local export
  const handleLocalExport = async () => {
    if (selectedLocalFileIds.length === 0) {
      alert({ title: "No Files Selected", description: "Please select at least one local file to export" });
      return;
    }
    setIsLocalExporting(true);
    try {
      const { sleepRows, nonwearRows } = await generateLocalExportRows(selectedLocalFileIds, username || "anonymous");
      if (sleepRows.length === 0 && nonwearRows.length === 0) {
        alert({ title: "No Data", description: "No scored data found for the selected files" });
        return;
      }
      const dateStr = new Date().toISOString().slice(0, 10);
      const files: Array<{ csv: string; filename: string }> = [];
      if (sleepRows.length > 0) {
        files.push({ csv: rowsToCsv(sleepRows), filename: `sleep_export_${dateStr}.csv` });
      }
      if (nonwearRows.length > 0) {
        files.push({ csv: rowsToCsv(nonwearRows), filename: `nonwear_export_${dateStr}.csv` });
      }
      if (files.length === 1) {
        downloadCsv(files[0].csv, files[0].filename);
      } else {
        downloadMultipleCsvs(files);
      }
    } catch (err) {
      alert({ title: "Export Failed", description: err instanceof Error ? err.message : "Export failed" });
    } finally {
      setIsLocalExporting(false);
    }
  };

  // Handle server export
  const handleExport = () => {
    if (selectedFileIds.length === 0 && selectedLocalFileIds.length === 0) {
      alert({ title: "No Files Selected", description: "Please select at least one file to export" });
      return;
    }

    // Local files export
    if (selectedLocalFileIds.length > 0 && selectedFileIds.length === 0) {
      handleLocalExport();
      return;
    }

    // Server files export
    const dateRange: [string, string] | null =
      startDate && endDate ? [startDate, endDate] : null;

    exportMutation.mutate({
      file_ids: selectedFileIds,
      columns: activeSelectedColumns.length > 0 ? activeSelectedColumns : null,
      include_header: includeHeader,
      include_metadata: includeMetadata,
      date_range: dateRange,
    });

    // Also export local files if any selected
    if (selectedLocalFileIds.length > 0) {
      handleLocalExport();
    }
  };

  // Redirect if not logged in
  useEffect(() => {
    if (!isAuthenticated) navigate("/login");
  }, [isAuthenticated, navigate]);

  if (!isAuthenticated) return null;

  const isLoading = filesLoading || columnsLoading;

  return (
    <div className="container mx-auto py-6 px-4 max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Export Data</h1>
          <p className="text-muted-foreground">
            Generate CSV exports of sleep scoring data
          </p>
        </div>
        <Button variant="outline" onClick={() => navigate("/scoring")}>
          Back to Scoring
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="text-muted-foreground">Loading...</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* File Selection */}
          <Card>
            <CardHeader>
              <CardTitle>Select Files</CardTitle>
              <CardDescription>
                Choose which files to include in the export
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2 mb-4">
                <Button variant="outline" size="sm" onClick={selectAllFiles}>
                  Select All
                </Button>
                <Button variant="outline" size="sm" onClick={clearAllFiles}>
                  Clear All
                </Button>
              </div>
              <div className="space-y-2 max-h-[400px] overflow-y-auto">
                {filesData?.items.map((file) => (
                  <div
                    key={file.id}
                    className="flex items-center space-x-2 p-2 hover:bg-muted rounded"
                  >
                    <Checkbox
                      id={`file-${file.id}`}
                      checked={selectedFileIds.includes(file.id)}
                      onCheckedChange={() => toggleFileSelection(file.id)}
                    />
                    <Label
                      htmlFor={`file-${file.id}`}
                      className="flex-1 cursor-pointer"
                    >
                      <span className="font-medium">{file.filename}</span>
                      {file.participant_id && (
                        <span className="text-muted-foreground ml-2">
                          ({file.participant_id})
                        </span>
                      )}
                    </Label>
                  </div>
                ))}
                {/* Local files */}
                {localFiles.filter((f) => f.id != null).map((file) => (
                  <div
                    key={`local-${file.id}`}
                    className="flex items-center space-x-2 p-2 hover:bg-muted rounded"
                  >
                    <Checkbox
                      id={`local-file-${file.id}`}
                      checked={selectedLocalFileIds.includes(file.id as number)}
                      onCheckedChange={() => {
                        const fid = file.id as number;
                        setSelectedLocalFileIds((prev) =>
                          prev.includes(fid)
                            ? prev.filter((id) => id !== fid)
                            : [...prev, fid]
                        );
                      }}
                    />
                    <Label
                      htmlFor={`local-file-${file.id}`}
                      className="flex-1 cursor-pointer"
                    >
                      <span className="font-medium">{file.filename}</span>
                      <span className="text-muted-foreground ml-2 text-xs">(local)</span>
                    </Label>
                  </div>
                ))}
                {(!filesData?.items || filesData.items.length === 0) && localFiles.length === 0 && (
                  <div className="text-muted-foreground py-4 text-center">
                    No files available
                  </div>
                )}
              </div>
              <div className="mt-4 text-sm text-muted-foreground">
                {selectedFileIds.length + selectedLocalFileIds.length} of {(filesData?.items.length || 0) + localFiles.length} files
                selected
              </div>
            </CardContent>
          </Card>

          {/* Date Range Filter */}
          <Card>
            <CardHeader>
              <CardTitle>Date Range (Optional)</CardTitle>
              <CardDescription>
                Filter exported data to a specific date range
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="start-date">Start Date</Label>
                  <Input
                    id="start-date"
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="end-date">End Date</Label>
                  <Input
                    id="end-date"
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                  />
                </div>
              </div>
              {startDate && endDate && (
                <div className="mt-3 flex items-center justify-between">
                  <p className="text-sm text-muted-foreground">
                    Filtering: {startDate} to {endDate}
                  </p>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => { setStartDate(""); setEndDate(""); }}
                  >
                    Clear
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Column Selection (server only) */}
          {caps.server && (<Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Select Columns</CardTitle>
                  <CardDescription>
                    Choose which data columns to include
                  </CardDescription>
                </div>
              </div>
              {/* Column Presets */}
              <div className="flex flex-wrap gap-2 pt-2">
                {(Object.entries(COLUMN_PRESETS) as [ColumnPreset, { label: string; description: string }][]).map(
                  ([key, { label, description }]) => (
                    <Button
                      key={key}
                      variant={activePreset === key ? "default" : "outline"}
                      size="sm"
                      className="h-8 text-xs"
                      onClick={() => applyPreset(key)}
                      title={description}
                    >
                      {label}
                    </Button>
                  )
                )}
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4 max-h-[400px] overflow-y-auto">
                {columnsData?.categories.map((category) => {
                  const allSelected = category.columns.every((col) =>
                    activeSelectedColumns.includes(col)
                  );
                  const someSelected = category.columns.some((col) =>
                    activeSelectedColumns.includes(col)
                  );

                  return (
                    <div key={category.name} className="space-y-2">
                      <div
                        className="flex items-center space-x-2 cursor-pointer"
                        onClick={() => toggleCategorySelection(category)}
                      >
                        <Checkbox
                          checked={allSelected}
                          // @ts-expect-error - indeterminate is valid but not in types
                          indeterminate={someSelected && !allSelected}
                          onCheckedChange={() =>
                            toggleCategorySelection(category)
                          }
                        />
                        <span className="font-semibold text-sm">
                          {category.name}
                        </span>
                      </div>
                      <div className="ml-6 grid grid-cols-1 gap-1">
                        {category.columns.map((columnName) => {
                          const column = columnsData.columns.find(
                            (c) => c.name === columnName
                          );
                          return (
                            <div
                              key={columnName}
                              className="flex items-center space-x-2"
                            >
                              <Checkbox
                                id={`col-${columnName}`}
                                checked={activeSelectedColumns.includes(columnName)}
                                onCheckedChange={() =>
                                  toggleColumnSelection(columnName)
                                }
                              />
                              <Label
                                htmlFor={`col-${columnName}`}
                                className="text-sm cursor-pointer"
                                title={column?.description || ""}
                              >
                                {columnName}
                              </Label>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-4 text-sm text-muted-foreground">
                {activeSelectedColumns.length} columns selected
              </div>
            </CardContent>
          </Card>)}

          {/* Export Summary */}
          <Card>
            <CardHeader>
              <CardTitle>Export Summary</CardTitle>
              <CardDescription>
                Overview of the data to be exported
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4">
                <div className="text-center p-3 rounded-lg bg-muted/50">
                  <div className="text-2xl font-bold">{selectedFileIds.length}</div>
                  <div className="text-xs text-muted-foreground">Files selected</div>
                </div>
                <div className="text-center p-3 rounded-lg bg-muted/50">
                  <div className="text-2xl font-bold">{activeSelectedColumns.length}</div>
                  <div className="text-xs text-muted-foreground">Columns selected</div>
                </div>
                <div className="text-center p-3 rounded-lg bg-muted/50">
                  <div className="text-2xl font-bold">
                    {new Set(
                      filesData?.items
                        .filter((f) => selectedFileIds.includes(f.id))
                        .map((f) => f.participant_id)
                        .filter(Boolean)
                    ).size || 0}
                  </div>
                  <div className="text-xs text-muted-foreground">Participants</div>
                </div>
                <div className="text-center p-3 rounded-lg bg-muted/50">
                  <div className="text-2xl font-bold">
                    {startDate && endDate ? "Filtered" : "All"}
                  </div>
                  <div className="text-xs text-muted-foreground">Date range</div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Export Options */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Export Options</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-6">
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="include-header"
                    checked={includeHeader}
                    onCheckedChange={(checked) =>
                      setIncludeHeader(checked === true)
                    }
                  />
                  <Label htmlFor="include-header">Include header row</Label>
                </div>
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="include-metadata"
                    checked={includeMetadata}
                    onCheckedChange={(checked) =>
                      setIncludeMetadata(checked === true)
                    }
                  />
                  <Label htmlFor="include-metadata">
                    Include metadata comments
                  </Label>
                </div>
              </div>

              <div className="mt-6 flex justify-end">
                <Button
                  onClick={handleExport}
                  disabled={
                    (selectedFileIds.length === 0 && selectedLocalFileIds.length === 0) || exportMutation.isPending || isLocalExporting
                  }
                  size="lg"
                >
                  {exportMutation.isPending || isLocalExporting ? "Exporting..." : "Download CSV"}
                </Button>
              </div>

              {exportMutation.isSuccess && (
                <div className="mt-4 p-3 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 rounded">
                  Export completed successfully!
                </div>
              )}

              {exportMutation.isError && (
                <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded">
                  Export failed. Please try again.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
      {alertDialog}
    </div>
  );
}
