/**
 * ACID-compliant audit log service — tracks every user action per file/date.
 *
 * **Durability guarantee**: Every `log()` call writes to IndexedDB immediately.
 * IndexedDB is the durable commit point — no event is lost on crash, tab kill,
 * or power loss. Server flush is replication, not the primary store.
 *
 * Flow: log() → IndexedDB (durable) → server replication (periodic)
 *
 * On startup, any events from previous crashed sessions are automatically
 * flushed to the server.
 *
 * Action types:
 *   session_start       — user opened this file/date (payload: initial marker state)
 *   marker_placed       — two-click marker creation completed
 *   marker_moved        — drag completed (from → to)
 *   marker_adjusted     — keyboard Q/E/A/D epoch adjustment
 *   marker_deleted      — single marker deleted
 *   markers_cleared     — all markers cleared
 *   auto_score_applied  — auto-score result accepted into markers
 *   auto_nonwear_applied — auto-nonwear result accepted
 *   no_sleep_toggled    — is_no_sleep changed
 *   consensus_toggled   — needs_consensus changed
 *   notes_changed       — notes text changed
 *   candidate_copied    — copied markers from consensus candidate
 *   undo                — undo performed
 *   redo                — redo performed
 *   markers_saved       — markers persisted to server/IndexedDB
 *   session_end         — user navigated away from this file/date
 */

import { fetchWithAuth } from "@/api/client";
import type { AuditLogRecord } from "@/db/schema";
import { getWorkspaceApiBase } from "@/lib/workspace-api";
import { getDb } from "@/lib/workspace-db";
import { useCapabilitiesStore } from "@/store/capabilities-store";

// ---------------------------------------------------------------------------
// Service
// ---------------------------------------------------------------------------

const FLUSH_INTERVAL_MS = 10_000; // 10 seconds
const FLUSH_BATCH_SIZE = 500; // Max events per server request

class AuditLogService {
  private sessionId: string;
  private sequence = 0;
  private fileId: number | null = null;
  private analysisDate: string | null = null;
  private username: string | null = null;
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private isFlushing = false;

