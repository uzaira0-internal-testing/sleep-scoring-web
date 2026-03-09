/**
 * Capability detection for the three UI modes:
 * - Server: Backend reachable → uploads, server auth, server-side export/analysis
 * - WASM: Always true → local file processing, IndexedDB storage
 * - Tauri: Running in Tauri WebView → peer sync, SQLite dual-write, native dialogs
 *
 * These are NOT mutually exclusive — a Tauri app with a reachable server has all three.
 */

import { isTauri } from "@/lib/tauri";

export interface AppCapabilities {
  server: boolean;
  tauri: boolean;
  peerSync: boolean;
}

/** Build capabilities from current runtime state. */
export function buildCapabilities(serverAvailable: boolean, groupConfigured: boolean): AppCapabilities {
  const tauri = isTauri();
  return {
    server: serverAvailable,
    tauri,
    peerSync: tauri && groupConfigured,
  };
}
