/**
 * k6 load test for Sleep Scoring Web API.
 *
 * Simulates concurrent researchers uploading files, scoring dates,
 * exporting results, managing diary entries, and running auto-score.
 *
 * Scenarios:
 *   default   — realistic mixed workload (ramp 5→20→10→0 VUs)
 *   upload    — file upload stress (3 VUs sustained)
 *   export    — export endpoint stress (5 VUs sustained)
 *   autoscore — auto-score burst (10 VUs, 15s)
 *
 * Run locally (all scenarios):
 *   k6 run tests/load/k6-api.js
 *
 * Run single scenario:
 *   k6 run --env SCENARIO=upload tests/load/k6-api.js
 *
 * Run with custom target:
 *   k6 run -e BASE_URL=http://your-server:8500 -e SITE_PASSWORD=yourpass tests/load/k6-api.js
 *
 * CI usage (smoke test — 2 VUs, 15s):
 *   k6 run --vus 2 --duration 15s tests/load/k6-api.js
 */

import http from "k6/http";
import { check, sleep as k6sleep, group } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------
const errorRate = new Rate("errors");
const activityLatency = new Trend("activity_data_latency", true);
const markerSaveLatency = new Trend("marker_save_latency", true);
const uploadLatency = new Trend("upload_latency", true);
const exportLatency = new Trend("export_latency", true);
const autoScoreLatency = new Trend("auto_score_latency", true);
const diaryLatency = new Trend("diary_latency", true);
const tablesLatency = new Trend("tables_latency", true);
const uploadsCompleted = new Counter("uploads_completed");
const exportsCompleted = new Counter("exports_completed");

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const BASE_URL = __ENV.BASE_URL || "http://localhost:8500";
const SITE_PASSWORD = __ENV.SITE_PASSWORD || "testpass";
const USERNAME = __ENV.USERNAME || "loadtest";
const API = `${BASE_URL}/api/v1`;

export const options = {
  scenarios: {
    // Realistic mixed workload
    default_load: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "10s", target: 5 },
        { duration: "30s", target: 10 },
        { duration: "10s", target: 20 },
        { duration: "30s", target: 10 },
        { duration: "10s", target: 0 },
      ],
      exec: "mixedWorkload",
    },
    // Upload stress
    upload_stress: {
      executor: "constant-vus",
      vus: 3,
      duration: "30s",
      exec: "uploadWorkload",
      startTime: "5s",
    },
    // Export stress
    export_stress: {
      executor: "constant-vus",
      vus: 5,
      duration: "20s",
      exec: "exportWorkload",
      startTime: "15s",
    },
    // Auto-score burst
    autoscore_burst: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "5s", target: 10 },
        { duration: "10s", target: 10 },
        { duration: "5s", target: 0 },
      ],
      exec: "autoScoreWorkload",
      startTime: "10s",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<2000"],
    errors: ["rate<0.05"],
    activity_data_latency: ["p(95)<3000"],
    marker_save_latency: ["p(95)<1000"],
    upload_latency: ["p(95)<5000"],
    export_latency: ["p(95)<5000"],
    auto_score_latency: ["p(95)<3000"],
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const headers = {
  "X-Site-Password": SITE_PASSWORD,
  "X-Username": USERNAME,
  "Content-Type": "application/json",
};

const authHeaders = {
  "X-Site-Password": SITE_PASSWORD,
  "X-Username": USERNAME,
};

