<objective>
Find and fix ALL instances of the broken architecture pattern where connectors go through main_window or coordinators to manipulate widgets, instead of handling it directly.

The CORRECT pattern is:
- Connector subscribes to store state changes
- Connector calls headless Service for data loading (if needed)
- Connector updates Widget directly

The BROKEN pattern is:
- Connector calls main_window.some_method()
- main_window delegates to coordinator
- coordinator accesses parent.widget or parent.some_service

This is NOT a research task. This is a FIX task. Do not make excuses. Do not add "architecture notes". Do not create backwards-compatible wrappers. DELETE the broken code and implement it correctly.
</objective>

<context>
Read the CLAUDE.md for the layered architecture requirements.

Key rules from CLAUDE.md:
1. Widgets are DUMB - emit signals only
2. Connectors bridge Widget ↔ Store - they subscribe to state, update widgets, connect signals to dispatch
3. Services are HEADLESS - no Qt imports
4. Coordinators are ONLY for QThread/QTimer glue - NOT for widget manipulation

The codebase has multiple violations of this pattern that need to be fixed.
</context>

<research>
Thoroughly search for ALL instances of these anti-patterns in `sleep_scoring_app/ui/`:

1. Connectors calling `self.main_window.<method>()` where that method manipulates widgets
2. Connectors calling `self.main_window.<coordinator>.<method>()`
3. UIStateCoordinator methods that access `self.parent.plot_widget`, `self.parent.<any_widget>`
4. Any coordinator that directly manipulates widgets instead of dispatching actions
5. Methods in main_window that just delegate to coordinators for widget manipulation

Search commands to run:
- Find connector methods calling main_window: `rg "self\.main_window\." store_connectors.py`
- Find coordinator widget access: `rg "self\.parent\." coordinators/`
- Find coordinator service access: `rg "self\.parent\.(data_service|export_manager|db_manager)" coordinators/`

For EACH violation found:
1. Identify what state change triggers the action
2. Identify what service (if any) provides the data
3. Identify what widget needs to be updated
4. Fix it by moving logic to connector (calling service directly, updating widget directly)
5. DELETE the dead code from coordinator/main_window
6. Remove from protocol if no longer needed
</research>

<requirements>
For each broken pattern found:

1. MOVE data loading to a headless Service method (no Qt imports)
2. UPDATE the Connector to:
   - Subscribe to the relevant state change
   - Call the Service for data (if needed)
   - Update the widget directly
3. DELETE the method from UIStateCoordinator
4. DELETE the delegate method from main_window
5. REMOVE from protocol if applicable
6. Add service to protocol/main_window init if new service method created

DO NOT:
- Add "architecture note" comments as excuses
- Create backwards-compatible wrappers
- Leave dead code with "DELETED" comments
- Make half-measures or bandaids
</requirements>

<specific_violations_to_check>
Based on the codebase, check these specific areas:

1. `UIStateCoordinator.update_data_source_status()` - accesses parent.db_manager and parent.data_settings_tab
2. `UIStateCoordinator.update_status_bar()` - accesses parent.status_bar
3. Any remaining methods in UIStateCoordinator that access self.parent
4. `DiaryIntegrationManager` - extensive self.main_window.plot_widget access
5. `ImportUICoordinator` - progress bar updates via tab manipulation
6. Any connector that calls `self.main_window.<method>()` where method touches widgets
</specific_violations_to_check>

<implementation_pattern>
For each fix, follow this exact pattern:

```python
# IN SERVICE (e.g., marker_service.py, data_service.py)
def load_something(self, param: str) -> SomeData:
    """Headless data loading - no Qt."""
    # Pure Python, no Qt imports
    return data

# IN CONNECTOR (store_connectors.py)
class SomeConnector:
    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        if old_state.some_field != new_state.some_field:
            self._update_widget(new_state)

    def _update_widget(self, state: UIState) -> None:
        # Call service for data (service is headless)
        service = self.main_window.some_service
        data = service.load_something(state.current_file)

        # Update widget directly (connector's job)
        widget = self.main_window.some_widget
        widget.update_display(data)
```

DELETE from coordinator. DELETE from main_window. REMOVE from protocol.
</implementation_pattern>

<output>
After fixing all violations:

1. Run type checker: `basedpyright sleep_scoring_app/ui/store_connectors.py sleep_scoring_app/ui/coordinators/*.py`
2. Run import test: `python -c "from sleep_scoring_app.ui.store_connectors import *"`
3. List all files modified
4. Summarize what was deleted vs what was created
</output>

<verification>
Before declaring complete:

1. Grep for remaining violations: `rg "self\.parent\.(plot_widget|data_service|export_manager|db_manager|data_settings_tab)" coordinators/`
2. The only acceptable `self.parent` access in coordinators is for QMessageBox parent parameter
3. Connectors should not call `self.main_window.<method>()` where method just delegates to coordinator
4. All data loading should be in services, not coordinators
</verification>

<success_criteria>
- Zero coordinator methods that manipulate widgets directly
- Zero main_window methods that just delegate to coordinators for widget updates
- All connectors call services directly for data loading
- All connectors update widgets directly
- Type checker passes with no new errors
- Imports work correctly
</success_criteria>
</content>
</invoke>