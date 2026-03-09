import { useState, useCallback } from "react";
import { Users, Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePeerStore } from "@/store/peer-store";
import { useSleepScoringStore } from "@/store";
import { pullAllPeerMarkers, parsePeerMarkers, type PeerMarker } from "@/services/peer-sync";
import { computeGroupHash, isTauri, saveMarkersToSqlite } from "@/lib/tauri";
import { getFileById } from "@/db";

interface ParsedPeerMarker extends PeerMarker {
  parsedSleepCount: number;
  parsedNonwearCount: number;
}

/**
 * Panel showing discovered LAN peers and their markers.
 * Only renders in Tauri mode.
 */
export function PeerMarkersPanel() {
  const peers = usePeerStore((s) => s.peers);
  const isDiscovering = usePeerStore((s) => s.isDiscovering);
  const [isPulling, setIsPulling] = useState(false);
  const [pullResult, setPullResult] = useState<{ imported: number; skipped: number } | null>(null);
  const [pullError, setPullError] = useState<string | null>(null);
  const [peerMarkers, setPeerMarkers] = useState<ParsedPeerMarker[]>([]);

  const handlePull = useCallback(async () => {
    const state = useSleepScoringStore.getState();
    const { currentFileId, availableDates, currentDateIndex, username, sitePassword } = state;
    const date = availableDates[currentDateIndex] ?? null;
    if (!currentFileId || !date || !sitePassword) return;

    const file = await getFileById(currentFileId);
    if (!file?.fileHash) return;

    setIsPulling(true);
    setPullResult(null);
    setPullError(null);
    try {
      const groupHash = await computeGroupHash(sitePassword);
      const result = await pullAllPeerMarkers(
        usePeerStore.getState().peers,
        file.fileHash,
        date,
        groupHash,
        username,
        async () => null, // TODO: look up existing content hash from Dexie
      );

      // Pre-parse marker counts once instead of on every render
      const parsed: ParsedPeerMarker[] = result.imported.map((m) => {
        const { sleepMarkers, nonwearMarkers } = parsePeerMarkers(m);
        return { ...m, parsedSleepCount: sleepMarkers.length, parsedNonwearCount: nonwearMarkers.length };
      });
      setPeerMarkers(parsed);
      setPullResult({ imported: result.imported.length, skipped: result.skipped });

      // Batch save imported markers to SQLite via Tauri IPC
      if (isTauri() && result.imported.length > 0) {
        let saveFailed = 0;
        const savePromises = result.imported.map((m) =>
          saveMarkersToSqlite({
            fileHash: file.fileHash,
            date,
            username: m.username,
            sleepMarkers: m.sleep_markers,
            nonwearMarkers: m.nonwear_markers,
            isNoSleep: m.is_no_sleep,
            notes: m.notes,
            contentHash: m.content_hash,
          }).catch((e) => {
            saveFailed++;
            console.error("Failed to save peer marker to SQLite:", e);
          })
        );
        await Promise.all(savePromises);
        if (saveFailed > 0) {
          setPullError(`${saveFailed} marker(s) failed to persist locally`);
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      console.error("Failed to pull peer markers:", msg);
      setPullError(`Failed to pull markers: ${msg}`);
    } finally {
      setIsPulling(false);
    }
  }, []);

  if (!isTauri()) return null;

  return (
    <div className="border-t border-border/60 p-3 space-y-2">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Users className="h-3.5 w-3.5" />
        <span>
          {isDiscovering ? "Scanning..." : `${peers.length} peer${peers.length !== 1 ? "s" : ""}`}
        </span>
      </div>

      {peers.length > 0 && (
        <>
          <div className="space-y-1">
            {peers.map((p) => (
              <div key={p.instance_id} className="text-xs flex items-center gap-1.5">
                <div className="h-1.5 w-1.5 rounded-full bg-green-500" />
                <span className="truncate">{p.username}</span>
              </div>
            ))}
          </div>

          <Button
            variant="outline"
            size="sm"
            className="w-full h-7 text-xs gap-1.5"
            onClick={handlePull}
            disabled={isPulling}
          >
            {isPulling ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Download className="h-3 w-3" />
            )}
            Pull from peers
          </Button>
        </>
      )}

      {pullResult && (
        <div className="text-xs text-muted-foreground">
          Imported {pullResult.imported}, skipped {pullResult.skipped}
        </div>
      )}

      {pullError && (
        <div className="text-xs text-destructive">
          {pullError}
        </div>
      )}

      {peerMarkers.length > 0 && (
        <div className="space-y-1 max-h-40 overflow-y-auto">
          {peerMarkers.map((m, i) => (
            <div key={`${m.username}-${i}`} className="text-xs p-1.5 rounded bg-muted/50">
              <span className="font-medium">{m.username}</span>
              <span className="text-muted-foreground ml-1">
                ({m.parsedSleepCount} sleep, {m.parsedNonwearCount} nonwear)
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
