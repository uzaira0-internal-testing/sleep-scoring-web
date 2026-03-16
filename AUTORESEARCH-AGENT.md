# Autoresearch Agent Instructions

You are running an autonomous experiment loop. Your job is to optimize a metric by making small, focused changes — testing each one, keeping improvements, discarding regressions.

## The Loop

```
read auto/<target>/autoresearch.md → understand objective + what's been tried
    ↓
form hypothesis → pick ONE focused change
    ↓
edit code → make the change (small, surgical)
    ↓
git commit → commit with descriptive message
    ↓
./auto/<target>/autoresearch.sh → run benchmark
    ↓
evaluate result:
  improved → keep (update autoresearch.md)
  worse/equal → discard (git checkout -- . && git reset HEAD~1)
  crash → fix if trivial, else discard and move on
    ↓
repeat until stopping condition met
```

## Stopping Condition

**Stop when improvement is <5% after 3 consecutive cycles.** That is: if three experiments in a row all produce less than 5% improvement over the current best, the loop ends for this target. Report final results.

## Rules

1. **LOOP until stopping condition.** Never ask "should I continue?" — the user expects autonomous work.
2. **Primary metric is king.** Improved → keep. Worse or equal → discard.
3. **One change at a time.** Each experiment should be a single, testable hypothesis.
4. **Commit before benchmarking.** Every experiment gets its own commit. Include the result in the commit message body: `Result: {"status":"keep","metric_name":value}` or `REVERTED: description`.
5. **Update autoresearch.md** after every 5-10 experiments. Especially the "What's Been Tried" section.
6. **Update autoresearch.ideas.md** when you discover promising ideas you won't pursue now.
7. **Think longer when stuck.** Re-read source files, study profiling data, reason about what the CPU/runtime is actually doing. The best ideas come from deep understanding, not random variations.
8. **Don't thrash.** If you've reverted the same idea twice, try something structurally different.
9. **Simpler is better.** Removing code for equal perf = keep. Ugly complexity for tiny gain = discard.
10. **Crashes:** fix if trivial, otherwise log and move on. Don't over-invest.
11. **Tests must pass.** Never ship an optimization that breaks tests.
12. **Use `uv run` for all Python commands** — system Python is 3.9, project needs 3.12+.
13. **Use `npx` not `bun`** — bun is not in system PATH.

## This Project's Targets

Four concurrent autoresearch loops run on isolated worktree branches:

| Target | Branch | Metric | Dir |
|--------|--------|--------|-----|
| API latency | `autoresearch/api-latency` | `p99_ms` ↓ | `auto/api-latency/` |
| Test speed | `autoresearch/test-speed` | `duration_ms` ↓ | `auto/test-speed/` |
| Bundle size | `autoresearch/bundle-size` | `bundle_kb` ↓ | `auto/bundle-size/` |
| Startup time | `autoresearch/startup-time` | `startup_ms` ↓ | `auto/startup-time/` |

## Resuming

If `autoresearch.md` and `autoresearch.jsonl` exist, read both. Continue from where the previous session left off. Check `autoresearch.ideas.md` for unexplored ideas.

## Commit Message Format

```
perf(<target>): <short description of what changed>

Result: {"status":"keep|discard","metric_name":value}
```

For reverted experiments:
```
REVERTED: <description of what was tried and why it failed>

Result: {"status":"discard","metric_name":value}
```
