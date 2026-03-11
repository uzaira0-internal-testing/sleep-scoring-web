import { getWasmApi, terminateWasmWorker } from "@/workers";
import { readFileAsText, type ChunkReadProgress } from "@/lib/chunked-reader";
import { computeFileHash } from "@/lib/content-hash";
import { stripBom } from "@/lib/csv-utils";
import * as localDb from "@/db";

/**
 * Result from WASM CSV parsing (matches Rust CsvParseResult via serde).
 * IMPORTANT: timestamps_ms are in milliseconds — convert to seconds
 * before storing in IndexedDB (done in processLocalFile).
 */
interface CsvParseResult {
  timestamps_ms: number[]; // Unix milliseconds from WASM
  axis_y: number[];
  axis_x: number[];
  axis_z: number[];
  vector_magnitude: number[];
  is_raw: boolean;
  sample_frequency: number;
  header_rows_skipped: number;
}

/**
 * Result from WASM epoching (matches Rust EpochResult via serde).
 * timestamps_ms are in milliseconds — converted to seconds downstream.
 */
interface EpochResult {
  timestamps_ms: number[]; // Unix milliseconds from WASM
  axis_y: number[];
  axis_x: number[];
  axis_z: number[];
  vector_magnitude: number[];
}

/**
 * Race a promise against a timeout. Rejects with a descriptive error if the timeout fires.
 * NOTE: This does NOT cancel the underlying WASM operation — it just stops waiting.
 * On timeout we terminate the worker to actually free resources.
 */
function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  let timeoutId: ReturnType<typeof setTimeout>;
  return Promise.race([
    promise.finally(() => clearTimeout(timeoutId)),
    new Promise<never>((_, reject) => {
      timeoutId = setTimeout(() => {
        // Terminate the worker so the WASM computation actually stops
        terminateWasmWorker();
        reject(new Error(`WASM operation timed out after ${ms / 1000}s: ${label}`));
      }, ms);
    }),
  ]);
}

/** Timeout for WASM operations (5 minutes — large files can take a while). */
const WASM_TIMEOUT_MS = 5 * 60 * 1000;

export type ProcessingPhase = "reading" | "parsing" | "epoching" | "scoring" | "nonwear" | "storing" | "complete";

export interface ProcessingProgress {
  phase: ProcessingPhase;
  percent: number;
  message: string;
}

/** Per-day algorithm results produced during local processing. */
interface DayAlgorithmResults {
  sadeh_1994_actilife: Uint8Array;
  sadeh_1994_original: Uint8Array;
  cole_kripke_1992_actilife: Uint8Array;
  cole_kripke_1992_original: Uint8Array;
  nonwear: Uint8Array;
}

/**
 * Process a locally-opened file through the full pipeline:
 * 1. Read file (chunked)
 * 2. Parse CSV via WASM (detect columns, extract data)
 * 3. If raw GENEActiv: epoch via WASM
 * 4. Split into per-date activity arrays
 * 5. Run sleep algorithm + nonwear detection via WASM
 * 6. Store all results in IndexedDB
 */
