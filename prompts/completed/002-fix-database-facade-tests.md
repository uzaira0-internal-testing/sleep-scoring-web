<objective>
Fix database manager tests that only verify delegation to repositories (facade testing) without testing actual database operations. Add round-trip integration tests that save and load data to verify serialization correctness.
</objective>

<context>
The test quality review identified that `tests/unit/data/test_database_manager.py` has weak tests:
- Line 74: `assert manager is not None` is trivial
- Lines 249-260: Tests only verify `assert_called_once_with()` on mocks, not actual data persistence
- Over-mocking of repository layer means serialization bugs would go undetected

Read CLAUDE.md for project conventions. This is a PyQt6 sleep scoring application.
</context>

<requirements>
1. **Fix trivial assertions** in `tests/unit/data/test_database_manager.py`:
   - Line 74: Replace `assert manager is not None` with assertions on manager properties (e.g., verify `manager.db_path` equals expected path)

2. **Add round-trip integration tests** that:
   - Create a SleepMetrics object with known values
   - Save it to the database
   - Load it back
   - Verify ALL fields match the original (not just `is not None`)

3. **Add round-trip tests for other entities**:
   - ManualNonwearPeriod save/load round-trip
   - SleepPeriod save/load round-trip
   - FileInfo save/load round-trip

4. **Test data integrity edge cases**:
   - Special characters in participant IDs
   - Unicode in notes fields
   - None/null values in optional fields
   - Very large numeric values

5. **Keep existing mock-based unit tests** - they verify API contracts. Add new tests, don't remove working ones.
</requirements>

<implementation>
Use pytest fixtures with `tmp_path` to create real SQLite databases for testing:

```python
@pytest.fixture
def real_db(tmp_path):
    """Create a real database for round-trip testing."""
    db_path = tmp_path / "test.db"
    manager = DatabaseManager(db_path)
    manager.initialize()
    return manager
```

For round-trip tests, assert on ALL fields:

```python
def test_sleep_metrics_round_trip(self, real_db):
    # Create with known values
    original = SleepMetrics(
        total_sleep_time=420.0,
        sleep_efficiency=0.85,
        waso=60,
        # ... all fields
    )

    # Save
    real_db.save_sleep_metrics("file.csv", "2024-01-15", "main_sleep", original)

    # Load
    loaded = real_db.load_sleep_metrics("file.csv", "2024-01-15", "main_sleep")

    # Verify ALL fields
    assert loaded.total_sleep_time == original.total_sleep_time
    assert loaded.sleep_efficiency == original.sleep_efficiency
    # ... all fields
```
</implementation>

<output>
Modify: `tests/unit/data/test_database_manager.py`
- Fix trivial assertions
- Add round-trip integration tests
- Add edge case tests

Run tests after modifications: `pytest tests/unit/data/test_database_manager.py -v`
</output>

<verification>
Before declaring complete:
1. Run `pytest tests/unit/data/test_database_manager.py -v` - all tests pass
2. Verify at least 5 new round-trip tests were added
3. Confirm no `assert x is not None` without additional meaningful assertions
4. Ensure tests create real database files (no mocks for the database itself)
</verification>

<success_criteria>
- All existing tests still pass
- At least 5 new round-trip integration tests added
- All dataclass fields are verified in round-trip tests (not just existence)
- Edge cases (special chars, unicode, nulls) are covered
- No trivial assertions remain without accompanying meaningful assertions
</success_criteria>
