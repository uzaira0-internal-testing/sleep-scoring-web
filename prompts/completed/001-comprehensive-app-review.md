<objective>
Conduct a thorough, systematic review of the entire sleep-scoring-demo application to identify:
1. Violations of CLAUDE.md architectural guidelines
2. Code that could silently fail or produce incorrect results for users
3. Gaps between user expectations and actual behavior
4. Insidious code patterns that hide bugs or cause subtle data corruption

This review is critical because the app processes sleep research data - incorrect metrics or silent failures could lead to flawed research conclusions.
</objective>

<context>
This is a PyQt6 desktop application for sleep scoring of accelerometer data. It implements:
- Multiple sleep scoring algorithms (Sadeh, Cole-Kripke, van Hees)
- Nonwear detection (Choi, van Hees)
- Interactive visualization with marker placement
- Export of sleep metrics for research use

Read @CLAUDE.md thoroughly first - this contains the mandatory coding standards and architecture requirements.

Key CLAUDE.md rules to enforce:
- Layered architecture: UI → Redux Store → Services → Core → IO
- Widgets are DUMB (emit signals only, no parent references, no hasattr abuse)
- StrEnums for ALL string constants (no magic strings)
- Dataclass access over dicts (no unnecessary .to_dict() conversions)
- Type annotations on ALL function signatures
- Frozen dataclasses for configs
- NO hasattr() abuse
- Metrics are PER-PERIOD, not per-date
</context>

<research>
Systematically examine these critical areas:

1. **Architecture Violations** - Search for:
   - Widgets calling parent directly or using hasattr() to check parent attributes
   - Services importing Qt or emitting signals
   - Core layer importing from UI or Services
   - Direct state mutation instead of store.dispatch()

2. **Silent Failure Patterns** - Look for:
   - Bare except blocks that swallow errors
   - Empty returns on error without logging
   - Database queries returning empty results without warning
   - File operations that fail silently
   - Data type conversions that could produce None/NaN without notice

3. **Metric Calculation Issues** - Verify:
   - All sleep metrics formulas match documented algorithms
   - Edge cases handled (empty data, single epoch, boundary conditions)
   - Timestamp handling is consistent (timezone issues?)
   - Epoch alignment is correct for 60-second epochs

4. **Export Data Integrity** - Check:
   - All exported columns have corresponding data sources
   - Metrics in export match what's displayed in UI
   - No data truncation or rounding issues
   - Participant ID parsing is robust

5. **State Management Issues** - Find:
   - Race conditions between autosave and user actions
   - Stale state being used after updates
   - Memory leaks from unsubscribed store listeners
   - Dirty flags not being reset properly

6. **User Expectation Gaps** - Identify:
   - Features that appear to work but have hidden limitations
   - Error messages that don't explain how to fix the problem
   - Default values that may surprise researchers
   - Terminology inconsistencies (onset vs sleep start, etc.)
</research>

<analysis_requirements>
For each issue found, document:
1. **File and Line**: Exact location of the problem
2. **Category**: Which type of issue (architecture, silent failure, etc.)
3. **Severity**: Critical (data corruption), High (incorrect results), Medium (confusing UX), Low (code smell)
4. **Description**: What the problem is and WHY it matters
5. **Impact**: What could go wrong for users
6. **Fix**: Specific recommendation to resolve

Prioritize issues that could:
- Corrupt or lose user data
- Produce incorrect sleep metrics
- Cause silent failures during export
- Violate the layered architecture in ways that make bugs harder to find
</analysis_requirements>

<specific_checks>
Run these specific searches and analyze results:

```bash
# Find hasattr abuse in widgets
grep -rn "hasattr.*parent" sleep_scoring_app/ui/widgets/

# Find widgets accessing parent directly
grep -rn "self\.parent\(\)\." sleep_scoring_app/ui/widgets/

# Find bare except blocks
grep -rn "except:" sleep_scoring_app/

# Find magic strings that should be StrEnums
grep -rn '"sleep"\|"nonwear"\|"onset"\|"offset"' sleep_scoring_app/ --include="*.py"

# Find .to_dict() calls that might be unnecessary
grep -rn "\.to_dict()" sleep_scoring_app/

# Find type annotation gaps
grep -rn "def .*(.*):" sleep_scoring_app/ | grep -v "->" | head -50

# Find Services importing Qt
grep -rn "from PyQt6\|import PyQt6" sleep_scoring_app/services/

# Find Core importing from UI or Services
grep -rn "from sleep_scoring_app.ui\|from sleep_scoring_app.services" sleep_scoring_app/core/
```
</specific_checks>

<output_format>
Create a comprehensive report with:

## Executive Summary
- Total issues found by severity
- Most critical issues requiring immediate attention
- Overall architecture compliance score

## Critical Issues (Data Corruption Risk)
[List each with full details]

## High Priority Issues (Incorrect Results)
[List each with full details]

## Medium Priority Issues (UX/Confusion)
[List each with full details]

## Architecture Violations
[Categorized list with specific violations]

## Recommendations
- Immediate fixes needed
- Refactoring suggestions
- Testing gaps to address

Save analysis to: `./analyses/comprehensive-app-review.md`
</output_format>

<verification>
Before completing, verify:
- [ ] All major directories examined: core/, services/, ui/, data/, utils/
- [ ] CLAUDE.md rules checked systematically
- [ ] At least 10 files in each major directory reviewed
- [ ] Export flow traced end-to-end
- [ ] Metric calculation code verified against algorithm documentation
- [ ] All grep searches executed and results analyzed
</verification>

<success_criteria>
The review is complete when:
1. Every CLAUDE.md rule has been verified with specific file examples
2. All critical and high-severity issues are documented with fixes
3. The export data flow is verified from calculation to CSV output
4. Silent failure patterns are identified and catalogued
5. User-facing issues are documented with clear impact descriptions
</success_criteria>
</content>
</invoke>