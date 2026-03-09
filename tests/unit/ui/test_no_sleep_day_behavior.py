"""
Tests for no-sleep-day nap/main-sleep behavior.

Verifies the four behavioral changes:
1. Diary nap columns allow nap placement on no-sleep days (guard relaxed)
2. Diary main sleep columns are blocked on no-sleep days (info message)
3. Plot clicks create NAPs (not MAIN_SLEEP) on no-sleep days
4. Bulk diary row skips main sleep creation on no-sleep days

Uses real UIStore, real dataclasses, real coordinator/connector logic.
Mocks only external boundaries (services, Qt widgets, navigation).
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.core.constants import DiaryTableColumn, MarkerCategory, MarkerType
from sleep_scoring_app.core.dataclasses import SleepPeriod
from sleep_scoring_app.core.dataclasses_diary import DiaryEntry
from sleep_scoring_app.core.dataclasses_markers import DailySleepMarkers
from sleep_scoring_app.ui.store import Actions, UIStore

# Patch QMessageBox in the coordinator module so Qt dialog calls don't
# fail when the parent is a MagicMock (tests run without a real QWidget).
_QMSGBOX_PATCH = "sleep_scoring_app.ui.coordinators.diary_integration_coordinator.QMessageBox"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> UIStore:
    """Create a real UIStore seeded with a file and date."""
    s = UIStore()
    s.dispatch(Actions.file_selected(filename="TEST-001.csv"))
    s.dispatch(Actions.dates_loaded(dates=["2024-06-15"]))
    s.dispatch(Actions.date_selected(date_index=0))
    return s


@pytest.fixture
def no_sleep_store(store: UIStore) -> UIStore:
    """Store with is_no_sleep_marked=True."""
    store.dispatch(Actions.markers_loaded(sleep=None, nonwear=None, is_no_sleep=True))
    assert store.state.is_no_sleep_marked is True
    return store


@pytest.fixture
def normal_store(store: UIStore) -> UIStore:
    """Store with is_no_sleep_marked=False (normal day)."""
    store.dispatch(Actions.markers_loaded(sleep=None, nonwear=None, is_no_sleep=False))
    assert store.state.is_no_sleep_marked is False
    return store


@pytest.fixture
def diary_entry_with_nap() -> DiaryEntry:
    """Diary entry with nap 1 times but no main sleep."""
    return DiaryEntry(
        participant_id="TEST-001",
        diary_date="2024-06-15",
        filename="TEST-001.csv",
        nap_onset_time="14:00",
        nap_offset_time="15:00",
    )


@pytest.fixture
def diary_entry_with_main_sleep() -> DiaryEntry:
    """Diary entry with main sleep times."""
    return DiaryEntry(
        participant_id="TEST-001",
        diary_date="2024-06-15",
        filename="TEST-001.csv",
        sleep_onset_time="22:30",
        sleep_offset_time="06:30",
    )


@pytest.fixture
def diary_entry_full() -> DiaryEntry:
    """Diary entry with main sleep + nap 1."""
    return DiaryEntry(
        participant_id="TEST-001",
        diary_date="2024-06-15",
        filename="TEST-001.csv",
        sleep_onset_time="22:30",
        sleep_offset_time="06:30",
        nap_onset_time="14:00",
        nap_offset_time="15:00",
    )


def _make_main_sleep_markers() -> DailySleepMarkers:
    """DailySleepMarkers with a complete main sleep in slot 1."""
    markers = DailySleepMarkers()
    markers.period_1 = SleepPeriod(
        onset_timestamp=1718492400.0,   # 2024-06-15 22:00 UTC
        offset_timestamp=1718521200.0,  # 2024-06-16 06:00 UTC
        marker_index=1,
        marker_type=MarkerType.MAIN_SLEEP,
    )
    return markers


def _build_coordinator(
    store: UIStore,
    diary_entries: list[DiaryEntry],
) -> tuple:
    """Build a DiaryIntegrationCoordinator with mocked boundaries.

    QMessageBox is patched so Qt dialogs don't fail with MagicMock parents.

    Returns (coordinator, mock_main_window, mock_msgbox, mock_marker_ops, mock_services).
    """
    from sleep_scoring_app.ui.coordinators.diary_integration_coordinator import (
        DiaryIntegrationCoordinator,
    )

    # --- navigation (protocol stub) ---
    nav = MagicMock()
    nav.available_dates = [datetime(2024, 6, 15).date()]
    nav.current_date_index = 0
    # _parse_time_to_timestamp: convert "HH:MM" to a float timestamp
    # relative to 2024-06-15 midnight in UTC-like domain
    base_ts = datetime(2024, 6, 15, 0, 0, 0).timestamp()

    def _parse(time_str: str, base_date: datetime) -> float | None:
        try:
            h, m = map(int, time_str.split(":"))
            return base_ts + h * 3600 + m * 60
        except (ValueError, AttributeError):
            return None

    nav._parse_time_to_timestamp = _parse

    # --- marker_ops ---
    marker_ops = MagicMock()

    # --- services ---
    services = MagicMock()
    services.data_service.load_diary_data_for_current_file.return_value = diary_entries

    # --- main_window (Qt-level) ---
    mw = MagicMock()
    mw.plot_widget.actual_data_bounds = (base_ts, base_ts + 48 * 3600)
    mw.plot_widget.current_marker_being_placed = None
    mw.plot_widget._skip_auto_apply_rules = False
    mw._check_unsaved_markers_before_navigation.return_value = True

    # Patch QMessageBox so .information()/.warning() don't raise on MagicMock parents
    patcher = patch(_QMSGBOX_PATCH)
    mock_msgbox = patcher.start()

    coordinator = DiaryIntegrationCoordinator(
        store=store,
        navigation=nav,
        marker_ops=marker_ops,
        services=services,
        parent=mw,
    )
    # Stash patcher on coordinator so callers can stop it (or we rely on gc)
    coordinator._test_msgbox_patcher = patcher
    coordinator._test_mock_msgbox = mock_msgbox
    return coordinator, mw, mock_msgbox, marker_ops, services


# ===================================================================
# 1. Diary nap columns: allow naps on no-sleep days
# ===================================================================


class TestDiaryNapColumnsOnNoSleepDay:
    """Nap diary columns should create naps even when no main sleep exists on a no-sleep day."""

    @pytest.mark.parametrize(
        "column_type",
        [DiaryTableColumn.NAP_1_START, DiaryTableColumn.NAP_1_END],
        ids=["nap1_start", "nap1_end"],
    )
    def test_nap_1_allowed_on_no_sleep_day(
        self,
        no_sleep_store: UIStore,
        diary_entry_with_nap: DiaryEntry,
        column_type: DiaryTableColumn,
    ) -> None:
        """Nap 1 diary column places a nap even without main sleep on no-sleep day."""
        coordinator, _mw, mock_msgbox, *_ = _build_coordinator(no_sleep_store, [diary_entry_with_nap])

        coordinator.set_markers_from_diary_column(0, column_type)

        # Warning about "set main sleep first" should NOT have been shown
        mock_msgbox.warning.assert_not_called()

        # Markers should have been dispatched to store
        markers = no_sleep_store.state.current_sleep_markers
        assert markers is not None
        # Nap 1 goes in slot 2
        period = markers.get_period_by_slot(2)
        assert period is not None
        assert period.marker_type == MarkerType.NAP

    @pytest.mark.parametrize(
        "column_type",
        [DiaryTableColumn.NAP_2_START, DiaryTableColumn.NAP_2_END],
        ids=["nap2_start", "nap2_end"],
    )
    def test_nap_2_allowed_on_no_sleep_day(
        self,
        no_sleep_store: UIStore,
        column_type: DiaryTableColumn,
    ) -> None:
        """Nap 2 diary column places a nap even without main sleep on no-sleep day."""
        entry = DiaryEntry(
            participant_id="TEST-001",
            diary_date="2024-06-15",
            filename="TEST-001.csv",
            nap_onset_time_2="16:00",
            nap_offset_time_2="17:00",
        )
        coordinator, _mw, mock_msgbox, *_ = _build_coordinator(no_sleep_store, [entry])

        coordinator.set_markers_from_diary_column(0, column_type)

        mock_msgbox.warning.assert_not_called()
        markers = no_sleep_store.state.current_sleep_markers
        assert markers is not None
        period = markers.get_period_by_slot(3)
        assert period is not None
        assert period.marker_type == MarkerType.NAP

    @pytest.mark.parametrize(
        "column_type",
        [DiaryTableColumn.NAP_3_START, DiaryTableColumn.NAP_3_END],
        ids=["nap3_start", "nap3_end"],
    )
    def test_nap_3_allowed_on_no_sleep_day(
        self,
        no_sleep_store: UIStore,
        column_type: DiaryTableColumn,
    ) -> None:
        """Nap 3 diary column places a nap even without main sleep on no-sleep day."""
        entry = DiaryEntry(
            participant_id="TEST-001",
            diary_date="2024-06-15",
            filename="TEST-001.csv",
            nap_onset_time_3="18:00",
            nap_offset_time_3="19:00",
        )
        coordinator, _mw, mock_msgbox, *_ = _build_coordinator(no_sleep_store, [entry])

        coordinator.set_markers_from_diary_column(0, column_type)

        mock_msgbox.warning.assert_not_called()
        markers = no_sleep_store.state.current_sleep_markers
        assert markers is not None
        period = markers.get_period_by_slot(4)
        assert period is not None
        assert period.marker_type == MarkerType.NAP


class TestDiaryNapColumnsOnNormalDay:
    """Nap diary columns should still require main sleep on a normal (non-no-sleep) day."""

    def test_nap_1_blocked_without_main_sleep_on_normal_day(
        self,
        normal_store: UIStore,
        diary_entry_with_nap: DiaryEntry,
    ) -> None:
        """Nap 1 column is blocked when no main sleep exists on a normal day."""
        coordinator, _mw, mock_msgbox, *_ = _build_coordinator(normal_store, [diary_entry_with_nap])

        coordinator.set_markers_from_diary_column(0, DiaryTableColumn.NAP_1_START)

        # Warning about "set main sleep first" SHOULD have been shown
        mock_msgbox.warning.assert_called_once()
        # No markers should be dispatched
        assert normal_store.state.current_sleep_markers is None

    def test_nap_1_allowed_with_main_sleep_on_normal_day(
        self,
        normal_store: UIStore,
        diary_entry_with_nap: DiaryEntry,
    ) -> None:
        """Nap 1 column works when main sleep exists on a normal day."""
        # Pre-load main sleep markers into the store
        normal_store.dispatch(Actions.sleep_markers_changed(_make_main_sleep_markers()))

        coordinator, _mw, mock_msgbox, *_ = _build_coordinator(normal_store, [diary_entry_with_nap])

        coordinator.set_markers_from_diary_column(0, DiaryTableColumn.NAP_1_START)

        mock_msgbox.warning.assert_not_called()
        markers = normal_store.state.current_sleep_markers
        assert markers is not None
        period = markers.get_period_by_slot(2)
        assert period is not None
        assert period.marker_type == MarkerType.NAP


# ===================================================================
# 2. Diary main sleep columns: blocked on no-sleep days
# ===================================================================


class TestDiaryMainSleepBlockedOnNoSleepDay:
    """Main sleep diary columns should be blocked when is_no_sleep_marked=True."""

    @pytest.mark.parametrize(
        "column_type",
        [DiaryTableColumn.SLEEP_ONSET, DiaryTableColumn.SLEEP_OFFSET],
        ids=["onset", "offset"],
    )
    def test_main_sleep_blocked_on_no_sleep_day(
        self,
        no_sleep_store: UIStore,
        diary_entry_with_main_sleep: DiaryEntry,
        column_type: DiaryTableColumn,
    ) -> None:
        """Main sleep columns show info message and don't create markers on no-sleep day."""
        coordinator, _mw, mock_msgbox, *_ = _build_coordinator(no_sleep_store, [diary_entry_with_main_sleep])

        coordinator.set_markers_from_diary_column(0, column_type)

        # Info dialog should have been shown
        mock_msgbox.information.assert_called_once()
        # No sleep markers should be in the store
        assert no_sleep_store.state.current_sleep_markers is None

    def test_main_sleep_allowed_on_normal_day(
        self,
        normal_store: UIStore,
        diary_entry_with_main_sleep: DiaryEntry,
    ) -> None:
        """Main sleep columns work normally when is_no_sleep_marked=False."""
        coordinator, _mw, mock_msgbox, *_ = _build_coordinator(normal_store, [diary_entry_with_main_sleep])

        coordinator.set_markers_from_diary_column(0, DiaryTableColumn.SLEEP_ONSET)

        # No info dialog about "No Sleep Marked" should appear
        mock_msgbox.information.assert_not_called()
        markers = normal_store.state.current_sleep_markers
        assert markers is not None
        period = markers.get_period_by_slot(1)
        assert period is not None
        assert period.marker_type == MarkerType.MAIN_SLEEP


