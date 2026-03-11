import { useSleepScoringStore } from "@/store";
import { checkResponse, parseJson } from "@/utils/api-errors";
import { getWorkspaceApiBase, getApiBaseForUrl } from "@/lib/workspace-api";

/**
 * Get API base path for the active workspace.
 */
const getApiBase = getWorkspaceApiBase;

/**
 * Helper function to fetch with authentication.
 * Automatically adds X-Site-Password and X-Username headers from store.
 */
export async function fetchWithAuth<T>(url: string, options?: RequestInit): Promise<T> {
  const { sitePassword, username } = useSleepScoringStore.getState();

  const response = await fetch(url, {
    ...options,
    headers: {
      ...options?.headers,
      ...(sitePassword ? { "X-Site-Password": sitePassword } : {}),
      "X-Username": username || "anonymous",
    },
  });

  await checkResponse(response);
  return parseJson<T>(response);
}

/**
 * Auth-specific API calls
 */
export const authApi = {
  /**
   * Verify site password.
   * @param password - site password to verify
   * @param serverUrl - optional explicit server URL (for pre-workspace-activation probes)
   */
  async verifyPassword(password: string, serverUrl?: string) {
    const base = serverUrl !== undefined ? getApiBaseForUrl(serverUrl) : getApiBase();
    const response = await fetch(`${base}/auth/verify`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ password }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
      throw new Error(error.detail || "Invalid password");
    }

    return response.json() as Promise<{
      valid: boolean;
      session_expire_hours: number;
    }>;
  },

  /**
   * Check if auth is required (site password configured).
   * @param serverUrl - optional explicit server URL (for pre-workspace-activation probes)
   */
  async getAuthStatus(serverUrl?: string) {
    const base = serverUrl !== undefined ? getApiBaseForUrl(serverUrl) : getApiBase();
    const response = await fetch(`${base}/auth/status`);
    if (!response.ok) {
      throw new Error("Failed to get auth status");
    }
    // Guard against non-JSON responses (e.g. Tauri asset server returning HTML)
    const ct = response.headers.get("content-type") ?? "";
    if (!ct.includes("application/json")) {
      throw new Error("Auth status response is not JSON");
    }
    return response.json() as Promise<{
      password_required: boolean;
    }>;
  },
};

/**
 * Get auth headers for API calls
 */
function getAuthHeaders(): Record<string, string> {
  const { sitePassword, username } = useSleepScoringStore.getState();
  return {
    ...(sitePassword ? { "X-Site-Password": sitePassword } : {}),
    "X-Username": username || "anonymous",
  };
}

/**
 * Settings API calls
 */
export const settingsApi = {
  async getSettings() {
    return fetchWithAuth<import("./types").UserSettingsResponse>(`${getApiBase()}/settings`);
  },

  async updateSettings(data: import("./types").UserSettingsUpdate) {
    const response = await fetch(`${getApiBase()}/settings`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify(data),
    });

    await checkResponse(response);
    return parseJson<import("./types").UserSettingsResponse>(response);
  },

  async resetSettings() {
    const response = await fetch(`${getApiBase()}/settings`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });

    // 204 No Content is success for DELETE
    if (!response.ok && response.status !== 204) {
      await checkResponse(response);
    }
  },

  // Study-wide settings (shared across all users)
  async getStudySettings() {
    return fetchWithAuth<import("./types").UserSettingsResponse>(`${getApiBase()}/settings/study`);
  },

  async updateStudySettings(data: import("./types").UserSettingsUpdate) {
    const response = await fetch(`${getApiBase()}/settings/study`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify(data),
    });

    await checkResponse(response);
    return parseJson<import("./types").UserSettingsResponse>(response);
  },

  async resetStudySettings() {
    const response = await fetch(`${getApiBase()}/settings/study`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });

    if (!response.ok && response.status !== 204) {
      await checkResponse(response);
    }
  },
};

/**
 * Diary API calls
 */
