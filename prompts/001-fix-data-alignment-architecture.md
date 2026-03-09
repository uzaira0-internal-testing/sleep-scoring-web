<objective>
Investigate and fix the critical data misalignment bug where timestamps and algorithm results have different lengths, causing sleep rule arrows to disappear and other visual issues. Then create a unified, single-source-of-truth architecture for data handling that prevents this class of bug permanently.

The current symptom: `main_48h_axis_y_timestamps` has 2880 entries but `main_48h_sadeh_results` has 2460 entries, causing `apply_sleep_scoring_rules` to fail with "timestamp/sadeh mismatch" warnings.
</objective>

<context>
This is a PyQt6 desktop application for sleep scoring. The codebase follows a layered architecture with Redux-like state management. Read CLAUDE.md thoroughly before making any changes.

Key architectural rules from CLAUDE.md:
- Widgets are DUMB (emit signals, don't call services directly)
- Services are HEADLESS (no Qt imports)
- Redux Store is the single source of truth
- Use StrEnums for all string constants
- Direct dataclass access over dicts

The data flow involves:
- Loading activity data from database (import_service.py, data_loading_service.py)
- Processing through algorithms (plot_algorithm_manager.py)
- Displaying on plot (activity_plot.py)

Multiple data sources exist: axis_y, axis_x, axis_z, vector_magnitude - and Sadeh algorithm specifically requires axis_y data with matching timestamps.
</context>

<research>
Before making changes, thoroughly investigate:

1. **Trace the data flow** from database load to algorithm execution:
   - Where is `main_48h_axis_y_timestamps` set?
   - Where is `main_48h_sadeh_results` computed?
   - Why might they have different lengths (2880 vs 2460)?

2. **Find all data loading paths**:
   - data_loading_service.py
   - import_service.py
   - activity_plot.py methods (_load_data, _get_axis_y_data_for_sadeh, etc.)
   - plot_algorithm_manager.py (plot_algorithms, _extract_view_subset_from_main_results)

3. **Identify the root cause**:
   - Is data being loaded from different sources with different row counts?
   - Is there filtering happening in one path but not another?
   - Are timestamps and data loaded separately when they should be loaded together?
   - Is the Sadeh algorithm receiving the wrong timestamps?

4. **Document all places where timestamps and data are paired**:
   - Every location where we assume `len(timestamps) == len(data)`
   - Every location where data is extracted or subsetted
</research>

<requirements>
1. **Find and fix the immediate bug**: Ensure timestamps and sadeh_results always have matching lengths

2. **Create a unified data container**: Design a dataclass or structure that keeps timestamps and their corresponding data TOGETHER, making it impossible for them to get out of sync:
   ```python
   @dataclass
   class AlgorithmDataset:
       """Immutable container for aligned algorithm data."""
       timestamps: list[datetime]
       activity_data: list[float]
       sadeh_results: list[int] | None = None

       def __post_init__(self):
           if len(self.timestamps) != len(self.activity_data):
               raise ValueError(f"Data length mismatch: timestamps={len(self.timestamps)}, data={len(self.activity_data)}")
   ```

3. **Single loading path**: Ensure there is ONE way to load 48hr data that returns aligned timestamps + data together

4. **Validation at boundaries**: Add validation that logs errors when mismatches occur, with clear messages about what went wrong

5. **Update all consumers**: Modify all code that uses timestamps + algorithm results to use the unified structure
</requirements>

<constraints>
- Follow CLAUDE.md architecture rules strictly
- Do NOT add backwards compatibility shims - delete old code completely
- Do NOT use hasattr() except for duck typing external libraries
- Use StrEnums from core/constants for any new string constants
- Services must remain headless (no Qt imports)
- All new dataclasses should be in core/dataclasses*.py
</constraints>

<implementation_steps>
1. **Investigate first** - Read and trace the code paths thoroughly before making changes
2. **Identify the root cause** - Find exactly where the 2880 vs 2460 mismatch originates
3. **Design the fix** - Create a unified data container that prevents misalignment
4. **Implement incrementally** - Fix one data path at a time, verifying each step
5. **Remove old code** - Delete any deprecated loading paths completely
6. **Add validation** - Ensure mismatches are caught early with clear error messages
</implementation_steps>

<key_files>
@sleep_scoring_app/ui/widgets/plot_algorithm_manager.py - Algorithm execution and caching
@sleep_scoring_app/ui/widgets/activity_plot.py - Plot widget with data loading methods
@sleep_scoring_app/services/data_loading_service.py - Database data loading
@sleep_scoring_app/core/dataclasses*.py - Where new data structures should go
@CLAUDE.md - Architecture rules that must be followed
</key_files>

<verification>
Before declaring complete:
1. Run the app and navigate between dates - sleep rule arrows should appear consistently
2. Check that timestamps=2880 always matches sadeh_results=2880 in logs
3. Verify no "timestamp/sadeh mismatch" warnings appear
4. Run `basedpyright` - should have 0 type errors
5. Run `pytest tests/ -v` - all tests should pass
6. Test with both 24hr and 48hr view modes
</verification>

<success_criteria>
- The data mismatch warning never appears
- Sleep rule arrows display correctly on all dates
- A unified data structure exists that makes misalignment impossible
- Only ONE code path exists for loading 48hr algorithm data
- All changes follow CLAUDE.md architectural guidelines
</success_criteria>
</content>
</invoke>