/**
 * Tests for workspace-db.ts.
 *
 * The module manages Dexie instances. In bun test, IndexedDB is simulated
 * by happy-dom, so we test the throw-before-switch behavior and function exports.
 */
import { describe, it, expect } from "bun:test";
import { getDb, switchDb, closeDb } from "./workspace-db";

describe("workspace-db", () => {
  describe("getDb", () => {
    it("throws when no database is active", () => {
      // Ensure we start clean
      closeDb();
      expect(() => getDb()).toThrow("No workspace database is active");
    });
  });

  describe("switchDb", () => {
    it("is a function", () => {
      expect(typeof switchDb).toBe("function");
    });
  });

  describe("closeDb", () => {
    it("is a function that does not throw when no db is active", () => {
      closeDb();
      expect(() => closeDb()).not.toThrow();
    });

    it("makes getDb throw after close", () => {
      closeDb();
      expect(() => getDb()).toThrow("No workspace database is active");
    });
  });

  describe("exports", () => {
    it("exports getDb, switchDb, closeDb", async () => {
      const mod = await import("./workspace-db");
      expect(typeof mod.getDb).toBe("function");
      expect(typeof mod.switchDb).toBe("function");
      expect(typeof mod.closeDb).toBe("function");
    });
  });
});
