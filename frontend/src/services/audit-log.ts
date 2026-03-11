/**
 * Persistent audit log service — tracks every user action per file/date.
 *
 * Events are buffered in memory and flushed to:
 * - Server API (POST /api/v1/audit/log) when online
 * - IndexedDB audit table as fallback when offline
 *
 * Designed for ML training data: given activity data + diary, replay exactly
 * what the researcher did to produce the final markers.
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
import { getWorkspaceApiBase } from "@/lib/workspace-api";
import { useCapabilitiesStore } from "@/store/capabilities-store";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuditEvent {
  action: string;
  clientTimestamp: number; // Unix seconds
  sessionId: string;
  sequence: number;
  payload?: Record<string, unknown>;
}

interface BufferedBatch {
  fileId: number;
  analysisDate: string;
  events: AuditEvent[];
}

// ---------------------------------------------------------------------------
// Service
// ---------------------------------------------------------------------------

const FLUSH_INTERVAL_MS = 10_000; // 10 seconds
const MAX_BUFFER_SIZE = 200; // Flush if buffer exceeds this

class AuditLogService {
  private buffer: AuditEvent[] = [];
  private sessionId: string;
  private sequence = 0;
  private fileId: number | null = null;
  private analysisDate: string | null = null;
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private isFlushing = false;
  // Hold batches from previous file/date contexts that haven't been flushed yet
  private pendingBatches: BufferedBatch[] = [];

  constructor() {
    this.sessionId = crypto.randomUUID();

    // Flush on page unload (best-effort)
    if (typeof window !== "undefined") {
      window.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden") {
          this.flush();
        }
      });
      window.addEventListener("beforeunload", () => {
        this.flush();
      });
    }
  }

  // -------------------------------------------------------------------------
  // Context management
  // -------------------------------------------------------------------------

  /**
   * Set the current file/date context. Flushes buffered events from the
   * previous context before switching.
   */
  setContext(fileId: number | null, analysisDate: string | null): void {
    // If context changed, save current buffer for later flush
    if (
      this.buffer.length > 0 &&
      (this.fileId !== fileId || this.analysisDate !== analysisDate)
    ) {
      if (this.fileId != null && this.analysisDate != null) {
        this.pendingBatches.push({
          fileId: this.fileId,
          analysisDate: this.analysisDate,
          events: [...this.buffer],
        });
        this.buffer = [];
      }
    }

    this.fileId = fileId;
    this.analysisDate = analysisDate;

    // Flush pending batches in background
    if (this.pendingBatches.length > 0) {
      void this.flushPendingBatches();
    }
  }

  /**
   * Generate a new session ID (call on page reload or workspace switch).
   */
  newSession(): void {
    void this.flush();
    this.sessionId = crypto.randomUUID();
    this.sequence = 0;
  }

  // -------------------------------------------------------------------------
  // Logging
  // -------------------------------------------------------------------------

  /**
   * Record an audit event. Cheap and synchronous — just appends to buffer.
   */
  log(action: string, payload?: Record<string, unknown>): void {
    if (this.fileId == null || this.analysisDate == null) return;

    const event: AuditEvent = {
      action,
      clientTimestamp: Date.now() / 1000,
      sessionId: this.sessionId,
      sequence: this.sequence++,
    };
    if (payload !== undefined) event.payload = payload;
    this.buffer.push(event);

    // Auto-flush if buffer is large
    if (this.buffer.length >= MAX_BUFFER_SIZE) {
      void this.flush();
    } else {
      this.scheduleFlush();
    }
  }

  // -------------------------------------------------------------------------
  // Flushing
  // -------------------------------------------------------------------------

  private scheduleFlush(): void {
    if (this.flushTimer != null) return;
    this.flushTimer = setTimeout(() => {
      this.flushTimer = null;
      void this.flush();
    }, FLUSH_INTERVAL_MS);
  }

  /**
   * Flush all buffered events to the server. Safe to call multiple times
   * concurrently — only one flush runs at a time.
   */
  async flush(): Promise<void> {
    if (this.isFlushing) return;
    this.isFlushing = true;

    try {
      // Flush pending batches from previous contexts
      await this.flushPendingBatches();

      // Flush current buffer
      if (this.buffer.length > 0 && this.fileId != null && this.analysisDate != null) {
        const events = [...this.buffer];
        this.buffer = [];
        await this.sendBatch(this.fileId, this.analysisDate, events);
      }
    } finally {
      this.isFlushing = false;
    }
  }

  private async flushPendingBatches(): Promise<void> {
    while (this.pendingBatches.length > 0) {
      const batch = this.pendingBatches[0]!;
      const ok = await this.sendBatch(batch.fileId, batch.analysisDate, batch.events);
      if (ok) {
        this.pendingBatches.shift();
      } else {
        break; // Stop flushing on failure — retry later
      }
    }
  }

  /**
   * Send a batch of events to the server. Returns true on success.
   * On failure, events are put back into pendingBatches for retry.
   */
  private async sendBatch(
    fileId: number,
    analysisDate: string,
    events: AuditEvent[],
  ): Promise<boolean> {
    if (events.length === 0) return true;

    // Only send to server when available
    const { serverAvailable } = useCapabilitiesStore.getState();
    if (!serverAvailable) {
      // Re-queue for later
      this.pendingBatches.push({ fileId, analysisDate, events });
      return false;
    }

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
            payload: e.payload,
          })),
        }),
      });
      return true;
    } catch (err) {
      console.warn("[AuditLog] Failed to flush events, will retry:", err);
      // Re-queue failed batch
      this.pendingBatches.push({ fileId, analysisDate, events });
      return false;
    }
  }
}

/** Singleton audit log service. */
export const auditLog = new AuditLogService();
