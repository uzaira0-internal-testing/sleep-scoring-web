/**
 * Diary Panel Component
 *
 * Read-only table showing all diary entries for the current file.
 * Matches the desktop app: 21 columns with all nap/nonwear details inline.
 * Click onset/offset/nap cells to place markers from diary times.
 * Diary data is imported via the Data Settings page, not from here.
 */

import { useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Book } from "lucide-react";
import { useSleepScoringStore } from "@/store";
import { diaryApi } from "@/api/client";
import type { DiaryEntryResponse } from "@/api/types";
import { useDataSource } from "@/contexts/data-source-context";
import { formatTimeDisplay } from "@/utils/formatters";

// =============================================================================
// AM/PM Correction Detection
// =============================================================================

/** Parse time string to 24h (hour, minute). Supports "9:30 PM", "23:30", etc. */
function parseTo24h(timeStr: string): [number, number] | null {
  const s = timeStr.trim().toUpperCase();
  const isPM = s.includes("PM");
  const isAM = s.includes("AM");
  const clean = s.replace(/[AP]M/g, "").trim();
  const parts = clean.split(":");
  if (parts.length < 2) return null;
  let h = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  if (isNaN(h) || isNaN(m)) return null;
  if (isAM || isPM) {
    if (h === 12) h = isAM ? 0 : 12;
    else if (isPM) h += 12;
  }
  if (h < 0 || h > 23 || m < 0 || m > 59) return null;
  return [h, m];
}

/** Flip AM↔PM in a time string. Returns null for 24h format. */
function flipAmPm(timeStr: string): string | null {
  const s = timeStr.trim();
  const upper = s.toUpperCase();
  if (upper.includes("PM")) {
    const idx = upper.indexOf("PM");
    return s.substring(0, idx) + "AM" + s.substring(idx + 2);
  } else if (upper.includes("AM")) {
    const idx = upper.indexOf("AM");
    return s.substring(0, idx) + "PM" + s.substring(idx + 2);
  }
  return null;
}

/** Convert time string to UTC timestamp for a given analysis date.
 *  isEvening: onset/bed times (h<12 → next day). Otherwise: wake times (h<18 → next day). */
function timeToTs(date: string, timeStr: string, isEvening: boolean): number | null {
  const parsed = parseTo24h(timeStr);
  if (!parsed) return null;
  const [h, m] = parsed;
  const d = new Date(date + "T00:00:00Z");
  if (isEvening && h < 12) d.setUTCDate(d.getUTCDate() + 1);
  else if (!isEvening && h < 18) d.setUTCDate(d.getUTCDate() + 1);
  d.setUTCHours(h, m, 0, 0);
  return d.getTime();
}

/** Check if onset/wake timestamps are physiologically plausible for a noon-to-noon window. */
function timesPlausible(onsetTs: number | null, wakeTs: number | null, date: string): boolean {
  if (onsetTs === null || wakeTs === null) return false;
  if (wakeTs <= onsetTs) return false;
  const gapH = (wakeTs - onsetTs) / 3_600_000;
  if (gapH < 2 || gapH > 18) return false;
  // Data window: noon of date to noon of date+1
  const d = new Date(date + "T12:00:00Z");
  const windowStart = d.getTime() - 2 * 3_600_000; // 2h margin
  const windowEnd = d.getTime() + 26 * 3_600_000;  // noon+24h + 2h margin
  if (onsetTs < windowStart || onsetTs > windowEnd) return false;
  if (wakeTs < windowStart || wakeTs > windowEnd) return false;
  return true;
}

interface AmPmCorrection {
  onset?: string;   // corrected onset value
  wake?: string;    // corrected wake value
  origOnset?: string;
  origWake?: string;
}

