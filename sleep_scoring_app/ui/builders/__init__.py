"""UI section builders for decomposing large tab classes."""

from __future__ import annotations

from sleep_scoring_app.ui.builders.activity_preferences_builder import ActivityPreferencesBuilder
from sleep_scoring_app.ui.builders.algorithm_section_builder import AlgorithmSectionBuilder
from sleep_scoring_app.ui.builders.data_paradigm_builder import DataParadigmSectionBuilder
from sleep_scoring_app.ui.builders.data_source_config_builder import DataSourceConfigBuilder
from sleep_scoring_app.ui.builders.file_column_mapping_builder import FileColumnMappingBuilder
from sleep_scoring_app.ui.builders.import_settings_builder import ImportSettingsBuilder
from sleep_scoring_app.ui.builders.pattern_section_builder import PatternSectionBuilder
from sleep_scoring_app.ui.builders.valid_values_builder import ValidValuesSectionBuilder

__all__ = [
    "ActivityPreferencesBuilder",
    "AlgorithmSectionBuilder",
    "DataParadigmSectionBuilder",
    "DataSourceConfigBuilder",
    "FileColumnMappingBuilder",
    "ImportSettingsBuilder",
    "PatternSectionBuilder",
    "ValidValuesSectionBuilder",
]
