<objective>
Conduct a comprehensive architecture review of the sleep-scoring-demo codebase. Compare the ACTUAL file structure and code organization against the documented architecture in CLAUDE.md. Identify violations, inconsistencies, and opportunities for improvement.

DO NOT write any code. This is a pure analysis and review task.
</objective>

<context>
This is a PyQt6 desktop application for sleep scoring with a layered architecture:
- UI Layer (Widgets, Connectors, Coordinators)
- Redux Store (Single Source of Truth)
- Services Layer (Headless, no Qt)
- Core Layer (Pure domain logic)
- IO Layer (File loaders)

The architecture documentation is in CLAUDE.md. Recent refactoring has aimed to enforce proper patterns (Connectors bridge Widget ↔ Store, Services are headless, etc.).
</context>

<review_scope>
Thoroughly analyze the following areas. For each file reviewed, note:
1. Its intended role in the architecture
2. Whether it follows documented patterns
3. Any violations or inconsistencies

Focus areas:
</review_scope>

<area_1_layer_boundaries>
Review layer separation:
- Do UI files import from Services correctly? (should never import Qt in services)
- Do Services import from Core correctly? (should never import from UI)
- Does Core have any forbidden imports?
- Are there circular dependencies?

Files to check:
- `sleep_scoring_app/ui/*.py` - Should only contain UI code
- `sleep_scoring_app/services/*.py` - Should be headless (no Qt)
- `sleep_scoring_app/core/*.py` - Should have no UI/Service imports
</area_1_layer_boundaries>

<area_2_redux_patterns>
Review Redux store usage:
- Are Connectors properly bridging Widget ↔ Store?
- Are widgets "dumb" (only emit signals, no direct service calls)?
- Is there direct widget manipulation outside of Connectors?
- Are Actions used consistently for state changes?

Files to check:
- `sleep_scoring_app/ui/store.py`
- `sleep_scoring_app/ui/store_connectors.py`
- `sleep_scoring_app/ui/coordinators/*.py`
- All widget files in `sleep_scoring_app/ui/widgets/*.py`
</area_2_redux_patterns>

<area_3_coordinator_responsibilities>
Review Coordinators:
- Per CLAUDE.md: "Coordinators are ONLY for QThread/QTimer glue"
- Are there Coordinators doing widget manipulation directly?
- Are there Coordinators that should be Connectors?

Files to check:
- `sleep_scoring_app/ui/coordinators/*.py` (all files)
</area_3_coordinator_responsibilities>

<area_4_constants_and_enums>
Review constant usage:
- Are magic strings used instead of StrEnums?
- Are all string constants in `core/constants/`?
- Is there duplication between `core/constants/` and `ui/constants/`?

Files to check:
- `sleep_scoring_app/core/constants/*.py`
- `sleep_scoring_app/ui/constants/*.py` (if exists)
- Search for hardcoded strings in services and UI
</area_4_constants_and_enums>

<area_5_dataclass_usage>
Review dataclass patterns:
- Are frozen dataclasses used for configs?
- Is dict conversion used unnecessarily instead of attribute access?
- Are there dataclasses that should be in Core but are elsewhere?

Files to check:
- `sleep_scoring_app/core/dataclasses*.py`
- Look for `to_dict()` calls that could be direct attribute access
</area_5_dataclass_usage>

<area_6_hasattr_abuse>
Search for hasattr() misuse:
- Per CLAUDE.md: "NO hasattr() Abuse"
- Valid uses: optional library features, duck typing for external objects
- Invalid uses: hiding init order bugs, checking for parent attributes

Grep for: `hasattr(` across all Python files
</area_6_hasattr_abuse>

<area_7_protocol_usage>
Review Protocol usage:
- Are protocols defined in `ui/protocols.py`?
- Are protocols used instead of hasattr checks?
- Are there missing protocols that should exist?

Files to check:
- `sleep_scoring_app/ui/protocols.py`
- Cross-reference with widget parent access patterns
</area_7_protocol_usage>

<area_8_file_organization>
Review file organization:
- Are files in correct directories per the architecture?
- Are there misplaced files?
- Is there dead code or unused files?
- Are there files with unclear responsibilities?

List the file tree and identify:
- Files that seem misplaced
- Overlapping responsibilities
- Missing organizational patterns
</area_8_file_organization>

<output>
Create a detailed architecture review report at: `./analyses/architecture-review.md`

Structure the report as:

## Executive Summary
- Overall health of architecture (1-10 rating with justification)
- Most critical issues (top 3-5)

## Layer Boundary Violations
[List each violation with file:line and explanation]

## Redux Pattern Compliance
[Analysis of store, connectors, widget patterns]

## Coordinator Analysis
[Which coordinators follow rules, which violate]

## Constants and Enums Audit
[Magic strings found, StrEnum gaps]

## Dataclass Review
[Frozen usage, unnecessary dict conversions]

## hasattr() Audit
[Valid vs invalid uses found]

## Protocol Coverage
[Missing protocols, protocol usage gaps]

## File Organization Issues
[Misplaced files, dead code, unclear responsibilities]

## Prioritized Improvement Plan
1. [Critical - must fix immediately]
2. [High - should fix soon]
3. [Medium - improve when touching these files]
4. [Low - nice to have]

Each improvement should be concrete and actionable.
</output>

<success_criteria>
- Every Python file in the codebase has been examined
- All violations are documented with file paths and line numbers
- The improvement plan is prioritized and actionable
- No code has been written or modified
</success_criteria>
