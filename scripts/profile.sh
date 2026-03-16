#!/usr/bin/env bash
# =============================================================================
# Master Profiling Script
# =============================================================================
# Runs profiling tools across the full stack and generates consolidated reports.
#
# Usage:
#   scripts/profile.sh [category]
#
# Categories:
#   all        — Run everything (default)
#   python     — Python CPU + memory profiling (pyinstrument, memray)
#   complexity — Code complexity analysis (radon + wily)
#   frontend   — Bundle analysis + dead code + TSC timing
#   rust       — WASM size analysis (twiggy, cargo-bloat)
#   db         — Database query profiling (pg_stat_statements)
#   benchmark  — Run benchmark suite
#   k6         — API endpoint load profiling
#   import     — Python import time analysis
#
# Output: profiling-reports/YYYY-MM-DD_HH-MM/
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

TIMESTAMP="$(date +%Y-%m-%d_%H-%M)"
REPORT_DIR="profiling-reports/$TIMESTAMP"
CATEGORY="${1:-all}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_header() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }
log_ok()     { echo -e "${GREEN}✓${NC} $1"; }
log_warn()   { echo -e "${YELLOW}⚠${NC} $1"; }
log_fail()   { echo -e "${RED}✗${NC} $1"; }
log_skip()   { echo -e "${YELLOW}↷${NC} $1 (skipped — not installed)"; }

ensure_dir() { mkdir -p "$1"; }
has() { command -v "$1" &>/dev/null; }

# =============================================================================
# Python CPU + Memory Profiling
# =============================================================================
run_python() {
    log_header "Python Profiling"
    local out="$REPORT_DIR/python"
    ensure_dir "$out"

    # --- Pyinstrument (call tree) ---
    if uv run python -c "import pyinstrument" 2>/dev/null; then
        log_header "Pyinstrument — call tree profiler"

        # App startup
        SITE_PASSWORD=testpass ADMIN_USERNAMES=testadmin \
        uv run python -c "
import pyinstrument
p = pyinstrument.Profiler()
p.start()
from sleep_scoring_web.main import app
p.stop()
with open('$out/startup-profile.html', 'w') as f:
    f.write(p.output_html())
print(p.output_text())
" 2>/dev/null \
            && log_ok "Startup profile → $out/startup-profile.html" \
            || log_warn "Startup profiling had warnings"

        # Algorithm profiling
        SITE_PASSWORD=testpass ADMIN_USERNAMES=testadmin \
        uv run python -c "
import pyinstrument, random
p = pyinstrument.Profiler()
random.seed(42)
epochs = [random.randint(0, 3000) for _ in range(1440)]
sleep_scores = [1 if x < 100 else 0 for x in epochs]
timestamps = [946684800 + i*60 for i in range(1440)]

p.start()
from sleep_scoring_web.services.algorithms.sadeh import sadeh_1994_original
for _ in range(100): sadeh_1994_original(epochs)
from sleep_scoring_web.services.complexity import compute_pre_complexity
for _ in range(50):
    compute_pre_complexity(
        timestamps=timestamps, activity_counts=[float(x) for x in epochs],
        sleep_scores=sleep_scores, choi_nonwear=[0]*1440,
        diary_onset_time='22:30', diary_wake_time='7:00',
        diary_nap_count=0, analysis_date='2000-01-01')
p.stop()
with open('$out/algorithms-profile.html', 'w') as f:
    f.write(p.output_html())
print(p.output_text())
" 2>/dev/null \
            && log_ok "Algorithm profile → $out/algorithms-profile.html" \
            || log_warn "Algorithm profiling had warnings"
    else
        log_skip "pyinstrument (uv add --group dev pyinstrument)"
    fi

    # --- Memray (memory) ---
    if uv run python -c "import memray" 2>/dev/null; then
        log_header "Memray — memory allocation profiler"
        uv run python -m memray run -o "$out/memray.bin" --force -c "
import random
random.seed(42)
epochs = [random.randint(0, 3000) for _ in range(1440)]
from sleep_scoring_web.services.algorithms.sadeh import sadeh_1994_original
for _ in range(50): sadeh_1994_original(epochs)
" 2>/dev/null \
            && uv run python -m memray flamegraph "$out/memray.bin" -o "$out/memray-flamegraph.html" --force 2>/dev/null \
            && uv run python -m memray stats "$out/memray.bin" > "$out/memray-stats.txt" 2>/dev/null \
            && log_ok "Memray flamegraph → $out/memray-flamegraph.html" \
            || log_warn "Memray had issues"
    else
        log_skip "memray (uv add --group dev memray)"
    fi

    # Import time
    run_import_time "$out"
}