# ===================================================================
# 3. Plot clicks: NAP instead of MAIN_SLEEP on no-sleep days
# ===================================================================


class TestPlotClickConnectorNoSleepDay:
    """PlotClickConnector should pass force_nap=True on no-sleep days."""

    def test_plot_click_calls_force_nap_on_no_sleep_day(
        self,
        no_sleep_store: UIStore,
    ) -> None:
        """Left click dispatches add_sleep_marker(ts, force_nap=True) when no-sleep is marked."""
        from sleep_scoring_app.ui.connectors.plot import PlotClickConnector

        mw = MagicMock()
        pw = MagicMock()
        mw.plot_widget = pw
        # The connector connects to signals in __init__; provide them
        pw.plot_left_clicked = MagicMock()
        pw.plot_right_clicked = MagicMock()

        # Set marker mode to SLEEP
        no_sleep_store.dispatch(Actions.marker_mode_changed(MarkerCategory.SLEEP))

        connector = PlotClickConnector(no_sleep_store, mw)

        # Simulate the left-click handler directly
        connector._on_plot_left_clicked(1718467200.0)

        pw.add_sleep_marker.assert_called_once_with(1718467200.0, force_nap=True)
        connector.disconnect()

    def test_plot_click_normal_on_regular_day(
        self,
        normal_store: UIStore,
    ) -> None:
        """Left click dispatches add_sleep_marker(ts) without force_nap on a normal day."""
        from sleep_scoring_app.ui.connectors.plot import PlotClickConnector

        mw = MagicMock()
        pw = MagicMock()
        mw.plot_widget = pw
        pw.plot_left_clicked = MagicMock()
        pw.plot_right_clicked = MagicMock()

        normal_store.dispatch(Actions.marker_mode_changed(MarkerCategory.SLEEP))

        connector = PlotClickConnector(normal_store, mw)
        connector._on_plot_left_clicked(1718467200.0)

        pw.add_sleep_marker.assert_called_once_with(1718467200.0)
        connector.disconnect()

    def test_plot_click_nonwear_unaffected_by_no_sleep(
        self,
        no_sleep_store: UIStore,
    ) -> None:
        """Nonwear clicks are unaffected by no-sleep flag."""
        from sleep_scoring_app.ui.connectors.plot import PlotClickConnector

        mw = MagicMock()
        pw = MagicMock()
        mw.plot_widget = pw
        pw.plot_left_clicked = MagicMock()
        pw.plot_right_clicked = MagicMock()

        no_sleep_store.dispatch(Actions.marker_mode_changed(MarkerCategory.NONWEAR))

        connector = PlotClickConnector(no_sleep_store, mw)
        connector._on_plot_left_clicked(1718467200.0)

        pw.add_nonwear_marker.assert_called_once_with(1718467200.0)
        pw.add_sleep_marker.assert_not_called()
        connector.disconnect()


