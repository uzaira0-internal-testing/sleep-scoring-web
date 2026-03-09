"""
Tests for PlotDataManager.

Tests data management operations for the activity plot widget including:
- Loading and caching activity data
- Managing 48-hour and view-specific data
- Handling timestamps and data ranges
- Managing data swapping between axis_y and vector magnitude
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from sleep_scoring_app.ui.widgets.plot_data_manager import PlotDataManager


@pytest.fixture
def mock_parent() -> MagicMock:
    """Create a mock ActivityPlotWidget parent."""
    parent = MagicMock()
    parent.timestamps = []
    parent.activity_data = []
    parent.main_48h_timestamps = None
    parent.main_48h_activity = None
    parent.main_48h_axis_y_data = None
    parent.main_48h_sadeh_results = None
    parent.main_48h_sadeh_timestamps = None
    return parent


@pytest.fixture
def data_manager(mock_parent: MagicMock) -> PlotDataManager:
    """Create a PlotDataManager instance."""
    return PlotDataManager(mock_parent)


@pytest.fixture
def sample_timestamps() -> list[datetime]:
    """Create sample timestamps for testing (48 hours of 1-minute epochs)."""
    start = datetime(2024, 1, 15, 0, 0, 0)
    return [start + timedelta(minutes=i) for i in range(48 * 60)]


@pytest.fixture
def sample_activity() -> list[float]:
    """Create sample activity data (48 hours of 1-minute epochs)."""
    return [float(i % 100) for i in range(48 * 60)]


@pytest.fixture
def sample_axis_y() -> list[float]:
    """Create sample axis_y data (different from activity)."""
    return [float((i * 2) % 100) for i in range(48 * 60)]


@pytest.fixture
def sample_sadeh() -> list[int]:
    """Create sample Sadeh results."""
    return [i % 2 for i in range(48 * 60)]


class TestPlotDataManagerInit:
    """Tests for PlotDataManager initialization."""

    def test_init_stores_parent(self, data_manager: PlotDataManager, mock_parent: MagicMock) -> None:
        """Stores parent reference."""
        assert data_manager.parent is mock_parent

    def test_init_empty_data_lists(self, data_manager: PlotDataManager) -> None:
        """Initializes with empty data lists."""
        assert data_manager.timestamps == []
        assert data_manager.activity_data == []
        assert data_manager.sadeh_results == []

    def test_init_none_48h_cache(self, data_manager: PlotDataManager) -> None:
        """Initializes with None 48h cache."""
        assert data_manager.main_48h_timestamps is None
        assert data_manager.main_48h_activity is None
        assert data_manager.main_48h_axis_y_data is None
        assert data_manager.main_48h_sadeh_results is None

    def test_init_zero_boundaries(self, data_manager: PlotDataManager) -> None:
        """Initializes with zero boundaries."""
        assert data_manager.data_start_time == 0
        assert data_manager.data_end_time == 0
        assert data_manager.view_start_idx == 0
        assert data_manager.view_end_idx == 0

    def test_init_default_view_hours(self, data_manager: PlotDataManager) -> None:
        """Initializes with 48 hour default view."""
        assert data_manager.current_view_hours == 48

    def test_init_data_not_swapped(self, data_manager: PlotDataManager) -> None:
        """Initializes with data not swapped."""
        assert data_manager.is_data_swapped is False


class TestSetTimestamps:
    """Tests for set_timestamps method."""

    def test_sets_timestamps(self, data_manager: PlotDataManager, sample_timestamps: list[datetime]) -> None:
        """Sets timestamp data."""
        data_manager.set_timestamps(sample_timestamps)
        assert data_manager.timestamps == sample_timestamps

    def test_updates_parent_reference(self, data_manager: PlotDataManager, mock_parent: MagicMock, sample_timestamps: list[datetime]) -> None:
        """Updates parent timestamps reference."""
        data_manager.set_timestamps(sample_timestamps)
        assert mock_parent.timestamps == sample_timestamps

    def test_sets_data_boundaries(self, data_manager: PlotDataManager, sample_timestamps: list[datetime]) -> None:
        """Sets data start and end times."""
        data_manager.set_timestamps(sample_timestamps)
        assert data_manager.data_start_time == sample_timestamps[0].timestamp()
        assert data_manager.data_end_time == sample_timestamps[-1].timestamp()

    def test_handles_empty_timestamps(self, data_manager: PlotDataManager) -> None:
        """Handles empty timestamps list."""
        data_manager.set_timestamps([])
        assert data_manager.timestamps == []
        assert data_manager.data_start_time == 0
        assert data_manager.data_end_time == 0


class TestSetActivityData:
    """Tests for set_activity_data method."""

    def test_sets_activity_data(self, data_manager: PlotDataManager, sample_activity: list[float]) -> None:
        """Sets activity data."""
        data_manager.set_activity_data(sample_activity)
        assert data_manager.activity_data == sample_activity

    def test_updates_parent_reference(self, data_manager: PlotDataManager, mock_parent: MagicMock, sample_activity: list[float]) -> None:
        """Updates parent activity_data reference."""
        data_manager.set_activity_data(sample_activity)
        assert mock_parent.activity_data == sample_activity


class TestSet48hMainData:
    """Tests for set_48h_main_data method."""

    def test_sets_timestamps_and_activity(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
    ) -> None:
        """Sets timestamps and activity data."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity)
        assert data_manager.main_48h_timestamps == sample_timestamps
        assert data_manager.main_48h_activity == sample_activity

    def test_sets_optional_axis_y(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
        sample_axis_y: list[float],
    ) -> None:
        """Sets optional axis_y data."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity, axis_y=sample_axis_y)
        assert data_manager.main_48h_axis_y_data == sample_axis_y

    def test_sets_optional_sadeh(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
        sample_sadeh: list[int],
    ) -> None:
        """Sets optional Sadeh results."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity, sadeh=sample_sadeh)
        assert data_manager.main_48h_sadeh_results == sample_sadeh

    def test_updates_parent_references(
        self,
        data_manager: PlotDataManager,
        mock_parent: MagicMock,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
        sample_axis_y: list[float],
        sample_sadeh: list[int],
    ) -> None:
        """Updates all parent references."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity, axis_y=sample_axis_y, sadeh=sample_sadeh)
        assert mock_parent.main_48h_timestamps == sample_timestamps
        assert mock_parent.main_48h_activity == sample_activity
        assert mock_parent.main_48h_axis_y_data == sample_axis_y
        assert mock_parent.main_48h_sadeh_results == sample_sadeh


class TestGetViewIndices:
    """Tests for get_view_indices method."""

    def test_calculates_indices_for_first_24h(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
    ) -> None:
        """Calculates correct indices for first 24 hours."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity)
        start_idx, end_idx = data_manager.get_view_indices(0, 24)
        assert start_idx == 0
        assert end_idx == 24 * 60  # 1440 minutes

    def test_calculates_indices_for_second_24h(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
    ) -> None:
        """Calculates correct indices for second 24 hours."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity)
        start_idx, end_idx = data_manager.get_view_indices(24, 24)
        assert start_idx == 24 * 60  # 1440
        assert end_idx == 48 * 60  # 2880

    def test_clamps_end_index_to_data_length(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
    ) -> None:
        """Clamps end index to data length."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity)
        _start_idx, end_idx = data_manager.get_view_indices(40, 24)  # Would exceed 48h
        assert end_idx == len(sample_timestamps)

    def test_returns_zeros_when_no_data(self, data_manager: PlotDataManager) -> None:
        """Returns zeros when no data loaded."""
        start_idx, end_idx = data_manager.get_view_indices(0, 24)
        assert start_idx == 0
        assert end_idx == 0


