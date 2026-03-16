#!/usr/bin/env bash
# Autoresearch: DB query parallelism benchmark
# Uses k6 for proper load testing with percentile metrics
set -euo pipefail
cd "$(dirname "$0")/../.."

METRIC_NAME="p50_ms"

echo "=== Pre-checks ==="
if ! curl -sf http://localhost:8500/health > /dev/null 2>&1; then
  echo "FATAL: backend not healthy"
  exit 1
fi

if ! command -v k6 &>/dev/null; then
  echo "FATAL: k6 not installed"
  exit 1
fi

BACKEND_CONTAINER=$(docker ps --format '{{.Names}}' | grep sleep-scoring-backend | head -1)
SITE_PASSWORD=$(docker exec "$BACKEND_CONTAINER" printenv SITE_PASSWORD 2>/dev/null || echo 'DACAdminTest123')

# Enable slow query logging in backend for diagnostics
docker exec "$BACKEND_CONTAINER" sh -c 'export SLOW_QUERY_THRESHOLD_MS=50' 2>/dev/null || true

echo "=== k6 dates/status benchmark (10 VUs, 30s) ==="
# Write a focused k6 script for dates/status
cat > /tmp/k6-dates-status.js << 'EOFK6'
import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const datesStatusLatency = new Trend("dates_status_latency", true);

const BASE_URL = __ENV.BASE_URL || "http://localhost:8500";
const API = `${BASE_URL}/api/v1`;
const headers = {
  "X-Site-Password": __ENV.SITE_PASSWORD || "testpass",
  "X-Username": __ENV.USERNAME || "Uzair",
};

export const options = {
  vus: 5,
  duration: "20s",
  thresholds: {
    dates_status_latency: ["p(50)<500", "p(95)<2000"],
  },
};

let fileId = null;

export function setup() {
  const res = http.get(`${API}/files`, { headers });
  const files = JSON.parse(res.body);
  const items = files.items || files;
  return { fileId: items && items.length > 0 ? items[0].id : null };
}

export default function (data) {
  if (!data.fileId) return;
  const res = http.get(`${API}/files/${data.fileId}/dates/status`, { headers });
  datesStatusLatency.add(res.timings.duration);
  check(res, { "status 200": (r) => r.status === 200 });
}
EOFK6

k6 run --quiet --summary-trend-stats="min,avg,med,p(90),p(95),p(99),max" \
  -e SITE_PASSWORD="$SITE_PASSWORD" \
  -e USERNAME="Uzair" \
  /tmp/k6-dates-status.js 2>&1 | tee /tmp/k6-dates-status-output.txt

# Extract p50 (med) from k6 output (strip ANSI codes first)
sed -i 's/\x1b\[[0-9;]*m//g' /tmp/k6-dates-status-output.txt
P50=$(grep "dates_status_latency" /tmp/k6-dates-status-output.txt | grep -oP 'med=\K[0-9.]+' || echo "0")
if [ "$P50" = "0" ]; then
  # Fallback: parse differently
  P50=$(grep "dates_status_latency" /tmp/k6-dates-status-output.txt | awk '{for(i=1;i<=NF;i++) if($i ~ /med=/) {gsub(/[^0-9.]/,"",$i); print $i}}')
fi

echo ""
echo "METRIC ${METRIC_NAME}=${P50}"
