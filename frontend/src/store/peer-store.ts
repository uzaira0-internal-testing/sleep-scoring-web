import { create } from "zustand";
import type { PeerInfo } from "@/services/peer-sync";

interface PeerState {
  peers: PeerInfo[];
  isDiscovering: boolean;
  lastDiscoveryAt: string | null;
  setPeers: (peers: PeerInfo[]) => void;
  setDiscovering: (v: boolean) => void;
}

export const usePeerStore = create<PeerState>((set) => ({
  peers: [],
  isDiscovering: false,
  lastDiscoveryAt: null,
  setPeers: (peers) =>
    set({ peers, lastDiscoveryAt: new Date().toISOString() }),
  setDiscovering: (isDiscovering) => set({ isDiscovering }),
}));
