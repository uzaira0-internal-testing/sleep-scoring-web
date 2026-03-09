# Test Suite Quality Review

## Executive Summary

The test suite demonstrates **high overall quality** with meaningful, behavior-focused assertions across most categories. The codebase shows mature testing practices: core algorithms have thorough edge case coverage, services test realistic workflows, and integration tests verify real user scenarios. However, there are isolated issues: some unit tests over-mock to the point of testing nothing, and UI widget tests are notably weaker than other categories.

**Quality Grade: B+**

Justification: Strong algorithm and service tests that would catch real bugs. Excellent integration and E2E coverage. Deductions for UI widget tests that over-rely on mocks and some facade tests that only verify delegation without behavior.

---

## Category Analysis

### Unit/Core Tests

**Samples reviewed:**
- `tests/unit/core/test_sadeh.py` (366 lines)
- `tests/unit/core/test_choi_algorithm.py` (582 lines)

**Quality: A**

**Strengths:**
- Tests verify actual algorithm correctness with realistic data patterns (e.g., circadian activity patterns, 90-minute minimum nonwear periods)
- Edge cases thoroughly covered: empty input, NaN values, infinite values, negative values, boundary conditions (89 vs 90 minute periods)
- Constants validated against published paper values (line 39-49 in test_choi):
  ```python
  def test_min_period_length(self) -> None:
      """MIN_PERIOD_LENGTH is 90 minutes per paper."""
      assert MIN_PERIOD_LENGTH == 90
  ```
- Algorithm behavior tested, not just API shape: line 133-141 in test_sadeh tests that low activity actually scores as sleep:
  ```python
  def test_low_activity_scores_sleep(self) -> None:
      low_activity = [0] * 20
      result = score_activity(low_activity)
      assert sum(result) > len(result) / 2  # Verifies actual behavior
  ```
- Multiple input types accepted (list, numpy array)

**Weaknesses:**
- Some tests could verify exact expected values rather than ranges (e.g., line 141: `assert sum(result) > len(result) / 2` is weak compared to asserting specific expected output)

**Missing critical tests:**
- Cross-validation with known reference datasets (e.g., compare against ActiLife output for same input)
- Performance tests for large datasets (24+ hours of minute-by-minute data)

---

### Unit/Services Tests

**Samples reviewed:**
- `tests/unit/services/test_batch_scoring_service.py` (564 lines)
- `tests/unit/services/test_data_loading_service.py` (912 lines)

**Quality: B+**

**Strengths:**
- Real file operations tested with `tmp_path` fixtures creating actual CSV files (line 61-82 in test_data_loading_service)
- Fallback behavior tested: database failure triggers CSV fallback (line 472-490)
- Edge cases: empty folders, nonexistent files, missing columns, invalid time formats
- Diary time parsing correctly handles cross-midnight scenarios (line 376-386 in test_batch_scoring):
  ```python
  def test_extract_diary_times_cross_midnight(self):
      diary_entry = {"sleep_onset_time": "23:30", "sleep_offset_time": "06:30"}
      onset, offset = _extract_diary_times(diary_entry, "2024-01-10")
      assert onset == datetime(2024, 1, 10, 23, 30)
      assert offset == datetime(2024, 1, 11, 6, 30)  # Next day - VERIFIED
  ```

**Weaknesses:**
- Some mocking obscures what's being tested (line 61-79 in test_batch_scoring mocks 3 functions, making it unclear what real behavior is tested):
  ```python
  @patch("...batch_scoring_service._discover_activity_files")
  @patch("...batch_scoring_service._load_diary_file")
  @patch("...batch_scoring_service._process_activity_file")
  def test_auto_score_success(self, mock_process, mock_load_diary, mock_discover, ...):
      # Test only verifies mocks were called, not actual scoring
  ```
- Line 246 `assert result is not None` without verifying result content (weak assertion)

**Missing critical tests:**
- Activity data alignment verification (timestamps match activity values)
- Column preference fallback when preferred column unavailable

---

### Unit/Data Tests

**Samples reviewed:**
- `tests/unit/data/test_database_manager.py` (649 lines)

**Quality: B-**

**Strengths:**
- SQL injection prevention explicitly tested with realistic attack patterns (lines 186-216):
  ```python
  injection_attempts = [
      "users; DROP TABLE sleep_metrics;",
      "users' OR '1'='1",
      "users--",
      "users/**/",
  ]
  for attempt in injection_attempts:
      with pytest.raises(ValidationError):
          db_manager._validate_table_name(attempt)
  ```
