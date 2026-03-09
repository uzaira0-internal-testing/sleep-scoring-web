<objective>
Conduct a comprehensive audit of the Sleep Scoring Application to identify broken features, missing functionality, and integration issues.

This app has undergone significant architectural changes (Redux store pattern, connector-based UI updates) and several bugs have been recently fixed. The goal is to find any remaining issues that slipped through the transition.
</objective>

<context>
This is a PyQt6 desktop application for visual sleep scoring of accelerometer data. Key architecture points:
- Redux-style store pattern in `ui/store.py`
- Connectors bridge widgets to store in `ui/connectors/`
- Services layer is headless (no Qt imports)
- Recent fixes include: adjacent markers not refreshing, Day label not updating, marker drag snapping

Read CLAUDE.md for project conventions and architecture rules.
</context>

<research>
Thoroughly examine the codebase to identify:

1. **Connector Coverage Gaps**: Check if all UI elements that should react to store state changes have proper connectors
   - Look for widgets that directly call services or MainWindow methods instead of going through connectors
   - Find any `hasattr()` abuse patterns that hide initialization order bugs
   - Identify signals that aren't connected to anything

2. **State Synchronization Issues**: Find cases where:
   - Widget local state can diverge from Redux store state
   - Actions are dispatched but UI doesn't update
   - Multiple sources of truth exist for the same data

3. **Dead Code Paths**: Identify methods that are no longer called after the Redux refactor
   - Old `load_*` methods that connectors replaced
   - Event handlers that lost their connections
   - Features that reference removed/renamed attributes

4. **Feature Integration Completeness**: Check each major feature area:
   - Sleep markers (create, edit, drag, delete, save, load)
   - Nonwear markers (create, edit, drag, delete, save, load)
   - Date navigation (prev/next, dropdown selection, keyboard shortcuts)
   - View mode switching (24h/48h)
   - File selection and loading
   - Export functionality
   - Algorithm display (Sadeh, sleep period detection)
   - Metrics calculation and display
   - Adjacent day markers
   - Diary integration
   - Settings persistence
   - Auto-save functionality

5. **Error Handling Gaps**: Find places where:
   - Exceptions are caught but not logged or shown to user
   - Empty results are returned without warning
   - User actions fail silently
</research>

<analysis_approach>
For each potential issue found:
1. Trace the data flow from user action → store dispatch → subscriber notification → UI update
2. Compare expected behavior (from docstrings/comments) to actual implementation
3. Check if tests exist that would catch the issue
4. Note the severity: Critical (blocks user), High (degraded experience), Medium (inconvenience), Low (polish)
</analysis_approach>

<files_to_examine>
Start with:
@ui/store.py - State definition and reducer
@ui/connectors/*.py - All connectors
@ui/main_window.py - Main window orchestration
@ui/analysis_tab.py - Primary UI tab
@ui/widgets/activity_plot.py - Plot widget
@ui/widgets/plot_marker_renderer.py - Marker rendering
@services/*.py - Service layer

Then follow references to related files.
</files_to_examine>

<output>
Create a detailed bug/issue report saved to: `./docs/FEATURE_AUDIT_REPORT.md`

Structure the report as:
1. **Executive Summary**: Overview of findings by severity
2. **Critical Issues**: Blocking bugs that need immediate attention
3. **High Priority Issues**: Degraded user experience
4. **Medium Priority Issues**: Inconveniences and polish items
5. **Low Priority Issues**: Nice-to-haves
6. **Dead Code**: Methods/files that can be safely removed
7. **Test Coverage Gaps**: Missing tests that would catch these issues
8. **Recommendations**: Suggested fixes with effort estimates

For each issue include:
- File location and line numbers
- Description of the problem
- How to reproduce (if applicable)
- Suggested fix approach
</output>

<verification>
Before completing:
- Verify each identified issue by tracing the actual code path
- Confirm dead code is truly unreachable
- Cross-reference with recent git history to avoid flagging intentional changes
- Run existing tests to see if any hint at undiscovered issues
</verification>

<success_criteria>
- All major feature areas examined
- At least connector, service, and widget layers checked for each feature
- Issues are actionable with clear reproduction steps
- No false positives (things that are actually working correctly)
</success_criteria>
