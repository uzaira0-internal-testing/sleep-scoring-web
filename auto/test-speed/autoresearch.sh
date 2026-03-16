#!/usr/bin/env bash
# Autoresearch: Test suite speed benchmark
# Measures total duration of the backend test suite
set -euo pipefail

cd "$(dirname "$0")/../.."

METRIC_NAME="duration_ms"
RUNS=3

echo "=== Benchmark ($RUNS runs) ==="
BEST=999999999

for i in $(seq 1 $RUNS); do
  START_NS=$(date +%s%N)
  uv run pytest tests/web/ -x -q \
    --ignore=tests/web/test_schema_fuzzing.py \
    --ignore=tests/unit/services \
    --ignore=tests/unit/ui \
    --ignore=tests/unit/core \
    --ignore=tests/unit/io \
    --tb=no --no-header 2>&1 | tail -3
  END_NS=$(date +%s%N)

  ELAPSED_MS=$(( (END_NS - START_NS) / 1000000 ))
  echo "  run $i: duration_ms=${ELAPSED_MS}"

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
echo "METRIC duration_ms=${BEST_RAW}"
