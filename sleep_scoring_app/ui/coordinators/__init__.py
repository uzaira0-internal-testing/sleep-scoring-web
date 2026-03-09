"""Qt-based coordinator components."""

from sleep_scoring_app.ui.coordinators.analysis_dialog_coordinator import AnalysisDialogCoordinator
from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
    AutosaveConfig,
    AutosaveCoordinator,
    PendingChangeType,
)
from sleep_scoring_app.ui.coordinators.diary_integration_coordinator import DiaryIntegrationCoordinator
from sleep_scoring_app.ui.coordinators.diary_table_connector import DiaryTableConnector
from sleep_scoring_app.ui.coordinators.import_ui_coordinator import ImportUICoordinator
from sleep_scoring_app.ui.coordinators.seamless_source_switcher import SeamlessSourceSwitcher
from sleep_scoring_app.ui.coordinators.time_field_coordinator import TimeFieldCoordinator
from sleep_scoring_app.ui.coordinators.ui_state_coordinator import UIStateCoordinator

__all__ = [
    "AnalysisDialogCoordinator",
    "AutosaveConfig",
    "AutosaveCoordinator",
    "DiaryIntegrationCoordinator",
    "DiaryTableConnector",
    "ImportUICoordinator",
    "PendingChangeType",
    "SeamlessSourceSwitcher",
    "TimeFieldCoordinator",
    "UIStateCoordinator",
]
