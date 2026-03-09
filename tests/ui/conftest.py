#!/usr/bin/env python3
"""
UI-specific test fixtures.
Provides fixtures for testing PyQt6 UI components.

IMPORTANT: All dialog fixtures are autouse=True to prevent blocking dialogs
from appearing during automated test runs.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox


@pytest.fixture(autouse=True)
def mock_message_box(monkeypatch):
    """Mock QMessageBox to prevent blocking during tests.

    NOTE: autouse=True ensures ALL ui tests automatically get mocked dialogs,
    preventing any blocking dialog boxes during test runs.
    """
    mock_box = Mock()
    mock_box.exec.return_value = QMessageBox.StandardButton.Yes
    mock_box.information = Mock(return_value=QMessageBox.StandardButton.Ok)
    mock_box.warning = Mock(return_value=QMessageBox.StandardButton.Ok)
    mock_box.question = Mock(return_value=QMessageBox.StandardButton.Yes)
    mock_box.critical = Mock(return_value=QMessageBox.StandardButton.Ok)

    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.exec", lambda self: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.information", mock_box.information)
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.warning", mock_box.warning)
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.question", mock_box.question)
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.critical", mock_box.critical)

    return mock_box


@pytest.fixture(autouse=True)
def mock_file_dialog(monkeypatch):
    """Mock QFileDialog to prevent blocking during tests.

    NOTE: autouse=True ensures ALL ui tests automatically get mocked dialogs,
    preventing any blocking file dialogs during test runs.
    """
    mock_dialog = Mock()
    mock_dialog.getExistingDirectory = Mock(return_value="/test/directory")
    mock_dialog.getOpenFileName = Mock(return_value=("/test/file.csv", "CSV Files (*.csv)"))
    mock_dialog.getOpenFileNames = Mock(return_value=(["/test/file1.csv", "/test/file2.csv"], "CSV Files (*.csv)"))
    mock_dialog.getSaveFileName = Mock(return_value=("/test/output.csv", "CSV Files (*.csv)"))

    monkeypatch.setattr("PyQt6.QtWidgets.QFileDialog.getExistingDirectory", mock_dialog.getExistingDirectory)
    monkeypatch.setattr("PyQt6.QtWidgets.QFileDialog.getOpenFileName", mock_dialog.getOpenFileName)
    monkeypatch.setattr("PyQt6.QtWidgets.QFileDialog.getOpenFileNames", mock_dialog.getOpenFileNames)
    monkeypatch.setattr("PyQt6.QtWidgets.QFileDialog.getSaveFileName", mock_dialog.getSaveFileName)

    return mock_dialog


@pytest.fixture(autouse=True)
def mock_input_dialog(monkeypatch):
    """Mock QInputDialog to prevent blocking during tests.

    NOTE: autouse=True ensures ALL ui tests automatically get mocked dialogs,
    preventing any blocking input dialogs during test runs.
    """
    mock_dialog = Mock()
    mock_dialog.getText = Mock(return_value=("test_input", True))
    mock_dialog.getInt = Mock(return_value=(42, True))
    mock_dialog.getDouble = Mock(return_value=(3.14, True))
    mock_dialog.getItem = Mock(return_value=("item1", True))

    monkeypatch.setattr("PyQt6.QtWidgets.QInputDialog.getText", mock_dialog.getText)
    monkeypatch.setattr("PyQt6.QtWidgets.QInputDialog.getInt", mock_dialog.getInt)
    monkeypatch.setattr("PyQt6.QtWidgets.QInputDialog.getDouble", mock_dialog.getDouble)
    monkeypatch.setattr("PyQt6.QtWidgets.QInputDialog.getItem", mock_dialog.getItem)

    return mock_dialog


@pytest.fixture(autouse=True)
def prevent_widget_show(monkeypatch):
    """Prevent widgets from actually showing during tests.

    This prevents test windows from popping up and potentially blocking.
    Only applies to show() calls - widgets can still be created and manipulated.
    """
    from PyQt6.QtWidgets import QWidget

    # Store original show
    original_show = QWidget.show

    def mock_show(self):
        """Mock show that doesn't actually display the widget."""
        # Still process events but don't display
        pass

    # Only patch if not in a qtbot context (qtbot handles this)
    # monkeypatch.setattr(QWidget, "show", mock_show)

    return original_show
