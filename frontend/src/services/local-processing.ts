import { getWasmApi, terminateWasmWorker } from "@/workers";
import { readFileAsText, type ChunkReadProgress } from "@/lib/chunked-reader";
import { computeFileHash } from "@/lib/content-hash";
import * as localDb from "@/db";

/** Result from WASM CSV parsing (matches Rust CsvParseResult via serde) */
interface CsvParseResult {
  timestamps_ms: number[];
  axis_y: number[];
  axis_x: number[];
  axis_z: number[];
  vector_magnitude: number[];
  is_raw: boolean;
  sample_frequency: number;
  header_rows_skipped: number;
}

/** Result from WASM epoching (matches Rust EpochResult via serde) */
interface EpochResult {
  timestamps_ms: number[];
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

  // Quick first-line check for GENEActiv format (avoids sending entire string to WASM)
  const firstLine = content.slice(0, content.indexOf("\n")).trim().toLowerCase();
  const isGeneactiv = firstLine.includes("geneactiv") || devicePreset === "geneactiv";

  let parseResult: CsvParseResult;
  if (isGeneactiv) {
    parseResult = await withTimeout(wasmApi.parseGeneactivCsv(content), WASM_TIMEOUT_MS, "parseGeneactivCsv") as CsvParseResult;
  } else {
    parseResult = await withTimeout(wasmApi.parseActigraphCsv(content, skipRows), WASM_TIMEOUT_MS, "parseActigraphCsv") as CsvParseResult;
  }

  let timestamps = parseResult.timestamps_ms;
  let axisY = parseResult.axis_y;
  let vectorMagnitude = parseResult.vector_magnitude;

  // Step 3: Epoch if raw data
  if (parseResult.is_raw && parseResult.sample_frequency > 0) {
    onProgress?.({ phase: "epoching", percent: 45, message: "Converting to epochs..." });
    const epochResult = await withTimeout(
      wasmApi.epochRawData(
        new Float64Array(timestamps),
        new Float64Array(parseResult.axis_x),
        new Float64Array(axisY),
        new Float64Array(parseResult.axis_z),
        parseResult.sample_frequency,
      ),
      WASM_TIMEOUT_MS,
      "epochRawData",
    ) as EpochResult;

    timestamps = epochResult.timestamps_ms;
    axisY = epochResult.axis_y;
    vectorMagnitude = epochResult.vector_magnitude;
  }

  // Step 4: Split into per-date arrays
  onProgress?.({ phase: "scoring", percent: 55, message: "Running sleep algorithms..." });
  const dateGroups = splitByDate(timestamps, axisY, vectorMagnitude);
  const availableDates = Object.keys(dateGroups).sort();

  // Step 5: Run algorithms on each day
  const algorithmResultsByDate: Record<string, { sadeh: Uint8Array; coleKripke: Uint8Array; nonwear: Uint8Array }> = {};

  for (let i = 0; i < availableDates.length; i++) {
    const date = availableDates[i];
    const group = dateGroups[date];
    const pct = 55 + (i / availableDates.length) * 30;

    onProgress?.({ phase: "scoring", percent: pct, message: `Scoring ${date}...` });

    const activityF64 = new Float64Array(group.axisY);
    const vmF64 = new Float64Array(group.vectorMagnitude);

    const [sadeh, coleKripke, nonwear] = await Promise.all([
      withTimeout(wasmApi.scoreSadeh(activityF64, -4.0), WASM_TIMEOUT_MS, `scoreSadeh(${date})`),
      withTimeout(wasmApi.scoreColeKripke(activityF64, true), WASM_TIMEOUT_MS, `scoreColeKripke(${date})`),
      withTimeout(wasmApi.detectNonwear(vmF64), WASM_TIMEOUT_MS, `detectNonwear(${date})`),
    ]);

    algorithmResultsByDate[date] = { sadeh, coleKripke, nonwear };
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
    const group = dateGroups[date];
    const algoResults = algorithmResultsByDate[date];

    await localDb.saveActivityDay({
      fileId,
      date,
      timestamps: new Float64Array(group.timestamps).buffer,
      axisY: new Float64Array(group.axisY).buffer,
      vectorMagnitude: new Float64Array(group.vectorMagnitude).buffer,
      algorithmResults: {
        sadeh_actilife: algoResults.sadeh.buffer.slice(0),
        cole_kripke_actilife: algoResults.coleKripke.buffer.slice(0),
      },
      nonwearResults: algoResults.nonwear.buffer.slice(0),
    });
  }

  onProgress?.({ phase: "complete", percent: 100, message: "Processing complete" });

  return { fileId, availableDates };
}

/**
 * Split epoch data into per-date groups.
 */
function splitByDate(
  timestamps: number[],
  axisY: number[],
  vectorMagnitude: number[],
): Record<string, { timestamps: number[]; axisY: number[]; vectorMagnitude: number[] }> {
  const groups: Record<string, { timestamps: number[]; axisY: number[]; vectorMagnitude: number[] }> = {};

  for (let i = 0; i < timestamps.length; i++) {
    const date = new Date(timestamps[i]);
    const dateStr = `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;

    if (!groups[dateStr]) {
      groups[dateStr] = { timestamps: [], axisY: [], vectorMagnitude: [] };
    }
    groups[dateStr].timestamps.push(timestamps[i]);
    groups[dateStr].axisY.push(axisY[i]);
    groups[dateStr].vectorMagnitude.push(vectorMagnitude[i]);
  }

  return groups;
}
