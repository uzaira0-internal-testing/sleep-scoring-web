#!/usr/bin/env bash
# Autoresearch: API latency benchmark
# Measures p99 response time across key endpoints
set -euo pipefail

cd "$(dirname "$0")/../.."

METRIC_NAME="p99_ms"
RUNS=3

# ── Step 1: Pre-check (health endpoint) ──────────────────────────────
echo "=== Pre-checks ==="
if ! curl -sf http://localhost:8500/health > /dev/null 2>&1; then
  echo "FATAL: backend not healthy"
  exit 1
fi
echo "Backend healthy."
echo ""

# ── Step 2: Benchmark (N runs, take best) ────────────────────────────
echo "=== Benchmark ($RUNS runs) ==="
BEST=999999999

for i in $(seq 1 $RUNS); do
  # Hit key endpoints and measure response times
  TIMES=""
  AUTH_HEADER="X-Site-Password: $(docker exec sleep-scoring-backend printenv SITE_PASSWORD 2>/dev/null)"
  for endpoint in \
    "http://localhost:8500/health" \
    "http://localhost:8500/api/v1/files" \
    "http://localhost:8500/api/v1/studies"; do
    # Time in ms, capture just the time_total
    T=$(curl -s -o /dev/null -w '%{time_total}' -H "$AUTH_HEADER" "$endpoint" 2>/dev/null)
    MS=$(echo "$T * 1000" | bc)
    TIMES="$TIMES $MS"
  done

  # Calculate p99 (since we have few endpoints, use max as proxy)
  P99=$(echo "$TIMES" | tr ' ' '\n' | grep -v '^$' | sort -n | tail -1)
  P99_INT=$(echo "$P99" | cut -d. -f1)

  echo "  run $i: p99_ms=${P99}"

  if [ "$P99_INT" -lt "$BEST" ]; then
    BEST=$P99_INT
    BEST_RAW=$P99
  fi
done

if [ "$BEST" = "999999999" ]; then
  echo "FATAL: no valid benchmark results"
  exit 1
fi

echo ""
echo "METRIC p99_ms=${BEST_RAW}"