function generateCsvContent(rows) {
  const n = rows || 100;
  let csv =
    "------------ Data File Created By ActiGraph GT3X+ ActiLife v6.13.4 Firmware v3.2.1 date format M/d/yyyy Filter Normal -----------\n" +
    "Serial Number: NEO1F00000000\n" +
    "Start Time 12:00:00\n" +
    "Start Date 1/1/2024\n" +
    "Epoch Period (hh:mm:ss) 00:01:00\n" +
    "Download Time 12:00:00\n" +
    "Download Date 1/2/2024\n" +
    "Current Memory Address: 0\n" +
    "Current Battery Voltage: 4.20     Mode = 12\n" +
    "--------------------------------------------------\n" +
    "Date,Time,Axis1,Axis2,Axis3,Vector Magnitude\n";
  for (let i = 0; i < n; i++) {
    const mins = i % 60;
    const hrs = 12 + Math.floor(i / 60);
    const time = `${hrs}:${mins < 10 ? "0" + mins : mins}:00`;
    csv += `01/01/2024,${time},${(i * 7) % 150},${i % 100},${(i * 3) % 200},${i * 4}\n`;
  }
  return csv;
}

function pickRandomFile() {
  const res = http.get(`${API}/files`, { headers });
  if (res.status !== 200) return null;
  const files = JSON.parse(res.body);
  const items = files.items || files;
  if (!items || items.length === 0) return null;
  return items[Math.floor(Math.random() * items.length)];
}

function pickRandomDate(fileId) {
  const res = http.get(`${API}/files/${fileId}/dates`, { headers });
  if (res.status !== 200) return null;
  const dates = JSON.parse(res.body);
  if (!dates || dates.length === 0) return null;
  return dates[Math.floor(Math.random() * dates.length)];
}

