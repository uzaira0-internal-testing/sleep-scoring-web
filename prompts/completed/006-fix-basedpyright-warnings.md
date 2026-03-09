# Fix Basedpyright Type Warnings

## Objective
Systematically fix the remaining ~676 basedpyright warnings in the codebase. Focus on real type safety issues, not false positives.

## Current Warning Breakdown

Run `basedpyright 2>&1 | grep -oP "report\w+" | sort | uniq -c | sort -rn` to get current counts.

Expected categories to fix:
- `reportOptionalMemberAccess` (~330) - Accessing members on potentially None values
- `reportArgumentType` (~188) - Argument type mismatches
- `reportPossiblyUnboundVariable` (~32) - Variables that might not be bound
- `reportOperatorIssue` (~25) - Operator type issues
- `reportGeneralTypeIssues` (~25) - General type mismatches
- `reportReturnType` (~24) - Return type mismatches
- `reportUnusedVariable` (~14) - Unused variables
- `reportOptionalOperand` (~14) - Operations on optional values
- `reportOptionalSubscript` (~10) - Subscripting optional values
- `reportCallIssue` (~9) - Call signature issues

## Fix Strategies

### 1. reportOptionalMemberAccess (Highest Priority)
Add assertions or early returns where values are guaranteed non-None:

```python
# Before - warning
def process_file(self):
    filename = self.store.state.current_file
    parts = filename.split(".")  # Warning: current_file could be None

# After - fixed with assertion
def process_file(self):
    filename = self.store.state.current_file
    assert filename is not None, "process_file called without file loaded"
    parts = filename.split(".")

# Or with early return
def process_file(self):
    filename = self.store.state.current_file
    if filename is None:
        return
    parts = filename.split(".")
```

### 2. reportArgumentType
Fix type annotations or add explicit casts:

```python
# Before
def set_value(self, value: int) -> None: ...
self.set_value(some_float)  # Warning

# After - fix the call
self.set_value(int(some_float))

# Or fix the annotation if float is valid
def set_value(self, value: int | float) -> None: ...
```

### 3. reportPossiblyUnboundVariable
Initialize variables before conditional blocks:

```python
# Before
if condition:
    result = compute()
return result  # Warning: possibly unbound

# After
result = None
if condition:
    result = compute()
return result
```

### 4. reportUnusedVariable
Prefix with underscore or remove:

```python
# Before
value = get_something()  # Never used - warning

# After
_ = get_something()  # Explicitly ignored
# Or just remove if side-effect not needed
```

### 5. reportReturnType
Fix return type annotations:

```python
# Before
def get_name(self) -> str:
    return self._name  # Warning if _name could be None

# After
def get_name(self) -> str | None:
    return self._name
```

## Process

1. Run basedpyright and capture output to a file
2. Group warnings by file
3. Fix one file at a time, starting with files that have the most warnings
4. After each file, re-run basedpyright to verify fixes don't introduce new issues
5. Prioritize fixes that improve actual type safety over suppression

## Files to Focus On (likely high warning count)
- `sleep_scoring_app/ui/store.py`
- `sleep_scoring_app/ui/widgets/activity_plot.py`
- `sleep_scoring_app/services/*.py`
- `sleep_scoring_app/ui/coordinators/*.py`

## Rules
- Do NOT suppress warnings with `# type: ignore` unless absolutely necessary
- Do NOT change runtime behavior - only add type safety
- Prefer assertions over `if x is None: return` when the None case is a bug
- Run `pytest tests/ -x -q` after major changes to ensure nothing breaks

## Success Criteria
- Reduce warnings from ~676 to under 200
- Zero errors
- All tests still pass
