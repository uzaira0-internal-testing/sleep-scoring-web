/**
 * Peer sync service for LAN marker sharing in Tauri mode.
 *
 * Uses Tauri IPC commands for mDNS discovery and direct HTTP
 * for pulling markers from peer axum servers.
 */
import { isTauri } from "@/lib/tauri";
import type { SleepMarkerJson, NonwearMarkerJson } from "@/db/schema";

export interface PeerInfo {
  username: string;
  address: string;
  instance_id: string;
}

export interface PeerMarker {
  username: string;
  sleep_markers: string;
  nonwear_markers: string;
  is_no_sleep: boolean;
  notes: string;
  content_hash: string;
}

interface MarkersResponse {
  markers: PeerMarker[];
}

const PRIVATE_IP_PATTERN = /^http:\/\/(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|169\.254\.|fe80:|fc|fd|\[fe80:|\[fc|\[fd)/i;

/** Validate that a peer address points to a private/link-local IP (not a public server). */
export function isPrivateAddress(address: string): boolean {
  return PRIVATE_IP_PATTERN.test(address);
}

/**
 * Discover peers on the LAN via Tauri IPC → mDNS.
 * Returns empty array when not running in Tauri.
 */
export async function discoverPeers(): Promise<PeerInfo[]> {
  if (!isTauri()) return [];
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<PeerInfo[]>("discover_peers");
}

/**
 * Pull markers from a single peer for a specific file + date.
 */
export async function pullMarkersFromPeer(
  peerAddress: string,
  fileHash: string,
  date: string,
  groupHash: string,
): Promise<PeerMarker[]> {
  if (!isPrivateAddress(peerAddress)) return [];
  try {
    const resp = await fetch(
      `${peerAddress}/api/peers/markers/${encodeURIComponent(fileHash)}/${encodeURIComponent(date)}`,
      {
        headers: { "X-Group-Hash": groupHash },
        signal: AbortSignal.timeout(5000),
      },
    );
    if (!resp.ok) {
      console.error(`Peer ${peerAddress} returned HTTP ${resp.status}`);
      return [];
    }
    const data: MarkersResponse = await resp.json();
    return data.markers ?? [];
  } catch (e) {
    console.error(`Failed to reach peer ${peerAddress}:`, e instanceof Error ? e.message : e);
    return [];
  }
}

/**
 * Parse peer marker JSON strings into typed arrays.
 */
export function parsePeerMarkers(raw: PeerMarker): {
  sleepMarkers: SleepMarkerJson[];
  nonwearMarkers: NonwearMarkerJson[];
} {
  let sleepMarkers: SleepMarkerJson[] = [];
  let nonwearMarkers: NonwearMarkerJson[] = [];
  try {
    sleepMarkers = JSON.parse(raw.sleep_markers);
  } catch (e) {
    console.warn(`Invalid sleep_markers JSON from ${raw.username}:`, e instanceof Error ? e.message : e);
  }
  try {
    nonwearMarkers = JSON.parse(raw.nonwear_markers);
  } catch (e) {
    console.warn(`Invalid nonwear_markers JSON from ${raw.username}:`, e instanceof Error ? e.message : e);
  }
  return { sleepMarkers, nonwearMarkers };
}

/**
 * Pull markers from all peers for a given file + date.
 * Skips own markers and markers that match existing content hashes.
 */
export async function pullAllPeerMarkers(
  peers: PeerInfo[],
  fileHash: string,
  date: string,
  groupHash: string,
  localUsername: string,
  getExistingContentHash: (username: string) => Promise<string | null>,
): Promise<{ imported: PeerMarker[]; skipped: number }> {
  // Fetch from all peers concurrently
  const results = await Promise.allSettled(
    peers.map((peer) => pullMarkersFromPeer(peer.address, fileHash, date, groupHash)),
  );

  const imported: PeerMarker[] = [];
  let skipped = 0;

  for (const result of results) {
    if (result.status !== "fulfilled") continue;
    for (const m of result.value) {
      if (m.username === localUsername) continue;

      const existingHash = await getExistingContentHash(m.username);
      if (existingHash === m.content_hash) {
        skipped++;
        continue;
      }

      imported.push(m);
    }
  }

  return { imported, skipped };
}

/**
 * Verify a peer belongs to our group by probing its health endpoint.
 * Returns true if the peer responds 200 with matching group hash.
 */
export async function verifyPeerGroup(peerAddress: string, groupHash: string): Promise<boolean> {
  if (!isPrivateAddress(peerAddress)) return false;
  try {
    const resp = await fetch(`${peerAddress}/api/peers/health`, {
      headers: { "X-Group-Hash": groupHash },
      signal: AbortSignal.timeout(3000),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

export interface PeerStudySettings {
  value_json: string;
  content_hash: string;
  updated_at: string;
}

/**
 * Pull study settings from a peer.
 * Returns null if the peer has no settings or request fails.
 */
export async function pullStudySettingsFromPeer(
  peerAddress: string,
  groupHash: string,
): Promise<PeerStudySettings | null> {
  if (!isPrivateAddress(peerAddress)) return null;
  try {
    const resp = await fetch(`${peerAddress}/api/peers/study-settings`, {
      headers: { "X-Group-Hash": groupHash },
      signal: AbortSignal.timeout(5000),
    });
    if (!resp.ok) {
      console.error(`Peer ${peerAddress} study-settings returned HTTP ${resp.status}`);
      return null;
    }
    const data: { settings: PeerStudySettings | null } = await resp.json();
    return data.settings;
  } catch (e) {
    console.error(`Failed to pull study settings from peer ${peerAddress}:`, e instanceof Error ? e.message : e);
    return null;
  }
}
