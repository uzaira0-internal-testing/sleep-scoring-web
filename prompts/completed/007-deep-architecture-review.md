# Deep Architecture Compliance Review

<objective>
Thoroughly analyze the entire codebase to determine whether the architecture principles in CLAUDE.md are being followed. This is NOT a superficial import-pattern check - you must deeply examine class responsibilities, widget complexity, layer boundaries, and identify anti-patterns that violate the layered architecture.
</objective>

<context>
Read @CLAUDE.md first to understand the mandatory architecture:

```
┌─────────────────────────────────────────────────────────────┐
│  UI Layer (PyQt6)                                           │
│  ├── Widgets (dumb, emit signals only)                      │
│  ├── Connectors (subscribe to store, update widgets)        │
│  └── Coordinators (QTimer, QThread - Qt glue)               │
├─────────────────────────────────────────────────────────────┤
│  Redux Store (Single Source of Truth)                       │
├─────────────────────────────────────────────────────────────┤
│  Services Layer (Headless, no Qt)                           │
├─────────────────────────────────────────────────────────────┤
│  Core Layer (Pure domain logic)                             │
├─────────────────────────────────────────────────────────────┤
│  IO Layer (Unified sources/)                                │
└─────────────────────────────────────────────────────────────┘
```

Key rules from CLAUDE.md:
1. **Widgets are DUMB** - emit signals only, NO direct parent access, NO service calls, NO store dispatch
2. **Connectors bridge Widget ↔ Store** - located in `ui/store_connectors.py`
3. **Services are HEADLESS** - no Qt imports, no signals, pure Python
4. **Core has NO dependencies** on UI or Services
5. **NO hasattr() abuse** - use Protocols instead
6. **NO magic strings** - use StrEnums from core/constants/
7. **Metrics are PER-PERIOD, not per-date**
</context>

<analysis_scope>
Examine ALL files in these directories:
- `sleep_scoring_app/ui/` - widgets, coordinators, store, connectors
- `sleep_scoring_app/services/` - headless services
- `sleep_scoring_app/core/` - pure domain logic
- `sleep_scoring_app/io/` - data loading
- `sleep_scoring_app/data/` - database layer
</analysis_scope>

<violation_categories>
For each category, find ALL violations:

## 1. Bloated Widgets (HIGH PRIORITY)
Widgets should be "dumb" - they emit signals and render state. Look for:
- Widgets with >200 lines of code (likely doing too much)
- Widgets that call services directly
- Widgets that dispatch to store directly (should go through connectors)
- Widgets that reference `self.parent()` or `self.parent` to access other widgets
- Widgets with business logic (calculations, data transformations)
- Widgets that manage their own state instead of reading from store

## 2. Layer Boundary Violations
- Services importing from `PyQt6` (should be headless)
- Core importing from Services or UI
- UI files importing from Data layer directly (should go through Services)
- Widgets importing from Services (should use Connectors)

## 3. Store/Redux Violations
- State mutations outside the reducer
- Components reading state without subscribing via Connector
- Direct store.state modifications instead of dispatch(Action)
- Business logic in the reducer (should be in Services)

## 4. hasattr() Abuse
- Any use of `hasattr()` to check for parent/sibling widget attributes
- Checking for optional attributes that should be guaranteed by Protocol

## 5. Magic Strings
- Hardcoded strings that should be StrEnums (algorithm names, marker types, etc.)
- String comparisons that should use enum values

## 6. Missing Connectors
- Widget ↔ Store bridging done inline instead of in store_connectors.py
- Widgets that subscribe to store directly instead of through a Connector

## 7. Coordinator Misuse
- Coordinators doing business logic instead of just Qt glue (timers, threads)
- Coordinators that should be Services (if they don't need Qt)

## 8. Protocol Violations
- Classes not implementing required Protocol methods
- Duck typing where Protocol should be used
</violation_categories>

<analysis_process>
1. **First Pass - File Structure Review**
   - List all files in each layer
   - Check file sizes (large files = potential bloat)
   - Check import statements at top of each file

2. **Second Pass - Deep Class Analysis**
   For each class, determine:
   - What layer does it belong to?
   - Does it have appropriate dependencies?
   - Is it doing only its designated responsibility?
   - How many lines of code? (flag if >300)

3. **Third Pass - Cross-Cutting Concerns**
   - How is state accessed and modified?
   - Where does business logic live?
   - How do layers communicate?

4. **Fourth Pass - Specific Anti-Pattern Search**
   Search for these patterns:
   ```python
   # Anti-patterns to grep for:
   self.parent()           # Direct parent access
   self.parent.            # Parent attribute access
   hasattr(self            # hasattr abuse
   from services import    # in ui/ files
   from PyQt6 import       # in services/ files
   store.state.            # Direct state access without connector
   ```
</analysis_process>

<output_format>
Save your analysis to: `./analyses/architecture-compliance-review.md`

Structure the report as:

```markdown
# Architecture Compliance Review

## Executive Summary
- Overall compliance score: [A/B/C/D/F]
- Critical violations: [count]
- Major violations: [count]
- Minor violations: [count]

## Critical Violations (Must Fix)
[Violations that fundamentally break the architecture]

### Violation 1: [Title]
- **File**: `path/to/file.py:line_number`
- **Rule Violated**: [Which CLAUDE.md rule]
- **Description**: [What's wrong]
- **Impact**: [Why this matters]
- **Fix**: [How to fix it]

## Major Violations (Should Fix)
[Violations that compromise the architecture but don't break it]

## Minor Violations (Nice to Fix)
[Style/consistency issues]

## Files Reviewed
[List of all files examined with line counts]

## Compliant Patterns Found
[Examples of code that correctly follows the architecture - for reference]
```
</output_format>

<verification>
Before declaring complete:
1. Verify you examined EVERY .py file in the target directories
2. Verify you checked for ALL violation categories listed
3. Verify each violation includes file path, line number, and specific fix
4. Run `find sleep_scoring_app -name "*.py" | wc -l` to confirm file count matches your review
</verification>

<success_criteria>
- Every file in sleep_scoring_app/ has been examined
- All 8 violation categories have been checked
- Each violation has a concrete, actionable fix
- Report is saved to ./analyses/architecture-compliance-review.md
</success_criteria>
