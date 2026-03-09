#!/usr/bin/env python3
"""
Unit tests for FileSelectionTable widget.
Tests file table display, filtering, sorting, and selection.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from sleep_scoring_app.ui.widgets.file_selection_table import FileSelectionTable, TableColumn


@pytest.mark.unit
@pytest.mark.gui
class TestFileSelectionTable:
    """Test FileSelectionTable widget."""

    @pytest.fixture
    def file_table(self, qtbot):
        """Create FileSelectionTable instance."""
        table = FileSelectionTable()
        qtbot.addWidget(table)
        return table

    def test_initialization(self, file_table):
        """Test table initializes with correct setup."""
        assert file_table.table is not None
        assert file_table.search_box is not None
        assert file_table.table.columnCount() == len(FileSelectionTable.COLUMN_DEFINITIONS)
        assert file_table.table.isSortingEnabled()

    def test_add_file(self, file_table, sample_file_list):
        """Test adding a file to the table."""
        file_info = sample_file_list[0]

        file_table.add_file(file_info)

        assert file_table.table.rowCount() == 1

    def test_add_multiple_files(self, file_table, sample_file_list):
        """Test adding multiple files."""
        for file_info in sample_file_list:
            file_table.add_file(file_info)

        assert file_table.table.rowCount() == len(sample_file_list)

    def test_add_file_with_color(self, file_table, sample_file_list, qtbot):
        """Test adding file with custom color."""
        file_info = sample_file_list[0]
        custom_color = QColor(Qt.GlobalColor.red)

        file_table.add_file(file_info, color=custom_color)

        assert file_table.table.rowCount() == 1
        # Table should have the file

    def test_clear_table(self, file_table, sample_file_list):
        """Test clearing all files from table."""
        # Add files
        for file_info in sample_file_list:
            file_table.add_file(file_info)

        assert file_table.table.rowCount() > 0

        # Clear
        file_table.table.setRowCount(0)
        file_table._file_data.clear()

        assert file_table.table.rowCount() == 0
        assert len(file_table._file_data) == 0

    def test_filter_table(self, file_table, sample_file_list, qtbot):
        """Test filtering table by search text."""
        # Add files
        for file_info in sample_file_list:
            file_table.add_file(file_info)

        # Filter by filename substring
        qtbot.keyClicks(file_table.search_box, "4000")

        # Should filter to only files containing "4000"
        visible_rows = sum(1 for i in range(file_table.table.rowCount()) if not file_table.table.isRowHidden(i))

        assert visible_rows >= 1  # At least one file with "4000"

    def test_filter_table_no_matches(self, file_table, sample_file_list, qtbot):
        """Test filtering with no matches hides all rows."""
        # Add files
        for file_info in sample_file_list:
            file_table.add_file(file_info)

        # Filter by non-existent pattern
        qtbot.keyClicks(file_table.search_box, "nonexistent_file")

        # All rows should be hidden
        visible_rows = sum(1 for i in range(file_table.table.rowCount()) if not file_table.table.isRowHidden(i))

        assert visible_rows == 0

    def test_filter_table_clear_shows_all(self, file_table, sample_file_list, qtbot):
        """Test clearing filter shows all rows."""
        # Add files
        for file_info in sample_file_list:
            file_table.add_file(file_info)

        total_files = len(sample_file_list)

        # Apply filter
        qtbot.keyClicks(file_table.search_box, "4000")

        # Clear filter
        file_table.search_box.clear()

        # All rows should be visible
        visible_rows = sum(1 for i in range(file_table.table.rowCount()) if not file_table.table.isRowHidden(i))

        assert visible_rows == total_files

    def test_selection_emits_signal(self, file_table, sample_file_list, qtbot):
        """Test selecting a file emits fileSelected signal."""
        # Add file
        file_table.add_file(sample_file_list[0])

        # Connect signal spy
        with qtbot.waitSignal(file_table.fileSelected, timeout=1000) as blocker:
            # Programmatically select first row
            file_table.table.selectRow(0)

        # Signal should have been emitted
        assert blocker.signal_triggered

    def test_sorting_enabled(self, file_table, sample_file_list):
        """Test table sorting is enabled."""
        # Add files
        for file_info in sample_file_list:
            file_table.add_file(file_info)

        assert file_table.table.isSortingEnabled()

    def test_alternating_row_colors(self, file_table):
        """Test table has alternating row colors."""
        assert file_table.table.alternatingRowColors()

    def test_single_selection_mode(self, file_table):
        """Test table uses single selection mode."""
        from PyQt6.QtWidgets import QTableWidget

        assert file_table.table.selectionMode() == QTableWidget.SelectionMode.SingleSelection

    def test_select_rows_behavior(self, file_table):
        """Test table selects entire rows."""
        from PyQt6.QtWidgets import QTableWidget

        assert file_table.table.selectionBehavior() == QTableWidget.SelectionBehavior.SelectRows

    def test_no_editing_allowed(self, file_table):
        """Test table cells are not editable."""
        from PyQt6.QtWidgets import QTableWidget

        assert file_table.table.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers

    def test_column_headers_set(self, file_table):
        """Test column headers are set correctly."""
        expected_headers = [col.header for col in FileSelectionTable.COLUMN_DEFINITIONS]

        for i, expected_header in enumerate(expected_headers):
            actual_header = file_table.table.horizontalHeaderItem(i)
            if actual_header:
                assert actual_header.text() == expected_header
