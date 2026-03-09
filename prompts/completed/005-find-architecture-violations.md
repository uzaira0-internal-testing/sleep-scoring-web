# Architecture Violation Scanner

## Objective
Scan the entire `sleep_scoring_app/` codebase for architecture violations as defined in CLAUDE.md. Fix all violations found.

## Architecture Rules to Check (from CLAUDE.md)

### 1. Layer Violations
- **Widgets should be DUMB**: Check if widgets:
  - Reference MainWindow or parent directly (except through protocols)
  - Use `hasattr()` to check for parent attributes
  - Call services directly
  - Dispatch to store directly

- **Services should be HEADLESS**: Check if services:
  - Import PyQt6 or Qt modules
  - Use signals (should use callbacks instead)

- **Core should have NO dependencies** on UI or Services:
  - Check for imports from `ui/` or `services/` in `core/`

### 2. Data Access Violations
- Using `getattr(self.parent, ...)` to access app state
- Accessing parent widget attributes for data (timestamps, results, etc.)
- Not using Redux store for app state
- Storing app state directly on widgets instead of in store

### 3. StrEnum Violations
- Hardcoded magic strings instead of StrEnums from `core/constants/`
- Patterns like `algorithm = "sadeh_1994"` instead of using constants

### 4. hasattr() Abuse
- Using `hasattr()` to hide init order bugs
- Using `hasattr()` to check for optional widget attributes

### 5. Backwards Compatibility Anti-patterns
- Deprecated wrappers or "legacy" fallbacks
- Unused imports or variables kept for compatibility

## Files to Scan
```
sleep_scoring_app/ui/widgets/*.py
sleep_scoring_app/ui/coordinators/*.py
sleep_scoring_app/ui/*.py
sleep_scoring_app/services/*.py
sleep_scoring_app/core/*.py
```

## Output Format
For each violation found:
1. File and line number
2. Violation type (from list above)
3. Current code
4. How to fix it

## Action Required
**FIX all violations found**. Do not just report them - actually fix them.

## Priority Order
1. Data access violations (using parent attributes instead of store)
2. Layer violations (widgets calling services, etc.)
3. hasattr() abuse
4. StrEnum violations
5. Backwards compatibility anti-patterns
