#!/usr/bin/env bash
# test-all.sh — Comprehensive local test suite (replaces GitHub Actions)
#
# Usage: scripts/test-all.sh [tier]
#   fast     — lint + typecheck + unit tests (pre-push, ~30s)
#   full     — fast + security + coverage + dead-code (before merge, ~2min)
#   heavy    — full + mutation + load + e2e + lighthouse (weekly/release, ~10min+)
#   <empty>  — defaults to 'full'

REPO_ROOT="/opt/sleep-scoring-web"
cd "$REPO_ROOT"

TIER="${1:-full}"

# ── Test credentials (used by multiple checks) ───────────────────────────
# Not exported to avoid leaking in `ps` — passed inline to commands that need them
_SITE_PASSWORD="${SITE_PASSWORD:-testpass}"
_ADMIN_USERNAMES="${ADMIN_USERNAMES:-testadmin}"

# ── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Counters ────────────────────────────────────────────────────────────────
PASS=0
FAIL=0
SKIP=0
ADVISORY_FAIL=0

# ── Helpers ─────────────────────────────────────────────────────────────────
step_start() {
    STEP_NAME="$1"
    STEP_START=$(date +%s)
    echo ""
    echo -e "${CYAN}▶ ${BOLD}$STEP_NAME${NC}"
}

step_pass() {
    local elapsed=$(( $(date +%s) - STEP_START ))
    echo -e "  ${GREEN}PASS${NC}  $STEP_NAME  (${elapsed}s)"
    PASS=$((PASS + 1))
}

step_fail() {
    local elapsed=$(( $(date +%s) - STEP_START ))
    echo -e "  ${RED}FAIL${NC}  $STEP_NAME  (${elapsed}s)"
    FAIL=$((FAIL + 1))
}

step_advisory_fail() {
    local elapsed=$(( $(date +%s) - STEP_START ))
    echo -e "  ${YELLOW}WARN${NC}  $STEP_NAME  (${elapsed}s)  [advisory — does not block]"
    ADVISORY_FAIL=$((ADVISORY_FAIL + 1))
}

step_skip() {
    echo -e "  ${YELLOW}SKIP${NC}  $STEP_NAME  [not installed or not available]"
    SKIP=$((SKIP + 1))
}

# ── Check functions ─────────────────────────────────────────────────────────

# ─── FAST tier ──────────────────────────────────────────────────────────────

check_ruff_lint() {
    step_start "Python lint (ruff check)"
    if uv run ruff check sleep_scoring_web/; then
        step_pass
    else
        step_fail
    fi
}

check_ruff_format() {
    step_start "Python format (ruff format --check)"
    if uv run ruff format --check sleep_scoring_web/; then
        step_pass
    else
        step_fail
    fi
}

check_eslint() {
    step_start "Frontend lint (eslint)"
    if (cd frontend && npx eslint src/); then
        step_pass
    else
        step_fail
    fi
}

check_basedpyright() {
    step_start "Python typecheck (basedpyright)"
    if uv run basedpyright sleep_scoring_web/; then
        step_pass
    else
        step_fail
    fi
}

check_tsc() {
    step_start "Frontend typecheck (tsc --noEmit)"
    # CRITICAL: kill any existing tsc to prevent OOM
    pkill -f "tsc --noEmit" 2>/dev/null || true
    sleep 1
    if (cd frontend && npx tsc --noEmit); then
        step_pass
    else
        step_fail
    fi
}

check_rust() {
    step_start "Rust clippy + tests"
    if (
        . "$HOME/.cargo/env" 2>/dev/null || true
        cd packages/sleep-scoring-wasm
        cargo clippy -- -D warnings && cargo test
    ); then
        step_pass
    else
        step_fail
    fi
}

check_pytest() {
    step_start "Python tests (pytest)"
    if (
        SITE_PASSWORD="$_SITE_PASSWORD" ADMIN_USERNAMES="$_ADMIN_USERNAMES" \
        uv run pytest tests/web/ tests/unit/ -v \
            --ignore=tests/unit/services --ignore=tests/unit/ui \
            --ignore=tests/unit/core --ignore=tests/unit/io \
            --ignore=tests/unit/utils \
            --ignore=tests/unit/test_seamless_switching_state_preservation.py \
            --ignore=tests/unit/test_algorithm_factory.py \
            --ignore=tests/unit/test_calibration.py \
            --ignore=tests/unit/test_choi_axis_selection.py \
            --ignore=tests/unit/test_count_scaled.py \
            --ignore=tests/unit/test_csv_datasource.py \
            --ignore=tests/unit/test_data_alignment.py \
            --ignore=tests/unit/test_datasource_factory.py \
            --ignore=tests/unit/test_diary_mapper.py \
            --ignore=tests/unit/test_diary_mapping_helpers.py \
            --ignore=tests/unit/test_gt3x_datasource.py \
            --ignore=tests/unit/test_imputation.py \
            --ignore=tests/unit/test_nonwear_factory.py \
            --ignore=tests/unit/test_onset_offset_factory.py \
            --ignore=tests/unit/test_sleep_metrics.py \
            --ignore=tests/unit/test_cross_impl_parity.py \
            --ignore=tests/web/test_schema_fuzzing.py \
            --randomly-seed=last --tb=short \
            --cov=sleep_scoring_web --cov-report=term-missing \
            --cov-branch --cov-fail-under=90
    ); then
        step_pass
    else
        step_fail
    fi
}

