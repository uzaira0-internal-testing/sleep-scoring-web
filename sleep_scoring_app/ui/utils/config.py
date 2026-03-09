#!/usr/bin/env python3
"""
Configuration Manager for Sleep Scoring Application
Handles loading and saving of application settings using QSettings.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

from sleep_scoring_app.core.dataclasses import AppConfig, DiaryColumnMapping
from sleep_scoring_app.core.exceptions import ValidationError
from sleep_scoring_app.core.validation import InputValidator
from sleep_scoring_app.utils.resource_resolver import get_config_path, get_diary_config_path


# Late import to avoid circular dependency
def _get_column_registry():
    from sleep_scoring_app.utils.column_registry import column_registry

    return column_registry


try:
    from PyQt6.QtCore import QSettings

    QSETTINGS_AVAILABLE = True
except ImportError:
    # Fallback when PyQt6 is not available
    QSETTINGS_AVAILABLE = False
    QSettings = None  # type: ignore[misc, assignment]

# Configure logging
logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages application configuration using QSettings."""

    def __init__(self) -> None:
        self._lock = Lock()

        if QSETTINGS_AVAILABLE and QSettings is not None:
            self.settings = QSettings("SleepResearch", "SleepScoringApp")
        else:
            self.settings = None

        self.config = None

        self.config_file = get_config_path()
        self.config_dir = self.config_file.parent

        self.config_dir.mkdir(exist_ok=True)

        self.config = self.try_load_config()

    def is_config_valid(self) -> bool:
        """Check if configuration is valid without throwing exceptions."""
        return self.config is not None

    def try_load_config(self) -> AppConfig | None:
        """Try to load configuration, return None if invalid instead of throwing."""
        try:
            return self.load_config()
        except Exception as e:
            logger.warning("Failed to load configuration: %s", e)
            return None

    def load_config(self) -> AppConfig:
        """Load configuration from QSettings (directory paths and export grouping) and use hardcoded defaults for everything else."""
        from dataclasses import replace

        if QSETTINGS_AVAILABLE and self.settings:
            # Load directory paths, export grouping, and study settings from QSettings
            try:
                overrides: dict[str, Any] = {}

                # String settings: only override if non-empty
                string_keys = [
                    "data_folder",
                    "export_directory",
                    "import_activity_directory",
                    "import_nonwear_directory",
                    "diary_import_directory",
                    "actilife_import_directory",
                    "study_timepoint_pattern",
                    "study_group_pattern",
                    "study_default_group",
                    "study_default_timepoint",
                    "study_unknown_value",
                    "choi_axis",
                    "preferred_activity_column",
                    "nonwear_algorithm_id",
                    "sleep_algorithm_id",
                    "onset_offset_rule_id",
                    "data_paradigm",
                    "data_source_type_id",
                ]
                for key in string_keys:
                    val = self.settings.value(key, "")
                    if val:
                        overrides[key] = val

                # Export grouping
                export_grouping = self.settings.value("export_grouping", None)
                if export_grouping is not None:
                    overrides["export_grouping"] = int(export_grouping)

                # Pipe-separated list settings
                patterns_str = self.settings.value("study_participant_id_patterns", "")
                if patterns_str:
                    overrides["study_participant_id_patterns"] = patterns_str.split("|")
                groups_str = self.settings.value("study_valid_groups", "")
                if groups_str:
                    overrides["study_valid_groups"] = groups_str.split("|")
                timepoints_str = self.settings.value("study_valid_timepoints", "")
                if timepoints_str:
                    overrides["study_valid_timepoints"] = timepoints_str.split("|")

                # Typed settings: only override if key exists in QSettings
                int_keys = ["night_start_hour", "night_end_hour", "csv_skip_rows", "gt3x_epoch_length"]
                for key in int_keys:
                    if self.settings.contains(key):
                        overrides[key] = self.settings.value(key, type=int)

                bool_keys = ["gt3x_return_raw", "auto_save_markers"]
                for key in bool_keys:
                    if self.settings.contains(key):
                        overrides[key] = self.settings.value(key, type=bool)

                self.config = replace(AppConfig.create_default(), **overrides) if overrides else AppConfig.create_default()

                # Validate algorithm compatibility with paradigm
                self._validate_algorithm_paradigm_compatibility()

                logger.debug("Loaded configuration from QSettings")
                return self.config

            except Exception as e:
                logger.warning("Failed to load configuration from QSettings: %s, using defaults", e)
                # Continue to create default config

        # Try loading from JSON file as fallback (for migration)
        try:
            if self.config_file.exists():
                with open(self.config_file, encoding="utf-8") as f:
                    config_data = json.load(f)

                # Extract directory paths and export grouping from JSON, ignore other settings
                directory_data = {
                    "data_folder": config_data.get("data_folder", ""),
                    "export_directory": config_data.get("export_directory", ""),
                    "import_activity_directory": config_data.get("import_activity_directory", ""),
                    "import_nonwear_directory": config_data.get("import_nonwear_directory", ""),
                    "diary_import_directory": config_data.get("diary_import_directory", ""),
                    "actilife_import_directory": config_data.get("actilife_import_directory", ""),
                    "export_grouping": config_data.get("export_grouping", 0),
                }

                self.config = AppConfig.from_dict(directory_data, validate_complete=False)
                logger.debug("Loaded directory paths and export grouping from JSON file, using hardcoded defaults for other settings")
                return self.config

        except Exception as e:
            logger.warning("Failed to load directory paths from JSON: %s, using defaults", e)

        # Create default config with hardcoded values
        self.config = AppConfig.create_default()
        logger.debug("Created default config with hardcoded values")
        return self.config

    def _validate_algorithm_paradigm_compatibility(self) -> None:
        """
        Validate that selected algorithms are compatible with the data paradigm.

        If an algorithm is incompatible, reset it to the default for that paradigm.
        """
        from dataclasses import replace

        if self.config is None:
            return

        from sleep_scoring_app.services.algorithm_service import get_algorithm_service

        paradigm = self.config.data_paradigm
        algo_service = get_algorithm_service()

        # Validate nonwear algorithm (paradigm-specific)
        available_nonwear = algo_service.get_nonwear_algorithms_for_paradigm(paradigm)
        if self.config.nonwear_algorithm_id not in available_nonwear:
            # Get first available or default
            if available_nonwear:
                new_algo = next(iter(available_nonwear.keys()))
                logger.warning(
                    "Nonwear algorithm '%s' incompatible with paradigm '%s', resetting to '%s'",
                    self.config.nonwear_algorithm_id,
                    paradigm,
                    new_algo,
                )
                self.config = replace(self.config, nonwear_algorithm_id=str(new_algo))
            else:
                logger.warning("No nonwear algorithms available for paradigm '%s'", paradigm)

        # Note: Sleep algorithms are not currently paradigm-restricted,
        # so we only validate nonwear algorithms here

    def save_config(self) -> None:
        """Save configuration to QSettings (directory paths and export grouping) or JSON fallback (thread-safe)."""
        if self.config is None:
            msg = "Cannot save configuration - no configuration object exists"
            raise ValueError(msg)

        with self._lock:
            if QSETTINGS_AVAILABLE and self.settings:
                # Save directory paths, export grouping, and study settings to QSettings
                try:
                    # Directory paths
                    self.settings.setValue("data_folder", self.config.data_folder)
                    self.settings.setValue("export_directory", self.config.export_directory)
                    self.settings.setValue("import_activity_directory", self.config.import_activity_directory)
                    self.settings.setValue("import_nonwear_directory", self.config.import_nonwear_directory)
                    self.settings.setValue("diary_import_directory", self.config.diary_import_directory)
                    self.settings.setValue("actilife_import_directory", self.config.actilife_import_directory)
                    self.settings.setValue("export_grouping", self.config.export_grouping)

                    # Study settings - save lists as pipe-separated strings
                    patterns_str = "|".join(self.config.study_participant_id_patterns) if self.config.study_participant_id_patterns else ""
                    self.settings.setValue("study_participant_id_patterns", patterns_str)
                    self.settings.setValue("study_timepoint_pattern", self.config.study_timepoint_pattern)
                    self.settings.setValue("study_group_pattern", self.config.study_group_pattern)

                    groups_str = "|".join(self.config.study_valid_groups) if self.config.study_valid_groups else ""
                    self.settings.setValue("study_valid_groups", groups_str)

                    timepoints_str = "|".join(self.config.study_valid_timepoints) if self.config.study_valid_timepoints else ""
                    self.settings.setValue("study_valid_timepoints", timepoints_str)

                    self.settings.setValue("study_default_group", self.config.study_default_group)
                    self.settings.setValue("study_default_timepoint", self.config.study_default_timepoint)
                    self.settings.setValue("study_unknown_value", self.config.study_unknown_value)

                    # Algorithm settings
                    self.settings.setValue("night_start_hour", self.config.night_start_hour)
                    self.settings.setValue("night_end_hour", self.config.night_end_hour)
                    self.settings.setValue("choi_axis", self.config.choi_axis)
                    self.settings.setValue("preferred_activity_column", self.config.preferred_activity_column)
                    self.settings.setValue("nonwear_algorithm_id", self.config.nonwear_algorithm_id)
                    self.settings.setValue("sleep_algorithm_id", self.config.sleep_algorithm_id)
                    self.settings.setValue("onset_offset_rule_id", self.config.onset_offset_rule_id)
                    self.settings.setValue("data_paradigm", self.config.data_paradigm)

                    # Data source settings
                    self.settings.setValue("data_source_type_id", self.config.data_source_type_id)
                    self.settings.setValue("csv_skip_rows", self.config.csv_skip_rows)
                    self.settings.setValue("gt3x_epoch_length", self.config.gt3x_epoch_length)
                    self.settings.setValue("gt3x_return_raw", self.config.gt3x_return_raw)

                    # Auto-save settings
                    self.settings.setValue("auto_save_markers", self.config.auto_save_markers)

                    # Force sync to disk
                    self.settings.sync()

                    logger.debug("Saved configuration to QSettings")

                except Exception as e:
                    logger.warning("Error saving configuration to QSettings: %s", e)
                    # Fall back to JSON saving
                    self._save_to_json()
            else:
                # Fall back to JSON saving
                self._save_to_json()

    def _ensure_config(self) -> AppConfig:
        """Ensure config exists, raise if not."""
        if self.config is None:
            msg = "Configuration not loaded"
            raise ValueError(msg)
        return self.config

    def _save_to_json(self) -> None:
        """Fallback method to save configuration to JSON (directory paths and export grouping)."""
        config = self._ensure_config()
        try:
            # Save configuration to JSON (includes all settings)
            config_data = config.to_dict()

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)

            logger.debug("Saved directory paths and export grouping to JSON file: %s", self.config_file)
            logger.debug("  data_folder: '%s'", config.data_folder)
            logger.debug("  export_directory: '%s'", config.export_directory)
            logger.debug("  import_activity_directory: '%s'", config.import_activity_directory)
            logger.debug("  import_nonwear_directory: '%s'", config.import_nonwear_directory)
            logger.debug("  diary_import_directory: '%s'", config.diary_import_directory)
            logger.debug("  actilife_import_directory: '%s'", config.actilife_import_directory)
            logger.debug("  export_grouping: %s", config.export_grouping)

        except Exception as e:
            logger.warning("Error saving configuration to JSON: %s", e)

    def update_data_folder(self, folder_path: str) -> None:
        """Update data folder setting."""
        from dataclasses import replace

        self.config = replace(self._ensure_config(), data_folder=folder_path)
        self.save_config()

    def update_export_directory(self, directory: str) -> None:
        """Update export directory."""
        from dataclasses import replace

        self.config = replace(self._ensure_config(), export_directory=directory)
        self.save_config()

    def update_import_settings(
        self,
        activity_dir: str | None = None,
        nonwear_dir: str | None = None,
        diary_dir: str | None = None,
        actilife_dir: str | None = None,
    ) -> None:
        """Update import directory settings (only directories are configurable)."""
        from dataclasses import replace

        overrides: dict[str, Any] = {}
        if activity_dir is not None:
            overrides["import_activity_directory"] = activity_dir
            logger.debug("Updated import activity directory to: %s", activity_dir)
        if nonwear_dir is not None:
            overrides["import_nonwear_directory"] = nonwear_dir
            logger.debug("Updated import nonwear directory to: %s", nonwear_dir)
        if diary_dir is not None:
            overrides["diary_import_directory"] = diary_dir
            logger.debug("Updated diary import directory to: %s", diary_dir)
        if actilife_dir is not None:
            overrides["actilife_import_directory"] = actilife_dir
            logger.debug("Updated actilife import directory to: %s", actilife_dir)
        if overrides:
            self.config = replace(self._ensure_config(), **overrides)
        self.save_config()

    def update_export_grouping(self, grouping_id: int) -> None:
        """Update export grouping preference."""
        from dataclasses import replace

        self.config = replace(self._ensure_config(), export_grouping=grouping_id)
        logger.debug("Updated export grouping to: %s", grouping_id)
        self.save_config()

    def update_export_options(self, include_headers: bool, include_metadata: bool) -> None:
        """Update export options (headers and metadata)."""
        from dataclasses import replace

        self.config = replace(self._ensure_config(), include_headers=include_headers, include_metadata=include_metadata)
        logger.debug("Updated export options: headers=%s, metadata=%s", include_headers, include_metadata)
        self.save_config()

    def get_export_columns(self) -> list[str]:
        """Get selected export columns or defaults if none set."""
        config = self._ensure_config()
        if not config.export_columns:
            # Return all exportable columns from column registry
            column_registry = _get_column_registry()
            exportable_columns = column_registry.get_exportable()
            return [col.export_column for col in exportable_columns if col.export_column]
        return config.export_columns

    def update_skip_rows(self, value: int) -> None:
        """Update the skip rows setting for CSV import."""
        from dataclasses import replace

        self.config = replace(self._ensure_config(), skip_rows=value, import_skip_rows=value)
        logger.debug("Updated skip_rows to: %s", value)
        self.save_config()

    def update_epoch_length(self, value: int) -> None:
        """Update the epoch length setting."""
        from dataclasses import replace

        self.config = replace(self._ensure_config(), epoch_length=value)
        logger.debug("Updated epoch_length to: %s", value)
        self.save_config()

    def update_auto_save_markers(self, enabled: bool) -> None:
        """Update the auto-save markers setting."""
        from dataclasses import replace

        self.config = replace(self._ensure_config(), auto_save_markers=enabled)
        logger.debug("Updated auto_save_markers to: %s", enabled)
        self.save_config()

    def update_study_settings(self, **kwargs: Any) -> None:
        """
        Update study settings and persist to QSettings.

        Accepts Redux-style field names matching AppConfig attributes.
        """
        from dataclasses import replace

        if self.config is None:
            return

        # Valid config attribute names
        valid_attrs = {
            "study_participant_id_patterns",
            "study_timepoint_pattern",
            "study_group_pattern",
            "study_valid_groups",
            "study_valid_timepoints",
            "study_default_group",
            "study_default_timepoint",
            "study_unknown_value",
            "data_paradigm",
            "sleep_algorithm_id",
            "onset_offset_rule_id",
            "night_start_hour",
            "night_end_hour",
            "nonwear_algorithm_id",
            "choi_axis",
        }

        # Collect valid overrides
        overrides = {k: v for k, v in kwargs.items() if k in valid_attrs}
        if overrides:
            self.config = replace(self.config, **overrides)

        # Save to QSettings
        self.save_config()

    def export_config(self, output_path: str | Path, include_paths: bool = False) -> None:
        """
        Export current configuration to a JSON file for sharing.

        Args:
            output_path: Path to save the configuration file.
            include_paths: If True, include directory paths (may contain sensitive info).

        """
        if self.config is None:
            msg = "Cannot export configuration - no configuration loaded"
            raise ValueError(msg)

        output_path = Path(output_path)
        config_dict = self.config.to_full_dict(include_paths=include_paths)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2)

        logger.info("Exported configuration to: %s", output_path)

    def export_config_csv(self, output_path: str | Path) -> None:
        """
        Export current configuration to a CSV sidecar file.

        Args:
            output_path: Path to save the configuration CSV file.

        """
        if self.config is None:
            msg = "Cannot export configuration - no configuration loaded"
            raise ValueError(msg)

        output_path = Path(output_path)
        flat_config = self.config.to_flat_dict()

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Setting", "Value"])
            for key, value in sorted(flat_config.items()):
                writer.writerow([key, value])

        logger.info("Exported configuration CSV to: %s", output_path)

    def import_config(self, config_path: str | Path) -> AppConfig:
        """
        Import configuration from a JSON file.

        Args:
            config_path: Path to the configuration file.

        Returns:
            The imported AppConfig instance.

        """
        config_path = Path(config_path)

        if not config_path.exists():
            msg = f"Configuration file not found: {config_path}"
            raise FileNotFoundError(msg)

        with open(config_path, encoding="utf-8") as f:
            config_data = json.load(f)

        self.config = AppConfig.from_full_dict(config_data)
        self.save_config()

        logger.info("Imported configuration from: %s", config_path)
        return self.config

    def get_config_metadata_header(self) -> list[str]:
        """
        Generate config metadata lines for CSV export headers.

        Returns:
            List of comment lines (with # prefix) containing config info.

        """
        if self.config is None:
            return ["# Configuration: Not available"]

        from sleep_scoring_app import __version__ as app_version

        # Config schema version - must match dataclasses.py
        CONFIG_SCHEMA_VERSION = "1.0.0"

        return [
            "# === Configuration Settings ===",
            f"# config_schema_version: {CONFIG_SCHEMA_VERSION}",
            f"# app_version: {app_version}",
            f"# sleep_algorithm_id: {self.config.sleep_algorithm_id}",
            f"# night_start_hour: {self.config.night_start_hour}",
            f"# night_end_hour: {self.config.night_end_hour}",
            f"# epoch_length: {self.config.epoch_length}",
            f"# activity_file_skip_rows: {self.config.skip_rows}",
            f"# activity_column_to_plot: {self.config.preferred_activity_column}",
            f"# choi_axis: {self.config.choi_axis}",
            f"# nonwear_algorithm_id: {self.config.nonwear_algorithm_id}",
            f"# use_actilife_sadeh: {self.config.use_actilife_sadeh}",
            f"# auto_place_diary_markers: {self.config.auto_place_diary_markers}",
            f"# auto_detect_nonwear_overlap: {self.config.auto_detect_nonwear_overlap}",
            "# === End Configuration ===",
        ]

    def load_diary_mapping_config(self, config_path: str | Path | None = None) -> DiaryColumnMapping:
        """
        Load and parse diary mapping configuration from JSON file.

        Args:
            config_path: Optional path to config file. If None, uses default config/diary_mapping.json

        Returns:
            DiaryColumnMapping: Parsed diary mapping configuration

        Raises:
            ValidationError: If config file path is invalid or contains malicious content
            FileNotFoundError: If config file doesn't exist
            ValueError: If JSON parsing fails or required fields are missing

        """
        # Determine config file path
        if config_path is None:
            config_file_path = get_diary_config_path("diary_mapping.json")
        else:
            config_file_path = Path(config_path)

        # Validate file path for security
        validator = InputValidator()
        try:
            validated_path = validator.validate_file_path(str(config_file_path))
            config_file_path = Path(validated_path)
        except ValidationError as e:
            logger.exception("Invalid diary mapping config file path: %s", e)
            raise

        # Check if file exists
        if not config_file_path.exists():
            msg = f"Diary mapping config file not found: {config_file_path}"
            logger.error(msg)
            raise FileNotFoundError(msg)

        # Load and parse JSON
        try:
            with open(config_file_path, encoding="utf-8") as f:
                config_data = json.load(f)

            logger.debug("Loaded diary mapping config from: %s", config_file_path)

            # Validate that it's a dictionary
            if not isinstance(config_data, dict):
                msg = f"Diary mapping config must be a JSON object, got {type(config_data).__name__}"
                raise ValueError(msg)

            # Create DiaryColumnMapping from the loaded data
            # Filter the config data to only include fields that exist in DiaryColumnMapping
            mapping_fields = {field.name for field in DiaryColumnMapping.__dataclass_fields__.values()}
            filtered_config_data = {key: value for key, value in config_data.items() if key in mapping_fields}

            diary_mapping = DiaryColumnMapping.from_dict(filtered_config_data)

            logger.info(
                "Successfully loaded diary mapping configuration with %d total fields and %d mapped fields",
                len([v for v in config_data.values() if v is not None and v != ""]),
                len([v for v in filtered_config_data.values() if v is not None and v != ""]),
            )

            return diary_mapping

        except json.JSONDecodeError as e:
            msg = f"Invalid JSON in diary mapping config file {config_file_path}: {e}"
            logger.exception(msg)
            raise ValueError(msg) from e
        except Exception as e:
            msg = f"Failed to load diary mapping config from {config_file_path}: {e}"
            logger.exception(msg)
            raise ValueError(msg) from e


