/**
 * Shared API error handling utilities.
 * Single source of truth for handling HTTP errors.
 */

import { useSleepScoringStore } from "@/store";

/**
 * Error class that carries the HTTP status code.
 * Use `err instanceof ApiError` to distinguish API errors from network errors,
 * and `err.status` to classify (4xx = permanent, 5xx = transient).
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Handle API response errors with consistent behavior.
 * - Clears auth on 401 Unauthorized
 * - Parses error detail from response body
 * - Throws ApiError with status code and message
 */
export async function handleApiError(response: Response): Promise<never> {
  // Clear auth on 401 Unauthorized (invalid password)
  if (response.status === 401) {
    useSleepScoringStore.getState().clearAuth();
  }

  // Try to parse error detail from response body
  const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
  throw new ApiError(error.detail || `HTTP ${response.status}`, response.status);
}

/**
 * Check response and handle errors if not ok.
 * Returns the response if successful for chaining.
 */
export async function checkResponse(response: Response): Promise<Response> {
  if (!response.ok) {
    await handleApiError(response);
  }
  return response;
}

/**
 * Parse response as JSON with proper typing.
 */
export async function parseJson<T>(response: Response): Promise<T> {
  return response.json() as Promise<T>;
}
