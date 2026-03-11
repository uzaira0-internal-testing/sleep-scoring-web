import type { SleepMarkerJson, NonwearMarkerJson } from "@/db/schema";

export function toHex(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let hex = "";
  for (let i = 0; i < bytes.length; i++) {
    hex += bytes[i]!.toString(16).padStart(2, "0");
  }
  return hex;
}

/** Compute the SHA-256 hex digest of a string. */
export async function sha256Hex(input: string): Promise<string> {
  const buffer = new TextEncoder().encode(input);
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  return toHex(hashBuffer);
}

/**
 * Compute SHA-256 content hash for marker data.
 * Same marker set = same hash regardless of when/where created.
 *
 * NOTE: Metadata flags like `needsConsensus` are intentionally excluded from
 * the hash. They must be compared separately at all sync decision points
 * (see sync.ts pullMarkers).
 */
export async function computeMarkerHash(data: {
  sleepMarkers: SleepMarkerJson[];
  nonwearMarkers: SleepMarkerJson[] | NonwearMarkerJson[];
  isNoSleep: boolean;
  notes: string;
}): Promise<string> {
  // Deterministic: sort top-level keys AND sort arrays by markerIndex
  const sorted: Record<string, unknown> = {};
  for (const key of Object.keys(data).sort()) {
    const val = data[key as keyof typeof data];
    if (Array.isArray(val)) {
      sorted[key] = [...val].sort((a, b) => {
        const ar = a as unknown as Record<string, unknown>;
        const br = b as unknown as Record<string, unknown>;
        const idxDiff = ((ar.markerIndex as number) ?? 0) - ((br.markerIndex as number) ?? 0);
        if (idxDiff !== 0) return idxDiff;
        // Tiebreaker: first timestamp field found (onsetTimestamp or startTimestamp)
        const at = (ar.onsetTimestamp ?? ar.startTimestamp ?? 0) as number;
        const bt = (br.onsetTimestamp ?? br.startTimestamp ?? 0) as number;
        return at - bt;
      });
    } else {
      sorted[key] = val;
    }
  }
  const canonical = JSON.stringify(sorted);
  return sha256Hex(canonical);
}

/**
 * Compute SHA-256 hash of the first 64KB of a file for dedup.
 */
export async function computeFileHash(file: File): Promise<string> {
  const slice = file.slice(0, 65536);
  const buffer = await slice.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  return toHex(hashBuffer);
}