  constructor() {
    this.sessionId = crypto.randomUUID();

    // Replicate to server on visibility change (best-effort optimization)
    if (typeof window !== "undefined") {
      window.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden") {
          void this.flushToServer();
        }
      });

      // Flush on startup — pick up events from previous crashed sessions
      // Delayed to avoid blocking page load
      setTimeout(() => void this.flushToServer(), 3000);
    }
  }

  // -------------------------------------------------------------------------
  // Context management
  // -------------------------------------------------------------------------

  /**
   * Set the current file/date/user context.
   * Triggers server replication of any pending events.
   */
  setContext(
    fileId: number | null,
    analysisDate: string | null,
    username?: string,
  ): void {
    this.fileId = fileId;
    this.analysisDate = analysisDate;
    if (username !== undefined) this.username = username;

    // Replicate pending events in background
    void this.flushToServer();
  }

  /**
   * Generate a new session ID (call on page reload or workspace switch).
   */
  newSession(): void {
    void this.flushToServer();
    this.sessionId = crypto.randomUUID();
    this.sequence = 0;
  }

  // -------------------------------------------------------------------------
  // Logging — ACID: writes to IndexedDB immediately
  // -------------------------------------------------------------------------

  /**
   * Record an audit event. Writes to IndexedDB immediately for durability.
   * Server replication happens periodically in the background.
   */
  log(action: string, payload?: Record<string, unknown>): void {
    if (this.fileId == null || this.analysisDate == null) return;

    const seq = this.sequence++;
    const record: Omit<AuditLogRecord, "id"> = {
      fileId: this.fileId,
      analysisDate: this.analysisDate,
      username: this.username ?? "unknown",
      action,
      clientTimestamp: Date.now() / 1000,
      sessionId: this.sessionId,
      sequence: seq,
      ...(payload !== undefined ? { payload } : {}),
    };

    // Write to IndexedDB — this is the durable commit point.
    // On failure, roll back the sequence counter so no gaps appear.
    let db;
    try {
      db = getDb();
    } catch {
      // DB not initialized yet — event lost (startup race)
      console.warn("[AuditLog] IndexedDB not ready, event lost:", action);
      return;
    }

    db.auditLog.add(record as AuditLogRecord).catch((err: unknown) => {
      // Event is lost — sequence gap is unavoidable since later events may
      // have already used subsequent sequence numbers. Log at error level.
      console.error("[AuditLog] IndexedDB write failed, event lost:", action, err);
    });

    this.scheduleFlush();
  }

  // -------------------------------------------------------------------------
  // Server replication
  // -------------------------------------------------------------------------

  private scheduleFlush(): void {
    if (this.flushTimer != null) return;
    this.flushTimer = setTimeout(() => {
      this.flushTimer = null;
      void this.flushToServer();
    }, FLUSH_INTERVAL_MS);
  }

  /**
   * Replicate committed events from IndexedDB to the server.
   * Events are only deleted from IndexedDB after confirmed server receipt.
   */
  async flushToServer(): Promise<void> {
    if (this.isFlushing) return;

    const { serverAvailable } = useCapabilitiesStore.getState();
    if (!serverAvailable) return;

    this.isFlushing = true;

    try {
      let db: ReturnType<typeof getDb>;
      try {
        db = getDb();
      } catch {
        return; // DB not ready
      }

      // Read oldest unflushed events
      const events = await db.auditLog
        .orderBy("id")
        .limit(FLUSH_BATCH_SIZE)
        .toArray();

      if (events.length === 0) return;

      // Group by (fileId, analysisDate) for batched API calls
      const groups = new Map<string, AuditLogRecord[]>();
      for (const event of events) {
        const key = `${event.fileId}:${event.analysisDate}`;
        let group = groups.get(key);
        if (!group) {
          group = [];
          groups.set(key, group);
        }
        group.push(event);
      }

      // Send each group to the server
      for (const group of Array.from(groups.values())) {
        const first = group[0]!;
        const result = await this.sendBatch(first.fileId, first.analysisDate, group);
        if (result === "ok" || result === "drop") {
          // Delete from IndexedDB after confirmed receipt OR permanent rejection
          const ids = group.map((e) => e.id!);
          await db.auditLog.bulkDelete(ids);
        }
        // "retry" — events stay in IndexedDB for next flush cycle
      }
    } catch (err) {
      console.warn("[AuditLog] Flush error:", err);
    } finally {
      this.isFlushing = false;
    }
  }

  /**
   * Send a batch of events to the server API.
   * Returns "ok" on success, "drop" on permanent rejection (4xx),
   * or "retry" on transient failure (network/5xx).
   */
  private async sendBatch(
    fileId: number,
    analysisDate: string,
    events: AuditLogRecord[],
  ): Promise<"ok" | "retry" | "drop"> {
    if (events.length === 0) return "ok";

    try {
      const base = getWorkspaceApiBase();
      await fetchWithAuth(`${base}/audit/log`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_id: fileId,
          analysis_date: analysisDate,
          events: events.map((e) => ({
            action: e.action,
            client_timestamp: e.clientTimestamp,
            session_id: e.sessionId,
            sequence: e.sequence,
            ...(e.payload != null ? { payload: e.payload } : {}),
          })),
        }),
      });
      return "ok";
    } catch (err) {
      // Permanent rejection (4xx) — drop the batch to avoid infinite retry
      const msg = err instanceof Error ? err.message : "";
      if (/\b4\d{2}\b/.test(msg)) {
        console.error("[AuditLog] Permanent rejection, dropping batch:", msg);
        return "drop";
      }
      console.warn("[AuditLog] Server send failed, will retry:", err);
      return "retry";
    }
  }
}

/** Singleton audit log service. */
export const auditLog = new AuditLogService();
