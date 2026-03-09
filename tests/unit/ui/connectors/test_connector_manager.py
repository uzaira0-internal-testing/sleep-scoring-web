"""Tests for StoreConnectorManager — ensures all connectors are created on
connect_all and cleaned up on disconnect_all.

Uses a real UIStore; heavily mocks MainWindow since we only test wiring.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.ui.store import UIStore


@pytest.fixture
def store() -> UIStore:
    return UIStore()


@pytest.fixture
def mock_main_window() -> MagicMock:
    """Comprehensive mock fulfilling MainWindowProtocol for connector creation."""
    mw = MagicMock()
    # StoreConnectorManager accesses many attributes during __init__
    mw.data_service = MagicMock()
    mw.db_manager = MagicMock()
    mw.plot_widget = MagicMock()
    mw.analysis_tab = MagicMock()
    mw.data_settings_tab = MagicMock()
    mw.study_settings_tab = MagicMock()
    mw.export_manager = MagicMock()
    mw.session_service = MagicMock()
    mw.config_manager = MagicMock()
    mw.table_manager = MagicMock()
    mw.file_table = MagicMock()
    mw.date_dropdown = MagicMock()
    mw.no_sleep_btn = MagicMock()
    return mw


class TestStoreConnectorManagerLifecycle:
    """Manager creates and disconnects all connectors."""

    def test_connect_all_creates_connectors(self, store: UIStore, mock_main_window: MagicMock) -> None:
        """connect_all_components creates a non-empty list of connectors."""
        from sleep_scoring_app.ui.connectors.manager import connect_all_components

        manager = connect_all_components(store, mock_main_window)

        assert len(manager.connectors) > 0
        manager.disconnect_all()

    def test_disconnect_all_clears_list(self, store: UIStore, mock_main_window: MagicMock) -> None:
        """disconnect_all empties the connectors list."""
        from sleep_scoring_app.ui.connectors.manager import connect_all_components

        manager = connect_all_components(store, mock_main_window)
        assert len(manager.connectors) > 0

        manager.disconnect_all()
        assert len(manager.connectors) == 0

    def test_no_double_connect(self, store: UIStore, mock_main_window: MagicMock) -> None:
        """Creating two managers doesn't break — each tracks its own connectors."""
        from sleep_scoring_app.ui.connectors.manager import connect_all_components

        manager1 = connect_all_components(store, mock_main_window)
        count1 = len(manager1.connectors)

        manager2 = connect_all_components(store, mock_main_window)
        count2 = len(manager2.connectors)

        # Both should have the same number of connectors
        assert count1 == count2
        assert count1 > 0

        manager1.disconnect_all()
        manager2.disconnect_all()
