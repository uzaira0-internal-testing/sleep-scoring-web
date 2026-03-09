import { useState, useCallback } from "react";
import { processLocalFile, type ProcessingProgress } from "@/services/local-processing";
import { useSleepScoringStore } from "@/store";

/** Progress that includes batch info for multi-file operations. */
export interface BatchProgress extends ProcessingProgress {
  fileIndex?: number;
  fileCount?: number;
  currentFilename?: string;
}

/**
 * Pick CSV files via File System Access API (Chromium) or <input type="file"> fallback.
 * Returns an array of File objects, or null if the user cancelled.
 */
async function pickFiles(multiple: boolean): Promise<File[] | null> {
  if ("showOpenFilePicker" in window) {
    try {
      const handles = await (window as unknown as { showOpenFilePicker: (opts: unknown) => Promise<FileSystemFileHandle[]> }).showOpenFilePicker({
        types: [{ description: "CSV Files", accept: { "text/csv": [".csv"] } }],
        multiple,
      });
      const files: File[] = [];
      for (const h of handles) files.push(await h.getFile());
      return files.length > 0 ? files : null;
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return null;
      throw err;
    }
  }

  // Fallback: <input type="file">
  return new Promise<File[] | null>((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".csv";
    if (multiple) input.multiple = true;
    input.onchange = () => {
      const list = Array.from(input.files ?? []);
      resolve(list.length > 0 ? list : null);
    };
    input.addEventListener("cancel", () => resolve(null));
    input.click();
  });
}

/**
 * Pick a folder via showDirectoryPicker (Chromium) or webkitdirectory fallback.
 * Filters for .csv files within the selected directory.
 */
async function pickFolder(): Promise<File[] | null> {
  if ("showDirectoryPicker" in window) {
    try {
      const dirHandle = await (window as unknown as { showDirectoryPicker: () => Promise<FileSystemDirectoryHandle> }).showDirectoryPicker();
      const files: File[] = [];
      for await (const entry of (dirHandle as unknown as AsyncIterable<FileSystemFileHandle | FileSystemDirectoryHandle>)) {
        const handle = entry as unknown as { kind: string; name: string; getFile: () => Promise<File> };
        if (handle.kind === "file" && handle.name.toLowerCase().endsWith(".csv")) {
          files.push(await handle.getFile());
        }
      }
      return files.length > 0 ? files : null;
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return null;
      throw err;
    }
  }

  // Fallback: <input webkitdirectory>
  return new Promise<File[] | null>((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.setAttribute("webkitdirectory", "");
    input.onchange = () => {
      const list = Array.from(input.files ?? []).filter((f) => f.name.toLowerCase().endsWith(".csv"));
      resolve(list.length > 0 ? list : null);
    };
    input.addEventListener("cancel", () => resolve(null));
    input.click();
  });
}

/**
 * Process multiple files sequentially, updating progress along the way.
 * Sets the first file as the current file after processing.
 */
async function processFiles(
  files: File[],
  setProgress: (p: BatchProgress | null) => void,
): Promise<Array<{ fileId: number; availableDates: string[] }>> {
  const state = useSleepScoringStore.getState();
  const devicePreset = state.devicePreset || "actigraph";
  const skipRows = state.skipRows ?? 10;
  const results: Array<{ fileId: number; availableDates: string[] }> = [];

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const onProgress = (p: ProcessingProgress) => {
      setProgress({
        ...p,
        fileIndex: i,
        fileCount: files.length,
        currentFilename: file.name,
        message: files.length > 1
          ? `[${i + 1}/${files.length}] ${file.name}: ${p.message}`
          : p.message,
      });
    };

    onProgress({ phase: "reading", percent: 0, message: "Starting..." });
    const result = await processLocalFile(file, devicePreset, skipRows, onProgress);
    results.push(result);
  }

  // Set first file as current
  if (results.length > 0) {
    useSleepScoringStore.setState({
      currentFileId: results[0].fileId,
      currentFilename: files[0].name,
      availableDates: results[0].availableDates,
      currentDateIndex: 0,
      currentFileSource: "local",
    });
  }

  return results;
}

/**
 * Hook for opening and processing local files.
 * Supports single file, multi-file, and folder selection.
 */
export function useLocalFile() {
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState<BatchProgress | null>(null);
  const [error, setError] = useState<string | null>(null);

  /** Shared wrapper: pick files, process them, handle errors/cleanup. */
  const run = useCallback(
    async <T>(
      picker: () => Promise<File[] | null>,
      initialMessage: string | ((files: File[]) => string),
      mapResult: (results: Array<{ fileId: number; availableDates: string[] }>) => T,
    ): Promise<T | null> => {
      setError(null);
      const files = await picker();
      if (!files) return null;

      setIsProcessing(true);
      const msg = typeof initialMessage === "function" ? initialMessage(files) : initialMessage;
      setProgress({ phase: "reading", percent: 0, message: msg });
      try {
        const results = await processFiles(files, setProgress);
        return mapResult(results);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Processing failed");
        return null;
      } finally {
        setIsProcessing(false);
        setTimeout(() => setProgress(null), 3000);
      }
    },
    [],
  );

  const openLocalFile = useCallback(
    () => run(() => pickFiles(false), "Starting...", (r) => r[0] ?? null),
    [run],
  );

  const openLocalFiles = useCallback(
    () => run(() => pickFiles(true), "Starting...", (r) => r),
    [run],
  );

  const openLocalFolder = useCallback(
    () => run(pickFolder, (files) => `Found ${files.length} CSV files...`, (r) => r),
    [run],
  );

  return { openLocalFile, openLocalFiles, openLocalFolder, isProcessing, progress, error };
}