check_frontend_tests() {
    step_start "Frontend unit tests (bun test)"
    if command -v bun &>/dev/null; then
        if (cd frontend && bun test); then step_pass; else step_fail; fi
    elif docker info &>/dev/null 2>&1; then
        if docker run --rm -v "$REPO_ROOT/frontend:/app" -w /app oven/bun:1-alpine bun test; then
            step_pass
        else
            step_fail
        fi
    else
        step_skip
    fi
}

check_vulture() {
    step_start "Dead code detection (vulture)"
    if command -v vulture &>/dev/null; then
        if vulture sleep_scoring_web/ --min-confidence 90; then
            step_pass
        else
            step_advisory_fail
        fi
    else
        step_skip
    fi
}

# ─── FULL tier ──────────────────────────────────────────────────────────────

check_gitleaks() {
    step_start "Secret detection (gitleaks)"
    if command -v gitleaks &>/dev/null; then
        if gitleaks detect --source . --verbose; then
            step_pass
        else
            step_fail
        fi
    else
        step_skip
    fi
}

check_pip_audit() {
    step_start "Python dep audit (pip-audit)"
    if command -v pip-audit &>/dev/null; then
        if uv export --no-hashes 2>/dev/null | pip-audit -r /dev/stdin --strict; then
            step_pass
        else
            step_fail
        fi
    else
        step_skip
    fi
}

check_npm_audit() {
    step_start "Node dep audit (npm audit)"
    if (cd frontend && npm audit --audit-level=high); then
        step_pass
    else
        step_fail
    fi
}

check_cargo_audit() {
    step_start "Rust dep audit (cargo audit)"
    . "$HOME/.cargo/env" 2>/dev/null || true
    if ! command -v cargo-audit &>/dev/null; then
        step_skip
        return
    fi
    if (cd packages/sleep-scoring-wasm && cargo audit); then
        step_pass
    else
        step_fail
    fi
}

check_bandit() {
    step_start "Python SAST (bandit)"
    if command -v bandit &>/dev/null; then
        if uv run bandit -r sleep_scoring_web/ -ll -ii --skip B101; then
            step_pass
        else
            step_fail
        fi
    else
        step_skip
    fi
}

check_depcheck() {
    step_start "Unused deps check (depcheck)"
    if (cd frontend && npx depcheck --ignores="@types/*,tailwindcss,@tailwindcss/*,autoprefixer,postcss"); then
        step_pass
    else
        step_advisory_fail
    fi
}

check_knip() {
    step_start "TypeScript dead exports (knip)"
    if (cd frontend && npx knip --no-progress 2>/dev/null); then
        step_pass
    else
        step_advisory_fail
    fi
}

check_deptry() {
    step_start "Python unused deps (deptry)"
    if command -v deptry &>/dev/null || uv run deptry --help &>/dev/null 2>&1; then
        if uv run deptry sleep_scoring_web/; then
            step_pass
        else
            step_advisory_fail
        fi
    else
        step_skip
    fi
}

check_semgrep() {
    step_start "SAST (semgrep)"
    if command -v semgrep &>/dev/null; then
        if semgrep --config=auto --error sleep_scoring_web/ 2>/dev/null; then
            step_pass
        else
            step_advisory_fail
        fi
    else
        step_skip
    fi
}

check_licenses() {
    step_start "License check (advisory)"
    if command -v pip-licenses &>/dev/null; then
        pip-licenses --format=markdown --order=license 2>/dev/null || true
    fi
    (cd frontend && npx license-checker --summary 2>/dev/null) || true
    # Advisory — never blocks, just informational output
    step_advisory_fail
}

check_hadolint() {
    step_start "Dockerfile lint (hadolint)"
    if command -v hadolint &>/dev/null; then
        if hadolint docker/backend/Dockerfile.local docker/frontend/Dockerfile; then
            step_pass
        else
            step_advisory_fail
        fi
    else
        step_skip
    fi
}

