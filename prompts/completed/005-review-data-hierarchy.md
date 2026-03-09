<objective>
Audit the desktop PyQt6 app (`sleep_scoring_app/`) for compliance with the data hierarchy rules and domain model conventions defined in CLAUDE.md. This covers the data flow from Study→Participant→Date→Markers→Period→Metrics, ensuring metrics are per-period (not per-date), DailyData contains both sleep AND nonwear markers, and nonwear is treated as a first-class citizen.

SCOPE: Only `sleep_scoring_app/` — ignore `sleep_scoring_web/`, `tests/`, and other directories.
</objective>

<context>
Read `./CLAUDE.md` for the data hierarchy rules:

```
Study → Participant → Date → (Sleep + Nonwear Markers) → Period → Metrics
```

Key rules:
- **DailyData** contains BOTH `sleep_markers` AND `nonwear_markers`
- **Metrics** belong to each **SleepPeriod**, NOT to the date
- **Nonwear** is a first-class citizen (not an afterthought)
- Database uses **filename only** as key (never full paths)
- `store.state.current_file` → filename only
- `FileInfo.filename` → filename only
- `FileInfo.source_path` → full path (for file operations only)
</context>

<research>
Read `./CLAUDE.md`, then thoroughly audit:

### 1. Data Hierarchy Compliance
Read the core dataclasses to understand the domain model:
- `sleep_scoring_app/core/dataclasses_markers.py` — DailyData, DailySleepMarkers, SleepPeriod, SleepMetrics
- `sleep_scoring_app/core/dataclasses*.py` — all domain dataclasses
- Verify: DailyData has both sleep_markers and nonwear_markers
- Verify: SleepMetrics is attached to SleepPeriod, not to date-level containers

### 2. Metrics Per-Period Enforcement
Search the entire codebase for:
- Any place metrics are calculated or stored at the date level
- `DailyData.metrics` or `DailyData.sleep_metrics_dict` — metrics should NOT be at this level
- Correct pattern: `period.metrics` where period is a `SleepPeriod`
- Check services that calculate metrics — do they return per-period or per-date?

### 3. Nonwear as First-Class Citizen
- Search for code paths that handle sleep markers but ignore nonwear
- Check that nonwear detection algorithms are given equal treatment
- Verify nonwear markers are loaded, displayed, and exported alongside sleep markers
- Look for TODO/FIXME comments about nonwear being incomplete

### 4. Filename vs Path Convention
Search the entire `sleep_scoring_app/` for path/filename confusion:
- `store.state.current_file` should always be filename only (no path separators)
- Database queries should use filename only
- Check for `os.path.join`, `Path()` operations on what should be bare filenames
- Check for full paths being passed where filenames are expected
- Look for the pattern described in CLAUDE.md's "Known Issues" about silent failures from path/filename mismatch

### 5. DatabaseColumn Enum Usage
Read `core/constants/database.py` for the DatabaseColumn enum.
- Check that database column references use the enum, not raw strings
- Search for raw column name strings in SQL queries or data access code
</research>

<output>
Save your findings to: `./reviews/005-data-hierarchy-review.md`

Structure the report as:

```markdown
# Data Hierarchy & Domain Model Review

## Summary
[Overview of compliance]

## Data Hierarchy
### DailyData Structure: [PASS/FAIL - does it contain both sleep + nonwear?]
### Metrics Attachment: [PASS/FAIL - are metrics per-period?]

## Per-Period Metrics Violations
[Any code that calculates/stores metrics at date level instead of period level]

## Nonwear First-Class Status
[Areas where nonwear is neglected or treated as secondary]

## Filename vs Path Violations
[Each instance where paths are used where filenames should be, or vice versa]

## DatabaseColumn Enum Violations
[Raw strings used instead of DatabaseColumn enum]
```
</output>

<verification>
Before completing:
- Confirm you read all dataclass definitions in core/
- Confirm you traced the metrics calculation pipeline end-to-end
- Confirm you searched for path separator characters in store/database-related code
- Confirm you checked nonwear handling in parallel with sleep handling
</verification>

<success_criteria>
- Domain model verified as matching CLAUDE.md's data hierarchy
- All metrics-at-date-level violations found
- All filename/path confusion instances found
- Nonwear handling compared against sleep handling for parity
- DatabaseColumn enum usage verified
</success_criteria>
