import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { useQuery } from "@tanstack/react-query";
import { useActivityData, useMarkers, useSleepScoringStore, useDates } from "@/store";
import { useTheme } from "@/components/theme-provider";
import { useDataSource } from "@/contexts/data-source-context";
import { getApiBase } from "@/api/client";
import type { ConsensusBallotResponse, MarkersWithMetricsResponse } from "@/api/types";
import { detectSleepOnsetOffset } from "@/utils/sleep-rules";
import { getDetectionRuleParams } from "@/constants/options";
import { hexToRgba, markerColorPair, overlayBorderColor } from "@/lib/color-themes";

/** Epoch duration for timestamp snapping (60 seconds) */
const EPOCH_DURATION_SEC = 60;

/** Snap timestamp to nearest epoch boundary (in seconds) */
function snapToEpoch(timestampSec: number): number {
  return Math.round(timestampSec / EPOCH_DURATION_SEC) * EPOCH_DURATION_SEC;
}

/**
 * Activity data plot using uPlot - renders markers directly into .u-over
 */
interface ActivityPlotProps {
  showComparisonMarkers?: boolean;
  highlightedCandidateId?: number | null;
}

export function ActivityPlot({ showComparisonMarkers = false, highlightedCandidateId = null }: ActivityPlotProps) {
  const { dataSource } = useDataSource();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<uPlot | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const originalXScaleRef = useRef<{ min: number; max: number } | null>(null);
  const isDraggingRef = useRef(false); // Track if currently dragging to prevent re-render
  const renderMarkersRef = useRef<(chart: uPlot) => void>(() => {});
  const wheelZoomPluginRef = useRef<(factor: number) => uPlot.Plugin>(
    (factor: number) => {
      void factor;
      return { hooks: {} };
    }
  );
  const { resolvedTheme } = useTheme();

  const { timestamps, axisX, axisY, axisZ, vectorMagnitude, algorithmResults, nonwearResults, sensorNonwearPeriods, preferredDisplayColumn, viewStart, viewEnd } = useActivityData();
  const viewModeHours = useSleepScoringStore((state) => state.viewModeHours);
  const currentFileId = useSleepScoringStore((state) => state.currentFileId);
  const sitePassword = useSleepScoringStore((state) => state.sitePassword);
  const username = useSleepScoringStore((state) => state.username);
  const showAdjacentMarkers = useSleepScoringStore((state) => state.showAdjacentMarkers);
  const showNonwearOverlays = useSleepScoringStore((state) => state.showNonwearOverlays);
  const sleepDetectionRule = useSleepScoringStore((state) => state.sleepDetectionRule);
  const colorTheme = useSleepScoringStore((state) => state.colorTheme);
  const { currentDate } = useDates();

  // Fetch markers with metrics for sleep rule arrows
  const { data: markersData } = useQuery({
    queryKey: ["markers", currentFileId, currentDate, username || "anonymous"],
    queryFn: async () => {
      if (!currentFileId || !currentDate) return null;
      const response = await fetch(
        `${getApiBase()}/markers/${currentFileId}/${currentDate}`,
        {
          headers: {
            ...(sitePassword ? { "X-Site-Password": sitePassword } : {}),
            "X-Username": username || "anonymous",
          },
        }
      );
      if (!response.ok) throw new Error(`Failed to fetch markers: ${response.status}`);
      return response.json() as Promise<MarkersWithMetricsResponse>;
    },
    enabled: !!currentFileId && !!currentDate,
  });

  // Fetch adjacent day markers for continuity display (via DataSource for local/server parity)
  const { data: adjacentMarkersData } = useQuery({
    queryKey: ["adjacent-markers", currentFileId, currentDate, username || "anonymous"],
    queryFn: () => dataSource.loadAdjacentMarkers(currentFileId!, currentDate!, username || "anonymous"),
    enabled: !!currentFileId && !!currentDate,
    staleTime: 30_000,
  });

  // Fetch consensus ballot candidates for overlay comparison.
  const { data: ballotData } = useQuery({
    queryKey: ["consensus-ballot", currentFileId, currentDate, username || "anonymous"],
    queryFn: async () => {
      if (!currentFileId || !currentDate) return null;
      const response = await fetch(
        `${getApiBase()}/consensus/${currentFileId}/${currentDate}/ballot`,
        {
          headers: {
            ...(sitePassword ? { "X-Site-Password": sitePassword } : {}),
            "X-Username": username || "anonymous",
          },
        }
      );
      if (!response.ok) return null;
      return response.json() as Promise<ConsensusBallotResponse>;
    },
    enabled: showComparisonMarkers && !!currentFileId && !!currentDate,
    staleTime: 0,
    refetchInterval: 10_000,
  });
  const {
    sleepMarkers,
    nonwearMarkers,
    markerMode,
    selectedPeriodIndex,
    creationMode,
    pendingOnsetTimestamp,
  } = useMarkers();

  // Helper to read current marker state inside uPlot plugin callbacks.
  // Uses getState() instead of effect-synced refs to avoid stale values
  // when callbacks fire before the sync effect has run (same class of bug
  // that caused consensus-toggle to wipe markers via useMarkerAutoSave).
  const getMarkerState = useCallback(() => {
    const s = useSleepScoringStore.getState();
    return {
      handlePlotClick: s.handlePlotClick,
      sleepMarkers: s.sleepMarkers,
      nonwearMarkers: s.nonwearMarkers,
      markerMode: s.markerMode,
      selectedPeriodIndex: s.selectedPeriodIndex,
      creationMode: s.creationMode,
      pendingOnsetTimestamp: s.pendingOnsetTimestamp,
      setSelectedPeriod: s.setSelectedPeriod,
      updateMarker: s.updateMarker,
      cancelMarkerCreation: s.cancelMarkerCreation,
    };
  }, []);

  const [containerReady, setContainerReady] = useState(false);
  const [isZoomed, setIsZoomed] = useState(false);
  const isDark = resolvedTheme === "dark";

  const comparisonCandidates = useMemo(() => {
    const candidates = ballotData?.candidates ?? [];
    return candidates.filter((c) => {
      if (c.is_no_sleep) return false;
      const markers = c.sleep_markers_json ?? [];
      return markers.length > 0;
    });
  }, [ballotData]);

  const comparisonColorMap = useMemo(() => {
    const palette = [
      "#38bdf8", // sky
      "#f97316", // orange
      "#a78bfa", // violet
      "#f43f5e", // rose
      "#22c55e", // green
      "#eab308", // amber
      "#14b8a6", // teal
      "#f59e0b", // yellow
    ];

    const map = new Map<string, string>();
    let i = 0;
    for (const c of comparisonCandidates) {
      if (map.has(String(c.candidate_id))) continue;
      if (c.source_type === "auto") {
        map.set(String(c.candidate_id), isDark ? "#34d399" : "#059669");
      } else {
        map.set(String(c.candidate_id), palette[i % palette.length]!);
        i += 1;
      }
    }
    return map;
  }, [comparisonCandidates, isDark]);

  // ============================================================================
  // CONVERT MASK TO CONTIGUOUS REGIONS
  // ============================================================================
  function maskToRegions(mask: number[], timestamps: number[]): Array<{ startIdx: number; endIdx: number; startTs: number; endTs: number }> {
    const regions: Array<{ startIdx: number; endIdx: number; startTs: number; endTs: number }> = [];
    let regionStart: number | null = null;

    for (let i = 0; i < mask.length; i++) {
      if (mask[i] === 1 && regionStart === null) {
        // Start of a new region
        regionStart = i;
      } else if (mask[i] === 0 && regionStart !== null) {
        // End of current region
        regions.push({
          startIdx: regionStart,
          endIdx: i - 1,
          startTs: timestamps[regionStart]!,
          endTs: timestamps[i - 1]!,
        });
        regionStart = null;
      }
    }

    // Handle region that extends to end of data
    if (regionStart !== null) {
      regions.push({
        startIdx: regionStart,
        endIdx: mask.length - 1,
        startTs: timestamps[regionStart]!,
        endTs: timestamps[mask.length - 1]!,
      });
    }

    return regions;
  }

  // ============================================================================
  // RENDER MARKERS - Append to wrapper with devicePixelRatio handling for zoom
  // ============================================================================
  // eslint-disable-next-line react-hooks/exhaustive-deps
  function renderMarkers(u: uPlot) {
    if (!u || !u.over) return;

    const over = u.over as HTMLElement;

    const wrapper = over.parentNode as HTMLElement;
    if (!wrapper) return;

    // Clear existing markers from wrapper (including Choi nonwear regions and sleep rule arrows)
    wrapper.querySelectorAll('.marker-region, .marker-line').forEach(el => el.remove());

    // Get plot dimensions accounting for browser zoom (devicePixelRatio)
    const plotLeft = u.bbox.left / devicePixelRatio;
    const plotTop = u.bbox.top / devicePixelRatio;
    const plotWidth = u.bbox.width / devicePixelRatio;
    const plotHeight = u.bbox.height / devicePixelRatio;
    const { sleepMarkers: markers, nonwearMarkers: nwMarkers, markerMode: mode, selectedPeriodIndex: selIdx, creationMode: cMode, pendingOnsetTimestamp: pendingTs } = getMarkerState();
    const { colorTheme } = useSleepScoringStore.getState();

    // === Desktop app color scheme (from UIColors in core/constants/ui.py) ===
    const pendingLineColor = "#808080";  // UIColors.INCOMPLETE_MARKER

    // Sensor nonwear overlay: gold (from UIColors.NONWEAR_SENSOR_BRUSH)
    const sensorNwFill = hexToRgba(colorTheme.sensorNonwear, 0.24);
    const sensorNwBorder = overlayBorderColor(colorTheme.sensorNonwear, 0.47);

    // Choi algorithm nonwear overlay: purple (from UIColors.CHOI_ALGORITHM_BRUSH)
    const choiFill = hexToRgba(colorTheme.choiNonwear, 0.24);
    const choiBorder = overlayBorderColor(colorTheme.choiNonwear, 0.47);

    // Process sleep markers — blue/orange onset/offset lines
    markers.forEach((marker, index) => {
      if (marker.onsetTimestamp === null || marker.offsetTimestamp === null) return;

      const startTs = marker.onsetTimestamp;
      const endTs = marker.offsetTimestamp;

      const startPx = u.valToPos(startTs, 'x');
      const endPx = u.valToPos(endTs, 'x');

      if (endPx < 0 || startPx > plotWidth) return;


      const isSelected = mode === "sleep" && selIdx === index;

      // Onset line (blue) and offset line (orange) — desktop colors
      const { selected: onsetSel, unselected: onsetUnsel } = markerColorPair(colorTheme.onset);
      const { selected: offsetSel, unselected: offsetUnsel } = markerColorPair(colorTheme.offset);
      const onsetColor = isSelected ? onsetSel : onsetUnsel;
      const offsetColor = isSelected ? offsetSel : offsetUnsel;
      if (startPx >= -10 && startPx <= plotWidth + 10) {
        createMarkerLine(u, wrapper, 'sleep', index, 'start', startPx, plotLeft, plotTop, plotWidth, plotHeight, onsetColor, isSelected, startTs);
      }
      if (endPx >= -10 && endPx <= plotWidth + 10) {
        createMarkerLine(u, wrapper, 'sleep', index, 'end', endPx, plotLeft, plotTop, plotWidth, plotHeight, offsetColor, isSelected, endTs);
      }
    });

    // Process manual nonwear markers — red lines (always visible, user-placed)
    nwMarkers.forEach((marker, index) => {
      if (marker.startTimestamp === null || marker.endTimestamp === null) return;

      const startTs = marker.startTimestamp;
      const endTs = marker.endTimestamp;

      const startPx = u.valToPos(startTs, 'x');
      const endPx = u.valToPos(endTs, 'x');

      if (endPx < 0 || startPx > plotWidth) return;


      const isSelected = mode === "nonwear" && selIdx === index;

      // Start line (crimson red) and end line (firebrick red) — desktop colors
      const { selected: nwStartSel, unselected: nwStartUnsel } = markerColorPair(colorTheme.nonwear);
      const startColor = isSelected ? nwStartSel : nwStartUnsel;
      // End line is slightly different shade — darken further
      const { unselected: nwEndUnsel } = markerColorPair(
        markerColorPair(colorTheme.nonwear).unselected
      );
      const endColor = isSelected ? nwStartUnsel : nwEndUnsel;
      if (startPx >= -10 && startPx <= plotWidth + 10) {
        createMarkerLine(u, wrapper, 'nonwear', index, 'start', startPx, plotLeft, plotTop, plotWidth, plotHeight, startColor, isSelected, startTs);
      }
      if (endPx >= -10 && endPx <= plotWidth + 10) {
        createMarkerLine(u, wrapper, 'nonwear', index, 'end', endPx, plotLeft, plotTop, plotWidth, plotHeight, endColor, isSelected, endTs);
      }
    });

    // Render sensor nonwear overlays (uploaded CSV, read-only, gold)
    if (showNonwearOverlays && sensorNonwearPeriods.length > 0) {
      sensorNonwearPeriods.forEach((period, index) => {
        const startPx = u.valToPos(period.startTimestamp, 'x');
        const endPx = u.valToPos(period.endTimestamp, 'x');

        if (endPx < 0 || startPx > plotWidth) return;

        const visibleStartPx = Math.max(0, startPx);
        const visibleEndPx = Math.min(plotWidth, endPx);

        const sensorRegion = document.createElement('div');
        sensorRegion.className = 'marker-region sensor-nonwear';
        sensorRegion.dataset.sensorIndex = String(index);
        sensorRegion.dataset.testid = `marker-region-sensor-${index}`;
        sensorRegion.style.position = 'absolute';
        sensorRegion.style.left = (plotLeft + visibleStartPx) + 'px';
        sensorRegion.style.top = plotTop + 'px';
        sensorRegion.style.width = (visibleEndPx - visibleStartPx) + 'px';
        sensorRegion.style.height = plotHeight + 'px';
        sensorRegion.style.background = sensorNwFill;
        sensorRegion.style.borderLeft = `2px solid ${sensorNwBorder}`;
        sensorRegion.style.borderRight = `2px solid ${sensorNwBorder}`;
        sensorRegion.style.pointerEvents = 'none';
        sensorRegion.style.zIndex = '2';
        wrapper.appendChild(sensorRegion);
      });
    }

    // Render Choi-detected nonwear regions (algorithm-detected, read-only, purple)
    if (showNonwearOverlays && nonwearResults && nonwearResults.length > 0 && timestamps.length > 0) {
      const choiRegions = maskToRegions(nonwearResults, timestamps);

      choiRegions.forEach((region, index) => {
        const startPx = u.valToPos(region.startTs, 'x');
        const endPx = u.valToPos(region.endTs, 'x');

        if (endPx < 0 || startPx > plotWidth) return;

        const visibleStartPx = Math.max(0, startPx);
        const visibleEndPx = Math.min(plotWidth, endPx);

        const choiRegion = document.createElement('div');
        choiRegion.className = 'marker-region choi-nonwear';
        choiRegion.dataset.choiIndex = String(index);
        choiRegion.dataset.testid = `marker-region-choi-${index}`;
        choiRegion.style.position = 'absolute';
        choiRegion.style.left = (plotLeft + visibleStartPx) + 'px';
        choiRegion.style.top = plotTop + 'px';
        choiRegion.style.width = (visibleEndPx - visibleStartPx) + 'px';
        choiRegion.style.height = plotHeight + 'px';
        choiRegion.style.background = choiFill;
        choiRegion.style.borderLeft = `2px solid ${choiBorder}`;
        choiRegion.style.borderRight = `2px solid ${choiBorder}`;
        choiRegion.style.pointerEvents = 'none';
        choiRegion.style.zIndex = '2';
        wrapper.appendChild(choiRegion);
      });
    }

    // Render pending marker line (grayed out line showing first click position)
    if (cMode === "placing_onset" && pendingTs !== null) {
      const pendingPx = u.valToPos(pendingTs, 'x');

      if (pendingPx >= -10 && pendingPx <= plotWidth + 10) {
        const pendingLine = document.createElement('div');
        pendingLine.className = 'marker-line pending';
        pendingLine.dataset.testid = 'marker-line-pending';
        pendingLine.style.position = 'absolute';
        pendingLine.style.left = (plotLeft + pendingPx - 2) + 'px';
        pendingLine.style.top = plotTop + 'px';
        pendingLine.style.width = '4px';
        pendingLine.style.height = plotHeight + 'px';
        pendingLine.style.background = pendingLineColor;
        pendingLine.style.opacity = '0.7';
        pendingLine.style.pointerEvents = 'none';
        pendingLine.style.borderStyle = 'dashed';
        wrapper.appendChild(pendingLine);
      }
    }

    // Render sleep rule arrows ONLY when a sleep marker is selected (matches desktop behavior)
    // Uses detectSleepOnsetOffset() which ports desktop's ConsecutiveEpochsSleepPeriodDetector
    if (mode === "sleep" && selIdx !== null && selIdx >= 0 && selIdx < markers.length && algorithmResults && algorithmResults.length > 0) {
      const selectedMarker = markers[selIdx];

      if (selectedMarker && selectedMarker.onsetTimestamp !== null && selectedMarker.offsetTimestamp !== null) {
        const ruleParams = getDetectionRuleParams(sleepDetectionRule);
        const { onsetIndex, offsetIndex } = detectSleepOnsetOffset(
          algorithmResults,
          timestamps,
          selectedMarker.onsetTimestamp,
          selectedMarker.offsetTimestamp,
          ruleParams.onsetN,
          ruleParams.offsetN,
          ruleParams.offsetState,
        );

        const arrowY = plotTop + plotHeight * 0.12;
        const offsetRuleText = ruleParams.offsetState === "wake"
          ? `${ruleParams.offsetN} consecutive wake epochs`
          : `${ruleParams.offsetN} consecutive sleep epochs`;

        if (onsetIndex !== null) {
          const onsetTs = timestamps[onsetIndex]!;
          const onsetPx = u.valToPos(onsetTs, 'x');
          if (onsetPx >= 0 && onsetPx <= plotWidth) {
            const timeStr = new Date(onsetTs * 1000).toLocaleTimeString('en-US', {
              hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC',
            });
            createSleepRuleArrow(wrapper, plotLeft, onsetPx, arrowY, colorTheme.onset, 'onset', selIdx,
              timeStr, 'Sleep Onset', `${ruleParams.onsetN} consecutive sleep epochs`);
          }
        }

        if (offsetIndex !== null) {
          const offsetTs = timestamps[offsetIndex]!;
          const offsetPx = u.valToPos(offsetTs, 'x');
          if (offsetPx >= 0 && offsetPx <= plotWidth) {
            const timeStr = new Date(offsetTs * 1000).toLocaleTimeString('en-US', {
              hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC',
            });
            createSleepRuleArrow(wrapper, plotLeft, offsetPx, arrowY, colorTheme.offset, 'offset', selIdx,
              timeStr, 'Sleep Offset', offsetRuleText);
          }
        }
      }
    }

    /** Create a sleep rule arrow with shaft, head, and label - matching desktop ArrowItem style */
    function createSleepRuleArrow(
      parent: HTMLElement, pLeft: number, px: number, y: number,
      color: string, type: string, idx: number,
      timeStr: string, titleText: string, ruleText: string
    ) {
      // Arrow dimensions matching desktop: headLen=15, headWidth=12, tailLen=25, tailWidth=3
      const ARROW_HEAD_LEN = 15;
      const ARROW_HEAD_WIDTH = 12;
      const ARROW_TAIL_LEN = 25;
      const ARROW_TAIL_WIDTH = 3;
      const ARROW_TOTAL_HEIGHT = ARROW_HEAD_LEN + ARROW_TAIL_LEN; // 40px

      // Arrow container - positions the arrow pointing downward
      const arrowContainer = document.createElement('div');
      arrowContainer.className = `marker-region sleep-rule-arrow ${type}`;
      arrowContainer.dataset.testid = `sleep-rule-arrow-${type}-${idx}`;
      arrowContainer.style.position = 'absolute';
      arrowContainer.style.left = (pLeft + px - ARROW_HEAD_WIDTH / 2) + 'px';
      arrowContainer.style.top = y + 'px';
      arrowContainer.style.width = ARROW_HEAD_WIDTH + 'px';
      arrowContainer.style.height = ARROW_TOTAL_HEIGHT + 'px';
      arrowContainer.style.pointerEvents = 'none';
      arrowContainer.title = `Algorithm-detected sleep ${type}`;

      // Tail (shaft) - thin rectangle at top, centered
      const tail = document.createElement('div');
      tail.style.position = 'absolute';
      tail.style.left = ((ARROW_HEAD_WIDTH - ARROW_TAIL_WIDTH) / 2) + 'px';
      tail.style.top = '0';
      tail.style.width = ARROW_TAIL_WIDTH + 'px';
      tail.style.height = ARROW_TAIL_LEN + 'px';
      tail.style.backgroundColor = color;
      arrowContainer.appendChild(tail);

      // Head (triangle pointing down) - CSS border trick
      const head = document.createElement('div');
      head.style.position = 'absolute';
      head.style.left = '0';
      head.style.top = ARROW_TAIL_LEN + 'px';
      head.style.width = '0';
      head.style.height = '0';
      head.style.borderLeft = (ARROW_HEAD_WIDTH / 2) + 'px solid transparent';
      head.style.borderRight = (ARROW_HEAD_WIDTH / 2) + 'px solid transparent';
      head.style.borderTop = ARROW_HEAD_LEN + 'px solid ' + color;
      arrowContainer.appendChild(head);

      parent.appendChild(arrowContainer);

      const label = document.createElement('div');
      label.className = `marker-region sleep-rule-label ${type}`;
      label.style.position = 'absolute';
      label.style.left = (pLeft + px) + 'px';
      label.style.top = (y - 32) + 'px';
      label.style.transform = 'translateX(-50%)';
      label.style.fontFamily = 'Arial, sans-serif';
      label.style.color = color;
      label.style.pointerEvents = 'none';
      label.style.textAlign = 'center';
      label.style.whiteSpace = 'nowrap';
      label.style.lineHeight = '1.3';

      // Title line: "Sleep Onset at HH:MM" (bold, 10px)
      const titleLine = document.createElement('div');
      titleLine.style.fontSize = '10px';
      titleLine.style.fontWeight = 'bold';
      titleLine.textContent = `${titleText} at ${timeStr}`;
      label.appendChild(titleLine);

      // Rule line: "3-minute rule applied" (normal, 9px)
      const ruleLine = document.createElement('div');
      ruleLine.style.fontSize = '9px';
      ruleLine.style.fontWeight = 'normal';
      ruleLine.textContent = ruleText;
      label.appendChild(ruleLine);

      parent.appendChild(label);
    }

    // Render adjacent day markers (from previous and next days) as dashed lines
    // These show markers from neighboring days for continuity
    const adjacentMarkers = adjacentMarkersData;
    const adjacentLineColor = isDark ? 'rgba(100, 100, 100, 0.6)' : 'rgba(50, 50, 50, 0.4)';

    // Previous day markers (gated by showAdjacentMarkers toggle)
    if (showAdjacentMarkers && adjacentMarkers?.previous_day_markers) {
      adjacentMarkers.previous_day_markers.forEach((marker, index) => {
        if (marker.onset_timestamp) {
          const px = u.valToPos(marker.onset_timestamp, 'x');
          if (px >= -10 && px <= plotWidth + 10) {
            createAdjacentDayLine(wrapper, 'prev', index, 'onset', px, plotLeft, plotTop, plotWidth, plotHeight, adjacentLineColor);
          }
        }
        if (marker.offset_timestamp) {
          const px = u.valToPos(marker.offset_timestamp, 'x');
          if (px >= -10 && px <= plotWidth + 10) {
            createAdjacentDayLine(wrapper, 'prev', index, 'offset', px, plotLeft, plotTop, plotWidth, plotHeight, adjacentLineColor);
          }
        }
      });
    }

    // Next day markers (gated by showAdjacentMarkers toggle)
    if (showAdjacentMarkers && adjacentMarkers?.next_day_markers) {
      adjacentMarkers.next_day_markers.forEach((marker, index) => {
        if (marker.onset_timestamp) {
          const px = u.valToPos(marker.onset_timestamp, 'x');
          if (px >= -10 && px <= plotWidth + 10) {
            createAdjacentDayLine(wrapper, 'next', index, 'onset', px, plotLeft, plotTop, plotWidth, plotHeight, adjacentLineColor);
          }
        }
        if (marker.offset_timestamp) {
          const px = u.valToPos(marker.offset_timestamp, 'x');
          if (px >= -10 && px <= plotWidth + 10) {
            createAdjacentDayLine(wrapper, 'next', index, 'offset', px, plotLeft, plotTop, plotWidth, plotHeight, adjacentLineColor);
          }
        }
      });
    }

    // Render comparison overlays from consensus ballot candidates.
    if (showComparisonMarkers && comparisonCandidates.length > 0) {
      comparisonCandidates.forEach((candidate, annIndex) => {
        const candidateKey = String(candidate.candidate_id);
        const color = comparisonColorMap.get(candidateKey) ?? (isDark ? "#94a3b8" : "#64748b");
        const isHighlighted = highlightedCandidateId !== null && candidate.candidate_id === highlightedCandidateId;
        const fill = color + "22"; // subtle translucent fill
        let labeled = false;

        (candidate.sleep_markers_json ?? []).forEach((marker, markerIndex) => {
          if (marker.onset_timestamp == null || marker.offset_timestamp == null) return;

          const startPx = u.valToPos(marker.onset_timestamp, 'x');
          const endPx = u.valToPos(marker.offset_timestamp, 'x');

          if (endPx < 0 || startPx > plotWidth) return;

          const visibleStartPx = Math.max(0, startPx);
          const visibleEndPx = Math.min(plotWidth, endPx);
          const widthPx = visibleEndPx - visibleStartPx;
          if (widthPx <= 0) return;

          const region = document.createElement("div");
          region.className = "marker-region comparison-overlay";
          region.dataset.testid = `comparison-region-${candidate.candidate_id}-${annIndex}-${markerIndex}`;
          region.style.position = "absolute";
          region.style.left = (plotLeft + visibleStartPx) + "px";
          region.style.top = (plotTop + 2) + "px";
          region.style.width = widthPx + "px";
          region.style.height = Math.max(0, plotHeight - 4) + "px";
          region.style.background = fill;
          region.style.border = `${isHighlighted ? 2 : 1}px dashed ${color}`;
          region.style.pointerEvents = "none";
          region.style.zIndex = isHighlighted ? "6" : "3";
          region.title = `${candidate.label}: ${marker.marker_type ?? "MAIN_SLEEP"}`;
          wrapper.appendChild(region);

          if (!labeled) {
            const label = document.createElement("div");
            label.className = "marker-region comparison-label";
            label.style.position = "absolute";
            label.style.left = (plotLeft + visibleStartPx + 4) + "px";
            label.style.top = (plotTop + 4 + annIndex * 14) + "px";
            label.style.fontSize = "10px";
            label.style.fontFamily = "ui-monospace, monospace";
            label.style.color = color;
            label.style.background = isDark ? "rgba(15, 23, 42, 0.75)" : "rgba(255, 255, 255, 0.75)";
            label.style.padding = "1px 4px";
            label.style.borderRadius = "4px";
            label.style.border = `1px solid ${color}55`;
            label.style.pointerEvents = "none";
            label.style.zIndex = "4";
            label.textContent = `${candidate.label} (${candidate.vote_count} votes)${candidate.source_type === "auto" ? " | auto" : ""}`;
            wrapper.appendChild(label);
            labeled = true;
          }
        });
      });
    }
  }

  // ============================================================================
  // CREATE ADJACENT DAY LINE - Dashed line for markers from neighboring days
  // ============================================================================
  function createAdjacentDayLine(
    wrapper: HTMLElement,
    day: 'prev' | 'next',
    index: number,
    edge: 'onset' | 'offset',
    px: number,
    plotLeft: number,
    plotTop: number,
    _plotWidth: number,
    plotHeight: number,
    color: string
  ) {
    const line = document.createElement('div');
    line.className = `marker-region adjacent-day-line ${day}-${edge}`;
    line.dataset.testid = `adjacent-line-${day}-${index}-${edge}`;
    line.style.position = 'absolute';
    line.style.left = (plotLeft + px - 1) + 'px';
    line.style.top = plotTop + 'px';
    line.style.width = '2px';
    line.style.height = plotHeight + 'px';
    line.style.background = `repeating-linear-gradient(
      to bottom,
      ${color},
      ${color} 4px,
      transparent 4px,
      transparent 8px
    )`; // Dashed pattern
    line.style.opacity = '0.4';
    line.style.pointerEvents = 'none';
    line.title = `${day === 'prev' ? 'Previous' : 'Next'} day ${edge}`;
    wrapper.appendChild(line);
  }

  // ============================================================================
  // CREATE MARKER LINE - Append to wrapper with devicePixelRatio positioning
  // ============================================================================
  function createMarkerLine(
    u: uPlot,
    wrapper: HTMLElement,
    type: 'sleep' | 'nonwear',
    index: number,
    edge: 'start' | 'end',
    px: number,
    plotLeft: number,
    plotTop: number,
    plotWidth: number,
    plotHeight: number,
    color: string,
    isSelected: boolean,
    timestampSec?: number
  ) {
    const line = document.createElement('div');
    line.className = `marker-line ${type}-${edge}`;
    line.dataset.testid = `marker-line-${type}-${index}-${edge}`;
    line.style.position = 'absolute';
    line.style.left = (plotLeft + px - 6) + 'px';
    line.style.top = plotTop + 'px';
    line.style.width = '12px';
    line.style.height = plotHeight + 'px';
    line.style.cursor = 'ew-resize';
    line.style.zIndex = '10';
    line.style.pointerEvents = 'auto';

    // Time label above the line
    if (timestampSec !== undefined) {
      const timeLabel = document.createElement('div');
      timeLabel.className = `marker-line time-label`;
      timeLabel.dataset.lineType = `${type}-${edge}`;
      timeLabel.dataset.lineIndex = String(index);
      timeLabel.style.position = 'absolute';
      timeLabel.style.left = (plotLeft + px) + 'px';
      timeLabel.style.top = (plotTop - 14) + 'px';
      timeLabel.style.transform = 'translateX(-50%)';
      timeLabel.style.fontSize = '9px';
      timeLabel.style.fontFamily = 'ui-monospace, monospace';
      timeLabel.style.color = color;
      timeLabel.style.pointerEvents = 'none';
      timeLabel.style.whiteSpace = 'nowrap';
      timeLabel.style.zIndex = '11';
      const d = new Date(timestampSec * 1000);
      timeLabel.textContent = `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
      wrapper.appendChild(timeLabel);
    }

    // Inner line visual
    const inner = document.createElement('div');
    inner.style.position = 'absolute';
    inner.style.left = '50%';
    inner.style.top = '0';
    inner.style.bottom = '0';
    inner.style.width = isSelected ? '4px' : '2px';
    inner.style.transform = 'translateX(-50%)';
    inner.style.background = color;
    line.appendChild(inner);

    // Drag state
    let isDragging = false;
    let dragStartX = 0;
    let dragStartLeft = 0;

    line.addEventListener('mousedown', (e) => {
      e.preventDefault();
      e.stopPropagation();
      isDragging = true;
      isDraggingRef.current = true; // Prevent re-renders during drag
      useSleepScoringStore.getState().beginDragTransaction();
      dragStartX = e.clientX;
      dragStartLeft = parseFloat(line.style.left);
      inner.style.width = '4px';
      line.classList.add('dragging');

      const onMouseMove = (e: MouseEvent) => {
        if (!isDragging) return;
        const dx = e.clientX - dragStartX;
        let newLeft = dragStartLeft + dx;
        // Clamp to plot boundaries
        const minLeft = plotLeft - 6;
        const maxLeft = plotLeft + plotWidth - 6;
        newLeft = Math.max(minLeft, Math.min(maxLeft, newLeft));
        line.style.left = newLeft + 'px';

        // Calculate pixel position for region update
        const linePx = newLeft - plotLeft + 6;

        // Calculate and update position in real-time (store won't trigger re-render because isDraggingRef is true)
        const lineRect = line.getBoundingClientRect();
        const rootRect = u.root.getBoundingClientRect();
        const currentPx = (lineRect.left + 6) - rootRect.left - plotLeft;
        const currentTs = u.posToVal(currentPx, 'x');
        if (currentTs !== undefined && currentTs !== null) {
          const snappedSec = snapToEpoch(currentTs);

          // Update time label during drag
          const timeLabel = wrapper.querySelector(`.marker-line.time-label[data-line-type="${type}-${edge}"][data-line-index="${index}"]`) as HTMLElement;
          if (timeLabel) {
            const d = new Date(snappedSec * 1000);
            timeLabel.textContent = `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
            timeLabel.style.left = (plotLeft + linePx) + 'px';
          }

          // Update the shaded region in real-time
          const region = wrapper.querySelector(`.marker-region.${type}[data-marker-id="${index}"]`) as HTMLElement;
          if (region) {
            // Get the other edge's position from current marker state
            const ms = getMarkerState();
            const markers = type === 'sleep' ? ms.sleepMarkers : ms.nonwearMarkers;
            const marker = markers[index];
            if (marker) {
              let startPx: number, endPx: number;
              if (type === 'sleep') {
                const m = marker as { onsetTimestamp: number | null; offsetTimestamp: number | null };
                if (edge === 'start') {
                  startPx = linePx;
                  endPx = m.offsetTimestamp !== null ? u.valToPos(m.offsetTimestamp, 'x') : linePx;
                } else {
                  startPx = m.onsetTimestamp !== null ? u.valToPos(m.onsetTimestamp, 'x') : linePx;
                  endPx = linePx;
                }
              } else {
                const m = marker as { startTimestamp: number | null; endTimestamp: number | null };
                if (edge === 'start') {
                  startPx = linePx;
                  endPx = m.endTimestamp !== null ? u.valToPos(m.endTimestamp, 'x') : linePx;
                } else {
                  startPx = m.startTimestamp !== null ? u.valToPos(m.startTimestamp, 'x') : linePx;
                  endPx = linePx;
                }
              }
              // Ensure proper order (start < end)
              const left = Math.min(startPx, endPx);
              const right = Math.max(startPx, endPx);
              const visibleLeft = Math.max(0, left);
              const visibleRight = Math.min(plotWidth, right);
              region.style.left = (plotLeft + visibleLeft) + 'px';
              region.style.width = Math.max(0, visibleRight - visibleLeft) + 'px';
            }
          }

          // Reposition sleep rule arrows in real-time during drag
          // (renderMarkers is skipped while isDraggingRef is true, so arrows would freeze)
          if (type === 'sleep' && algorithmResults && algorithmResults.length > 0 && timestamps.length > 0) {
            const markers = getMarkerState().sleepMarkers;
            const marker = markers[index];
            if (marker) {
              const currentOnset = edge === 'start' ? snappedSec : marker.onsetTimestamp;
              const currentOffset = edge === 'end' ? snappedSec : marker.offsetTimestamp;

              if (currentOnset !== null && currentOffset !== null) {
                const dragRuleParams = getDetectionRuleParams(sleepDetectionRule);
                const { onsetIndex, offsetIndex } = detectSleepOnsetOffset(
                  algorithmResults,
                  timestamps,
                  currentOnset,
                  currentOffset,
                  dragRuleParams.onsetN,
                  dragRuleParams.offsetN,
                  dragRuleParams.offsetState,
                );

                const arrowY = plotTop + plotHeight * 0.12;
                const ARROW_HW = 12; // matches ARROW_HEAD_WIDTH in createSleepRuleArrow

                // Reposition onset arrow + label
                const onsetArrow = wrapper.querySelector('.sleep-rule-arrow.onset') as HTMLElement | null;
                const onsetLabel = wrapper.querySelector('.sleep-rule-label.onset') as HTMLElement | null;
                if (onsetIndex !== null) {
                  const oTs = timestamps[onsetIndex]!;
                  const oPx = u.valToPos(oTs, 'x');
                  if (onsetArrow) {
                    onsetArrow.style.left = (plotLeft + oPx - ARROW_HW / 2) + 'px';
                    onsetArrow.style.top = arrowY + 'px';
                    onsetArrow.style.display = '';
                  }
                  if (onsetLabel) {
                    onsetLabel.style.left = (plotLeft + oPx) + 'px';
                    onsetLabel.style.top = (arrowY - 32) + 'px';
                    onsetLabel.style.display = '';
                    const titleEl = onsetLabel.firstElementChild as HTMLElement | null;
                    if (titleEl) {
                      const t = new Date(oTs * 1000).toLocaleTimeString('en-US', {
                        hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC',
                      });
                      titleEl.textContent = `Sleep Onset at ${t}`;
                    }
                  }
                } else {
                  if (onsetArrow) onsetArrow.style.display = 'none';
                  if (onsetLabel) onsetLabel.style.display = 'none';
                }

                // Reposition offset arrow + label
                const offsetArrow = wrapper.querySelector('.sleep-rule-arrow.offset') as HTMLElement | null;
                const offsetLabel = wrapper.querySelector('.sleep-rule-label.offset') as HTMLElement | null;
                if (offsetIndex !== null) {
                  const oTs = timestamps[offsetIndex]!;
                  const oPx = u.valToPos(oTs, 'x');
                  if (offsetArrow) {
                    offsetArrow.style.left = (plotLeft + oPx - ARROW_HW / 2) + 'px';
                    offsetArrow.style.top = arrowY + 'px';
                    offsetArrow.style.display = '';
                  }
                  if (offsetLabel) {
                    offsetLabel.style.left = (plotLeft + oPx) + 'px';
                    offsetLabel.style.top = (arrowY - 32) + 'px';
                    offsetLabel.style.display = '';
                    const titleEl = offsetLabel.firstElementChild as HTMLElement | null;
                    if (titleEl) {
                      const t = new Date(oTs * 1000).toLocaleTimeString('en-US', {
                        hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC',
                      });
                      titleEl.textContent = `Sleep Offset at ${t}`;
                    }
                  }
                } else {
                  if (offsetArrow) offsetArrow.style.display = 'none';
                  if (offsetLabel) offsetLabel.style.display = 'none';
                }
              }
            }
          }

          if (type === 'sleep') {
            const updates = edge === 'start'
              ? { onsetTimestamp: snappedSec }
              : { offsetTimestamp: snappedSec };
            getMarkerState().updateMarker(type, index, updates);
          } else {
            const updates = edge === 'start'
              ? { startTimestamp: snappedSec }
              : { endTimestamp: snappedSec };
            getMarkerState().updateMarker(type, index, updates);
          }
        }
      };

      const onMouseUp = () => {
        if (!isDragging) return;
        isDragging = false;
        isDraggingRef.current = false; // Allow re-renders again
        useSleepScoringStore.getState().commitDragTransaction();
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        inner.style.width = isSelected ? '4px' : '2px';

        // Final position update
        const lineRect = line.getBoundingClientRect();
        const rootRect = u.root.getBoundingClientRect();
        const finalPx = (lineRect.left + 6) - rootRect.left - plotLeft;
        const newTs = u.posToVal(finalPx, 'x');
        if (newTs === undefined || newTs === null) return;

        const snappedSec = snapToEpoch(newTs);

        if (type === 'sleep') {
          const updates = edge === 'start'
            ? { onsetTimestamp: snappedSec }
            : { offsetTimestamp: snappedSec };
          getMarkerState().updateMarker(type, index, updates);
        } else {
          const updates = edge === 'start'
            ? { startTimestamp: snappedSec }
            : { endTimestamp: snappedSec };
          getMarkerState().updateMarker(type, index, updates);
        }

        // Select this period and trigger final re-render
        getMarkerState().setSelectedPeriod(index);
        // Force re-render markers after drag
        if (chartRef.current) {
          renderMarkersRef.current(chartRef.current);
        }
      };

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });

    // Forward wheel events to chart for zoom
    line.addEventListener('wheel', (e) => {
      e.preventDefault();
      e.stopPropagation();
      u.root.dispatchEvent(new WheelEvent('wheel', {
        deltaY: e.deltaY,
        clientX: e.clientX,
        clientY: e.clientY,
        bubbles: true,
      }));
    }, { passive: false });

    wrapper.appendChild(line);
  }

  // ============================================================================
  // WHEEL ZOOM PLUGIN - EXACT COPY FROM benchmark.html
  // ============================================================================
  // eslint-disable-next-line react-hooks/exhaustive-deps
  function wheelZoomPlugin(factor: number) {
    return {
      hooks: {
        ready: (u: uPlot) => {
          const wrapper = u.root;

          // Wheel zoom
          wrapper.addEventListener('wheel', (e: WheelEvent) => {
            e.preventDefault();
            e.stopPropagation();

            const rect = u.over.getBoundingClientRect();
            const left = e.clientX - rect.left;

            if (left < 0 || left > rect.width) return;

            const xVal = u.posToVal(left, 'x');
            const oxRange = (u.scales.x!.max ?? 0) - (u.scales.x!.min ?? 0);

            const nxRange = e.deltaY > 0 ? oxRange / factor : oxRange * factor;
            const minRange = 60;
            const maxRange = originalXScaleRef.current
              ? (originalXScaleRef.current.max - originalXScaleRef.current.min)
              : oxRange * 10;

            if (nxRange < minRange || nxRange > maxRange) return;

            const leftPct = left / (u.bbox.width / devicePixelRatio);
            const nxMin = xVal - leftPct * nxRange;
            const nxMax = nxMin + nxRange;

            u.batch(() => {
              u.setScale('x', { min: nxMin, max: nxMax });
            });
          }, { passive: false });

          // Pan with any mouse button drag (left, middle, or shift+left)
          let isPanning = false;
          let panStartX = 0;
          let panStartY = 0;
          let panStartMin = 0;
          let panStartMax = 0;
          let hasDragged = false;

          u.over.addEventListener('mousedown', (e: MouseEvent) => {
            // Allow panning with left button (0), middle button (1), or shift+left
            if (e.button === 0 || e.button === 1) {
              panStartX = e.clientX;
              panStartY = e.clientY;
              panStartMin = u.scales.x!.min ?? 0;
              panStartMax = u.scales.x!.max ?? 0;
              hasDragged = false;
              // Don't set isPanning yet - wait for actual drag movement
              // This allows click events to still work for marker placement
            }
          });

          // Store references for cleanup in destroy hook
          const onDocMouseMove = (e: MouseEvent) => {
            // Check if we should start panning (moved more than 5px threshold)
            if (!isPanning && panStartX !== 0) {
              const dx = Math.abs(e.clientX - panStartX);
              const dy = Math.abs(e.clientY - panStartY);
              if (dx > 5 || dy > 5) {
                isPanning = true;
                hasDragged = true;
                u.over.style.cursor = 'grabbing';
              }
            }

            if (!isPanning) return;
            const dx = e.clientX - panStartX;
            const pxPerVal = (u.bbox.width / devicePixelRatio) / (panStartMax - panStartMin);
            const dVal = -dx / pxPerVal;

            let nxMin = panStartMin + dVal;
            let nxMax = panStartMax + dVal;

            if (originalXScaleRef.current) {
              if (nxMin < originalXScaleRef.current.min) {
                nxMax += (originalXScaleRef.current.min - nxMin);
                nxMin = originalXScaleRef.current.min;
              }
              if (nxMax > originalXScaleRef.current.max) {
                nxMin -= (nxMax - originalXScaleRef.current.max);
                nxMax = originalXScaleRef.current.max;
              }
            }

            u.batch(() => {
              u.setScale('x', { min: nxMin, max: nxMax });
            });
          };

          const onDocMouseUp = () => {
            isPanning = false;
            panStartX = 0;
            panStartY = 0;
            u.over.style.cursor = 'crosshair';
          };

          document.addEventListener('mousemove', onDocMouseMove);
          document.addEventListener('mouseup', onDocMouseUp);

          // Stash cleanup references on the uPlot instance for the destroy hook
          (u as unknown as Record<string, unknown>)._panCleanup = { onDocMouseMove, onDocMouseUp };

          // Click handler for marker placement - only if not dragging
          u.over.addEventListener('click', (e: MouseEvent) => {
            // Don't place marker if we were panning
            if (hasDragged) {
              hasDragged = false;
              return;
            }

            const rect = u.over.getBoundingClientRect();
            const left = e.clientX - rect.left;

            if (left < 0 || left > rect.width) return;

            const ts = u.posToVal(left, 'x');
            if (ts === undefined || ts === null) return;

            const snappedSec = snapToEpoch(ts);
            getMarkerState().handlePlotClick(snappedSec);
          });

          // Right-click handler to cancel marker placement
          u.over.addEventListener('contextmenu', (e: MouseEvent) => {
            e.preventDefault();
            // Cancel marker creation if in progress
            if (getMarkerState().creationMode !== 'idle') {
              getMarkerState().cancelMarkerCreation();
            }
          });

          // Initial marker render
          renderMarkersRef.current(u);
        },
        setScale: [(u: uPlot, key: string) => {
          if (key === 'x') {
            renderMarkersRef.current(u);
            // Track zoom state by comparing current range to original
            if (originalXScaleRef.current) {
              const orig = originalXScaleRef.current;
              const curMin = u.scales.x!.min ?? orig.min;
              const curMax = u.scales.x!.max ?? orig.max;
              const tolerance = (orig.max - orig.min) * 0.01;
              const zoomed = Math.abs(curMin - orig.min) > tolerance || Math.abs(curMax - orig.max) > tolerance;
              setIsZoomed(zoomed);
            }
          }
        }],
        setSize: [(u: uPlot) => {
          renderMarkersRef.current(u);
        }],
        destroy: [(u: uPlot) => {
          // Clean up document-level listeners to prevent memory leaks on chart rebuild
          const cleanup = (u as unknown as Record<string, unknown>)._panCleanup as { onDocMouseMove: (e: MouseEvent) => void; onDocMouseUp: () => void } | undefined;
          if (cleanup) {
            document.removeEventListener('mousemove', cleanup.onDocMouseMove);
            document.removeEventListener('mouseup', cleanup.onDocMouseUp);
          }
        }],
      },
    };
  }

  // Keep the latest function implementations available to effects without
  // forcing those effects to depend on unstable function identities.
  useEffect(() => {
    renderMarkersRef.current = renderMarkers;
  }, [renderMarkers]);

  useEffect(() => {
    wheelZoomPluginRef.current = wheelZoomPlugin;
  }, [wheelZoomPlugin]);

  // Wait for container to have dimensions
  // Re-run when timestamps change because the containerRef div is conditionally rendered
  const hasData = timestamps.length > 0;
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect.width > 0) {
          setContainerReady(true);
        }
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [hasData]);

  // ============================================================================
  // CREATE CHART - EXACT STRUCTURE FROM benchmark.html
  // ============================================================================
  useEffect(() => {
    if (!containerRef.current || !containerReady) return;
    if (timestamps.length === 0) return;

    const container = containerRef.current;
    // Select display data based on user preference
    const displayData = (() => {
      switch (preferredDisplayColumn) {
        case "axis_x": return axisX;
        case "axis_y": return axisY;
        case "axis_z": return axisZ;
        case "vector_magnitude": return vectorMagnitude;
        default: return axisY;
      }
    })();
    if (displayData.length === 0) return;

    // Destroy existing chart
    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }

    // Remove old marker elements (scoped to this chart container)
    container.querySelectorAll('.marker-line, .marker-region').forEach(el => el.remove());

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 380;

    // Use view range from backend if available, otherwise fall back to data range
    // This ensures the full expected range is shown even if data is missing at edges
    const dataMin = timestamps[0] ?? 0;
    const dataMax = timestamps[timestamps.length - 1] ?? dataMin;
    const initialMin = viewStart ?? dataMin;
    const initialMax = viewEnd ?? dataMax;
    originalXScaleRef.current = { min: initialMin, max: initialMax };

    // uPlot options
    const opts: uPlot.Options = {
      width,
      height,
      plugins: [wheelZoomPluginRef.current(0.75)],
      legend: { show: false }, // Hide legend - we show info in sidebar
      scales: {
        x: {
          time: true,
          min: initialMin as number,
          max: initialMax as number,
        },
        y: { auto: true },
      },
      axes: [
        {
          stroke: isDark ? '#888' : '#666',
          grid: { stroke: isDark ? '#333' : '#ddd', width: 1 },
          ticks: { stroke: isDark ? '#444' : '#999' },
          // Format x-axis times in UTC to match stored data (no timezone conversion)
          values: (_u: uPlot, vals: number[]) => vals.map(v => {
            const d = new Date(v * 1000);
            // Use UTC methods to avoid local timezone conversion
            const hours = String(d.getUTCHours()).padStart(2, '0');
            const mins = String(d.getUTCMinutes()).padStart(2, '0');
            return `${hours}:${mins}`;
          }),
        },
        {
          stroke: isDark ? '#888' : '#666',
          grid: { stroke: isDark ? '#333' : '#ddd', width: 1 },
          ticks: { stroke: isDark ? '#444' : '#999' },
        },
      ],
      series: [
        {},
        {
          stroke: colorTheme.activityLine,
          width: 1,
          fill: hexToRgba(colorTheme.activityLine, 0.1),
        },
      ],
      cursor: {
        drag: { x: false, y: false },
        sync: { key: 'activity' },
        focus: { prox: 30 },
        points: {
          show: true,
          size: 8,
          fill: colorTheme.activityLine,
          stroke: isDark ? '#fff' : '#000',
          width: 2,
        },
      },
      hooks: {
        setCursor: [(u: uPlot) => {
          const tooltip = tooltipRef.current;
          if (!tooltip) return;
          
          const { left, top, idx } = u.cursor;
          
          if (idx === null || idx === undefined || left === undefined || top === undefined || left < 0) {
            tooltip.style.display = 'none';
            return;
          }
          
          const ts = u.data[0]![idx];
          const val = u.data[1]![idx];
          
          if (ts == null || val == null) {
            tooltip.style.display = 'none';
            return;
          }
          
          // Format timestamp in UTC to match stored data (no timezone conversion)
          const date = new Date(ts * 1000);
          const timeStr = date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
            timeZone: 'UTC',
          });
          const dateStr = date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            timeZone: 'UTC',
          });
          
          // Update tooltip content
          tooltip.innerHTML = `
            <div style="font-weight: 600; margin-bottom: 4px;">${dateStr} ${timeStr}</div>
            <div>Value: <span style="font-weight: 600;">${val.toFixed(1)}</span></div>
          `;
          
          // Position tooltip near cursor but keep in bounds
          const plotLeft = u.bbox.left / devicePixelRatio;
          const plotTop = u.bbox.top / devicePixelRatio;
          const plotWidth = u.bbox.width / devicePixelRatio;
          
          let tooltipX = plotLeft + left + 12;
          let tooltipY = plotTop + top - 40;
          
          // Keep tooltip in bounds
          const tooltipWidth = 140;
          if (tooltipX + tooltipWidth > plotLeft + plotWidth) {
            tooltipX = plotLeft + left - tooltipWidth - 12;
          }
          if (tooltipY < plotTop) {
            tooltipY = plotTop + top + 12;
          }
          
          tooltip.style.left = tooltipX + 'px';
          tooltip.style.top = tooltipY + 'px';
          tooltip.style.display = 'block';
        }],
      },
    };

    const chartData: uPlot.AlignedData = [timestamps, displayData];
    chartRef.current = new uPlot(opts, chartData, container);

    // Handle resize with rAF debounce for panel drag performance
    let resizeRaf = 0;
    const resizeObserver = new ResizeObserver((entries) => {
      cancelAnimationFrame(resizeRaf);
      resizeRaf = requestAnimationFrame(() => {
        for (const entry of entries) {
          const { width, height: newHeight } = entry.contentRect;
          if (chartRef.current && width > 0 && newHeight > 0) {
            chartRef.current.setSize({ width, height: newHeight });
          }
        }
      });
    });
    resizeObserver.observe(container);

    return () => {
      cancelAnimationFrame(resizeRaf);
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, [timestamps, axisX, axisY, axisZ, vectorMagnitude, preferredDisplayColumn, viewModeHours, containerReady, isDark, viewStart, viewEnd, colorTheme]);

  // Re-render markers when marker state changes (skip during drag to prevent DOM destruction)
  useEffect(() => {
    if (chartRef.current && !isDraggingRef.current) {
      renderMarkersRef.current(chartRef.current);
    }
  }, [
    sleepMarkers,
    nonwearMarkers,
    nonwearResults,
    sensorNonwearPeriods,
    algorithmResults,
    selectedPeriodIndex,
    markerMode,
    creationMode,
    pendingOnsetTimestamp,
    markersData,
    adjacentMarkersData,
    showAdjacentMarkers,
    showNonwearOverlays,
    sleepDetectionRule,
    showComparisonMarkers,
    comparisonCandidates,
    comparisonColorMap,
    highlightedCandidateId,
  ]);

  if (timestamps.length === 0) {
    return (
      <div className="w-full h-full flex items-center justify-center text-muted-foreground">
        No activity data available
      </div>
    );
  }

  const handleResetZoom = () => {
    if (chartRef.current && originalXScaleRef.current) {
      chartRef.current.setScale('x', {
        min: originalXScaleRef.current.min,
        max: originalXScaleRef.current.max,
      });
      setIsZoomed(false);
    }
  };

  return (
    <div className="w-full h-full relative overflow-hidden">
      <div ref={containerRef} className="w-full h-full" />
      {isZoomed && (
        <button
          onClick={handleResetZoom}
          className="absolute top-2 right-2 z-20 px-2 py-1 text-xs font-medium rounded-md border shadow-sm bg-background/90 hover:bg-muted transition-colors"
          title="Reset zoom to full view"
        >
          Reset Zoom
        </button>
      )}
      <div
        ref={tooltipRef}
        className="absolute pointer-events-none z-50 px-3 py-2 rounded-md shadow-lg text-sm"
        style={{
          display: 'none',
          backgroundColor: isDark ? 'rgba(30, 30, 50, 0.95)' : 'rgba(255, 255, 255, 0.95)',
          color: isDark ? '#e0e0e0' : '#333',
          border: isDark ? '1px solid #444' : '1px solid #ddd',
          minWidth: '120px',
        }}
      />
    </div>
  );
}
