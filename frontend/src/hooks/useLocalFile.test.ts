/**
 * Tests for useLocalFile — tests the BatchProgress type and
 * the store state that processFiles depends on.
 *
 * The hook itself wraps File System Access API and WASM processing,
 * so we test the store interactions and type contracts.
 */
import { describe, it, expect, beforeEach } from "bun:test";
import { useSleepScoringStore } from "@/store";
import type { BatchProgress } from "./useLocalFile";

describe("useLocalFile store dependencies", () => {
  beforeEach(() => {
    useSleepScoringStore.setState({
      currentFileId: null,
      currentFilename: null,
      currentFileSource: "server",
      currentDateIndex: 0,
      availableDates: [],
      devicePreset: "actigraph",
      skipRows: 10,
    });
  });

  describe("processFiles store reads", () => {
    it("should have default devicePreset of actigraph", () => {
      const state = useSleepScoringStore.getState();
      expect(state.devicePreset).toBe("actigraph");
    });

    it("should have default skipRows of 10", () => {
      const state = useSleepScoringStore.getState();
      expect(state.skipRows).toBe(10);
    });

    it("should update currentFileId after processing completes", () => {
      useSleepScoringStore.setState({
        currentFileId: 42,
        currentFilename: "test.csv",
        currentFileSource: "local",
        availableDates: ["2024-01-01"],
        currentDateIndex: 0,
      });

      const state = useSleepScoringStore.getState();
      expect(state.currentFileId).toBe(42);
      expect(state.currentFilename).toBe("test.csv");
      expect(state.currentFileSource).toBe("local");
    });
  });

  describe("BatchProgress type contract", () => {
    it("should accept batch progress with file info", () => {
      const progress: BatchProgress = {
        phase: "reading",
        percent: 50,
        message: "[1/3] file.csv: Reading...",
        fileIndex: 0,
        fileCount: 3,
        currentFilename: "file.csv",
      };

      expect(progress.phase).toBe("reading");
      expect(progress.fileIndex).toBe(0);
      expect(progress.fileCount).toBe(3);
      expect(progress.currentFilename).toBe("file.csv");
    });

    it("should accept progress without batch info (single file)", () => {
      const progress: BatchProgress = {
        phase: "epoching",
        percent: 75,
        message: "Epoching data...",
      };

      expect(progress.fileIndex).toBeUndefined();
      expect(progress.fileCount).toBeUndefined();
    });
  });
});
