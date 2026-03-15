/**
 * Tests for data-source.ts — getDataSource factory, ServerDataSource URL
 * construction, and internal helper functions.
 *
 * Uses Bun's built-in test runner. Avoids browser-only APIs (IndexedDB, DOM).
 */

import { describe, it, expect, beforeEach, mock } from "bun:test";
import {
  getDataSource,
  ServerDataSource,
  LocalDataSource,
} from "./data-source";

// ---------------------------------------------------------------------------
// Module-level mocks
// ---------------------------------------------------------------------------

// Mock @/api/client — getApiBase returns a fixed URL, fetchWithAuth is a stub.
mock.module("@/api/client", () => ({
  getApiBase: () => "http://localhost:8500/api/v1",
  fetchWithAuth: mock(() => Promise.resolve({})),
}));

// Mock @/db — LocalDataSource calls into IndexedDB; not under test here.
mock.module("@/db", () => ({}));

// Note: We intentionally do NOT mock @/services/marker-placement,
// @/services/complexity, or @/constants/options here. Bun's mock.module
// contaminates globally and breaks tests in those modules. Instead, we
// only mock what ServerDataSource actually uses (fetch, @/api/client, @/db).

// ---------------------------------------------------------------------------
// Helpers to capture fetch calls
// ---------------------------------------------------------------------------

let fetchCalls: Array<{ url: string; init?: RequestInit }> = [];

