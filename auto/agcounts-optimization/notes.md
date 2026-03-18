# agcounts Processing Optimization Research (2026-03-17)

## Baseline
- 4GB raw GENEActiv (100Hz, 3-axis) → 60s epoch counts
- ~20 minutes processing time on server (single-threaded agcounts v0.2.6)
- 667 chunks × 600K samples × ~1.8s/chunk

## Tier 1: Quick Wins (target: 12-16 min)
1. `OMP_NUM_THREADS=8` — enables BLAS threading in scipy filters (1.2-1.5x)
2. Chunk size 600K→1.2M — fewer function call overhead (1.05x)
3. `dtype='float32'` in CSV read — faster parsing, less memory (1.1x)

## Tier 2: Medium Effort (target: 8-10 min)
4. Polars for CSV parsing (already a dependency)
5. Overlapped parallel chunk processing — complex, needs golden tests

## Not Viable
- WASM epoching: different algorithm (sum-of-abs vs ActiLife calibration)
- GPU/CuPy: no NVIDIA hardware on server
- Alternative libraries: none match agcounts' ActiLife compatibility

## Next Steps
- Profile actual file to confirm CSV vs agcounts time split
- Implement Tier 1
- If insufficient, profile again and consider Tier 2
