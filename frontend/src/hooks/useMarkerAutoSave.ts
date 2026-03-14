import { useEffect, useRef, useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMarkers, useSleepScoringStore, useDates } from "@/store";
import type { MarkerData } from "@/services/data-source";
import { getDataSource } from "@/services/data-source";

/**
 * Debounce delay for marker drag operations (continuous updates).
 * Discrete actions (consensus toggle, no-sleep, marker add/delete) save immediately.
 */
const DRAG_DEBOUNCE_MS = 300;

/** Maximum retry attempts */
const MAX_RETRIES = 3;

/**
 * Build MarkerData from current store state.
 * Reads directly from getState() to guarantee latest values.
 */
function buildMarkerData(): MarkerData {
  const state = useSleepScoringStore.getState();
  return {
    sleepMarkers: state.sleepMarkers.map((m) => ({
      onsetTimestamp: m.onsetTimestamp,
      offsetTimestamp: m.offsetTimestamp,
      markerIndex: m.markerIndex,
      markerType: m.markerType,
    })),
    nonwearMarkers: state.nonwearMarkers.map((m) => ({
      startTimestamp: m.startTimestamp,
      endTimestamp: m.endTimestamp,
      markerIndex: m.markerIndex,
    })),
    isNoSleep: state.isNoSleep,
    notes: state.notes || "",
    needsConsensus: state.needsConsensus,
  };
}

/** Construct a DataSource from current store state (prevents stale closures). */
function getDataSourceFromStore() {
  const state = useSleepScoringStore.getState();
  return getDataSource(state.currentFileSource, state.sitePassword, state.username);
}

/**
 * Auto-save hook for markers.
 *
 * - Discrete changes (consensus, no-sleep, marker add/delete): save immediately
 * - Marker drag operations: debounced at 300ms to batch rapid position updates
 * - Navigation: flushes any pending save before clearing state
 *
 * Routes through DataSource — local saves go to IndexedDB, server saves go to API.
 */
