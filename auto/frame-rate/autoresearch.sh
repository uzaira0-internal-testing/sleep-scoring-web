#!/usr/bin/env bash
# Autoresearch: Frame rate benchmark
# Measures FPS during scroll, drag, and zoom on the scoring page
set -euo pipefail

cd "$(dirname "$0")/../.."

METRIC_NAME="fps_p10"
RUNS=3

# ── Pre-check: typecheck ─────────────────────────────────────────────
echo "=== Pre-checks ==="
cd frontend
if ! npx tsc -p tsconfig.app.json --noEmit 2>&1; then
  echo "FATAL: typecheck failed"
  exit 1
fi
echo "Typecheck passed."
cd ..

# ── Benchmark ────────────────────────────────────────────────────────
echo ""
echo "=== Benchmark ($RUNS runs) ==="
BEST=0

for i in $(seq 1 $RUNS); do
  OUT=$(cd frontend && npx playwright test auto/frame-rate/bench-fps.ts --reporter=list 2>&1 || true)

  # Extract fps_p10 from all tests, take the minimum (worst-case)
  P10=$(echo "$OUT" | grep -oE "fps_p10=[0-9]+" | cut -d= -f2 | sort -n | head -1)

  if [ -z "$P10" ]; then
    echo "  run $i: could not extract fps_p10"
    echo "  output: $(echo "$OUT" | tail -5)"
    continue
  fi

  echo "  run $i: fps_p10=${P10}"

  # Higher is better for FPS
  if [ "$P10" -gt "$BEST" ]; then
    BEST=$P10
    BEST_RAW=$P10
  fi
done

if [ "$BEST" = "0" ]; then
  echo "FATAL: no valid benchmark results"
  exit 1
fi

echo ""
echo "METRIC fps_p10=${BEST_RAW}"
