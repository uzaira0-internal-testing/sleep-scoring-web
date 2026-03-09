<objective>
Review the codebase for violations of the mandatory coding standards defined in CLAUDE.md.
Focus on patterns that indicate real problems (bugs, maintenance burden, inconsistency)
rather than cosmetic issues. This is a targeted standards audit, not a style review.
</objective>

<context>
Read CLAUDE.md for the full coding standards. Key mandatory rules:
1. StrEnums for ALL string constants (no magic strings)
2. Dataclass access over dicts (no unnecessary to_dict() conversions)
3. Type annotations on new/modified function signatures
4. Frozen dataclasses for configs
5. NO hasattr() abuse (use Protocols instead)
6. NO backwards compatibility wrappers
7. Metrics are PER-PERIOD, not per-date

The application code lives in:
- `sleep_scoring_app/` - Main application code
- `sleep_scoring_web/` - Web application code
- `tests/` - Test suite
</context>

<requirements>
Search for these specific violation patterns:

1. **Magic strings** - hardcoded string literals that should be StrEnums:
   - grep for quoted strings used as identifiers: algorithm names, marker types, status values, table names
   - Focus on sleep_scoring_app/ (not tests or third-party)

2. **hasattr() abuse** - using hasattr to check for attributes that should be protocol-guaranteed:
   - Exclude valid uses: optional library features, duck typing for external objects
   - Focus on internal code checking for parent/sibling attributes

3. **Missing type annotations** - functions in recently-modified files that lack return types or parameter types:
   - Check files modified in the last 5 commits
   - Focus on public methods, not private helpers

4. **Dict access instead of dataclass attributes** - unnecessary .to_dict() followed by dict access:
   - grep for `.to_dict()` followed by `[]` or `.get()`

5. **Mutable config dataclasses** - config/settings classes that should be frozen but aren't

6. **Date-level metrics** - any code that attaches metrics to a date instead of to a period
</requirements>

<output>
Save findings to: `./reviews/010-coding-standards-review.md`

Format each finding as:
```
### [SEVERITY] Finding title
- **File**: path:line_number
- **Rule violated**: Which CLAUDE.md rule
- **Current code**: What's there now (brief snippet)
- **Fix**: What it should be
```

Group by severity: CRITICAL > HIGH > MEDIUM > LOW.
Only report findings you are confident about (>80% confidence).
Limit to top 20 findings maximum (prioritize by severity and impact).
</output>

<verification>
Before completing:
- Verify each magic string finding is actually used as an identifier (not a log message or UI label)
- Verify each hasattr finding is actually abuse (not a valid duck-typing use)
- Cross-reference findings with existing StrEnums in core/constants/ to confirm the enum exists
- Count total findings per category in a summary at the top
</verification>
