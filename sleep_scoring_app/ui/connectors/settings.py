"""
Settings connectors.

Connects algorithm configuration, algorithm dropdowns, study settings, data settings, and cache to the Redux store.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sleep_scoring_app.ui.data_settings_tab import DataSettingsTab
    from sleep_scoring_app.ui.protocols import MainWindowProtocol
    from sleep_scoring_app.ui.store import UIState, UIStore

logger = logging.getLogger(__name__)


class AlgorithmConfigConnector:
    """Connects calibration and imputation settings to the UI and triggers reloads."""

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial update
        self._update_ui(store.state)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to calibration or imputation changes."""
        changed = (
            old_state.auto_calibrate_enabled != new_state.auto_calibrate_enabled or old_state.impute_gaps_enabled != new_state.impute_gaps_enabled
        )

        if changed:
            self._update_ui(new_state)
            # NOTE: DO NOT call load_current_date() here!
            # ActivityDataConnector watches for config changes and reloads data automatically
            if new_state.current_file:
                logger.info("Algorithm config changed - ActivityDataConnector will reload data")

    def _update_ui(self, state: UIState) -> None:
        """Update checkboxes in DataSettingsTab."""
        # Protocol guarantees data_settings_tab exists on MainWindowProtocol
        tab = self.main_window.data_settings_tab
        if not tab:
            return

        # These checkboxes are optional UI elements - use getattr with default
        auto_calibrate_check = getattr(tab, "auto_calibrate_check", None)
        if auto_calibrate_check:
            auto_calibrate_check.blockSignals(True)
            auto_calibrate_check.setChecked(state.auto_calibrate_enabled)
            auto_calibrate_check.blockSignals(False)

        impute_gaps_check = getattr(tab, "impute_gaps_check", None)
        if impute_gaps_check:
            impute_gaps_check.blockSignals(True)
            impute_gaps_check.setChecked(state.impute_gaps_enabled)
            impute_gaps_check.blockSignals(False)

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class AlgorithmDropdownConnector:
    """Connects the activity source dropdown to the store algorithm preference."""

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial update
        self._update_ui(store.state.current_algorithm)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to algorithm changes."""
        if old_state.current_algorithm != new_state.current_algorithm:
            self._update_ui(new_state.current_algorithm)

    def _update_ui(self, algorithm: str) -> None:
        """Update dropdown selection."""
        # Protocol guarantees analysis_tab has activity_source_dropdown
        tab = self.main_window.analysis_tab
        if not tab:
            return

        dropdown = tab.activity_source_dropdown

        # Find index for this algorithm ID
        index = dropdown.findData(algorithm)
        if index != -1:
            dropdown.blockSignals(True)
            dropdown.setCurrentIndex(index)
            dropdown.blockSignals(False)

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class StudySettingsConnector:
    """
    Connects the StudySettingsTab to the Redux store.

    SOLE Authority for syncing Study Settings UI with the Redux state.
    - Subscribes to store state changes and updates the tab UI
    - Connects the tab's studySettingChanged signal to dispatch actions to the store
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window

        # Find the widget
        self.tab = getattr(main_window, "study_settings_tab", None)
        if not self.tab:
            logger.warning("STUDY SETTINGS CONNECTOR: StudySettingsTab not found")
            return

        self._unsubscribe = store.subscribe(self._on_state_change)

        # Connect widget signal -> store dispatch (widget is dumb, connector dispatches)
        self.tab.studySettingChanged.connect(self._on_setting_changed)

        # Initial update
        self._update_ui(store.state)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to study settings changes in the store."""
        # Check for any study settings changes
        fields_to_check = [
            "study_unknown_value",
            "study_valid_groups",
            "study_valid_timepoints",
            "study_default_group",
            "study_default_timepoint",
            "study_participant_id_patterns",
            "study_timepoint_pattern",
            "study_group_pattern",
            "data_paradigm",
            "sleep_algorithm_id",
            "onset_offset_rule_id",
            "night_start_hour",
            "night_end_hour",
            "nonwear_algorithm_id",
            "choi_axis",
        ]

        changed_fields = [f for f in fields_to_check if getattr(old_state, f) != getattr(new_state, f)]

        if changed_fields:
            logger.info(f"STUDY SETTINGS CONNECTOR: Settings changed: {changed_fields}")
            self._update_ui(new_state)
            self._handle_side_effects(old_state, new_state, changed_fields)

    def _update_ui(self, state: UIState) -> None:
        """Update the StudySettingsTab UI from state."""
        # Protocol guarantees _load_settings_from_state exists on StudySettingsTabProtocol
        if not self.tab:
            return

        self.tab._load_settings_from_state(state)

    def _on_setting_changed(self, field: str, value: object) -> None:
        """Handle study setting changes from the tab widget and dispatch to store."""
        from sleep_scoring_app.ui.store import Actions

        self.store.dispatch_async(Actions.study_settings_changed({field: value}))

    def _handle_side_effects(self, old_state: UIState, new_state: UIState, changed_fields: list[str]) -> None:
        """Handle side effects of setting changes."""
        from sleep_scoring_app.services.algorithm_service import get_algorithm_service

        pw = self.main_window.plot_widget
        if not pw:
            return

        # 1. Sleep Algorithm or Onset/Offset Rule Change
        # Protocol guarantees algorithm_manager exists (can be None initially)
        if "sleep_algorithm_id" in changed_fields or "onset_offset_rule_id" in changed_fields:
            if pw.algorithm_manager:
                algo_id = new_state.sleep_algorithm_id
                rule_id = new_state.onset_offset_rule_id

                # Update algorithm
                if "sleep_algorithm_id" in changed_fields:
                    # We need the full config for the algorithm
                    config = self.main_window.config_manager.config
                    algorithm = get_algorithm_service().create_sleep_algorithm(algo_id, config)
                    pw.algorithm_manager.set_sleep_scoring_algorithm(algorithm)

                # Update rule
                if "onset_offset_rule_id" in changed_fields:
                    detector = get_algorithm_service().create_sleep_period_detector(rule_id)
                    pw.algorithm_manager.set_sleep_period_detector(detector)

                # Recalculate and update plot
                pw.algorithm_manager._algorithm_cache.clear()
                pw.algorithm_manager.plot_algorithms()

                # Clear and reapply rules to current selection
                pw.algorithm_manager.clear_sleep_onset_offset_markers()
                selected = pw.get_selected_marker_period()
                if selected and selected.is_complete:
                    pw.algorithm_manager.apply_sleep_scoring_rules(selected)

                pw.update()
                logger.info("Updated plot algorithms due to setting change")

                # Update table headers to reflect new algorithm name
                if "sleep_algorithm_id" in changed_fields:
                    if self.main_window.table_manager:
                        # Force update - we know the algorithm just changed
                        self.main_window.table_manager.update_table_headers_for_algorithm(force=True)

                    # Update algorithm compatibility status in status bar
                    if self.main_window.compatibility_helper:
                        self.main_window.compatibility_helper.on_algorithm_changed(algo_id)

                # CRITICAL: Refresh marker tables with new algorithm values
                # The table data contains algorithm scores which need recalculation
                self._refresh_marker_tables_for_selection(selected)

        # 2. Paradigm Change
        # Protocol guarantees data_settings_tab exists with update_loaders_for_paradigm method
        if "data_paradigm" in changed_fields:
            dst = self.main_window.data_settings_tab
            if dst:
                from sleep_scoring_app.core.constants import StudyDataParadigm

                try:
                    paradigm = StudyDataParadigm(new_state.data_paradigm)
                    dst.update_loaders_for_paradigm(paradigm)
                except Exception as e:
                    logger.exception(f"Error updating loaders for paradigm: {e}")

        # 3. Nonwear Algorithm or Choi Axis Change
        # Protocol guarantees these methods exist on PlotWidgetProtocol
        if "nonwear_algorithm_id" in changed_fields or "choi_axis" in changed_fields:
            # Clear caches
            if pw.algorithm_manager:
                pw.algorithm_manager._algorithm_cache.clear()
            pw.clear_choi_cache()

            # Reload nonwear data with the correct choi_axis data
            # This ensures the Choi algorithm uses the configured axis, not display data
            filename = new_state.current_file
            date_str = (
                new_state.available_dates[new_state.current_date_index]
                if 0 <= new_state.current_date_index < len(new_state.available_dates)
                else None
            )

            if filename and date_str:
                # Use load_nonwear_data_for_plot which loads the correct choi_axis data
                self.main_window.load_nonwear_data_for_plot()
                logger.info("Reloaded nonwear data for algorithm/axis change")
            else:
                logger.warning("Cannot reload nonwear data - no file/date selected")

            pw.update()
            logger.info("Updated nonwear detection due to setting change")

    def _refresh_marker_tables_for_selection(self, selected_period: Any | None) -> None:
        """
        Refresh marker tables with recalculated algorithm values.

        Called after algorithm or rule changes to update the table data
        which contains algorithm scores at each epoch.

        """
        from sleep_scoring_app.core.constants import MarkerCategory

        # Only update tables in SLEEP mode
        if self.store.state.marker_mode != MarkerCategory.SLEEP:
            return

        table_manager = self.main_window.table_manager
        if not table_manager:
            return

        if selected_period and selected_period.is_complete:
            # Get fresh data with new algorithm values using table_manager service
            onset_data = table_manager.get_marker_data_cached(selected_period.onset_timestamp, None)
            offset_data = table_manager.get_marker_data_cached(selected_period.offset_timestamp, None)

            if onset_data or offset_data:
                table_manager.update_marker_tables(onset_data, offset_data)
                logger.info("Refreshed marker tables with new algorithm values")

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class CacheConnector:
    """Handles cache invalidation based on store state changes."""

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to state changes that require cache invalidation."""
        # Invalidate cache when markers are saved or cleared
        if old_state.last_saved_file != new_state.last_saved_file:
            if new_state.last_saved_file:
                self._invalidate_cache(new_state.last_saved_file)

        # Also invalidate on markers_cleared (when last_saved_file becomes None)
        if old_state.last_saved_file and not new_state.last_saved_file:
            self._invalidate_cache(old_state.last_saved_file)

    def _invalidate_cache(self, filename: str) -> None:
        """Invalidate marker status cache for a file."""
        # Protocol guarantees data_service exists
        if self.main_window.data_service:
            self.main_window.data_service.invalidate_marker_status_cache(filename)
            logger.debug("Invalidated marker cache for %s", filename)

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class DataSettingsDispatchConnector:
    """
    Bridges DataSettingsTab signals to store dispatches and main_window methods.

    Connects:
    - fileCleared signal -> store.dispatch(file_selected(None)) + store.dispatch(dates_loaded([]))
    - clearActivityDataRequested signal -> store.dispatch(clear_activity_data_requested())
    - epochLengthChanged signal -> main_window.on_epoch_length_changed()
    - skipRowsChanged signal -> main_window.on_skip_rows_changed()
    - browseActivityFilesRequested signal -> main_window.browse_activity_files()
    - startActivityImportRequested signal -> main_window.start_activity_import()
    - browseNonwearFilesRequested signal -> main_window.browse_nonwear_files()
    - startNonwearImportRequested signal -> main_window.start_nonwear_import()
    """

    def __init__(self, tab: DataSettingsTab, store: UIStore, main_window: MainWindowProtocol) -> None:
        self._tab = tab
        self._store = store
        self._main_window = main_window

        # Connect store dispatch signals
        tab.fileCleared.connect(self._on_file_cleared)
        tab.clearActivityDataRequested.connect(self._on_clear_activity_data)
        tab.refreshFilesRequested.connect(self._on_refresh_files)
        tab.clearNwtDataRequested.connect(self._on_clear_nwt_data)
        tab.clearDiaryDataRequested.connect(self._on_clear_diary_data)

        # Connect data setting config persistence signal
        tab.dataSettingChanged.connect(self._on_data_setting_changed)

        # Connect main_window method signals
        tab.epochLengthChanged.connect(self._on_epoch_length_changed)
        tab.skipRowsChanged.connect(self._on_skip_rows_changed)
        tab.browseActivityFilesRequested.connect(self._on_browse_activity_files)
        tab.startActivityImportRequested.connect(self._on_start_activity_import)
        tab.browseNonwearFilesRequested.connect(self._on_browse_nonwear_files)
        tab.startNonwearImportRequested.connect(self._on_start_nonwear_import)

        logger.info("DataSettingsDispatchConnector initialized")

    def _on_data_setting_changed(self, field: str, value: object) -> None:
        """Persist a data setting change to config on behalf of the widget."""
        from dataclasses import replace

        config_manager = self._main_window.config_manager
        if config_manager and config_manager.config:
            config_manager.config = replace(config_manager.config, **{field: value})
            config_manager.save_config()
            logger.info("Config updated via connector: %s = %s", field, value)

    def _on_file_cleared(self) -> None:
        """Dispatch file cleared actions to the store."""
        from sleep_scoring_app.ui.store import Actions

        self._store.dispatch(Actions.file_selected(None))
        self._store.dispatch(Actions.dates_loaded([]))

    def _on_clear_activity_data(self) -> None:
        """Dispatch clear activity data request to the store."""
        from sleep_scoring_app.ui.store import Actions

        self._store.dispatch(Actions.clear_activity_data_requested())

    def _on_refresh_files(self) -> None:
        """Dispatch refresh files request to the store."""
        from sleep_scoring_app.ui.store import Actions

        self._store.dispatch(Actions.refresh_files_requested())

    def _on_clear_nwt_data(self) -> None:
        """Clear NWT data via db_manager (through main_window services)."""
        from PyQt6.QtWidgets import QMessageBox

        try:
            self._main_window.db_manager.clear_nwt_data()
            QMessageBox.information(None, "Success", "NWT data cleared successfully!")
            logger.info("NWT data cleared by user via connector")
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to clear NWT data: {e}")
            logger.exception("Failed to clear NWT data")

    def _on_clear_diary_data(self) -> None:
        """Clear diary data via db_manager (through main_window services)."""
        from PyQt6.QtWidgets import QMessageBox

        try:
            self._main_window.db_manager.clear_diary_data()
            QMessageBox.information(None, "Success", "Diary data cleared successfully!")
            logger.info("Diary data cleared by user via connector")
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to clear diary data: {e}")
            logger.exception("Failed to clear diary data")

    def _on_epoch_length_changed(self, value: int) -> None:
        """Forward epoch length change to main_window."""
        self._main_window.on_epoch_length_changed(value)

    def _on_skip_rows_changed(self, value: int) -> None:
        """Forward skip rows change to main_window."""
        self._main_window.on_skip_rows_changed(value)

    def _on_browse_activity_files(self) -> None:
        """Forward browse activity files request to main_window."""
        self._main_window.browse_activity_files()

    def _on_start_activity_import(self) -> None:
        """Forward start activity import request to main_window."""
        self._main_window.start_activity_import()

    def _on_browse_nonwear_files(self) -> None:
        """Forward browse nonwear files request to main_window."""
        self._main_window.browse_nonwear_files()

    def _on_start_nonwear_import(self) -> None:
        """Forward start nonwear import request to main_window."""
        self._main_window.start_nonwear_import()

    def disconnect(self) -> None:
        """Cleanup signal connections."""
        try:
            self._tab.dataSettingChanged.disconnect(self._on_data_setting_changed)
            self._tab.fileCleared.disconnect(self._on_file_cleared)
            self._tab.clearActivityDataRequested.disconnect(self._on_clear_activity_data)
            self._tab.epochLengthChanged.disconnect(self._on_epoch_length_changed)
            self._tab.skipRowsChanged.disconnect(self._on_skip_rows_changed)
            self._tab.browseActivityFilesRequested.disconnect(self._on_browse_activity_files)
            self._tab.startActivityImportRequested.disconnect(self._on_start_activity_import)
            self._tab.browseNonwearFilesRequested.disconnect(self._on_browse_nonwear_files)
            self._tab.startNonwearImportRequested.disconnect(self._on_start_nonwear_import)
        except (TypeError, RuntimeError):
            pass  # Signals may already be disconnected
