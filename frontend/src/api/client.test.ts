import { describe, it, expect, beforeEach, mock } from "bun:test";
import { useSleepScoringStore } from "@/store";
import { switchApi } from "@/lib/workspace-api";

// Reset workspace API and store before each test
beforeEach(() => {
  switchApi("");
  useSleepScoringStore.setState({
    sitePassword: null,
    username: "testuser",
  });
});

describe("getApiBase", () => {
  it("returns workspace API base", async () => {
    const { getApiBase } = await import("./client");
    expect(getApiBase()).toBe("/api/v1");
  });

  it("reflects workspace switch", async () => {
    const { getApiBase } = await import("./client");
    switchApi("http://example.com:8500");
    expect(getApiBase()).toBe("http://example.com:8500/api/v1");
    switchApi("");
  });
});

describe("authApi", () => {
  it("verifyPassword sends POST with password", async () => {
    const { authApi } = await import("./client");

    globalThis.fetch = mock(() =>
      Promise.resolve(
        new Response(JSON.stringify({ valid: true, session_expire_hours: 24 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    ) as typeof fetch;

    const result = await authApi.verifyPassword("secret");
    expect(result.valid).toBe(true);
    expect(result.session_expire_hours).toBe(24);
  });

  it("verifyPassword throws on invalid password", async () => {
    const { authApi } = await import("./client");

    globalThis.fetch = mock(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "Invalid password" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    ) as typeof fetch;

    await expect(authApi.verifyPassword("wrong")).rejects.toThrow("Invalid password");
  });

  it("getAuthStatus returns password_required", async () => {
    const { authApi } = await import("./client");

    globalThis.fetch = mock(() =>
      Promise.resolve(
        new Response(JSON.stringify({ password_required: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    ) as typeof fetch;

    const result = await authApi.getAuthStatus();
    expect(result.password_required).toBe(true);
  });

  it("getAuthStatus throws on non-JSON response", async () => {
    const { authApi } = await import("./client");

    globalThis.fetch = mock(() =>
      Promise.resolve(
        new Response("<html>Not Found</html>", {
          status: 200,
          headers: { "Content-Type": "text/html" },
        }),
      ),
    ) as typeof fetch;

    await expect(authApi.getAuthStatus()).rejects.toThrow("not JSON");
  });
});

describe("fetchWithAuth", () => {
  it("adds auth headers from store", async () => {
    const { fetchWithAuth } = await import("./client");
    let capturedHeaders: Record<string, string> = {};

    useSleepScoringStore.setState({
      sitePassword: "mypass",
      username: "alice",
    });

    globalThis.fetch = mock((url: string, init?: RequestInit) => {
      capturedHeaders = Object.fromEntries(
        Object.entries(init?.headers ?? {}),
      );
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }) as typeof fetch;

    await fetchWithAuth("/api/v1/test");
    expect(capturedHeaders["X-Site-Password"]).toBe("mypass");
    expect(capturedHeaders["X-Username"]).toBe("alice");
  });

  it("uses anonymous when no username", async () => {
    const { fetchWithAuth } = await import("./client");

    useSleepScoringStore.setState({
      sitePassword: null,
      username: "",
    });

    let capturedHeaders: Record<string, string> = {};
    globalThis.fetch = mock((_url: string, init?: RequestInit) => {
      capturedHeaders = Object.fromEntries(
        Object.entries(init?.headers ?? {}),
      );
      return Promise.resolve(
        new Response(JSON.stringify({}), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }) as typeof fetch;

    await fetchWithAuth("/api/v1/test");
    expect(capturedHeaders["X-Username"]).toBe("anonymous");
    expect(capturedHeaders["X-Site-Password"]).toBeUndefined();
  });
});