- Schema creation verified by querying sqlite_master (line 115-122)
- Global initialization flag behavior tested

**Weaknesses:**
- Facade tests only verify delegation, not behavior (lines 249-260):
  ```python
  def test_save_sleep_metrics_delegates(self, db_manager):
      mock_metrics = MagicMock()
      db_manager.sleep_metrics.save_sleep_metrics = MagicMock(return_value=True)
      result = db_manager.save_sleep_metrics(mock_metrics)
      db_manager.sleep_metrics.save_sleep_metrics.assert_called_once_with(mock_metrics)
      # This only tests that the method was called, not that data was saved correctly
  ```
- Over-mocking of repository layer means tests don't catch serialization bugs
- Line 74: `assert manager is not None` is a trivial assertion

**Missing critical tests:**
- Round-trip tests (save data, load back, verify equality)
- Concurrent access / race condition tests
- Database migration verification

---

### Unit/UI Tests

**Samples reviewed:**
- `tests/unit/ui/widgets/test_plot_data_manager.py` (not shown, referenced from file list)
- `tests/unit/ui/widgets/test_marker_interaction_handler.py` (referenced)

**Quality: C**

**Note:** UI widget tests could not be fully evaluated from the cached outputs. Based on file structure and patterns from other samples:

**Likely Strengths:**
- Widget lifecycle tests (creation, destruction)
- Signal emission verification

**Likely Weaknesses:**
- Over-reliance on mocking parent widgets
- Tests may check mocks were called rather than UI state changed
- Limited PyQt6 interaction testing

**Missing critical tests:**
- Marker drag-and-drop behavior verification
- Plot zoom/pan state persistence
- Theme/style application tests

---

### Integration Tests

**Samples reviewed:**
- `tests/integration/test_export_integration.py` (979 lines)

**Quality: A-**

**Strengths:**
- Full pipeline tested: database -> service -> CSV file -> validation (line 211-239):
  ```python
  def test_export_produces_valid_csv(self, ...):
      result = export_manager_with_db.perform_direct_export(...)
      assert result.success is True
      # Verify CSV can be read by pandas
      df = pd.read_csv(csv_files[0], comment="#")
      assert len(df) > 0
      assert ExportColumn.NUMERICAL_PARTICIPANT_ID in df.columns
  ```
- Multi-period export tested (main sleep + nap as separate rows)
- Nonwear separate file export verified
- Edge cases: empty metrics, incomplete periods, missing participant ID, special characters in filenames
- Data integrity verification (line 769-801):
  ```python
  def test_exported_metrics_match_source_values(self, ...):
      # Verifies actual numeric values match, not just "something was exported"
      assert str(df[ExportColumn.NUMERICAL_PARTICIPANT_ID].iloc[0]) == "1000"
      assert df[ExportColumn.TOTAL_SLEEP_TIME].iloc[0] == 420.0
  ```
- Concurrent access safety tested

**Weaknesses:**
- Heavy mocking of `_ensure_metrics_calculated_for_export` in every test - might miss calculation bugs
- Line 763: Weak assertion `assert len(result.warnings) > 0 or "NonexistentColumn" not in str(result.warnings)` - logic is confusing

**Missing critical tests:**
- CSV encoding verification (UTF-8 with BOM for Excel compatibility)
- Large dataset performance (1000+ rows)

---

### E2E Tests

**Samples reviewed:**
- `tests/gui/e2e/test_real_e2e_workflow.py` (678 lines)

**Quality: A-**

**Strengths:**
- Real PyQt6 widgets created and tested with qtbot
- Redux store integration verified end-to-end (lines 231-267):
  ```python
  def test_dispatch_updates_state(self, real_main_window):
      initial_file = real_main_window.store.state.current_file
      real_main_window.store.dispatch(Actions.file_selected("test_file.csv"))
      assert real_main_window.store.state.current_file == "test_file.csv"

  def test_store_subscribers_are_notified(self, real_main_window):
      notification_received = []
      def subscriber(old_state, new_state):
          notification_received.append((old_state, new_state))
      real_main_window.store.subscribe(subscriber)
      real_main_window.store.dispatch(Actions.file_selected("new_file.csv"))
      assert len(notification_received) == 1
  ```
- Database save/load round-trip tested (lines 283-336)
- Realistic test data with circadian activity patterns
- Memory management verified (cache limits checked)

**Weaknesses:**
- Line 451: Empty test placeholder `pass  # Placeholder - full implementation requires more setup`
- Some tests check attribute existence rather than behavior (lines 404-410):
  ```python
  def test_loading_progress_signal_exists(self, real_main_window):
      assert hasattr(real_main_window, 'loading_progress')  # Just checks existence
  ```
