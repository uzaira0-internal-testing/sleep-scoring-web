"""
Tests for Marker Interaction Handler.

Tests marker click, drag, and selection behavior for both sleep and nonwear markers.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.core.constants import MarkerCategory, MarkerEndpoint, SleepMarkerEndpoint


@pytest.fixture
def mock_plot_widget() -> MagicMock:
    """Create a mock ActivityPlotWidget."""
    widget = MagicMock()

    # Marker category state
    widget.get_active_marker_category.return_value = MarkerCategory.SLEEP

    # Marker click/drag state
    widget._marker_click_in_progress = False
    widget._marker_drag_in_progress = False

    # X data for snapping
    widget.x_data = list(range(0, 86400, 60))  # One day of minute-level timestamps

    # Marker renderer
    mock_renderer = MagicMock()
    mock_renderer.selected_marker_set_index = 1
    mock_renderer.selected_nonwear_marker_index = 0
    mock_renderer.get_selected_marker_period.return_value = MagicMock()
    mock_renderer.daily_sleep_markers = MagicMock()
    mock_renderer.daily_sleep_markers.update_classifications = MagicMock()
    mock_renderer.daily_sleep_markers.check_duration_tie.return_value = False
    mock_renderer.daily_nonwear_markers = MagicMock()
    mock_renderer.daily_nonwear_markers.check_overlap.return_value = False
    widget.marker_renderer = mock_renderer

    # Helper methods
    widget._find_closest_data_index.return_value = 100
    widget.apply_sleep_scoring_rules = MagicMock()
    widget.mark_sleep_markers_dirty = MagicMock()
    widget.mark_nonwear_markers_dirty = MagicMock()
    widget.setFocus = MagicMock()
    widget.marker_limit_exceeded = MagicMock()
    widget.marker_limit_exceeded.emit = MagicMock()

    return widget


@pytest.fixture
def mock_line() -> MagicMock:
    """Create a mock InfiniteLine."""
    line = MagicMock()
    line.getPos.return_value = (3600.0, 0)  # 1 hour in seconds
    line.marker_type = SleepMarkerEndpoint.ONSET

    # Mock period
    mock_period = MagicMock()
    mock_period.onset_timestamp = 3600.0
    mock_period.offset_timestamp = 7200.0
    mock_period.is_complete = True
    mock_period.marker_index = 1
    line.period = mock_period

    return line


@pytest.fixture
def interaction_handler(mock_plot_widget: MagicMock):
    """Create a MarkerInteractionHandler with mocked widget."""
    from sleep_scoring_app.ui.widgets.marker_interaction_handler import (
        MarkerInteractionHandler,
    )

    return MarkerInteractionHandler(mock_plot_widget)


class TestMarkerInteractionHandlerInit:
    """Tests for MarkerInteractionHandler initialization."""

    def test_init_stores_plot_widget(self, mock_plot_widget: MagicMock) -> None:
        """Stores plot widget reference."""
        from sleep_scoring_app.ui.widgets.marker_interaction_handler import (
            MarkerInteractionHandler,
        )

        handler = MarkerInteractionHandler(mock_plot_widget)

        assert handler.plot_widget is mock_plot_widget


class TestSleepMarkerClick:
    """Tests for on_marker_clicked."""

    def test_ignores_click_when_not_in_sleep_mode(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Ignores click when not in SLEEP mode."""
        mock_plot_widget.get_active_marker_category.return_value = MarkerCategory.NONWEAR

        interaction_handler.on_marker_clicked(mock_line)

        mock_plot_widget.marker_renderer.select_marker_set_by_period.assert_not_called()

    def test_sets_click_in_progress_flag(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Sets marker click in progress flag."""
        with patch("sleep_scoring_app.ui.widgets.marker_interaction_handler.QTimer"):
            interaction_handler.on_marker_clicked(mock_line)

        assert mock_plot_widget._marker_click_in_progress is True

    def test_selects_marker_set_by_period(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Selects marker set when line has period."""
        with patch("sleep_scoring_app.ui.widgets.marker_interaction_handler.QTimer"):
            interaction_handler.on_marker_clicked(mock_line)

        mock_plot_widget.marker_renderer.select_marker_set_by_period.assert_called_with(mock_line.period)

    def test_updates_sleep_scoring_rules(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Updates sleep scoring rules after click."""
        mock_selected = MagicMock()
        mock_selected.is_complete = True
        mock_plot_widget.marker_renderer.get_selected_marker_period.return_value = mock_selected

        with patch("sleep_scoring_app.ui.widgets.marker_interaction_handler.QTimer"):
            interaction_handler.on_marker_clicked(mock_line)

        mock_plot_widget.apply_sleep_scoring_rules.assert_called()


class TestSleepMarkerDrag:
    """Tests for on_marker_dragged."""

    def test_ignores_drag_when_not_in_sleep_mode(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Ignores drag when not in SLEEP mode."""
        mock_plot_widget.get_active_marker_category.return_value = MarkerCategory.NONWEAR

        interaction_handler.on_marker_dragged(mock_line)

        assert mock_plot_widget._marker_drag_in_progress is False

    def test_sets_drag_in_progress_flag(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Sets marker drag in progress flag."""
        interaction_handler.on_marker_dragged(mock_line)

        assert mock_plot_widget._marker_drag_in_progress is True

    def test_updates_onset_timestamp_during_drag(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Updates onset timestamp when dragging onset marker."""
        mock_line.marker_type = SleepMarkerEndpoint.ONSET
        mock_plot_widget.x_data = [i * 60 for i in range(1000)]
        mock_plot_widget._find_closest_data_index.return_value = 100

        interaction_handler.on_marker_dragged(mock_line)

        # Should update onset_timestamp to snapped value
        assert mock_line.period.onset_timestamp == 6000  # 100 * 60

    def test_updates_offset_timestamp_during_drag(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Updates offset timestamp when dragging offset marker."""
        mock_line.marker_type = SleepMarkerEndpoint.OFFSET
        mock_plot_widget.x_data = [i * 60 for i in range(1000)]
        mock_plot_widget._find_closest_data_index.return_value = 150

        interaction_handler.on_marker_dragged(mock_line)

        assert mock_line.period.offset_timestamp == 9000  # 150 * 60

    def test_marks_sleep_markers_dirty(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Marks sleep markers dirty during drag."""
        mock_plot_widget.x_data = [i * 60 for i in range(1000)]
        mock_plot_widget._find_closest_data_index.return_value = 100

        interaction_handler.on_marker_dragged(mock_line)

        mock_plot_widget.mark_sleep_markers_dirty.assert_called()

    def test_throttles_updates_when_index_unchanged(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Throttles updates when index hasn't changed."""
        mock_line._last_drag_idx = 100  # Same as what will be returned
        mock_plot_widget._find_closest_data_index.return_value = 100

        interaction_handler.on_marker_dragged(mock_line)

        # Should not update period since index unchanged
        mock_plot_widget.mark_sleep_markers_dirty.assert_not_called()


class TestSleepMarkerDragFinished:
    """Tests for on_marker_drag_finished."""

    def test_clears_drag_in_progress_flag(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Clears drag in progress flag."""
        mock_plot_widget._marker_drag_in_progress = True

        interaction_handler.on_marker_drag_finished(mock_line)

        assert mock_plot_widget._marker_drag_in_progress is False

    def test_reverts_when_not_in_sleep_mode(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Reverts marker position when not in SLEEP mode."""
        mock_plot_widget.get_active_marker_category.return_value = MarkerCategory.NONWEAR

        interaction_handler.on_marker_drag_finished(mock_line)

        mock_line.setPos.assert_called()

    def test_snaps_position_to_nearest_data_epoch(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Snaps position to nearest data epoch (not just minute boundary).

        Snaps to x_data[closest_index] rather than minute boundaries.
        """
        mock_line.getPos.return_value = (3625.0, 0)  # Not on minute boundary

        # Mock _find_closest_data_index to return index 60, which maps to x_data[60] = 3600
        mock_plot_widget._find_closest_data_index.return_value = 60

        interaction_handler.on_marker_drag_finished(mock_line)

        # Should snap to x_data[60] = 3600 (nearest data epoch)
        mock_line.setPos.assert_called_with(3600)

    def test_triggers_full_redraw(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Triggers full marker redraw after drag."""
        interaction_handler.on_marker_drag_finished(mock_line)

        mock_plot_widget.marker_renderer.redraw_markers.assert_called()

    def test_emits_warning_on_duration_tie(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Emits warning when duration tie detected."""
        mock_plot_widget.marker_renderer.daily_sleep_markers.check_duration_tie.return_value = True

        interaction_handler.on_marker_drag_finished(mock_line)

        mock_plot_widget.marker_limit_exceeded.emit.assert_called()


class TestNonwearMarkerClick:
    """Tests for on_nonwear_marker_clicked."""

    def test_ignores_click_when_not_in_nonwear_mode(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Ignores click when not in NONWEAR mode."""
        mock_plot_widget.get_active_marker_category.return_value = MarkerCategory.SLEEP

        interaction_handler.on_nonwear_marker_clicked(mock_line)

        mock_plot_widget.marker_renderer.select_nonwear_marker_by_period.assert_not_called()

    def test_selects_nonwear_marker(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Selects nonwear marker when in NONWEAR mode."""
        mock_plot_widget.get_active_marker_category.return_value = MarkerCategory.NONWEAR

        with patch("sleep_scoring_app.ui.widgets.marker_interaction_handler.QTimer"):
            interaction_handler.on_nonwear_marker_clicked(mock_line)

        mock_plot_widget.marker_renderer.select_nonwear_marker_by_period.assert_called_with(mock_line.period)

    def test_deselects_sleep_markers(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Deselects sleep markers when nonwear marker clicked."""
        mock_plot_widget.get_active_marker_category.return_value = MarkerCategory.NONWEAR

        with patch("sleep_scoring_app.ui.widgets.marker_interaction_handler.QTimer"):
            interaction_handler.on_nonwear_marker_clicked(mock_line)

        # Should set sleep marker selection to 0
        assert mock_plot_widget.marker_renderer.selected_marker_set_index == 0


class TestNonwearMarkerDrag:
    """Tests for on_nonwear_marker_dragged."""

    def test_ignores_drag_when_not_in_nonwear_mode(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Ignores drag when not in NONWEAR mode."""
        mock_plot_widget.get_active_marker_category.return_value = MarkerCategory.SLEEP
        mock_line.marker_type = MarkerEndpoint.START

        interaction_handler.on_nonwear_marker_dragged(mock_line)

        assert mock_plot_widget._marker_drag_in_progress is False

    def test_updates_start_timestamp(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Updates start timestamp when dragging start marker."""
        mock_plot_widget.get_active_marker_category.return_value = MarkerCategory.NONWEAR
        mock_line.marker_type = MarkerEndpoint.START
        mock_line.period.start_timestamp = 3600.0
        mock_line.period.end_timestamp = 7200.0
        mock_line.period.is_complete = True
        mock_plot_widget.x_data = [i * 60 for i in range(1000)]
        mock_plot_widget._find_closest_data_index.return_value = 50

        interaction_handler.on_nonwear_marker_dragged(mock_line)

        assert mock_line.period.start_timestamp == 3000  # 50 * 60

    def test_handles_marker_crossing(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Handles marker crossing (start crosses end)."""
        mock_plot_widget.get_active_marker_category.return_value = MarkerCategory.NONWEAR
        mock_line.marker_type = MarkerEndpoint.START
        mock_line.period.start_timestamp = 3600.0
        mock_line.period.end_timestamp = 7200.0
        mock_line.period.is_complete = True
        mock_plot_widget.x_data = [i * 60 for i in range(1000)]
        # Drag start marker past end (index 200 = 12000, which is past 7200)
        mock_plot_widget._find_closest_data_index.return_value = 200

        interaction_handler.on_nonwear_marker_dragged(mock_line)

        # Markers should swap - start becomes end
        assert mock_line.marker_type == MarkerEndpoint.END


class TestNonwearMarkerDragFinished:
    """Tests for on_nonwear_marker_drag_finished."""

    def test_clears_drag_flag(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Clears drag in progress flag."""
        mock_plot_widget.get_active_marker_category.return_value = MarkerCategory.NONWEAR
        mock_line.marker_type = MarkerEndpoint.START
        mock_line.period.start_timestamp = 3600.0
        mock_line.period.end_timestamp = 7200.0
        mock_plot_widget._marker_drag_in_progress = True

        interaction_handler.on_nonwear_marker_drag_finished(mock_line)

        assert mock_plot_widget._marker_drag_in_progress is False

    def test_reverts_on_overlap(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Reverts position when overlap detected."""
        mock_plot_widget.get_active_marker_category.return_value = MarkerCategory.NONWEAR
        mock_line.marker_type = MarkerEndpoint.START
        mock_line.period.start_timestamp = 3600.0
        mock_line.period.end_timestamp = 7200.0
        mock_line.period.is_complete = True
        mock_plot_widget.marker_renderer.daily_nonwear_markers.check_overlap.return_value = True

        interaction_handler.on_nonwear_marker_drag_finished(mock_line)

        mock_plot_widget.marker_limit_exceeded.emit.assert_called_with("Nonwear periods cannot overlap")

    def test_triggers_redraw(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Triggers nonwear marker redraw."""
        mock_plot_widget.get_active_marker_category.return_value = MarkerCategory.NONWEAR
        mock_line.marker_type = MarkerEndpoint.START
        mock_line.period.start_timestamp = 3600.0
        mock_line.period.end_timestamp = 7200.0

        interaction_handler.on_nonwear_marker_drag_finished(mock_line)

        mock_plot_widget.marker_renderer.redraw_nonwear_markers.assert_called()


class TestHelperMethods:
    """Tests for helper methods."""

    def test_deselect_nonwear_markers(self, interaction_handler, mock_plot_widget: MagicMock) -> None:
        """Deselects all nonwear markers."""
        mock_plot_widget.marker_renderer.selected_nonwear_marker_index = 5

        interaction_handler._deselect_nonwear_markers()

        assert mock_plot_widget.marker_renderer.selected_nonwear_marker_index == 0

    def test_deselect_sleep_markers(self, interaction_handler, mock_plot_widget: MagicMock) -> None:
        """Deselects all sleep markers."""
        mock_plot_widget.marker_renderer.selected_marker_set_index = 3

        interaction_handler._deselect_sleep_markers()

        assert mock_plot_widget.marker_renderer.selected_marker_set_index == 0

    def test_update_sleep_scoring_rules_with_complete_period(self, interaction_handler, mock_plot_widget: MagicMock) -> None:
        """Updates rules when selected period is complete."""
        mock_period = MagicMock()
        mock_period.is_complete = True
        mock_plot_widget.marker_renderer.get_selected_marker_period.return_value = mock_period

        interaction_handler._update_sleep_scoring_rules()

        mock_plot_widget.apply_sleep_scoring_rules.assert_called_with(mock_period)

    def test_update_sleep_scoring_rules_skips_incomplete(self, interaction_handler, mock_plot_widget: MagicMock) -> None:
        """Skips rules update when period is incomplete."""
        mock_period = MagicMock()
        mock_period.is_complete = False
        mock_plot_widget.marker_renderer.get_selected_marker_period.return_value = mock_period

        interaction_handler._update_sleep_scoring_rules()

        mock_plot_widget.apply_sleep_scoring_rules.assert_not_called()

    def test_update_sleep_scoring_rules_skips_no_period(self, interaction_handler, mock_plot_widget: MagicMock) -> None:
        """Skips rules update when no period selected."""
        mock_plot_widget.marker_renderer.get_selected_marker_period.return_value = None

        interaction_handler._update_sleep_scoring_rules()

        mock_plot_widget.apply_sleep_scoring_rules.assert_not_called()


class TestSleepDragFinishedOnsetOffsetCrossing:
    """Regression tests for onset/offset crossing during drag-finished.

    When a user drags onset past offset (or vice versa), the handler must:
    1. Revert to the original timestamps (not line.getPos() + arbitrary offset)
    2. Still dispatch dirty state so tables sync with the reverted position
    """

    def test_onset_crossing_offset_reverts_to_original(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Onset dragged past offset reverts to original onset timestamp."""
        # Setup: onset at 3600, offset at 7200
        mock_line.marker_type = SleepMarkerEndpoint.ONSET
        mock_line.period.onset_timestamp = 3600.0
        mock_line.period.offset_timestamp = 7200.0
        mock_line.period.is_complete = True
        mock_line.getPos.return_value = (8000.0, 0)  # Dragged past offset

        # _find_closest_data_index returns index mapping to 8040 (past offset)
        mock_plot_widget._find_closest_data_index.return_value = 134
        mock_plot_widget.x_data = [i * 60 for i in range(1000)]

        interaction_handler.on_marker_drag_finished(mock_line)

        # Should revert onset to original 3600, not to getPos()[0] + 60
        assert mock_line.period.onset_timestamp == 3600.0
        assert mock_line.period.offset_timestamp == 7200.0

    def test_offset_crossing_onset_reverts_to_original(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Offset dragged before onset reverts to original offset timestamp."""
        mock_line.marker_type = SleepMarkerEndpoint.OFFSET
        mock_line.period.onset_timestamp = 3600.0
        mock_line.period.offset_timestamp = 7200.0
        mock_line.period.is_complete = True
        mock_line.getPos.return_value = (2000.0, 0)  # Dragged before onset

        # _find_closest_data_index returns index mapping to 1980 (before onset)
        mock_plot_widget._find_closest_data_index.return_value = 33
        mock_plot_widget.x_data = [i * 60 for i in range(1000)]

        interaction_handler.on_marker_drag_finished(mock_line)

        assert mock_line.period.onset_timestamp == 3600.0
        assert mock_line.period.offset_timestamp == 7200.0

    def test_crossing_still_dispatches_dirty(self, interaction_handler, mock_plot_widget: MagicMock, mock_line: MagicMock) -> None:
        """Tables sync even when drag is reverted due to crossing."""
        mock_line.marker_type = SleepMarkerEndpoint.ONSET
        mock_line.period.onset_timestamp = 3600.0
        mock_line.period.offset_timestamp = 7200.0
        mock_line.period.is_complete = True
        mock_line.getPos.return_value = (8000.0, 0)

        mock_plot_widget._find_closest_data_index.return_value = 134
        mock_plot_widget.x_data = [i * 60 for i in range(1000)]

        interaction_handler.on_marker_drag_finished(mock_line)

        # Must dispatch dirty even on revert, so tables update
        mock_plot_widget.mark_sleep_markers_dirty.assert_called()


class TestBoundaryClampingRegression:
    """Regression tests for _find_closest_data_index boundary clamping.

    When marker is dragged outside the data range (e.g. into the empty area
    of a noon-to-noon 24h view), the method should clamp to the nearest
    boundary data point instead of returning None.
    """

    def test_clamps_to_first_data_point_when_before_range(self) -> None:
        """Target before first data point returns index 0."""
        import numpy as np

        widget = MagicMock()
        widget.x_data = np.array([1000.0, 1060.0, 1120.0, 1180.0])

        from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

        result = ActivityPlotWidget._find_closest_data_index(widget, 500.0)

        assert result == 0

    def test_clamps_to_last_data_point_when_after_range(self) -> None:
        """Target after last data point returns last index."""
        import numpy as np

        widget = MagicMock()
        widget.x_data = np.array([1000.0, 1060.0, 1120.0, 1180.0])

        from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

        result = ActivityPlotWidget._find_closest_data_index(widget, 9999.0)

        assert result == 3

    def test_finds_exact_match_within_range(self) -> None:
        """Target exactly on a data point returns that index."""
        import numpy as np

        widget = MagicMock()
        widget.x_data = np.array([1000.0, 1060.0, 1120.0, 1180.0])

        from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

        result = ActivityPlotWidget._find_closest_data_index(widget, 1120.0)

        assert result == 2

    def test_finds_nearest_within_range(self) -> None:
        """Target between data points returns nearest index."""
        import numpy as np

        widget = MagicMock()
        widget.x_data = np.array([1000.0, 1060.0, 1120.0, 1180.0])

        from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

        result = ActivityPlotWidget._find_closest_data_index(widget, 1085.0)

        # 1085 is closer to 1060 (diff=25) than 1120 (diff=35)
        assert result == 1

    def test_returns_none_when_no_data(self) -> None:
        """Returns None when x_data is empty."""
        import numpy as np

        widget = MagicMock()
        widget.x_data = np.array([])

        from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

        result = ActivityPlotWidget._find_closest_data_index(widget, 1000.0)

        assert result is None


class TestClickSnappingBehavior:
    """Regression tests for click-to-place snapping to actual data epochs.

    Plot clicks in empty view-edge space should snap to the nearest actual
    data point, not place markers at timestamps with no data.
    """

    def test_click_in_data_range_emits_snapped_timestamp(self) -> None:
        """Click within data emits snapped (not raw) timestamp."""
        import numpy as np

        widget = MagicMock()
        widget.x_data = np.array([1000.0, 1060.0, 1120.0, 1180.0])
        widget.data_start_time = 900.0  # View starts before data
        widget.data_end_time = 1300.0  # View ends after data

        from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

        # Simulate _find_closest_data_index using the real method
        idx = ActivityPlotWidget._find_closest_data_index(widget, 1085.0)
        assert idx is not None
        snapped = float(widget.x_data[idx])
        # 1085 is closer to 1060 (idx 1), not raw 1085
        assert snapped == 1060.0

    def test_click_past_data_end_snaps_to_last_point(self) -> None:
        """Click in empty view space past data end snaps to last data point."""
        import numpy as np

        widget = MagicMock()
        widget.x_data = np.array([1000.0, 1060.0, 1120.0, 1180.0])

        from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

        idx = ActivityPlotWidget._find_closest_data_index(widget, 1250.0)
        assert idx == 3
        assert float(widget.x_data[idx]) == 1180.0

    def test_click_before_data_start_snaps_to_first_point(self) -> None:
        """Click in empty view space before data start snaps to first data point."""
        import numpy as np

        widget = MagicMock()
        widget.x_data = np.array([1000.0, 1060.0, 1120.0, 1180.0])

        from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

        idx = ActivityPlotWidget._find_closest_data_index(widget, 800.0)
        assert idx == 0
        assert float(widget.x_data[idx]) == 1000.0


class TestActualDataBoundsProperty:
    """Tests for the actual_data_bounds property on ActivityPlotWidget."""

    def test_returns_tuple_when_data_loaded(self) -> None:
        """Returns (first, last) timestamps when x_data has values."""
        import numpy as np

        widget = MagicMock()
        widget.x_data = np.array([1000.0, 1060.0, 1120.0, 1180.0])

        from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

        result = ActivityPlotWidget.actual_data_bounds.fget(widget)

        assert result == (1000.0, 1180.0)

    def test_returns_none_when_no_data(self) -> None:
        """Returns None when x_data is empty."""
        import numpy as np

        widget = MagicMock()
        widget.x_data = np.array([])

        from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

        result = ActivityPlotWidget.actual_data_bounds.fget(widget)

        assert result is None

    def test_returns_none_when_x_data_is_none(self) -> None:
        """Returns None when x_data is None."""
        widget = MagicMock()
        widget.x_data = None

        from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

        result = ActivityPlotWidget.actual_data_bounds.fget(widget)

        assert result is None
