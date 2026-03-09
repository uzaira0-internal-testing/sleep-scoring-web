# Task: Thoroughly Test Export Functionality

## Objective
Comprehensively test the export functionality in the sleep scoring application to ensure all export paths work correctly, data integrity is maintained, and edge cases are handled properly.

## Context
The export system consists of:
- **ExportService** (`services/export_service.py`) - Core export logic
- **ExportTab** (`ui/export_tab.py`) - UI tab for configuring exports
- **ExportDialog** (`ui/export_dialog.py`) - Modal dialog for export options
- **Column Registry** (`utils/column_registry.py`) - Manages exportable columns

## Test Areas

### 1. Unit Tests for ExportService

Create/update tests in `tests/unit/test_export_service.py`:

#### 1.1 ExportResult Dataclass
- Test `add_warning()` accumulates warnings
- Test `add_error()` accumulates errors
- Test `has_issues()` returns True when warnings or errors present
- Test `has_issues()` returns False when clean

#### 1.2 CSV Sanitization
- Test `_sanitize_csv_cell()` prefixes formula injection characters (`=`, `+`, `-`, `@`, `\t`, `\r`)
- Test non-string values pass through unchanged
- Test empty strings handled correctly
- Test normal strings pass through unchanged

#### 1.3 Path Validation
- Test `_validate_export_path()` with valid local path
- Test `_validate_export_path()` with non-existent parent directory
- Test `_validate_export_path()` with network UNC path (if applicable)
- Test `_validate_export_path()` with unmapped drive letter
- Test `_validate_export_path()` with read-only directory (permission error)

#### 1.4 Atomic CSV Write
- Test `_atomic_csv_write()` creates file successfully
- Test `_atomic_csv_write()` cleans up temp file on failure
- Test `_atomic_csv_write()` fails on empty DataFrame

#### 1.5 Data Grouping
- Test `_group_export_data()` with grouping_option=0 (all in one file)
- Test `_group_export_data()` with grouping_option=1 (by participant)
- Test `_group_export_data()` with grouping_option=2 (by group)
- Test `_group_export_data()` with grouping_option=3 (by timepoint)

#### 1.6 Direct Export
- Test `perform_direct_export()` with valid data produces CSV files
- Test `perform_direct_export()` with empty metrics list returns error
- Test `perform_direct_export()` creates output directory if missing
- Test `perform_direct_export()` respects column selection
- Test `perform_direct_export()` includes metadata when requested
- Test `perform_direct_export()` excludes metadata when not requested
- Test `perform_direct_export()` exports nonwear to separate file when enabled

#### 1.7 Metrics Calculation Before Export
- Test `_ensure_metrics_calculated_for_export()` calculates missing metrics
- Test caching of activity data prevents redundant database calls
- Test handling of missing activity data (returns warning, continues)

### 2. Integration Tests

Create/update tests in `tests/integration/test_export_integration.py`:

#### 2.1 Full Export Pipeline
- Load sample data into database
- Create sleep markers with complete periods
- Export via `perform_direct_export()`
- Verify CSV contents match database state
- Verify all selected columns present
- Verify data sorted correctly (by participant, date, marker index)

#### 2.2 Multi-Period Export
- Create main sleep + nap markers for same participant/date
- Export and verify each period appears as separate row
- Verify Marker Index column correctly identifies periods
- Verify Period Type column shows "Main Sleep" vs "Nap"

#### 2.3 Nonwear Separate Export
- Create sleep and nonwear markers
- Export with `export_nonwear_separate=True`
- Verify two files created (sleep data + nonwear markers)
- Verify nonwear file contains correct columns and data

### 3. Edge Cases

#### 3.1 Empty Data
- Export with no metrics in database
- Export with metrics but no complete periods
- Export with participant having no numerical_id

#### 3.2 Special Characters
- Participant IDs with special characters
- Filenames with spaces
- Export paths with unicode characters

#### 3.3 Column Selection
- Export with all columns selected
- Export with only required columns
- Export with non-existent columns in selection (should be skipped with warning)

#### 3.4 Concurrent Access
- Export while database is being written to
- Multiple exports simultaneously (should use unique temp files via PID)

### 4. UI Tests (Manual or E2E)

#### 4.1 ExportTab
- Column count label updates when columns selected
- Data summary refreshes with correct counts
- Grouping option persists in config
- Output directory persists in config
- Export button triggers export

#### 4.2 ExportDialog
- Select/Deselect All works for sleep columns
- Select/Deselect All works for nonwear columns
- Data summary loads asynchronously (no UI freeze)
- Output directory picker works

### 5. Data Integrity Verification

#### 5.1 Metrics Accuracy
- Export metrics should match calculated values
- TST, Efficiency, WASO should be correct for exported periods
- Nonwear overlap minutes should be calculated correctly

#### 5.2 Timestamp Formatting
- Onset/offset times formatted as HH:MM
- Datetime columns formatted as YYYY-MM-DD HH:MM:SS
- Duration in minutes rounded to appropriate precision

## Test Data Requirements

Create test fixtures with:
- Multiple participants (at least 3)
- Multiple dates per participant
- Main sleep + nap periods
- Nonwear markers overlapping and non-overlapping with sleep
- Various group/timepoint combinations

## Success Criteria

1. All unit tests pass
2. All integration tests pass
3. Export produces valid CSV that can be read by pandas
4. Data integrity maintained (no data loss or corruption)
5. Error handling provides meaningful feedback
6. Performance acceptable for large datasets (100+ participants)

## Files to Create/Modify

- `tests/unit/test_export_service.py` - Unit tests
- `tests/integration/test_export_integration.py` - Integration tests
- `tests/fixtures/export_fixtures.py` - Test data fixtures (if needed)

## Important Notes

- DO NOT modify production code unless bugs are found
- Use pytest fixtures for test data setup
- Mock database access for unit tests where appropriate
- Use temporary directories for file output tests
- Clean up test files after each test