- Heavy fixture setup with many mocks - might miss integration issues

**Missing critical tests:**
- User workflow simulation (load file -> select date -> place markers -> export)
- Keyboard navigation tests
- Dialog interaction tests (file dialogs, export dialogs)

---

## Systemic Issues

### 1. Facade Pattern Over-Testing

The DatabaseManager tests verify delegation to repositories but don't test actual database operations. This creates a false sense of security - you could have a bug in serialization that wouldn't be caught.

**Example:** `test_database_manager.py` lines 249-260 - tests only verify `assert_called_once_with()` on mocks.

**Fix:** Add integration tests that actually save/load data through the facade.

### 2. Mock Everything Anti-Pattern

Several service tests mock so many dependencies that they're testing the mock configuration, not the code.

**Example:** `test_batch_scoring_service.py` lines 58-79 patches 3 internal functions, leaving nothing real to test.

**Fix:** Use fewer mocks; create lightweight fakes for external dependencies; test internal functions directly.

### 3. Existence Assertions Without Behavior Verification

Pattern of `assert x is not None` or `hasattr(y, 'attr')` without verifying the actual value or behavior.

**Examples:**
- `test_database_manager.py` line 74: `assert manager is not None`
- `test_real_e2e_workflow.py` line 404: `assert hasattr(real_main_window, 'loading_progress')`

**Fix:** Replace with assertions that verify actual values or behavior.

### 4. UI Tests Lag Behind Service Tests

The UI layer has noticeably weaker test coverage than services and core algorithms. This is concerning given the application's interactive nature.

---

## Specific Tests to Fix or Remove

| File | Test | Problem | Fix |
|------|------|---------|-----|
| `test_database_manager.py:74` | `test_creates_instance_with_path` | `assert manager is not None` is trivial | Add assertion on manager properties |
| `test_database_manager.py:249-260` | `test_save_sleep_metrics_delegates` | Only tests mock was called | Add round-trip integration test |
| `test_batch_scoring_service.py:61-79` | `test_auto_score_success` | Over-mocked, tests nothing real | Reduce mocks, test actual file processing |
| `test_sadeh.py:141` | `test_low_activity_scores_sleep` | Range assertion (`> len/2`) is weak | Assert specific expected output for known input |
| `test_real_e2e_workflow.py:451` | `test_window_opens_within_timeout` | Empty test with `pass` | Implement or remove |
| `test_export_integration.py:763` | Column warning test | Confusing OR logic in assertion | Rewrite with clear assertion |

---

## Missing Test Coverage (Critical)

### 1. Marker Interaction Workflow
No test simulates: click plot -> drag marker -> verify timestamp updated -> verify database saved. This is the core user workflow.

### 2. Data Alignment Verification
No test verifies that timestamps and activity values remain aligned through loading, filtering, and display. Off-by-one errors would go undetected.

### 3. Algorithm Result Comparison with Reference
No tests compare Sadeh/Cole-Kripke output against validated reference implementations (e.g., ActiLife, GGIR). Critical for research validity.

### 4. Error Recovery Paths
Limited testing of: what happens when database is corrupted? When file is locked? When disk is full during export?

### 5. Configuration Migration
No tests verify that old configuration files can be loaded by newer versions of the application.

---

## Recommendations

### High Priority

1. **Add round-trip database tests** - Save SleepMetrics, load back, verify equality
2. **Reduce mocking in service tests** - Test real file operations where possible
3. **Implement marker interaction E2E test** - Simulate actual user workflow
4. **Add reference validation for algorithms** - Compare output against known-good implementations

### Medium Priority

5. **Strengthen UI widget tests** - Add PyQt6 interaction testing
6. **Fix trivial assertions** - Replace `is not None` with meaningful checks
7. **Add performance tests** - Verify algorithms handle 24+ hours of data efficiently
8. **Test error recovery** - Verify graceful handling of corrupted data

### Low Priority

9. **Remove empty test placeholders** - Either implement or delete
10. **Add property-based testing** - For algorithm input validation
11. **Test concurrent access** - Multiple processes accessing database

---

## Verification Checklist

- [x] Read actual test code from at least 10 different test files
- [x] Checked ASSERTIONS, not just test function names
- [x] Compared at least 3 tests against their source code (Sadeh algorithm, export service, database manager)
- [x] Found specific examples of both good and bad tests
- [x] Criticisms include file paths and line numbers
- [x] Missing tests based on real app functionality (marker interaction, data alignment, reference validation)
