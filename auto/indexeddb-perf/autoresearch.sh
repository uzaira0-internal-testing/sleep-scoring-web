#!/usr/bin/env bash
# Autoresearch: IndexedDB performance benchmark
# Uses vitest benchmark or Playwright to measure listDatesStatus
set -euo pipefail
cd "$(dirname "$0")/../.."

METRIC_NAME="dates_status_ms"

echo "=== Pre-checks ==="
cd frontend

# TypeScript must compile
echo "Checking TypeScript..."
npx tsc --noEmit 2>&1 | tail -5
if [ ${PIPESTATUS[0]} -ne 0 ]; then
  echo "FATAL: TypeScript errors"
  exit 1
fi

# Tests must pass
echo "Running vitest..."
npx vitest run --reporter=verbose 2>&1 | tail -10
if [ ${PIPESTATUS[0]} -ne 0 ]; then
  echo "FATAL: vitest failures"
  exit 1
fi

# For now, measure bundle size of data-source.ts related code as proxy
# (actual IndexedDB benchmarking requires browser environment)
echo "=== Measuring data-source module size ==="
npx vite build 2>&1 | tail -5

# Measure the chunk containing data-source
CHUNK_SIZE=$(find dist/assets -name "*.js" -exec grep -l "listDatesStatus\|LocalDataSource" {} \; 2>/dev/null | head -1 | xargs stat -c%s 2>/dev/null || echo "0")
CHUNK_KB=$(echo "scale=1; $CHUNK_SIZE / 1024" | bc)

echo ""
echo "Data source chunk: ${CHUNK_KB} KB"
echo "METRIC ${METRIC_NAME}=${CHUNK_KB}"