# ─── HEAVY tier ─────────────────────────────────────────────────────────

check_contract_drift() {
    step_start "API contract drift"
    if ! curl -sf --max-time 3 http://localhost:8500/health -o /dev/null 2>/dev/null; then
        if ! ensure_docker_stack; then
            step_skip
            return
        fi
    fi
    if bash "$REPO_ROOT/scripts/check-contract-drift.sh" http://localhost:8500; then
        step_pass
    else
        step_fail
    fi
}

check_mutation_python() {
    step_start "Mutation testing — Python (mutmut)"
    if ! command -v mutmut &>/dev/null && ! python -m mutmut --help &>/dev/null 2>&1; then
        step_skip
        return
    fi
    (
        SITE_PASSWORD="$_SITE_PASSWORD" ADMIN_USERNAMES="$_ADMIN_USERNAMES" \
        uv run mutmut run \
            --paths-to-mutate "sleep_scoring_web/services/algorithms/" \
            --tests-dir "tests/unit/" \
            --runner "uv run pytest tests/unit/test_algorithm_properties.py -x -q --tb=no"
        # mutmut exits 0 even with surviving mutants — must check output
        uv run mutmut results 2>&1 | tee /tmp/mutmut_results.txt
        if grep -q "survived" /tmp/mutmut_results.txt; then
            exit 1
        fi
    )
    if [[ $? -eq 0 ]]; then
        step_pass
    else
        step_advisory_fail
    fi
}

check_mutation_js() {
    step_start "Mutation testing — JS (stryker)"
    if (cd frontend && npx stryker run); then
        step_pass
    else
        step_advisory_fail
    fi
}

check_schema_fuzzing() {
    step_start "Schema fuzzing"
    if (
        SITE_PASSWORD="$_SITE_PASSWORD" ADMIN_USERNAMES="$_ADMIN_USERNAMES" \
        uv run pytest tests/web/test_schema_fuzzing.py -v --tb=short
    ); then
        step_pass
    else
        step_fail
    fi
}

ensure_docker_stack() {
    # Returns 0 if stack is running (or was started), 1 if cannot start
    if curl -sf --max-time 3 http://localhost:8500/health -o /dev/null 2>/dev/null; then
        return 0
    fi
    echo "  Starting docker stack..."
    (cd docker && docker compose -f docker-compose.local.yml up -d --build) || return 1
    # Wait up to 60s for health
    for i in $(seq 1 30); do
        if curl -sf --max-time 2 http://localhost:8500/health -o /dev/null 2>/dev/null; then
            echo "  Docker stack healthy after ~$((i*2))s"
            return 0
        fi
        sleep 2
    done
    echo "  Docker stack failed to become healthy"
    return 1
}

DOCKER_STARTED_BY_US=false

check_e2e() {
    step_start "E2E tests (Playwright)"
    if ! ensure_docker_stack; then
        step_skip
        return
    fi
    DOCKER_STARTED_BY_US=true
    if (cd frontend && npx playwright test --project=chromium); then
        step_pass
    else
        step_fail
    fi
}

check_accessibility() {
    step_start "Accessibility tests (axe-core)"
    if ! curl -sf --max-time 3 http://localhost:8500/health -o /dev/null 2>/dev/null; then
        step_skip
        return
    fi
    if (cd frontend && npx playwright test e2e/accessibility.spec.ts --project=chromium); then
        step_pass
    else
        step_advisory_fail
    fi
}

check_smoke() {
    step_start "Smoke test (smoke-test.sh)"
    if ! curl -sf --max-time 3 http://localhost:8500/health -o /dev/null 2>/dev/null; then
        step_skip
        return
    fi
    if "$REPO_ROOT/scripts/smoke-test.sh"; then
        step_pass
    else
        step_fail
    fi
}

check_lighthouse() {
    step_start "Lighthouse CI"
    if ! ensure_docker_stack; then
        step_skip
        return
    fi
    if (cd frontend && npx lhci autorun); then
        step_pass
    else
        step_advisory_fail
    fi
}

check_load() {
    step_start "Load test (k6)"
    if ! command -v k6 &>/dev/null; then
        step_skip
        return
    fi
    if ! curl -sf --max-time 3 http://localhost:8500/health -o /dev/null 2>/dev/null; then
        step_skip
        return
    fi
    if k6 run --vus 2 --duration 15s tests/load/k6-api.js; then
        step_pass
    else
        step_advisory_fail
    fi
}

check_chromatic() {
    step_start "Chromatic (visual regression)"
    if [[ -z "${CHROMATIC_PROJECT_TOKEN:-}" ]]; then
        echo "  Set CHROMATIC_PROJECT_TOKEN env var to run"
        step_skip
        return
    fi
    if (cd frontend && npx chromatic --project-token="$CHROMATIC_PROJECT_TOKEN" --exit-zero-on-changes); then
        step_pass
    else
        step_advisory_fail
    fi
}

