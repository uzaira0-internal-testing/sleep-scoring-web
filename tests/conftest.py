#!/usr/bin/env python3
"""
Shared test fixtures for the sleep scoring application.
Provides common test setup and utilities.

IMPORTANT: Tests use isolated database and QSettings to avoid affecting real app data.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

try:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication, QWidget

    from sleep_scoring_app.core.dataclasses import ParticipantInfo
    from sleep_scoring_app.data.database import DatabaseManager
    from sleep_scoring_app.services.unified_data_service import UnifiedDataService
    from sleep_scoring_app.ui.utils.config import ConfigManager

    _HAS_DESKTOP_APP = True
except ImportError:
    _HAS_DESKTOP_APP = False


@pytest.fixture(scope="session", autouse=True)
def isolated_test_environment(tmp_path_factory):
    """
    Session-scoped fixture that isolates ALL tests from real app data.

    This fixture:
    1. Creates a temporary directory for test databases
    2. Configures QSettings to use a test-specific scope
    3. Patches the database path function to use temp location

    This runs automatically for all tests (autouse=True).
    """
    if not _HAS_DESKTOP_APP:
        yield {}
        return

    # Create session-wide temp directory for test data
    test_data_dir = tmp_path_factory.mktemp("sleep_scoring_test_data")
    test_db_path = test_data_dir / "test_sleep_scoring.db"

    # Store original environment
    original_env = os.environ.copy()

    # Set environment variable to signal test mode
    os.environ["SLEEP_SCORING_TEST_MODE"] = "1"
    os.environ["SLEEP_SCORING_TEST_DB_PATH"] = str(test_db_path)

    # Configure QSettings to use test-specific organization/app name
    # This ensures tests don't read/write real user settings
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)

    # Patch the database path function to return test path
    def get_test_database_path():
        return test_db_path

    with patch("sleep_scoring_app.data.database.get_database_path", get_test_database_path):
        yield {
            "test_data_dir": test_data_dir,
            "test_db_path": test_db_path,
        }

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture(autouse=True)
def isolated_qsettings(tmp_path):
    """
    Function-scoped fixture that gives each test its own QSettings.

    This ensures tests don't interfere with each other's settings.
    """
    if not _HAS_DESKTOP_APP:
        yield None
        return

    from threading import Lock

    from sleep_scoring_app.utils.resource_resolver import get_config_path

    # Create a unique settings file for this test
    settings_path = tmp_path / "test_settings.ini"

    # Create QSettings pointing to test file
    test_settings = QSettings(str(settings_path), QSettings.Format.IniFormat)

    # Patch ConfigManager to use test settings
    original_init = ConfigManager.__init__

    def patched_init(self):
        self._lock = Lock()
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self.config = None
        self.config_file = get_config_path()
        self.config_dir = self.config_file.parent
        self.config_dir.mkdir(exist_ok=True)
        self.config = self.try_load_config()

    with patch.object(ConfigManager, "__init__", patched_init):
        yield test_settings

    # Clean up settings
    test_settings.clear()
    test_settings.sync()


@pytest.fixture
def test_database(tmp_path):
    """
    Create a fresh test database for tests that need direct database access.

    Returns a DatabaseManager instance pointing to a temporary database.
    """
    db_path = tmp_path / "test.db"
    return DatabaseManager(db_path=db_path)
    # Cleanup happens automatically when tmp_path is cleaned up


@pytest.fixture
def test_config_manager(isolated_qsettings, tmp_path):
    """
    Create a ConfigManager that uses isolated test settings.

    Note: The isolated_qsettings fixture already patches ConfigManager.__init__
    to use test-specific QSettings, so we can just instantiate normally.
    """
    config_manager = ConfigManager()
    yield config_manager

    # Cleanup
    if config_manager.settings:
        config_manager.settings.clear()
        config_manager.settings.sync()


@pytest.fixture(scope="session")
def qt_app():
    """Provide QApplication for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# pytest-qt configuration
