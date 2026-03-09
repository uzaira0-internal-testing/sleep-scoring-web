"""
Tests for Store Connectors.

Tests the connector pattern, representative connectors, and StoreConnectorManager.
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from sleep_scoring_app.core.constants import MarkerCategory
from sleep_scoring_app.ui.connectors import (
    AutoSaveConnector,
    DateDropdownConnector,
    FileListConnector,
    MarkerModeConnector,
    NavigationConnector,
    SaveButtonConnector,
    StatusConnector,
    StoreConnectorManager,
    ViewModeConnector,
    connect_all_components,
)
from sleep_scoring_app.ui.store import Actions, UIState, UIStore


@pytest.fixture
def store() -> UIStore:
    """Create a fresh store for testing."""
    return UIStore()


@pytest.fixture
def mock_main_window() -> MagicMock:
    """Create a mock main window with all required attributes."""
    main_window = MagicMock()

    # Save button
    main_window.save_markers_btn = MagicMock()

    # Date dropdown at main_window level (used by DateDropdownConnector)
    main_window.date_dropdown = MagicMock()
    main_window.date_dropdown.blockSignals = MagicMock()
    main_window.date_dropdown.clear = MagicMock()
    main_window.date_dropdown.addItem = MagicMock()
    main_window.date_dropdown.setCurrentIndex = MagicMock()
    main_window.date_dropdown.count = MagicMock(return_value=0)
    main_window.date_dropdown.setEnabled = MagicMock()
    main_window.date_dropdown.setItemData = MagicMock()

    # Analysis tab with no_sleep_btn
    main_window.analysis_tab = MagicMock()
    main_window.analysis_tab.no_sleep_btn = MagicMock()
    main_window.analysis_tab.marker_table = MagicMock()
    main_window.analysis_tab.marker_table.current_markers = None
    main_window.analysis_tab.date_dropdown = MagicMock()
    main_window.analysis_tab.file_dropdown = MagicMock()
    main_window.analysis_tab.date_dropdown.blockSignals = MagicMock()
    main_window.analysis_tab.date_dropdown.clear = MagicMock()
    main_window.analysis_tab.date_dropdown.addItems = MagicMock()
    main_window.analysis_tab.date_dropdown.setCurrentIndex = MagicMock()
    main_window.analysis_tab.date_dropdown.count = MagicMock(return_value=0)
    main_window.analysis_tab.update_activity_source_dropdown = MagicMock()

    # Navigation buttons (actual names from NavigationConnector)
    main_window.analysis_tab.prev_date_btn = MagicMock()
    main_window.analysis_tab.next_date_btn = MagicMock()

    # View mode buttons
    main_window.analysis_tab.view_24h_btn = MagicMock()
    main_window.analysis_tab.view_48h_btn = MagicMock()

    # Marker mode buttons
    main_window.analysis_tab.sleep_mode_btn = MagicMock()
    main_window.analysis_tab.nonwear_mode_btn = MagicMock()

    # Autosave checkbox and status label (actual names from AutoSaveConnector)
    main_window.analysis_tab.auto_save_checkbox = MagicMock()
    main_window.analysis_tab.auto_save_checkbox.blockSignals = MagicMock()
    main_window.analysis_tab.autosave_status_label = MagicMock()

    # File management
    main_window.file_management_widget = MagicMock()
    main_window.file_management_widget.file_list = MagicMock()

    # Data settings tab
    main_window.data_settings_tab = MagicMock()
    main_window.data_settings_tab.file_table = MagicMock()

    # Plot widget
    main_window.plot_widget = MagicMock()
    main_window.plot_widget.clear_sleep_markers = MagicMock()
    main_window.plot_widget.clear_nonwear_markers = MagicMock()
    main_window.plot_widget.clear_sleep_onset_offset_markers = MagicMock()

    # Side table
    main_window.side_table = MagicMock()

    # Services
    main_window.data_service = MagicMock()
    main_window.file_service = MagicMock()
    main_window.marker_service = MagicMock()
    main_window.cache_service = MagicMock()

    # Export manager for DateDropdownConnector _update_visuals
    main_window.export_manager = MagicMock()
    main_window.export_manager.db_manager = MagicMock()
    main_window.export_manager.db_manager.load_sleep_metrics = MagicMock(return_value=[])

    # Config
    main_window.config = MagicMock()

    return main_window


class TestConnectorPattern:
    """Tests for the common connector pattern."""

    def test_connector_subscribes_to_store(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Connectors subscribe to store on init."""
        initial_subscribers = len(store._subscribers)

        connector = SaveButtonConnector(store, mock_main_window)

        assert len(store._subscribers) == initial_subscribers + 1
        connector.disconnect()

    def test_connector_disconnect_unsubscribes(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Connectors unsubscribe on disconnect."""
        connector = SaveButtonConnector(store, mock_main_window)
        subscribers_after_connect = len(store._subscribers)

        connector.disconnect()

        assert len(store._subscribers) == subscribers_after_connect - 1

    def test_connector_updates_on_init(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Connectors update UI on initialization."""
        # Set initial state
        store.dispatch(Actions.auto_save_toggled(enabled=False))

        connector = SaveButtonConnector(store, mock_main_window)

        # Button should be visible (auto_save disabled)
        mock_main_window.save_markers_btn.setVisible.assert_called()
        connector.disconnect()


class TestSaveButtonConnector:
    """Tests for SaveButtonConnector."""

    def test_button_hidden_when_autosave_enabled(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Save button hidden when autosave is enabled."""
        store.dispatch(Actions.auto_save_toggled(enabled=True))
        connector = SaveButtonConnector(store, mock_main_window)

        mock_main_window.save_markers_btn.setVisible.assert_called_with(False)
        connector.disconnect()

    def test_button_visible_when_autosave_disabled(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Save button visible when autosave is disabled."""
        store.dispatch(Actions.auto_save_toggled(enabled=False))
        connector = SaveButtonConnector(store, mock_main_window)

        mock_main_window.save_markers_btn.setVisible.assert_called_with(True)
        connector.disconnect()

    def test_button_disabled_when_no_markers(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Save button disabled when no markers."""
        store.dispatch(Actions.auto_save_toggled(enabled=False))
        connector = SaveButtonConnector(store, mock_main_window)

        mock_main_window.save_markers_btn.setEnabled.assert_called_with(False)
        connector.disconnect()

    def test_button_enabled_when_dirty(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Save button enabled when markers are dirty."""
        store.dispatch(Actions.auto_save_toggled(enabled=False))
        connector = SaveButtonConnector(store, mock_main_window)

        # Add dirty markers
        store.dispatch(Actions.sleep_markers_changed(markers=MagicMock()))

        mock_main_window.save_markers_btn.setEnabled.assert_called_with(True)
        connector.disconnect()

    def test_reacts_to_dirty_state_changes(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Connector reacts to dirty state changes."""
        connector = SaveButtonConnector(store, mock_main_window)
        initial_call_count = mock_main_window.save_markers_btn.setEnabled.call_count

        # Trigger dirty state
        store.dispatch(Actions.sleep_markers_changed(markers=MagicMock()))

        assert mock_main_window.save_markers_btn.setEnabled.call_count > initial_call_count
        connector.disconnect()


class TestStatusConnector:
    """Tests for StatusConnector."""

    def test_updates_no_sleep_button(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Updates no sleep button based on state."""
        connector = StatusConnector(store, mock_main_window)

        # Should have called setText on the button
        mock_main_window.analysis_tab.no_sleep_btn.setText.assert_called()
        connector.disconnect()

    def test_reacts_to_no_sleep_flag_change(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Reacts when is_no_sleep_marked changes."""
        connector = StatusConnector(store, mock_main_window)
        initial_calls = mock_main_window.analysis_tab.no_sleep_btn.setText.call_count

        # Load markers with no_sleep flag
        store.dispatch(Actions.markers_loaded(sleep=None, nonwear=None, is_no_sleep=True))

        assert mock_main_window.analysis_tab.no_sleep_btn.setText.call_count > initial_calls
        connector.disconnect()


class TestDateDropdownConnector:
    """Tests for DateDropdownConnector.

    Note: DateDropdownConnector uses main_window.date_dropdown (NOT analysis_tab.date_dropdown)
    """

    def test_populates_dropdown_on_dates_loaded(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Populates dropdown when dates are loaded."""
        connector = DateDropdownConnector(store, mock_main_window)

        # Load dates
        store.dispatch(Actions.dates_loaded(dates=["2024-01-01", "2024-01-02", "2024-01-03"]))

        # Uses addItem (singular) in a loop, not addItems
        mock_main_window.date_dropdown.addItem.assert_called()
        connector.disconnect()

    def test_updates_selection_on_date_change(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Updates selection when date index changes."""
        connector = DateDropdownConnector(store, mock_main_window)

        # Load dates first
        store.dispatch(Actions.dates_loaded(dates=["2024-01-01", "2024-01-02"]))

        # Change selection
        store.dispatch(Actions.date_selected(date_index=1))

        mock_main_window.date_dropdown.setCurrentIndex.assert_called()
        connector.disconnect()

    def test_clears_dropdown_on_file_change(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Clears dropdown when file changes (dates change to empty)."""
        # Set up initial state with dates
        store.dispatch(Actions.dates_loaded(dates=["2024-01-01"]))
        connector = DateDropdownConnector(store, mock_main_window)

        # Change file triggers dates_loaded with empty list (in real app)
        # We simulate this by loading empty dates
        store.dispatch(Actions.dates_loaded(dates=[]))

        mock_main_window.date_dropdown.clear.assert_called()
        connector.disconnect()


class TestViewModeConnector:
    """Tests for ViewModeConnector."""

    def test_updates_buttons_on_view_mode_change(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Updates view mode buttons on state change."""
        connector = ViewModeConnector(store, mock_main_window)

        store.dispatch(Actions.view_mode_changed(hours=24))

        # Should have updated button checked states
        mock_main_window.analysis_tab.view_24h_btn.setChecked.assert_called()
        connector.disconnect()

    def test_initial_state_sets_48h(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Initial state (48h) is reflected in buttons."""
        connector = ViewModeConnector(store, mock_main_window)

        # Default is 48h, so 48h button should be checked
        mock_main_window.analysis_tab.view_48h_btn.setChecked.assert_called_with(True)
        connector.disconnect()


class TestMarkerModeConnector:
    """Tests for MarkerModeConnector."""

    def test_updates_buttons_on_mode_change(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Updates marker mode buttons on state change."""
        connector = MarkerModeConnector(store, mock_main_window)

        store.dispatch(Actions.marker_mode_changed(category=MarkerCategory.NONWEAR))

        mock_main_window.analysis_tab.nonwear_mode_btn.setChecked.assert_called_with(True)
        connector.disconnect()

    def test_initial_state_sleep_mode(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Initial state is SLEEP mode."""
        connector = MarkerModeConnector(store, mock_main_window)

        mock_main_window.analysis_tab.sleep_mode_btn.setChecked.assert_called_with(True)
        connector.disconnect()


class TestAutoSaveConnector:
    """Tests for AutoSaveConnector.

    Note: Uses tab.auto_save_checkbox (NOT autosave_checkbox)
    """

    def test_updates_checkbox_on_toggle(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Updates checkbox when autosave toggled."""
        connector = AutoSaveConnector(store, mock_main_window)

        store.dispatch(Actions.auto_save_toggled(enabled=False))

        mock_main_window.analysis_tab.auto_save_checkbox.setChecked.assert_called_with(False)
        connector.disconnect()

    def test_initial_state_checked(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Initial state has autosave enabled (checked)."""
        connector = AutoSaveConnector(store, mock_main_window)

        mock_main_window.analysis_tab.auto_save_checkbox.setChecked.assert_called_with(True)
        connector.disconnect()


class TestNavigationConnector:
    """Tests for NavigationConnector.

    Note: Uses tab.prev_date_btn and tab.next_date_btn (NOT prev_btn/next_btn)
    """

    def test_disables_prev_at_start(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Disables prev button at first date."""
        store.dispatch(Actions.dates_loaded(dates=["2024-01-01", "2024-01-02", "2024-01-03"]))
        store.dispatch(Actions.date_selected(date_index=0))

        connector = NavigationConnector(store, mock_main_window)

        mock_main_window.analysis_tab.prev_date_btn.setEnabled.assert_called_with(False)
        connector.disconnect()

    def test_disables_next_at_end(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Disables next button at last date."""
        store.dispatch(Actions.dates_loaded(dates=["2024-01-01", "2024-01-02", "2024-01-03"]))
        store.dispatch(Actions.date_selected(date_index=2))

        connector = NavigationConnector(store, mock_main_window)

        mock_main_window.analysis_tab.next_date_btn.setEnabled.assert_called_with(False)
        connector.disconnect()

    def test_enables_both_in_middle(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Enables both buttons in middle of date range."""
        store.dispatch(Actions.dates_loaded(dates=["2024-01-01", "2024-01-02", "2024-01-03"]))
        store.dispatch(Actions.date_selected(date_index=1))

        connector = NavigationConnector(store, mock_main_window)

        # Both should be enabled (check last call was True)
        prev_calls = list(mock_main_window.analysis_tab.prev_date_btn.setEnabled.call_args_list)
        next_calls = list(mock_main_window.analysis_tab.next_date_btn.setEnabled.call_args_list)

        # Get the most recent calls
        assert prev_calls[-1][0][0] is True
        assert next_calls[-1][0][0] is True
        connector.disconnect()


class TestStoreConnectorManager:
    """Tests for StoreConnectorManager."""

    def test_creates_all_connectors(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Creates all connectors on init."""
        manager = StoreConnectorManager(store, mock_main_window)

        assert len(manager.connectors) > 0
        manager.disconnect_all()

    def test_disconnect_all_clears_connectors(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """disconnect_all clears all connectors."""
        manager = StoreConnectorManager(store, mock_main_window)
        initial_count = len(manager.connectors)

        manager.disconnect_all()

        assert len(manager.connectors) == 0
        assert initial_count > 0  # Verify we had connectors

    def test_disconnect_all_unsubscribes_from_store(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """disconnect_all unsubscribes all from store."""
        subscribers_before = len(store._subscribers)
        manager = StoreConnectorManager(store, mock_main_window)
        subscribers_with_connectors = len(store._subscribers)

        manager.disconnect_all()

        # Should have fewer subscribers after disconnect
        assert len(store._subscribers) < subscribers_with_connectors


class TestConnectAllComponents:
    """Tests for connect_all_components helper function."""

    def test_returns_manager(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Returns StoreConnectorManager instance."""
        manager = connect_all_components(store, mock_main_window)

        assert isinstance(manager, StoreConnectorManager)
        manager.disconnect_all()

    def test_manager_has_connectors(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Returned manager has connectors."""
        manager = connect_all_components(store, mock_main_window)

        assert len(manager.connectors) > 10  # Should have many connectors
        manager.disconnect_all()


class TestStateChangeFiltering:
    """Tests for efficient state change filtering."""

    def test_connector_ignores_unrelated_changes(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Connectors ignore unrelated state changes."""
        connector = SaveButtonConnector(store, mock_main_window)
        initial_calls = mock_main_window.save_markers_btn.setEnabled.call_count

        # Dispatch unrelated action (window geometry)
        store.dispatch(Actions.window_geometry_changed(x=100, y=200, width=800, height=600))

        # Save button should not have been updated
        assert mock_main_window.save_markers_btn.setEnabled.call_count == initial_calls
        connector.disconnect()

    def test_connector_responds_to_related_changes(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Connectors respond to related state changes."""
        connector = SaveButtonConnector(store, mock_main_window)
        initial_calls = mock_main_window.save_markers_btn.setEnabled.call_count

        # Dispatch related action (markers changed)
        store.dispatch(Actions.sleep_markers_changed(markers=MagicMock()))

        # Save button should have been updated
        assert mock_main_window.save_markers_btn.setEnabled.call_count > initial_calls
        connector.disconnect()


class TestMultipleConnectors:
    """Tests for multiple connectors working together."""

    def test_multiple_connectors_same_state(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Multiple connectors can subscribe to same store."""
        connector1 = SaveButtonConnector(store, mock_main_window)
        connector2 = StatusConnector(store, mock_main_window)
        connector3 = ViewModeConnector(store, mock_main_window)

        # All should be subscribed
        assert len(store._subscribers) >= 3

        # Dispatch an action - all should receive it
        store.dispatch(Actions.view_mode_changed(hours=24))

        connector1.disconnect()
        connector2.disconnect()
        connector3.disconnect()

    def test_one_disconnect_doesnt_affect_others(
        self,
        store: UIStore,
        mock_main_window: MagicMock,
    ) -> None:
        """Disconnecting one connector doesn't affect others."""
        connector1 = SaveButtonConnector(store, mock_main_window)
        connector2 = ViewModeConnector(store, mock_main_window)

        connector1.disconnect()

        # connector2 should still work
        initial_calls = mock_main_window.analysis_tab.view_24h_btn.setChecked.call_count
        store.dispatch(Actions.view_mode_changed(hours=24))

        assert mock_main_window.analysis_tab.view_24h_btn.setChecked.call_count > initial_calls
        connector2.disconnect()
