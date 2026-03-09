/**
 * Shared API error handling utilities.
 * Single source of truth for handling HTTP errors.
 */

import { useSleepScoringStore } from "@/store";

/**
 * Handle API response errors with consistent behavior.
 * - Clears auth on 401 Unauthorized
 * - Parses error detail from response body
 * - Throws Error with appropriate message
 */
export async function handleApiError(response: Response): Promise<never> {
  // Clear auth on 401 Unauthorized (invalid password)
  if (response.status === 401) {
    useSleepScoringStore.getState().clearAuth();
  }

  // Try to parse error detail from response body
  const error = await response.json().catch(() => ({ detail: "Request failed" }));
  throw new Error(error.detail || `HTTP ${response.status}`);
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
