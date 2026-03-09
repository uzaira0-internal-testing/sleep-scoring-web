<objective>
Audit the desktop PyQt6 app (`sleep_scoring_app/`) for compliance with the Redux store pattern and Widget/Connector/Coordinator separation defined in CLAUDE.md.

SCOPE: Only `sleep_scoring_app/` — ignore `sleep_scoring_web/`, `tests/`, and other directories.
</objective>

<context>
This app uses a custom Redux-like pattern for state management. Read `./CLAUDE.md` for the full rules.

Key architecture:
- **Store** (`ui/store.py`): Single source of truth. Actions → Reducer → State → Subscribers.
- **Widgets**: Dumb. Emit signals ONLY. Never dispatch, never call services, never access parent.
- **Connectors** (`ui/connectors/`): Bridge Widget ↔ Store. Subscribe to state changes, connect widget signals to dispatch.
- **Coordinators** (`ui/coordinators/`): Qt glue only (QTimer, QThread). No business logic.
- **Protocols** (`ui/protocols.py`): Replace hasattr() with typed interfaces.
</context>

<research>
Read `./CLAUDE.md` and `sleep_scoring_app/ui/store.py` first to understand the Redux pattern, available Actions, and UIState shape.

Then audit:

### 1. Store Usage Correctness
- Read `ui/store.py` to catalog all available Actions and UIState fields
- Search for direct state mutation instead of dispatch:
  - `store.state.X = Y` (WRONG — must use `store.dispatch(Actions.X(...))`)
  - Any code modifying state outside the reducer
- Search for state reads that bypass the store:
  - Widgets or services maintaining their own shadow state that duplicates store state

### 2. Widget Compliance (Dumb Widgets)
Audit ALL files in `sleep_scoring_app/ui/` that define QWidget subclasses (excluding connectors/ and coordinators/):
- Widgets must NOT call `store.dispatch()` directly
- Widgets must NOT import or reference the store
- Widgets must NOT call services directly
- Widgets must NOT use `self.parent()` to access other widgets
- Widgets SHOULD only emit `pyqtSignal`s
- List any widget that violates these rules with specific file:line

### 3. Connector Pattern Compliance
Audit ALL files in `sleep_scoring_app/ui/connectors/`:
- Each connector should subscribe to store state changes
- Each connector should connect widget signals to store dispatch
- Connectors should NOT contain domain/business logic (belongs in Services)
- Check the pattern:
  ```python
  store.subscribe(self._on_state_change)
  widget.someSignal.connect(self._handle_signal)
  def _on_state_change(self, old_state, new_state):
      if old_state.X != new_state.X:
          self._update_widget()
  ```

### 4. Coordinator Compliance
Audit `sleep_scoring_app/ui/coordinators/`:
- Coordinators should only contain Qt glue (QTimer, QThread setup)
- No business logic, no direct service calls for data processing
- They should delegate to services or dispatch to store

### 5. Protocol Usage
- Read `ui/protocols.py` to understand defined Protocols
- Search for `hasattr()` on `self` or `self.parent` that should use Protocol instead
- Check that widgets reference protocols rather than concrete parent types

### 6. Signal/Slot Wiring Audit
- Check that signal→slot connections are made in Connectors, not in widgets or main_window
- Look for `connect()` calls in widget `__init__` methods that cross widget boundaries
</research>

<output>
Save your findings to: `./reviews/004-redux-pattern-review.md`

Structure the report as:

```markdown
# Redux Pattern & Widget Architecture Review

## Summary
[Overview of compliance status]

## Store Audit
### Available Actions: [list from store.py]
### Direct State Mutations: [violations]
### Shadow State: [any widgets/services maintaining duplicate state]

## Widget Compliance
[For each non-compliant widget: file:line, violation type, suggested fix]

## Connector Compliance
[For each connector: does it follow the pattern? Business logic leaks?]

## Coordinator Compliance
[Status of each coordinator]

## Protocol Usage
[hasattr() replacements needed, Protocol coverage gaps]

## Signal Wiring
[Connections that should be moved to Connectors]
```
</output>

<verification>
Before completing:
- Confirm you read store.py to understand the full Action/State shape
- Confirm you checked EVERY widget file in ui/ for store/service/parent access
- Confirm you checked EVERY connector file for pattern compliance
- Confirm you searched for hasattr() and direct state mutations globally
</verification>

<success_criteria>
- Complete catalog of all store Actions and UIState fields
- Every widget audited for dumb-widget compliance
- Every connector audited for proper pattern usage
- All hasattr() usages classified as valid or needing Protocol replacement
- All direct state mutations identified
</success_criteria>
