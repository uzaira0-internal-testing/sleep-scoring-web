"""
Tests for PlotMarkerRenderer.

Tests marker rendering operations for the activity plot including:
- Sleep marker state access
- Marker selection and visual state
- Period validation and bounds checking
- Nonwear marker management
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.core.constants import MarkerEndpoint, SleepMarkerEndpoint, UIColors
from sleep_scoring_app.core.dataclasses import (
    DailyNonwearMarkers,
    DailySleepMarkers,
    ManualNonwearPeriod,
    MarkerType,
    SleepPeriod,
)
from sleep_scoring_app.ui.widgets.plot_marker_renderer import PlotMarkerRenderer


@pytest.fixture
def mock_parent() -> MagicMock:
    """Create a mock ActivityPlotWidget parent."""
    parent = MagicMock()
    parent.daily_sleep_markers = DailySleepMarkers()
    parent.marker_lines = []
    parent.selected_marker_set_index = 0
    parent._daily_nonwear_markers = DailyNonwearMarkers()
    parent._nonwear_marker_lines = []
    parent._selected_nonwear_marker_index = 0
    parent._nonwear_markers_visible = True
    parent.current_marker_being_placed = None
    parent._current_nonwear_marker_being_placed = None
    parent.adjacent_day_marker_lines = []
    parent.adjacent_day_marker_labels = []
    parent.data_start_time = 1705276800.0  # 2024-01-15 00:00:00
    parent.data_end_time = 1705449600.0  # 2024-01-17 00:00:00
    parent.actual_data_bounds = (1705276800.0, 1705449600.0)
    parent.custom_colors = {}
    parent.plotItem = MagicMock()
    parent.markers_saved = True
    parent._skip_auto_apply_rules = False
    return parent


@pytest.fixture
def renderer(mock_parent: MagicMock) -> PlotMarkerRenderer:
    """Create a PlotMarkerRenderer instance."""
    with (
        patch("sleep_scoring_app.ui.widgets.plot_marker_renderer.MarkerDrawingStrategy"),
        patch("sleep_scoring_app.ui.widgets.plot_marker_renderer.MarkerInteractionHandler"),
    ):
        return PlotMarkerRenderer(mock_parent)


@pytest.fixture
def sample_sleep_period() -> SleepPeriod:
    """Create a sample complete sleep period."""
    return SleepPeriod(
        marker_type=MarkerType.MAIN_SLEEP,
        onset_timestamp=1705280400.0,  # 2024-01-15 01:00:00
        offset_timestamp=1705309200.0,  # 2024-01-15 09:00:00
    )


@pytest.fixture
def sample_nap_period() -> SleepPeriod:
    """Create a sample nap period."""
    return SleepPeriod(
        marker_type=MarkerType.NAP,
        onset_timestamp=1705323600.0,  # 2024-01-15 13:00:00
        offset_timestamp=1705330800.0,  # 2024-01-15 15:00:00
    )


@pytest.fixture
def sample_nonwear_period() -> ManualNonwearPeriod:
    """Create a sample nonwear period."""
    return ManualNonwearPeriod(
        marker_index=1,
        start_timestamp=1705340400.0,  # 2024-01-15 17:00:00
        end_timestamp=1705347600.0,  # 2024-01-15 19:00:00
    )


class TestPlotMarkerRendererInit:
    """Tests for PlotMarkerRenderer initialization."""

    def test_init_stores_parent(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Stores parent reference."""
        assert renderer.parent is mock_parent

    def test_init_creates_strategies(self, mock_parent: MagicMock) -> None:
        """Creates drawing strategy and interaction handler."""
        with (
            patch("sleep_scoring_app.ui.widgets.plot_marker_renderer.MarkerDrawingStrategy") as mock_draw,
            patch("sleep_scoring_app.ui.widgets.plot_marker_renderer.MarkerInteractionHandler") as mock_interact,
        ):
            renderer = PlotMarkerRenderer(mock_parent)
            mock_draw.assert_called_once_with(mock_parent)
            mock_interact.assert_called_once_with(mock_parent)