class TestExtractViewSubset:
    """Tests for extract_view_subset method."""

    def test_extracts_timestamps_and_activity(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
    ) -> None:
        """Extracts timestamps and activity for view."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity)
        view_data = data_manager.extract_view_subset(0, 100)
        assert view_data["timestamps"] == sample_timestamps[0:100]
        assert view_data["activity"] == sample_activity[0:100]

    def test_includes_sadeh_when_available(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
        sample_sadeh: list[int],
    ) -> None:
        """Includes Sadeh results when available."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity, sadeh=sample_sadeh)
        view_data = data_manager.extract_view_subset(0, 100)
        assert view_data["sadeh"] == sample_sadeh[0:100]

    def test_excludes_sadeh_when_requested(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
        sample_sadeh: list[int],
    ) -> None:
        """Excludes Sadeh when include_algorithms=False."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity, sadeh=sample_sadeh)
        view_data = data_manager.extract_view_subset(0, 100, include_algorithms=False)
        assert "sadeh" not in view_data

    def test_updates_view_indices(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
    ) -> None:
        """Updates view start and end indices."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity)
        data_manager.extract_view_subset(50, 150)
        assert data_manager.view_start_idx == 50
        assert data_manager.view_end_idx == 150

    def test_returns_empty_dict_when_no_data(self, data_manager: PlotDataManager) -> None:
        """Returns empty dict when no data loaded."""
        view_data = data_manager.extract_view_subset(0, 100)
        assert view_data == {}


