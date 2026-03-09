"""Tests for TimeFieldCoordinator — ensures time field parsing, overnight
handling, and update callbacks work correctly.

Uses mock QLineEdit and QLabel widgets; real UIStore.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QLabel, QLineEdit

from sleep_scoring_app.ui.store import UIStore


@pytest.fixture
def store() -> UIStore:
    return UIStore()


@pytest.fixture
def mock_widgets(qtbot):
    """Real QLineEdit/QLabel widgets (required because TimeFieldCoordinator is a QObject)."""
    onset = QLineEdit()
    offset = QLineEdit()
    duration_label = QLabel()
    qtbot.addWidget(onset)
    qtbot.addWidget(offset)
    qtbot.addWidget(duration_label)
    return {"onset": onset, "offset": offset, "duration_label": duration_label}


def _make_coordinator(store, widgets, callback=None):
    from sleep_scoring_app.ui.coordinators.time_field_coordinator import (
        TimeFieldCoordinator,
    )

    return TimeFieldCoordinator(
        store=store,
        onset_time_input=widgets["onset"],
        offset_time_input=widgets["offset"],
        total_duration_label=widgets["duration_label"],
        update_callback=callback or MagicMock(),
    )


class TestTimeFieldCoordinatorInit:
    """Coordinator connects signals on init."""

    def test_creates_without_error(self, store: UIStore, mock_widgets: dict) -> None:
        """Coordinator initializes successfully with real widgets."""
        coordinator = _make_coordinator(store, mock_widgets)
        assert coordinator is not None

    def test_stores_references(self, store: UIStore, mock_widgets: dict) -> None:
        """Coordinator stores onset/offset input references."""
        coordinator = _make_coordinator(store, mock_widgets)
        assert coordinator.onset_time_input is mock_widgets["onset"]
        assert coordinator.offset_time_input is mock_widgets["offset"]

    def test_has_event_filters(self, store: UIStore, mock_widgets: dict) -> None:
        """Coordinator installs event filters on both fields."""
        coordinator = _make_coordinator(store, mock_widgets)
        assert coordinator.onset_filter is not None
        assert coordinator.offset_filter is not None


class TestTimeFieldCoordinatorUpdate:
    """Trigger update calls the callback."""

    def test_trigger_update_calls_callback(self, store: UIStore, mock_widgets: dict) -> None:
        callback = MagicMock()
        coordinator = _make_coordinator(store, mock_widgets, callback=callback)

        coordinator.trigger_update()

        callback.assert_called_once()

    def test_return_pressed_triggers_update(self, store: UIStore, mock_widgets: dict) -> None:
        callback = MagicMock()
        coordinator = _make_coordinator(store, mock_widgets, callback=callback)

        coordinator.on_time_field_return_pressed()

        callback.assert_called_once()


class TestTimeFieldCoordinatorDuration:
    """Duration label updated from time inputs."""

    def test_both_empty_clears_label(self, store: UIStore, mock_widgets: dict) -> None:
        coordinator = _make_coordinator(store, mock_widgets)

        coordinator.on_time_input_changed()

        assert mock_widgets["duration_label"].text() == ""

    def test_valid_same_day_shows_duration(self, store: UIStore, mock_widgets: dict) -> None:
        """14:00 to 16:00 = 2.0 hours."""
        mock_widgets["onset"].setText("14:00")
        mock_widgets["offset"].setText("16:00")
        coordinator = _make_coordinator(store, mock_widgets)

        coordinator.on_time_input_changed()

        assert mock_widgets["duration_label"].text() == "Total Duration: 2.0 hours"

    def test_overnight_sleep_shows_correct_duration(self, store: UIStore, mock_widgets: dict) -> None:
        """22:00 to 06:00 = 8.0 hours (overnight)."""
        mock_widgets["onset"].setText("22:00")
        mock_widgets["offset"].setText("06:00")
        coordinator = _make_coordinator(store, mock_widgets)

        coordinator.on_time_input_changed()

        assert mock_widgets["duration_label"].text() == "Total Duration: 8.0 hours"

    def test_invalid_format_clears_label(self, store: UIStore, mock_widgets: dict) -> None:
        """Invalid time format clears the duration label."""
        mock_widgets["onset"].setText("not:a:time")
        mock_widgets["offset"].setText("invalid")
        coordinator = _make_coordinator(store, mock_widgets)

        coordinator.on_time_input_changed()

        assert mock_widgets["duration_label"].text() == ""

    def test_one_field_empty_clears_label(self, store: UIStore, mock_widgets: dict) -> None:
        """Only one field filled clears the duration label."""
        mock_widgets["onset"].setText("22:00")
        # offset stays empty
        coordinator = _make_coordinator(store, mock_widgets)

        coordinator.on_time_input_changed()

        assert mock_widgets["duration_label"].text() == ""