/** Detect AM/PM errors for each diary entry. Returns map of entry id → corrections. */
function useAmPmCorrections(entries: DiaryEntryResponse[] | undefined) {
  return useMemo(() => {
    const corrections = new Map<number, AmPmCorrection>();
    if (!entries) return corrections;

    for (const e of entries) {
      const onsetStr = e.lights_out || e.bed_time;
      const wakeStr = e.wake_time;
      if (!onsetStr || !wakeStr) continue;
      const date = String(e.analysis_date);

      let onsetTs = timeToTs(date, onsetStr, true);
      let wakeTs = timeToTs(date, wakeStr, false);
      if (wakeTs !== null && onsetTs !== null && wakeTs <= onsetTs) wakeTs += 86_400_000;

      if (timesPlausible(onsetTs, wakeTs, date)) continue;

      // Try flips: wake only, onset only, both
      const flippedWake = flipAmPm(wakeStr);
      const flippedOnset = flipAmPm(onsetStr);
      type Attempt = { oStr: string | null; wStr: string | null; fixOnset: boolean; fixWake: boolean };
      const attempts: Attempt[] = [];
      if (flippedWake) attempts.push({ oStr: onsetStr, wStr: flippedWake, fixOnset: false, fixWake: true });
      if (flippedOnset) attempts.push({ oStr: flippedOnset, wStr: wakeStr, fixOnset: true, fixWake: false });
      if (flippedOnset && flippedWake) attempts.push({ oStr: flippedOnset, wStr: flippedWake, fixOnset: true, fixWake: true });

      for (const att of attempts) {
        if (!att.oStr || !att.wStr) continue;
        let aOnset = timeToTs(date, att.oStr, true);
        let aWake = timeToTs(date, att.wStr, false);
        if (aWake !== null && aOnset !== null && aWake <= aOnset) aWake += 86_400_000;
        if (timesPlausible(aOnset, aWake, date)) {
          const c: AmPmCorrection = {};
          if (att.fixOnset) { c.onset = att.oStr; c.origOnset = onsetStr; }
          if (att.fixWake) { c.wake = att.wStr; c.origWake = wakeStr; }
          corrections.set(e.id, c);
          break;
        }
      }
    }
    return corrections;
  }, [entries]);
}

interface DiaryPanelProps {
  compact?: boolean;
}

/** Table header cell */
function Th({ children, className = "", compact = false }: { children: React.ReactNode; className?: string; compact?: boolean }) {
  return (
    <th className={`px-2.5 py-1.5 text-center font-medium whitespace-nowrap ${compact ? "text-sm" : "text-sm"} ${className}`}>
      {children}
    </th>
  );
}

/** Table data cell */
function Td({
  children,
  className = "",
  clickable = false,
  onClick,
  title,
  compact = false,
}: {
  children: React.ReactNode;
  className?: string;
  clickable?: boolean;
  onClick?: () => void;
  title?: string | undefined;
  compact?: boolean;
}) {
  return (
    <td
      className={`px-2.5 ${compact ? "py-1" : "py-1.5"} text-center whitespace-nowrap ${compact ? "text-sm" : "text-sm"} ${clickable ? "cursor-pointer hover:bg-primary/20 rounded" : ""} ${className}`}
      onClick={clickable ? onClick : undefined}
      title={title}
    >
      {children}
    </td>
  );
}

/** Determine which optional column groups have data across all entries */
function useVisibleColumns(entries: DiaryEntryResponse[] | undefined) {
  return useMemo(() => {
    if (!entries || entries.length === 0) {
      return { hasNap1: false, hasNap2: false, hasNap3: false, hasNapCount: false, hasNw1: false, hasNw2: false, hasNw3: false, hasNwFlag: false };
    }
    let hasNap1 = false, hasNap2 = false, hasNap3 = false;
    let hasNw1 = false, hasNw2 = false, hasNw3 = false;
    for (const e of entries) {
      if (e.nap_1_start || e.nap_1_end) hasNap1 = true;
      if (e.nap_2_start || e.nap_2_end) hasNap2 = true;
      if (e.nap_3_start || e.nap_3_end) hasNap3 = true;
      const ent = e as Record<string, unknown>;
      if (ent.nonwear_1_start || ent.nonwear_1_end) hasNw1 = true;
      if (ent.nonwear_2_start || ent.nonwear_2_end) hasNw2 = true;
      if (ent.nonwear_3_start || ent.nonwear_3_end) hasNw3 = true;
    }
    const hasAnyNap = hasNap1 || hasNap2 || hasNap3;
    const hasAnyNw = hasNw1 || hasNw2 || hasNw3;
    return {
      hasNap1, hasNap2, hasNap3,
      hasNapCount: hasAnyNap,
      hasNw1, hasNw2, hasNw3,
      hasNwFlag: hasAnyNw,
    };
  }, [entries]);
}

