import { describe, it, expect, beforeEach, mock } from "bun:test";
import {
  isPrivateAddress,
  parsePeerMarkers,
  pullMarkersFromPeer,
  pullAllPeerMarkers,
  verifyPeerGroup,
  pullStudySettingsFromPeer,
} from "./peer-sync";
import type { PeerMarker, PeerInfo } from "./peer-sync";

describe("isPrivateAddress", () => {
  it("accepts 10.x.x.x addresses", () => {
    expect(isPrivateAddress("http://10.0.0.1:3000")).toBe(true);
  });

  it("accepts 192.168.x.x addresses", () => {
    expect(isPrivateAddress("http://192.168.1.100:8080")).toBe(true);
  });

  it("accepts 172.16-31.x.x addresses", () => {
    expect(isPrivateAddress("http://172.16.0.1:3000")).toBe(true);
    expect(isPrivateAddress("http://172.31.255.255:3000")).toBe(true);
  });

  it("accepts 127.x.x.x (loopback)", () => {
    expect(isPrivateAddress("http://127.0.0.1:3000")).toBe(true);
  });

  it("accepts fe80 (link-local IPv6)", () => {
    expect(isPrivateAddress("http://fe80::1")).toBe(true);
  });

  it("rejects public IP addresses", () => {
    expect(isPrivateAddress("http://8.8.8.8:3000")).toBe(false);
    expect(isPrivateAddress("http://203.0.113.1:3000")).toBe(false);
  });

  it("rejects domain names", () => {
    expect(isPrivateAddress("http://example.com:3000")).toBe(false);
  });

  it("rejects https public addresses", () => {
    // The pattern only matches http://
    expect(isPrivateAddress("https://10.0.0.1:3000")).toBe(false);
  });
});

describe("parsePeerMarkers", () => {
  it("parses valid sleep and nonwear markers", () => {
    const raw: PeerMarker = {
      username: "alice",
      sleep_markers: JSON.stringify([
        { onsetTimestamp: 1000, offsetTimestamp: 2000, markerIndex: 0, markerType: "MAIN_SLEEP" },
      ]),
      nonwear_markers: JSON.stringify([
        { startTimestamp: 3000, endTimestamp: 4000, markerIndex: 0 },
      ]),
      is_no_sleep: false,
      notes: "",
      content_hash: "abc",
    };

    const { sleepMarkers, nonwearMarkers } = parsePeerMarkers(raw);
    expect(sleepMarkers).toHaveLength(1);
    expect(sleepMarkers[0]!.onsetTimestamp).toBe(1000);
    expect(nonwearMarkers).toHaveLength(1);
    expect(nonwearMarkers[0]!.startTimestamp).toBe(3000);
  });

  it("returns empty arrays for invalid JSON", () => {
    const raw: PeerMarker = {
      username: "bob",
      sleep_markers: "not-json",
      nonwear_markers: "{broken",
      is_no_sleep: false,
      notes: "",
      content_hash: "def",
    };

    const { sleepMarkers, nonwearMarkers } = parsePeerMarkers(raw);
    expect(sleepMarkers).toEqual([]);
    expect(nonwearMarkers).toEqual([]);
  });

  it("handles empty JSON arrays", () => {
    const raw: PeerMarker = {
      username: "carol",
      sleep_markers: "[]",
      nonwear_markers: "[]",
      is_no_sleep: true,
      notes: "no sleep",
      content_hash: "ghi",
    };

    const { sleepMarkers, nonwearMarkers } = parsePeerMarkers(raw);
    expect(sleepMarkers).toEqual([]);
    expect(nonwearMarkers).toEqual([]);
  });
});

describe("pullMarkersFromPeer", () => {
  beforeEach(() => {
    globalThis.fetch = mock(() =>
      Promise.resolve(new Response(JSON.stringify({ markers: [] }), { status: 200 }))
    ) as typeof fetch;
  });

  it("returns empty array for non-private address", async () => {
    const result = await pullMarkersFromPeer("http://8.8.8.8:3000", "hash", "2024-01-01", "group");
    expect(result).toEqual([]);
  });

  it("fetches markers from a private address", async () => {
    const markers = [{ username: "alice", sleep_markers: "[]", nonwear_markers: "[]", is_no_sleep: false, notes: "", content_hash: "a" }];
    globalThis.fetch = mock(() =>
      Promise.resolve(new Response(JSON.stringify({ markers }), { status: 200 }))
    ) as typeof fetch;

    const result = await pullMarkersFromPeer("http://192.168.1.1:3000", "hash", "2024-01-01", "group");
    expect(result).toHaveLength(1);
    expect(result[0]!.username).toBe("alice");
  });

  it("returns empty array on HTTP error", async () => {
    globalThis.fetch = mock(() =>
      Promise.resolve(new Response("", { status: 500 }))
    ) as typeof fetch;

    const result = await pullMarkersFromPeer("http://192.168.1.1:3000", "hash", "2024-01-01", "group");
    expect(result).toEqual([]);
  });

  it("returns empty array on network error", async () => {
    globalThis.fetch = mock(() => Promise.reject(new Error("network down"))) as typeof fetch;

    const result = await pullMarkersFromPeer("http://192.168.1.1:3000", "hash", "2024-01-01", "group");
    expect(result).toEqual([]);
  });
});