check_trivy() {
    step_start "Container scan (trivy)"
    if ! command -v trivy &>/dev/null; then
        step_skip
        return
    fi
    (cd docker && docker compose -f docker-compose.local.yml build backend) || true
    if trivy image sleep-scoring-web-local-backend --severity CRITICAL,HIGH; then
        step_pass
    else
        step_advisory_fail
    fi
}

check_container_structure() {
    step_start "Container structure tests"
    if ! command -v container-structure-test &>/dev/null; then
        step_skip
        return
    fi
    # Build backend image if not already available
    if ! docker image inspect sleep-scoring-web-local-backend &>/dev/null 2>&1; then
        echo "  Building backend image..."
        (cd docker && docker compose -f docker-compose.local.yml build backend) || { step_fail; return; }
    fi
    local failed=false
    echo "  Testing backend image..."
    if ! container-structure-test test \
        --image sleep-scoring-web-local-backend \
        --config "$REPO_ROOT/docker/container-structure-test.yaml"; then
        failed=true
    fi
    # Build frontend image if not already available
    if ! docker image inspect sleep-scoring-web-local-frontend &>/dev/null 2>&1; then
        echo "  Building frontend image..."
        (cd docker && docker compose -f docker-compose.local.yml build frontend) || { step_fail; return; }
    fi
    echo "  Testing frontend image..."
    if ! container-structure-test test \
        --image sleep-scoring-web-local-frontend \
        --config "$REPO_ROOT/docker/container-structure-test-frontend.yaml"; then
        failed=true
    fi
    if [[ "$failed" == "true" ]]; then
        step_fail
    else
        step_pass
    fi
}

check_bundle_size() {
    step_start "Bundle size (size-limit)"
    if (cd frontend && npx vite build && npx size-limit); then
        step_pass
    else
        step_advisory_fail
    fi
}

# ── Run tiers ───────────────────────────────────────────────────────────────

SUITE_START=$(date +%s)

echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  test-all.sh — tier: ${CYAN}${TIER}${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"

case "$TIER" in
    fast|full|heavy) ;;
    *)
        echo -e "${RED}Unknown tier: $TIER${NC}"
        echo "Usage: $0 [fast|full|heavy]"
        exit 2
        ;;
esac

# ─── FAST ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Fast tier ──────────────────────────────────────────────${NC}"

check_ruff_lint
check_ruff_format
check_eslint
check_basedpyright
check_tsc
check_rust
check_pytest
check_frontend_tests
check_vulture

# ─── FULL ───────────────────────────────────────────────────────────────────
if [[ "$TIER" == "full" || "$TIER" == "heavy" ]]; then
    echo ""
    echo -e "${BOLD}── Full tier ──────────────────────────────────────────────${NC}"

    check_gitleaks
    check_pip_audit
    check_npm_audit
    check_cargo_audit
    check_bandit
    check_semgrep
    check_depcheck
    check_knip
    check_deptry
    check_licenses
    check_hadolint
fi

# ─── HEAVY ──────────────────────────────────────────────────────────────────
if [[ "$TIER" == "heavy" ]]; then
    echo ""
    echo -e "${BOLD}── Heavy tier ─────────────────────────────────────────────${NC}"

    check_contract_drift
    check_mutation_python
    check_mutation_js
    check_schema_fuzzing
    check_e2e
    check_accessibility
    check_smoke
    check_lighthouse
    check_load
    check_chromatic
    check_trivy
    check_container_structure
    check_bundle_size
fi

# ── Summary ─────────────────────────────────────────────────────────────────
SUITE_ELAPSED=$(( $(date +%s) - SUITE_START ))

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}PASS: $PASS${NC}   ${RED}FAIL: $FAIL${NC}   ${YELLOW}SKIP: $SKIP${NC}   ${YELLOW}ADVISORY: $ADVISORY_FAIL${NC}"
echo -e "  Total time: ${SUITE_ELAPSED}s"
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"

# Clean up docker stack if we started it
if [[ "$DOCKER_STARTED_BY_US" == "true" ]]; then
    echo ""
    echo -e "${CYAN}Stopping docker stack we started...${NC}"
    (cd docker && docker compose -f docker-compose.local.yml down) 2>/dev/null || true
fi

if [[ $FAIL -gt 0 ]]; then
    echo -e "${RED}$FAIL required check(s) failed.${NC}"
    exit 1
else
    echo -e "${GREEN}All required checks passed.${NC}"
    exit 0
fi
