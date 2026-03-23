/**
 * Reusable TanStack Query v5 queryOptions factories.
 *
 * Centralizes query keys and fetch functions so they can be shared
 * between useQuery, prefetchQuery, and queryClient.invalidateQueries.
 */
import { queryOptions } from "@tanstack/react-query";
import { fetchWithAuth, getApiBase, filesApi, settingsApi, assignmentApi, autoScoreApi, pipelineApi } from "@/api/client";
import { getLocalFiles } from "@/db";
import type { DataSource } from "@/services/data-source";

// ── Files ──────────────────────────────────────────────────────────

export function filesQueryOptions() {
  return queryOptions({
    queryKey: ["files"] as const,
    queryFn: () => filesApi.listFiles(),
  });
}

// ── Local Files (IndexedDB) ─────────────────────────────────────────

export function localFilesQueryOptions() {
  return queryOptions({
    queryKey: ["local-files"] as const,
    queryFn: () => getLocalFiles(),
  });
}

// ── Study Settings ─────────────────────────────────────────────────

export function studySettingsQueryOptions() {
  return queryOptions({
    queryKey: ["study-settings"] as const,
    queryFn: () => settingsApi.getStudySettings(),
  });
}

// ── Export Columns ─────────────────────────────────────────────────

interface ExportColumnInfo {
  name: string;
  category: string;
  description: string | null;
  data_type: string;
  is_default: boolean;
}

interface ExportColumnCategory {
  name: string;
  columns: string[];
}

interface ExportColumnsResponse {
  columns: ExportColumnInfo[];
  categories: ExportColumnCategory[];
}

export function exportColumnsQueryOptions() {
  return queryOptions({
    queryKey: ["export-columns"] as const,
    queryFn: () => fetchWithAuth<ExportColumnsResponse>(`${getApiBase()}/export/columns`),
  });
}

// ── Admin Assignments ──────────────────────────────────────────────

export function assignmentProgressQueryOptions() {
  return queryOptions({
    queryKey: ["assignment-progress"] as const,
    queryFn: () => assignmentApi.getAssignmentProgress(),
  });
}

export function unassignedFilesQueryOptions() {
  return queryOptions({
    queryKey: ["unassigned-files"] as const,
    queryFn: () => assignmentApi.getUnassignedFiles(),
  });
}

// ── Auto-Score Batch Status ────────────────────────────────────────

export function autoScoreBatchStatusQueryOptions() {
  return queryOptions({
    queryKey: ["auto-score-batch-status"] as const,
    queryFn: () => autoScoreApi.getBatchStatus(),
  });
}

// ── Pipeline Discovery ───────────────────────────────────────────

// ── Activity Data ───────────────────────────────────────────────

export function activityDataQueryOptions(
  dataSource: DataSource,
  fileId: number | null,
  date: string | null,
  viewModeHours: number,
  algorithm: string,
  source: "local" | "server",
) {
  return queryOptions({
    queryKey: ["activity", fileId, date, viewModeHours, algorithm, source] as const,
    queryFn: () =>
      dataSource.loadActivityData(fileId!, date!, {
        algorithm,
        viewHours: viewModeHours,
      }),
    enabled: !!fileId && !!date,
  });
}

// ── Pipeline Discovery ───────────────────────────────────────────

export function pipelineDiscoverQueryOptions() {
  return queryOptions({
    queryKey: ["pipeline-discover"] as const,
    queryFn: () => pipelineApi.discover(),
    staleTime: 5 * 60 * 1000, // 5 minutes — component list rarely changes
  });
}
