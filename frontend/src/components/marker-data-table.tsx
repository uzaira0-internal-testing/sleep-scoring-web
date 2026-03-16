import { useRef, useEffect, useCallback, useMemo } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { useSleepScoringStore, useMarkers, useDates } from "@/store";
import { fetchWithAuth, getApiBase } from "@/api/client";
import { hexToRgba } from "@/lib/color-themes";
import { Maximize2, Home } from "lucide-react";
import type { OnsetOffsetDataPoint, OnsetOffsetTableResponse, OnsetOffsetColumnar, OnsetOffsetColumnarResponse } from "@/api/types";
import { ApiError } from "@/utils/api-errors";
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
  const algoResults = algoKey ? new Uint8Array(day.algorithmResults[algoKey]!) : null;
  const nwResults = day.nonwearResults ? new Uint8Array(day.nonwearResults) : null;

  const buildWindow = (centerTs: number | null): OnsetOffsetDataPoint[] => {
    if (centerTs == null || tsSec.length === 0) return [];
    const halfWindow = windowMinutes * 60 / 2;
    const points: OnsetOffsetDataPoint[] = [];
    for (let i = 0; i < tsSec.length; i++) {
      if (tsSec[i]! >= centerTs - halfWindow && tsSec[i]! <= centerTs + halfWindow) {
        const d = new Date(tsSec[i]! * 1000);
        points.push({
          timestamp: tsSec[i]!,
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

/** Convert row-based onset/offset data to columnar format for unified rendering. */
function toColumnar(points: OnsetOffsetDataPoint[]): OnsetOffsetColumnar {
  return {
    timestamps: points.map((p) => p.timestamp),
    axis_y: points.map((p) => p.axis_y),
    vector_magnitude: points.map((p) => p.vector_magnitude),
    algorithm_result: points.map((p) => p.algorithm_result ?? null),
    choi_result: points.map((p) => p.choi_result ?? null),
    is_nonwear: points.map((p) => p.is_nonwear),
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
  const currentAlgorithm = useSleepScoringStore((state) => state.currentAlgorithm);

  const { data: tableData, isLoading, error: tableError } = useQuery<OnsetOffsetColumnarResponse | null>({
    queryKey: ["marker-table", currentFileId, currentDate, selectedPeriodIndex, type, quantize(onsetTs), quantize(offsetTs), isLocal ? "local" : "server", currentAlgorithm],
    queryFn: async (): Promise<OnsetOffsetColumnarResponse | null> => {
      if (!currentFileId || !currentDate || selectedPeriodIndex === null) return null;

      // Local mode: build table data directly from IndexedDB, convert to columnar
      if (isLocal) {
        const result = await buildLocalTableData(currentFileId, currentDate, onsetTs, offsetTs, 100);
        if (!result) return null;
        return {
          onset_data: toColumnar(result.onset_data ?? []),
          offset_data: toColumnar(result.offset_data ?? []),
          period_index: result.period_index,
        };
      }

      // Server mode: fetch columnar endpoint
      const params = new URLSearchParams({ window_minutes: "100" });
      if (onsetTs !== null) params.set("onset_ts", String(onsetTs));
      if (offsetTs !== null) params.set("offset_ts", String(offsetTs));
      if (currentAlgorithm) params.set("algorithm", currentAlgorithm);
      const url = `${getApiBase()}/markers/${currentFileId}/${currentDate}/table/${selectedPeriodIndex + 1}/columnar?${params}`;
      try {
        return await fetchWithAuth<OnsetOffsetColumnarResponse>(url);
      } catch (err) {
        // 404 is expected when marker hasn't been saved to backend yet
        if (err instanceof ApiError && err.status === 404) {
          return null;
        }
        throw err;
      }
    },
    enabled: (isLocal || isAuthenticated) && !!currentFileId && !!currentDate && selectedPeriodIndex !== null && onsetTs !== null && offsetTs !== null,
    staleTime: 30000,
    placeholderData: keepPreviousData,
  });

  const colData = type === "onset" ? tableData?.onset_data : tableData?.offset_data;
  const rowCount = colData?.timestamps?.length ?? 0;

  const markerRowIndex = colData?.timestamps?.findIndex(
    (ts) => targetTimestamp && Math.abs(ts - targetTimestamp) < 60
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

  const handleRowClick = useCallback((timestamp: number) => {
    if (selectedPeriodIndex === null) return;
    if (isSleepMode) {
      if (type === "onset") updateMarker("sleep", selectedPeriodIndex, { onsetTimestamp: timestamp });
      else updateMarker("sleep", selectedPeriodIndex, { offsetTimestamp: timestamp });
    } else {
      if (type === "onset") updateMarker("nonwear", selectedPeriodIndex, { startTimestamp: timestamp });
      else updateMarker("nonwear", selectedPeriodIndex, { endTimestamp: timestamp });
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

  if (tableError) {
    return (
      <div className="h-full flex flex-col">
        <TableHeader title={title} onOpenPopout={onOpenPopout} onScrollToMarker={scrollToMarker} />
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-xs text-destructive">Failed to load table data</p>
        </div>
      </div>
    );
  }

  if (!colData || rowCount === 0) {
    return (
      <div className="h-full flex flex-col">
        <TableHeader title={title} onOpenPopout={onOpenPopout} onScrollToMarker={scrollToMarker} />
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-xs text-muted-foreground">No data available</p>
        </div>
      </div>
    );
  }

  const markerRowStyle = useMemo(() => {
    const color = isSleepMode ? colorTheme.sleepOverlay : colorTheme.nonwear;
    return {
      backgroundColor: hexToRgba(color, 0.25),
      borderLeft: `3px solid ${color}`,
      boxShadow: `inset 0 0 0 1px ${hexToRgba(color, 0.3)}`,
    } as const;
  }, [isSleepMode, colorTheme.sleepOverlay, colorTheme.nonwear]);

  return (
    <div className="h-full flex flex-col">
      <TableHeader title={title} onOpenPopout={onOpenPopout} onScrollToMarker={scrollToMarker} />
      <div ref={tableRef} className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-background border-b z-10">
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
            {colData.timestamps.map((ts, idx) => {
              const isMarkerRow = idx === markerRowIndex;
              const algoResult = colData.algorithm_result[idx];
              const choiResult = colData.choi_result[idx];
              const nonwear = colData.is_nonwear[idx];
              const sleepWake = algoResult === 1 ? "S" : algoResult === 0 ? "W" : "-";
              const choiLabel = choiResult === 1 ? "N" : "-";
              const nwLabel = nonwear ? "N" : "-";
              const d = new Date(ts * 1000);
              const timeStr = `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;

              return (
                <tr
                  key={idx}
                  ref={isMarkerRow ? markerRowRef : undefined}
                  onClick={() => handleRowClick(ts)}
                  className={`border-b border-border/20 cursor-pointer transition-colors ${
                    isMarkerRow
                      ? "font-bold"
                      : "hover:bg-muted/40"
                  }`}
                  style={isMarkerRow ? markerRowStyle : undefined}
                >
                  <td className="px-2 py-1 font-mono">{timeStr}</td>
                  <td className="px-1.5 py-1 text-right font-mono">{colData.axis_y[idx]}</td>
                  <td className="px-1.5 py-1 text-right font-mono text-muted-foreground">{colData.vector_magnitude[idx]}</td>
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
        {rowCount} rows
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
