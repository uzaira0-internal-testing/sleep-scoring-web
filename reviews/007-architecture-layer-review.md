# 007 Architecture Layer Review

## Summary
- CRITICAL: 0
- HIGH: 2
- MEDIUM: 1
- LOW: 0

Verified clean against the required grep checks: no widget imports from services, no `store.dispatch` in `ui/widgets`, no Qt imports in `services`, and no `core` imports from `ui`/`services`.

## CRITICAL
No CRITICAL findings.

## HIGH
### [HIGH] MainWindow contains service/business persistence logic that belongs below the UI layer
- **File**: sleep_scoring_app/ui/main_window.py:1096
- **Violation**: UI layer method `_autosave_sleep_markers_to_db` builds domain objects, resolves algorithm/rule enums, extracts participant info, and writes directly via `db_manager`. This is service/persistence work in the window class instead of a headless service/coordinator boundary.
- **Impact**: Increases coupling between UI and persistence/domain logic, makes autosave behavior harder to test independently, and spreads save logic across layers.
- **Fix**: Move marker persistence logic into a dedicated service (or persistence coordinator), keep `MainWindow` as a thin delegate that calls that service.

### [HIGH] MainWindow performs a second nonwear load path that bypasses Redux flow
- **File**: sleep_scoring_app/ui/main_window.py:1760
- **Violation**: `load_saved_markers()` delegates to `state_manager.load_saved_markers()` (which already loads sleep+nonwear and dispatches `markers_loaded`), then immediately calls `load_saved_nonwear_markers()` for a direct DB->widget load.
- **Impact**: Breaks single-path layering (UI bypasses Store path), duplicates load logic, and can create widget/store divergence if the two loads differ.
- **Fix**: Remove the direct nonwear reload call and keep one canonical load path through `WindowStateManager` -> `store.dispatch(Actions.markers_loaded(...))` -> connectors.

## MEDIUM
### [MEDIUM] Connector layer contains heavy side-effect orchestration beyond simple widget-store bridging
- **File**: sleep_scoring_app/ui/connectors/manager.py:93
- **Violation**: `SideEffectConnector.handle_clear_activity_data()` performs multi-table destructive DB operations, state-reset orchestration, and UI confirmation flows in `ui/connectors`.
- **Impact**: Connector boundary becomes harder to reason about; business/persistence orchestration is mixed with bridge responsibilities.
- **Fix**: Move destructive data workflows into a dedicated coordinator/service and keep connectors focused on signal/state bridging.

## LOW
No LOW findings.
