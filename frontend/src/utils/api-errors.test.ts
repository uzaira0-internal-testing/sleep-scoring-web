/**
 * Tests for API error handling utilities.
 */
import { describe, it, expect, beforeEach } from "bun:test";
import { ApiError, handleApiError, checkResponse, parseJson } from "./api-errors";
import { useSleepScoringStore } from "@/store";

describe("ApiError", () => {
  it("should create an error with message and status", () => {
    const err = new ApiError("Not Found", 404);
    expect(err.message).toBe("Not Found");
    expect(err.status).toBe(404);
    expect(err.name).toBe("ApiError");
  });

  it("should be an instance of Error", () => {
    const err = new ApiError("Server Error", 500);
    expect(err instanceof Error).toBe(true);
    expect(err instanceof ApiError).toBe(true);
  });
});

describe("handleApiError", () => {
  beforeEach(() => {
    useSleepScoringStore.setState({
      sitePassword: "pw",
      username: "user",
      isAuthenticated: true,
    });
  });

  it("should throw ApiError with parsed detail", async () => {
    const response = new Response(JSON.stringify({ detail: "Bad request" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });

    try {
      await handleApiError(response);
      expect(true).toBe(false); // should not reach
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).message).toBe("Bad request");
      expect((err as ApiError).status).toBe(400);
    }
  });

  it("should clear auth on 401", async () => {
    const response = new Response(JSON.stringify({ detail: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });

    try {
      await handleApiError(response);
    } catch {
      // expected
    }

    const state = useSleepScoringStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.sitePassword).toBeNull();
  });

  it("should fallback to HTTP status when body is not JSON", async () => {
    const response = new Response("not json", {
      status: 500,
    });

    try {
      await handleApiError(response);
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).message).toBe("HTTP 500");
      expect((err as ApiError).status).toBe(500);
    }
  });
});

describe("checkResponse", () => {
  it("should return response when ok", async () => {
    const response = new Response("ok", { status: 200 });
    const result = await checkResponse(response);
    expect(result).toBe(response);
  });

  it("should throw ApiError when not ok", async () => {
    const response = new Response(JSON.stringify({ detail: "Forbidden" }), {
      status: 403,
      headers: { "Content-Type": "application/json" },
    });

    try {
      await checkResponse(response);
      expect(true).toBe(false); // should not reach
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(403);
    }
  });
});

describe("parseJson", () => {
  it("should parse JSON response", async () => {
    const data = { foo: "bar", count: 42 };
    const response = new Response(JSON.stringify(data), {
      headers: { "Content-Type": "application/json" },
    });

    const result = await parseJson<{ foo: string; count: number }>(response);
    expect(result.foo).toBe("bar");
    expect(result.count).toBe(42);
  });
});