export function useMarkerAutoSave() {
  const currentFileId = useSleepScoringStore((state) => state.currentFileId);
  const username = useSleepScoringStore((state) => state.username);
  const { currentDate } = useDates();
  const queryClient = useQueryClient();

  const {
    sleepMarkers,
    nonwearMarkers,
    isNoSleep,
    needsConsensus,
    notes,
    isDirty,
    setSaving,
    setSaveError,
    markSaved,
  } = useMarkers();

  // Debounce timer ref
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);

  // Track previous marker count to detect discrete vs drag changes
  const prevSleepCountRef = useRef(sleepMarkers.length);
  const prevNonwearCountRef = useRef(nonwearMarkers.length);
  const prevIsNoSleepRef = useRef(isNoSleep);
  const prevNeedsConsensusRef = useRef(needsConsensus);

  // Post-save effects — conditional on local vs server
  const applyPostSaveEffects = useCallback(
    (fileId: number | null, date: string | null, isLocal: boolean, editGeneration?: number) => {
      markSaved(editGeneration);
      retryCountRef.current = 0;
      if (!fileId || !date) return;

      const sourceKey = isLocal ? "local" : "server";

      // Update the markers query cache so useMarkerLoad doesn't overwrite
      queryClient.setQueryData(
        ["markers", fileId, date, username || "anonymous", sourceKey],
        (): MarkerData => buildMarkerData(),
      );

      if (isLocal) {
        // Local: invalidate local dates-status
        queryClient.invalidateQueries({ queryKey: ["local-dates-status", fileId] });
      } else {
        // Server: refresh date status indicators and consensus sidebar
        queryClient.invalidateQueries({ queryKey: ["dates-status", fileId] });
        queryClient.invalidateQueries({ queryKey: ["consensus", fileId, date] });
        queryClient.invalidateQueries({ queryKey: ["consensus-ballot", fileId, date] });
        queryClient.invalidateQueries({ queryKey: ["analysis-summary"] });

        // Complexity recompute runs in backend background tasks
        setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: ["dates-status", fileId] });
          queryClient.invalidateQueries({ queryKey: ["analysis-summary"] });
        }, 1500);
        setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: ["dates-status", fileId] });
          queryClient.invalidateQueries({ queryKey: ["analysis-summary"] });
        }, 4000);
      }
    },
    [markSaved, queryClient, username]
  );

  // Save mutation — routes through DataSource
  const saveMutation = useMutation({
    mutationFn: async () => {
      const state = useSleepScoringStore.getState();
      const fileId = state.currentFileId;
      const { availableDates, currentDateIndex } = state;
      const date = availableDates[currentDateIndex] ?? null;
      if (!fileId || !date) throw new Error("No file/date for save");

      // Capture the edit generation at save start so markSaved can detect
      // whether the user edited during the in-flight save.
      const editGeneration = state._editGeneration;

      const ds = getDataSourceFromStore();
      const markerData = buildMarkerData();
      await ds.saveMarkers(fileId, date, state.username || "anonymous", markerData);
      return { savedFileId: fileId, savedDate: date, isLocal: state.currentFileSource === "local", editGeneration };
    },
    onMutate: () => {
      setSaving(true);
      setSaveError(null);
    },
    onSuccess: ({ savedFileId, savedDate, isLocal, editGeneration }) => {
      applyPostSaveEffects(savedFileId, savedDate, isLocal, editGeneration);
    },
    onError: (error: Error) => {
      setSaving(false);
      setSaveError(error.message);

      if (retryCountRef.current < MAX_RETRIES) {
        retryCountRef.current += 1;
        const retryDelay = Math.pow(2, retryCountRef.current) * 1000;
        const retryState = useSleepScoringStore.getState();
        const retryFileId = retryState.currentFileId;
        const retryDate = retryState.availableDates[retryState.currentDateIndex] ?? null;
        console.warn(
          `Save failed, retrying in ${retryDelay}ms (attempt ${retryCountRef.current}/${MAX_RETRIES})`
        );

        debounceTimerRef.current = setTimeout(() => {
          const s = useSleepScoringStore.getState();
          const curDate = s.availableDates[s.currentDateIndex] ?? null;
          if (s.currentFileId === retryFileId && curDate === retryDate) {
            performSave();
          }
        }, retryDelay);
      }
    },
  });

  const { mutate: saveMutate } = saveMutation;

  const performSave = useCallback(() => {
    const { currentFileId: fid, availableDates, currentDateIndex } = useSleepScoringStore.getState();
    const date = availableDates[currentDateIndex] ?? null;
    if (!fid || !date) return;

    saveMutate();
  }, [saveMutate]);

  // Watch for changes and trigger save
  useEffect(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }

    if (!isDirty || !currentFileId || !currentDate) return;

    retryCountRef.current = 0;

    const isDiscreteChange =
      isNoSleep !== prevIsNoSleepRef.current ||
      needsConsensus !== prevNeedsConsensusRef.current ||
      sleepMarkers.length !== prevSleepCountRef.current ||
      nonwearMarkers.length !== prevNonwearCountRef.current;

    prevIsNoSleepRef.current = isNoSleep;
    prevNeedsConsensusRef.current = needsConsensus;
    prevSleepCountRef.current = sleepMarkers.length;
    prevNonwearCountRef.current = nonwearMarkers.length;

    if (isDiscreteChange) {
      performSave();
    } else {
      debounceTimerRef.current = setTimeout(() => {
        performSave();
      }, DRAG_DEBOUNCE_MS);
    }

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [isDirty, currentFileId, currentDate, sleepMarkers, nonwearMarkers, isNoSleep, needsConsensus, notes, performSave]);

  // Register flush callback for navigateDate
  useEffect(() => {
    const flush = async (): Promise<boolean> => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }

      const state = useSleepScoringStore.getState();
      if (!state.isDirty) return true;

      const fileId = state.currentFileId;
      const date = state.availableDates[state.currentDateIndex] ?? null;
      if (!fileId || !date) return true;

      setSaving(true);
      setSaveError(null);

      let lastError: string | null = null;
      for (let attempt = 1; attempt <= MAX_RETRIES; attempt += 1) {
        try {
          const ds = getDataSourceFromStore();
          const markerData = buildMarkerData();
          await ds.saveMarkers(fileId, date, state.username || "anonymous", markerData);
          applyPostSaveEffects(fileId, date, state.currentFileSource === "local");
          return true;
        } catch (error) {
          lastError = error instanceof Error ? error.message : "Failed to save before navigation";
          if (attempt < MAX_RETRIES) {
            await new Promise<void>((resolve) => { setTimeout(resolve, attempt * 300); });
          }
        }
      }

      setSaving(false);
      setSaveError(lastError || "Failed to save before navigation");
      return false;
    };

    useSleepScoringStore.getState().registerFlushSave(flush);
    return () => {
      const current = useSleepScoringStore.getState()._flushSave;
      if (current === flush) {
        useSleepScoringStore.getState().registerFlushSave(null);
      }
    };
  }, [applyPostSaveEffects, setSaveError, setSaving]);

  // Warn user before closing tab with unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      const state = useSleepScoringStore.getState();
      if (state.isDirty) {
        e.preventDefault();
        // Modern browsers show a generic message regardless of returnValue
        e.returnValue = "You have unsaved changes. Are you sure you want to leave?";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  return {
    saveNow: performSave,
    isSaving: saveMutation.isPending,
  };
}
