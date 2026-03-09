<objective>
Fix over-mocking in service tests and strengthen weak assertions in algorithm tests. Tests should verify real behavior, not just that mocks were called.
</objective>

<context>
The test quality review identified issues in:
1. `tests/unit/services/test_batch_scoring_service.py`:
   - Lines 61-79: Patches 3 internal functions, leaving nothing real to test
   - Line 246: `assert result is not None` without verifying content

2. `tests/unit/core/test_sadeh.py`:
   - Line 141: `assert sum(result) > len(result) / 2` is weak compared to asserting specific expected output

3. `tests/unit/services/test_data_loading_service.py`:
   - Some tests check `is not None` without verifying actual values

Read CLAUDE.md for project conventions. This is a PyQt6 sleep scoring application.
</context>

<requirements>
1. **Reduce mocking in batch_scoring_service tests**:
   - Identify tests that mock internal functions (`_discover_activity_files`, `_load_diary_file`, etc.)
   - Create lightweight test fixtures (real CSV files) instead of mocking
   - Test actual file processing, not just that mocks were called

2. **Strengthen algorithm assertions** in `test_sadeh.py`:
   - For `test_low_activity_scores_sleep`: Replace range assertion with specific expected output
   - Create known-good reference inputs with expected outputs
   - Document where reference values came from (paper, validated implementation, etc.)

3. **Fix weak assertions** throughout service tests:
   - Find all `assert x is not None` patterns
   - Add follow-up assertions that verify actual content/behavior
   - Pattern: `assert result is not None` becomes:
     ```python
     assert result is not None
     assert result.success is True  # or whatever the actual verification should be
     assert len(result.data) > 0
     ```

4. **Add behavior-focused tests** for batch scoring:
   - Test that scoring a file with known activity pattern produces expected sleep/wake classification
   - Test that diary times constrain sleep detection correctly
</requirements>

<implementation>
For algorithm tests, use deterministic test cases:

```python
def test_low_activity_scores_sleep_exact(self) -> None:
    """Known input produces known output - verified against reference implementation."""
    # 11-element window of zeros should score as sleep
    # Reference: This matches ActiLife output for zero-activity epochs
    input_data = [0] * 20
    expected = [1] * 20  # All epochs should be sleep (1)

    result = score_activity(input_data)

    assert result == expected, f"Expected {expected}, got {result}"
```

For service tests, use real files:

```python
@pytest.fixture
def sample_activity_csv(tmp_path):
    """Create a real CSV file for testing."""
    csv_content = """epoch,activity
0,10
1,5
2,0
..."""
    csv_file = tmp_path / "activity.csv"
    csv_file.write_text(csv_content)
    return csv_file

def test_process_activity_file_real(self, sample_activity_csv):
    # Test with real file, no mocking
    result = _process_activity_file(sample_activity_csv)
    assert result.success
    assert len(result.epochs) > 0
```
</implementation>

<output>
Modify these files:
- `tests/unit/services/test_batch_scoring_service.py` - reduce mocking, add real file tests
- `tests/unit/core/test_sadeh.py` - strengthen assertions with exact expected outputs
- `tests/unit/services/test_data_loading_service.py` - fix weak assertions

Run tests after modifications: `pytest tests/unit/services/ tests/unit/core/test_sadeh.py -v`
</output>

<verification>
Before declaring complete:
1. Run `pytest tests/unit/services/ tests/unit/core/test_sadeh.py -v` - all tests pass
2. Count remaining `@patch` decorators in batch_scoring_service tests - should be reduced
3. Grep for `assert.*is not None` patterns - each should have a follow-up assertion
4. Confirm algorithm tests have at least 2 tests with exact expected outputs
</verification>

<success_criteria>
- All tests pass
- At least 3 batch scoring tests use real files instead of mocks
- All `assert x is not None` are followed by content verification
- Algorithm tests include exact expected output verification for at least 2 test cases
- No tests that only verify mocks were called without any behavior verification
</success_criteria>