# ===================================================================
# 3b. add_sleep_marker with force_nap=True (widget-level)
# ===================================================================


class TestAddSleepMarkerForceNap:
    """ActivityPlotWidget.add_sleep_marker(force_nap=True) should always create NAP."""

    @pytest.fixture
    def plot_widget(self, qtbot):
        """Create a real ActivityPlotWidget for testing."""
        from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

        mock_app_state = MagicMock()
        widget = ActivityPlotWidget(main_window=mock_app_state)
        qtbot.addWidget(widget)
        return widget

    def test_force_nap_creates_nap_even_without_main_sleep(self, plot_widget) -> None:
        """force_nap=True creates a NAP marker even when no main sleep exists."""
        assert plot_widget.daily_sleep_markers.get_main_sleep() is None

        ts = 1718467200.0
        plot_widget.add_sleep_marker(ts, force_nap=True)

        # Should have started a NAP period (incomplete — onset only)
        period = plot_widget.current_marker_being_placed
        assert period is not None
        assert period.marker_type == MarkerType.NAP
        assert period.onset_timestamp == ts

    def test_without_force_nap_creates_main_sleep_when_none_exists(self, plot_widget) -> None:
        """Default behavior: creates MAIN_SLEEP when no main sleep exists."""
        assert plot_widget.daily_sleep_markers.get_main_sleep() is None

        ts = 1718467200.0
        plot_widget.add_sleep_marker(ts)

        period = plot_widget.current_marker_being_placed
        assert period is not None
        assert period.marker_type == MarkerType.MAIN_SLEEP

    def test_force_nap_still_creates_nap_when_main_sleep_exists(self, plot_widget) -> None:
        """force_nap=True creates a NAP even when main sleep already exists."""
        # Pre-populate main sleep
        plot_widget.daily_sleep_markers.period_1 = SleepPeriod(
            onset_timestamp=1718492400.0,
            offset_timestamp=1718521200.0,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )

        ts = 1718467200.0
        plot_widget.add_sleep_marker(ts, force_nap=True)

        period = plot_widget.current_marker_being_placed
        assert period is not None
        assert period.marker_type == MarkerType.NAP

    def test_default_creates_nap_when_main_sleep_exists(self, plot_widget) -> None:
        """Default behavior: creates NAP when main sleep already exists."""
        plot_widget.daily_sleep_markers.period_1 = SleepPeriod(
            onset_timestamp=1718492400.0,
            offset_timestamp=1718521200.0,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )

        ts = 1718467200.0
        plot_widget.add_sleep_marker(ts)

        period = plot_widget.current_marker_being_placed
        assert period is not None
        assert period.marker_type == MarkerType.NAP


