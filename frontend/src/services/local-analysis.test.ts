/**
 * Tests for local-analysis.ts.
 *
 * The computeLocalAnalysis function depends heavily on IndexedDB (Dexie)
 * which is not available in bun test. We test the exported interface shape
 * and verify the function is properly exported.
 */
import { describe, it, expect } from "bun:test";
import type { LocalAnalysisSummary } from "./local-analysis";

describe("local-analysis", () => {
  it("LocalAnalysisSummary has expected shape", () => {
    const summary: LocalAnalysisSummary = {
      total_files: 2,
      total_dates: 10,
      scored_dates: 8,
      files_summary: [
        {
          file_id: 1,
          filename: "test.csv",
          participant_id: null,
          total_dates: 5,
          scored_dates: 4,
          has_diary: false,
        },
      ],
      aggregate_metrics: {
        mean_tst_minutes: 420,
        mean_sleep_efficiency: 85.5,
        mean_waso_minutes: 30,
        mean_sleep_onset_latency: 15,
        total_sleep_periods: 8,
        total_nap_periods: 2,
      },
    };

    expect(summary.total_files).toBe(2);
    expect(summary.total_dates).toBe(10);
    expect(summary.scored_dates).toBe(8);
    expect(summary.files_summary).toHaveLength(1);
    expect(summary.aggregate_metrics.mean_tst_minutes).toBe(420);
    expect(summary.aggregate_metrics.total_sleep_periods).toBe(8);
  });

  it("LocalAnalysisSummary allows null metrics", () => {
    const summary: LocalAnalysisSummary = {
      total_files: 0,
      total_dates: 0,
      scored_dates: 0,
      files_summary: [],
      aggregate_metrics: {
        mean_tst_minutes: null,
        mean_sleep_efficiency: null,
        mean_waso_minutes: null,
        mean_sleep_onset_latency: null,
        total_sleep_periods: 0,
        total_nap_periods: 0,
      },
    };

    expect(summary.aggregate_metrics.mean_tst_minutes).toBeNull();
    expect(summary.aggregate_metrics.mean_sleep_efficiency).toBeNull();
  });

  it("computeLocalAnalysis is exported as a function", async () => {
    const mod = await import("./local-analysis");
    expect(typeof mod.computeLocalAnalysis).toBe("function");
  });
});