// ---------------------------------------------------------------------------
// Scenario: Mixed workload (browsing, scoring, saving)
// ---------------------------------------------------------------------------
export function mixedWorkload() {
  group("Health check", () => {
    const res = http.get(`${BASE_URL}/health`);
    check(res, { "health 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  group("List files", () => {
    const res = http.get(`${API}/files`, { headers });
    check(res, { "files 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  const file = pickRandomFile();
  if (!file) { k6sleep(1); return; }
  const fileId = file.id;
  const date = pickRandomDate(fileId);
  if (!date) { k6sleep(1); return; }

  group("Load activity data", () => {
    const res = http.get(`${API}/activity/${fileId}/${date}/score`, { headers });
    activityLatency.add(res.timings.duration);
    check(res, { "activity 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  group("Load markers", () => {
    const res = http.get(`${API}/markers/${fileId}/${date}`, { headers });
    check(res, { "markers 200|404": (r) => r.status === 200 || r.status === 404 });
  });

  group("Load table data", () => {
    const res = http.get(`${API}/markers/${fileId}/${date}/table-full`, { headers });
    tablesLatency.add(res.timings.duration);
    check(res, { "table 200": (r) => r.status === 200 });
  });

  group("Load diary", () => {
    const res = http.get(`${API}/diary/${fileId}`, { headers });
    diaryLatency.add(res.timings.duration);
    check(res, { "diary 200": (r) => r.status === 200 });
  });

  group("Load dates status", () => {
    const res = http.get(`${API}/files/${fileId}/dates/status`, { headers });
    check(res, { "status 200": (r) => r.status === 200 });
  });

  group("Load adjacent markers", () => {
    const res = http.get(`${API}/markers/${fileId}/${date}/adjacent`, { headers });
    check(res, { "adjacent 200|404": (r) => r.status === 200 || r.status === 404 });
  });

  group("Analysis summary", () => {
    const res = http.get(`${API}/analysis/summary`, { headers });
    check(res, { "summary 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  // 30% chance to save markers (simulate active scoring)
  if (Math.random() < 0.3) {
    group("Save markers", () => {
      const payload = JSON.stringify({
        sleep_markers: [{
          onset_timestamp: 1704070800,
          offset_timestamp: 1704099600,
          marker_type: "MAIN_SLEEP",
          marker_index: 1,
        }],
        nonwear_markers: [],
        is_no_sleep: false,
        notes: `k6 load test VU ${__VU} iter ${__ITER}`,
        needs_consensus: false,
      });
      const res = http.put(`${API}/markers/${fileId}/${date}`, payload, { headers });
      markerSaveLatency.add(res.timings.duration);
      check(res, { "save 200": (r) => r.status === 200 });
      errorRate.add(res.status !== 200);
    });
  }

  k6sleep(Math.random() * 2 + 0.5); // 0.5-2.5s think time
}

// ---------------------------------------------------------------------------
// Scenario: Upload stress
// ---------------------------------------------------------------------------
export function uploadWorkload() {
  group("Upload CSV file", () => {
    const csv = generateCsvContent(200);
    const filename = `k6_upload_vu${__VU}_iter${__ITER}.csv`;

    const formData = {
      file: http.file(csv, filename, "text/csv"),
    };

    const res = http.post(`${API}/files/upload`, formData, {
      headers: authHeaders,
    });
    uploadLatency.add(res.timings.duration);

    const ok = res.status === 200 || res.status === 400; // 400 = duplicate filename
    check(res, { "upload 200|400": (r) => ok });
    errorRate.add(!ok);

    if (res.status === 200) {
      uploadsCompleted.add(1);
      const fileId = JSON.parse(res.body).file_id;

      // Verify file is accessible
      const datesRes = http.get(`${API}/files/${fileId}/dates`, { headers });
      check(datesRes, { "dates after upload 200": (r) => r.status === 200 });

      // Clean up — delete the uploaded file
      http.del(`${API}/files/${fileId}`, null, { headers });
    }
  });

  k6sleep(1);
}

// ---------------------------------------------------------------------------
// Scenario: Export stress
// ---------------------------------------------------------------------------
export function exportWorkload() {
  const file = pickRandomFile();
  if (!file) { k6sleep(1); return; }

  group("Export CSV", () => {
    const payload = JSON.stringify({
      file_ids: [file.id],
      columns: [
        "Filename", "Study Date", "Period Index", "Marker Type",
        "Onset Time", "Offset Time", "Total Sleep Time (min)",
        "Sleep Efficiency (%)", "WASO (min)", "Algorithm",
      ],
      include_metadata: true,
    });
    const res = http.post(`${API}/export/csv`, payload, { headers });
    exportLatency.add(res.timings.duration);
    check(res, { "export 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
    if (res.status === 200) exportsCompleted.add(1);
  });

  group("Quick export", () => {
    const res = http.get(`${API}/export/quick?file_ids=${file.id}`, { headers });
    exportLatency.add(res.timings.duration);
    check(res, { "quick export 200": (r) => r.status === 200 });
  });

  group("Export columns", () => {
    const res = http.get(`${API}/export/columns`, { headers });
    check(res, { "columns 200": (r) => r.status === 200 });
  });

  k6sleep(0.5);
}

// ---------------------------------------------------------------------------
// Scenario: Auto-score burst
// ---------------------------------------------------------------------------
export function autoScoreWorkload() {
  const file = pickRandomFile();
  if (!file) { k6sleep(1); return; }
  const date = pickRandomDate(file.id);
  if (!date) { k6sleep(1); return; }

  group("Auto-score", () => {
    const res = http.post(
      `${API}/markers/${file.id}/${date}/auto-score?algorithm=sadeh_1994_actilife&onset_epochs=3&offset_minutes=5&detection_rule=consecutive_onset3s_offset5s`,
      null,
      { headers }
    );
    autoScoreLatency.add(res.timings.duration);
    check(res, { "autoscore 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);

    if (res.status === 200) {
      const body = JSON.parse(res.body);
      check(body, {
        "has sleep_markers": (b) => Array.isArray(b.sleep_markers),
        "has notes": (b) => Array.isArray(b.notes),
      });
    }
  });

  group("Auto-nonwear", () => {
    const res = http.post(
      `${API}/markers/${file.id}/${date}/auto-nonwear?threshold=2`,
      null,
      { headers }
    );
    check(res, { "auto-nonwear 200": (r) => r.status === 200 });
  });

  group("Get auto-score result", () => {
    const res = http.get(`${API}/markers/${file.id}/${date}/auto-score-result`, { headers });
    check(res, { "result 200|404": (r) => r.status === 200 || r.status === 404 });
  });

  k6sleep(0.5);
}
