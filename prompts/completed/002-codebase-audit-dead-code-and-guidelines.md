# Comprehensive Codebase Audit: Dead Code and CLAUDE.md Violations

## Objective

Perform a thorough audit of the entire `sleep_scoring_app/` codebase to identify:
1. **Dead/useless code** similar to the AUTOSAVE_METRICS pattern (code that exists but is never used, or writes data that is never read)
2. **CLAUDE.md violations** - code that doesn't follow the mandatory coding standards

## Context

We just removed an entirely useless `AUTOSAVE_METRICS` table that was:
- Created and maintained in migrations
- Data was written to it during autosave
- **But data was NEVER read from it** - loads always came from `SLEEP_METRICS`
- Complete waste of code, database space, and maintenance burden

This is the pattern we're looking for: **code that does something, but the result is never used**.

## Audit Checklist

### 1. Dead Code Patterns to Find

Search for these anti-patterns:

- [ ] **Write-only database operations**: Data saved but never loaded
- [ ] **Unused methods/functions**: Defined but never called
- [ ] **Unused imports**: Imported but never referenced
- [ ] **Unused class attributes**: Set but never read
- [ ] **Dead branches**: if/else branches that can never execute
- [ ] **Orphaned files**: Python files not imported anywhere
- [ ] **Unused configuration options**: Config values defined but never used
- [ ] **Deprecated code with "legacy" or "old" in name**: Should have been deleted
- [ ] **Commented-out code blocks**: Should be deleted, not commented
- [ ] **TODO comments for already-completed work**: Stale TODOs

### 2. CLAUDE.md Violations to Find

Check for violations of these MANDATORY standards:

#### StrEnums for ALL String Constants
```python
# VIOLATION - hardcoded strings
algorithm = "sadeh_1994"
marker_type = "MAIN_SLEEP"
table_name = "sleep_metrics"

# CORRECT
algorithm = AlgorithmType.SADEH_1994_ACTILIFE
marker_type = MarkerType.MAIN_SLEEP
table = DatabaseTable.SLEEP_METRICS
```

#### Dataclass Access Over Dicts
```python
# VIOLATION - unnecessary dict conversion
metrics_dict = sleep_metrics.to_dict()
tst = metrics_dict.get("total_sleep_time")

# CORRECT
tst = sleep_metrics.total_sleep_time
```

#### Type Annotations on ALL Function Signatures
```python
# VIOLATION
def calculate_metrics(period, results, x_data):

# CORRECT
def calculate_metrics(
    period: SleepPeriod,
    results: list[int],
    x_data: list[float],
) -> SleepMetrics | None:
```

#### NO hasattr() Abuse
```python
# VIOLATION - hiding init order bugs
if hasattr(self.parent, "plot_widget"):
    self.parent.plot_widget.clear()
```

#### Frozen Dataclasses for Configs
```python
# VIOLATION
@dataclass
class AlgorithmConfig:

# CORRECT
@dataclass(frozen=True)
class AlgorithmConfig:
```

#### Layer Violations
- Widgets importing/using services directly (should go through Connectors)
- Widgets dispatching to store directly (should emit signals)
- Widgets referencing parent with hasattr checks
- Services importing Qt (should be headless)
- Core importing from UI or Services

#### Metrics are PER-PERIOD, Not Per-Date
```python
# VIOLATION
class DailyData:
    sleep_metrics: dict  # NO!
```

### 3. Specific Areas to Audit

Focus on these directories:

1. **`data/repositories/`** - Check for unused repository methods, write-only operations
2. **`data/database.py`** - Check for unused table definitions, dead migration code
3. **`services/`** - Check for unused service methods, Qt imports (violation)
4. **`ui/widgets/`** - Check for hasattr() abuse, direct service calls, parent references
5. **`core/constants/`** - Check for unused enum values
6. **`core/dataclasses*.py`** - Check for unused fields, non-frozen configs

## Deliverables

1. **List of dead code** with file paths and line numbers
2. **List of CLAUDE.md violations** with file paths, line numbers, and what the fix should be
3. **Prioritized fix recommendations** (high/medium/low based on impact)

## Execution Instructions

1. Use Grep/Glob extensively to search for patterns
2. For each potential issue found, verify it's actually dead/violating
3. Don't just find issues - **propose the fix**
4. Group findings by category for easy review

## Output Format

```markdown
## Dead Code Found

### High Priority
1. `path/to/file.py:123` - Description of dead code
   - **Evidence**: Why it's dead (never called, never read, etc.)
   - **Fix**: Delete lines X-Y

### Medium Priority
...

## CLAUDE.md Violations

### StrEnum Violations
1. `path/to/file.py:45` - Hardcoded string "some_value"
   - **Fix**: Use `SomeEnum.SOME_VALUE`

### Type Annotation Violations
...

### Layer Violations
...
```
