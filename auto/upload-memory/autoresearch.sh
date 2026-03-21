#!/usr/bin/env bash
# Autoresearch: Upload peak memory benchmark
# Uses memray for memory profiling of the upload/insert pipeline
set -euo pipefail
cd "$(dirname "$0")/../.."

METRIC_NAME="peak_rss_mb"

echo "=== Pre-checks ==="
if ! uv run python -c "import memray" 2>/dev/null; then
  echo "WARN: memray not available"
fi

# Profile the bulk_insert pathway with memray
echo "=== Memray upload pipeline profiling ==="
MEMRAY_OUT="/tmp/memray-upload-bench.bin"
uv run python -m memray run -o "$MEMRAY_OUT" --force -c "
import random, time

# Generate synthetic CSV-like data (simulating what bulk_insert_activity_data receives)
rng = random.Random(42)
n_rows = 10080  # 7 days of 1-min epochs

# Simulate the DataFrame that would come from CSV loading
import pandas as pd
import numpy as np

timestamps = [946684800.0 + i * 60.0 for i in range(n_rows)]
data = {
    'timestamp': timestamps,
    'axis_x': [float(rng.randint(0, 500)) for _ in range(n_rows)],
    'axis_y': [float(rng.randint(0, 500)) for _ in range(n_rows)],
    'axis_z': [float(rng.randint(0, 300)) for _ in range(n_rows)],
    'vector_magnitude': [float(rng.randint(0, 800)) for _ in range(n_rows)],
    'steps': [float(rng.randint(0, 20)) for _ in range(n_rows)],
}
df = pd.DataFrame(data)

# Simulate the copy + itertuples pattern from bulk_insert_activity_data
start = time.perf_counter()
export_df = df.copy()
rows = [(1, r.timestamp, 'epoch', r.axis_x, r.axis_y, r.axis_z, r.vector_magnitude, r.steps, 0, i)
        for i, r in enumerate(export_df.itertuples(index=False))]
elapsed = (time.perf_counter() - start) * 1000
print(f'bulk_insert simulation: {elapsed:.0f}ms for {n_rows} rows, {len(rows)} tuples')
" 2>&1 || echo "WARN: memray profiling had issues"

# Get peak memory from memray
echo "=== Memray stats ==="
if [ -f "$MEMRAY_OUT" ]; then
  PEAK_LINE=$(uv run python -m memray stats "$MEMRAY_OUT" 2>/dev/null | grep -i "peak\|total" | head -3)
  echo "$PEAK_LINE"
  PEAK_MB=$(echo "$PEAK_LINE" | grep -oP '[0-9.]+\s*MB' | head -1 | grep -oP '[0-9.]+' || echo "0")
fi

# Also measure container RSS if backend is running
if curl -sf http://localhost:8500/health > /dev/null 2>&1; then
  BACKEND_PID=$(docker exec sleep-scoring-backend pgrep -f "uvicorn" | head -1 2>/dev/null || echo "")
  if [ -n "$BACKEND_PID" ]; then
    PEAK_HWM=$(docker exec sleep-scoring-backend cat /proc/$BACKEND_PID/status | grep VmHWM | awk '{print $2}')
    PEAK_MB=$(echo "scale=1; $PEAK_HWM / 1024" | bc)
    echo "Container VmHWM: ${PEAK_MB} MB"
  fi
fi

echo ""
echo "METRIC ${METRIC_NAME}=${PEAK_MB:-0}"
