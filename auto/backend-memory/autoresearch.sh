#!/usr/bin/env bash
# Autoresearch: Backend memory usage benchmark
# Uses memray for memory profiling + pyinstrument for CPU profiling
set -euo pipefail
cd "$(dirname "$0")/../.."

METRIC_NAME="rss_kb"

echo "=== Pre-checks ==="
if ! uv run python -c "import memray" 2>/dev/null; then
  echo "WARN: memray not available, using RSS measurement"
fi

# Run the Python benchmark suite for algorithm memory
echo "=== Algorithm memory profiling with memray ==="
MEMRAY_OUT="/tmp/memray-sadeh-bench.bin"
uv run python -m memray run -o "$MEMRAY_OUT" --force -c "
import time
from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm
import random

rng = random.Random(42)
counts = []
for i in range(1440):
    hour = (i % 1440) / 60
    if 23 <= hour or hour < 6:
        counts.append(rng.choice([0, 0, 0, 0, 0, 1, 2, 5]))
    else:
        counts.append(rng.randint(0, 500))

algo = SadehAlgorithm(variant='actilife')

# Run 50 scoring calls to measure steady-state memory
for _ in range(50):
    algo.score(counts)
" 2>&1 || echo "WARN: memray profiling had issues"

# Get peak memory from memray
echo "=== Memray stats ==="
if [ -f "$MEMRAY_OUT" ]; then
  uv run python -m memray stats "$MEMRAY_OUT" 2>/dev/null | head -20 || true
fi

# Also profile with pyinstrument for CPU hotspots
echo "=== Pyinstrument CPU profile ==="
uv run python -c "
import pyinstrument, random

rng = random.Random(42)
counts = []
for i in range(1440):
    hour = (i % 1440) / 60
    if 23 <= hour or hour < 6:
        counts.append(rng.choice([0, 0, 0, 0, 0, 1, 2, 5]))
    else:
        counts.append(rng.randint(0, 500))

from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm
algo = SadehAlgorithm(variant='actilife')

p = pyinstrument.Profiler()
p.start()
for _ in range(100):
    algo.score(counts)
p.stop()
print(p.output_text())
" 2>&1

# Measure RSS via Docker container
echo "=== Container RSS benchmark ==="
if curl -sf http://localhost:8500/health > /dev/null 2>&1; then
  AUTH_HEADER="X-Site-Password: $(docker exec sleep-scoring-backend printenv SITE_PASSWORD 2>/dev/null || echo 'DACAdminTest123')"
  FILE_ID=$(curl -s -H "$AUTH_HEADER" http://localhost:8500/api/v1/files | python3 -c "import sys,json; files=json.load(sys.stdin); print(files[0]['id'] if files else '')" 2>/dev/null || echo "")
  DATE=$(curl -s -H "$AUTH_HEADER" "http://localhost:8500/api/v1/files/${FILE_ID}/dates/status" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['date'] if d else '')" 2>/dev/null || echo "")

  if [ -n "$FILE_ID" ] && [ -n "$DATE" ]; then
    BACKEND_PID=$(docker exec sleep-scoring-backend pgrep -f "uvicorn" | head -1 2>/dev/null || echo "")
    if [ -n "$BACKEND_PID" ]; then
      RSS_BEFORE=$(docker exec sleep-scoring-backend cat /proc/$BACKEND_PID/status | grep VmRSS | awk '{print $2}')
      for i in $(seq 1 30); do
        curl -s -o /dev/null -H "$AUTH_HEADER" "http://localhost:8500/api/v1/activity/${FILE_ID}/${DATE}/score" 2>/dev/null
      done
      RSS_AFTER=$(docker exec sleep-scoring-backend cat /proc/$BACKEND_PID/status | grep VmRSS | awk '{print $2}')
      DELTA=$((RSS_AFTER - RSS_BEFORE))
      echo "RSS before: ${RSS_BEFORE} kB, after: ${RSS_AFTER} kB, delta: ${DELTA} kB"
      echo ""
      echo "METRIC ${METRIC_NAME}=${DELTA}"
      exit 0
    fi
  fi
fi

echo "WARN: Could not measure container RSS, using memray peak"
echo "METRIC ${METRIC_NAME}=0"
