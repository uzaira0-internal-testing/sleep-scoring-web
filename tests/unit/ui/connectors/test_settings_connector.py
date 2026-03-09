"""Tests for AlgorithmConfigConnector — ensures calibration and imputation
checkboxes update correctly in response to store state changes.

Uses a real UIStore with real state transitions; mocks only Qt widgets.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sleep_scoring_app.ui.connectors.settings import AlgorithmConfigConnector
from sleep_scoring_app.ui.store import Actions, UIStore


@pytest.fixture
def store() -> UIStore:
    """Real UIStore seeded with a file."""
    s = UIStore()
    s.dispatch(Actions.file_selected(filename="TEST-001.csv"))
    return s


@pytest.fixture
def mock_main_window() -> MagicMock:
    """Mock main window with data_settings_tab."""
    mw = MagicMock()
    tab = mw.data_settings_tab

    # Checkboxes that the connector updates
    tab.auto_calibrate_check = MagicMock()
    tab.auto_calibrate_check.blockSignals = MagicMock()
    tab.impute_gaps_check = MagicMock()
    tab.impute_gaps_check.blockSignals = MagicMock()

    return mw


class TestAlgorithmConfigConnectorSubscription:
    """Connector subscribes and unsubscribes properly."""

    def test_subscribes_on_init(self, store: UIStore, mock_main_window: MagicMock) -> None:
        initial_count = len(store._subscribers)
        connector = AlgorithmConfigConnector(store, mock_main_window)
        assert len(store._subscribers) == initial_count + 1
        connector.disconnect()

    def test_unsubscribes_on_disconnect(self, store: UIStore, mock_main_window: MagicMock) -> None:
        initial_count = len(store._subscribers)
        connector = AlgorithmConfigConnector(store, mock_main_window)
        connector.disconnect()
        assert len(store._subscribers) == initial_count


class TestAlgorithmConfigConnectorReacts:
    """Connector updates checkboxes when calibration/imputation settings change."""

    def test_updates_checkbox_on_calibration_toggle(
        self, store: UIStore, mock_main_window: MagicMock
    ) -> None:
        """Toggling calibration dispatches and connector syncs checkbox."""
        connector = AlgorithmConfigConnector(store, mock_main_window)
        check = mock_main_window.data_settings_tab.auto_calibrate_check
        check.setChecked.reset_mock()

        store.dispatch(Actions.calibration_toggled(False))

        check.setChecked.assert_called_with(False)
        connector.disconnect()

    def test_updates_checkbox_on_imputation_toggle(
        self, store: UIStore, mock_main_window: MagicMock
    ) -> None:
        """Toggling imputation dispatches and connector syncs checkbox."""
        connector = AlgorithmConfigConnector(store, mock_main_window)
        check = mock_main_window.data_settings_tab.impute_gaps_check
        check.setChecked.reset_mock()

        store.dispatch(Actions.imputation_toggled(False))

        check.setChecked.assert_called_with(False)
        connector.disconnect()

    def test_ignores_unrelated_state_changes(
        self, store: UIStore, mock_main_window: MagicMock
    ) -> None:
        """Connector does not update UI for unrelated state changes."""
        connector = AlgorithmConfigConnector(store, mock_main_window)
        check = mock_main_window.data_settings_tab.auto_calibrate_check
        check.setChecked.reset_mock()

        # Dispatch an unrelated action
        store.dispatch(Actions.view_mode_changed(24))

        check.setChecked.assert_not_called()
        connector.disconnect()