# ===================================================================
# 4. Bulk diary row: skip main sleep on no-sleep days
# ===================================================================


class TestBulkDiaryRowNoSleepDay:
    """set_markers_from_diary_row should skip main sleep creation on no-sleep days."""

    def test_bulk_row_skips_main_sleep_on_no_sleep_day(
        self,
        no_sleep_store: UIStore,
        diary_entry_full: DiaryEntry,
    ) -> None:
        """Bulk row import skips main sleep but still creates naps on no-sleep day."""
        coordinator, mw, *_ = _build_coordinator(no_sleep_store, [diary_entry_full])
        # _create_sleep_period_from_timestamps is on main_window — returns a SleepPeriod
        nap_period = SleepPeriod(
            onset_timestamp=1718456400.0,
            offset_timestamp=1718460000.0,
            marker_index=2,
            marker_type=MarkerType.NAP,
        )
        mw._create_sleep_period_from_timestamps.return_value = nap_period

        coordinator.set_markers_from_diary_row(0)

        # _create_sleep_period_from_timestamps should NOT have been called with is_main_sleep=True
        for call in mw._create_sleep_period_from_timestamps.call_args_list:
            _, kwargs = call
            assert kwargs.get("is_main_sleep") is not True, (
                "Main sleep should not be created on a no-sleep day"
            )

    def test_bulk_row_creates_main_sleep_on_normal_day(
        self,
        normal_store: UIStore,
        diary_entry_full: DiaryEntry,
    ) -> None:
        """Bulk row import creates main sleep on a normal day."""
        coordinator, mw, *_ = _build_coordinator(normal_store, [diary_entry_full])
        main_period = SleepPeriod(
            onset_timestamp=1718492400.0,
            offset_timestamp=1718521200.0,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )
        mw._create_sleep_period_from_timestamps.return_value = main_period

        # Pre-load empty markers so update_classifications doesn't fail
        normal_store.dispatch(Actions.sleep_markers_changed(DailySleepMarkers()))

        coordinator.set_markers_from_diary_row(0)

        # Should have called _create_sleep_period_from_timestamps with is_main_sleep=True
        main_sleep_calls = [
            c for c in mw._create_sleep_period_from_timestamps.call_args_list
            if c[1].get("is_main_sleep") is True or (len(c[0]) >= 3 and c[0][2] is True)
        ]
        assert len(main_sleep_calls) >= 1, "Main sleep should be created on a normal day"