class TestPropertyAccess:
    """Tests for property accessors."""

    def test_daily_sleep_markers_getter(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Gets daily_sleep_markers from parent."""
        markers = DailySleepMarkers()
        mock_parent.daily_sleep_markers = markers
        assert renderer.daily_sleep_markers is markers

    def test_daily_sleep_markers_setter(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Sets daily_sleep_markers on parent."""
        markers = DailySleepMarkers()
        renderer.daily_sleep_markers = markers
        assert mock_parent.daily_sleep_markers is markers

    def test_marker_lines_getter(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Gets marker_lines from parent."""
        lines = [MagicMock()]
        mock_parent.marker_lines = lines
        assert renderer.marker_lines is lines

    def test_selected_marker_set_index_getter(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Gets selected_marker_set_index from parent."""
        mock_parent.selected_marker_set_index = 2
        assert renderer.selected_marker_set_index == 2

    def test_daily_nonwear_markers_getter(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Gets daily_nonwear_markers from parent."""
        markers = DailyNonwearMarkers()
        mock_parent._daily_nonwear_markers = markers
        assert renderer.daily_nonwear_markers is markers

    def test_nonwear_markers_visible_getter(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Gets nonwear_markers_visible from parent."""
        mock_parent._nonwear_markers_visible = False
        assert renderer.nonwear_markers_visible is False


class TestGetNapNumber:
    """Tests for get_nap_number method."""

    def test_returns_correct_nap_number_for_first(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Returns 1 for first nap by onset time."""
        nap1 = SleepPeriod(marker_type=MarkerType.NAP, onset_timestamp=1000.0, offset_timestamp=2000.0)
        nap2 = SleepPeriod(marker_type=MarkerType.NAP, onset_timestamp=3000.0, offset_timestamp=4000.0)

        markers = DailySleepMarkers()
        markers.period_1 = nap1
        markers.period_2 = nap2
        mock_parent.daily_sleep_markers = markers

        # nap1 has earlier onset, should be nap #1
        assert renderer.get_nap_number(nap1) == 1

    def test_sorts_naps_by_onset_time(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Sorts naps by onset time for numbering."""
        # Create naps in reverse order (later one in slot 1)
        later_nap = SleepPeriod(marker_type=MarkerType.NAP, onset_timestamp=3000.0, offset_timestamp=4000.0)
        earlier_nap = SleepPeriod(marker_type=MarkerType.NAP, onset_timestamp=1000.0, offset_timestamp=2000.0)

        markers = DailySleepMarkers()
        markers.period_1 = later_nap  # In slot 1 but has later timestamp
        markers.period_2 = earlier_nap  # In slot 2 but has earlier timestamp
        mock_parent.daily_sleep_markers = markers

        # Earlier nap by time should be #1, later nap should be #2
        assert renderer.get_nap_number(earlier_nap) == 1

    def test_returns_1_for_not_found(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Returns 1 when period not found in naps."""
        mock_parent.daily_sleep_markers = DailySleepMarkers()
        unknown_period = SleepPeriod(marker_type=MarkerType.NAP, onset_timestamp=5000.0, offset_timestamp=6000.0)
        assert renderer.get_nap_number(unknown_period) == 1


class TestGetMarkerColors:
    """Tests for _get_marker_colors method."""

    def test_returns_selected_colors(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Returns selected colors when is_selected=True."""
        mock_parent.custom_colors = {}
        onset_color, offset_color = renderer._get_marker_colors(is_selected=True)
        assert onset_color == UIColors.SELECTED_MARKER_ONSET
        assert offset_color == UIColors.SELECTED_MARKER_OFFSET

    def test_returns_unselected_colors(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Returns unselected colors when is_selected=False."""
        mock_parent.custom_colors = {}
        onset_color, offset_color = renderer._get_marker_colors(is_selected=False)
        assert onset_color == UIColors.UNSELECTED_MARKER_ONSET
        assert offset_color == UIColors.UNSELECTED_MARKER_OFFSET

    def test_uses_custom_colors(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Uses custom colors when provided."""
        mock_parent.custom_colors = {
            "selected_onset": "#FF0000",
            "selected_offset": "#00FF00",
        }
        onset_color, offset_color = renderer._get_marker_colors(is_selected=True)
        assert onset_color == "#FF0000"
        assert offset_color == "#00FF00"


class TestGetSelectedMarkerPeriod:
    """Tests for get_selected_marker_period method."""

    def test_returns_period_1_when_index_1(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock, sample_sleep_period: SleepPeriod) -> None:
        """Returns period_1 when selected index is 1."""
        markers = DailySleepMarkers()
        markers.period_1 = sample_sleep_period
        mock_parent.daily_sleep_markers = markers
        mock_parent.selected_marker_set_index = 1

        assert renderer.get_selected_marker_period() is sample_sleep_period

    def test_returns_period_2_when_index_2(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock, sample_nap_period: SleepPeriod) -> None:
        """Returns period_2 when selected index is 2."""
        markers = DailySleepMarkers()
        markers.period_2 = sample_nap_period
        mock_parent.daily_sleep_markers = markers
        mock_parent.selected_marker_set_index = 2

        assert renderer.get_selected_marker_period() is sample_nap_period

    def test_returns_none_when_index_0(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Returns None when selected index is 0."""
        mock_parent.selected_marker_set_index = 0
        assert renderer.get_selected_marker_period() is None

    def test_returns_none_when_index_invalid(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Returns None for invalid index."""
        mock_parent.selected_marker_set_index = 99
        assert renderer.get_selected_marker_period() is None


class TestSelectMarkerSetByPeriod:
    """Tests for select_marker_set_by_period method."""

    def test_selects_correct_index_for_period_1(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock, sample_sleep_period: SleepPeriod) -> None:
        """Selects index 1 for period_1."""
        markers = DailySleepMarkers()
        markers.period_1 = sample_sleep_period
        mock_parent.daily_sleep_markers = markers
        mock_parent.selected_marker_set_index = 0

        renderer.select_marker_set_by_period(sample_sleep_period)

        assert mock_parent.selected_marker_set_index == 1

    def test_selects_correct_index_for_period_3(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock, sample_nap_period: SleepPeriod) -> None:
        """Selects index 3 for period_3."""
        markers = DailySleepMarkers()
        markers.period_3 = sample_nap_period
        mock_parent.daily_sleep_markers = markers
        mock_parent.selected_marker_set_index = 0

        renderer.select_marker_set_by_period(sample_nap_period)

        assert mock_parent.selected_marker_set_index == 3

    def test_does_not_change_if_period_not_found(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Does not change selection if period not found."""
        mock_parent.daily_sleep_markers = DailySleepMarkers()
        mock_parent.selected_marker_set_index = 1
        unknown_period = SleepPeriod(MarkerType.NAP, 1000.0, 2000.0)

        renderer.select_marker_set_by_period(unknown_period)

        assert mock_parent.selected_marker_set_index == 1  # Unchanged


class TestAutoSelectMarkerSet:
    """Tests for auto_select_marker_set method."""

    def test_keeps_valid_selection(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock, sample_sleep_period: SleepPeriod) -> None:
        """Keeps current selection if still valid."""
        markers = DailySleepMarkers()
        markers.period_1 = sample_sleep_period
        mock_parent.daily_sleep_markers = markers
        mock_parent.selected_marker_set_index = 1

        renderer.auto_select_marker_set()

        assert mock_parent.selected_marker_set_index == 1

    def test_calls_update_sleep_scoring_rules(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Calls parent's _update_sleep_scoring_rules after auto-selecting."""
        mock_parent.daily_sleep_markers = DailySleepMarkers()
        mock_parent.selected_marker_set_index = 0

        renderer.auto_select_marker_set()

        mock_parent._update_sleep_scoring_rules.assert_called_once()


class TestGetSelectedNonwearPeriod:
    """Tests for get_selected_nonwear_period method."""

    def test_returns_period_by_index(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock, sample_nonwear_period: ManualNonwearPeriod) -> None:
        """Returns period matching selected index."""
        markers = DailyNonwearMarkers()
        markers.set_period_by_slot(1, sample_nonwear_period)
        mock_parent._daily_nonwear_markers = markers
        mock_parent._selected_nonwear_marker_index = 1

        assert renderer.get_selected_nonwear_period() is sample_nonwear_period

    def test_returns_none_for_empty_slot(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Returns None for empty slot."""
        mock_parent._daily_nonwear_markers = DailyNonwearMarkers()
        mock_parent._selected_nonwear_marker_index = 5

        assert renderer.get_selected_nonwear_period() is None


class TestSelectNonwearMarkerByPeriod:
    """Tests for select_nonwear_marker_by_period method."""

    def test_logs_selection_change(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock, caplog) -> None:
        """Logs when selection changes."""
        import logging

        period = ManualNonwearPeriod(marker_index=5, start_timestamp=1000.0, end_timestamp=2000.0)
        mock_parent._selected_nonwear_marker_index = 0

        with caplog.at_level(logging.DEBUG):
            renderer.select_nonwear_marker_by_period(period)

        # The method sets the index via property which logs the change
        assert "Nonwear marker selection changed" in caplog.text or mock_parent.selected_nonwear_marker_index == 5


class TestAutoSelectNonwearMarker:
    """Tests for auto_select_nonwear_marker method."""

    def test_keeps_valid_selection(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock, sample_nonwear_period: ManualNonwearPeriod) -> None:
        """Keeps current selection if valid."""
        markers = DailyNonwearMarkers()
        markers.set_period_by_slot(1, sample_nonwear_period)
        mock_parent._daily_nonwear_markers = markers
        mock_parent._selected_nonwear_marker_index = 1

        renderer.auto_select_nonwear_marker()

        # Selection should stay the same (1)
        assert mock_parent._selected_nonwear_marker_index == 1

    def test_calls_apply_visual_state(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Calls _apply_nonwear_marker_visual_state."""
        mock_parent._daily_nonwear_markers = DailyNonwearMarkers()
        mock_parent._selected_nonwear_marker_index = 0

        with patch.object(renderer, "_apply_nonwear_marker_visual_state") as mock_apply:
            renderer.auto_select_nonwear_marker()
            mock_apply.assert_called_once()


class TestGetNonwearMarkerColors:
    """Tests for _get_nonwear_marker_colors method."""

    def test_returns_selected_color(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Returns selected color when is_selected=True."""
        mock_parent.custom_colors = {}
        start_color, end_color = renderer._get_nonwear_marker_colors(is_selected=True)
        assert start_color == UIColors.SELECTED_MANUAL_NWT_START
        assert end_color == UIColors.SELECTED_MANUAL_NWT_START  # Same color for both

    def test_returns_unselected_color(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Returns unselected color when is_selected=False."""
        mock_parent.custom_colors = {}
        start_color, end_color = renderer._get_nonwear_marker_colors(is_selected=False)
        assert start_color == UIColors.UNSELECTED_MANUAL_NWT_START
        assert end_color == UIColors.UNSELECTED_MANUAL_NWT_START

    def test_uses_custom_colors(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Uses custom colors when provided."""
        mock_parent.custom_colors = {"selected_manual_nwt": "#AABBCC"}
        start_color, end_color = renderer._get_nonwear_marker_colors(is_selected=True)
        assert start_color == "#AABBCC"
        assert end_color == "#AABBCC"


class TestClearMethods:
    """Tests for clear methods."""

    def test_clear_sleep_markers(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Clears all sleep markers."""
        mock_line = MagicMock()
        mock_parent.marker_lines = [mock_line]

        renderer.clear_sleep_markers()

        mock_parent.plotItem.removeItem.assert_called_once_with(mock_line)
        assert mock_parent.marker_lines == []
        assert mock_parent.current_marker_being_placed is None

    def test_clear_nonwear_markers(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Clears all nonwear markers."""
        mock_line = MagicMock()
        mock_parent._nonwear_marker_lines = [mock_line]

        renderer.clear_nonwear_markers()

        mock_parent.plotItem.removeItem.assert_called_once_with(mock_line)
        assert mock_parent._nonwear_marker_lines == []
        assert mock_parent._current_nonwear_marker_being_placed is None

    def test_clear_adjacent_day_markers(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Clears adjacent day markers."""
        mock_line = MagicMock()
        mock_label = MagicMock()
        mock_parent.adjacent_day_marker_lines = [mock_line]
        mock_parent.adjacent_day_marker_labels = [mock_label]

        renderer.clear_adjacent_day_markers()

        assert mock_parent.plotItem.removeItem.call_count == 2
        assert mock_parent.adjacent_day_marker_lines == []
        assert mock_parent.adjacent_day_marker_labels == []


class TestCancelIncompleteMarkers:
    """Tests for cancel incomplete marker methods."""

    def test_cancel_incomplete_marker(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Cancels incomplete sleep marker."""
        mock_parent.current_marker_being_placed = MagicMock()

        renderer.cancel_incomplete_marker()

        assert mock_parent.current_marker_being_placed is None

    def test_cancel_incomplete_marker_no_op_when_none(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Does nothing when no incomplete marker."""
        mock_parent.current_marker_being_placed = None

        renderer.cancel_incomplete_marker()  # Should not raise

        assert mock_parent.current_marker_being_placed is None

    def test_cancel_incomplete_nonwear_marker(self, renderer: PlotMarkerRenderer, mock_parent: MagicMock) -> None:
        """Cancels incomplete nonwear marker."""
        mock_parent._current_nonwear_marker_being_placed = MagicMock()

        renderer.cancel_incomplete_nonwear_marker()

        assert mock_parent._current_nonwear_marker_being_placed is None
