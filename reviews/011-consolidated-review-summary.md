# 011 Consolidated Review Summary (Normalized)

## Scope
Normalized consolidation of:
- `reviews/007-architecture-layer-review.md`
- `reviews/008-state-management-review.md`
- `reviews/009-data-persistence-review.md`
- `reviews/010-coding-standards-review.md`

## Normalization Rules
1. Single severity rubric across all reports.
2. One canonical owner review per finding (cross-report duplicates removed).
3. Only high-confidence findings retained.

## Authoritative Counts (Deduped)
| Review | CRIT | HIGH | MED | LOW | Total |
|---|---:|---:|---:|---:|---:|
| 007 Architecture Layers | 0 | 2 | 1 | 0 | 3 |
| 008 State Management | 0 | 2 | 1 | 0 | 3 |
| 009 Data Persistence | 0 | 3 | 2 | 1 | 6 |
| 010 Coding Standards | 0 | 2 | 3 | 2 | 7 |
| **Total** | **0** | **9** | **7** | **3** | **19** |

## Key Dedupe Decisions
- `auto_save_current_markers` widget-vs-store save-path issue is owned by **008** (state lifecycle), not duplicated in **009**.
- `load_saved_nonwear_markers` duplicate load-path issue is owned by **007** (layering/architecture), not duplicated in **009**.

## Top Actionable Findings
1. `sleep_scoring_app/ui/main_window.py:1096` - MainWindow still performs persistence/business logic that should live in services/coordinators.
2. `sleep_scoring_app/ui/main_window.py:916` - Nonwear-only dirty state can bypass manual-save navigation warning flow.
3. `sleep_scoring_app/ui/main_window.py:2180` - `closeEvent` executes redundant second save path via widget state after `force_save()`.
4. `sleep_scoring_app/data/repositories/sleep_metrics_repository.py:82` - Autosave path can leave `sleep_markers_extended` stale relative to `sleep_metrics`.
5. `sleep_scoring_app/ui/window_state.py:302` - Clear operation is not atomic across sleep/nonwear deletes.
6. `sleep_scoring_app/core/dataclasses_config.py:55` - Config dataclasses (`AppConfig`, `ColumnMapping`) are mutable (not frozen).
7. `sleep_scoring_app/services/export_service.py:669` - Main sleep metrics are persisted as top-level date fields in addition to period-level metrics.

## Verified Clean Areas
- Core layer imports: no upward dependency on UI/services.
- Services layer: no `PyQt6` imports.
- `ui/widgets/`: no direct service imports and no direct `store.dispatch(...)`.
- Marker deep-copy-before-mutation pattern is in place in marker modification paths.