export function DiaryPanel({ compact = false }: DiaryPanelProps) {
  const currentFileId = useSleepScoringStore((state) => state.currentFileId);
  const currentDateIndex = useSleepScoringStore((state) => state.currentDateIndex);
  const availableDates = useSleepScoringStore((state) => state.availableDates);
  const currentDate = availableDates[currentDateIndex] ?? null;
  const addSleepMarker = useSleepScoringStore((state) => state.addSleepMarker);
  const addNonwearMarker = useSleepScoringStore((state) => state.addNonwearMarker);

  const { dataSource, isLocal } = useDataSource();

  // Fetch ALL diary entries for current file via DataSource (server or local)
  const { data: entries } = useQuery({
    queryKey: ["diary", currentFileId, isLocal ? "local" : "server"],
    queryFn: async (): Promise<DiaryEntryResponse[]> => {
      if (isLocal) {
        const localEntries = await dataSource.listDiaryEntries(currentFileId!);
        return localEntries.map((e) => ({
          id: 0,
          file_id: e.fileId,
          analysis_date: e.analysisDate,
          bed_time: e.bedTime ?? null,
          wake_time: e.wakeTime ?? null,
          lights_out: e.lightsOut ?? null,
          got_up: e.gotUp ?? null,
          sleep_quality: e.sleepQuality ?? null,
          time_to_fall_asleep_minutes: e.timeToFallAsleepMinutes ?? null,
          number_of_awakenings: e.numberOfAwakenings ?? null,
          notes: e.notes ?? null,
          nap_1_start: e.nap1Start ?? null,
          nap_1_end: e.nap1End ?? null,
          nap_2_start: e.nap2Start ?? null,
          nap_2_end: e.nap2End ?? null,
          nap_3_start: e.nap3Start ?? null,
          nap_3_end: e.nap3End ?? null,
          nonwear_1_start: e.nonwear1Start ?? null,
          nonwear_1_end: e.nonwear1End ?? null,
          nonwear_1_reason: e.nonwear1Reason ?? null,
          nonwear_2_start: e.nonwear2Start ?? null,
          nonwear_2_end: e.nonwear2End ?? null,
          nonwear_2_reason: e.nonwear2Reason ?? null,
          nonwear_3_start: e.nonwear3Start ?? null,
          nonwear_3_end: e.nonwear3End ?? null,
          nonwear_3_reason: e.nonwear3Reason ?? null,
        }));
      }
      return diaryApi.listDiaryEntries(currentFileId!);
    },
    enabled: !!currentFileId,
  });

  /**
   * Parse a time string to 24-hour (hours, minutes).
   * Supports "23:30", "11:30 PM", "9:27 AM", "12:45 AM", "12:00 PM".
   */
  const parseTimeTo24h = useCallback((timeStr: string): [number, number] | null => {
    const s = timeStr.trim().toUpperCase();
    const isPM = s.includes("PM");
    const isAM = s.includes("AM");
    const clean = s.replace(/[AP]M/g, "").trim();
    const parts = clean.split(":");
    if (parts.length < 2) return null;
    let h = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    if (isNaN(h) || isNaN(m)) return null;

    if (isAM || isPM) {
      if (h === 12) h = isAM ? 0 : 12;
      else if (isPM) h += 12;
    }
    if (h < 0 || h > 23 || m < 0 || m > 59) return null;
    return [h, m];
  }, []);

  /**
   * Convert a diary time string to a UTC timestamp in seconds.
   * Bed/onset times >= 12 are evening of analysis date, < 12 are next day.
   * Wake/offset times < 18 are next day after analysis date.
   */
  const diaryTimeToTimestamp = useCallback(
    (date: string, timeStr: string, isOvernightStart: boolean): number | null => {
      if (!timeStr || !date) return null;
      const parsed = parseTimeTo24h(timeStr);
      if (!parsed) return null;
      const [hours, minutes] = parsed;

      const dateObj = new Date(date + "T00:00:00Z");
      if (isOvernightStart) {
        if (hours < 12) dateObj.setUTCDate(dateObj.getUTCDate() + 1);
      } else {
        if (hours < 18) dateObj.setUTCDate(dateObj.getUTCDate() + 1);
      }
      dateObj.setUTCHours(hours, minutes, 0, 0);
      return dateObj.getTime() / 1000;
    },
    [parseTimeTo24h]
  );

  /** Place main sleep marker from diary onset/offset (both at once, like desktop). */
  const handlePlaceSleep = useCallback(
    (entry: DiaryEntryResponse) => {
      const onset = entry.lights_out || entry.bed_time;
      const offset = entry.wake_time;
      if (!onset || !offset) return;
      const date = String(entry.analysis_date);
      const onsetTs = diaryTimeToTimestamp(date, onset, true);
      const offsetTs = diaryTimeToTimestamp(date, offset, false);
      if (onsetTs === null || offsetTs === null || onsetTs >= offsetTs) return;
      addSleepMarker(onsetTs, offsetTs);
    },
    [diaryTimeToTimestamp, addSleepMarker]
  );

  /** Place nap marker from diary nap start/end. */
  const handlePlaceNap = useCallback(
    (entry: DiaryEntryResponse, napIdx: 1 | 2 | 3) => {
      const start = (entry as Record<string, unknown>)[`nap_${napIdx}_start`] as string | null;
      const end = (entry as Record<string, unknown>)[`nap_${napIdx}_end`] as string | null;
      if (!start || !end) return;
      const date = String(entry.analysis_date);
      const startTs = diaryTimeToTimestamp(date, start, true);
      const endTs = diaryTimeToTimestamp(date, end, true);
      if (startTs === null || endTs === null || startTs >= endTs) return;
      addSleepMarker(startTs, endTs, "NAP");
    },
    [diaryTimeToTimestamp, addSleepMarker]
  );

  /** Place nonwear marker from diary nonwear start/end.
   *  Nonwear can happen anytime in the noon-to-noon window, so use
   *  isOvernightStart=true (h<12 → next day) for both start and end. */
  const handlePlaceNonwear = useCallback(
    (entry: DiaryEntryResponse, nwIdx: 1 | 2 | 3) => {
      const start = (entry as Record<string, unknown>)[`nonwear_${nwIdx}_start`] as string | null;
      const end = (entry as Record<string, unknown>)[`nonwear_${nwIdx}_end`] as string | null;
      if (!start || !end) return;
      const date = String(entry.analysis_date);
      const startTs = diaryTimeToTimestamp(date, start, true);
      const endTs = diaryTimeToTimestamp(date, end, true);
      if (startTs === null || endTs === null || startTs >= endTs) return;
      addNonwearMarker(startTs, endTs);
    },
    [diaryTimeToTimestamp, addNonwearMarker]
  );

  // Helper: get field from entry by dynamic key
  const getField = (entry: DiaryEntryResponse, key: string): string | null =>
    (entry as Record<string, unknown>)[key] as string | null;

  // Count naps for an entry
  const napCount = (e: DiaryEntryResponse) =>
    [e.nap_1_start, e.nap_2_start, e.nap_3_start].filter(Boolean).length;

  const vis = useVisibleColumns(entries);
  const ampmCorrections = useAmPmCorrections(entries);

  // Hide entirely if no file or no diary data
  if (!currentFileId || !entries || entries.length === 0) return null;

  const napIndices = ([1, 2, 3] as const).filter(
    (i) => vis[`hasNap${i}` as keyof typeof vis]
  );
  const nwIndices = ([1, 2, 3] as const).filter(
    (i) => vis[`hasNw${i}` as keyof typeof vis]
  );

  return (
    <Card className={compact ? "h-full flex flex-col" : ""}>
      <CardHeader className={compact ? "py-1.5 px-3 flex-none" : ""}>
        <CardTitle className={compact ? "text-sm" : "text-base"}>
          <Book className="h-4 w-4 inline mr-1.5" />
          Sleep Diary ({entries.length})
        </CardTitle>
      </CardHeader>
      <CardContent className={compact ? "p-0 flex-1 overflow-auto" : "p-0 overflow-auto"}>
        <table className={`w-full border-collapse ${compact ? "text-sm" : "text-base"}`}>
          <thead className="sticky top-0 bg-muted/90 backdrop-blur-sm z-10">
            <tr>
              {/* Core sleep columns — always visible */}
              <Th className="text-left" compact={compact}>Date</Th>
              <Th compact={compact}>In Bed</Th>
              <Th compact={compact}>Onset</Th>
              <Th compact={compact}>Offset</Th>
              {/* Nap columns — only groups that have data */}
              {vis.hasNapCount && <Th compact={compact}>#Nap</Th>}
              {napIndices.map((i) => [
                <Th key={`nap-${i}-h-on`} compact={compact}>Nap{i} On</Th>,
                <Th key={`nap-${i}-h-off`} compact={compact}>Nap{i} Off</Th>,
              ])}
              {/* Nonwear columns — only groups that have data */}
              {vis.hasNwFlag && <Th compact={compact}>NW</Th>}
              {nwIndices.map((i) => [
                <Th key={`nw-${i}-h-st`} compact={compact}>NW{i} St</Th>,
                <Th key={`nw-${i}-h-end`} compact={compact}>NW{i} End</Th>,
                <Th key={`nw-${i}-h-rsn`} className="text-left" compact={compact}>NW{i} Rsn</Th>,
              ])}
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => {
              const dateStr = String(entry.analysis_date);
              const isCurrentDate = dateStr === currentDate;
              const hasOnset = !!(entry.lights_out || entry.bed_time);
              const hasOffset = !!entry.wake_time;
              const canPlaceSleep = isCurrentDate && hasOnset && hasOffset;
              const hasNonwear = !!(entry.nonwear_1_start || entry.nonwear_2_start || entry.nonwear_3_start);
              const correction = ampmCorrections.get(entry.id);

              return (
                <tr
                  key={entry.id}
                  className={`border-t border-border/40 ${
                    isCurrentDate
                      ? "bg-primary/10 font-medium"
                      : "hover:bg-muted/40"
                  }`}
                >
                  {/* Date */}
                  <Td className="text-left font-mono" compact={compact}>{dateStr.slice(5)}</Td>

                  {/* In Bed Time */}
                  <Td className="text-muted-foreground" compact={compact}>{formatTimeDisplay(entry.bed_time)}</Td>

                  {/* Sleep Onset — clickable to place marker */}
                  <Td
                    clickable={canPlaceSleep}
                    onClick={() => handlePlaceSleep(entry)}
                    title={correction?.onset ? `Original: ${correction.origOnset}` : (canPlaceSleep ? "Click to place sleep marker" : undefined)}
                    className={correction?.onset ? "!bg-amber-100 dark:!bg-amber-950" : ""}
                    compact={compact}
                  >
                    {correction?.onset
                      ? <span className="text-red-700 dark:text-red-400 font-semibold">{correction.onset}</span>
                      : formatTimeDisplay(entry.lights_out)}
                  </Td>

                  {/* Sleep Offset — clickable to place marker */}
                  <Td
                    clickable={canPlaceSleep}
                    onClick={() => handlePlaceSleep(entry)}
                    title={correction?.wake ? `Original: ${correction.origWake}` : (canPlaceSleep ? "Click to place sleep marker" : undefined)}
                    className={correction?.wake ? "!bg-amber-100 dark:!bg-amber-950" : ""}
                    compact={compact}
                  >
                    {correction?.wake
                      ? <span className="text-red-700 dark:text-red-400 font-semibold">{correction.wake}</span>
                      : formatTimeDisplay(entry.wake_time)}
                  </Td>

                  {/* #Naps */}
                  {vis.hasNapCount && (
                    <Td className="text-muted-foreground" compact={compact}>{napCount(entry) || "--"}</Td>
                  )}

                  {/* Nap onset/offset columns — paired per nap */}
                  {napIndices.map((i) => {
                    const start = getField(entry, `nap_${i}_start`);
                    const end = getField(entry, `nap_${i}_end`);
                    const canPlace = isCurrentDate && !!start && !!end;
                    return [
                      <Td
                        key={`nap-${i}-on`}
                        clickable={canPlace}
                        onClick={() => handlePlaceNap(entry, i)}
                        title={canPlace ? `Click to place nap ${i} marker` : undefined}
                        compact={compact}
                      >
                        {formatTimeDisplay(start)}
                      </Td>,
                      <Td
                        key={`nap-${i}-off`}
                        clickable={canPlace}
                        onClick={() => handlePlaceNap(entry, i)}
                        title={canPlace ? `Click to place nap ${i} marker` : undefined}
                        compact={compact}
                      >
                        {formatTimeDisplay(end)}
                      </Td>,
                    ];
                  })}

                  {/* Nonwear Yes/No */}
                  {vis.hasNwFlag && (
                    <Td className="text-muted-foreground" compact={compact}>{hasNonwear ? "Yes" : "No"}</Td>
                  )}

                  {/* Nonwear start/end/reason for visible groups */}
                  {nwIndices.map((i) => {
                    const start = getField(entry, `nonwear_${i}_start`);
                    const end = getField(entry, `nonwear_${i}_end`);
                    const reason = getField(entry, `nonwear_${i}_reason`);
                    const canPlace = isCurrentDate && !!start && !!end;
                    return [
                      <Td
                        key={`nw-${i}-st`}
                        clickable={canPlace}
                        onClick={() => handlePlaceNonwear(entry, i)}
                        title={canPlace ? `Click to place nonwear ${i} marker` : undefined}
                        compact={compact}
                      >
                        {formatTimeDisplay(start)}
                      </Td>,
                      <Td
                        key={`nw-${i}-end`}
                        clickable={canPlace}
                        onClick={() => handlePlaceNonwear(entry, i)}
                        title={canPlace ? `Click to place nonwear ${i} marker` : undefined}
                        compact={compact}
                      >
                        {formatTimeDisplay(end)}
                      </Td>,
                      <Td key={`nw-${i}-rsn`} className="text-left text-muted-foreground" compact={compact}>
                        {reason || "--"}
                      </Td>,
                    ];
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
