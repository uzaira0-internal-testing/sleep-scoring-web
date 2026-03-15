import { describe, it, expect, beforeEach } from "bun:test";
import { usePeerStore } from "./peer-store";
import type { PeerInfo } from "@/services/peer-sync";

describe("PeerStore", () => {
  beforeEach(() => {
    usePeerStore.setState({
      peers: [],
      isDiscovering: false,
      lastDiscoveryAt: null,
    });
  });

  describe("initial state", () => {
    it("has empty peers and not discovering", () => {
      const state = usePeerStore.getState();
      expect(state.peers).toEqual([]);
      expect(state.isDiscovering).toBe(false);
      expect(state.lastDiscoveryAt).toBeNull();
    });
  });

  describe("setPeers", () => {
    it("sets peers and updates lastDiscoveryAt", () => {
      const peers: PeerInfo[] = [
        { username: "alice", address: "http://192.168.1.1:3000", instance_id: "i1" },
        { username: "bob", address: "http://192.168.1.2:3000", instance_id: "i2" },
      ];

      usePeerStore.getState().setPeers(peers);

      const state = usePeerStore.getState();
      expect(state.peers).toHaveLength(2);
      expect(state.peers[0]!.username).toBe("alice");
      expect(state.peers[1]!.username).toBe("bob");
      expect(state.lastDiscoveryAt).toBeTruthy();
    });

    it("replaces existing peers", () => {
      usePeerStore.getState().setPeers([
        { username: "alice", address: "http://192.168.1.1:3000", instance_id: "i1" },
      ]);

      usePeerStore.getState().setPeers([
        { username: "bob", address: "http://192.168.1.2:3000", instance_id: "i2" },
      ]);

      expect(usePeerStore.getState().peers).toHaveLength(1);
      expect(usePeerStore.getState().peers[0]!.username).toBe("bob");
    });

    it("can set empty peers array", () => {
      usePeerStore.getState().setPeers([
        { username: "alice", address: "http://192.168.1.1:3000", instance_id: "i1" },
      ]);

      usePeerStore.getState().setPeers([]);
      expect(usePeerStore.getState().peers).toEqual([]);
    });
  });

  describe("setDiscovering", () => {
    it("sets discovering to true", () => {
      usePeerStore.getState().setDiscovering(true);
      expect(usePeerStore.getState().isDiscovering).toBe(true);
    });

    it("sets discovering to false", () => {
      usePeerStore.getState().setDiscovering(true);
      usePeerStore.getState().setDiscovering(false);
      expect(usePeerStore.getState().isDiscovering).toBe(false);
    });
  });
});
