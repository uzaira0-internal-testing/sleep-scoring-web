import { useEffect, useRef } from "react";
import { isTauri, computeGroupHash } from "@/lib/tauri";
import { discoverPeers, verifyPeerGroup } from "@/services/peer-sync";
import { usePeerStore } from "@/store/peer-store";
import { useSleepScoringStore } from "@/store";

const DISCOVERY_INTERVAL = 15_000;

/**
 * Polls for LAN peers via mDNS every 15 seconds (Tauri mode only).
 * Verifies each peer belongs to our group via the health endpoint.
 * Caches the group hash and verified peer set to avoid redundant work.
 * No-op in the web browser.
 */
export function usePeerDiscovery(): void {
  const setPeers = usePeerStore((s) => s.setPeers);
  const setDiscovering = usePeerStore((s) => s.setDiscovering);

  // Cache group hash — only recompute when sitePassword changes
  const groupHashCache = useRef<{ password: string; hash: string } | null>(null);
  // Cache verified peer instance_ids to skip re-verification
  const verifiedIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!isTauri()) return;

    let cancelled = false;

    const discover = async () => {
      setDiscovering(true);
      try {
        const rawPeers = await discoverPeers();
        if (cancelled) return;

        const sitePassword = useSleepScoringStore.getState().sitePassword;
        if (!sitePassword) {
          if (!cancelled) setPeers(rawPeers);
          return;
        }

        // Reuse cached group hash if password hasn't changed
        let groupHash: string;
        if (groupHashCache.current?.password === sitePassword) {
          groupHash = groupHashCache.current.hash;
        } else {
          groupHash = await computeGroupHash(sitePassword);
          groupHashCache.current = { password: sitePassword, hash: groupHash };
        }

        // Only verify peers we haven't already verified
        const verified = await Promise.all(
          rawPeers.map(async (peer) => {
            if (verifiedIds.current.has(peer.instance_id)) return peer;
            const ok = await verifyPeerGroup(peer.address, groupHash);
            if (ok) verifiedIds.current.add(peer.instance_id);
            return ok ? peer : null;
          }),
        );

        // Prune cache of peers no longer present
        const currentIds = new Set(rawPeers.map((p) => p.instance_id));
        for (const id of verifiedIds.current) {
          if (!currentIds.has(id)) verifiedIds.current.delete(id);
        }

        if (!cancelled) setPeers(verified.filter((p): p is NonNullable<typeof p> => p !== null));
      } catch (e) {
        console.error("Peer discovery failed:", e instanceof Error ? e.message : e);
      } finally {
        if (!cancelled) setDiscovering(false);
      }
    };

    discover();
    const interval = setInterval(discover, DISCOVERY_INTERVAL);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [setPeers, setDiscovering]);
}
