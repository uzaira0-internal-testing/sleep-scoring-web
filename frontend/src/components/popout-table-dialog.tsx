import { useCallback, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSleepScoringStore, useMarkers, useDates } from "@/store";
import { fetchWithAuth, getApiBase } from "@/api/client";
import { hexToRgba } from "@/lib/color-themes";
import { WindowPortal } from "./window-portal";
import { Home } from "lucide-react";

// TODO: Generate these types from backend OpenAPI schema
interface FullTableDataPoint {
  timestamp: number;
  datetime_str: string;
  axis_y: number;
  vector_magnitude: number;
  algorithm_result: number | null;
  choi_result: number | null;
  is_nonwear: boolean;
}

interface FullTableResponse {
  data: FullTableDataPoint[];
  total_rows: number;
  start_time: string | null;
  end_time: string | null;
}

interface PopoutTableDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Which marker type to highlight: "onset" or "offset" */
  highlightType?: "onset" | "offset";
}

/**
 * Full 48h data table in a separate browser window with click-to-move support.
 * Renders via React portal so Zustand store and all callbacks stay connected.
 * Each highlightType gets its own independent window.
 */
export function PopoutTableDialog({ open, onOpenChange, highlightType = "onset" }: PopoutTableDialogProps) {
  const currentFileId = useSleepScoringStore((state) => state.currentFileId);
  const { currentDate } = useDates();
  const isAuthenticated = useSleepScoringStore((state) => state.isAuthenticated);
  const colorTheme = useSleepScoringStore((state) => state.colorTheme);

  const { sleepMarkers, nonwearMarkers, selectedPeriodIndex, updateMarker, markerMode } = useMarkers();

  const tableRef = useRef<HTMLDivElement>(null);
  const markerRowRef = useRef<HTMLTableRowElement>(null);

  // Get current marker timestamp for highlighting (supports both sleep and nonwear modes)
  const currentMarker = markerMode === "sleep"
    ? sleepMarkers[selectedPeriodIndex ?? -1]
    : nonwearMarkers[selectedPeriodIndex ?? -1];
  const targetTimestamp = currentMarker
    ? markerMode === "sleep"
      ? highlightType === "onset" ? currentMarker.onsetTimestamp : currentMarker.offsetTimestamp
      : highlightType === "onset" ? currentMarker.startTimestamp : currentMarker.endTimestamp
    : null;

  // Fetch full table data from API
  const { data: tableData, isLoading } = useQuery({
    queryKey: ["full-table", currentFileId, currentDate],
    queryFn: async () => {
      if (!currentFileId || !currentDate) {
        return null;
      }
      const url = `${getApiBase()}/markers/${currentFileId}/${currentDate}/table-full`;
      return fetchWithAuth<FullTableResponse>(url);
    },
    enabled: open && isAuthenticated && !!currentFileId && !!currentDate,
    staleTime: 60000,
  });

  // Find marker row index
  const markerRowIndex = tableData?.data?.findIndex(
    (row) => targetTimestamp && Math.abs(row.timestamp * 1000 - targetTimestamp) < 60000
  );

  // Scroll marker row into view when data loads or marker changes
  useEffect(() => {
    if (open && markerRowRef.current) {
      setTimeout(() => {
        markerRowRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      }, 100);
    }
  }, [open, tableData, markerRowIndex]);

  // "Go to marker" scroll handler
  const scrollToMarker = useCallback(() => {
    if (markerRowRef.current) {
      markerRowRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, []);

  // Handle click-to-move (supports both sleep and nonwear modes)
  const handleRowClick = useCallback((row: FullTableDataPoint) => {
    if (selectedPeriodIndex === null) return;

    const newTimestamp = row.timestamp * 1000;

    if (markerMode === "sleep") {
      if (highlightType === "onset") {
        updateMarker("sleep", selectedPeriodIndex, { onsetTimestamp: newTimestamp });
      } else {
        updateMarker("sleep", selectedPeriodIndex, { offsetTimestamp: newTimestamp });
      }
    } else {
      if (highlightType === "onset") {
        updateMarker("nonwear", selectedPeriodIndex, { startTimestamp: newTimestamp });
      } else {
        updateMarker("nonwear", selectedPeriodIndex, { endTimestamp: newTimestamp });
      }
    }
  }, [selectedPeriodIndex, markerMode, highlightType, updateMarker]);

  const data = tableData?.data ?? [];

  const isSleepMode = markerMode === "sleep";

  const markerLabel = isSleepMode
    ? highlightType === "onset" ? "onset" : "offset"
    : highlightType === "onset" ? "start" : "end";

  const handleClose = useCallback(() => onOpenChange(false), [onOpenChange]);

  // Offset window position so onset and offset don't overlap
  const windowTitle = `${highlightType === "onset" ? "Onset" : "Offset"} — ${currentDate ?? ""}`;

  return (
    <WindowPortal
      open={open}
      onClose={handleClose}
      title={windowTitle}
      windowName={`popout-${highlightType}`}
      width={750}
      height={900}
    >
      <div className="h-screen flex flex-col bg-background text-foreground text-sm">
        {/* Header with go-to-marker button */}
        <div className="flex-none px-4 py-3 border-b bg-muted/30">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-base">
                {isSleepMode
                  ? highlightType === "onset" ? "Sleep Onset Table" : "Sleep Offset Table"
                  : highlightType === "onset" ? "NW Start Table" : "NW End Table"
                }
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                {tableData?.start_time && tableData?.end_time && (
                  <span>{tableData.start_time} to {tableData.end_time} ({tableData.total_rows} epochs)</span>
                )}
                {" | "}Click any row to move the {markerLabel} marker
              </p>
            </div>
            {/* Go to marker button */}
            <button
              onClick={scrollToMarker}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-primary/10 hover:bg-primary/20 text-primary transition-colors"
              title="Scroll to current marker position"
            >
              <Home className="h-3.5 w-3.5" />
              Go to marker
            </button>
          </div>
        </div>

        {/* Table */}
        <div ref={tableRef} className="flex-1 overflow-auto">
          {isLoading ? (
            <div className="flex items-center justify-center h-32 text-muted-foreground">
              Loading...
            </div>
          ) : data.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-muted-foreground">
              No data available
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-background border-b z-10">
                <tr>
                  <th className="px-2 py-1.5 text-left whitespace-nowrap font-medium">#</th>
                  <th className="px-2 py-1.5 text-left whitespace-nowrap font-medium">Time</th>
                  <th className="px-2 py-1.5 text-right whitespace-nowrap font-medium" title="Axis Y Activity">Axis Y</th>
                  <th className="px-2 py-1.5 text-right whitespace-nowrap font-medium" title="Vector Magnitude">VM</th>
                  <th className="px-2 py-1.5 text-center whitespace-nowrap font-medium" title="Sleep/Wake">Sleep</th>
                  <th className="px-2 py-1.5 text-center whitespace-nowrap font-medium" title="Choi Nonwear Detection">Choi</th>
                  <th className="px-2 py-1.5 text-center whitespace-nowrap font-medium" title="Nonwear Sensor">NWT</th>
                </tr>
              </thead>
              <tbody>
                {data.map((row, idx) => {
                  const isMarkerRow = idx === markerRowIndex;
                  const sleepWake = row.algorithm_result === 1 ? "Sleep" : row.algorithm_result === 0 ? "Wake" : "-";
                  const choiLabel = row.choi_result === 1 ? "Nonwear" : "-";
                  const nwLabel = row.is_nonwear ? "Nonwear" : "-";

                  return (
                    <tr
                      key={idx}
                      ref={isMarkerRow ? markerRowRef : undefined}
                      onClick={() => handleRowClick(row)}
                      className={`border-b cursor-pointer transition-colors ${
                        isMarkerRow
                          ? "font-bold border-l-4"
                          : "hover:bg-muted/50"
                      }`}
                      style={isMarkerRow ? {
                        backgroundColor: hexToRgba(isSleepMode ? colorTheme.sleepOverlay : colorTheme.nonwear, 0.25),
                        borderLeftColor: isSleepMode ? colorTheme.sleepOverlay : colorTheme.nonwear,
                      } : undefined}
                    >
                      <td className="px-2 py-1 text-muted-foreground font-mono">{idx + 1}</td>
                      <td className="px-2 py-1 font-mono">{row.datetime_str}</td>
                      <td className="px-2 py-1 text-right font-mono">{row.axis_y}</td>
                      <td className="px-2 py-1 text-right font-mono text-muted-foreground">{row.vector_magnitude}</td>
                      <td className={`px-2 py-1 text-center ${
                        sleepWake === "Sleep" ? "text-purple-600 dark:text-purple-400" :
                        sleepWake === "Wake" ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"
                      }`}>
                        {sleepWake}
                      </td>
                      <td className={`px-2 py-1 text-center ${
                        choiLabel === "Nonwear" ? "text-red-600 dark:text-red-400" : "text-muted-foreground"
                      }`}>
                        {choiLabel}
                      </td>
                      <td className={`px-2 py-1 text-center ${
                        nwLabel === "Nonwear" ? "text-orange-600 dark:text-orange-400" : "text-muted-foreground"
                      }`}>
                        {nwLabel}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="flex-none text-xs text-muted-foreground text-center py-2 border-t">
          {data.length} epochs | Close this window or the main app to dismiss
        </div>
      </div>
    </WindowPortal>
  );
}
