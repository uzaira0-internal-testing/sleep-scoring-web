"""
Store Connectors - Connect UI components to the Redux-style store.

Each connector is responsible for:
1. Subscribing to relevant state changes
2. Updating the component when state changes
3. Handling cleanup (unsubscribe) when component is destroyed

Components own their update logic - the store just notifies them of changes.

ARCHITECTURE:
- ALL state (file/date selection, view mode, window geometry, markers) -> UIStore (Redux pattern)
- Persistence -> QSettings (synced from store via QSettingsPersistenceConnector)

All connectors subscribe to Redux store state changes - NO POLLING.

Usage:
    # In main_window.py after creating store:
    self.store = UIStore()
    connect_all_components(self.store, self)
"""

from .activity import ActivityDataConnector
from .error import ErrorNotificationConnector
from .file import FileListConnector, FileManagementConnector, FileSelectionLabelConnector, FileTableConnector
from .manager import SideEffectConnector, StoreConnectorManager, connect_all_components
from .marker import AdjacentMarkersConnector, AutoSaveConnector, MarkerModeConnector, MarkersConnector
from .navigation import ConsensusCheckboxConnector, DateDropdownConnector, NavigationConnector, NavigationGuardConnector, ViewModeConnector
from .persistence import ConfigPersistenceConnector, WindowGeometryConnector
from .plot import PlotArrowsConnector, PlotClickConnector, PlotDataConnector
from .save_status import SaveButtonConnector, StatusConnector
from .settings import AlgorithmConfigConnector, AlgorithmDropdownConnector, CacheConnector, DataSettingsDispatchConnector, StudySettingsConnector
from .table import DiaryTableConnector, PopOutConnector, SideTableConnector
from .ui_controls import AnalysisTabConnector, SignalsConnector, TimeFieldConnector, UIControlsConnector

__all__ = [
    # activity.py
    "ActivityDataConnector",
    # marker.py
    "AdjacentMarkersConnector",
    # settings.py
    "AlgorithmConfigConnector",
    "AlgorithmDropdownConnector",
    # ui_controls.py
    "AnalysisTabConnector",
    "AutoSaveConnector",
    "CacheConnector",
    # persistence.py
    "ConfigPersistenceConnector",
    # navigation.py
    "ConsensusCheckboxConnector",
    # settings.py (DataSettings)
    "DataSettingsDispatchConnector",
    "DateDropdownConnector",
    # table.py
    "DiaryTableConnector",
    # error.py
    "ErrorNotificationConnector",
    # file.py
    "FileListConnector",
    "FileManagementConnector",
    "FileSelectionLabelConnector",
    "FileTableConnector",
    "MarkerModeConnector",
    "MarkersConnector",
    "NavigationConnector",
    "NavigationGuardConnector",
    # plot.py
    "PlotArrowsConnector",
    "PlotClickConnector",
    "PlotDataConnector",
    "PopOutConnector",
    # save_status.py
    "SaveButtonConnector",
    # manager.py
    "SideEffectConnector",
    "SideTableConnector",
    "SignalsConnector",
    "StatusConnector",
    "StoreConnectorManager",
    "StudySettingsConnector",
    "TimeFieldConnector",
    "UIControlsConnector",
    "ViewModeConnector",
    "WindowGeometryConnector",
    "connect_all_components",
]
