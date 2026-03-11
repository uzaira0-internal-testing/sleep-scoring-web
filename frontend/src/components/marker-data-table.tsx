import { useRef, useEffect, useCallback } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { useSleepScoringStore, useMarkers, useDates } from "@/store";
import { fetchWithAuth, getApiBase } from "@/api/client";
import { hexToRgba } from "@/lib/color-themes";
import { Maximize2, Home } from "lucide-react";
import type { OnsetOffsetDataPoint, OnsetOffsetTableResponse } from "@/api/types";
import * as localDb from "@/db";


/** Build table data from local IndexedDB activity data around a marker timestamp. */
async function buildLocalTableData(
  fileId: number,
  date: string,
  onsetTs: number | null,
  offsetTs: number | null,
  windowMinutes: number,
): Promise<OnsetOffsetTableResponse | null> {
  const day = await localDb.getActivityDay(fileId, date);
  if (!day) return null;

  const tsSec = Array.from(new Float64Array(day.timestamps));
  const axisY = Array.from(new Float64Array(day.axisY));
  const vm = Array.from(new Float64Array(day.vectorMagnitude));
  const algoKey = Object.keys(day.algorithmResults)[0];
  const algoResults = algoKey ? new Uint8Array(day.algorithmResults[algoKey]) : null;
  const nwResults = day.nonwearResults ? new Uint8Array(day.nonwearResults) : null;

  const buildWindow = (centerTs: number | null): OnsetOffsetDataPoint[] => {
    if (centerTs == null || tsSec.length === 0) return [];
    const halfWindow = windowMinutes * 60 / 2;
    const points: OnsetOffsetDataPoint[] = [];
    for (let i = 0; i < tsSec.length; i++) {
      if (tsSec[i] >= centerTs - halfWindow && tsSec[i] <= centerTs + halfWindow) {
        const d = new Date(tsSec[i] * 1000);
        points.push({
          timestamp: tsSec[i],
          datetime_str: `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`,
          axis_y: Math.round(axisY[i] ?? 0),
          vector_magnitude: Math.round(vm[i] ?? 0),
          algorithm_result: algoResults ? algoResults[i] ?? null : null,
          choi_result: nwResults ? nwResults[i] ?? null : null,
          is_nonwear: nwResults ? nwResults[i] === 1 : false,
        });
      }
    }
    return points;
  };

  return {
    onset_data: buildWindow(onsetTs),
    offset_data: buildWindow(offsetTs),
    period_index: 1,
  };
}

interface MarkerDataTableProps {
  type: "onset" | "offset";
  onOpenPopout?: () => void;
}

/**
 * Shows activity data around a marker timestamp with click-to-move support.
 */
