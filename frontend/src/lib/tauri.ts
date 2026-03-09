/**
 * Tauri detection and helpers.
 *
 * All Tauri-specific code is gated behind `isTauri()` so the web app
 * continues to work unchanged in the browser.
 */
import { sha256Hex } from "@/lib/content-hash";

/** Returns true when running inside a Tauri WebView. */
export function isTauri(): boolean {
  return "__TAURI__" in window;
}

/** Compute the full 64-char SHA-256 hex hash for group hash namespacing. */
export async function computeGroupHash(sitePassword: string): Promise<string> {
  return sha256Hex(sitePassword);
}

/** Configure the Tauri backend with group hash + username after login. */
export async function setTauriGroupConfig(groupHash: string, username: string): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("set_group_config", { groupHash, username });
}

/** Switch the Tauri backend to a workspace-scoped SQLite database. */
export async function switchTauriWorkspace(workspaceId: string): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("switch_workspace", { workspaceId });
}

/** Delete a workspace's SQLite database from the Tauri backend. */
export async function deleteTauriWorkspace(workspaceId: string): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("delete_workspace_db", { workspaceId });
}

/** Save markers to the local SQLite database via Tauri IPC. */
export async function saveMarkersToSqlite(params: {
  fileHash: string;
  date: string;
  username: string;
  sleepMarkers: string;
  nonwearMarkers: string;
  isNoSleep: boolean;
  notes: string;
  contentHash: string;
}): Promise<void> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("save_markers_to_sqlite", params);
}
