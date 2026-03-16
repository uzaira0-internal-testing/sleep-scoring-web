#!/usr/bin/env bash
# Autoresearch: Frontend bundle size benchmark
# Measures total JS+CSS output after vite build
set -euo pipefail

cd "$(dirname "$0")/../../frontend"

METRIC_NAME="bundle_kb"
RUNS=1  # Build is deterministic, 1 run is enough

# ── Pre-check: typecheck ─────────────────────────────────────────────
echo "=== Pre-checks ==="
if ! npx tsc -p tsconfig.app.json --noEmit 2>&1; then
  echo "FATAL: typecheck failed"
  exit 1
fi
echo "Typecheck passed."
echo ""

echo "=== Benchmark ==="

# Build
npx vite build 2>&1 | tail -10

# Measure total size of JS + CSS in dist/assets/
TOTAL_BYTES=$(find dist/assets/ -name '*.js' -o -name '*.css' | xargs du -cb 2>/dev/null | tail -1 | cut -f1)
TOTAL_KB=$((TOTAL_BYTES / 1024))

echo ""
echo "  Total JS+CSS: ${TOTAL_KB} KB"
echo ""
echo "METRIC bundle_kb=${TOTAL_KB}"