# Convenience function for direct access
def load_diary_mapping_config(config_path: str | Path | None = None) -> DiaryColumnMapping:
    """
    Convenience function to load diary mapping configuration without creating a ConfigManager instance.

    This function loads the diary column mapping configuration from a JSON file and returns
    a DiaryColumnMapping object that can be used by diary import services.

    Args:
        config_path: Optional path to config file. If None, uses default config/diary_mapping.json

    Returns:
        DiaryColumnMapping: Parsed diary mapping configuration with validated column mappings

    Raises:
        ValidationError: If config file path is invalid or contains malicious content
        FileNotFoundError: If config file doesn't exist
        ValueError: If JSON parsing fails or required fields are missing

    Example:
        ```python
        from sleep_scoring_app.ui.utils.config import load_diary_mapping_config

        # Load default mapping configuration
        mapping = load_diary_mapping_config()

        # Access column mappings for diary import
        participant_col = mapping.participant_id_column_name  # "participant_id"
        sleep_onset_col = mapping.sleep_onset_time_column_name  # "asleep_time"
        sleep_offset_col = mapping.sleep_offset_time_column_name  # "wake_time"

        # Check for nonwear data columns
        if mapping.nonwear_occurred_column_name:
            nonwear_col = mapping.nonwear_occurred_column_name  # "takeoff"

        # Use custom config file path
        custom_mapping = load_diary_mapping_config("/path/to/custom/mapping.json")
        ```

    """
    # Create a temporary ConfigManager instance to use the method
    config_manager = ConfigManager()
    return config_manager.load_diary_mapping_config(config_path)
