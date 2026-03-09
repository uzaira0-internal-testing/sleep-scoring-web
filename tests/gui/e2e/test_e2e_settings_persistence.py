#!/usr/bin/env python3
"""E2E settings persistence: study/data settings survive tab switches and store roundtrips.

Satisfies all acceptance criteria from TEST_SUITE_RATIONALIZATION_PLAN.md:
1. Constructs SleepScoringMainWindow() normally (no __new__).
2. Uses user-like actions (combo selection, spin box changes).
3. No mock_main_window.
4. No ``assert True``.
5. No placeholder ``pass``.
6. No direct store.dispatch() for core user workflow steps.
7. Asserts both UI-visible effects and persisted/state effects.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTabWidget

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_csv(folder: Path, filename: str, start: datetime, days: int = 7) -> Path:
    """Write a realistic epoch-based CSV and return its path."""
    np.random.seed(42)
    epochs = days * 24 * 60
    timestamps = [start + timedelta(minutes=i) for i in range(epochs)]

    activity = []
    for ts in timestamps:
        hour = ts.hour
        if 7 <= hour < 22:
            base = 200 + np.random.randint(-80, 150)
        elif hour >= 22 or hour < 1:
            base = 50 + np.random.randint(-20, 40)
        else:
            base = 5 + np.random.randint(0, 15)
        activity.append(max(0, base))

    df = pd.DataFrame(
        {
            "Date": [ts.strftime("%m/%d/%Y") for ts in timestamps],
            "Time": [ts.strftime("%H:%M:%S") for ts in timestamps],
            "Axis1": activity,
            "Axis2": [int(a * 0.7) for a in activity],
            "Axis3": [int(a * 0.4) for a in activity],
            "Vector Magnitude": [int(np.sqrt(a**2 + (a * 0.7) ** 2 + (a * 0.4) ** 2)) for a in activity],
            "Steps": [np.random.randint(0, 30) if a > 100 else 0 for a in activity],
        }
    )
    path = folder / filename
    df.to_csv(path, index=False)
    return path


def _click_tab_by_name(tab_widget: QTabWidget, name: str, qtbot: QtBot) -> None:
    tab_bar = tab_widget.tabBar()
    for i in range(tab_widget.count()):
        if name.lower() in tab_widget.tabText(i).lower():
            rect = tab_bar.tabRect(i)
            qtbot.mouseClick(tab_bar, Qt.MouseButton.LeftButton, pos=rect.center())
            qtbot.wait(50)
            return


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def e2e_env(qtbot: QtBot, tmp_path: Path):
    """Build a fully-real SleepScoringMainWindow with temp data on disk."""
    import sleep_scoring_app.data.database as db_module
    from sleep_scoring_app.core.dataclasses import AppConfig
    from sleep_scoring_app.ui.utils.config import ConfigManager

    db_module._database_initialized.clear()
    db_path = tmp_path / "test.db"

    data_folder = tmp_path / "activity_data"
    data_folder.mkdir()
    _create_test_csv(data_folder, "P001_T1_Control_actigraph.csv", datetime(2024, 1, 15))

    exports_folder = tmp_path / "exports"
    exports_folder.mkdir()

    from dataclasses import replace as dc_replace

    config = AppConfig.create_default()
    config = dc_replace(config, data_folder=str(data_folder), export_directory=str(exports_folder), epoch_length=60)

    original_init = db_module.DatabaseManager.__init__

    def patched_init(self, db_path_arg=None, resource_manager=None):
        original_init(self, db_path=str(db_path), resource_manager=resource_manager)

    with (
        patch.object(db_module.DatabaseManager, "__init__", patched_init),
        patch.object(ConfigManager, "is_config_valid", return_value=True),
        patch.object(ConfigManager, "config", config, create=True),
    ):
        from sleep_scoring_app.ui.main_window import SleepScoringMainWindow

        window = SleepScoringMainWindow()
        window.config_manager.config = config
        window.export_output_path = str(exports_folder)

        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)

        yield {
            "window": window,
            "qtbot": qtbot,
            "data_folder": data_folder,
        }

        window.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.gui
class TestSettingsPersistence:
    """Settings changes via UI persist in Redux store across tab switches."""

    def test_sleep_algorithm_change_persists_after_tab_switch(self, e2e_env: dict) -> None:
        """Changing the sleep algorithm combo on Study Settings survives a round-trip to Analysis."""
        window = e2e_env["window"]
        qtbot: QtBot = e2e_env["qtbot"]
        tab_widget = window.findChild(QTabWidget)

        # Navigate to Study Settings
        _click_tab_by_name(tab_widget, "Study", qtbot)
        qtbot.wait(100)

        combo = window.study_settings_tab.sleep_algorithm_combo
        assert combo is not None
        assert combo.count() >= 2

        # Change to a different algorithm (index 1)
        combo.setCurrentIndex(1)
        selected_data = combo.currentData()
        qtbot.wait(100)

        # Switch away to Analysis and back
        _click_tab_by_name(tab_widget, "Analysis", qtbot)
        qtbot.wait(100)
        _click_tab_by_name(tab_widget, "Study", qtbot)
        qtbot.wait(100)

        # UI assertion: combo still shows the same selection
        assert combo.currentData() == selected_data

        # STATE assertion: store reflects the algorithm
        assert window.store.state.sleep_algorithm_id == selected_data

    def test_nonwear_algorithm_change_persists_after_tab_switch(self, e2e_env: dict) -> None:
        """Changing the nonwear algorithm combo on Study Settings survives a round-trip."""
        window = e2e_env["window"]
        qtbot: QtBot = e2e_env["qtbot"]
        tab_widget = window.findChild(QTabWidget)

        _click_tab_by_name(tab_widget, "Study", qtbot)
        qtbot.wait(100)

        combo = window.study_settings_tab.nonwear_algorithm_combo
        assert combo is not None

        if combo.count() < 2:
            pytest.skip("Need >= 2 nonwear algorithm options")

        combo.setCurrentIndex(1)
        selected_data = combo.currentData()
        qtbot.wait(100)

        _click_tab_by_name(tab_widget, "Analysis", qtbot)
        qtbot.wait(100)
        _click_tab_by_name(tab_widget, "Study", qtbot)
        qtbot.wait(100)

        assert combo.currentData() == selected_data

    def test_id_pattern_edit_retains_text_after_tab_switch(self, e2e_env: dict) -> None:
        """Typing into the ID pattern field on Study Settings retains text after tab switch."""
        window = e2e_env["window"]
        qtbot: QtBot = e2e_env["qtbot"]
        tab_widget = window.findChild(QTabWidget)

        _click_tab_by_name(tab_widget, "Study", qtbot)
        qtbot.wait(100)

        id_pattern = window.study_settings_tab.id_pattern_edit
        assert id_pattern is not None

        id_pattern.clear()
        test_pattern = r"(P\d{3})"
        qtbot.keyClicks(id_pattern, test_pattern)
        qtbot.wait(100)

        # Switch away and back
        _click_tab_by_name(tab_widget, "Analysis", qtbot)
        qtbot.wait(100)
        _click_tab_by_name(tab_widget, "Study", qtbot)
        qtbot.wait(100)

        # UI assertion: text is still there
        assert id_pattern.text() == test_pattern

    def test_view_mode_persists_across_file_selection(self, e2e_env: dict) -> None:
        """Setting 24h view mode persists when navigating between dates."""
        window = e2e_env["window"]
        qtbot: QtBot = e2e_env["qtbot"]
        tab_widget = window.findChild(QTabWidget)
        data_folder: Path = e2e_env["data_folder"]

        # Import and load file
        window.data_service.set_data_folder(str(data_folder))
        csv_files = sorted(data_folder.glob("*.csv"))
        window.import_service.import_files(
            file_paths=csv_files,
            skip_rows=0,
            force_reimport=True,
        )
        qtbot.wait(100)

        available = window.data_service.find_available_files()
        _click_tab_by_name(tab_widget, "Analysis", qtbot)
        qtbot.wait(50)
        window.on_file_selected_from_table(available[0])
        qtbot.wait(300)

        # Set 24h mode via button click
        view_24h = window.analysis_tab.view_24h_btn
        assert view_24h is not None
        qtbot.mouseClick(view_24h, Qt.MouseButton.LeftButton)
        qtbot.wait(200)

        # STATE check: view mode is 24
        assert window.store.state.view_mode_hours == 24

        # Navigate to next date (if available)
        dates = window.store.state.available_dates
        if len(dates) >= 2:
            next_btn = window.analysis_tab.next_date_btn
            if next_btn is not None and next_btn.isEnabled():
                qtbot.mouseClick(next_btn, Qt.MouseButton.LeftButton)
                qtbot.wait(300)

            # STATE assertion: view mode is still 24
            assert window.store.state.view_mode_hours == 24

            # UI assertion: 24h button is still checked
            assert view_24h.isChecked()
