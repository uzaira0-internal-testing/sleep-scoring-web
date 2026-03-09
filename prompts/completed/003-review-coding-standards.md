<objective>
Audit the desktop PyQt6 app (`sleep_scoring_app/`) for violations of the mandatory coding standards defined in CLAUDE.md. These are non-negotiable rules — every violation must be found and reported.

SCOPE: Only `sleep_scoring_app/` — ignore `sleep_scoring_web/`, `tests/`, and other directories.
</objective>

<context>
Read `./CLAUDE.md` first. The "MANDATORY CODING STANDARDS" section defines 7 non-negotiable rules.
This project is a PyQt6 desktop app for visual sleep scoring of accelerometer data.
</context>

<research>
Read `./CLAUDE.md` thoroughly, then audit the entire `sleep_scoring_app/` directory for these violations:

### 1. Hardcoded Strings (Must be StrEnums)
Search for magic strings that should use StrEnums from `core/constants/`:
- Algorithm names used as raw strings instead of `AlgorithmType.XXX`
- Marker types as strings instead of `MarkerType.XXX`
- Data source types, column names, file types as raw strings
- Check patterns: string literals that match known enum values (e.g., `"sadeh"`, `"MAIN_SLEEP"`, `"csv"`, `"nonwear"`, `"sleep"`)
- First read `sleep_scoring_app/core/constants/` to understand what StrEnums exist

### 2. Dict Access Instead of Dataclass Attributes
Search for unnecessary `.to_dict()` calls or dict-style access on dataclass instances:
- `metrics_dict = something.to_dict()` followed by `metrics_dict.get("key")`
- `metrics["total_sleep_time"]` when `metrics.total_sleep_time` would work
- `.to_dict()` calls that aren't for serialization/export

### 3. Missing Type Annotations
Search for functions/methods missing return type annotations or parameter type annotations:
- `def foo(self, x, y):` instead of `def foo(self, x: Type, y: Type) -> ReturnType:`
- Focus on public methods and any function with non-trivial parameters
- `__init__` methods with untyped parameters

### 4. Non-Frozen Config Dataclasses
Search for `@dataclass` without `frozen=True` on configuration/settings classes:
- Any dataclass that represents configuration should be frozen
- Check `core/` and `services/` for mutable config dataclasses

### 5. hasattr() Abuse
Search for `hasattr()` usage that hides initialization order bugs:
- `hasattr(self.parent, ...)` or `hasattr(self, "some_widget")`
- Valid uses: optional library features (`hasattr(module, 'func')`), duck typing for external objects
- Invalid uses: checking if parent/self has attributes that should be guaranteed by Protocol

### 6. Backwards Compatibility Code
Search for deprecated wrappers, legacy fallbacks, or commented-out old code:
- `# deprecated`, `# legacy`, `# old`, `# backwards compat`
- Unused imports or variables with `_` prefix that suggest renamed-but-kept-around code
- `# TODO: remove` style comments on code that should already be removed

### 7. Per-Date Instead of Per-Period Metrics
Check that metrics are always associated with periods, not dates:
- Search for metrics stored at the date level rather than per-period
- Check data structures that might attach metrics to `DailyData` instead of `SleepPeriod`
</research>

<output>
Save your findings to: `./reviews/003-coding-standards-review.md`

Structure the report as:

```markdown
# Coding Standards Review

## Summary
[Violation counts by category]

## Rule 1: Hardcoded Strings (StrEnum violations)
[Each violation with file:line, the hardcoded string, and which StrEnum should be used]

## Rule 2: Dict Access Over Dataclass
[Each violation with file:line and suggested dataclass attribute access]

## Rule 3: Missing Type Annotations
[Each violation with file:line and what annotations are missing]

## Rule 4: Non-Frozen Config Dataclasses
[Each violation with file:line]

## Rule 5: hasattr() Abuse
[Each violation with file:line, distinguishing valid vs invalid uses]

## Rule 6: Backwards Compatibility Code
[Each instance with file:line]

## Rule 7: Per-Date vs Per-Period Metrics
[Any violations found]
```
</output>

<verification>
Before completing:
- Confirm you checked EVERY .py file in `sleep_scoring_app/`
- Confirm you read `core/constants/` first to know what StrEnums exist
- Confirm you distinguished valid vs invalid hasattr() uses
- Confirm each violation includes the specific file path and line number
</verification>

<success_criteria>
- All 7 mandatory coding standards have been audited across the full `sleep_scoring_app/` directory
- Every violation includes file:line, what rule it breaks, and a concrete fix suggestion
- No false positives: valid uses of hasattr(), to_dict() for serialization, etc. are excluded
- StrEnum audit cross-references the actual enum definitions in core/constants/
</success_criteria>
