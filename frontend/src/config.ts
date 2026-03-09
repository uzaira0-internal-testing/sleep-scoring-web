// Runtime configuration injected by docker-entrypoint.sh via config.js
declare global {
  interface Window {
    __CONFIG__?: { basePath?: string };
  }
}

// Check if we're in development mode
// In production builds, Bun replaces process.env.NODE_ENV with "production"
const isDev =
  typeof process !== "undefined" &&
  process.env?.NODE_ENV !== "production";

export const config = {
  get basePath(): string {
    return window.__CONFIG__?.basePath || "";
  },
  /**
   * Default API base URL (from docker-injected basePath or dev proxy).
   * For workspace-specific URLs, use getWorkspaceApiBase() from workspace-api.ts.
   */
  get apiBaseUrl(): string {
    return `${this.basePath}/api/v1`;
  },
  get isDev(): boolean {
    return isDev;
  },
  get isProd(): boolean {
    return !isDev;
  },
};
