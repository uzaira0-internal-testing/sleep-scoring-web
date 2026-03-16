#!/usr/bin/env bash
# Autoresearch: Backend startup time benchmark
# Measures time from process start to first healthy response
# NOTE: no set -e because we background+kill processes

cd "$(dirname "$0")/.."

METRIC_NAME="startup_ms"
RUNS=3
PORT=8599

# Clean up stale processes
pkill -f "uvicorn.*${PORT}" 2>/dev/null || true
sleep 0.5

echo "=== Benchmark ($RUNS runs) ==="
BEST=999999999
BEST_RAW=""

for i in $(seq 1 $RUNS); do
  START_NS=$(date +%s%N)

  UPLOAD_DIR=/tmp/bench_uploads TUS_UPLOAD_DIR=/tmp/bench_tus DATA_DIR=/tmp/bench_data \
  uv run uvicorn sleep_scoring_web.main:app \
    --host 127.0.0.1 --port $PORT \
    --log-level warning > /dev/null 2>&1 &
  PID=$!

  # Poll for health (max 30s)
  HEALTHY=0
  for attempt in $(seq 1 300); do
    if curl -sf "http://127.0.0.1:${PORT}/health" > /dev/null 2>&1; then
      HEALTHY=1
      break
    fi
    sleep 0.1
  done

  END_NS=$(date +%s%N)

  # Kill in subshell to avoid signal propagation issues
  (kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null) || true
  sleep 0.3

  if [ "$HEALTHY" = "0" ]; then
    echo "  run $i: FAILED (timeout)"
    continue
  fi

  ELAPSED_MS=$(( (END_NS - START_NS) / 1000000 ))
  echo "  run $i: startup_ms=${ELAPSED_MS}"

  if [ "$ELAPSED_MS" -lt "$BEST" ]; then
    BEST=$ELAPSED_MS
    BEST_RAW=$ELAPSED_MS
  fi
done

if [ "$BEST" = "999999999" ]; then
  echo "FATAL: no valid benchmark results"
  exit 1
fi

echo ""
echo "METRIC startup_ms=${BEST_RAW}"