# =============================================================================
# Import Time Analysis
# =============================================================================
run_import_time() {
    local out="${1:-$REPORT_DIR/python}"
    ensure_dir "$out"
    log_header "Import Time Analysis"

    SITE_PASSWORD=testpass ADMIN_USERNAMES=testadmin \
    uv run python -X importtime -c "import sleep_scoring_web.main" 2> "$out/import-time.txt" || true

    echo "  Top 10 slowest imports:"
    sort -t'|' -k2 -rn "$out/import-time.txt" 2>/dev/null | head -10 || true
    log_ok "Import time → $out/import-time.txt"
}

# =============================================================================
# Code Complexity Analysis
# =============================================================================
run_complexity() {
    log_header "Code Complexity Analysis"
    local out="$REPORT_DIR/complexity"
    ensure_dir "$out"

    if ! uv run radon --version &>/dev/null 2>&1; then
        log_skip "radon (uv add --group dev radon)"
        return
    fi

    # Cyclomatic complexity (JSON for tracking)
    uv run radon cc sleep_scoring_web/ -a -s -j > "$out/radon-cc.json" 2>/dev/null \
        && log_ok "Cyclomatic complexity → $out/radon-cc.json"

    # Maintainability index (JSON)
    uv run radon mi sleep_scoring_web/ -s -j > "$out/radon-mi.json" 2>/dev/null \
        && log_ok "Maintainability index → $out/radon-mi.json"

    # Halstead metrics (JSON)
    uv run radon hal sleep_scoring_web/ -j > "$out/radon-hal.json" 2>/dev/null \
        && log_ok "Halstead metrics → $out/radon-hal.json"

    # Raw metrics (SLOC, comments)
    uv run radon raw sleep_scoring_web/ -s -j > "$out/radon-raw.json" 2>/dev/null \
        && log_ok "Raw metrics → $out/radon-raw.json"

    # Worst offenders (human-readable)
    echo "=== Top 20 Most Complex Functions ===" > "$out/worst-complexity.txt"
    uv run radon cc sleep_scoring_web/ -n C -s 2>/dev/null >> "$out/worst-complexity.txt" \
        && log_ok "Worst complexity → $out/worst-complexity.txt"
    head -20 "$out/worst-complexity.txt"

    # CSV for tracking over time
    uv run python -c "
import json, csv, sys
with open('$out/radon-cc.json') as f:
    data = json.load(f)
writer = csv.writer(sys.stdout)
writer.writerow(['file', 'type', 'name', 'line', 'complexity', 'grade'])
for filepath, blocks in data.items():
    for b in blocks:
        writer.writerow([filepath, b['type'], b['name'], b['lineno'], b['complexity'], b['rank']])
" > "$out/complexity-all.csv" 2>/dev/null \
        && log_ok "Complexity CSV → $out/complexity-all.csv"

    # Wily — complexity over git history
    if uv run wily --version &>/dev/null 2>&1; then
        log_header "Wily — complexity over git history"
        uv run wily build sleep_scoring_web/ 2>/dev/null \
            && uv run wily report sleep_scoring_web/services/marker_placement.py > "$out/wily-marker-placement.txt" 2>/dev/null \
            && uv run wily report sleep_scoring_web/services/complexity.py > "$out/wily-complexity.txt" 2>/dev/null \
            && uv run wily report sleep_scoring_web/api/diary.py > "$out/wily-diary.txt" 2>/dev/null \
            && log_ok "Wily reports → $out/wily-*.txt" \
            || log_warn "Wily completed with warnings"
    else
        log_skip "wily"
    fi
}

