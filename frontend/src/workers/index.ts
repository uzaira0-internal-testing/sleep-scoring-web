import { wrap, type Remote } from "comlink";
import type { WasmWorkerApi } from "./wasm-worker";

let _worker: Worker | null = null;
let _api: Remote<WasmWorkerApi> | null = null;

/**
 * Get the WASM worker API (lazy-initialized singleton).
 * Uses Comlink for type-safe RPC.
 */
export function getWasmApi(): Remote<WasmWorkerApi> {
  if (!_api) {
    _worker = new Worker(new URL("./wasm-worker.ts", import.meta.url), {
      type: "module",
    });
    _api = wrap<WasmWorkerApi>(_worker);
  }
  return _api;
}

/**
 * Terminate the WASM worker (for cleanup).
 */
export function terminateWasmWorker(): void {
  if (_worker) {
    _worker.terminate();
    _worker = null;
    _api = null;
  }
}

// Clean up worker on page unload to prevent memory leaks
if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", () => terminateWasmWorker());
}
