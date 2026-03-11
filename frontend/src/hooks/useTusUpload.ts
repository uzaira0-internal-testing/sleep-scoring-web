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
import { filesApi } from "@/api/client";
import { filesQueryOptions } from "@/api/query-options";

export type TusPhase = "idle" | "compressing" | "uploading" | "processing" | "done" | "error";

export interface TusProgress {
  phase: TusPhase;
  percent: number;
  bytesUploaded: number;
  bytesTotal: number;
  speed: number; // bytes/sec
  eta: number; // seconds
  fileName: string;
  /** Server processing progress (after upload) */
  processingPhase: string | null;
  processingPercent: number;
  error: string | null;
  /** File ID assigned by server (available after upload completes) */
  fileId: number | null;
}

const INITIAL_PROGRESS: TusProgress = {
  phase: "idle",
  percent: 0,
  bytesUploaded: 0,
  bytesTotal: 0,
  speed: 0,
  eta: 0,
  fileName: "",
  processingPhase: null,
  processingPercent: 0,
  error: null,
  fileId: null,
};

/** Minimum file size to trigger TUS upload (50MB). Below this, use simple upload. */
export const TUS_SIZE_THRESHOLD = 50 * 1024 * 1024;

export function useTusUpload() {
  const [progress, setProgress] = useState<TusProgress>(INITIAL_PROGRESS);
  const uppyRef = useRef<Uppy | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const speedTracker = useRef({ lastBytes: 0, lastTime: 0 });

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
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
      endpoint: `${getWorkspaceApiBase()}/tus/`,
      chunkSize: 5 * 1024 * 1024, // 5MB chunks
      retryDelays: [0, 1000, 3000, 5000, 10000],
      removeFingerprintOnSuccess: true,
      onBeforeRequest: (req: any) => {
        // Attach auth and metadata to each TUS request
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
      const speed = elapsed > 0 ? bytesDelta / elapsed : 0;
      const remaining = (progress.bytesTotal ?? 0) - (progress.bytesUploaded ?? 0);
      const eta = speed > 0 ? remaining / speed : 0;

      speedTracker.current = { lastBytes: progress.bytesUploaded ?? 0, lastTime: now };

      setProgress((prev) => ({
        ...prev,
        phase: "uploading",
        percent: progress.bytesTotal ? ((progress.bytesUploaded ?? 0) / progress.bytesTotal) * 100 : 0,
        bytesUploaded: progress.bytesUploaded ?? 0,
        bytesTotal: progress.bytesTotal ?? 0,
        speed,
        eta,
        fileName: file.name ?? "",
      }));
    });

    // Upload success — start polling server processing
    uppy.on("upload-success", (_file, _response) => {
      setProgress((prev) => ({
        ...prev,
        phase: "processing",
        percent: 100,
        processingPhase: "Starting...",
        processingPercent: 0,
      }));
      // Invalidate file list so it shows the new file
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
    async (files: File[]) => {
      const uppy = getUppy();
      uppy.cancelAll();

      // Reset progress
      setProgress({ ...INITIAL_PROGRESS, phase: "compressing", fileName: files[0]?.name ?? "" });
      speedTracker.current = { lastBytes: 0, lastTime: Date.now() };

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
          },
        });
      }

      try {
        const result = await uppy.upload();
        if (result && result.successful && result.successful.length > 0) {
          // Start polling for processing status
          startProcessingPoll(files[0]?.name ?? "");
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

  const startProcessingPoll = useCallback(
    (filename: string) => {
      // Cache fileId after first successful lookup to avoid re-fetching file list every poll
      let cachedFileId: number | null = null;

      const poll = async () => {
        try {
          // Resolve fileId once, then reuse
          if (cachedFileId === null) {
            const listData = await filesApi.listFiles();
            const fileEntry = listData.items?.find(
              (f) => f.filename === filename
            );
            if (!fileEntry) return;
            cachedFileId = fileEntry.id;
            setProgress((prev) => ({ ...prev, fileId: cachedFileId }));
          }

          const statusData = await filesApi.getProcessingStatus(cachedFileId);

          if (statusData.status === "ready") {
            setProgress((prev) => ({
              ...prev,
              phase: "done",
              processingPercent: 100,
              processingPhase: null,
              fileId: cachedFileId,
            }));
            if (pollingRef.current) clearInterval(pollingRef.current);
            queryClient.invalidateQueries({ queryKey: filesQueryOptions().queryKey });
            queryClient.invalidateQueries({ queryKey: ["dates-status"] });
            return;
          }

          if (statusData.status === "failed") {
            setProgress((prev) => ({
              ...prev,
              phase: "error",
              error: statusData.error || "Server processing failed",
              fileId: cachedFileId,
            }));
            if (pollingRef.current) clearInterval(pollingRef.current);
            return;
          }

          setProgress((prev) => ({
            ...prev,
            phase: "processing",
            processingPhase: statusData.phase || "Processing...",
            processingPercent: statusData.percent || 0,
            fileId: cachedFileId,
          }));
        } catch {
          // Polling errors are non-fatal
        }
      };

      if (pollingRef.current) clearInterval(pollingRef.current);
      pollingRef.current = setInterval(poll, 2000);
      poll(); // Immediate first poll
    },
    []
  );

  const cancel = useCallback(() => {
    uppyRef.current?.cancelAll();
    if (pollingRef.current) clearInterval(pollingRef.current);
    setProgress(INITIAL_PROGRESS);
  }, []);

  const pause = useCallback(() => {
    uppyRef.current?.pauseAll();
  }, []);

  const resume = useCallback(() => {
    uppyRef.current?.resumeAll();
  }, []);

  const reset = useCallback(() => {
    if (pollingRef.current) clearInterval(pollingRef.current);
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
