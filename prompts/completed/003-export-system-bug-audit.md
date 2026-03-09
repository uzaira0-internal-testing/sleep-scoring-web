<objective>
Conduct an exhaustive bug audit of the sleep scoring export system. Two critical bugs were just discovered and fixed:

1. **Activity data caching bug**: Cache loaded data only for the first date's time range, causing metrics calculation to fail for other dates
2. **Key mismatch bug**: Period metrics stored with lowercase keys but export expected ExportColumn keys, causing naps to show main sleep metrics

Given these bugs slipped through existing tests, perform a thorough investigation to identify any other potential bugs, edge cases, or logic errors in the export pipeline.

This is a READ-ONLY investigation. Do NOT write or modify any code. Output a comprehensive report document.
</objective>

<context>
This is a desktop PyQt6 application for sleep scoring. The export system:
- Exports sleep metrics and markers to CSV
- Calculates metrics on-the-fly during export using cached activity data
- Handles multiple sleep periods per date (main sleep + naps)
- Supports multiple participants and files
- Uses a Redux-like store pattern

The user is suspicious that more bugs exist because two significant bugs were found despite existing tests.
</context>

<files_to_investigate>
Thoroughly analyze these files and their interactions:

Core Export Logic:
@sleep_scoring_app/services/export_service.py

Data Classes and Export Format:
@sleep_scoring_app/core/dataclasses_markers.py (especially to_export_dict, to_export_dict_list, store_period_metrics)
@sleep_scoring_app/core/constants/io.py (ExportColumn enum)

Database Layer:
@sleep_scoring_app/data/repositories/sleep_metrics_repository.py (especially _load_period_metrics_for_sleep_metrics)
@sleep_scoring_app/data/database.py

Metrics Calculation:
@sleep_scoring_app/services/data_service.py (calculate_sleep_metrics_for_period)
@sleep_scoring_app/services/metrics_calculation_service.py

Related Tests:
@tests/unit/services/test_export_service.py
</files_to_investigate>

<analysis_requirements>
Use deep, thorough reasoning for each area. Consider multiple scenarios and edge cases.

1. **Data Flow Analysis**
   - Trace the complete data flow from database load to CSV output
   - Identify any points where data could be lost, corrupted, or misaligned
   - Check for inconsistent key naming between components

2. **Caching Logic Review**
   - Examine all caching mechanisms in the export pipeline
   - Check cache invalidation logic
   - Look for stale data issues or cache key collisions

3. **Period/Metrics Association**
   - How are metrics associated with specific sleep periods?
   - Is the period indexing consistent between storage, retrieval, and export?
   - What happens with gaps in period slots (e.g., period_1 and period_3 exist, but not period_2)?

4. **Edge Cases to Investigate**
   - Empty data scenarios (no periods, no activity data, no metrics)
   - Multiple periods with same duration (tie-breaking for main sleep detection)
   - Periods that span midnight or multiple days
   - Files with missing or partial data
   - Unicode/special characters in filenames or participant IDs
   - Very large files or many participants
   - Concurrent export operations

5. **Type Safety and Conversion**
   - Timestamp conversions (Unix timestamps, datetime objects, strings)
   - Numeric type handling (int vs float for metrics)
   - None/null handling throughout the pipeline

6. **Test Coverage Gaps**
   - What scenarios are NOT covered by existing tests?
   - Are the tests testing the right things or just happy paths?
   - Do tests use realistic data structures?

7. **Silent Failure Patterns**
   - Where does code `continue` or return early without logging?
   - Are there try/except blocks that swallow errors?
   - What happens when assertions fail?
</analysis_requirements>

<investigation_approach>
For each file:
1. Read the entire file carefully
2. Map out the function call graph
3. Identify assumptions made by the code
4. Look for inconsistencies with other components
5. Consider what could go wrong

For each potential bug found:
- Describe the bug clearly
- Explain the conditions that trigger it
- Assess severity (Critical/High/Medium/Low)
- Note if existing tests would catch it
</investigation_approach>

<output>
Create a comprehensive bug audit report at: `./docs/EXPORT_SYSTEM_BUG_AUDIT.md`

Structure the report as:

# Export System Bug Audit Report

## Executive Summary
[Brief overview of findings]

## Investigation Scope
[What was examined]

## Confirmed Bugs (Already Fixed)
[Document the two bugs that were just fixed for reference]

## Potential Bugs Identified
[For each potential bug:]
### Bug N: [Title]
- **Severity**: Critical/High/Medium/Low
- **Location**: file:line_number
- **Description**: What's wrong
- **Trigger Conditions**: When this would occur
- **Impact**: What would happen
- **Test Coverage**: Would existing tests catch this?
- **Recommended Fix**: Brief description

## Suspicious Code Patterns
[Code that isn't necessarily buggy but is concerning]

## Test Coverage Gaps
[Scenarios that should be tested but aren't]

## Recommendations
[Prioritized list of actions]
</output>

<constraints>
- DO NOT write or modify any code
- DO NOT create test files
- ONLY read files and produce the analysis document
- Be thorough - the user explicitly wants deep investigation
- If uncertain about something, note it as "needs verification" rather than assuming
</constraints>

<verification>
Before completing, verify:
- All core export files have been read and analyzed
- The data flow has been traced end-to-end
- At least 10 distinct edge cases have been considered
- The report is saved to the correct location
- Findings are prioritized by severity
</verification>
