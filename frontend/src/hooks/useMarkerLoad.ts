import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSleepScoringStore, useDates } from "@/store";
import { useDataSource } from "@/contexts/data-source-context";
import type { MarkerData } from "@/services/data-source";

/**
 * Hook to load markers when file/date changes.
 * Routes through DataSource (server or local) based on current file source.
 *
 * MarkerData from both DataSource impls is already in milliseconds.
 */
export function useMarkerLoad() {
  const currentFileId = useSleepScoringStore((state) => state.currentFileId);
  const username = useSleepScoringStore((state) => state.username);
  const { currentDate } = useDates();
  const { dataSource, isLocal } = useDataSource();

  // Use server-load variants that skip undo history + isDirty
  const _loadSleepMarkersFromServer = useSleepScoringStore((s) => s._loadSleepMarkersFromServer);
  const _loadNonwearMarkersFromServer = useSleepScoringStore((s) => s._loadNonwearMarkersFromServer);

  // Fetch markers via DataSource
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["markers", currentFileId, currentDate, username || "anonymous", isLocal ? "local" : "server"],
    queryFn: (): Promise<MarkerData | null> => {
      if (!currentFileId || !currentDate) return Promise.resolve(null);
      return dataSource.loadMarkers(currentFileId, currentDate, username || "anonymous");
    },
    enabled: !!currentFileId && !!currentDate,
    staleTime: 0,
    gcTime: 5 * 60 * 1000,
    // In server mode, poll for other users' changes every 30s.
    // Local mode doesn't need polling (single user, no remote changes).
    refetchInterval: isLocal ? false : 30_000,
    refetchIntervalInBackground: false,
  });

  // Update store when data is loaded
  useEffect(() => {
    if (!data) return;

    const current = useSleepScoringStore.getState();

    // Status flags (isNoSleep, needsConsensus, notes).
    // Only apply when the user has no pending local changes.
    if (!current.isDirty) {
      const apiIsNoSleep = data.isNoSleep ?? false;
      const apiNeedsConsensus = data.needsConsensus ?? false;
      const apiNotes = data.notes ?? "";
      const statusUpdate: Record<string, boolean | string> = {};
      if (current.isNoSleep !== apiIsNoSleep) statusUpdate.isNoSleep = apiIsNoSleep;
      if (current.needsConsensus !== apiNeedsConsensus) statusUpdate.needsConsensus = apiNeedsConsensus;
      if (current.notes !== apiNotes) statusUpdate.notes = apiNotes;
      if (Object.keys(statusUpdate).length > 0) {
        useSleepScoringStore.setState(statusUpdate);
      }
    }

    // CRITICAL: Never overwrite unsaved local changes with stale data.
    if (current.isDirty) return;

    // MarkerData is already in ms from both DataSource impls
    const apiSleepMarkers = data.sleepMarkers ?? [];
    const apiNonwearMarkers = data.nonwearMarkers ?? [];

    // Only update if changed (avoids re-render jank after auto-save)
    const sleepChanged =
      current.sleepMarkers.length !== apiSleepMarkers.length ||
      current.sleepMarkers.some((m, i) =>
        m.onsetTimestamp !== apiSleepMarkers[i].onsetTimestamp ||
        m.offsetTimestamp !== apiSleepMarkers[i].offsetTimestamp ||
        m.markerType !== apiSleepMarkers[i].markerType ||
        m.markerIndex !== apiSleepMarkers[i].markerIndex
      );

    const nonwearChanged =
      current.nonwearMarkers.length !== apiNonwearMarkers.length ||
      current.nonwearMarkers.some((m, i) =>
        m.startTimestamp !== apiNonwearMarkers[i].startTimestamp ||
        m.endTimestamp !== apiNonwearMarkers[i].endTimestamp ||
        m.markerIndex !== apiNonwearMarkers[i].markerIndex
      );

    if (sleepChanged) _loadSleepMarkersFromServer(apiSleepMarkers);
    if (nonwearChanged) _loadNonwearMarkersFromServer(apiNonwearMarkers);

    // Auto-select the first sleep marker when loading existing markers
    if (sleepChanged && apiSleepMarkers.length > 0 && current.selectedPeriodIndex === null) {
      useSleepScoringStore.setState({ selectedPeriodIndex: 0, markerMode: "sleep" });
    }
  }, [data, _loadSleepMarkersFromServer, _loadNonwearMarkersFromServer]);

  return {
    isLoading,
    error,
    refetch,
    hasMarkers: (data?.sleepMarkers?.length ?? 0) > 0 || (data?.nonwearMarkers?.length ?? 0) > 0,
    // Metrics and verificationStatus are server-only concepts; return defaults for local
    metrics: [],
    verificationStatus: "draft" as const,
  };
}
