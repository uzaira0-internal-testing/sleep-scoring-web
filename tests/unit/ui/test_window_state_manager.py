"""Focused tests for WindowStateManager marker persistence behavior."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from sleep_scoring_app.ui.store import Actions, UIStore
from sleep_scoring_app.ui.window_state import WindowStateManager


def _build_manager() -> tuple[WindowStateManager, UIStore, MagicMock, MagicMock, MagicMock]:
    """Create a WindowStateManager with minimal mocked dependencies."""
    store = UIStore()

    navigation = MagicMock()
    navigation.selected_file = "test.csv"
    navigation.available_dates = [date(2024, 1, 15)]
    navigation.current_date_index = 0

    marker_ops = MagicMock()
    app_state = MagicMock()

    services = MagicMock()
    services.db_manager = MagicMock()
    services.data_service = MagicMock()
    services.export_tab = None
    services.plot_widget = MagicMock()

    main_window = MagicMock()
    main_window._autosave_sleep_markers_to_db = MagicMock(return_value=True)
    main_window._autosave_nonwear_markers_to_db = MagicMock(return_value=True)
    main_window.plot_widget = MagicMock()
    main_window.onset_time_input = MagicMock()
    main_window.offset_time_input = MagicMock()

    manager = WindowStateManager(
        store=store,
        navigation=navigation,
        marker_ops=marker_ops,
        app_state=app_state,
        services=services,
        parent=main_window,
    )
    return manager, store, services, navigation, main_window


def _make_complete_sleep_markers() -> tuple[MagicMock, MagicMock]:
    """Create a mocked complete sleep marker set."""
    main_sleep = MagicMock()
    main_sleep.is_complete = True
    main_sleep.onset_timestamp = 1000.0
    main_sleep.offset_timestamp = 1600.0

    sleep_markers = MagicMock()
    sleep_markers.get_complete_periods.return_value = [main_sleep]
    sleep_markers.get_main_sleep.return_value = main_sleep
    return sleep_markers, main_sleep


def _make_complete_nonwear_markers() -> MagicMock:
    """Create a mocked complete nonwear marker set."""
    nonwear_markers = MagicMock()
    nonwear_markers.get_complete_periods.return_value = [MagicMock()]
    return nonwear_markers


def test_save_current_markers_does_not_clear_dirty_on_sleep_save_failure() -> None:
    """Manual save keeps dirty state when sleep marker DB save fails."""
    manager, store, _services, _navigation, main_window = _build_manager()
    sleep_markers, _main_sleep = _make_complete_sleep_markers()

    store.dispatch(Actions.sleep_markers_changed(markers=sleep_markers))
    main_window._autosave_sleep_markers_to_db.return_value = False

    with (
        patch("sleep_scoring_app.ui.window_state.QMessageBox.warning"),
        patch("sleep_scoring_app.ui.window_state.QMessageBox.information"),
        patch("sleep_scoring_app.ui.window_state.QMessageBox.critical") as mock_critical,
    ):
        manager.save_current_markers()

    assert store.state.sleep_markers_dirty is True
    assert store.state.last_markers_save_time is None
    mock_critical.assert_called_once()


def test_save_current_markers_supports_nonwear_only_save() -> None:
    """Manual save persists nonwear markers even when no sleep markers are present."""
    manager, store, _services, _navigation, main_window = _build_manager()
    nonwear_markers = _make_complete_nonwear_markers()
    store.dispatch(Actions.nonwear_markers_changed(markers=nonwear_markers))

    with (
        patch("sleep_scoring_app.ui.window_state.QMessageBox.warning"),
        patch("sleep_scoring_app.ui.window_state.QMessageBox.information"),
        patch("sleep_scoring_app.ui.window_state.QMessageBox.critical"),
    ):
        manager.save_current_markers()

    main_window._autosave_nonwear_markers_to_db.assert_called_once_with(nonwear_markers)
    assert store.state.nonwear_markers_dirty is False


def test_clear_current_markers_shows_warning_on_partial_db_failure() -> None:
    """Clear action shows warning on partial DB failure but still clears UI to prevent divergence."""
    manager, store, services, _navigation, _main_window = _build_manager()
    sleep_markers, _main_sleep = _make_complete_sleep_markers()
    store.dispatch(Actions.sleep_markers_changed(markers=sleep_markers))

    services.db_manager.delete_sleep_metrics_for_date.return_value = False

    with patch("sleep_scoring_app.ui.window_state.QMessageBox") as mock_qmessagebox:
        confirm_box = MagicMock()
        mock_qmessagebox.return_value = confirm_box
        confirm_box.exec.return_value = mock_qmessagebox.StandardButton.Yes

        manager.clear_current_markers()

        # Warning shown for partial failure
        mock_qmessagebox.warning.assert_called_once()

    # UI is still cleared to prevent DB/UI divergence
    services.db_manager.delete_sleep_metrics_for_date.assert_called_once()
    services.plot_widget.clear_sleep_markers.assert_called_once()
