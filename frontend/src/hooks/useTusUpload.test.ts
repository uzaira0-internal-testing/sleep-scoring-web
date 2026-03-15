import { describe, it, expect } from "bun:test";
import { TUS_SIZE_THRESHOLD } from "./useTusUpload";
import type { TusPhase, TusProgress } from "./useTusUpload";

describe("useTusUpload", () => {
  describe("TUS_SIZE_THRESHOLD", () => {
    it("is 50MB", () => {
      expect(TUS_SIZE_THRESHOLD).toBe(50 * 1024 * 1024);
    });
  });

  describe("TusPhase type", () => {
    it("accepts all valid phases", () => {
      const phases: TusPhase[] = ["idle", "compressing", "uploading", "processing", "done", "error"];
      expect(phases).toHaveLength(6);
    });
  });

  describe("TusProgress type", () => {
    it("has expected shape", () => {
      const progress: TusProgress = {
        phase: "idle",
        percent: 0,
        bytesUploaded: 0,
        bytesTotal: 0,
        speed: 0,
        eta: 0,
        fileName: "",
        processingPhase: null,
        processingPercent: 0,
        error: null,
        fileId: null,
      };

      expect(progress.phase).toBe("idle");
      expect(progress.percent).toBe(0);
      expect(progress.fileId).toBeNull();
    });

    it("accepts uploading state with progress", () => {
      const progress: TusProgress = {
        phase: "uploading",
        percent: 45.5,
        bytesUploaded: 5_000_000,
        bytesTotal: 11_000_000,
        speed: 1_000_000,
        eta: 6,
        fileName: "data.csv",
        processingPhase: null,
        processingPercent: 0,
        error: null,
        fileId: null,
      };

      expect(progress.phase).toBe("uploading");
      expect(progress.bytesUploaded).toBe(5_000_000);
    });

    it("accepts error state", () => {
      const progress: TusProgress = {
        phase: "error",
        percent: 0,
        bytesUploaded: 0,
        bytesTotal: 0,
        speed: 0,
        eta: 0,
        fileName: "fail.csv",
        processingPhase: null,
        processingPercent: 0,
        error: "Network error",
        fileId: null,
      };

      expect(progress.error).toBe("Network error");
    });

    it("accepts done state with fileId", () => {
      const progress: TusProgress = {
        phase: "done",
        percent: 100,
        bytesUploaded: 10_000_000,
        bytesTotal: 10_000_000,
        speed: 0,
        eta: 0,
        fileName: "complete.csv",
        processingPhase: null,
        processingPercent: 100,
        error: null,
        fileId: 42,
      };

      expect(progress.fileId).toBe(42);
    });
  });

  describe("useTusUpload hook export", () => {
    it("is exported as a function", async () => {
      const mod = await import("./useTusUpload");
      expect(typeof mod.useTusUpload).toBe("function");
    });
  });
});
