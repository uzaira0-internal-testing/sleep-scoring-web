#!/usr/bin/env bash
# Autoresearch: API response size benchmark
# Uses k6 for proper measurement with response body analysis
set -euo pipefail
cd "$(dirname "$0")/../.."

METRIC_NAME="response_kb"

echo "=== Pre-checks ==="
if ! curl -sf http://localhost:8500/health > /dev/null 2>&1; then
  echo "FATAL: backend not healthy"
  exit 1
fi

SITE_PASSWORD=$(docker exec sleep-scoring-backend printenv SITE_PASSWORD 2>/dev/null || echo 'DACAdminTest123')
AUTH_HEADER="X-Site-Password: $SITE_PASSWORD"

FILE_ID=$(curl -s -H "$AUTH_HEADER" http://localhost:8500/api/v1/files | python3 -c "import sys,json; files=json.load(sys.stdin); print(files[0]['id'] if files else '')" 2>/dev/null || echo "")
if [ -z "$FILE_ID" ]; then
  echo "FATAL: no files found"; exit 1
fi

DATE=$(curl -s -H "$AUTH_HEADER" "http://localhost:8500/api/v1/files/${FILE_ID}/dates/status" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['date'] if d else '')" 2>/dev/null || echo "")
if [ -z "$DATE" ]; then
  echo "FATAL: no dates found"; exit 1
fi

echo "Using file_id=$FILE_ID date=$DATE"

echo "=== Measuring response sizes ==="
TOTAL_COMPRESSED=0
TOTAL_UNCOMPRESSED=0

for endpoint in \
  "http://localhost:8500/api/v1/activity/${FILE_ID}/${DATE}/score?fields=available_dates" \
  "http://localhost:8500/api/v1/files/${FILE_ID}/dates/status" \
  "http://localhost:8500/api/v1/markers/${FILE_ID}/${DATE}/table-full"; do

  # Compressed size
  COMPRESSED=$(curl -s -o /dev/null -w '%{size_download}' -H "$AUTH_HEADER" -H "Accept-Encoding: gzip" "$endpoint" 2>/dev/null)
  # Uncompressed size
  UNCOMPRESSED=$(curl -s -o /dev/null -w '%{size_download}' -H "$AUTH_HEADER" "$endpoint" 2>/dev/null)

  C_INT=$(echo "$COMPRESSED" | cut -d. -f1)
  U_INT=$(echo "$UNCOMPRESSED" | cut -d. -f1)
  TOTAL_COMPRESSED=$((TOTAL_COMPRESSED + C_INT))
  TOTAL_UNCOMPRESSED=$((TOTAL_UNCOMPRESSED + U_INT))

  RATIO=$(echo "scale=1; $C_INT * 100 / ($U_INT + 1)" | bc)
  echo "  $endpoint"
  echo "    compressed: ${C_INT} bytes, uncompressed: ${U_INT} bytes (${RATIO}% ratio)"
done

TOTAL_KB=$(echo "scale=2; $TOTAL_COMPRESSED / 1024" | bc)
TOTAL_UNCOMP_KB=$(echo "scale=2; $TOTAL_UNCOMPRESSED / 1024" | bc)

echo ""
echo "Total compressed: ${TOTAL_KB} KB"
echo "Total uncompressed: ${TOTAL_UNCOMP_KB} KB"
echo ""
echo "METRIC ${METRIC_NAME}=${TOTAL_KB}"
