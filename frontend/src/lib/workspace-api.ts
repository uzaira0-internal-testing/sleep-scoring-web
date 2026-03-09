/**
 * Dynamic API client manager.
 * Manages which server URL is targeted by the active workspace.
 */
import createClient from "openapi-fetch";
import type { paths } from "@/api/schema";
import { config } from "@/config";

let currentBaseUrl: string = "";
let currentClient: ReturnType<typeof createClient<paths>> | null = null;

/**
 * Get the API base URL for the active workspace.
 * Falls back to config.apiBaseUrl if no workspace URL is set.
 */
export function getWorkspaceApiBase(): string {
  if (currentBaseUrl) {
    return `${currentBaseUrl}/api/v1`;
  }
  return config.apiBaseUrl;
}

/**
 * Get the openapi-fetch client for the active workspace.
 * Creates one lazily if needed.
 */
export function getWorkspaceApi(): ReturnType<typeof createClient<paths>> {
  if (!currentClient) {
    currentClient = createClient<paths>({ baseUrl: getWorkspaceApiBase() });
  }
  return currentClient;
}

/**
 * Switch to a different workspace's server URL.
 * Pass "" for local-only workspaces (will use default/fallback).
 */
export function switchApi(serverUrl: string): void {
  currentBaseUrl = serverUrl.replace(/\/+$/, "");
  // Force re-creation of client on next access
  currentClient = null;
}

/**
 * Get the raw server URL (without /api/v1 suffix).
 */
export function getWorkspaceServerUrl(): string {
  return currentBaseUrl;
}

/**
 * Build an API base URL from an explicit server URL.
 * Used during login before a workspace is fully activated.
 */
export function getApiBaseForUrl(serverUrl: string): string {
  if (serverUrl) {
    return `${serverUrl.replace(/\/+$/, "")}/api/v1`;
  }
  return config.apiBaseUrl;
}
