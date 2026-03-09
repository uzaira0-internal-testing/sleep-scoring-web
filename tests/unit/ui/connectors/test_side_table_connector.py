"""
Tests for SideTableConnector — ensures side tables clear on date/file navigation
and when markers become None.

Uses a real UIStore with real state transitions; mocks only Qt widgets.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sleep_scoring_app.core.constants import MarkerCategory, MarkerType
from sleep_scoring_app.core.dataclasses import SleepPeriod
from sleep_scoring_app.core.dataclasses_markers import DailySleepMarkers
from sleep_scoring_app.ui.connectors.table import SideTableConnector
from sleep_scoring_app.ui.store import Actions, UIStore


@pytest.fixture
def store() -> UIStore:
    """Real UIStore seeded with a file, two dates, and sleep mode."""
    s = UIStore()
    s.dispatch(Actions.file_selected(filename="TEST-001.csv"))
    s.dispatch(Actions.dates_loaded(dates=["2024-06-15", "2024-06-16"]))
    s.dispatch(Actions.date_selected(date_index=0))
    s.dispatch(Actions.marker_mode_changed(MarkerCategory.SLEEP))
    return s


@pytest.fixture
def mock_main_window() -> MagicMock:
    """Mock main window with table_manager and plot_widget."""
    mw = MagicMock()
    mw.table_manager.update_marker_tables = MagicMock()
    mw.table_manager.get_marker_data_cached = MagicMock(return_value=[{"row": 1}])
    mw.plot_widget.get_selected_marker_period.return_value = None
    mw.plot_widget.get_selected_nonwear_period.return_value = None
    return mw


def _make_markers() -> DailySleepMarkers:
    markers = DailySleepMarkers()
    markers.period_1 = SleepPeriod(
        onset_timestamp=1718492400.0,
        offset_timestamp=1718521200.0,
        marker_index=1,
        marker_type=MarkerType.MAIN_SLEEP,
    )
    return markers


class TestSideTableClearsOnDateChange:
    """Tables must clear when navigating to a different date."""

    def test_tables_clear_on_date_navigation(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Navigating to a new date clears the side tables immediately."""
        # Load markers on date 0
        store.dispatch(Actions.sleep_markers_changed(_make_markers()))

        connector = SideTableConnector(store, mock_main_window)
        mock_main_window.table_manager.update_marker_tables.reset_mock()

        # Navigate to date 1
        store.dispatch(Actions.date_navigated(1))

        # Tables should have been cleared (called with empty lists)
        mock_main_window.table_manager.update_marker_tables.assert_called_with([], [])
        connector.disconnect()

    def test_tables_clear_on_file_change(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Switching to a different file clears the side tables."""
        store.dispatch(Actions.sleep_markers_changed(_make_markers()))

        connector = SideTableConnector(store, mock_main_window)
        mock_main_window.table_manager.update_marker_tables.reset_mock()

        store.dispatch(Actions.file_selected(filename="OTHER-002.csv"))

        mock_main_window.table_manager.update_marker_tables.assert_called_with([], [])
        connector.disconnect()


class TestSideTableClearsOnNullMarkers:
    """Tables must clear when markers become None."""

    def test_tables_clear_when_sleep_markers_become_none(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Tables clear when sleep markers transition from present to None."""
        store.dispatch(Actions.sleep_markers_changed(_make_markers()))

        connector = SideTableConnector(store, mock_main_window)
        mock_main_window.table_manager.update_marker_tables.reset_mock()

        # Clear markers (sets current_sleep_markers to None)
        store.dispatch(Actions.markers_cleared())

        mock_main_window.table_manager.update_marker_tables.assert_called_with([], [])
        connector.disconnect()

    def test_tables_clear_when_markers_loaded_as_none(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Tables clear when markers_loaded dispatches None sleep markers."""
        store.dispatch(Actions.sleep_markers_changed(_make_markers()))

        connector = SideTableConnector(store, mock_main_window)
        mock_main_window.table_manager.update_marker_tables.reset_mock()

        store.dispatch(Actions.markers_loaded(sleep=None, nonwear=None))

        mock_main_window.table_manager.update_marker_tables.assert_called_with([], [])
        connector.disconnect()


class TestSideTableNonwearMode:
    """Nonwear mode tables also clear properly."""

    def test_tables_clear_on_date_change_in_nonwear_mode(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Tables clear on date navigation even in nonwear mode."""
        store.dispatch(Actions.marker_mode_changed(MarkerCategory.NONWEAR))

        connector = SideTableConnector(store, mock_main_window)
        mock_main_window.table_manager.update_marker_tables.reset_mock()

        store.dispatch(Actions.date_navigated(1))

        mock_main_window.table_manager.update_marker_tables.assert_called_with([], [])
        connector.disconnect()

    def test_tables_clear_when_nonwear_markers_become_none(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Tables clear when nonwear markers transition from present to None."""
        store.dispatch(Actions.marker_mode_changed(MarkerCategory.NONWEAR))
        # Load non-None nonwear markers first so clearing actually changes state
        store.dispatch(Actions.markers_loaded(sleep=None, nonwear=MagicMock()))

        connector = SideTableConnector(store, mock_main_window)
        mock_main_window.table_manager.update_marker_tables.reset_mock()

        store.dispatch(Actions.markers_cleared())

        mock_main_window.table_manager.update_marker_tables.assert_called_with([], [])
        connector.disconnect()
