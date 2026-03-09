import { afterEach, describe, expect, it } from "bun:test";

import { buildConsensusWsUrl } from "./consensus-vote-sidebar";

const originalWindow = (globalThis as { window?: unknown }).window;

afterEach(() => {
  (globalThis as { window?: unknown }).window = originalWindow;
});

describe("buildConsensusWsUrl", () => {
  it("builds ws URL from relative API base path", () => {
    (globalThis as { window: { location: { origin: string }; __CONFIG__?: { basePath?: string } } }).window = {
      location: { origin: "http://localhost:5173" },
      __CONFIG__: { basePath: "/sleep-scoring" },
    };

    const url = buildConsensusWsUrl({
      fileId: 42,
      analysisDate: "2024-01-01",
      username: "alice",
      sitePassword: "secret",
    });

    expect(url).toBeTruthy();
    const parsed = new URL(url!);
    expect(parsed.protocol).toBe("ws:");
    expect(parsed.host).toBe("localhost:5173");
    expect(parsed.pathname).toBe("/sleep-scoring/api/v1/consensus/stream");
    expect(parsed.searchParams.get("file_id")).toBe("42");
    expect(parsed.searchParams.get("analysis_date")).toBe("2024-01-01");
    expect(parsed.searchParams.get("username")).toBe("alice");
    expect(parsed.searchParams.get("site_password")).toBe("secret");
  });

  it("uses wss when origin is https", () => {
    (globalThis as { window: { location: { origin: string }; __CONFIG__?: { basePath?: string } } }).window = {
      location: { origin: "https://example.org" },
      __CONFIG__: { basePath: "" },
    };

    const url = buildConsensusWsUrl({
      fileId: 7,
      analysisDate: "2024-02-03",
      username: "bob",
      sitePassword: null,
    });

    expect(url).toBeTruthy();
    const parsed = new URL(url!);
    expect(parsed.protocol).toBe("wss:");
    expect(parsed.host).toBe("example.org");
    expect(parsed.pathname).toBe("/api/v1/consensus/stream");
    expect(parsed.searchParams.get("file_id")).toBe("7");
    expect(parsed.searchParams.get("analysis_date")).toBe("2024-02-03");
    expect(parsed.searchParams.get("username")).toBe("bob");
    expect(parsed.searchParams.has("site_password")).toBeFalse();
  });

  it("returns null when window is unavailable", () => {
    (globalThis as { window?: unknown }).window = undefined;

    const url = buildConsensusWsUrl({
      fileId: 1,
      analysisDate: "2024-01-01",
      username: "anon",
      sitePassword: null,
    });

    expect(url).toBeNull();
  });
});
