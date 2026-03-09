<objective>
Audit the codebase for Redux pattern compliance and hasattr() abuse as defined in CLAUDE.md.

The application uses a Redux-like pattern with strict rules:
- Single source of truth in UIStore
- Widgets are DUMB (emit signals only)
- Connectors bridge Widget ↔ Store
- No hasattr() abuse for checking parent attributes
</objective>

<context>
Read @CLAUDE.md thoroughly first, especially the "Redux Pattern" and "Protocols Replace hasattr()" sections.

Key patterns to enforce:
1. Widgets emit signals, they do NOT:
   - Reference MainWindow or parent directly
   - Use hasattr() to check for parent attributes
   - Call services directly
   - Dispatch to store directly

2. Connectors (in store_connectors.py) should:
   - Subscribe to store state changes
   - Update widget properties when state changes
   - Connect widget signals to store.dispatch()

3. Valid hasattr() uses ONLY:
   - Optional library features: hasattr(gt3x_rs, 'load')
   - Duck typing for external objects
</context>

<analysis_steps>
1. Read CLAUDE.md to understand Redux pattern rules completely

2. Audit hasattr() usage across entire codebase:
   ```
   Search for: hasattr\(
   ```
   For each occurrence, determine if it's:
   - VALID: Checking optional library features or external objects
   - INVALID: Checking parent/self attributes to hide init order bugs

3. Audit Widgets (`ui/widgets/`):
   - Check for direct store.dispatch() calls
   - Check for direct service instantiation/calls
   - Check for self.parent() or parent attribute access
   - Verify widgets only emit signals for actions

4. Audit Connectors (`ui/store_connectors.py`):
   - Verify all widget-to-store connections go through connectors
   - Check that connectors subscribe to store properly
   - Verify connectors handle widget signals correctly

5. Check for state mutations outside store:
   - Look for direct state object modifications
   - All state changes should go through store.dispatch(Actions.xxx())

6. Audit Protocols (`ui/protocols.py`):
   - Are protocols being used instead of hasattr()?
   - Are there missing protocols that should exist?
</analysis_steps>

<output>
Save findings to: `./analyses/003-redux-pattern-violations.md`

Format:
```markdown
# Redux Pattern Compliance Audit

## Summary
[Overview of compliance status]

## hasattr() Abuse (Must Fix)
[Each invalid hasattr() with file:line and what it should be replaced with]

## Widget Violations (Must Fix)
[Widgets doing things they shouldn't - direct store/service/parent access]

## Missing Connectors
[Widget behaviors that should be moved to connectors]

## State Mutation Issues
[Any direct state modifications outside store]

## Recommendations
[Specific refactoring for each violation]
```
</output>

<verification>
Before completing:
- Every hasattr() call in the codebase has been reviewed
- All widget files have been checked for direct store/service access
- Each violation includes exact file:line reference
- Recommendations are actionable
</verification>
