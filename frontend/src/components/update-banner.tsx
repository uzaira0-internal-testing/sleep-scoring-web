import { useCallback, useEffect, useRef, useState } from "react";
import { isTauri } from "@/lib/tauri";
import { formatBytes } from "@/lib/format";
import type { UpdateInfo } from "@/lib/updater";
import { Download, RefreshCw, RotateCcw, X, ChevronDown, ChevronUp } from "lucide-react";

type BannerState =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "available"; info: UpdateInfo }
  | { status: "downloading"; percent: number | null; downloaded: number; total: number }
  | { status: "ready"; info: UpdateInfo }
  | { status: "error"; message: string; retryAction?: "check" | "download"; info?: UpdateInfo | undefined }
  | { status: "dismissed"; version: string };

/** Check interval: 15 minutes */
const CHECK_INTERVAL_MS = 15 * 60 * 1000;
/** Initial delay before first check */
const INITIAL_DELAY_MS = 3000;
/** Max retries for failed checks */
const MAX_RETRIES = 3;
/** Delay between retries (doubles each time) */
const RETRY_BASE_MS = 5000;
/** Minimum time between visibility-triggered checks */
const VISIBILITY_COOLDOWN_MS = 60 * 1000;

export function UpdateBanner() {
  const [state, setState] = useState<BannerState>({ status: "idle" });
  const [showNotes, setShowNotes] = useState(false);
  const retryCount = useRef(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastCheckRef = useRef(0);
  const checkInFlightRef = useRef(false);
  const downloadingRef = useRef(false);
  // Updated synchronously at every setState call site — no effect-sync needed
  const statusRef = useRef<BannerState["status"]>("idle");
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const setStateTracked = useCallback((next: BannerState | ((prev: BannerState) => BannerState)) => {
    if (!mountedRef.current) return;
    setState((prev) => {
      const resolved = typeof next === "function" ? next(prev) : next;
      statusRef.current = resolved.status;
      return resolved;
    });
  }, []);

  const doCheck = useCallback(async () => {
    if (checkInFlightRef.current) return;
    if (statusRef.current === "downloading" || statusRef.current === "ready") return;

    checkInFlightRef.current = true;
    lastCheckRef.current = Date.now();
    setStateTracked({ status: "checking" });
    try {
      const { checkForUpdate } = await import("@/lib/updater");
      const info = await checkForUpdate();
      retryCount.current = 0;
      if (info) {
        setStateTracked((prev) => {
          if (prev.status === "dismissed" && prev.version === info.version) {
            return prev;
          }
          return { status: "available", info };
        });
      } else {
        setStateTracked({ status: "idle" });
      }
    } catch (err) {
      console.error("[UpdateBanner] Update check failed:", err);
      const message = err instanceof Error ? err.message : "Update check failed";

      if (retryCount.current < MAX_RETRIES) {
        retryCount.current++;
        const delay = RETRY_BASE_MS * Math.pow(2, retryCount.current - 1);
        retryTimerRef.current = setTimeout(doCheck, delay);
        checkInFlightRef.current = false;
        return;
      }

      setStateTracked({ status: "error", message, retryAction: "check" });
    } finally {
      checkInFlightRef.current = false;
    }
  }, [setStateTracked]);

  // Initial check + periodic re-check + visibility/focus re-check
  useEffect(() => {
    if (!isTauri()) return;
    mountedRef.current = true;

    const initialTimer = setTimeout(doCheck, INITIAL_DELAY_MS);
    intervalRef.current = setInterval(doCheck, CHECK_INTERVAL_MS);

    const handleAppResume = () => {
      if (document.visibilityState !== "visible") return;
      if (Date.now() - lastCheckRef.current < VISIBILITY_COOLDOWN_MS) return;
      doCheck();
    };
    document.addEventListener("visibilitychange", handleAppResume);
    window.addEventListener("focus", handleAppResume);

    return () => {
      mountedRef.current = false;
      clearTimeout(initialTimer);
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      document.removeEventListener("visibilitychange", handleAppResume);
      window.removeEventListener("focus", handleAppResume);
    };
  }, [doCheck]);

  const handleUpdate = async () => {
    // Guard against double-click
    if (downloadingRef.current) return;
    downloadingRef.current = true;

    const info = state.status === "available" ? state.info
      : state.status === "error" ? state.info
      : undefined;

    setStateTracked({ status: "downloading", percent: null, downloaded: 0, total: 0 });
    let downloadedSoFar = 0;
    let lastPercent = -1;

    try {
      const { downloadAndInstall } = await import("@/lib/updater");
      await downloadAndInstall((progress) => {
        if (progress.chunkSize === 0 && progress.total > 0 && downloadedSoFar > 0) {
          // Finished event
          setStateTracked({ status: "downloading", percent: 100, downloaded: progress.total, total: progress.total });
        } else if (progress.total > 0) {
          downloadedSoFar += progress.chunkSize;
          const percent = Math.min(100, Math.round((downloadedSoFar / progress.total) * 100));
          // Only update state when displayed percent changes (throttle renders)
          if (percent !== lastPercent) {
            lastPercent = percent;
            setStateTracked({ status: "downloading", percent, downloaded: downloadedSoFar, total: progress.total });
          }
        }
      });
      setStateTracked({ status: "ready", info: info ?? { version: "latest", currentVersion: "" } });
    } catch (err) {
      console.error("[UpdateBanner] Download/install failed:", err);
      setStateTracked({
        status: "error",
        message: err instanceof Error ? err.message : "Update failed",
        retryAction: "download",
        info,
      });
    } finally {
      downloadingRef.current = false;
    }
  };

  const handleRestart = async () => {
    try {
      const { relaunchApp } = await import("@/lib/updater");
      await relaunchApp();
    } catch (err) {
      console.error("[UpdateBanner] Relaunch failed:", err);
      setStateTracked({
        status: "error",
        message: "Could not restart automatically. Please close and reopen the app.",
      });
    }
  };

  const handleRetry = () => {
    if (state.status === "error") {
      retryCount.current = 0;
      if (state.retryAction === "download") {
        void handleUpdate();
      } else {
        void doCheck();
      }
    }
  };

  const dismiss = () => {
    const version = state.status === "available" ? state.info.version
      : state.status === "error" && state.info ? state.info.version
      : "unknown";
    setStateTracked({ status: "dismissed", version });
  };

  if (!isTauri() || state.status === "idle" || state.status === "checking" || state.status === "dismissed") {
    return null;
  }

  if (state.status === "available") {
    const notes = state.info.body;
    return (
      <div className="bg-indigo-600 text-sm text-white">
        <div className="flex items-center justify-between gap-3 px-4 py-2">
          <div className="flex items-center gap-2 min-w-0">
            <Download className="h-4 w-4 shrink-0" />
            <span className="truncate">
              <strong>v{state.info.version}</strong> available
              {state.info.currentVersion && (
                <span className="text-indigo-200 ml-1">(current: v{state.info.currentVersion})</span>
              )}
            </span>
            {notes && (
              <button
                onClick={() => setShowNotes(!showNotes)}
                className="text-indigo-200 hover:text-white transition-colors shrink-0"
                aria-label={showNotes ? "Hide release notes" : "Show release notes"}
              >
                {showNotes ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </button>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleUpdate}
              className="rounded bg-white px-3 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50 transition-colors"
            >
              Update now
            </button>
            <button
              onClick={dismiss}
              className="text-indigo-200 hover:text-white transition-colors"
              aria-label="Dismiss"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        {showNotes && notes && (
          <div className="px-4 pb-2 text-xs text-indigo-100 whitespace-pre-wrap border-t border-indigo-500/30 pt-2">
            {notes}
          </div>
        )}
      </div>
    );
  }

  if (state.status === "downloading") {
    const isIndeterminate = state.percent === null;
    return (
      <div className="bg-indigo-600 px-4 py-2 text-sm text-white">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            <span>
              Downloading update...
              {!isIndeterminate && ` ${state.percent}%`}
              {state.total > 0 && (
                <span className="text-indigo-200 ml-1">
                  ({formatBytes(state.downloaded)} / {formatBytes(state.total)})
                </span>
              )}
            </span>
          </div>
        </div>
        <div className="h-1.5 w-full rounded-full bg-indigo-400/40 overflow-hidden">
          <div
            className={`h-full rounded-full bg-white ${isIndeterminate ? "animate-pulse w-full opacity-60" : "transition-all duration-300"}`}
            style={isIndeterminate ? undefined : { width: `${state.percent}%` }}
          />
        </div>
      </div>
    );
  }

  if (state.status === "ready") {
    return (
      <div className="flex items-center justify-between gap-3 bg-emerald-600 px-4 py-2 text-sm text-white">
        <div className="flex items-center gap-2">
          <RotateCcw className="h-4 w-4" />
          <span>
            Update to <strong>v{state.info.version}</strong> installed — Restart to apply
          </span>
        </div>
        <button
          onClick={handleRestart}
          className="rounded bg-white px-3 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-50 transition-colors"
        >
          Restart now
        </button>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="flex items-center justify-between gap-3 bg-red-600 px-4 py-2 text-sm text-white">
        <span className="truncate">Update failed: {state.message}</span>
        <div className="flex items-center gap-2 shrink-0">
          {state.retryAction && (
            <button
              onClick={handleRetry}
              className="rounded bg-white px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50 transition-colors"
            >
              Retry
            </button>
          )}
          <button
            onClick={dismiss}
            className="text-red-200 hover:text-white transition-colors"
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    );
  }

  return null;
}