def pytest_configure(config):
    """Configure pytest-qt for headless testing."""
    config.addinivalue_line("markers", "gui: mark test as a GUI test")
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "e2e: mark test as an end-to-end test")


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_db_path(temp_dir):
    """Provide path for test database."""
    return temp_dir / "test_sleep_scoring.db"


@pytest.fixture
def mock_database_manager(test_db_path):
    """Create a mock database manager."""
    mock_db = Mock(spec=DatabaseManager)
    mock_db.db_path = test_db_path
    mock_db.get_database_stats.return_value = {"unique_files": 5, "total_records": 150, "autosave_records": 10}
    mock_db.load_sleep_metrics.return_value = []
    return mock_db


@pytest.fixture
def mock_config_manager():
    """Create a mock config manager with default values."""
    mock_config = Mock(spec=ConfigManager)

    # Create a mock config object with all necessary attributes
    mock_config_obj = Mock()
    mock_config_obj.use_database = True
    mock_config_obj.activity_use_database = True
    mock_config_obj.data_folder = "/test/data/folder"
    mock_config_obj.export_directory = "/test/export"
    mock_config_obj.import_activity_directory = "/test/import/activity"
    mock_config_obj.import_nonwear_directory = "/test/import/nonwear"
    mock_config_obj.window_width = 1280
    mock_config_obj.window_height = 720
    mock_config_obj.epoch_length = 60
    mock_config_obj.skip_rows = 10

    mock_config.config = mock_config_obj
    mock_config.update_data_folder = Mock()
    mock_config.update_export_directory = Mock()
    mock_config.save_config = Mock()

    return mock_config


@pytest.fixture
def mock_unified_data_service():
    """Create a mock unified data service."""
    mock_service = Mock(spec=UnifiedDataService)
    mock_service.get_database_mode.return_value = True
    mock_service.available_files = []
    mock_service.get_data_folder.return_value = "/test/data/folder"

    return mock_service


@pytest.fixture
def sample_participant_info():
    """Provide sample participant information."""
    return ParticipantInfo(numerical_id="4000", full_id="4000 BO G1", group="G1", timepoint=ParticipantTimepoint.BASELINE, date="2021-04-20")


@pytest.fixture
def sample_participant_files():
    """Provide sample file information for participant extraction testing."""
    from sleep_scoring_app.core.constants import ParticipantGroup, ParticipantTimepoint

    return [
        {
            "filename": "P1-4000 T1 (2021-04-20)60sec.csv",
            "expected": {
                "numerical_id": "P1-4000",
                "timepoint": ParticipantTimepoint.T1,
                "group": ParticipantGroup.GROUP_1,
                "full_id": "P1-4000 T1 G1",
            },
        },
        {
            "filename": "P1-4001 T2 (2021-05-15)60sec.csv",
            "expected": {
                "numerical_id": "P1-4001",
                "timepoint": ParticipantTimepoint.T2,
                "group": ParticipantGroup.GROUP_1,
                "full_id": "P1-4001 T2 G1",
            },
        },
        {
            "filename": "4002 T3 (2021-06-10)60sec.csv",
            "expected": {
                "numerical_id": "P1-4002",
                "timepoint": ParticipantTimepoint.T3,
                "group": ParticipantGroup.GROUP_1,
                "full_id": "P1-4002 T3 G1",
            },
        },
    ]