class TestSwapActivityDataSource:
    """Tests for swap_activity_data_source method."""

    def test_swaps_to_vector_magnitude(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
        sample_axis_y: list[float],
    ) -> None:
        """Swaps to vector magnitude data."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity, axis_y=sample_axis_y)
        original_activity = data_manager.main_48h_activity.copy()
        original_axis_y = data_manager.main_48h_axis_y_data.copy()

        result = data_manager.swap_activity_data_source(use_vector_magnitude=True)

        assert result is True
        assert data_manager.is_data_swapped is True
        assert data_manager.main_48h_activity == original_axis_y
        assert data_manager.main_48h_axis_y_data == original_activity

    def test_swaps_back_to_axis_y(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
        sample_axis_y: list[float],
    ) -> None:
        """Swaps back to axis_y data."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity, axis_y=sample_axis_y)
        original_activity = data_manager.main_48h_activity.copy()

        # Swap to VM then back
        data_manager.swap_activity_data_source(use_vector_magnitude=True)
        result = data_manager.swap_activity_data_source(use_vector_magnitude=False)

        assert result is True
        assert data_manager.is_data_swapped is False
        assert data_manager.main_48h_activity == original_activity

    def test_no_swap_when_already_correct(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
        sample_axis_y: list[float],
    ) -> None:
        """Does not swap when already using correct source."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity, axis_y=sample_axis_y)
        original_activity = data_manager.main_48h_activity.copy()

        # Already using axis_y, request axis_y
        result = data_manager.swap_activity_data_source(use_vector_magnitude=False)

        assert result is True
        assert data_manager.is_data_swapped is False
        assert data_manager.main_48h_activity == original_activity

    def test_returns_false_when_missing_data(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
    ) -> None:
        """Returns False when axis_y data is missing."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity)  # No axis_y
        result = data_manager.swap_activity_data_source(use_vector_magnitude=True)
        assert result is False

    def test_returns_false_when_no_data(self, data_manager: PlotDataManager) -> None:
        """Returns False when no data loaded."""
        result = data_manager.swap_activity_data_source(use_vector_magnitude=True)
        assert result is False


class TestClearAllData:
    """Tests for clear_all_data method."""

    def test_clears_current_data(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
    ) -> None:
        """Clears current timestamps and activity data."""
        data_manager.set_timestamps(sample_timestamps)
        data_manager.set_activity_data(sample_activity)
        data_manager.sadeh_results = [1, 0, 1]

        data_manager.clear_all_data()

        assert data_manager.timestamps == []
        assert data_manager.activity_data == []
        assert data_manager.sadeh_results == []

    def test_clears_48h_cache(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
        sample_axis_y: list[float],
        sample_sadeh: list[int],
    ) -> None:
        """Clears 48h main data cache."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity, axis_y=sample_axis_y, sadeh=sample_sadeh)

        data_manager.clear_all_data()

        assert data_manager.main_48h_timestamps is None
        assert data_manager.main_48h_activity is None
        assert data_manager.main_48h_axis_y_data is None
        assert data_manager.main_48h_sadeh_results is None

    def test_resets_boundaries(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
    ) -> None:
        """Resets data boundaries."""
        data_manager.set_timestamps(sample_timestamps)
        data_manager.view_start_idx = 100
        data_manager.view_end_idx = 200

        data_manager.clear_all_data()

        assert data_manager.data_start_time == 0
        assert data_manager.data_end_time == 0
        assert data_manager.view_start_idx == 0
        assert data_manager.view_end_idx == 0

    def test_resets_swap_state(
        self,
        data_manager: PlotDataManager,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
        sample_axis_y: list[float],
    ) -> None:
        """Resets data swap state."""
        data_manager.set_48h_main_data(sample_timestamps, sample_activity, axis_y=sample_axis_y)
        data_manager.swap_activity_data_source(use_vector_magnitude=True)

        data_manager.clear_all_data()

        assert data_manager.is_data_swapped is False

    def test_clears_parent_references(
        self,
        data_manager: PlotDataManager,
        mock_parent: MagicMock,
        sample_timestamps: list[datetime],
        sample_activity: list[float],
    ) -> None:
        """Clears parent references."""
        data_manager.set_timestamps(sample_timestamps)
        data_manager.set_activity_data(sample_activity)
        data_manager.set_48h_main_data(sample_timestamps, sample_activity)

        data_manager.clear_all_data()

        assert mock_parent.timestamps == []
        assert mock_parent.activity_data == []
        assert mock_parent.main_48h_timestamps is None
        assert mock_parent.main_48h_activity is None


class TestViewHours:
    """Tests for view hours getter/setter."""

    def test_get_current_view_hours(self, data_manager: PlotDataManager) -> None:
        """Gets current view hours."""
        assert data_manager.get_current_view_hours() == 48

    def test_set_current_view_hours(self, data_manager: PlotDataManager) -> None:
        """Sets current view hours."""
        data_manager.set_current_view_hours(24)
        assert data_manager.current_view_hours == 24
        assert data_manager.get_current_view_hours() == 24
