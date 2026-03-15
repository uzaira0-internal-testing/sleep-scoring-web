import { describe, it, expect, beforeEach } from "bun:test";
import {
  getWorkspaceApiBase,
  getWorkspaceApi,
  switchApi,
  getWorkspaceServerUrl,
  getApiBaseForUrl,
} from "./workspace-api";

describe("workspace-api", () => {
  beforeEach(() => {
    // Reset to default (no workspace URL)
    switchApi("");
  });

  describe("getWorkspaceApiBase", () => {
    it("returns default /api/v1 when no workspace URL is set", () => {
      const base = getWorkspaceApiBase();
      expect(base).toBe("/api/v1");
    });

    it("returns workspace URL + /api/v1 when set", () => {
      switchApi("http://localhost:8500");
      expect(getWorkspaceApiBase()).toBe("http://localhost:8500/api/v1");
    });
  });

  describe("switchApi", () => {
    it("strips trailing slashes from URL", () => {
      switchApi("http://localhost:8500///");
      expect(getWorkspaceServerUrl()).toBe("http://localhost:8500");
    });

    it("clears URL when switching to empty string", () => {
      switchApi("http://localhost:8500");
      switchApi("");
      expect(getWorkspaceServerUrl()).toBe("");
    });

    it("forces client re-creation", () => {
      switchApi("http://server-a:8500");
      const client1 = getWorkspaceApi();
      switchApi("http://server-b:8500");
      const client2 = getWorkspaceApi();
      // After switching, a new client should be created
      expect(client1).not.toBe(client2);
    });
  });

  describe("getWorkspaceServerUrl", () => {
    it("returns empty string by default", () => {
      expect(getWorkspaceServerUrl()).toBe("");
    });

    it("returns the raw server URL without /api/v1", () => {
      switchApi("http://example.com:8500");
      expect(getWorkspaceServerUrl()).toBe("http://example.com:8500");
    });
  });

  describe("getWorkspaceApi", () => {
    it("returns a client object", () => {
      const client = getWorkspaceApi();
      expect(client).toBeDefined();
      expect(typeof client).toBe("object");
    });

    it("returns same client on repeated calls (lazy caching)", () => {
      const c1 = getWorkspaceApi();
      const c2 = getWorkspaceApi();
      expect(c1).toBe(c2);
    });
  });

  describe("getApiBaseForUrl", () => {
    it("returns URL + /api/v1 for non-empty URL", () => {
      expect(getApiBaseForUrl("http://localhost:8500")).toBe("http://localhost:8500/api/v1");
    });

    it("strips trailing slashes from explicit URL", () => {
      expect(getApiBaseForUrl("http://localhost:8500//")).toBe("http://localhost:8500/api/v1");
    });

    it("returns default /api/v1 for empty URL", () => {
      expect(getApiBaseForUrl("")).toBe("/api/v1");
    });
  });
});
