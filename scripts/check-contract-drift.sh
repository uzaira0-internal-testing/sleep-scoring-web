#!/bin/bash
# Contract drift detection: ensures frontend types match backend OpenAPI schema
# Usage: ./scripts/check-contract-drift.sh [backend-url]
#
# Exit code 0 = types are in sync
# Exit code 1 = drift detected (regenerate types)

set -euo pipefail

BACKEND_URL="${1:-http://localhost:8500}"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cleanup() {
    rm -f /tmp/openapi-current.json /tmp/schema-fresh.ts
}
trap cleanup EXIT

echo "=== API Contract Drift Check ==="
echo "Backend: $BACKEND_URL"

# 1. Snapshot the current OpenAPI spec
echo "Fetching OpenAPI spec..."
if ! curl -sf "$BACKEND_URL/api/v1/openapi.json" -o /tmp/openapi-current.json; then
    echo "ERROR: Failed to fetch OpenAPI spec from $BACKEND_URL/api/v1/openapi.json"
    echo "Is the backend running? Start it with: cd docker && docker compose up -d"
    exit 1
fi

# Validate the fetched spec is valid JSON
if ! python3 -m json.tool /tmp/openapi-current.json > /dev/null 2>&1; then
    echo "ERROR: Fetched OpenAPI spec is not valid JSON"
    exit 1
fi

# 2. Generate fresh types from the live spec
echo "Generating types from live spec..."
cd "$SCRIPT_DIR/frontend"
if ! npx openapi-typescript /tmp/openapi-current.json -o /tmp/schema-fresh.ts 2>/dev/null; then
    echo "ERROR: Failed to generate TypeScript types from OpenAPI spec"
    echo "Ensure openapi-typescript is installed: npm install -D openapi-typescript"
    exit 1
fi

# 3. Compare with committed types
if [ -f src/api/schema.ts ]; then
    if diff -q src/api/schema.ts /tmp/schema-fresh.ts > /dev/null 2>&1; then
        echo "OK: Frontend types match backend schema — no drift detected"
        exit 0
    else
        echo "FAIL: API CONTRACT DRIFT DETECTED!"
        echo ""
        echo "The committed frontend types (src/api/schema.ts) do not match"
        echo "the types generated from the live backend OpenAPI spec."
        echo ""
        echo "Diff (committed vs generated):"
        diff --unified=3 src/api/schema.ts /tmp/schema-fresh.ts | head -80
        echo ""
        echo "To fix: cd frontend && npm run generate:types:live"
        exit 1
    fi
else
    echo "FAIL: No committed schema.ts found at src/api/schema.ts!"
    echo ""
    echo "To fix:"
    echo "  1. cd frontend && npm run generate:types:live"
    echo "  2. git add src/api/schema.ts"
    echo "  3. Commit the generated file"
    exit 1
fi
