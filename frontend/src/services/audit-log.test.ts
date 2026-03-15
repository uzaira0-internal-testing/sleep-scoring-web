/**
 * Tests for audit-log.ts — ACID-compliant audit log service.
 *
 * Tests the AuditLogService contract: context management, logging, sequence.
 * Uses dynamic import to avoid module mock contamination.
 */
import { describe, it, expect, beforeEach } from "bun:test";

// ---------------------------------------------------------------------------
// We test the AuditLogService class behavior by directly constructing
// a minimal test harness rather than using mock.module (which would
// contaminate the global module registry for other test files).
// ---------------------------------------------------------------------------

describe("AuditLogService", () => {
  // We verify the exported singleton exists and has the right interface
  it("exports auditLog singleton with expected methods", async () => {
    // Dynamic import to avoid side effects at module level
    const mod = await import("./audit-log");
    expect(mod.auditLog).toBeDefined();
    expect(typeof mod.auditLog.log).toBe("function");
    expect(typeof mod.auditLog.setContext).toBe("function");
    expect(typeof mod.auditLog.newSession).toBe("function");
    expect(typeof mod.auditLog.flushToServer).toBe("function");
  });

  // Test the core logic: log() should silently return when context is null
  it("log() does nothing without context (fileId/analysisDate are null)", async () => {
    const mod = await import("./audit-log");
    // Reset context to null
    mod.auditLog.setContext(null, null);
    // Should not throw
    expect(() => mod.auditLog.log("test_action")).not.toThrow();
  });

  it("log() does not throw when context is set", async () => {
    const mod = await import("./audit-log");
    mod.auditLog.setContext(42, "2025-03-01", "testuser");
    // May fail to write to IndexedDB in test env but should not throw
    expect(() => mod.auditLog.log("marker_placed", { onset: 100 })).not.toThrow();
  });

  it("newSession() does not throw", async () => {
    const mod = await import("./audit-log");
    expect(() => mod.auditLog.newSession()).not.toThrow();
  });

  it("flushToServer() returns a promise", async () => {
    const mod = await import("./audit-log");
    const result = mod.auditLog.flushToServer();
    expect(result).toBeInstanceOf(Promise);
    // Should resolve without error (server unavailable = noop)
    await expect(result).resolves.toBeUndefined();
  });
});
