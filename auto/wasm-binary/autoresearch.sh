#!/usr/bin/env bash
# Autoresearch: WASM binary size + throughput benchmark
# Uses cargo-bloat, twiggy for size analysis + criterion for throughput
set -euo pipefail
cd "$(dirname "$0")/../.."

METRIC_NAME="wasm_kb"

echo "=== Pre-checks ==="
. ~/.cargo/env 2>/dev/null || true
if ! command -v wasm-pack &>/dev/null; then
  echo "FATAL: wasm-pack not found"
  exit 1
fi

cd packages/sleep-scoring-wasm/crates/algorithms

# Run tests first
echo "=== Running cargo tests ==="
cargo test --quiet 2>&1 || { echo "FATAL: cargo test failed"; exit 1; }

# Run criterion benchmarks if available
echo "=== Running criterion benchmarks ==="
cargo bench 2>&1 | tee /tmp/criterion-output.txt || echo "WARN: benchmarks had issues"

# Build WASM
echo "=== Building WASM ==="
wasm-pack build --target web --out-dir /tmp/autoresearch-wasm-pkg 2>&1

WASM_FILE=$(ls -1 /tmp/autoresearch-wasm-pkg/*.wasm 2>/dev/null | head -1)
if [ -z "$WASM_FILE" ]; then
  echo "FATAL: no .wasm file produced"
  exit 1
fi

SIZE_BYTES=$(stat -c%s "$WASM_FILE")
SIZE_KB=$(echo "scale=1; $SIZE_BYTES / 1024" | bc)

# Run twiggy for size dominators
echo "=== Twiggy size dominators ==="
if command -v twiggy &>/dev/null; then
  twiggy top "$WASM_FILE" -n 15 2>/dev/null || echo "WARN: twiggy failed"
  echo ""
  twiggy dominators "$WASM_FILE" -d 3 2>/dev/null | head -30 || echo "WARN: twiggy dominators failed"
fi

# Run cargo-bloat for function-level analysis
echo "=== cargo-bloat analysis ==="
if command -v cargo-bloat &>/dev/null; then
  cargo bloat --release -n 15 2>/dev/null || echo "WARN: cargo-bloat failed"
fi

echo ""
echo "WASM file: $WASM_FILE"
echo "Size: ${SIZE_KB} KB (${SIZE_BYTES} bytes)"
echo ""
echo "METRIC ${METRIC_NAME}=${SIZE_KB}"
