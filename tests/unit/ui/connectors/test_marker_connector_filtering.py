"""Tests for MarkersConnector bounds filtering (copy-and-filter methods).

These methods create deep copies of Redux state markers and remove
out-of-bounds periods, ensuring Redux state is never mutated.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sleep_scoring_app.core.constants import MarkerType
from sleep_scoring_app.core.dataclasses_markers import (
    DailyNonwearMarkers,
    DailySleepMarkers,
    ManualNonwearPeriod,
    SleepPeriod,
)
from sleep_scoring_app.ui.connectors.marker import MarkersConnector

# Data bounds used across tests (24h window)
DATA_START = 1705276800.0  # 2024-01-15 00:00:00
DATA_END = 1705449600.0  # 2024-01-17 00:00:00


@pytest.fixture
def connector() -> MarkersConnector:
    """Create a MarkersConnector with mocked dependencies (no Qt)."""
    store = MagicMock()
    store.state = MagicMock()
    store.subscribe = MagicMock(return_value=lambda: None)

    main_window = MagicMock()
    main_window.plot_widget = None  # No widget needed for unit testing filter methods

    return MarkersConnector(store, main_window)


# ========== Sleep marker filtering ==========


class TestCopyAndFilterSleepMarkers:
    """Tests for _copy_and_filter_sleep_markers."""

    def test_returns_deep_copy_not_original(self, connector: MarkersConnector) -> None:
        """Returned object is a different instance from the input."""
        markers = DailySleepMarkers()
        markers.period_1 = SleepPeriod(
            marker_type=MarkerType.MAIN_SLEEP,
            onset_timestamp=DATA_START + 3600,
            offset_timestamp=DATA_START + 7200,
        )

        result, removed = connector._copy_and_filter_sleep_markers(markers, (DATA_START, DATA_END))

        assert result is not markers
        assert result.period_1 is not markers.period_1
        assert removed == 0

    def test_does_not_mutate_original(self, connector: MarkersConnector) -> None:
        """Original markers object is unchanged after filtering removes periods."""
        valid = SleepPeriod(
            marker_type=MarkerType.MAIN_SLEEP,
            onset_timestamp=DATA_START + 3600,
            offset_timestamp=DATA_START + 7200,
        )
        invalid = SleepPeriod(
            marker_type=MarkerType.NAP,
            onset_timestamp=1000.0,  # Way before data start
            offset_timestamp=2000.0,
        )
        markers = DailySleepMarkers()
        markers.period_1 = valid
        markers.period_2 = invalid

        connector._copy_and_filter_sleep_markers(markers, (DATA_START, DATA_END))

        # Original must be untouched
        assert markers.period_1 is valid
        assert markers.period_2 is invalid

    def test_removes_onset_out_of_bounds(self, connector: MarkersConnector) -> None:
        """Removes period when onset is outside data bounds."""
        markers = DailySleepMarkers()
        markers.period_1 = SleepPeriod(
            marker_type=MarkerType.MAIN_SLEEP,
            onset_timestamp=1000.0,
            offset_timestamp=DATA_START + 3600,
        )

        result, removed = connector._copy_and_filter_sleep_markers(markers, (DATA_START, DATA_END))

        assert result.period_1 is None
        assert removed == 1

    def test_removes_offset_out_of_bounds(self, connector: MarkersConnector) -> None:
        """Removes period when offset is outside data bounds."""
        markers = DailySleepMarkers()
        markers.period_1 = SleepPeriod(
            marker_type=MarkerType.MAIN_SLEEP,
            onset_timestamp=DATA_START + 3600,
            offset_timestamp=9999999999.0,
        )

        result, removed = connector._copy_and_filter_sleep_markers(markers, (DATA_START, DATA_END))

        assert result.period_1 is None
        assert removed == 1

    def test_keeps_valid_periods(self, connector: MarkersConnector) -> None:
        """Keeps periods that are within bounds."""
        markers = DailySleepMarkers()
        markers.period_1 = SleepPeriod(
            marker_type=MarkerType.MAIN_SLEEP,
            onset_timestamp=DATA_START + 3600,
            offset_timestamp=DATA_START + 7200,
        )

        result, removed = connector._copy_and_filter_sleep_markers(markers, (DATA_START, DATA_END))

        assert result.period_1 is not None
        assert result.period_1.onset_timestamp == DATA_START + 3600
        assert removed == 0

    def test_no_bounds_returns_copy_unfiltered(self, connector: MarkersConnector) -> None:
        """When data_bounds is None, returns a copy with all periods intact."""
        markers = DailySleepMarkers()
        markers.period_1 = SleepPeriod(
            marker_type=MarkerType.MAIN_SLEEP,
            onset_timestamp=1000.0,
            offset_timestamp=2000.0,
        )

        result, removed = connector._copy_and_filter_sleep_markers(markers, None)

        assert result is not markers
        assert result.period_1 is not None
        assert removed == 0

    def test_mixed_valid_and_invalid(self, connector: MarkersConnector) -> None:
        """Removes only invalid periods, keeps valid ones."""
        valid = SleepPeriod(
            marker_type=MarkerType.MAIN_SLEEP,
            onset_timestamp=DATA_START + 3600,
            offset_timestamp=DATA_START + 7200,
        )
        invalid = SleepPeriod(
            marker_type=MarkerType.NAP,
            onset_timestamp=1000.0,
            offset_timestamp=2000.0,
        )
        markers = DailySleepMarkers()
        markers.period_1 = valid
        markers.period_2 = invalid

        result, removed = connector._copy_and_filter_sleep_markers(markers, (DATA_START, DATA_END))

        assert result.period_1 is not None
        assert result.period_2 is None
        assert removed == 1


# ========== Nonwear marker filtering ==========


class TestCopyAndFilterNonwearMarkers:
    """Tests for _copy_and_filter_nonwear_markers."""

    def test_returns_deep_copy_not_original(self, connector: MarkersConnector) -> None:
        """Returned object is a different instance from the input."""
        markers = DailyNonwearMarkers()
        markers.set_period_by_slot(
            1,
            ManualNonwearPeriod(
                marker_index=1,
                start_timestamp=DATA_START + 3600,
                end_timestamp=DATA_START + 7200,
            ),
        )

        result, removed = connector._copy_and_filter_nonwear_markers(markers, (DATA_START, DATA_END))

        assert result is not markers
        assert removed == 0

    def test_does_not_mutate_original(self, connector: MarkersConnector) -> None:
        """Original markers object is unchanged after filtering."""
        valid = ManualNonwearPeriod(marker_index=1, start_timestamp=DATA_START + 3600, end_timestamp=DATA_START + 7200)
        invalid = ManualNonwearPeriod(marker_index=2, start_timestamp=1000.0, end_timestamp=2000.0)

        markers = DailyNonwearMarkers()
        markers.set_period_by_slot(1, valid)
        markers.set_period_by_slot(2, invalid)

        connector._copy_and_filter_nonwear_markers(markers, (DATA_START, DATA_END))

        # Original must be untouched
        assert markers.get_period_by_slot(1) is valid
        assert markers.get_period_by_slot(2) is invalid

    def test_removes_start_out_of_bounds(self, connector: MarkersConnector) -> None:
        """Removes period when start is outside data bounds."""
        markers = DailyNonwearMarkers()
        markers.set_period_by_slot(
            1,
            ManualNonwearPeriod(
                marker_index=1,
                start_timestamp=1000.0,
                end_timestamp=DATA_START + 3600,
            ),
        )

        result, removed = connector._copy_and_filter_nonwear_markers(markers, (DATA_START, DATA_END))

        assert result.get_period_by_slot(1) is None
        assert removed == 1

    def test_removes_end_out_of_bounds(self, connector: MarkersConnector) -> None:
        """Removes period when end is outside data bounds."""
        markers = DailyNonwearMarkers()
        markers.set_period_by_slot(
            1,
            ManualNonwearPeriod(
                marker_index=1,
                start_timestamp=DATA_START + 3600,
                end_timestamp=9999999999.0,
            ),
        )

        result, removed = connector._copy_and_filter_nonwear_markers(markers, (DATA_START, DATA_END))

        assert result.get_period_by_slot(1) is None
        assert removed == 1

    def test_keeps_valid_periods(self, connector: MarkersConnector) -> None:
        """Keeps periods that are within bounds."""
        markers = DailyNonwearMarkers()
        markers.set_period_by_slot(
            1,
            ManualNonwearPeriod(
                marker_index=1,
                start_timestamp=DATA_START + 3600,
                end_timestamp=DATA_START + 7200,
            ),
        )

        result, removed = connector._copy_and_filter_nonwear_markers(markers, (DATA_START, DATA_END))

        assert result.get_period_by_slot(1) is not None
        assert removed == 0

    def test_no_bounds_returns_copy_unfiltered(self, connector: MarkersConnector) -> None:
        """When data_bounds is None, returns a copy with all periods intact."""
        markers = DailyNonwearMarkers()
        markers.set_period_by_slot(
            1,
            ManualNonwearPeriod(
                marker_index=1,
                start_timestamp=1000.0,
                end_timestamp=2000.0,
            ),
        )

        result, removed = connector._copy_and_filter_nonwear_markers(markers, None)

        assert result is not markers
        assert result.get_period_by_slot(1) is not None
        assert removed == 0

    def test_mixed_valid_and_invalid(self, connector: MarkersConnector) -> None:
        """Removes only invalid periods, keeps valid ones."""
        valid = ManualNonwearPeriod(marker_index=1, start_timestamp=DATA_START + 3600, end_timestamp=DATA_START + 7200)
        invalid = ManualNonwearPeriod(marker_index=2, start_timestamp=1000.0, end_timestamp=2000.0)

        markers = DailyNonwearMarkers()
        markers.set_period_by_slot(1, valid)
        markers.set_period_by_slot(2, invalid)

        result, removed = connector._copy_and_filter_nonwear_markers(markers, (DATA_START, DATA_END))

        assert result.get_period_by_slot(1) is not None
        assert result.get_period_by_slot(2) is None
        assert removed == 1