export const diaryApi = {
  async listDiaryEntries(fileId: number) {
    return fetchWithAuth<import("./types").DiaryEntryResponse[]>(
      `${getApiBase()}/diary/${fileId}`
    );
  },

  async getDiaryEntry(fileId: number, date: string) {
    return fetchWithAuth<import("./types").DiaryEntryResponse | null>(
      `${getApiBase()}/diary/${fileId}/${date}`
    );
  },

  async updateDiaryEntry(
    fileId: number,
    date: string,
    data: import("./types").DiaryEntryCreate
  ) {
    const response = await fetch(`${getApiBase()}/diary/${fileId}/${date}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify(data),
    });

    await checkResponse(response);
    return parseJson<import("./types").DiaryEntryResponse>(response);
  },

  async deleteDiaryEntry(fileId: number, date: string) {
    const response = await fetch(`${getApiBase()}/diary/${fileId}/${date}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });

    // 204 No Content is success for DELETE
    if (!response.ok && response.status !== 204) {
      await checkResponse(response);
    }
  },

  /**
   * Upload diary CSV (study-wide). Matches rows to activity files
   * by participant_id column in the CSV.
   */
  async uploadDiaryCsv(file: File) {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${getApiBase()}/diary/upload`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: formData,
    });

    await checkResponse(response);
    return parseJson<import("./types").DiaryUploadResponse>(response);
  },

  /**
   * Upload diary CSV for a specific activity file (per-file).
   * Does not require participant_id column — all rows go to this file.
   */
  async uploadDiaryCsvForFile(fileId: number, file: File) {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${getApiBase()}/diary/${fileId}/upload`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: formData,
    });

    await checkResponse(response);
    return parseJson<import("./types").DiaryUploadResponse>(response);
  },
};

/**
 * File upload API calls
 */
export const filesApi = {
  async uploadFile(file: File, replace = false) {
    const formData = new FormData();
    formData.append("file", file);

    const url = `${getApiBase()}/files/upload${replace ? "?replace=true" : ""}`;
    const response = await fetch(url, {
      method: "POST",
      headers: getAuthHeaders(),
      body: formData,
    });

    await checkResponse(response);
    return parseJson<import("./types").FileUploadResponse>(response);
  },

  async listFiles() {
    return fetchWithAuth<{ items: import("./types").FileInfo[]; total: number }>(
      `${getApiBase()}/files`
    );
  },

  async getProcessingStatus(fileId: number) {
    return fetchWithAuth<{
      file_id: number;
      status: string;
      phase: string | null;
      percent: number;
      rows_processed: number;
      total_rows_estimate: number | null;
      error: string | null;
      started_at: string | null;
    }>(`${getApiBase()}/files/${fileId}/processing-status`);
  },

  async deleteFile(fileId: number) {
    const response = await fetch(`${getApiBase()}/files/${fileId}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });

    if (!response.ok && response.status !== 204) {
      await checkResponse(response);
    }
  },
};

/**
 * Complexity (scoring difficulty) API calls
 */
export const complexityApi = {
  async computeForFile(fileId: number) {
    const response = await fetch(`${getApiBase()}/files/${fileId}/compute-complexity`, {
      method: "POST",
      headers: getAuthHeaders(),
    });
    await checkResponse(response);
    return parseJson<{ message: string; date_count: number }>(response);
  },

  async getDetail(fileId: number, date: string) {
    return fetchWithAuth<{
      complexity_pre: number | null;
      complexity_post: number | null;
      features: Record<string, number | string | null>;
      computed_at: string | null;
    }>(`${getApiBase()}/files/${fileId}/${date}/complexity`);
  },
};

/**
 * Nonwear sensor data API calls
 */
export const nonwearApi = {
  /**
   * Upload nonwear CSV (study-wide). Matches rows to activity files
   * by participant_id column in the CSV.
   */
  async uploadNonwearCsv(file: File) {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${getApiBase()}/markers/nonwear/upload`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: formData,
    });

    await checkResponse(response);
    return parseJson<{ dates_imported: number; markers_created: number; dates_skipped: number; errors: string[] }>(response);
  },
};

/**
 * Import API calls (desktop export → web)
 */
