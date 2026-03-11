/// <reference types="vite/client" />

// CSS modules
declare module "*.css" {
  const css: string;
  export default css;
}

// WASM package (built by wasm-pack, gitignored)
declare module "@/wasm/pkg/sleep_scoring_wasm" {
  export default function init(): Promise<void>;
  export function scoreSadeh(activity: Float64Array, threshold: number): Uint8Array;
  export function scoreColeKripke(activity: Float64Array, useActilifeScaling: boolean): Uint8Array;
  export function detectNonwear(counts: Float64Array): Uint8Array;
  export function parseActigraphCsv(content: string, skipRows: number): unknown;
  export function parseGeneactivCsv(content: string): unknown;
  export function isGeneactivFormat(content: string): boolean;
  export function epochRawData(
    timestampsMs: Float64Array,
    axisX: Float64Array,
    axisY: Float64Array,
    axisZ: Float64Array,
    sampleFreq: number,
  ): unknown;
}