# =============================================================================
# Frontend Profiling
# =============================================================================
run_frontend() {
    log_header "Frontend Profiling"
    local out="$REPORT_DIR/frontend"
    ensure_dir "$out"
    local fe_dir="$PROJECT_ROOT/frontend"

    # --- Bundle analysis ---
    if grep -q "visualizer" "$fe_dir/vite.config.ts" 2>/dev/null; then
        log_header "Vite Bundle Analysis"
        (cd "$fe_dir" && ANALYZE=1 npx vite build 2>/dev/null) \
            && cp "$fe_dir/dist/stats.html" "$out/bundle-treemap.html" 2>/dev/null \
            && log_ok "Bundle treemap → $out/bundle-treemap.html" \
            || log_warn "Bundle analysis had issues"
    else
        log_warn "rollup-plugin-visualizer not configured in vite.config.ts"
    fi

    # --- Size-limit ---
    log_header "Bundle Size Check"
    (cd "$fe_dir" && npx size-limit 2>/dev/null) | tee "$out/bundle-size.txt" \
        && log_ok "Bundle size → $out/bundle-size.txt"

    # --- Knip (dead code) ---
    log_header "Knip — unused files, deps, exports"
    (cd "$fe_dir" && npx knip --no-progress 2>/dev/null) > "$out/knip-report.txt" 2>&1 \
        && log_ok "Knip report → $out/knip-report.txt" \
        || log_warn "Knip found issues (check report)"

    # --- TSC timing ---
    log_header "TypeScript type-check timing"
    pkill -f "tsc --noEmit" 2>/dev/null || true
    sleep 1
    local ts_start ts_end ts_dur
    ts_start=$(date +%s%N)
    (cd "$fe_dir" && npx tsc --noEmit 2>/dev/null) \
        && ts_end=$(date +%s%N) \
        && ts_dur=$(( (ts_end - ts_start) / 1000000 )) \
        && echo "TypeScript type-check: ${ts_dur}ms" | tee "$out/tsc-timing.txt" \
        && log_ok "TSC timing → $out/tsc-timing.txt (${ts_dur}ms)" \
        || log_warn "TypeScript type-check had errors"
}

# =============================================================================
# Rust/WASM Size Analysis
# =============================================================================
run_rust() {
    log_header "Rust/WASM Size Analysis"
    local out="$REPORT_DIR/rust"
    ensure_dir "$out"
    . "$HOME/.cargo/env" 2>/dev/null || true

    local wasm_dir="packages/sleep-scoring-wasm"
    if [[ ! -d "$wasm_dir" ]]; then
        log_warn "WASM crate not found"
        return
    fi

    # Compile time analysis
    log_header "Cargo Build Timings"
    (cd "$wasm_dir" && cargo build --release --timings 2>/dev/null) || true
    local timing_html
    timing_html=$(find "$wasm_dir/target" -name "cargo-timing*.html" 2>/dev/null | head -1)
    if [[ -n "$timing_html" ]]; then
        cp "$timing_html" "$out/cargo-timing.html"
        log_ok "Cargo timings → $out/cargo-timing.html"
    fi

    # Twiggy WASM size analysis
    local wasm_file
    wasm_file=$(find "$wasm_dir/target" -name "*.wasm" -path "*/release/*" 2>/dev/null | head -1)
    if has twiggy && [[ -n "$wasm_file" ]]; then
        log_header "Twiggy — WASM size dominators"
        twiggy top "$wasm_file" -n 20 | tee "$out/wasm-size-top.txt"
        twiggy dominators "$wasm_file" | head -30 > "$out/wasm-dominators.txt"
        log_ok "Twiggy reports → $out/wasm-*.txt"
    else
        log_skip "twiggy"
    fi

    # Cargo bloat
    if has cargo-bloat; then
        log_header "Cargo Bloat — largest functions"
        (cd "$wasm_dir" && cargo bloat --release -n 20 2>/dev/null) | tee "$out/cargo-bloat.txt" \
            && log_ok "Cargo bloat → $out/cargo-bloat.txt"
    else
        log_skip "cargo-bloat"
    fi
}

