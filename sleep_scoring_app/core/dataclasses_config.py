#!/usr/bin/env python3
"""Configuration-related dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sleep_scoring_app.core.constants import (
    ActivityDataPreference,
    AlgorithmType,
    ConfigKey,
    DataSourceType,
    NonwearAlgorithm,
    SleepPeriodDetectorType,
    StudyDataParadigm,
)


@dataclass(frozen=True)
class ColumnMapping:
    """CSV column mapping configuration."""

    # Date/time columns
    date_column: str | None = None
    time_column: str | None = None
    datetime_column: str | None = None

    # Activity columns
    activity_column: str | None = None
    axis_x_column: str | None = None
    axis_z_column: str | None = None
    vector_magnitude_column: str | None = None

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for config storage."""
        result = {}
        if self.date_column:
            result[ConfigKey.DATE_COLUMN] = self.date_column
        if self.time_column:
            result[ConfigKey.TIME_COLUMN] = self.time_column
        if self.datetime_column:
            result[ConfigKey.DATETIME_COLUMN] = self.datetime_column
        if self.activity_column:
            result[ConfigKey.ACTIVITY_COLUMN] = self.activity_column
        if self.axis_x_column:
            result[ConfigKey.AXIS_X_COLUMN] = self.axis_x_column
        if self.axis_z_column:
            result[ConfigKey.AXIS_Z_COLUMN] = self.axis_z_column
        if self.vector_magnitude_column:
            result[ConfigKey.VECTOR_MAGNITUDE_COLUMN] = self.vector_magnitude_column
        return result