function installFetchMock(response: unknown = {}, status = 200): void {
  fetchCalls = [];
  globalThis.fetch = mock((url: string | URL | Request, init?: RequestInit) => {
    fetchCalls.push({ url: String(url), init });
    return Promise.resolve(
      new Response(JSON.stringify(response), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    );
  }) as typeof fetch;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("getDataSource factory", () => {
  it("returns LocalDataSource for source='local'", () => {
    const ds = getDataSource("local", null, "alice");
    expect(ds).toBeInstanceOf(LocalDataSource);
  });

  it("returns ServerDataSource for source='server'", () => {
    const ds = getDataSource("server", "s3cret", "bob");
    expect(ds).toBeInstanceOf(ServerDataSource);
  });

  it("returns ServerDataSource with null password", () => {
    const ds = getDataSource("server", null, "anon");
    expect(ds).toBeInstanceOf(ServerDataSource);
  });
});

describe("ServerDataSource", () => {
  beforeEach(() => {
    installFetchMock();
  });

  describe("getHeaders (tested via loadMarkers)", () => {
    it("includes X-Site-Password when sitePassword is set", async () => {
      const ds = new ServerDataSource("my-pass", "alice");
      installFetchMock({ sleep_markers: [], nonwear_markers: [] });

      await ds.loadMarkers(1, "2024-06-01", "alice");

      expect(fetchCalls).toHaveLength(1);
      const headers = fetchCalls[0]!.init?.headers as Record<string, string>;
      expect(headers["X-Site-Password"]).toBe("my-pass");
      expect(headers["X-Username"]).toBe("alice");
    });

    it("omits X-Site-Password when sitePassword is null", async () => {
      const ds = new ServerDataSource(null, "bob");
      installFetchMock({ sleep_markers: [], nonwear_markers: [] });

      await ds.loadMarkers(1, "2024-06-01", "bob");

      const headers = fetchCalls[0]!.init?.headers as Record<string, string>;
      expect(headers["X-Site-Password"]).toBeUndefined();
      expect(headers["X-Username"]).toBe("bob");
    });
  });

  describe("loadActivityData URL construction", () => {
    it("builds correct URL with algorithm and viewHours", async () => {
      const ds = new ServerDataSource("pw", "user1");
      installFetchMock({ data: { timestamps: [], axis_x: [], axis_y: [], axis_z: [], vector_magnitude: [] } });

      await ds.loadActivityData(42, "2024-03-10", {
        algorithm: "sadeh_1994_actilife",
        viewHours: 48,
      });

      expect(fetchCalls).toHaveLength(1);
      const url = fetchCalls[0]!.url;
      expect(url).toContain("/activity/42/2024-03-10/score");
      expect(url).toContain("view_hours=48");
      expect(url).toContain("algorithm=sadeh_1994_actilife");
      expect(url).toContain("fields=available_dates");
    });

    it("builds URL without optional params when not provided", async () => {
      const ds = new ServerDataSource(null, "user1");
      installFetchMock({ data: { timestamps: [], axis_x: [], axis_y: [], axis_z: [], vector_magnitude: [] } });

      await ds.loadActivityData(7, "2024-01-15");

      const url = fetchCalls[0]!.url;
      expect(url).toContain("/activity/7/2024-01-15/score");
      expect(url).not.toContain("view_hours");
      expect(url).not.toContain("algorithm=");
      // fields=available_dates is always present
      expect(url).toContain("fields=available_dates");
    });
  });

  describe("loadMarkers URL and response mapping", () => {
    it("constructs correct URL and maps snake_case to camelCase", async () => {
      const ds = new ServerDataSource("pw", "scorer");
      installFetchMock({
        sleep_markers: [
          { onset_timestamp: 1000, offset_timestamp: 2000, marker_index: 0, marker_type: "MAIN_SLEEP" },
        ],
        nonwear_markers: [
          { start_timestamp: 3000, end_timestamp: 4000, marker_index: 0 },
        ],
        is_no_sleep: false,
        needs_consensus: true,
        notes: "test note",
      });

      const result = await ds.loadMarkers(5, "2024-02-20", "scorer");

      // URL check
      expect(fetchCalls[0]!.url).toBe("http://localhost:8500/api/v1/markers/5/2024-02-20");

      // Response mapping
      expect(result).not.toBeNull();
      expect(result!.sleepMarkers).toHaveLength(1);
      expect(result!.sleepMarkers[0]!.onsetTimestamp).toBe(1000);
      expect(result!.sleepMarkers[0]!.offsetTimestamp).toBe(2000);
      expect(result!.sleepMarkers[0]!.markerType).toBe("MAIN_SLEEP");
      expect(result!.nonwearMarkers).toHaveLength(1);
      expect(result!.nonwearMarkers[0]!.startTimestamp).toBe(3000);
      expect(result!.isNoSleep).toBe(false);
      expect(result!.needsConsensus).toBe(true);
      expect(result!.notes).toBe("test note");
    });

    it("returns null on 404", async () => {
      const ds = new ServerDataSource(null, "user");
      installFetchMock({}, 404);

      const result = await ds.loadMarkers(99, "2024-01-01", "user");
      expect(result).toBeNull();
    });
  });

  describe("saveMarkers payload", () => {
    it("sends camelCase-to-snake_case mapped body via PUT", async () => {
      const ds = new ServerDataSource("pw", "scorer");
      installFetchMock({});

      await ds.saveMarkers(5, "2024-02-20", "scorer", {
        sleepMarkers: [
          { onsetTimestamp: 100, offsetTimestamp: 200, markerIndex: 0, markerType: "NAP" as const },
        ],
        nonwearMarkers: [
          { startTimestamp: 300, endTimestamp: 400, markerIndex: 0 },
        ],
        isNoSleep: true,
        notes: "no main sleep",
        needsConsensus: false,
      });

      expect(fetchCalls).toHaveLength(1);
      const call = fetchCalls[0]!;
      expect(call.init?.method).toBe("PUT");
      expect(call.url).toBe("http://localhost:8500/api/v1/markers/5/2024-02-20");

      const body = JSON.parse(call.init?.body as string);
      expect(body.sleep_markers[0].onset_timestamp).toBe(100);
      expect(body.sleep_markers[0].marker_type).toBe("NAP");
      expect(body.nonwear_markers[0].start_timestamp).toBe(300);
      expect(body.is_no_sleep).toBe(true);
      expect(body.needs_consensus).toBe(false);
    });
  });

  describe("listFiles", () => {
    it("maps API response to FileInfo[]", async () => {
      const ds = new ServerDataSource(null, "u");
      installFetchMock({
        items: [
          { id: 1, filename: "accel.csv", status: "ready" },
          { id: 2, filename: "data.csv", status: "processing" },
        ],
      });

      const files = await ds.listFiles();
      expect(files).toHaveLength(2);
      expect(files[0]!.id).toBe(1);
      expect(files[0]!.filename).toBe("accel.csv");
      expect(files[0]!.source).toBe("server");
      expect(files[1]!.status).toBe("processing");
    });

    it("returns empty array on non-OK response", async () => {
      const ds = new ServerDataSource(null, "u");
      installFetchMock({}, 500);

      const files = await ds.listFiles();
      expect(files).toEqual([]);
    });
  });
});
