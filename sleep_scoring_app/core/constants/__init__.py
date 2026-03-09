"""
Constants for Sleep Scoring Application.

This package provides centralized definitions for all string enums,
numeric constants, and configuration values used throughout the application.

The constants are organized into domain-specific modules:
- algorithms: Algorithm-related constants (sleep scoring, nonwear detection)
- database: Database schema constants (tables, columns)
- io: Import/export and file system constants
- ui: User interface constants (styling, messages, configuration)

All constants are re-exported from this __init__.py for backward compatibility.
You can import directly from the submodules for more specific imports:

    # Full backward-compatible import
    from sleep_scoring_app.core.constants import AlgorithmType, DatabaseColumn

    # Domain-specific import
    from sleep_scoring_app.core.constants.algorithms import AlgorithmType
    from sleep_scoring_app.core.constants.database import DatabaseColumn
"""

# Algorithm constants
from .algorithms import (
    AlgorithmOutputColumn,
    AlgorithmParams,
    AlgorithmResult,
    AlgorithmType,
    MarkerCategory,
    MarkerEndpoint,
    MarkerLimits,
    MarkerPlacementState,
    MarkerType,
    NonwearAlgorithm,
    NonwearDataSource,
    NonwearSourceFilter,
    SadehDataSource,
    SelectionState,
    SleepMarkerEndpoint,
    SleepPeriodDetectorType,
    SleepStatusValue,
    StudyDataParadigm,
)

# Database constants
from .database import (
    DatabaseColumn,
    DatabaseTable,
)

# I/O constants
from .io import (
    ActivityColumn,
    ActivityDataPreference,
    DataSourceType,
    DefaultColumn,
    DeleteStatus,
    DevicePreset,
    DiaryFileType,
    DiaryPeriodKey,
    DirectoryName,
    ExportColumn,
    FileExtension,
    FileName,
    FileSourceType,
    ImportStatus,
    MetadataKey,
    ParticipantGroup,
    ParticipantTimepoint,
    RegexPattern,
    get_backup_filename,
    sanitize_filename_component,
)

# UI constants
from .ui import (
    AlgorithmHelpText,
    AlgorithmTooltip,
    AppArgument,
    ArrowColorKey,
    ButtonStyle,
    ButtonText,
    ConfigDefaults,
    ConfigKey,
    ConfirmationMessage,
    DebugMessage,
    DiaryTableColumn,
    EditMode,
    ErrorMessage,
    ExportUIGroup,
    FeatureFlags,
    FileDialogText,
    GroupBoxTitle,
    InfoMessage,
    LabelStyle,
    LabelText,
    MarkerLabel,
    MemoryConstants,
    MenuText,
    MessageType,
    ParadigmInfoText,
    ParadigmLabel,
    ParadigmStyle,
    ParadigmTooltip,
    ParadigmWarning,
    PeriodKey,
    PlotConstants,
    PyQtGraphConfig,
    SettingsSection,
    StatusMessage,
    SuccessMessage,
    TableColumn,
    TableDimensions,
    TabName,
    TimeConstants,
    TimeFormat,
    TooltipText,
    UIColors,
    ViewHours,
    ViewMode,
    WindowTitle,
)

__all__ = [
    # I/O constants
    "ActivityColumn",
    "ActivityDataPreference",
    # UI constants
    "AlgorithmHelpText",
    # Algorithm constants
    "AlgorithmOutputColumn",
    "AlgorithmParams",
    "AlgorithmResult",
    "AlgorithmTooltip",
    "AlgorithmType",
    "AppArgument",
    "ArrowColorKey",
    "ButtonStyle",
    "ButtonText",
    "ConfigDefaults",
    "ConfigKey",
    "ConfirmationMessage",
    "DataSourceType",
    # Database constants
    "DatabaseColumn",
    "DatabaseTable",
    "DebugMessage",
    "DefaultColumn",
    "DeleteStatus",
    "DevicePreset",
    "DiaryFileType",
    "DiaryPeriodKey",
    "DiaryTableColumn",
    "DirectoryName",
    "EditMode",
    "ErrorMessage",
    "ExportColumn",
    "ExportUIGroup",
    "FeatureFlags",
    "FileDialogText",
    "FileExtension",
    "FileName",
    "FileSourceType",
    "GroupBoxTitle",
    "ImportStatus",
    "InfoMessage",
    "LabelStyle",
    "LabelText",
    "MarkerCategory",
    "MarkerEndpoint",
    "MarkerLabel",
    "MarkerLimits",
    "MarkerPlacementState",
    "MarkerType",
    "MemoryConstants",
    "MenuText",
    "MessageType",
    "MetadataKey",
    "NonwearAlgorithm",
    "NonwearDataSource",
    "NonwearSourceFilter",
    "ParadigmInfoText",
    "ParadigmLabel",
    "ParadigmStyle",
    "ParadigmTooltip",
    "ParadigmWarning",
    "ParticipantGroup",
    "ParticipantTimepoint",
    "PeriodKey",
    "PlotConstants",
    "PyQtGraphConfig",
    "RegexPattern",
    "SadehDataSource",
    "SelectionState",
    "SettingsSection",
    "SleepMarkerEndpoint",
    "SleepPeriodDetectorType",
    "SleepStatusValue",
    "StatusMessage",
    "StudyDataParadigm",
    "SuccessMessage",
    "TabName",
    "TableColumn",
    "TableDimensions",
    "TimeConstants",
    "TimeFormat",
    "TooltipText",
    "UIColors",
    "ViewHours",
    "ViewMode",
    "WindowTitle",
    "get_backup_filename",
    "sanitize_filename_component",
]