describe("pullAllPeerMarkers", () => {
  it("skips own markers", async () => {
    const markers: PeerMarker[] = [
      { username: "alice", sleep_markers: "[]", nonwear_markers: "[]", is_no_sleep: false, notes: "", content_hash: "a" },
    ];
    globalThis.fetch = mock(() =>
      Promise.resolve(new Response(JSON.stringify({ markers }), { status: 200 }))
    ) as typeof fetch;

    const peers: PeerInfo[] = [{ username: "alice", address: "http://192.168.1.1:3000", instance_id: "i1" }];
    const result = await pullAllPeerMarkers(peers, "hash", "2024-01-01", "group", "alice", async () => null);
    expect(result.imported).toHaveLength(0);
  });

  it("skips markers with matching content hash", async () => {
    const markers: PeerMarker[] = [
      { username: "bob", sleep_markers: "[]", nonwear_markers: "[]", is_no_sleep: false, notes: "", content_hash: "existing-hash" },
    ];
    globalThis.fetch = mock(() =>
      Promise.resolve(new Response(JSON.stringify({ markers }), { status: 200 }))
    ) as typeof fetch;

    const peers: PeerInfo[] = [{ username: "bob", address: "http://192.168.1.2:3000", instance_id: "i2" }];
    const result = await pullAllPeerMarkers(
      peers, "hash", "2024-01-01", "group", "alice",
      async () => "existing-hash",
    );
    expect(result.imported).toHaveLength(0);
    expect(result.skipped).toBe(1);
  });

  it("imports new markers from peers", async () => {
    const markers: PeerMarker[] = [
      { username: "bob", sleep_markers: "[]", nonwear_markers: "[]", is_no_sleep: false, notes: "", content_hash: "new-hash" },
    ];
    globalThis.fetch = mock(() =>
      Promise.resolve(new Response(JSON.stringify({ markers }), { status: 200 }))
    ) as typeof fetch;

    const peers: PeerInfo[] = [{ username: "bob", address: "http://192.168.1.2:3000", instance_id: "i2" }];
    const result = await pullAllPeerMarkers(
      peers, "hash", "2024-01-01", "group", "alice",
      async () => null,
    );
    expect(result.imported).toHaveLength(1);
    expect(result.imported[0]!.username).toBe("bob");
  });
});

describe("verifyPeerGroup", () => {
  it("returns false for non-private address", async () => {
    const result = await verifyPeerGroup("http://8.8.8.8:3000", "group");
    expect(result).toBe(false);
  });

  it("returns true on 200 OK", async () => {
    globalThis.fetch = mock(() =>
      Promise.resolve(new Response("", { status: 200 }))
    ) as typeof fetch;

    const result = await verifyPeerGroup("http://192.168.1.1:3000", "group");
    expect(result).toBe(true);
  });

  it("returns false on non-OK response", async () => {
    globalThis.fetch = mock(() =>
      Promise.resolve(new Response("", { status: 403 }))
    ) as typeof fetch;

    const result = await verifyPeerGroup("http://192.168.1.1:3000", "group");
    expect(result).toBe(false);
  });

  it("returns false on network error", async () => {
    globalThis.fetch = mock(() => Promise.reject(new Error("timeout"))) as typeof fetch;

    const result = await verifyPeerGroup("http://192.168.1.1:3000", "group");
    expect(result).toBe(false);
  });
});

describe("pullStudySettingsFromPeer", () => {
  it("returns null for non-private address", async () => {
    const result = await pullStudySettingsFromPeer("http://8.8.8.8:3000", "group");
    expect(result).toBeNull();
  });

  it("returns settings on success", async () => {
    const settings = { value_json: "{}", content_hash: "abc", updated_at: "2024-01-01T00:00:00Z" };
    globalThis.fetch = mock(() =>
      Promise.resolve(new Response(JSON.stringify({ settings }), { status: 200 }))
    ) as typeof fetch;

    const result = await pullStudySettingsFromPeer("http://192.168.1.1:3000", "group");
    expect(result).toBeDefined();
    expect(result!.content_hash).toBe("abc");
  });

  it("returns null on HTTP error", async () => {
    globalThis.fetch = mock(() =>
      Promise.resolve(new Response("", { status: 500 }))
    ) as typeof fetch;

    const result = await pullStudySettingsFromPeer("http://192.168.1.1:3000", "group");
    expect(result).toBeNull();
  });

  it("returns null on network error", async () => {
    globalThis.fetch = mock(() => Promise.reject(new Error("network"))) as typeof fetch;

    const result = await pullStudySettingsFromPeer("http://192.168.1.1:3000", "group");
    expect(result).toBeNull();
  });
});
