import { useEffect, useRef, useCallback } from "react";
import { useSyncStore } from "@/store/sync-store";
import { useSleepScoringStore } from "@/store";
import { config } from "@/config";
import { isTauri } from "@/lib/tauri";
import { syncAll } from "@/services/sync";
import * as localDb from "@/db";

const HEALTH_CHECK_INTERVAL = 10_000; // 10 seconds
const SYNC_INTERVAL = 30_000; // 30 seconds

/**
 * Hook that monitors connectivity and triggers sync.
 * Both navigator.onLine AND health check must pass for isOnline = true.
 * When online, runs sync every 30s and on connectivity recovery.
 */
export function useConnectivity(enabled: boolean = true) {
  const { isOnline, setOnline, setSyncing, setSyncComplete, setSyncError } = useSyncStore();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const syncIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const syncInProgressRef = useRef(false);

  const runSync = useCallback(async () => {
    if (syncInProgressRef.current) return;
    syncInProgressRef.current = true;

    const { sitePassword, username } = useSleepScoringStore.getState();
    if (!username) {
      syncInProgressRef.current = false;
      return;
    }

    // Check if there's anything to sync before updating UI
    const pending = await localDb.getPendingMarkers();
    if (pending.length === 0) {
      setSyncComplete(0);
      syncInProgressRef.current = false;
      return;
    }

    setSyncing();
    try {
      const result = await syncAll(sitePassword, username);
      const remainingPending = await localDb.getPendingMarkers();
      setSyncComplete(remainingPending.length);
      if (result.errors.length > 0) {
        console.warn("[Sync] Errors:", result.errors);
      }
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      syncInProgressRef.current = false;
    }
  }, [setSyncing, setSyncComplete, setSyncError]);

  const checkHealth = useCallback(async () => {
    // In Tauri, /health hits the asset server which returns 200 HTML for all paths.
    // This would falsely set isOnline=true. Skip health checks entirely in Tauri.
    if (isTauri()) {
      setOnline(false);
      return;
    }

    if (!navigator.onLine) {
      setOnline(false);
      return;
    }

    try {
      const response = await fetch(`${config.basePath}/health`, {
        method: "GET",
        signal: AbortSignal.timeout(5000),
      });
      // Guard: ensure response is actually from our backend, not an SPA fallback
      const ct = response.headers.get("content-type") ?? "";
      if (!ct.includes("application/json")) {
        setOnline(false);
        return;
      }
      const wasOnline = useSyncStore.getState().isOnline;
      setOnline(response.ok);

      // Trigger sync when coming back online
      if (response.ok && !wasOnline) {
        runSync();
      }
    } catch {
      setOnline(false);
    }
  }, [setOnline, runSync]);

  useEffect(() => {
    if (!enabled) return;
    // In Tauri, there's no backend server — skip all connectivity infrastructure
    if (isTauri()) return;

    const handleOnline = () => {
      checkHealth();
    };
    const handleOffline = () => {
      setOnline(false);
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    // Poll health when navigator says we're online and tab is visible
    intervalRef.current = setInterval(() => {
      if (navigator.onLine && document.visibilityState === "visible") {
        checkHealth();
      }
    }, HEALTH_CHECK_INTERVAL);

    // Periodic sync when online
    syncIntervalRef.current = setInterval(() => {
      if (useSyncStore.getState().isOnline && document.visibilityState === "visible") {
        runSync();
      }
    }, SYNC_INTERVAL);

    // Initial check
    checkHealth();

    // Update pending count on mount
    localDb.getPendingMarkers().then((p) => setSyncComplete(p.length));

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (syncIntervalRef.current) clearInterval(syncIntervalRef.current);
    };
  }, [enabled, checkHealth, setOnline, runSync, setSyncComplete]);

  return { isOnline };
}
