import React, { useState, useCallback } from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { useSleepScoringStore, useMarkers } from "@/store";
import { formatTime, formatDuration } from "@/utils/formatters";
import { resolveEditedTimeToTimestamp } from "@/utils/time-edit";

/**
 * Inline time editing inputs for sleep onset/offset and nonwear start/end.
 * Reads marker state directly from the store to avoid prop drilling.
 */
export const MarkerTimeEditor = React.memo(function MarkerTimeEditor() {
  const [editingOnset, setEditingOnset] = useState<string | null>(null);
  const [editingOffset, setEditingOffset] = useState<string | null>(null);
  const [editingNwStart, setEditingNwStart] = useState<string | null>(null);
  const [editingNwEnd, setEditingNwEnd] = useState<string | null>(null);

  const {
    sleepMarkers,
    nonwearMarkers,
    markerMode,
    selectedPeriodIndex,
    updateMarker,
  } = useMarkers();

  const currentDateIndex = useSleepScoringStore((state) => state.currentDateIndex);
  const availableDates = useSleepScoringStore((state) => state.availableDates);
  const currentDate = availableDates[currentDateIndex] ?? null;

  const commitMarkerTimeEdit = useCallback((
    mode: "sleep" | "nonwear",
    field: "onset" | "offset" | "start" | "end",
    value: string,
  ) => {
    if (markerMode !== mode || selectedPeriodIndex === null) return;
    const markers = mode === "sleep" ? sleepMarkers : nonwearMarkers;
    const marker = markers[selectedPeriodIndex];
    if (!marker) return;

    const tsKeys = mode === "sleep"
      ? { first: "onsetTimestamp" as const, second: "offsetTimestamp" as const }
      : { first: "startTimestamp" as const, second: "endTimestamp" as const };
    const isFirst = field === "onset" || field === "start";
    const refTs = (marker as Record<string, unknown>)[isFirst ? tsKeys.first : tsKeys.second] as number | null;
    if (refTs === null) return;
    const counterpartTs = (marker as Record<string, unknown>)[isFirst ? tsKeys.second : tsKeys.first] as number | null;

    const newTs = resolveEditedTimeToTimestamp({
      timeStr: value,
      currentDate,
      referenceTimestamp: refTs,
      otherBoundaryTimestamp: counterpartTs,
      field: isFirst ? "onset" : "offset",
    });
    if (newTs === null) return;

    updateMarker(mode, selectedPeriodIndex, { [isFirst ? tsKeys.first : tsKeys.second]: newTs });
  }, [markerMode, selectedPeriodIndex, sleepMarkers, nonwearMarkers, currentDate, updateMarker]);

  const commitTimeEdit = useCallback((field: "onset" | "offset", value: string) => {
    commitMarkerTimeEdit("sleep", field, value);
  }, [commitMarkerTimeEdit]);

  const commitNwTimeEdit = useCallback((field: "start" | "end", value: string) => {
    commitMarkerTimeEdit("nonwear", field, value);
  }, [commitMarkerTimeEdit]);

  // Sleep marker time editor
  if (markerMode === "sleep" && selectedPeriodIndex !== null && sleepMarkers[selectedPeriodIndex]) {
    const marker = sleepMarkers[selectedPeriodIndex];
    return (
      <div className="flex items-center gap-2 shrink-0">
        <div className="flex items-center gap-1.5">
          <Label className="text-xs font-semibold">Onset:</Label>
          <Input
            type="text"
            className="w-24 h-7 text-xs text-center"
            value={editingOnset ?? formatTime(marker.onsetTimestamp)}
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
            value={editingOffset ?? formatTime(marker.offsetTimestamp)}
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
        <span className="text-xs font-medium tabular-nums">
          {formatDuration(marker.onsetTimestamp, marker.offsetTimestamp)}
        </span>
      </div>
    );
  }

  // Nonwear marker time editor
  if (markerMode === "nonwear" && selectedPeriodIndex !== null && nonwearMarkers[selectedPeriodIndex]) {
    const marker = nonwearMarkers[selectedPeriodIndex];
    return (
      <div className="flex items-center gap-2 shrink-0">
        <div className="flex items-center gap-1.5">
          <Label className="text-xs font-semibold">Start:</Label>
          <Input
            type="text"
            className="w-24 h-7 text-xs text-center"
            value={editingNwStart ?? formatTime(marker.startTimestamp)}
            onChange={(e) => setEditingNwStart(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                commitNwTimeEdit("start", (e.target as HTMLInputElement).value);
                setEditingNwStart(null);
              } else if (e.key === "Escape") {
                setEditingNwStart(null);
              }
            }}
            onFocus={(e) => setEditingNwStart(e.target.value)}
            onBlur={(e) => {
              commitNwTimeEdit("start", e.target.value);
              setEditingNwStart(null);
            }}
          />
        </div>
        <div className="flex items-center gap-1.5">
          <Label className="text-xs font-semibold">End:</Label>
          <Input
            type="text"
            className="w-24 h-7 text-xs text-center"
            value={editingNwEnd ?? formatTime(marker.endTimestamp)}
            onChange={(e) => setEditingNwEnd(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                commitNwTimeEdit("end", (e.target as HTMLInputElement).value);
                setEditingNwEnd(null);
              } else if (e.key === "Escape") {
                setEditingNwEnd(null);
              }
            }}
            onFocus={(e) => setEditingNwEnd(e.target.value)}
            onBlur={(e) => {
              commitNwTimeEdit("end", e.target.value);
              setEditingNwEnd(null);
            }}
          />
        </div>
        <span className="text-xs font-medium tabular-nums">
          {formatDuration(marker.startTimestamp, marker.endTimestamp)}
        </span>
      </div>
    );
  }

  return null;
});
