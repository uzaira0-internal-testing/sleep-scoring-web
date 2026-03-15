/**
 * k6 load test for Sleep Scoring Web API.
 *
 * Simulates concurrent researchers uploading files, scoring dates,
 * and exporting results.
 *
 * Run locally:
 *   k6 run tests/load/k6-api.js
 *
 * Run with custom target:
 *   k6 run -e BASE_URL=http://your-server:8500 -e SITE_PASSWORD=yourpass tests/load/k6-api.js
 *
 * CI usage (smoke test — 1 VU, 10s):
 *   k6 run --vus 1 --duration 10s tests/load/k6-api.js
 */

import http from "k6/http";
import { check, sleep as k6sleep, group } from "k6";
import { Rate, Trend } from "k6/metrics";

// Custom metrics
const errorRate = new Rate("errors");
const activityLatency = new Trend("activity_data_latency", true);
const markerSaveLatency = new Trend("marker_save_latency", true);

// Configuration
const BASE_URL = __ENV.BASE_URL || "http://localhost:8500";
const SITE_PASSWORD = __ENV.SITE_PASSWORD || "testpass";
const USERNAME = __ENV.USERNAME || "loadtest";

export const options = {
  stages: [
    { duration: "10s", target: 5 },   // Ramp up to 5 users
    { duration: "30s", target: 10 },   // Hold at 10 users
    { duration: "10s", target: 20 },   // Spike to 20 users
    { duration: "30s", target: 10 },   // Back to 10
    { duration: "10s", target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<2000"],  // 95% of requests under 2s
    errors: ["rate<0.05"],              // Error rate under 5%
    activity_data_latency: ["p(95)<3000"], // Activity data under 3s
    marker_save_latency: ["p(95)<1000"],   // Marker save under 1s
  },
};

const headers = {
  "X-Site-Password": SITE_PASSWORD,
  "X-Username": USERNAME,
  "Content-Type": "application/json",
};

export default function () {
  group("Health check", () => {
    const res = http.get(`${BASE_URL}/health`);
    check(res, { "health 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  group("List files", () => {
    const res = http.get(`${BASE_URL}/api/v1/files`, { headers });
    check(res, { "files 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);

    if (res.status === 200) {
      const files = JSON.parse(res.body);
      const items = files.items || files;

      if (items.length > 0) {
        const file = items[Math.floor(Math.random() * items.length)];
        const fileId = file.id;

        group("Load activity data", () => {
          // Get dates for this file
          const datesRes = http.get(
            `${BASE_URL}/api/v1/files/${fileId}/dates`,
            { headers }
          );

          if (datesRes.status === 200) {
            const dates = JSON.parse(datesRes.body);
            if (dates.length > 0) {
              const date = dates[Math.floor(Math.random() * dates.length)];

              // Load activity data (the heaviest endpoint)
              const actRes = http.get(
                `${BASE_URL}/api/v1/activity/${fileId}/${date}/score`,
                { headers }
              );
              activityLatency.add(actRes.timings.duration);
              check(actRes, { "activity 200": (r) => r.status === 200 });
              errorRate.add(actRes.status !== 200);

              // Load markers
              const markersRes = http.get(
                `${BASE_URL}/api/v1/markers/${fileId}/${date}`,
                { headers }
              );
              check(markersRes, {
                "markers 200 or 404": (r) =>
                  r.status === 200 || r.status === 404,
              });

              // Save markers (simulate scoring)
              if (Math.random() < 0.3) {
                const payload = JSON.stringify({
                  sleep_markers: [],
                  nonwear_markers: [],
                  is_no_sleep: false,
                  notes: "",
                  needs_consensus: false,
                });
                const saveRes = http.put(
                  `${BASE_URL}/api/v1/markers/${fileId}/${date}`,
                  payload,
                  { headers }
                );
                markerSaveLatency.add(saveRes.timings.duration);
                check(saveRes, { "save 200": (r) => r.status === 200 });
                errorRate.add(saveRes.status !== 200);
              }
            }
          }
        });
      }
    }
  });

  group("Analysis summary", () => {
    const res = http.get(`${BASE_URL}/api/v1/analysis/summary`, { headers });
    check(res, { "summary 200": (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  k6sleep(1); // Think time between iterations
}
