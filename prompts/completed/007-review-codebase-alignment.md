<objective>
Review the sleep-scoring-demo codebase for alignment with CLAUDE.md guidelines and general best practices.
Use BOTH your own analysis AND OpenAI's Codex CLI (`codex exec`) as an independent second reviewer.
Combine findings into a single actionable report.
</objective>

<context>
This is a PyQt6 desktop application for sleep scoring of accelerometer data.
The project has a detailed CLAUDE.md with mandatory architecture rules, coding standards, and patterns.
Previous reviews have found and fixed issues; this is a fresh pass to catch remaining violations.

Key files:
- `./CLAUDE.md` - Project guidelines (READ THIS FIRST)
- `./sleep_scoring_app/ui/` - UI layer (widgets, connectors, coordinators)
- `./sleep_scoring_app/services/` - Headless services
- `./sleep_scoring_app/core/` - Pure domain logic
- `./sleep_scoring_app/ui/store.py` - Redux store
</context>

<research>
Step 1: Read CLAUDE.md thoroughly to understand all mandatory rules.

Step 2: Run your own analysis across these categories:
  1. **Layer violations** - Widgets calling services directly, core importing from UI/services
  2. **Redux pattern** - Direct state mutation, missing dispatch, store bypasses
  3. **StrEnum compliance** - Hardcoded magic strings that should be enums
  4. **hasattr() abuse** - hasattr used on typed parents (not for optional library features)
  5. **Type annotations** - Missing annotations on function signatures
  6. **Data hierarchy** - Metrics at wrong level, dict access instead of dataclass attributes
  7. **Backwards compat hacks** - Deprecated wrappers, legacy fallbacks, re-exports

Step 3: Use Codex CLI for an independent review. Run these commands via Bash:

```bash
codex exec "Review the codebase in ./sleep_scoring_app/ against the rules in ./CLAUDE.md. Focus on: (1) widgets calling services directly instead of through connectors, (2) hasattr() abuse on typed parents, (3) hardcoded strings that should be StrEnums, (4) missing type annotations on function signatures. Report file paths and line numbers for each finding. Be specific - no vague findings."
```

```bash
codex exec "Analyze ./sleep_scoring_app/ui/widgets/ for CLAUDE.md violations. Widgets must be DUMB - they should NOT call services directly, NOT reference MainWindow or parent directly via hasattr(), NOT dispatch to store directly. Report any violations with file:line format."
```

```bash
codex exec "Check ./sleep_scoring_app/core/ for dependency violations. The core layer must have NO imports from ui/ or services/. Also check for any hardcoded strings that should use StrEnum constants from core/constants/. Report findings with file:line."
```

Step 4: Combine and deduplicate findings from both reviews.
</research>

<output_format>
Save the combined report to `./reviews/007-codebase-alignment-review.md` with this structure:

```markdown
# Codebase Alignment Review

Date: [date]
Reviewers: Claude Code, OpenAI Codex

## Findings

### High Priority (Bugs / Broken Behavior)
- [finding] — `file:line`

### Medium Priority (Architecture Violations)
- [finding] — `file:line`

### Low Priority (Style / Documentation)
- [finding] — `file:line`

## Recommendations
[Ordered list of what to fix first]
```
</output_format>

<constraints>
- Every finding MUST include a specific file path and line number - no vague claims
- Only report REAL violations, not stylistic preferences
- Do NOT report issues in test files unless they indicate production bugs
- Do NOT report issues that are explicitly called out as acceptable in CLAUDE.md
- Deduplicate findings between your review and Codex's review
- If Codex reports something you disagree with, note the disagreement
</constraints>

<verification>
Before finalizing:
- Verify each finding by reading the actual code at the reported location
- Confirm the finding is a real CLAUDE.md violation, not a false positive
- Ensure no duplicate findings in the report
</verification>
</content>
</invoke>