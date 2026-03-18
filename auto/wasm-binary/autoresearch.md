# Autoresearch: WASM Binary Optimization

## Objective
Reduce WASM binary size and improve processing throughput. `wasm-opt` is currently disabled (`wasm_opt = false` in Cargo.toml). Enable it and explore further WASM-level optimizations.

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `wasm_kb` (KB, lower is better)
- **Secondary**: parse throughput (rows/sec)

## How to Run
`./auto/wasm-binary/autoresearch.sh`

## Files in Scope
- `packages/sleep-scoring-wasm/crates/algorithms/Cargo.toml` — build config, wasm-opt, LTO, opt-level
- `packages/sleep-scoring-wasm/crates/algorithms/src/*.rs` — all Rust source files
- `packages/sleep-scoring-wasm/Cargo.toml` — workspace config

## Off Limits
- `tests/` — Do not modify tests
- `frontend/` — Frontend code
- `auto/` — Autoresearch infrastructure
- Algorithm correctness (Sadeh, Cole-Kripke, Choi must produce identical results)

## Constraints
- `cargo test` must pass
- Algorithm output must not change (golden tests enforce this)
- No new crate dependencies without strong justification

## What's Been Tried
(nothing yet)
