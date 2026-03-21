#!/usr/bin/env bash
# Autoresearch: TypeScript compile time benchmark
# Uses hyperfine if available for statistical benchmarking, falls back to manual timing
# IMPORTANT: Only one tsc process at a time (OOM risk)
set -euo pipefail
cd "$(dirname "$0")/../.."

METRIC_NAME="tsc_seconds"

echo "=== Pre-checks ==="
# Kill any existing tsc processes
pkill -f "tsc --noEmit" 2>/dev/null || true
sleep 2

cd frontend

if command -v hyperfine &>/dev/null; then
  echo "=== Benchmark with hyperfine (3 runs, 1 warmup) ==="
  # hyperfine gives proper statistical analysis
  hyperfine --warmup 1 --runs 3 --export-json /tmp/tsc-hyperfine.json \
    "npx tsc --noEmit" 2>&1

  # Extract median from hyperfine JSON
  MEDIAN=$(python3 -c "import json; d=json.load(open('/tmp/tsc-hyperfine.json')); print(f'{d[\"results\"][0][\"median\"]:.2f}')" 2>/dev/null || echo "0")
  echo ""
  echo "METRIC ${METRIC_NAME}=${MEDIAN}"
else
  echo "=== Benchmark with manual timing (3 runs) ==="
  BEST=999999

  for i in 1 2 3; do
    pkill -f "tsc --noEmit" 2>/dev/null || true
    sleep 1

    START=$(date +%s%N)
    npx tsc --noEmit 2>&1 | tail -3
    EXIT_CODE=${PIPESTATUS[0]}
    END=$(date +%s%N)

    if [ $EXIT_CODE -ne 0 ]; then
      echo "FATAL: tsc failed"
      exit 1
    fi

    ELAPSED_NS=$((END - START))
    ELAPSED_S=$(echo "scale=2; $ELAPSED_NS / 1000000000" | bc)
    echo "  run $i: ${ELAPSED_S}s"

    ELAPSED_INT=$(echo "$ELAPSED_S" | cut -d. -f1)
    if [ "${ELAPSED_INT:-999}" -lt "$BEST" ]; then
      BEST=$ELAPSED_INT
      BEST_RAW=$ELAPSED_S
    fi
  done

  echo ""
  echo "METRIC ${METRIC_NAME}=${BEST_RAW}"
fi
