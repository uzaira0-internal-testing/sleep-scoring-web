import { describe, it, expect, beforeEach } from "bun:test";
import { config } from "./config";

describe("config", () => {
  beforeEach(() => {
    // Clear any injected config
    delete (window as Record<string, unknown>).__CONFIG__;
  });

  describe("basePath", () => {
    it("returns empty string when no config is injected", () => {
      expect(config.basePath).toBe("");
    });

    it("returns injected basePath", () => {
      (window as Record<string, unknown>).__CONFIG__ = { basePath: "/app" };
      expect(config.basePath).toBe("/app");
    });
  });

  describe("apiBaseUrl", () => {
    it("returns /api/v1 by default", () => {
      expect(config.apiBaseUrl).toBe("/api/v1");
    });

    it("prepends basePath to /api/v1", () => {
      (window as Record<string, unknown>).__CONFIG__ = { basePath: "/myapp" };
      expect(config.apiBaseUrl).toBe("/myapp/api/v1");
    });
  });

  describe("isDev / isProd", () => {
    it("isDev and isProd are mutually exclusive", () => {
      expect(config.isDev).not.toBe(config.isProd);
    });

    it("isDev is a boolean", () => {
      expect(typeof config.isDev).toBe("boolean");
    });

    it("isProd is a boolean", () => {
      expect(typeof config.isProd).toBe("boolean");
    });
  });
});