# =============================================================================
# Database Profiling
# =============================================================================
run_db() {
    log_header "Database Profiling"
    local out="$REPORT_DIR/db"
    ensure_dir "$out"

    # Determine psql command
    local PSQL=""
    if has psql; then
        PSQL="psql postgresql://postgres:${POSTGRES_PASSWORD:-postgres}@localhost:5432/sleep_scoring"
    elif docker exec sleep-scoring-db psql -U postgres -d sleep_scoring -c "SELECT 1" &>/dev/null 2>&1; then
        PSQL="docker exec sleep-scoring-db psql -U postgres -d sleep_scoring"
    else
        log_warn "Database not reachable. Start Docker stack first."
        return
    fi

    echo "=== Database Profiling Report ===" > "$out/db-profile.txt"
    echo "Generated: $(date)" >> "$out/db-profile.txt"

    # pg_stat_statements
    $PSQL -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;" 2>/dev/null || true

    echo "" >> "$out/db-profile.txt"
    echo "=== Top 20 Slowest Queries ===" >> "$out/db-profile.txt"
    $PSQL -c "
SELECT round(total_exec_time::numeric, 2) AS total_ms, calls,
       round(mean_exec_time::numeric, 2) AS mean_ms,
       round(max_exec_time::numeric, 2) AS max_ms,
       rows, LEFT(query, 120) AS query
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY total_exec_time DESC LIMIT 20;
" >> "$out/db-profile.txt" 2>/dev/null \
        && log_ok "Slow queries saved" \
        || log_warn "pg_stat_statements not available"

    echo "" >> "$out/db-profile.txt"
    echo "=== Tables with Sequential Scans (missing indexes) ===" >> "$out/db-profile.txt"
    $PSQL -c "
SELECT schemaname || '.' || relname AS table_name, seq_scan, seq_tup_read,
       idx_scan, n_live_tup AS rows,
       CASE WHEN seq_scan + idx_scan > 0
            THEN round(100.0 * seq_scan / (seq_scan + idx_scan), 1)
            ELSE 0 END AS seq_pct
FROM pg_stat_user_tables WHERE seq_scan > 0
ORDER BY seq_tup_read DESC LIMIT 20;
" >> "$out/db-profile.txt" 2>/dev/null \
        && log_ok "Sequential scan report saved"

    echo "" >> "$out/db-profile.txt"
    echo "=== Unused Indexes ===" >> "$out/db-profile.txt"
    $PSQL -c "
SELECT schemaname || '.' || relname AS table_name, indexrelname AS index_name,
       idx_scan AS scans, pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE idx_scan = 0 AND indexrelname NOT LIKE '%_pkey'
ORDER BY pg_relation_size(indexrelid) DESC LIMIT 20;
" >> "$out/db-profile.txt" 2>/dev/null \
        && log_ok "Unused indexes saved"

    echo "" >> "$out/db-profile.txt"
    echo "=== Table Sizes ===" >> "$out/db-profile.txt"
    $PSQL -c "
SELECT schemaname || '.' || relname AS table_name,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
       pg_size_pretty(pg_relation_size(relid)) AS table_size,
       n_live_tup AS rows
FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC;
" >> "$out/db-profile.txt" 2>/dev/null \
        && log_ok "Table sizes saved"

    echo "" >> "$out/db-profile.txt"
    echo "=== Cache Hit Ratio ===" >> "$out/db-profile.txt"
    $PSQL -c "
SELECT 'table' AS type, sum(heap_blks_hit) AS hits, sum(heap_blks_read) AS reads,
       CASE WHEN sum(heap_blks_hit) + sum(heap_blks_read) > 0
            THEN round(100.0 * sum(heap_blks_hit) / (sum(heap_blks_hit) + sum(heap_blks_read)), 2)
            ELSE 100 END AS hit_pct
FROM pg_statio_user_tables
UNION ALL
SELECT 'index', sum(idx_blks_hit), sum(idx_blks_read),
       CASE WHEN sum(idx_blks_hit) + sum(idx_blks_read) > 0
            THEN round(100.0 * sum(idx_blks_hit) / (sum(idx_blks_hit) + sum(idx_blks_read)), 2)
            ELSE 100 END
FROM pg_statio_user_indexes;
" >> "$out/db-profile.txt" 2>/dev/null \
        && log_ok "Cache hit ratio saved"

    log_ok "Database profile → $out/db-profile.txt"
}

# =============================================================================
# Benchmark Suite
# =============================================================================
run_benchmark() {
    log_header "Benchmark Suite"
    local out="$REPORT_DIR/benchmark"
    ensure_dir "$out"

    SITE_PASSWORD=testpass ADMIN_USERNAMES=testadmin \
    uv run pytest tests/unit/test_benchmarks.py -v --tb=short 2>&1 | tee "$out/benchmarks.txt"

    . "$HOME/.cargo/env" 2>/dev/null || true
    if [[ -d "packages/sleep-scoring-wasm" ]]; then
        (cd packages/sleep-scoring-wasm && cargo bench 2>&1) | tee "$out/rust-benchmarks.txt"
    fi
    log_ok "Benchmarks → $out/"
}

