#!/usr/bin/env bash
# smoke-test.sh — Quick health check after docker compose up
# Usage: scripts/smoke-test.sh [BASE_URL]
#   BASE_URL defaults to http://localhost:8500 (backend)
#   Frontend is assumed at BASE_URL's port + 1

set -euo pipefail

BASE_URL="${1:-http://localhost:8500}"
# Derive frontend URL: replace port with port+1
BACKEND_PORT=$(echo "$BASE_URL" | grep -oP ':\K[0-9]+' || echo "8500")
FRONTEND_PORT=$((BACKEND_PORT + 1))
FRONTEND_URL=$(echo "$BASE_URL" | sed "s/:${BACKEND_PORT}/:${FRONTEND_PORT}/")

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

PASS=0
FAIL=0

check() {
    local name="$1"
    shift
    if "$@"; then
        echo -e "  ${GREEN}PASS${NC}  $name"
        ((PASS++))
    else
        echo -e "  ${RED}FAIL${NC}  $name"
        ((FAIL++))
    fi
}

echo "Smoke test: backend=$BASE_URL  frontend=$FRONTEND_URL"
echo "-----------------------------------------------------------"

check "Backend health endpoint" \
    curl -sf --max-time 5 "${BASE_URL}/health" -o /dev/null

check "API responds (GET /api/v1/files)" \
    curl -sf --max-time 5 -H "X-Site-Password: testpass" "${BASE_URL}/api/v1/files" -o /dev/null

check "Frontend serves" \
    curl -sf --max-time 5 "${FRONTEND_URL}/" -o /dev/null

echo "-----------------------------------------------------------"
if [[ $FAIL -gt 0 ]]; then
    echo -e "${RED}$FAIL check(s) failed${NC}, $PASS passed"
    exit 1
else
    echo -e "${GREEN}All $PASS checks passed${NC}"
    exit 0
fi
