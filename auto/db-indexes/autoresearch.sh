#!/usr/bin/env bash
# Autoresearch: DB index optimization benchmark
# Uses k6 for proper load testing + SLOW_QUERY_THRESHOLD_MS for diagnostics
set -euo pipefail
cd "$(dirname "$0")/../.."

METRIC_NAME="query_ms"

echo "=== Pre-checks ==="
if ! curl -sf http://localhost:8500/health > /dev/null 2>&1; then
  echo "FATAL: backend not healthy"
  exit 1
fi

if ! command -v k6 &>/dev/null; then
  echo "FATAL: k6 not installed"
  exit 1
fi

SITE_PASSWORD=$(docker exec sleep-scoring-backend printenv SITE_PASSWORD 2>/dev/null || echo 'DACAdminTest123')

echo "=== k6 mixed query benchmark (5 VUs, 20s) ==="
cat > /tmp/k6-db-indexes.js << 'EOFK6'
import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const queryLatency = new Trend("query_latency", true);
const filesLatency = new Trend("files_latency", true);
const datesLatency = new Trend("dates_latency", true);
const markersLatency = new Trend("markers_latency", true);

const BASE_URL = __ENV.BASE_URL || "http://localhost:8500";
const API = `${BASE_URL}/api/v1`;
const headers = {
  "X-Site-Password": __ENV.SITE_PASSWORD || "testpass",
  "X-Username": "benchmark",
};

export const options = {
  vus: 5,
  duration: "20s",
  thresholds: {
    query_latency: ["p(95)<500"],
  },
};

export function setup() {
  const res = http.get(`${API}/files`, { headers });
  const files = JSON.parse(res.body);
  const items = files.items || files;
  if (!items || items.length === 0) return { fileId: null, date: null };
  const fileId = items[0].id;
  const datesRes = http.get(`${API}/files/${fileId}/dates/status`, { headers });
  const dates = JSON.parse(datesRes.body);
  return { fileId, date: dates && dates.length > 0 ? dates[0].date : null };
}

export default function (data) {
  if (!data.fileId) return;

  // Test multiple query-heavy endpoints
  const r1 = http.get(`${API}/files`, { headers });
  filesLatency.add(r1.timings.duration);
  queryLatency.add(r1.timings.duration);

  const r2 = http.get(`${API}/files/${data.fileId}/dates/status`, { headers });
  datesLatency.add(r2.timings.duration);
  queryLatency.add(r2.timings.duration);

  if (data.date) {
    const r3 = http.get(`${API}/markers/${data.fileId}/${data.date}`, { headers });
    markersLatency.add(r3.timings.duration);
    queryLatency.add(r3.timings.duration);
  }

  check(r1, { "files ok": (r) => r.status === 200 });
  check(r2, { "dates ok": (r) => r.status === 200 });
}
EOFK6

k6 run --quiet --summary-trend-stats="min,avg,med,p(90),p(95),p(99),max" \
  -e SITE_PASSWORD="$SITE_PASSWORD" \
  /tmp/k6-db-indexes.js 2>&1 | tee /tmp/k6-db-indexes-output.txt

# Extract p95 worst-case from k6
P95=$(grep "query_latency" /tmp/k6-db-indexes-output.txt | grep -oP 'p\(95\)=\K[0-9.]+' || echo "0")

echo ""
echo "METRIC ${METRIC_NAME}=${P95}"
