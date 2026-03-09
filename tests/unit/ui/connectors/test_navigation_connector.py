"""Tests for NavigationConnector — ensures prev/next buttons and dropdown
update correctly in response to store state changes.

Uses a real UIStore with real state transitions; mocks only Qt widgets.
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest

from sleep_scoring_app.ui.connectors.navigation import NavigationConnector
from sleep_scoring_app.ui.store import Actions, UIStore


@pytest.fixture
def store() -> UIStore:
    """Real UIStore seeded with a file and three dates."""
    s = UIStore()
    s.dispatch(Actions.file_selected(filename="TEST-001.csv"))
    s.dispatch(Actions.dates_loaded(dates=["2024-06-15", "2024-06-16", "2024-06-17"]))
    s.dispatch(Actions.date_selected(date_index=1))  # middle date
    return s


@pytest.fixture
def mock_main_window() -> MagicMock:
    """Mock main window with analysis_tab and plot_widget."""
    mw = MagicMock()

    # analysis_tab has prev/next buttons, date_dropdown, weekday_label
    tab = mw.analysis_tab
    tab.prev_date_btn = MagicMock()
    tab.next_date_btn = MagicMock()
    tab.date_dropdown = MagicMock()
    tab.date_dropdown.blockSignals = MagicMock()
    tab.weekday_label = MagicMock()
    tab.update_activity_source_dropdown = MagicMock()

    # plot_widget
    mw.plot_widget = MagicMock()

    return mw


class TestNavigationConnectorSubscription:
    """Connector subscribes and unsubscribes properly."""

    def test_subscribes_on_init(self, store: UIStore, mock_main_window: MagicMock) -> None:
        """Creating the connector subscribes to the store."""
        initial_count = len(store._subscribers)
        connector = NavigationConnector(store, mock_main_window)
        assert len(store._subscribers) == initial_count + 1
        connector.disconnect()

    def test_unsubscribes_on_disconnect(self, store: UIStore, mock_main_window: MagicMock) -> None:
        """Disconnecting removes the subscription."""
        initial_count = len(store._subscribers)
        connector = NavigationConnector(store, mock_main_window)
        connector.disconnect()
        assert len(store._subscribers) == initial_count


class TestNavigationConnectorButtonState:
    """Prev/next buttons enabled/disabled at boundaries."""

    def test_prev_disabled_at_first_date(self, store: UIStore, mock_main_window: MagicMock) -> None:
        """Prev button is disabled when at first date."""
        connector = NavigationConnector(store, mock_main_window)

        store.dispatch(Actions.date_selected(date_index=0))

        mock_main_window.analysis_tab.prev_date_btn.setEnabled.assert_called_with(False)
        mock_main_window.analysis_tab.next_date_btn.setEnabled.assert_called_with(True)
        connector.disconnect()

    def test_next_disabled_at_last_date(self, store: UIStore, mock_main_window: MagicMock) -> None:
        """Next button is disabled when at last date."""
        connector = NavigationConnector(store, mock_main_window)

        store.dispatch(Actions.date_selected(date_index=2))

        mock_main_window.analysis_tab.prev_date_btn.setEnabled.assert_called_with(True)
        mock_main_window.analysis_tab.next_date_btn.setEnabled.assert_called_with(False)
        connector.disconnect()

    def test_both_enabled_at_middle_date(self, store: UIStore, mock_main_window: MagicMock) -> None:
        """Both buttons enabled when at a middle date."""
        connector = NavigationConnector(store, mock_main_window)

        # Already at index 1 (middle), trigger a state change to force update
        store.dispatch(Actions.date_navigated(1))  # move to index 2
        store.dispatch(Actions.date_navigated(-1))  # back to index 1

        mock_main_window.analysis_tab.prev_date_btn.setEnabled.assert_called_with(True)
        mock_main_window.analysis_tab.next_date_btn.setEnabled.assert_called_with(True)
        connector.disconnect()


class TestNavigationConnectorIgnoresUnrelated:
    """Connector should not trigger heavy updates for unrelated changes."""

    def test_ignores_marker_changes_after_initial_sync(
        self, store: UIStore, mock_main_window: MagicMock
    ) -> None:
        """After initial sync, marker changes should not re-clear plot markers."""
        connector = NavigationConnector(store, mock_main_window)

        # Trigger one state change so NavigationConnector caches _last_date_str
        store.dispatch(Actions.view_mode_changed(24))

        # Now reset mocks after the connector has synced
        mock_main_window.plot_widget.clear_sleep_markers.reset_mock()

        # Dispatch marker-only action — should NOT trigger navigation update
        store.dispatch(Actions.sleep_markers_changed(None))

        mock_main_window.plot_widget.clear_sleep_markers.assert_not_called()
        connector.disconnect()
