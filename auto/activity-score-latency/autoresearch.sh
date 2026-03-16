#!/usr/bin/env bash
# Autoresearch: Activity score endpoint latency benchmark
# Uses server-side duration_ms from backend logs for accurate measurement
# (curl round-trip includes Docker networking overhead that dwarfs actual latency)
set -euo pipefail
cd "$(dirname "$0")/../.."

METRIC_NAME="p50_ms"
RUNS=20

echo "=== Pre-checks ==="

# Find the actual container name (may have hash prefix from Docker Compose conflicts)
BACKEND_CONTAINER=$(docker ps --format '{{.Names}}' | grep -m1 'sleep-scoring-backend' || echo "")
if [ -z "$BACKEND_CONTAINER" ]; then
  echo "FATAL: sleep-scoring-backend container not found"
  exit 1
fi

if ! curl -sf http://localhost:8500/health > /dev/null 2>&1; then
  echo "FATAL: backend not healthy"
  exit 1
fi

SITE_PW="$(docker exec "$BACKEND_CONTAINER" printenv SITE_PASSWORD 2>/dev/null || echo 'DACAdminTest123')"
AUTH_HEADER="X-Site-Password: ${SITE_PW}"
USER_HEADER="X-Username: admin"

# Find a file and date with activity data
# Try file 78 first (stable real data), fall back to auto-detection
FILE_ID=78
DATE=$(curl -s -H "$AUTH_HEADER" -H "$USER_HEADER" "http://localhost:8500/api/v1/files/${FILE_ID}/dates/status" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['date'] if d else '')" 2>/dev/null || echo "")
if [ -z "$DATE" ]; then
  # Fallback: find any file
  FILE_ID=$(curl -s -H "$AUTH_HEADER" -H "$USER_HEADER" http://localhost:8500/api/v1/files | python3 -c "import sys,json; d=json.load(sys.stdin); items=d.get('items',d) if isinstance(d,dict) else d; print(items[0]['id'] if items else '')" 2>/dev/null || echo "")
  if [ -z "$FILE_ID" ]; then
    echo "FATAL: no files found"; exit 1
  fi
  DATE=$(curl -s -H "$AUTH_HEADER" -H "$USER_HEADER" "http://localhost:8500/api/v1/files/${FILE_ID}/dates/status" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['date'] if d else '')" 2>/dev/null || echo "")
  if [ -z "$DATE" ]; then
    echo "FATAL: no dates found"; exit 1
  fi
fi

echo "Using file_id=$FILE_ID date=$DATE container=$BACKEND_CONTAINER"

# Warm up (3 requests to prime caches)
for i in 1 2 3; do
  curl -s -o /dev/null -H "$AUTH_HEADER" -H "$USER_HEADER" "http://localhost:8500/api/v1/activity/${FILE_ID}/${DATE}/score?fields=available_dates" 2>/dev/null
done

# Record log line count before benchmark
LOG_OFFSET=$(docker logs "$BACKEND_CONTAINER" 2>&1 | wc -l)

echo "=== Benchmark ($RUNS runs) ==="
for i in $(seq 1 $RUNS); do
  curl -s -o /dev/null -H "$AUTH_HEADER" -H "$USER_HEADER" "http://localhost:8500/api/v1/activity/${FILE_ID}/${DATE}/score?fields=available_dates" 2>/dev/null
done

# Extract server-side duration_ms from backend logs (strip ANSI escapes first)
TIMES=$(docker logs "$BACKEND_CONTAINER" 2>&1 | tail -n +"$LOG_OFFSET" | sed 's/\x1b\[[0-9;]*m//g' | grep 'score' | grep -oP 'duration_ms=\K[\d.]+' | tail -n "$RUNS")

COUNT=$(echo "$TIMES" | wc -l)
if [ "$COUNT" -lt "$RUNS" ]; then
  echo "WARNING: only found $COUNT timing entries (expected $RUNS)"
fi

# Print individual times
I=1
for T in $TIMES; do
  echo "  run $I: ${T}ms"
  I=$((I + 1))
done

# Calculate p50
SORTED=$(echo "$TIMES" | sort -n)
P50_IDX=$(( (COUNT + 1) / 2 ))
P50=$(echo "$SORTED" | sed -n "${P50_IDX}p")

echo ""
echo "METRIC ${METRIC_NAME}=${P50}"