export async function processLocalFile(
  file: File,
  devicePreset: string,
  skipRows: number,
  onProgress?: (progress: ProcessingProgress) => void,
  choiAxis: string = "vector_magnitude",
): Promise<{ fileId: number; availableDates: string[] }> {
  const wasmApi = getWasmApi();

  // Early dedup check (hash first 64KB, no full read needed)
  const fileHash = await computeFileHash(file);
  const existing = await localDb.getFileByFilename(file.name);
  if (existing?.fileHash === fileHash) {
    const dates = await localDb.getAvailableDates(existing.id!);
    return { fileId: existing.id!, availableDates: dates };
  }

  // Step 1: Read file
  onProgress?.({ phase: "reading", percent: 0, message: "Reading file..." });
  const content = await readFileAsText(file, (p: ChunkReadProgress) => {
    onProgress?.({ phase: "reading", percent: p.percent * 0.3, message: `Reading: ${Math.round(p.percent)}%` });
  });

  // Step 2: Parse CSV
  onProgress?.({ phase: "parsing", percent: 30, message: "Parsing CSV..." });

  // Strip BOM before any parsing (Windows/Excel CSVs may have UTF-8 BOM)
  const cleanContent = stripBom(content);

  // Quick first-line check for GENEActiv format (avoids sending entire string to WASM)
  const firstLine = cleanContent.slice(0, cleanContent.indexOf("\n")).trim().toLowerCase();
  const isGeneactiv = firstLine.includes("geneactiv") || devicePreset === "geneactiv";

  let parseResult: CsvParseResult;
  if (isGeneactiv) {
    parseResult = await withTimeout(wasmApi.parseGeneactivCsv(cleanContent), WASM_TIMEOUT_MS, "parseGeneactivCsv") as CsvParseResult;
  } else {
    parseResult = await withTimeout(wasmApi.parseActigraphCsv(cleanContent, skipRows), WASM_TIMEOUT_MS, "parseActigraphCsv") as CsvParseResult;
  }

  let timestamps = parseResult.timestamps_ms;
  let axisX = parseResult.axis_x;
  let axisY = parseResult.axis_y;
  let axisZ = parseResult.axis_z;
  let vectorMagnitude = parseResult.vector_magnitude;

  // Step 3: Epoch if raw data
  if (parseResult.is_raw && parseResult.sample_frequency > 0) {
    onProgress?.({ phase: "epoching", percent: 45, message: "Converting to epochs..." });
    const epochResult = await withTimeout(
      wasmApi.epochRawData(
        new Float64Array(timestamps),
        new Float64Array(axisX),
        new Float64Array(axisY),
        new Float64Array(axisZ),
        parseResult.sample_frequency,
      ),
      WASM_TIMEOUT_MS,
      "epochRawData",
    ) as EpochResult;

    timestamps = epochResult.timestamps_ms;
    axisX = epochResult.axis_x;
    axisY = epochResult.axis_y;
    axisZ = epochResult.axis_z;
    vectorMagnitude = epochResult.vector_magnitude;
  }

  // Select the axis to use for Choi nonwear detection
  const choiData: Record<string, number[]> = {
    vector_magnitude: vectorMagnitude,
    axis_y: axisY,
    axis_x: axisX,
    axis_z: axisZ,
  };
  const choiAxisData = choiData[choiAxis];
  if (!choiAxisData) {
    console.warn(`[local-processing] Unknown choiAxis "${choiAxis}", falling back to vector_magnitude`);
  }
  const selectedChoiData = choiAxisData ?? vectorMagnitude;

  // Step 4: Convert ms→seconds and split into per-date arrays
  // WASM outputs timestamps_ms — convert once here so all downstream storage is seconds.
  onProgress?.({ phase: "scoring", percent: 55, message: "Running sleep algorithms..." });
  const timestampsSec = timestamps.map(t => t / 1000);
  const extraChoiArray = choiAxis !== "vector_magnitude" ? selectedChoiData : undefined;
  const dateGroups = splitByDate(timestampsSec, axisY, vectorMagnitude, extraChoiArray);
  const availableDates = Object.keys(dateGroups).sort();

  // Step 5: Run ALL algorithm variants on each day
  const algorithmResultsByDate: Record<string, DayAlgorithmResults> = {};

  for (let i = 0; i < availableDates.length; i++) {
    const date = availableDates[i]!;
    const group = dateGroups[date]!;
    const pct = 55 + (i / availableDates.length) * 30;

    onProgress?.({ phase: "scoring", percent: pct, message: `Scoring ${date}...` });

    const activityF64 = new Float64Array(group.axisY);
    const [sadehActilife, sadehOriginal, ckActilife, ckOriginal, nonwear] = await Promise.all([
      withTimeout(wasmApi.scoreSadeh(activityF64, -4.0), WASM_TIMEOUT_MS, `scoreSadeh_actilife(${date})`),
      withTimeout(wasmApi.scoreSadeh(activityF64, 0.0), WASM_TIMEOUT_MS, `scoreSadeh_original(${date})`),
      withTimeout(wasmApi.scoreColeKripke(activityF64, true), WASM_TIMEOUT_MS, `scoreColeKripke_actilife(${date})`),
      withTimeout(wasmApi.scoreColeKripke(activityF64, false), WASM_TIMEOUT_MS, `scoreColeKripke_original(${date})`),
      withTimeout(wasmApi.detectNonwear(new Float64Array(group.choiAxis ?? group.vectorMagnitude)), WASM_TIMEOUT_MS, `detectNonwear(${date})`),
    ]);

    algorithmResultsByDate[date] = {
      sadeh_1994_actilife: sadehActilife,
      sadeh_1994_original: sadehOriginal,
      cole_kripke_1992_actilife: ckActilife,
      cole_kripke_1992_original: ckOriginal,
      nonwear,
    };
  }

  // Step 6: Store in IndexedDB
  onProgress?.({ phase: "storing", percent: 85, message: "Saving to local database..." });

  const fileId = await localDb.saveFileRecord({
    filename: file.name,
    devicePreset,
    epochLengthSeconds: 60,
    availableDates,
    fileHash,
    source: "local",
    createdAt: new Date().toISOString(),
  });

  for (const date of availableDates) {
    const group = dateGroups[date]!;
    const algoResults = algorithmResultsByDate[date]!;

    // .buffer is safe without .slice(0) — WASM worker uses Comlink.transfer() which
    // transfers ownership to the main thread, so these are already independent buffers.
    await localDb.saveActivityDay({
      fileId,
      date,
      timestamps: new Float64Array(group.timestamps).buffer as ArrayBuffer,
      axisY: new Float64Array(group.axisY).buffer as ArrayBuffer,
      vectorMagnitude: new Float64Array(group.vectorMagnitude).buffer as ArrayBuffer,
      algorithmResults: {
        sadeh_1994_actilife: algoResults.sadeh_1994_actilife.buffer as ArrayBuffer,
        sadeh_1994_original: algoResults.sadeh_1994_original.buffer as ArrayBuffer,
        cole_kripke_1992_actilife: algoResults.cole_kripke_1992_actilife.buffer as ArrayBuffer,
        cole_kripke_1992_original: algoResults.cole_kripke_1992_original.buffer as ArrayBuffer,
      },
      nonwearResults: algoResults.nonwear.buffer as ArrayBuffer,
    });
  }

  onProgress?.({ phase: "complete", percent: 100, message: "Processing complete" });

  return { fileId, availableDates };
}