export function MarkerDataTable({ type, onOpenPopout }: MarkerDataTableProps) {
  const currentFileId = useSleepScoringStore((state) => state.currentFileId);
  const { currentDate } = useDates();
  const isAuthenticated = useSleepScoringStore((state) => state.isAuthenticated);
  const colorTheme = useSleepScoringStore((state) => state.colorTheme);

  const { sleepMarkers, nonwearMarkers, selectedPeriodIndex, markerMode, updateMarker } = useMarkers();

  const tableRef = useRef<HTMLDivElement>(null);
  const markerRowRef = useRef<HTMLTableRowElement>(null);

  const isSleepMode = markerMode === "sleep";
  const title = isSleepMode
    ? type === "onset" ? "Sleep Onset" : "Sleep Offset"
    : type === "onset" ? "NW Start" : "NW End";

  const currentMarker = isSleepMode
    ? sleepMarkers[selectedPeriodIndex ?? -1]
    : nonwearMarkers[selectedPeriodIndex ?? -1];

  const targetTimestamp = currentMarker
    ? isSleepMode
      ? type === "onset" ? (currentMarker as { onsetTimestamp: number | null }).onsetTimestamp : (currentMarker as { offsetTimestamp: number | null }).offsetTimestamp
      : type === "onset" ? (currentMarker as { startTimestamp: number | null }).startTimestamp : (currentMarker as { endTimestamp: number | null }).endTimestamp
    : null;

  // Get marker timestamps to pass as query params (avoids requiring DB save first)
  const onsetTs = currentMarker
    ? isSleepMode
      ? (currentMarker as { onsetTimestamp: number | null }).onsetTimestamp
      : (currentMarker as { startTimestamp: number | null }).startTimestamp
    : null;
  const offsetTs = currentMarker
    ? isSleepMode
      ? (currentMarker as { offsetTimestamp: number | null }).offsetTimestamp
      : (currentMarker as { endTimestamp: number | null }).endTimestamp
    : null;

  // Quantize timestamps to 5-minute buckets for the query key so that small drag
  // movements don't create a new cache key on every mousemove tick (reduces flicker)
  const quantize = (ts: number | null) => ts !== null ? Math.round(ts / 300) : null;

  const isLocal = useSleepScoringStore((state) => state.currentFileSource === "local");

  const { data: tableData, isLoading } = useQuery({
    queryKey: ["marker-table", currentFileId, currentDate, selectedPeriodIndex, type, quantize(onsetTs), quantize(offsetTs), isLocal ? "local" : "server"],
    queryFn: async () => {
      if (!currentFileId || !currentDate || selectedPeriodIndex === null) return null;

      // Local mode: build table data directly from IndexedDB
      if (isLocal) {
        return buildLocalTableData(currentFileId, currentDate, onsetTs, offsetTs, 100);
      }

      // Server mode: fetch from backend API
      const params = new URLSearchParams({ window_minutes: "100" });
      if (onsetTs !== null) params.set("onset_ts", String(onsetTs));
      if (offsetTs !== null) params.set("offset_ts", String(offsetTs));
      const url = `${getApiBase()}/markers/${currentFileId}/${currentDate}/table/${selectedPeriodIndex + 1}?${params}`;
      try {
        return await fetchWithAuth<OnsetOffsetTableResponse>(url);
      } catch {
        // 404 is expected when marker hasn't been saved to backend yet and no timestamps provided
        return null;
      }
    },
    enabled: (isLocal || isAuthenticated) && !!currentFileId && !!currentDate && selectedPeriodIndex !== null && onsetTs !== null && offsetTs !== null,
    staleTime: 30000,
    placeholderData: keepPreviousData,
  });

  const data = type === "onset" ? tableData?.onset_data : tableData?.offset_data;

  const markerRowIndex = data?.findIndex(
    (row) => targetTimestamp && Math.abs(row.timestamp - targetTimestamp) < 60
  );

  // Track previous marker row index to only scroll when it actually changes
  const prevMarkerRowRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (markerRowRef.current && tableRef.current && markerRowIndex !== prevMarkerRowRef.current) {
      prevMarkerRowRef.current = markerRowIndex;
      markerRowRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [markerRowIndex]);

  // "Go to marker" scroll handler
  const scrollToMarker = useCallback(() => {
    if (markerRowRef.current) {
      markerRowRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, []);

  const handleRowClick = useCallback((row: OnsetOffsetDataPoint) => {
    if (selectedPeriodIndex === null) return;
    if (isSleepMode) {
      if (type === "onset") updateMarker("sleep", selectedPeriodIndex, { onsetTimestamp: row.timestamp });
      else updateMarker("sleep", selectedPeriodIndex, { offsetTimestamp: row.timestamp });
    } else {
      if (type === "onset") updateMarker("nonwear", selectedPeriodIndex, { startTimestamp: row.timestamp });
      else updateMarker("nonwear", selectedPeriodIndex, { endTimestamp: row.timestamp });
    }
  }, [selectedPeriodIndex, isSleepMode, type, updateMarker]);

  // Empty / Loading states
  if (selectedPeriodIndex === null) {
    return (
      <div className="h-full flex flex-col">
        <TableHeader title={title} onOpenPopout={onOpenPopout} onScrollToMarker={scrollToMarker} />
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-xs text-muted-foreground text-center">
            {isSleepMode ? "Select a sleep marker" : "Select a nonwear marker"}
          </p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="h-full flex flex-col">
        <TableHeader title={title} onOpenPopout={onOpenPopout} onScrollToMarker={scrollToMarker} />
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="h-full flex flex-col">
        <TableHeader title={title} onOpenPopout={onOpenPopout} onScrollToMarker={scrollToMarker} />
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-xs text-muted-foreground">No data available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <TableHeader title={title} onOpenPopout={onOpenPopout} onScrollToMarker={scrollToMarker} />
      <div ref={tableRef} className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-background/95 backdrop-blur-sm border-b z-10">
            <tr className="text-muted-foreground">
              <th className="px-2 py-1.5 text-left font-medium">Time</th>
              <th className="px-1.5 py-1.5 text-right font-medium" title="Axis Y">Y</th>
              <th className="px-1.5 py-1.5 text-right font-medium" title="Vector Magnitude">VM</th>
              <th className="px-1.5 py-1.5 text-center font-medium" title="Sleep/Wake">S</th>
              <th className="px-1.5 py-1.5 text-center font-medium" title="Choi Nonwear">C</th>
              <th className="px-1.5 py-1.5 text-center font-medium" title="Nonwear Sensor">N</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row, idx) => {
              const isMarkerRow = idx === markerRowIndex;
              const sleepWake = row.algorithm_result === 1 ? "S" : row.algorithm_result === 0 ? "W" : "-";
              const choiLabel = row.choi_result === 1 ? "N" : "-";
              const nwLabel = row.is_nonwear ? "N" : "-";

              return (
                <tr
                  key={idx}
                  ref={isMarkerRow ? markerRowRef : undefined}
                  onClick={() => handleRowClick(row)}
                  className={`border-b border-border/20 cursor-pointer transition-colors ${
                    isMarkerRow
                      ? "font-bold"
                      : "hover:bg-muted/40"
                  }`}
                  style={isMarkerRow ? {
                    backgroundColor: hexToRgba(isSleepMode ? colorTheme.sleepOverlay : colorTheme.nonwear, 0.25),
                    borderLeft: `3px solid ${isSleepMode ? colorTheme.sleepOverlay : colorTheme.nonwear}`,
                    boxShadow: `inset 0 0 0 1px ${hexToRgba(isSleepMode ? colorTheme.sleepOverlay : colorTheme.nonwear, 0.3)}`,
                  } : undefined}
                >
                  <td className="px-2 py-1 font-mono">{row.datetime_str}</td>
                  <td className="px-1.5 py-1 text-right font-mono">{row.axis_y}</td>
                  <td className="px-1.5 py-1 text-right font-mono text-muted-foreground">{row.vector_magnitude}</td>
                  <td className={`px-1.5 py-1 text-center font-medium ${
                    sleepWake === "S" ? "text-sleep" : sleepWake === "W" ? "text-warning" : "text-muted-foreground/40"
                  }`}>
                    {sleepWake}
                  </td>
                  <td className={`px-1.5 py-1 text-center ${choiLabel === "N" ? "text-destructive" : "text-muted-foreground/40"}`}>
                    {choiLabel}
                  </td>
                  <td className={`px-1.5 py-1 text-center ${nwLabel === "N" ? "text-nonwear" : "text-muted-foreground/40"}`}>
                    {nwLabel}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="text-xs text-muted-foreground/60 text-center py-1.5 border-t border-border/40 font-mono">
        {data.length} rows
      </div>
    </div>
  );
}

/** Table header with title, go-to-marker button, and popout button */
function TableHeader({
  title,
  onOpenPopout,
  onScrollToMarker,
}: {
  title: string;
  onOpenPopout?: (() => void) | undefined;
  onScrollToMarker?: () => void;
}) {
  return (
    <div className="flex-none text-xs font-medium py-1.5 border-b border-border/40 flex items-center justify-between px-2.5">
      <span>{title}</span>
      <div className="flex items-center gap-1">
        {onScrollToMarker && (
          <button
            className="h-5 w-5 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            onClick={onScrollToMarker}
            title="Go to current marker"
          >
            <Home className="h-3.5 w-3.5" />
          </button>
        )}
        {onOpenPopout && (
          <button
            className="h-5 w-5 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            onClick={onOpenPopout}
            title="Open full table"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
