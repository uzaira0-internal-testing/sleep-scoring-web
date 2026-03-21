/**
 * React hook for TUS resumable file uploads with gzip compression.
 *
 * Creates an Uppy instance with TUS plugin and gzip compressor.
 * Tracks progress through compression → upload → server processing phases.
 * After upload completes, polls the processing status endpoint.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import Uppy from "@uppy/core";
import Tus from "@uppy/tus";
import { useSleepScoringStore } from "@/store";
import { GzipCompressorPlugin } from "@/lib/uppy-gzip-plugin";
import { queryClient } from "@/query-client";
import { getWorkspaceApiBase } from "@/lib/workspace-api";
import { filesQueryOptions } from "@/api/query-options";

export type TusPhase = "idle" | "compressing" | "uploading" | "done" | "error";

export interface TusProgress {
  phase: TusPhase;
  percent: number;
  bytesUploaded: number;
  bytesTotal: number;
  speed: number; // bytes/sec
  eta: number; // seconds
  fileName: string;
  error: string | null;
}

const INITIAL_PROGRESS: TusProgress = {
  phase: "idle",
  percent: 0,
  bytesUploaded: 0,
  bytesTotal: 0,
  speed: 0,
  eta: 0,
  fileName: "",
  error: null,
};

/** Minimum file size to trigger TUS upload (50MB). Below this, use simple upload. */
export const TUS_SIZE_THRESHOLD = 50 * 1024 * 1024; // v2 — cache-bust 2026-03-16

export function useTusUpload() {
  const [progress, setProgress] = useState<TusProgress>(INITIAL_PROGRESS);
  const uppyRef = useRef<Uppy | null>(null);
  const speedTracker = useRef({ lastBytes: 0, lastTime: 0, lastSpeed: 0 });

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      uppyRef.current?.cancelAll();
      uppyRef.current?.destroy();
    };
  }, []);

  const getUppy = useCallback(() => {
    if (uppyRef.current) return uppyRef.current;

    const { sitePassword, username } = useSleepScoringStore.getState();

    const uppy = new Uppy({
      restrictions: {
        allowedFileTypes: [".csv", ".xlsx", ".xls"],
      },
      autoProceed: false,
    });

    // Add gzip compressor (runs before upload)
    uppy.use(GzipCompressorPlugin, { minSize: 1024 });

    // Add TUS plugin
    uppy.use(Tus, {
      endpoint: `${getWorkspaceApiBase()}/tus/files/`,
      chunkSize: 5 * 1024 * 1024, // 5MB chunks
      retryDelays: [0, 1000, 3000, 5000, 10000],
      removeFingerprintOnSuccess: true,
      storeFingerprintForResuming: false, // Disable localStorage URL caching — stale entries cause 404 loops
      onBeforeRequest: (req: { setHeader: (key: string, value: string) => void }) => {
        const state = useSleepScoringStore.getState();
        if (state.sitePassword) {
          req.setHeader("X-Site-Password", state.sitePassword);
        }
        req.setHeader("X-Username", state.username || "anonymous");
      },
      headers: {
        "X-Site-Password": sitePassword || "",
        "X-Username": username || "anonymous",
      },
    });

    // Track upload progress
    uppy.on("upload-progress", (file, progress) => {
      if (!file || !progress) return;
      const now = Date.now();
      const elapsed = (now - speedTracker.current.lastTime) / 1000;
      const bytesDelta = (progress.bytesUploaded ?? 0) - speedTracker.current.lastBytes;

      // Exponential moving average for smooth speed/ETA display
      const instantSpeed = elapsed > 0.1 ? bytesDelta / elapsed : 0;
      const prevSpeed = speedTracker.current.lastSpeed ?? 0;
      const smoothed = prevSpeed > 0 && instantSpeed > 0
        ? prevSpeed * 0.7 + instantSpeed * 0.3
        : instantSpeed || prevSpeed;
      const remaining = (progress.bytesTotal ?? 0) - (progress.bytesUploaded ?? 0);
      const eta = smoothed > 0 ? remaining / smoothed : 0;

      // Only update tracker if enough time has passed to avoid jitter
      if (elapsed > 0.1) {
        speedTracker.current = { lastBytes: progress.bytesUploaded ?? 0, lastTime: now, lastSpeed: smoothed };
      }

      setProgress((prev) => ({
        ...prev,
        phase: "uploading",
        percent: progress.bytesTotal ? ((progress.bytesUploaded ?? 0) / progress.bytesTotal) * 100 : 0,
        bytesUploaded: progress.bytesUploaded ?? 0,
        bytesTotal: progress.bytesTotal ?? 0,
        speed: smoothed,
        eta,
        fileName: file.name ?? "",
      }));
    });

    // Upload success — done. Server processing happens in the background
    // and the file won't appear for scoring until it's assigned anyway.
    uppy.on("upload-success", () => {
      setProgress((prev) => ({
        ...prev,
        phase: "done",
        percent: 100,
      }));
      queryClient.invalidateQueries({ queryKey: filesQueryOptions().queryKey });
    });

    // Upload error
    uppy.on("upload-error", (_file, error) => {
      setProgress((prev) => ({
        ...prev,
        phase: "error",
        error: error?.message || "Upload failed",
      }));
    });

    uppyRef.current = uppy;
    return uppy;
  }, []);

  const upload = useCallback(
    async (files: File[], replace = false) => {
      const uppy = getUppy();
      uppy.cancelAll();

      // Reset progress
      setProgress({ ...INITIAL_PROGRESS, phase: "compressing", fileName: files[0]?.name ?? "" });
      speedTracker.current = { lastBytes: 0, lastTime: Date.now(), lastSpeed: 0 };

      // Add files with metadata
      const { sitePassword, username, devicePreset, skipRows } = useSleepScoringStore.getState();
      for (const file of files) {
        uppy.addFile({
          name: file.name,
          type: file.type || "text/csv",
          data: file,
          meta: {
            filename: file.name,
            site_password: sitePassword || "",
            username: username || "anonymous",
            device_preset: devicePreset || "",
            skip_rows: String(skipRows ?? 10),
            replace: replace ? "true" : "false",
          },
        });
      }

      try {
        const result = await uppy.upload();
        if (result && result.failed && result.failed.length > 0) {
          const failedNames = result.failed.map((f) => f.name ?? "unknown").join(", ");
          setProgress((prev) => ({
            ...prev,
            phase: "error",
            error: `Upload failed for: ${failedNames}`,
          }));
        }
      } catch (err) {
        setProgress((prev) => ({
          ...prev,
          phase: "error",
          error: err instanceof Error ? err.message : "Upload failed",
        }));
      }
    },
    [getUppy]
  );

  const cancel = useCallback(() => {
    uppyRef.current?.cancelAll();
    setProgress(INITIAL_PROGRESS);
  }, []);

  const pause = useCallback(() => {
    uppyRef.current?.pauseAll();
  }, []);

  const resume = useCallback(() => {
    uppyRef.current?.resumeAll();
  }, []);

  const reset = useCallback(() => {
    uppyRef.current?.cancelAll();
    setProgress(INITIAL_PROGRESS);
  }, []);

  return {
    progress,
    upload,
    cancel,
    pause,
    resume,
    reset,
  };
}
