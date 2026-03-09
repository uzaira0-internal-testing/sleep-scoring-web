<objective>
Find messy, repeated, redundant code, or code that duplicates functionality that exists elsewhere in the codebase.

This includes:
- Copy-pasted code blocks
- Functions that do similar things differently
- Multiple implementations of the same pattern
- Unused code that should be deleted
- Overly complex code that could be simplified
</objective>

<context>
Read @CLAUDE.md first to understand project conventions.

Key areas to look for duplication:
1. Participant info extraction (should use extract_participant_info())
2. Algorithm type handling (should use AlgorithmType enum)
3. Database queries (should use repositories)
4. File path handling (filename vs full path confusion)
5. Timestamp/datetime conversions
6. Error handling patterns
</context>

<analysis_steps>
1. Read CLAUDE.md to understand preferred patterns

2. Search for duplicate participant extraction patterns:
   - Find all places that parse participant IDs from filenames
   - Should all use `extract_participant_info()` from core
   - Flag any regex patterns that duplicate this logic

3. Search for duplicate algorithm handling:
   - Find hardcoded algorithm strings like "sadeh", "cole_kripke"
   - Should all use AlgorithmType enum
   - Find places defaulting to specific algorithms

4. Search for duplicate database patterns:
   - Find raw SQL queries outside repositories
   - Find duplicate INSERT/SELECT patterns
   - Should use repository pattern consistently

5. Search for duplicate datetime handling:
   - Find timestamp conversion code
   - Find date parsing patterns
   - Should use utility functions consistently

6. Search for duplicate error handling:
   - Find try/except blocks with similar patterns
   - Find repeated validation logic
   - Should use centralized validation

7. Find unused/dead code:
   - Functions never called
   - Imports never used
   - Classes never instantiated
   - Commented-out code blocks

8. Find overly complex code:
   - Functions > 50 lines that could be split
   - Deeply nested conditionals
   - Repeated conditional checks
</analysis_steps>

<output>
Save findings to: `./analyses/004-code-duplication.md`

Format:
```markdown
# Code Duplication and Redundancy Audit

## Summary
[Overview of duplication found]

## Duplicate Patterns (Must Consolidate)
For each pattern found:
- Pattern description
- All locations where it appears (file:line)
- Existing utility that should be used (if any)
- Recommended consolidation approach

## Dead/Unused Code (Must Delete)
[List of unused functions, imports, classes with file:line]

## Overly Complex Code (Should Simplify)
[Complex code blocks that could be refactored]

## Recommendations
[Priority-ordered list of consolidation tasks]
```
</output>

<verification>
Before completing:
- All major modules have been scanned
- Each duplication includes all occurrences with file:line
- Recommendations are specific and actionable
- Dead code has been verified as unused (not just seemingly unused)
</verification>
