"""
Tests for Plot Algorithm Manager.

Tests algorithm execution, caching, sleep period detection, and cache management.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd
import pytest

from sleep_scoring_app.core.constants import ActivityDataPreference, NonwearAlgorithm


@pytest.fixture
def mock_parent() -> MagicMock:
    """Create a mock ActivityPlotWidget parent."""
    parent = MagicMock()

    # Basic data properties
    parent.timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(100)]
    parent.x_data = list(range(100))
    parent.activity_data = [50.0 + (i % 20) for i in range(100)]
    parent.sadeh_results = [1] * 100
    parent.data_max_y = 500.0
    parent.current_view_hours = 24

    # 48hr data
    parent.main_48h_timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(200)]
    parent.main_48h_activity = [50.0 + (i % 20) for i in range(200)]
    parent.main_48h_sadeh_results = [1] * 200
    parent.main_48h_axis_y_data = [100.0] * 200
    parent.main_48h_axis_y_timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(200)]
    parent.main_48h_sadeh_timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(200)]

    # Config and factories
    parent.get_algorithm_config.return_value = MagicMock()
    parent.get_default_sleep_algorithm_id.return_value = "sadeh_1994_actilife"
    parent.get_default_sleep_period_detector_id.return_value = "consecutive_onset3s_offset5s"
    parent.get_choi_activity_column.return_value = ActivityDataPreference.VECTOR_MAGNITUDE

    # Factory methods
    mock_algorithm = MagicMock()
    mock_algorithm.name = "Sadeh (1994)"
    mock_algorithm.identifier = "sadeh_1994_actilife"
    mock_algorithm.score.return_value = pd.DataFrame({"Sleep Score": [1] * 200})
    parent.create_sleep_algorithm.return_value = mock_algorithm

    mock_detector = MagicMock()
    mock_detector.name = "Consecutive 3S/5S"
    mock_detector.identifier = "consecutive_onset3s_offset5s"
    mock_detector.apply_rules.return_value = (10, 90)
    mock_detector.get_marker_labels.return_value = ("Onset Label", "Offset Label")
    parent.create_sleep_period_detector.return_value = mock_detector

    mock_nonwear = MagicMock()
    mock_nonwear.detect.return_value = []
    parent.create_nonwear_algorithm.return_value = mock_nonwear

    # Plot item
    parent.plotItem = MagicMock()
    parent.plotItem.addItem = MagicMock()
    parent.plotItem.removeItem = MagicMock()

    # Sleep rule markers
    parent.sleep_rule_markers = []

    # Selected marker
    mock_period = MagicMock()
    mock_period.is_complete = True
    mock_period.onset_timestamp = datetime(2024, 1, 1, 22, 0).timestamp()
    mock_period.offset_timestamp = datetime(2024, 1, 2, 7, 0).timestamp()
    parent.get_selected_marker_period.return_value = mock_period

    # Axis Y data loader
    parent._get_axis_y_data_for_sadeh.return_value = [100.0] * 200

    # Arrow colors
    parent.custom_arrow_colors = {"onset": "#0066CC", "offset": "#FFA500"}

    return parent


@pytest.fixture
def algorithm_manager(mock_parent: MagicMock):
    """Create a PlotAlgorithmManager with mocked parent."""
    from sleep_scoring_app.ui.widgets.plot_algorithm_manager import PlotAlgorithmManager

    return PlotAlgorithmManager(mock_parent)


class TestPlotAlgorithmManagerInit:
    """Tests for PlotAlgorithmManager initialization."""

    def test_init_stores_parent_reference(self, mock_parent: MagicMock) -> None:
        """Stores parent reference on init."""
        from sleep_scoring_app.ui.widgets.plot_algorithm_manager import PlotAlgorithmManager

        manager = PlotAlgorithmManager(mock_parent)

        assert manager.parent is mock_parent

    def test_init_creates_empty_caches(self, mock_parent: MagicMock) -> None:
        """Creates empty caches on init."""
        from sleep_scoring_app.ui.widgets.plot_algorithm_manager import PlotAlgorithmManager

        manager = PlotAlgorithmManager(mock_parent)

        assert manager._algorithm_cache == {}
        assert manager._sleep_pattern_cache == {}

    def test_init_no_cached_algorithm(self, mock_parent: MagicMock) -> None:
        """No cached algorithm on init."""
        from sleep_scoring_app.ui.widgets.plot_algorithm_manager import PlotAlgorithmManager

        manager = PlotAlgorithmManager(mock_parent)

        assert manager._sleep_scoring_algorithm is None
        assert manager._sleep_period_detector is None


class TestPlotAlgorithmManagerProperties:
    """Tests for property accessors."""

    def test_timestamps_delegates_to_parent(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """timestamps property delegates to parent."""
        result = algorithm_manager.timestamps

        assert result == mock_parent.timestamps

    def test_x_data_delegates_to_parent(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """x_data property delegates to parent."""
        result = algorithm_manager.x_data

        assert result == mock_parent.x_data

    def test_activity_data_delegates_to_parent(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """activity_data property delegates to parent."""
        result = algorithm_manager.activity_data

        assert result == mock_parent.activity_data

    def test_sadeh_results_delegates_to_parent(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """sadeh_results property delegates to parent."""
        result = algorithm_manager.sadeh_results

        assert result == mock_parent.sadeh_results

    def test_sadeh_results_setter(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Can set sadeh_results on parent."""
        new_results = [0, 1, 0, 1]
        algorithm_manager.sadeh_results = new_results

        assert mock_parent.sadeh_results == new_results

    def test_data_max_y_delegates_to_parent(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """data_max_y property delegates to parent."""
        result = algorithm_manager.data_max_y

        assert result == mock_parent.data_max_y

    def test_plotItem_delegates_to_parent(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """plotItem property delegates to parent."""
        result = algorithm_manager.plotItem

        assert result == mock_parent.plotItem


class TestSleepScoringAlgorithmManagement:
    """Tests for sleep scoring algorithm getter/setter."""

    def test_get_sleep_scoring_algorithm_creates_on_first_call(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Creates algorithm on first call."""
        result = algorithm_manager.get_sleep_scoring_algorithm()

        mock_parent.create_sleep_algorithm.assert_called_once()
        assert result is not None

    def test_get_sleep_scoring_algorithm_caches_result(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Caches algorithm after first creation."""
        result1 = algorithm_manager.get_sleep_scoring_algorithm()
        result2 = algorithm_manager.get_sleep_scoring_algorithm()

        # Factory should only be called once
        assert mock_parent.create_sleep_algorithm.call_count == 1
        assert result1 is result2

    def test_set_sleep_scoring_algorithm(self, algorithm_manager) -> None:
        """Can set sleep scoring algorithm."""
        mock_algorithm = MagicMock()
        mock_algorithm.name = "Custom Algorithm"

        algorithm_manager.set_sleep_scoring_algorithm(mock_algorithm)

        assert algorithm_manager._sleep_scoring_algorithm is mock_algorithm

    def test_set_sleep_scoring_algorithm_clears_caches(self, algorithm_manager) -> None:
        """Setting algorithm clears caches."""
        # Add some cache entries
        algorithm_manager._algorithm_cache["test"] = {"data": [1, 2, 3]}
        algorithm_manager._sleep_pattern_cache[("key",)] = (1, 2)

        mock_algorithm = MagicMock()
        algorithm_manager.set_sleep_scoring_algorithm(mock_algorithm)

        assert algorithm_manager._algorithm_cache == {}
        assert algorithm_manager._sleep_pattern_cache == {}


class TestSleepPeriodDetectorManagement:
    """Tests for sleep period detector getter/setter."""

    def test_get_sleep_period_detector_creates_on_first_call(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Creates detector on first call."""
        result = algorithm_manager.get_sleep_period_detector()

        mock_parent.create_sleep_period_detector.assert_called_once()
        assert result is not None

    def test_get_sleep_period_detector_caches_result(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Caches detector after first creation."""
        result1 = algorithm_manager.get_sleep_period_detector()
        result2 = algorithm_manager.get_sleep_period_detector()

        # Factory should only be called once
        assert mock_parent.create_sleep_period_detector.call_count == 1
        assert result1 is result2

    def test_set_sleep_period_detector(self, algorithm_manager) -> None:
        """Can set sleep period detector."""
        mock_detector = MagicMock()
        mock_detector.name = "Custom Detector"

        algorithm_manager.set_sleep_period_detector(mock_detector)

        assert algorithm_manager._sleep_period_detector is mock_detector

    def test_set_sleep_period_detector_clears_pattern_cache(self, algorithm_manager) -> None:
        """Setting detector clears sleep pattern cache."""
        algorithm_manager._sleep_pattern_cache[("key",)] = (1, 2)

        mock_detector = MagicMock()
        algorithm_manager.set_sleep_period_detector(mock_detector)

        assert algorithm_manager._sleep_pattern_cache == {}


class TestGetChoiActivityColumn:
    """Tests for _get_choi_activity_column."""

    def test_gets_from_parent(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Gets Choi activity column from parent."""
        mock_parent.get_choi_activity_column.return_value = ActivityDataPreference.AXIS_Y

        result = algorithm_manager._get_choi_activity_column()

        assert result == ActivityDataPreference.AXIS_Y

    def test_falls_back_to_vector_magnitude_on_error(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Falls back to VECTOR_MAGNITUDE on error."""
        mock_parent.get_choi_activity_column.side_effect = Exception("Config error")

        result = algorithm_manager._get_choi_activity_column()

        assert result == ActivityDataPreference.VECTOR_MAGNITUDE


class TestCacheManagement:
    """Tests for cache management methods."""

    def test_clear_algorithm_cache(self, algorithm_manager) -> None:
        """clear_algorithm_cache clears both caches."""
        algorithm_manager._algorithm_cache["key1"] = {"data": [1]}
        algorithm_manager._sleep_pattern_cache[("key2",)] = (1, 2)

        algorithm_manager.clear_algorithm_cache()

        assert algorithm_manager._algorithm_cache == {}
        assert algorithm_manager._sleep_pattern_cache == {}

    def test_get_algorithm_cache_info(self, algorithm_manager) -> None:
        """get_algorithm_cache_info returns cache sizes."""
        algorithm_manager._algorithm_cache["key1"] = {"data": [1]}
        algorithm_manager._algorithm_cache["key2"] = {"data": [2]}
        algorithm_manager._sleep_pattern_cache[("key3",)] = (1, 2)

        info = algorithm_manager.get_algorithm_cache_info()

        assert info["algorithm_cache_size"] == 2
        assert info["sleep_pattern_cache_size"] == 1


class TestPlotAlgorithms:
    """Tests for plot_algorithms method."""

    def test_plot_algorithms_returns_early_if_no_activity_data(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Returns early if no activity data."""
        mock_parent.activity_data = None

        algorithm_manager.plot_algorithms()

        # Should not call algorithm scoring
        mock_parent.create_sleep_algorithm.return_value.score.assert_not_called()

    def test_plot_algorithms_uses_48h_data_when_available(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Uses 48hr data when available."""
        algorithm_manager.plot_algorithms()

        # Should use the sleep scoring algorithm
        mock_algorithm = mock_parent.create_sleep_algorithm.return_value
        mock_algorithm.score.assert_called()

    def test_plot_algorithms_runs_choi_detection(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Runs Choi nonwear detection."""
        algorithm_manager.plot_algorithms()

        mock_parent.create_nonwear_algorithm.assert_called_with(NonwearAlgorithm.CHOI_2011)
        mock_parent.create_nonwear_algorithm.return_value.detect.assert_called()

    def test_plot_algorithms_caches_results(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Caches algorithm results."""
        algorithm_manager.plot_algorithms()

        assert len(algorithm_manager._algorithm_cache) > 0

    def test_plot_algorithms_uses_cache_on_second_call(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Uses cached results on second call with same data."""
        algorithm_manager.plot_algorithms()
        call_count_1 = mock_parent.create_sleep_algorithm.return_value.score.call_count

        algorithm_manager.plot_algorithms()
        call_count_2 = mock_parent.create_sleep_algorithm.return_value.score.call_count

        # Should not score again due to caching
        assert call_count_2 == call_count_1

    def test_plot_algorithms_limits_cache_size(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Limits cache size to 5 entries."""
        # Fill cache with 5 entries manually
        for i in range(5):
            algorithm_manager._algorithm_cache[f"key_{i}"] = {"sadeh": [i]}

        # Run plot_algorithms which should add a new entry and evict oldest
        algorithm_manager.plot_algorithms()

        assert len(algorithm_manager._algorithm_cache) <= 5


class TestApplySleepScoringRules:
    """Tests for apply_sleep_scoring_rules method."""

    def test_apply_sleep_scoring_rules_no_selected_period(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Returns early if no selected period."""
        mock_parent.get_selected_marker_period.return_value = None

        algorithm_manager.apply_sleep_scoring_rules(MagicMock())

        # Should not call detector
        mock_parent.create_sleep_period_detector.return_value.apply_rules.assert_not_called()

    def test_apply_sleep_scoring_rules_incomplete_period(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Returns early if period is incomplete."""
        mock_period = MagicMock()
        mock_period.is_complete = False
        mock_parent.get_selected_marker_period.return_value = mock_period

        algorithm_manager.apply_sleep_scoring_rules(MagicMock())

        mock_parent.create_sleep_period_detector.return_value.apply_rules.assert_not_called()

    def test_apply_sleep_scoring_rules_no_sadeh_results(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Returns early if no Sadeh results."""
        mock_parent.main_48h_sadeh_results = []

        algorithm_manager.apply_sleep_scoring_rules(MagicMock())

        mock_parent.create_sleep_period_detector.return_value.apply_rules.assert_not_called()

    def test_apply_sleep_scoring_rules_calls_detector(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Calls sleep period detector."""
        # Pre-populate the 48hr sadeh results
        algorithm_manager.main_48h_sadeh_results = mock_parent.main_48h_sadeh_results

        algorithm_manager.apply_sleep_scoring_rules(MagicMock())

        mock_parent.create_sleep_period_detector.return_value.apply_rules.assert_called()


class TestClearSleepOnsetOffsetMarkers:
    """Tests for clear_sleep_onset_offset_markers."""

    def test_clears_markers_from_plot(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Removes markers from plot."""
        mock_marker1 = MagicMock()
        mock_marker2 = MagicMock()
        mock_parent.sleep_rule_markers = [mock_marker1, mock_marker2]

        algorithm_manager.clear_sleep_onset_offset_markers()

        mock_parent.plotItem.removeItem.assert_any_call(mock_marker1)
        mock_parent.plotItem.removeItem.assert_any_call(mock_marker2)

    def test_clears_marker_list(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Clears the marker list."""
        mock_parent.sleep_rule_markers = [MagicMock(), MagicMock()]

        algorithm_manager.clear_sleep_onset_offset_markers()

        assert mock_parent.sleep_rule_markers == []


class TestCreateMarkerMethods:
    """Tests for create_sleep_onset_marker and create_sleep_offset_marker."""

    def test_create_sleep_onset_marker_adds_to_plot(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Creates onset marker and adds to plot."""
        timestamp = datetime(2024, 1, 1, 22, 0).timestamp()

        algorithm_manager.create_sleep_onset_marker(timestamp)

        # Should add arrow and text items
        assert mock_parent.plotItem.addItem.call_count >= 2
        assert len(mock_parent.sleep_rule_markers) >= 2

    def test_create_sleep_offset_marker_adds_to_plot(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Creates offset marker and adds to plot."""
        timestamp = datetime(2024, 1, 2, 7, 0).timestamp()

        algorithm_manager.create_sleep_offset_marker(timestamp)

        # Should add arrow and text items
        assert mock_parent.plotItem.addItem.call_count >= 2
        assert len(mock_parent.sleep_rule_markers) >= 2

    def test_create_onset_marker_uses_detector_labels(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Uses detector labels when provided."""
        mock_detector = MagicMock()
        mock_detector.get_marker_labels.return_value = ("Custom Onset", "Custom Offset")
        timestamp = datetime(2024, 1, 1, 22, 0).timestamp()

        algorithm_manager.create_sleep_onset_marker(timestamp, mock_detector)

        mock_detector.get_marker_labels.assert_called()


class TestExtractViewSubsetFromMainResults:
    """Tests for _extract_view_subset_from_main_results."""

    def test_uses_full_results_for_48h_view(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Uses full results for 48hr view."""
        mock_parent.current_view_hours = 48
        algorithm_manager.main_48h_sadeh_results = [1, 0, 1, 0]
        # Must also set timestamps to match (DATA ALIGNMENT FIX validation)
        mock_parent.main_48h_sadeh_timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(4)]

        algorithm_manager._extract_view_subset_from_main_results()

        assert algorithm_manager.sadeh_results == [1, 0, 1, 0]

    def test_returns_empty_if_no_main_results(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Returns empty list if no main results."""
        mock_parent.main_48h_sadeh_results = None
        mock_parent.main_48h_axis_y_timestamps = None

        algorithm_manager._extract_view_subset_from_main_results()

        assert algorithm_manager.sadeh_results == []

    def test_returns_empty_if_no_timestamps(self, algorithm_manager, mock_parent: MagicMock) -> None:
        """Returns empty list if no timestamps."""
        mock_parent.timestamps = []
        mock_parent.current_view_hours = 24

        algorithm_manager._extract_view_subset_from_main_results()

        assert algorithm_manager.sadeh_results == []
