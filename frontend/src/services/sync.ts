import { getApiBase } from "@/api/client";
import * as localDb from "@/db";
import { getDb } from "@/lib/workspace-db";
import { computeMarkerHash } from "@/lib/content-hash";
import { toSeconds, toMilliseconds } from "@/utils/timestamps";
import type { MarkerType } from "@/api/types";

export interface SyncResult {
  pushed: number;
  pulled: number;
  conflicts: number;
  errors: string[];
}

/**
 * Push pending local markers to server.
 */
async function pushMarkers(
  sitePassword: string | null,
): Promise<{ pushed: number; errors: string[] }> {
  const pending = await localDb.getPendingMarkers();
  let pushed = 0;
  const errors: string[] = [];

  // Pre-fetch all needed file records to avoid N+1 reads
  const fileIds = [...new Set(pending.map((m) => m.fileId))];
  const fileMap = new Map<number, localDb.FileRecord>();
  for (const id of fileIds) {
    const f = await localDb.getFileById(id);
    if (f) fileMap.set(id, f);
  }

  for (const marker of pending) {
    const file = fileMap.get(marker.fileId);
    if (!file?.serverFileId) {
      // File only exists locally — can't push to server
      continue;
    }

    const payload = {
      sleep_markers: marker.sleepMarkers.map((m) => ({
        onset_timestamp: toSeconds(m.onsetTimestamp),
        offset_timestamp: toSeconds(m.offsetTimestamp),
        marker_index: m.markerIndex,
        marker_type: m.markerType,
      })),
      nonwear_markers: marker.nonwearMarkers.map((m) => ({
        start_timestamp: toSeconds(m.startTimestamp),
        end_timestamp: toSeconds(m.endTimestamp),
        marker_index: m.markerIndex,
      })),
      is_no_sleep: marker.isNoSleep,
      notes: marker.notes,
    };

    try {
      const response = await fetch(
        `${getApiBase()}/markers/${file.serverFileId}/${marker.date}`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            ...(sitePassword ? { "X-Site-Password": sitePassword } : {}),
            "X-Username": marker.username || "anonymous",
          },
          body: JSON.stringify(payload),
        },
      );

      if (response.ok) {
        await localDb.markSynced(marker.id!);
        pushed++;
      } else if (response.status === 409) {
        await localDb.markConflict(marker.id!);
      } else {
        errors.push(`Push failed for ${marker.date}: ${response.status}`);
      }
    } catch (err) {
      errors.push(`Push error for ${marker.date}: ${err}`);
    }
  }

  return { pushed, errors };
}

/**
 * Pull remote markers for files that exist both locally and on server.
 */
async function pullMarkers(
  sitePassword: string | null,
  username: string,
): Promise<{ pulled: number; errors: string[] }> {
  const localFiles = await localDb.getLocalFiles();
  let pulled = 0;
  const errors: string[] = [];

  for (const file of localFiles) {
    if (!file.serverFileId) continue;

    for (const date of file.availableDates) {
      try {
        // Check if local has pending changes — skip pull (local wins)
        const localMarker = await localDb.getMarkers(file.id!, date, username);
        if (localMarker?.syncStatus === "pending") continue;

        const response = await fetch(
          `${getApiBase()}/markers/${file.serverFileId}/${date}`,
          {
            headers: {
              ...(sitePassword ? { "X-Site-Password": sitePassword } : {}),
              "X-Username": username || "anonymous",
            },
          },
        );

        if (response.status === 404) continue;
        if (!response.ok) {
          errors.push(`Pull failed for ${date}: ${response.status}`);
          continue;
        }

        const data = await response.json();

        const sleepMarkers = (data.sleep_markers ?? []).map((m: Record<string, unknown>) => ({
          onsetTimestamp: toMilliseconds(m.onset_timestamp as number | null),
          offsetTimestamp: toMilliseconds(m.offset_timestamp as number | null),
          markerIndex: m.marker_index as number,
          markerType: m.marker_type as MarkerType,
        }));

        const nonwearMarkers = (data.nonwear_markers ?? []).map((m: Record<string, unknown>) => ({
          startTimestamp: toMilliseconds(m.start_timestamp as number | null),
          endTimestamp: toMilliseconds(m.end_timestamp as number | null),
          markerIndex: m.marker_index as number,
        }));

        const remoteHash = await computeMarkerHash({
          sleepMarkers,
          nonwearMarkers,
          isNoSleep: data.is_no_sleep ?? false,
          notes: data.notes ?? "",
        });

        // Skip if content is the same
        if (localMarker?.contentHash === remoteHash) continue;

        // Atomic check+save: re-verify not pending inside transaction
        const db = getDb();
        const saved = await db.transaction("rw", db.markers, async () => {
          const current = await db.markers
            .where("[fileId+date+username]")
            .equals([file.id!, date, username])
            .first();
          // Re-check inside transaction — if became pending since our check, skip
          if (current?.syncStatus === "pending") return false;

          const contentHash = await computeMarkerHash({
            sleepMarkers,
            nonwearMarkers,
            isNoSleep: data.is_no_sleep ?? false,
            notes: data.notes ?? "",
          });

          const record = {
            fileId: file.id!,
            date,
            username,
            sleepMarkers,
            nonwearMarkers,
            isNoSleep: data.is_no_sleep ?? false,
            notes: data.notes ?? "",
            contentHash,
            syncStatus: "synced" as const,
            lastModifiedAt: new Date().toISOString(),
          };

          if (current?.id) {
            await db.markers.update(current.id, record);
          } else {
            await db.markers.add(record as localDb.MarkerRecord);
          }
          return true;
        });
        if (saved) pulled++;
      } catch (err) {
        errors.push(`Pull error for ${date}: ${err}`);
      }
    }
  }

  return { pulled, errors };
}

/**
 * Full sync cycle: push pending, then pull updates.
 */
export async function syncAll(
  sitePassword: string | null,
  username: string,
): Promise<SyncResult> {
  const pushResult = await pushMarkers(sitePassword);
  const pullResult = await pullMarkers(sitePassword, username);

  const conflicts = await localDb.getConflictCount();

  return {
    pushed: pushResult.pushed,
    pulled: pullResult.pulled,
    conflicts,
    errors: [...pushResult.errors, ...pullResult.errors],
  };
}
