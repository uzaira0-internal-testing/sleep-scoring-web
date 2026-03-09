"""Tests for SeamlessSourceSwitcher — ensures activity source switching
dispatches preferred_display_column_changed and handles fallback.

Uses a real UIStore; mocks services and plot widget.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.core.constants import ActivityDataPreference
from sleep_scoring_app.ui.coordinators.seamless_source_switcher import (
    SeamlessSourceSwitcher,
)
from sleep_scoring_app.ui.store import Actions, UIStore


@pytest.fixture
def store() -> UIStore:
    """Real UIStore seeded with file, dates, and display column."""
    s = UIStore()
    s.dispatch(Actions.file_selected(filename="TEST-001.csv"))
    s.dispatch(Actions.dates_loaded(dates=["2024-06-15", "2024-06-16"]))
    s.dispatch(Actions.date_selected(date_index=0))
    return s


@pytest.fixture
def mock_deps(store: UIStore) -> dict:
    """Mock dependencies for SeamlessSourceSwitcher."""
    data_service = MagicMock()
    data_service.load_raw_activity_data.return_value = ([1.0, 2.0], [100.0, 200.0])

    config_manager = MagicMock()
    config_manager.config = MagicMock()
    config_manager.config.choi_axis = ActivityDataPreference.AXIS_Y

    plot_widget = MagicMock()
    plot_widget.vb = MagicMock()
    plot_widget.vb.viewRange.return_value = [[0.0, 100.0], [0.0, 500.0]]

    return {
        "store": store,
        "data_service": data_service,
        "config_manager": config_manager,
        "plot_widget": plot_widget,
        "set_pref_callback": MagicMock(),
        "auto_save_callback": MagicMock(),
        "load_markers_callback": MagicMock(),
        "get_tab_dropdown_fn": MagicMock(),
    }


def _make_switcher(deps: dict) -> SeamlessSourceSwitcher:
    return SeamlessSourceSwitcher(
        store=deps["store"],
        data_service=deps["data_service"],
        config_manager=deps["config_manager"],
        plot_widget=deps["plot_widget"],
        available_dates=list(deps["store"].state.available_dates),
        set_pref_callback=deps["set_pref_callback"],
        auto_save_callback=deps["auto_save_callback"],
        load_markers_callback=deps["load_markers_callback"],
        get_tab_dropdown_fn=deps["get_tab_dropdown_fn"],
    )


class TestSeamlessSourceSwitcherFallback:
    """Fallback path dispatches preferred_display_column_changed."""

    def test_fallback_dispatches_column_change(self, mock_deps: dict) -> None:
        """_fallback_to_full_reload dispatches preferred_display_column_changed."""
        store = mock_deps["store"]
        switcher = _make_switcher(mock_deps)

        switcher._fallback_to_full_reload(ActivityDataPreference.VECTOR_MAGNITUDE)

        assert store.state.preferred_display_column == ActivityDataPreference.VECTOR_MAGNITUDE

    def test_fallback_calls_auto_save(self, mock_deps: dict) -> None:
        """_fallback_to_full_reload calls auto_save_callback before reloading."""
        switcher = _make_switcher(mock_deps)

        switcher._fallback_to_full_reload(ActivityDataPreference.AXIS_Y)

        mock_deps["auto_save_callback"].assert_called_once()

    def test_fallback_calls_load_markers(self, mock_deps: dict) -> None:
        """_fallback_to_full_reload calls load_markers_callback after dispatch."""
        switcher = _make_switcher(mock_deps)

        switcher._fallback_to_full_reload(ActivityDataPreference.AXIS_Y)

        mock_deps["load_markers_callback"].assert_called_once()


class TestSeamlessSourceSwitcherSwitch:
    """Source switching with dropdown interaction."""

    def test_negative_index_is_noop(self, mock_deps: dict) -> None:
        """Negative index does nothing."""
        switcher = _make_switcher(mock_deps)

        switcher.switch_activity_source(-1)

        mock_deps["set_pref_callback"].assert_not_called()

    def test_switch_calls_set_pref_callback(self, mock_deps: dict) -> None:
        """Successful switch calls set_pref_callback with selected column."""
        dropdown = MagicMock()
        dropdown.itemData.return_value = ActivityDataPreference.VECTOR_MAGNITUDE
        mock_deps["get_tab_dropdown_fn"].return_value = dropdown

        switcher = _make_switcher(mock_deps)

        with (
            patch.object(switcher, "_load_activity_data_seamlessly", return_value=True),
            patch("sleep_scoring_app.ui.coordinators.seamless_source_switcher.QApplication"),
        ):
            switcher.switch_activity_source(0)

        mock_deps["set_pref_callback"].assert_called_once_with(
            ActivityDataPreference.VECTOR_MAGNITUDE,
            ActivityDataPreference.AXIS_Y,
        )


class TestSeamlessSourceSwitcherSerialization:
    """Period serialization/deserialization round-trips."""

    def test_serialize_none_returns_none(self, mock_deps: dict) -> None:
        switcher = _make_switcher(mock_deps)
        assert switcher._serialize_sleep_period(None) is None

    def test_deserialize_none_returns_none(self, mock_deps: dict) -> None:
        switcher = _make_switcher(mock_deps)
        assert switcher._deserialize_sleep_period(None) is None

    def test_round_trip_preserves_timestamps(self, mock_deps: dict) -> None:
        """Serialize then deserialize preserves onset/offset timestamps."""
        from sleep_scoring_app.core.dataclasses import SleepPeriod

        switcher = _make_switcher(mock_deps)
        period = SleepPeriod(onset_timestamp=100.0, offset_timestamp=200.0, marker_index=1)

        serialized = switcher._serialize_sleep_period(period)
        deserialized = switcher._deserialize_sleep_period(serialized)

        assert deserialized is not None
        assert deserialized.onset_timestamp == 100.0
        assert deserialized.offset_timestamp == 200.0
        assert deserialized.marker_index == 1