export const importApi = {
  /**
   * Upload a desktop sleep marker CSV export.
   * Matches rows to activity files by filename column.
   * Replaces existing sleep markers for imported dates and triggers metric recalculation.
   */
  async uploadSleepCsv(file: File) {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${getApiBase()}/markers/sleep/upload`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: formData,
    });

    await checkResponse(response);
    return parseJson<{
      dates_imported: number;
      markers_created: number;
      nonwear_markers_created: number;
      no_sleep_dates: number;
      dates_skipped: number;
      errors: string[];
      total_rows: number;
      matched_rows: number;
      unmatched_identifiers: string[];
      ambiguous_identifiers: string[];
    }>(response);
  },
};

/**
 * Auth info API calls
 */
export const meApi = {
  async getMe() {
    return fetchWithAuth<import("./types").AuthMeResponse>(
      `${getApiBase()}/files/auth/me`
    );
  },
};

/**
 * File assignment API calls (admin only)
 */
export const assignmentApi = {
  async listAssignments() {
    return fetchWithAuth<import("./types").FileAssignment[]>(
      `${getApiBase()}/files/assignments`
    );
  },

  async createAssignments(fileIds: number[], username: string) {
    const response = await fetch(`${getApiBase()}/files/assignments`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify({ file_ids: fileIds, username }),
    });
    await checkResponse(response);
    return parseJson<{ created: number; total_requested: number }>(response);
  },

  async deleteUserAssignments(username: string) {
    const response = await fetch(`${getApiBase()}/files/assignments/${encodeURIComponent(username)}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });
    if (!response.ok && response.status !== 204) await checkResponse(response);
    if (response.status === 204) return { deleted: 0 };
    return parseJson<{ deleted: number }>(response);
  },

  async deleteFileAssignment(fileId: number, username: string) {
    const response = await fetch(
      `${getApiBase()}/files/${fileId}/assignments/${encodeURIComponent(username)}`,
      {
        method: "DELETE",
        headers: getAuthHeaders(),
      }
    );
    if (!response.ok && response.status !== 204) await checkResponse(response);
    if (response.status === 204) return { deleted: 0 };
    return parseJson<{ deleted: number }>(response);
  },

  async getAssignmentProgress() {
    return fetchWithAuth<import("./types").AssignmentProgress[]>(
      `${getApiBase()}/files/assignments/progress`
    );
  },

  async getUnassignedFiles() {
    return fetchWithAuth<import("./types").FileInfo[]>(
      `${getApiBase()}/files/assignments/unassigned`
    );
  },
};

/**
 * Auto-score result API calls
 */
export const autoScoreApi = {
  async startBatch(payload?: {
    file_ids?: number[];
    only_missing?: boolean;
    algorithm?: string;
    include_diary?: boolean;
    onset_epochs?: number;
    offset_minutes?: number;
    detection_rule?: string;
  }) {
    const response = await fetch(`${getApiBase()}/markers/auto-score/batch`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify(payload ?? {}),
    });
    await checkResponse(response);
    return parseJson<{
      is_running: boolean;
      total_dates: number;
      processed_dates: number;
      scored_dates: number;
      skipped_existing: number;
      skipped_incomplete_diary: number;
      skipped_no_activity: number;
      skipped_no_markers: number;
      failed_dates: number;
      started_at: string | null;
      finished_at: string | null;
      current_file_id: number | null;
      current_date: string | null;
      errors: string[];
    }>(response);
  },

  async getBatchStatus() {
    return fetchWithAuth<{
      is_running: boolean;
      total_dates: number;
      processed_dates: number;
      scored_dates: number;
      skipped_existing: number;
      skipped_incomplete_diary: number;
      skipped_no_activity: number;
      skipped_no_markers: number;
      failed_dates: number;
      started_at: string | null;
      finished_at: string | null;
      current_file_id: number | null;
      current_date: string | null;
      errors: string[];
    }>(`${getApiBase()}/markers/auto-score/batch/status`);
  },

  async getResult(fileId: number, date: string) {
    return fetchWithAuth<{
      sleep_markers: Array<Record<string, unknown>>;
      nonwear_markers: Array<Record<string, unknown>>;
      algorithm_used: string | null;
      notes: string | null;
    }>(`${getApiBase()}/markers/${fileId}/${date}/auto-score-result`);
  },
};

/**
 * Consensus ballot and vote API calls
 */
export const consensusApi = {
  async getBallot(fileId: number, date: string) {
    return fetchWithAuth<import("./types").ConsensusBallotResponse>(
      `${getApiBase()}/consensus/${fileId}/${date}/ballot`
    );
  },

  async castVote(fileId: number, date: string, candidateId: number | null) {
    return fetchWithAuth<import("./types").ConsensusBallotResponse>(
      `${getApiBase()}/consensus/${fileId}/${date}/vote`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_id: candidateId }),
      }
    );
  },
};

/**
 * Pipeline discovery API calls
 */
export const pipelineApi = {
  async discover() {
    return fetchWithAuth<import("./types").PipelineDiscoveryResponse>(
      `${getApiBase()}/markers/pipeline/discover`
    );
  },
};

// Export getApiBase for use in other modules
export { getApiBase };