# =============================================================================
# k6 Load Profiling
# =============================================================================
run_k6() {
    log_header "k6 API Endpoint Profiling"
    local out="$REPORT_DIR/api"
    ensure_dir "$out"

    if ! has k6; then
        log_skip "k6"
        return
    fi
    if ! curl -sf --max-time 3 http://localhost:8500/health -o /dev/null 2>/dev/null; then
        log_warn "Backend not running at localhost:8500"
        return
    fi

    k6 run --out json="$out/k6-results.json" \
        --env "SITE_PASSWORD=testpass" \
        tests/load/k6-api.js 2>/dev/null \
        && log_ok "k6 results → $out/k6-results.json" \
        || log_warn "Some k6 thresholds crossed"
}

# =============================================================================
# Summary + Compression
# =============================================================================
compress_reports() {
    local compressed=0
    while IFS= read -r f; do
        gzip -9 "$f" && compressed=$((compressed + 1))
        log_ok "Gzipped $(basename "$f") → $(du -h "${f}.gz" | cut -f1)"
    done < <(find "$REPORT_DIR" -name "*.json" -size +1M 2>/dev/null)
    while IFS= read -r f; do
        gzip -9 "$f" && compressed=$((compressed + 1))
    done < <(find "$REPORT_DIR" -name "*.html" -size +1M 2>/dev/null)
    [[ "$compressed" -eq 0 ]] && log_ok "No files needed compression"
}

generate_summary() {
    log_header "Generating Summary"
    local summary="$REPORT_DIR/summary.txt"
    cat > "$summary" <<SUMMARY
==============================================================================
  Profiling Report — $TIMESTAMP
  Project: Sleep Scoring Web
  Category: $CATEGORY
  Generated: $(date)
==============================================================================

Generated Files:
----------------
SUMMARY
    find "$REPORT_DIR" -type f | sort | while read -r f; do
        local size
        size=$(du -h "$f" | cut -f1)
        echo "  $size  ${f#$REPORT_DIR/}" >> "$summary"
    done

    if [[ -f "$REPORT_DIR/complexity/worst-complexity.txt" ]]; then
        echo "" >> "$summary"
        echo "=== Complexity Hotspots ===" >> "$summary"
        head -30 "$REPORT_DIR/complexity/worst-complexity.txt" >> "$summary"
    fi
    if [[ -f "$REPORT_DIR/python/import-time.txt" ]]; then
        echo "" >> "$summary"
        echo "=== Slowest Imports (top 10) ===" >> "$summary"
        sort -t'|' -k2 -rn "$REPORT_DIR/python/import-time.txt" 2>/dev/null | head -10 >> "$summary" || true
    fi
    log_ok "Summary → $summary"
}

# =============================================================================
# Main
# =============================================================================
echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              Performance Profiling Suite                     ║"
echo "║  Category: $CATEGORY"
echo "║  Output:   $REPORT_DIR/"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

ensure_dir "$REPORT_DIR"

case "$CATEGORY" in
    all)
        run_python
        run_complexity
        run_frontend
        run_rust
        run_db
        run_benchmark
        run_k6
        ;;
    python)     run_python ;;
    complexity) run_complexity ;;
    frontend)   run_frontend ;;
    rust)       run_rust ;;
    db)         run_db ;;
    benchmark)  run_benchmark ;;
    k6)         run_k6 ;;
    import)     run_import_time "$REPORT_DIR/python" ;;
    *)
        echo "Unknown category: $CATEGORY"
        echo "Valid: all, python, complexity, frontend, rust, db, benchmark, k6, import"
        exit 1
        ;;
esac

compress_reports
generate_summary

echo ""
echo -e "${GREEN}Done!${NC} Reports saved to: ${BLUE}$REPORT_DIR/${NC}"
local total_files
total_files=$(find "$REPORT_DIR" -type f | wc -l)
echo "  $total_files files generated"
du -sh "$REPORT_DIR" | awk '{print "  Total size: " $1}'
