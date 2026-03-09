<objective>
Fix E2E test issues and add critical missing marker interaction workflow tests. Address empty test placeholders and weak hasattr assertions.
</objective>

<context>
The test quality review identified issues in `tests/gui/e2e/test_real_e2e_workflow.py`:
- Line 451: Empty test placeholder with `pass` - needs implementation or removal
- Lines 404-410: `assert hasattr(real_main_window, 'loading_progress')` only checks existence
- Missing critical test: User workflow simulation (load file -> select date -> place markers -> export)
- Missing: Marker drag-and-drop behavior verification

Read CLAUDE.md for project conventions. This is a PyQt6 sleep scoring application.

Note: Marker interaction tests DO exist in `tests/unit/ui/widgets/test_marker_interaction_handler.py` (30 tests) but these test the handler in isolation with mocks. The E2E tests should verify the complete workflow with real widgets.
</context>

<requirements>
1. **Fix or remove empty test placeholders**:
   - Line 451 `test_window_opens_within_timeout` - implement meaningful test or remove
   - Search for other `pass` placeholder tests and fix them

2. **Strengthen hasattr assertions**:
   - Line 404-410: Replace `hasattr` checks with actual usage tests
   - Pattern: `assert hasattr(x, 'attr')` becomes:
     ```python
     # Verify attribute exists AND works
     signal = real_main_window.loading_progress
     assert isinstance(signal, pyqtSignal) or callable(signal.emit)
     ```

3. **Add marker interaction E2E workflow test**:
   - Load a real activity file
   - Navigate to a specific date
   - Simulate marker placement on the plot (click + drag)
   - Verify marker is created with correct timestamps
   - Verify marker is persisted to database
   - Verify marker appears in the marker table

4. **Add complete user workflow E2E test**:
   - Load file -> score with algorithm -> place markers -> export CSV
   - Verify exported CSV contains the placed markers

5. **Add keyboard navigation tests**:
   - Arrow keys for date navigation
   - Keyboard shortcuts for marker operations
</requirements>

<implementation>
Use qtbot for PyQt6 interaction:

```python
def test_marker_placement_workflow(self, real_main_window, qtbot):
    """Complete marker placement workflow with real widgets."""
    # Setup: Load a test file with activity data
    test_file = create_test_activity_file()
    real_main_window.load_file(test_file)
    qtbot.waitUntil(lambda: real_main_window.plot_widget.has_data())

    # Navigate to first date
    real_main_window.store.dispatch(Actions.date_navigated(0))

    # Simulate click and drag on plot to create marker
    plot = real_main_window.plot_widget
    start_pos = plot.time_to_pixel(datetime(2024, 1, 15, 22, 0))  # 10 PM
    end_pos = plot.time_to_pixel(datetime(2024, 1, 16, 6, 0))     # 6 AM

    qtbot.mousePress(plot, Qt.LeftButton, pos=start_pos)
    qtbot.mouseMove(plot, end_pos)
    qtbot.mouseRelease(plot, Qt.LeftButton, pos=end_pos)

    # Verify marker was created
    markers = real_main_window.store.state.markers
    assert len(markers) == 1
    assert markers[0].start_time == datetime(2024, 1, 15, 22, 0)
    assert markers[0].end_time == datetime(2024, 1, 16, 6, 0)

    # Verify marker in database
    db_markers = real_main_window.db.load_markers("test.csv", "2024-01-15")
    assert len(db_markers) == 1

    # Verify marker in table
    table = real_main_window.marker_table
    assert table.rowCount() == 1
```

For hasattr replacement:

```python
# BEFORE (weak)
def test_loading_progress_signal_exists(self, real_main_window):
    assert hasattr(real_main_window, 'loading_progress')

# AFTER (strong)
def test_loading_progress_signal_works(self, real_main_window, qtbot):
    received = []
    real_main_window.loading_progress.connect(lambda v: received.append(v))

    # Trigger something that emits progress
    real_main_window._emit_loading_progress(50)

    assert len(received) == 1
    assert received[0] == 50
```
</implementation>

<output>
Modify: `tests/gui/e2e/test_real_e2e_workflow.py`
- Fix or remove empty placeholders
- Strengthen hasattr assertions
- Add marker interaction workflow test
- Add complete user workflow test

Run tests after modifications: `pytest tests/gui/e2e/test_real_e2e_workflow.py -v`
</output>

<verification>
Before declaring complete:
1. Run `pytest tests/gui/e2e/test_real_e2e_workflow.py -v` - all tests pass
2. Grep for `pass  #` placeholder comments - none should remain
3. Grep for `assert hasattr` - each should have follow-up behavior verification
4. Confirm at least 1 test covers the marker placement workflow
5. Confirm at least 1 test covers load-to-export user journey
</verification>

<success_criteria>
- All tests pass
- No empty placeholder tests remain
- All hasattr assertions are strengthened with behavior verification
- At least 1 marker interaction workflow test added
- At least 1 complete user workflow test (load -> score -> mark -> export)
- Tests use qtbot for realistic PyQt6 interactions
</success_criteria>