# ===================================================================
# Integration: verify store state transitions
# ===================================================================


class TestNoSleepStateTransitions:
    """Verify that is_no_sleep_marked state transitions work correctly."""

    def test_markers_loaded_sets_no_sleep(self, store: UIStore) -> None:
        """markers_loaded with is_no_sleep=True sets the flag."""
        store.dispatch(Actions.markers_loaded(sleep=None, nonwear=None, is_no_sleep=True))
        assert store.state.is_no_sleep_marked is True

    def test_markers_loaded_clears_no_sleep(self, store: UIStore) -> None:
        """markers_loaded with is_no_sleep=False clears the flag."""
        store.dispatch(Actions.markers_loaded(sleep=None, nonwear=None, is_no_sleep=True))
        store.dispatch(Actions.markers_loaded(sleep=None, nonwear=None, is_no_sleep=False))
        assert store.state.is_no_sleep_marked is False

    def test_markers_saved_clears_no_sleep_when_sleep_dirty(self, store: UIStore) -> None:
        """Saving sleep markers clears the no-sleep flag (saving sleep implies there IS sleep)."""
        store.dispatch(Actions.markers_loaded(sleep=None, nonwear=None, is_no_sleep=True))
        assert store.state.is_no_sleep_marked is True

        # User places sleep markers → sleep_markers_dirty becomes True
        from sleep_scoring_app.core.dataclasses_markers import DailySleepMarkers

        store.dispatch(Actions.sleep_markers_changed(DailySleepMarkers()))
        assert store.state.sleep_markers_dirty is True

        store.dispatch(Actions.markers_saved())
        assert store.state.is_no_sleep_marked is False

    def test_markers_saved_preserves_no_sleep_when_only_nonwear_dirty(self, store: UIStore) -> None:
        """Saving only nonwear markers preserves the no-sleep flag."""
        store.dispatch(Actions.markers_loaded(sleep=None, nonwear=None, is_no_sleep=True))
        assert store.state.is_no_sleep_marked is True

        # Only nonwear changed → sleep_markers_dirty stays False
        store.dispatch(Actions.nonwear_markers_changed(None))
        assert store.state.sleep_markers_dirty is False

        store.dispatch(Actions.markers_saved())
        assert store.state.is_no_sleep_marked is True

    def test_markers_cleared_clears_no_sleep(self, store: UIStore) -> None:
        """Clearing markers clears the no-sleep flag."""
        store.dispatch(Actions.markers_loaded(sleep=None, nonwear=None, is_no_sleep=True))
        store.dispatch(Actions.markers_cleared())
        assert store.state.is_no_sleep_marked is False
