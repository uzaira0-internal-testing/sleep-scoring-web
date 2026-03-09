import * as Comlink from "comlink";

// Lazy-init WASM module
let wasmModule: typeof import("@/wasm/pkg/sleep_scoring_wasm") | null = null;

async function ensureWasm() {
  if (!wasmModule) {
    const mod = await import("@/wasm/pkg/sleep_scoring_wasm");
    await mod.default();
    wasmModule = mod;
  }
  return wasmModule;
}

const workerApi = {
  /**
   * Score activity data using Sadeh (1994) algorithm.
   */
  async scoreSadeh(activity: Float64Array, threshold: number): Promise<Uint8Array> {
    const wasm = await ensureWasm();
    const result = new Uint8Array(wasm.scoreSadeh(activity, threshold));
    return Comlink.transfer(result, [result.buffer]);
  },

  /**
   * Score activity data using Cole-Kripke (1992) algorithm.
   */
  async scoreColeKripke(activity: Float64Array, useActilifeScaling: boolean): Promise<Uint8Array> {
    const wasm = await ensureWasm();
    const result = new Uint8Array(wasm.scoreColeKripke(activity, useActilifeScaling));
    return Comlink.transfer(result, [result.buffer]);
  },

  /**
   * Detect nonwear periods using Choi (2011) algorithm.
   */
  async detectNonwear(counts: Float64Array): Promise<Uint8Array> {
    const wasm = await ensureWasm();
    const result = new Uint8Array(wasm.detectNonwear(counts));
    return Comlink.transfer(result, [result.buffer]);
  },

  /**
   * Parse an ActiGraph-style CSV file.
   */
  async parseActigraphCsv(content: string, skipRows: number) {
    const wasm = await ensureWasm();
    return wasm.parseActigraphCsv(content, skipRows);
  },

  /**
   * Parse a GENEActiv CSV file.
   */
  async parseGeneactivCsv(content: string) {
    const wasm = await ensureWasm();
    return wasm.parseGeneactivCsv(content);
  },

  /**
   * Check if CSV content is GENEActiv format.
   */
  async isGeneactivFormat(content: string): Promise<boolean> {
    const wasm = await ensureWasm();
    return wasm.isGeneactivFormat(content);
  },

  /**
   * Epoch raw high-frequency data to 60-second counts.
   */
  async epochRawData(
    timestampsMs: Float64Array,
    axisX: Float64Array,
    axisY: Float64Array,
    axisZ: Float64Array,
    sampleFreq: number,
  ) {
    const wasm = await ensureWasm();
    return wasm.epochRawData(timestampsMs, axisX, axisY, axisZ, sampleFreq);
  },
};

export type WasmWorkerApi = typeof workerApi;

Comlink.expose(workerApi);