interface DateGroup {
  timestamps: number[];
  axisY: number[];
  vectorMagnitude: number[];
  choiAxis?: number[];
}

/**
 * Split epoch data into per-date groups.
 * Optionally splits an extra array (e.g. Choi axis data) in the same pass.
 */
function splitByDate(
  timestamps: number[],
  axisY: number[],
  vectorMagnitude: number[],
  extraArray?: number[],
): Record<string, DateGroup> {
  const groups: Record<string, DateGroup> = {};
  const hasExtra = extraArray != null;

  // Cache: only create Date object when day boundary crossed
  let cachedDateStr = "";
  let cachedDayStart = 0;
  let cachedDayEnd = 0;

  for (let i = 0; i < timestamps.length; i++) {
    const ts = timestamps[i]!;

    if (ts < cachedDayStart || ts >= cachedDayEnd) {
      const date = new Date(ts * 1000);
      cachedDateStr = `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
      cachedDayStart = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()) / 1000;
      cachedDayEnd = cachedDayStart + 86400;
    }

    if (!groups[cachedDateStr]) {
      groups[cachedDateStr] = { timestamps: [], axisY: [], vectorMagnitude: [], ...(hasExtra ? { choiAxis: [] } : {}) };
    }
    const g = groups[cachedDateStr]!;
    g.timestamps.push(ts);
    g.axisY.push(axisY[i]!);
    g.vectorMagnitude.push(vectorMagnitude[i]!);
    if (hasExtra) g.choiAxis!.push(extraArray[i]!);
  }

  return groups;
}