@pytest.fixture
def mock_main_window(qt_app, mock_database_manager, mock_config_manager, mock_unified_data_service):
    """Create a mock main window for tab testing.

    Uses a real QWidget as the base to satisfy PyQt6's parent type requirements.
    """
    mock_window = QWidget()  # Real QWidget to satisfy Qt parent type requirements

    # Set up essential attributes
    mock_window.db_manager = mock_database_manager
    mock_window.config_manager = mock_config_manager
    mock_window.data_service = mock_unified_data_service
    mock_window.export_manager = Mock()

    # UI state
    mock_window.available_files = []
    mock_window.selected_file = None
    mock_window.current_date_index = 0
    mock_window.available_dates = []

    # Mock methods that tabs might call
    mock_window.load_available_files = Mock()
    mock_window.update_status_bar = Mock()
    mock_window.update_folder_info_label = Mock()
    mock_window.browse_data_folder = Mock()
    mock_window.load_data_folder = Mock()
    mock_window.browse_activity_directory = Mock()
    mock_window.browse_nonwear_directory = Mock()
    mock_window.start_activity_import = Mock()
    mock_window.start_nonwear_import = Mock()
    mock_window.clear_all_markers = Mock()
    mock_window.perform_direct_export = Mock()
    mock_window.browse_export_output_directory = Mock()
    mock_window._get_cached_metrics = Mock(return_value=[])
    mock_window.on_epoch_length_changed = Mock()
    mock_window.on_skip_rows_changed = Mock()
    mock_window.browse_activity_files = Mock()
    mock_window.browse_nonwear_files = Mock()
    mock_window.state_manager = Mock()

    # Mock UI elements that might be referenced
    mock_window.file_selector = Mock()
    mock_window.date_dropdown = Mock()
    mock_window.plot_widget = Mock()

    return mock_window


@pytest.fixture
def participant_extraction_test_cases():
    """Provide comprehensive test cases for participant extraction."""
    return {
        "valid_primary_patterns": [
            {
                "filename": "4000 BO (2021-04-20)60sec",
                "expected": {"numerical_id": "4000", "timepoint": "BO", "group": "G1", "date": "2021-04-20", "confidence": 1.0},
            },
            {
                "filename": "4001 P2g2 (2021-05-15)60sec",
                "expected": {"numerical_id": "4001", "timepoint": "P2", "group": "G2", "date": "2021-05-15", "confidence": 1.0},
            },
            {
                "filename": "4002 P1g3 (2021-06-10)60sec",
                "expected": {"numerical_id": "4002", "timepoint": "P1", "group": "G3", "date": "2021-06-10", "confidence": 1.0},
            },
        ],
        "fallback_patterns": [
            {
                "filename": "4000_data.csv",
                "expected": {
                    "numerical_id": "4000",
                    "timepoint": "BO",  # default
                    "group": "G1",  # default
                    "date": None,
                    "confidence": 0.6,
                },
            },
            {
                "filename": "participant_4001.csv",
                "expected": {
                    "numerical_id": "4001",
                    "timepoint": "BO",  # default
                    "group": "G1",  # default
                    "date": None,
                    "confidence": 0.6,
                },
            },
        ],
        "unknown_files": [
            {
                "filename": "random_file.csv",
                "expected": {
                    "numerical_id": "random_fil",  # truncated filename
                    "timepoint": "BO",  # default
                    "group": "G1",  # default
                    "date": None,
                    "confidence": 0.2,
                },
            }
        ],
    }


@pytest.fixture
def mock_import_service():
    """Create a mock import service."""
    mock_service = Mock()
    mock_service.import_activity_data = Mock()
    mock_service.import_nonwear_data = Mock()
    return mock_service


def create_test_file_info(filename: str, path: str | None = None) -> dict[str, Any]:
    """Helper function to create file info dictionaries for testing."""
    return {"filename": filename, "path": path or f"/test/path/{filename}", "size": 1024, "modified": "2021-04-20 10:00:00"}


def assert_participant_extraction(actual: Any, expected: dict[str, Any], check_confidence: bool = True) -> None:
    """Helper function to assert participant extraction results."""
    assert actual.numerical_id == expected["numerical_id"]
    assert actual.timepoint == expected["timepoint"]
    assert actual.group == expected["group"]

    if "date" in expected:
        assert actual.date == expected["date"]

    if check_confidence and "confidence" in expected:
        assert abs(actual.confidence - expected["confidence"]) < 0.1


def create_mock_tab_ui_elements():
    """Create mock UI elements commonly used in tabs."""
    return {"buttons": Mock(), "labels": Mock(), "inputs": Mock(), "tables": Mock(), "dropdowns": Mock()}