@dataclass(frozen=True)
class AppConfig:
    """Application configuration settings with hardcoded defaults."""

    # Directory settings (configurable via QSettings)
    data_folder: str = ""
    export_directory: str = ""
    import_activity_directory: str = ""
    import_nonwear_directory: str = ""
    diary_import_directory: str = ""
    actilife_import_directory: str = ""

    # Hardcoded data settings (no longer configurable)
    data_directory: str = ""  # Directory path for ActiLife import browsing
    epoch_length: int = 60
    skip_rows: int = 10
    use_database: bool = True  # Prefer imported database files over CSV files

    # Hardcoded column mappings
    column_mapping: ColumnMapping = field(default_factory=ColumnMapping)
    preferred_activity_column: ActivityDataPreference = ActivityDataPreference.AXIS_Y
    choi_activity_column: ActivityDataPreference = ActivityDataPreference.AXIS_Y

    # Hardcoded window settings
    window_width: int = 1200
    window_height: int = 800

    # Recently used files (stored in QSettings)
    recent_files: list[str] = field(default_factory=list)

    # Hardcoded export settings
    export_columns: list[str] = field(default_factory=list)
    export_grouping: int = 0  # 0=all, 1=participant, 2=group, 3=timepoint
    include_headers: bool = True
    include_metadata: bool = True
    include_config_in_metadata: bool = True  # Include config settings in CSV metadata header
    export_config_sidecar: bool = True  # Export config as separate .config.csv file
    export_nonwear_separate: bool = True  # Export nonwear markers to separate file

    # Hardcoded import settings
    import_new_files_only: bool = True
    show_import_progress_details: bool = False
    max_import_file_size_mb: int = 100
    nwt_data_folder: str = ""  # NWT sensor data folder
    import_skip_rows: int = 10
    import_force_reimport: bool = False

    # Hardcoded study days settings
    study_days_use_database: bool = True
    study_days_file: str = ""  # Direct load file path
    study_days_import_file: str = ""  # Import to database file path

    # Hardcoded diary settings
    diary_use_database: bool = True
    diary_skip_rows: int = 1  # Diaries typically have fewer header rows

    # Hardcoded ActiLife Sadeh settings
    use_actilife_sadeh: bool = False  # Enable ActiLife Sadeh data usage
    actilife_skip_rows: int = 3  # Header rows to skip in ActiLife CSV files
    actilife_prefer_over_calculated: bool = True  # Prefer ActiLife over calculated when available
    actilife_validate_against_calculated: bool = False  # Validate ActiLife against calculated

    # Hardcoded study settings - defaults match DEMO data patterns
    study_default_group: str = "G1"
    study_default_timepoint: str = "T1"
    study_valid_groups: list[str] = field(default_factory=lambda: ["G1", "DEMO"])
    study_valid_timepoints: list[str] = field(default_factory=lambda: ["T1", "T2", "T3"])
    study_unknown_value: str = "Unknown"
    study_group_pattern: str = r"(G1|DEMO)"
    study_timepoint_pattern: str = r"(T[123])"
    study_participant_id_patterns: list[str] = field(default_factory=lambda: [r"(DEMO-\d{3})"])

    # Device/Format Configuration
    device_preset: str = "actigraph"
    custom_date_column: str = ""
    custom_time_column: str = ""
    custom_activity_column: str = ""  # Primary activity column (for display/general use)
    datetime_combined: bool = False

    # Custom axis column mappings (for Generic CSV)
    # User specifies which CSV column maps to each axis
    custom_axis_y_column: str = ""  # Y-axis (vertical) - Required for Sadeh algorithm
    custom_axis_x_column: str = ""  # X-axis (lateral)
    custom_axis_z_column: str = ""  # Z-axis (forward)
    custom_vector_magnitude_column: str = ""  # Recommended for Choi algorithm

    # Algorithm Configuration
    night_start_hour: int = 22
    night_end_hour: int = 7
    max_sleep_periods: int = 4  # 1 main sleep + up to 3 naps (hardcoded, not configurable)
    choi_axis: str = ActivityDataPreference.VECTOR_MAGNITUDE

    # Data Paradigm Selection (controls file types and available algorithms)
    data_paradigm: str = StudyDataParadigm.EPOCH_BASED  # StudyDataParadigm enum value

    # Sleep Scoring Algorithm Selection (DI pattern)
    sleep_algorithm_id: str = AlgorithmType.SADEH_1994_ACTILIFE  # Algorithm identifier for factory

    # Onset/Offset Rule Selection (DI pattern)
    onset_offset_rule_id: str = SleepPeriodDetectorType.CONSECUTIVE_ONSET3S_OFFSET5S  # Rule identifier for factory

    # Raw Data Pipeline (gt3x) - for future use
    data_source_type: str = DataSourceType.CSV
    gt3x_folder: str = ""

    # Data Source Configuration (DI pattern)
    data_source_type_id: str = DataSourceType.CSV  # Factory identifier for data source loader
    csv_skip_rows: int = 10  # CSV-specific: rows to skip
    gt3x_epoch_length: int = 60  # GT3X-specific: epoch length in seconds
    gt3x_return_raw: bool = False  # GT3X-specific: return raw acceleration data

    # Nonwear Detection Algorithm Selection (DI pattern)
    nonwear_algorithm_id: str = NonwearAlgorithm.CHOI_2011  # Algorithm identifier for factory

    # Automatic Processing
    auto_place_diary_markers: bool = True
    auto_place_apply_rules_until_convergence: bool = True
    auto_detect_nonwear_overlap: bool = True
    auto_scroll_to_unmarked: bool = True
    auto_advance_after_save: bool = False
    auto_populate_nap_markers: bool = True
    auto_save_markers: bool = True  # Auto-save markers when navigating away

    # Diary Integration Settings
    diary_auto_adjust_early_morning: bool = False  # If True, auto-adjust times 00:00-06:00 to next day (OFF by default)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON storage (only directory paths)."""
        return {
            ConfigKey.DATA_FOLDER: self.data_folder,
            "export_directory": self.export_directory,
            "import_activity_directory": self.import_activity_directory,
            "import_nonwear_directory": self.import_nonwear_directory,
            "diary_import_directory": self.diary_import_directory,
            "actilife_import_directory": self.actilife_import_directory,
        }

    def to_full_dict(self, include_paths: bool = False) -> dict[str, Any]:
        """
        Convert to comprehensive dictionary for config export/sharing.

        This focuses on RESEARCH-RELEVANT settings that affect reproducibility:
        - Study identification patterns (how participants are identified)
        - Algorithm parameters (how sleep is scored)
        - Data processing settings (how data is interpreted)

        UI preferences (colors, window size) are NOT included as they don't
        affect research outcomes.

        Args:
            include_paths: If True, include directory paths (may contain sensitive info).
                          If False, exclude paths for safe sharing.

        Returns:
            Complete configuration dictionary suitable for export.

        """
        # Import app version from package
        from sleep_scoring_app import __version__ as app_version

        # Config schema version - increment when config structure changes
        # This is separate from app version to track config compatibility
        CONFIG_SCHEMA_VERSION = "1.0.0"

        config_dict = {
            # Version info for compatibility checking
            "config_schema_version": CONFIG_SCHEMA_VERSION,  # Schema version for config structure
            "app_version": app_version,  # App version that created this config
            "app_name": "SleepScoringApp",
            "study": {
                # Regex patterns for extracting info from filenames
                "participant_id_patterns": self.study_participant_id_patterns,
                "timepoint_pattern": self.study_timepoint_pattern,
                "group_pattern": self.study_group_pattern,
                # Valid values for categorical fields
                "valid_groups": self.study_valid_groups,
                "valid_timepoints": self.study_valid_timepoints,
                # Default values when extraction fails
                "default_group": self.study_default_group,
                "default_timepoint": self.study_default_timepoint,
                "unknown_value": self.study_unknown_value,
            },
            "algorithm": {
                # Sleep scoring algorithm selection (DI pattern)
                "sleep_algorithm_id": self.sleep_algorithm_id,  # e.g., "sadeh_1994_actilife", "sadeh_1994_original", "cole_kripke_1992"
                # Onset/offset rule selection (DI pattern)
                "onset_offset_rule_id": self.onset_offset_rule_id,  # e.g., "consecutive_3_5", "tudor_locke_2014"
                # Night definition for sleep period detection
                "night_start_hour": self.night_start_hour,
                "night_end_hour": self.night_end_hour,
                # Nonwear detection algorithm (DI pattern)
                "choi_axis": self.choi_axis,  # Which axis to use for nonwear detection
                "nonwear_algorithm_id": self.nonwear_algorithm_id,
            },
            "data_processing": {
                "epoch_length": self.epoch_length,
                "skip_rows": self.skip_rows,  # Header rows in CSV files
                "preferred_activity_column": self.preferred_activity_column,
                "device_preset": self.device_preset,
            },
        }

        # Optionally include paths (for full backup, not for sharing)
        if include_paths:
            config_dict["paths"] = {
                "data_folder": self.data_folder,
                "export_directory": self.export_directory,
                "import_activity_directory": self.import_activity_directory,
                "import_nonwear_directory": self.import_nonwear_directory,
                "diary_import_directory": self.diary_import_directory,
                "actilife_import_directory": self.actilife_import_directory,
            }

        return config_dict

    def to_flat_dict(self) -> dict[str, Any]:
        """
        Convert to flat key-value dictionary for CSV sidecar export.

        Returns:
            Flat dictionary with dot-notation keys for CSV export.

        """
        full_dict = self.to_full_dict(include_paths=False)
        flat = {}

        def flatten(obj: dict | list | Any, prefix: str = "") -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_key = f"{prefix}.{key}" if prefix else key
                    flatten(value, new_key)
            elif isinstance(obj, list):
                flat[prefix] = "|".join(str(v) for v in obj) if obj else ""
            else:
                flat[prefix] = str(obj) if obj is not None else ""

        flatten(full_dict)
        return flat

    @classmethod
    def from_full_dict(cls, data: dict[str, Any]) -> AppConfig:
        """
        Create AppConfig from a full config dictionary (for import).

        Loads RESEARCH-RELEVANT settings only:
        - Study identification patterns (participant ID, group, timepoint extraction)
        - Algorithm parameters (Sadeh variant, night hours, Choi settings)
        - Data processing settings (epoch length, skip rows)

        Args:
            data: Configuration dictionary from to_full_dict() or loaded from file.

        Returns:
            New AppConfig instance with loaded settings.

        """
        from dataclasses import replace

        config = cls.create_default()
        overrides: dict[str, Any] = {}

        # Study identification settings (Critical for reproducibility)
        if "study" in data:
            st = data["study"]
            study_map = {
                "participant_id_patterns": "study_participant_id_patterns",
                "timepoint_pattern": "study_timepoint_pattern",
                "group_pattern": "study_group_pattern",
                "valid_groups": "study_valid_groups",
                "valid_timepoints": "study_valid_timepoints",
                "default_group": "study_default_group",
                "default_timepoint": "study_default_timepoint",
                "unknown_value": "study_unknown_value",
            }
            for src_key, dst_attr in study_map.items():
                if src_key in st:
                    overrides[dst_attr] = st[src_key]

        # Algorithm settings (Critical for reproducibility)
        if "algorithm" in data:
            alg = data["algorithm"]
            for key in ("sleep_algorithm_id", "onset_offset_rule_id", "night_start_hour", "night_end_hour", "choi_axis", "nonwear_algorithm_id"):
                if key in alg:
                    overrides[key] = alg[key]

        # Data processing settings
        if "data_processing" in data:
            d = data["data_processing"]
            for key in ("epoch_length", "skip_rows", "preferred_activity_column", "device_preset"):
                if key in d:
                    overrides[key] = d[key]

        # Paths (only if provided - typically not shared between researchers)
        if "paths" in data:
            paths = data["paths"]
            for key in (
                "data_folder",
                "export_directory",
                "import_activity_directory",
                "import_nonwear_directory",
                "diary_import_directory",
                "actilife_import_directory",
            ):
                if key in paths:
                    overrides[key] = paths[key]

        return replace(config, **overrides) if overrides else config

    @classmethod
    def from_dict(cls, data: dict[str, Any], validate_complete: bool = True) -> AppConfig:
        """Create from dictionary data (loads only directory paths, uses hardcoded defaults for everything else)."""
        # Create instance with hardcoded defaults, only override directory paths
        return cls(
            data_folder=data.get(ConfigKey.DATA_FOLDER, ""),
            export_directory=data.get("export_directory", ""),
            import_activity_directory=data.get("import_activity_directory", ""),
            import_nonwear_directory=data.get("import_nonwear_directory", ""),
            diary_import_directory=data.get("diary_import_directory", ""),
            actilife_import_directory=data.get("actilife_import_directory", ""),
            # All other values use hardcoded defaults defined in the dataclass
        )

    @classmethod
    def create_default(cls) -> AppConfig:
        """Create default configuration with all hardcoded values."""
        return cls()

    @classmethod
    def builder(cls):
        """
        Start building a new config with fluent API.

        Returns:
            ConfigBuilder instance for method chaining

        Example:
            >>> config = (
            ...     AppConfig.builder()
            ...     .with_sleep_algorithm(AlgorithmType.SADEH_1994_ACTILIFE.value)
            ...     .with_night_hours(22, 6)
            ...     .build()
            ... )

        """
        from sleep_scoring_app.utils.config_builder import ConfigBuilder

        return ConfigBuilder()


@dataclass(frozen=True)
class ActiLifeSadehConfig:
    """ActiLife Sadeh configuration settings."""

    enabled: bool = False
    skip_rows: int = 3
    prefer_over_calculated: bool = True
    validate_against_calculated: bool = False


__all__ = [
    "ActiLifeSadehConfig",
    "AppConfig",
    "ColumnMapping",
]
