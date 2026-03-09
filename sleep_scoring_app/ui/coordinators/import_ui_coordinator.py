#!/usr/bin/env python3
"""
Import UI Coordinator Service.

Coordinates import operations between UI components and import workers.
Handles file selection, validation, progress updates, and completion.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from sleep_scoring_app.core.constants import StudyDataParadigm

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import AppConfig
    from sleep_scoring_app.ui.protocols import MainWindowProtocol, ServiceContainer

logger = logging.getLogger(__name__)


class ImportUICoordinator:
    """
    Coordinates import operations between UI and worker threads.

    Responsibilities:
    - File browsing and selection
    - File validation against data paradigm
    - Import worker management
    - Progress updates to UI
    - Import completion handling

    ARCHITECTURE NOTE: This coordinator manages QThread workers which require
    Qt signal/slot connections. While it does some direct widget manipulation
    for progress updates, this is acceptable for ephemeral import state.

    Future improvement: Progress could be dispatched to Redux and a connector
    could update progress bars, but the complexity gain is minimal for
    ephemeral state that only exists during import operations.
    """

    def __init__(self, parent: MainWindowProtocol, services: ServiceContainer) -> None:
        """
        Initialize the import UI coordinator.

        Args:
            parent: Reference to main window for UI access
            services: Service container for headless services

        """
        self.main_window = parent
        self.services = services

        # Track selected files for import
        self._selected_activity_files: list[Path] = []
        self._selected_nonwear_files: list[Path] = []

        # Worker references
        self.import_worker = None
        self.nonwear_import_worker = None

        logger.info("ImportUICoordinator initialized with decoupled services")

    def _get_config(self) -> AppConfig:
        """Get config, raising if not available."""
        config = self.services.config_manager.config
        if config is None:
            msg = "Configuration not loaded"
            raise RuntimeError(msg)
        return config

    @property
    def _parent_widget(self) -> QWidget | None:
        """Get parent as QWidget for dialogs."""
        return self.main_window if isinstance(self.main_window, QWidget) else None

    def browse_data_folder(self) -> None:
        """Browse for CSV data folder (does not automatically load files)."""
        # Start from last used folder or home directory
        config = self._get_config()
        start_dir = config.data_folder or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self._parent_widget, "Select Data Folder", start_dir)

        if directory:
            # Save to config but don't automatically load files
            self.services.config_manager.update_data_folder(directory)

    def browse_activity_files(self) -> None:
        """Browse for activity data files (multi-select)."""
        config = self._get_config()
        # Start from last used activity directory or home directory
        start_dir = config.import_activity_directory or str(Path.home())

        # Build file filter based on current data paradigm
        file_filter = self._get_paradigm_file_filter()

        files, _ = QFileDialog.getOpenFileNames(
            self._parent_widget,
            "Select Activity Data Files",
            start_dir,
            file_filter,
        )

        if files:
            try:
                # Store selected files
                self._selected_activity_files = [Path(f) for f in files]
                # Display file count
                file_count = len(files)
                display_text = f"{file_count} file(s) selected"
                self.main_window.data_settings_tab._set_path_label_text(self.main_window.data_settings_tab.activity_import_files_label, display_text)
                self.main_window.data_settings_tab.activity_import_btn.setEnabled(True)
                # Save directory of first file to config for next browse
                from dataclasses import replace as dc_replace

                self.services.config_manager.config = dc_replace(config, import_activity_directory=str(Path(files[0]).parent))
                self.services.config_manager.save_config()
            except AttributeError as e:
                logger.warning("Parent window missing required attributes: %s", e)

    def _get_paradigm_file_filter(self) -> str:
        """
        Build file filter string based on current data paradigm.

        Returns:
            File filter string for QFileDialog based on paradigm setting.
            - EPOCH_BASED: CSV and Excel files only
            - RAW_ACCELEROMETER: GT3X, CSV, and Excel files

        """
        try:
            config = self._get_config()
            paradigm_value = config.data_paradigm
            paradigm = StudyDataParadigm(paradigm_value)
        except (ValueError, AttributeError, RuntimeError):
            paradigm = StudyDataParadigm.get_default()

        if paradigm == StudyDataParadigm.RAW_ACCELEROMETER:
            # Raw accelerometer mode - GT3X files primary, CSV/Excel secondary
            return "Supported Files (*.gt3x *.csv *.xlsx *.xls);;GT3X Files (*.gt3x);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls);;All Files (*)"
        # Default: EPOCH_BASED - CSV and Excel files only
        return "Epoch Data Files (*.csv *.xlsx *.xls);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls);;All Files (*)"

    def browse_nonwear_files(self) -> None:
        """Browse for nonwear sensor files (multi-select)."""
        # Start from last used nonwear directory or home directory
        config = self._get_config()
        start_dir = config.import_nonwear_directory or str(Path.home())
        files, _ = QFileDialog.getOpenFileNames(
            self._parent_widget,
            "Select Nonwear Sensor Files",
            start_dir,
            "CSV Files (*.csv);;All Files (*)",
        )

        if files:
            try:
                # Store selected files
                self._selected_nonwear_files = [Path(f) for f in files]
                # Display file count
                file_count = len(files)
                display_text = f"{file_count} file(s) selected"
                self.main_window.data_settings_tab._set_path_label_text(self.main_window.data_settings_tab.nwt_import_files_label, display_text)
                self.main_window.data_settings_tab.nwt_import_btn.setEnabled(True)
                # Save directory of first file to config for next browse
                from dataclasses import replace as dc_replace

                self.services.config_manager.config = dc_replace(config, import_nonwear_directory=str(Path(files[0]).parent))
                self.services.config_manager.save_config()
            except AttributeError as e:
                logger.warning("Parent window missing required attributes: %s", e)

    def _validate_files_against_paradigm(self, files: list[Path]) -> tuple[list[Path], list[Path]]:
        """
        Validate selected files against the current data paradigm.

        Args:
            files: List of file paths to validate

        Returns:
            Tuple of (compatible_files, incompatible_files)

        """
        try:
            config = self._get_config()
            paradigm_value = config.data_paradigm
            paradigm = StudyDataParadigm(paradigm_value)
        except (ValueError, AttributeError, RuntimeError):
            paradigm = StudyDataParadigm.get_default()

        compatible_extensions = paradigm.get_compatible_file_extensions()
        compatible_files = []
        incompatible_files = []

        for file_path in files:
            ext = file_path.suffix.lower()
            if ext in compatible_extensions:
                compatible_files.append(file_path)
            else:
                incompatible_files.append(file_path)

        return compatible_files, incompatible_files

    def start_activity_import(self) -> None:
        """Start the activity data import process."""
        from sleep_scoring_app.ui.workers import ImportWorker

        # Check for selected files
        if not self._selected_activity_files:
            QMessageBox.warning(
                self._parent_widget,
                "No Files Selected",
                "Please select activity data files to import",
            )
            return

        # Validate files against current paradigm
        compatible_files, incompatible_files = self._validate_files_against_paradigm(self._selected_activity_files)
        config = self._get_config()

        if incompatible_files:
            # Get current paradigm for message
            try:
                paradigm_value = config.data_paradigm
                paradigm = StudyDataParadigm(paradigm_value)
            except (ValueError, AttributeError):
                paradigm = StudyDataParadigm.get_default()

            paradigm_name = paradigm.get_display_name()
            compatible_exts = ", ".join(paradigm.get_compatible_file_extensions())
            incompatible_names = "\n".join(f"  - {f.name}" for f in incompatible_files[:10])
            if len(incompatible_files) > 10:
                incompatible_names += f"\n  ... and {len(incompatible_files) - 10} more"

            if compatible_files:
                # Some files are compatible - ask user what to do
                msg = (
                    f"The following files are not compatible with the current paradigm "
                    f"({paradigm_name}):\n\n{incompatible_names}\n\n"
                    f"Compatible file types: {compatible_exts}\n\n"
                    f"Do you want to import only the {len(compatible_files)} compatible file(s)?"
                )
                reply = QMessageBox.question(
                    self._parent_widget,
                    "Incompatible Files",
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    return
                # Use only compatible files
                self._selected_activity_files = compatible_files
            else:
                # No compatible files at all
                QMessageBox.warning(
                    self._parent_widget,
                    "Incompatible Files",
                    f"None of the selected files are compatible with the current paradigm "
                    f"({paradigm_name}).\n\n"
                    f"Compatible file types: {compatible_exts}\n\n"
                    f"Please select different files or change the data paradigm in Study Settings.",
                )
                return

        tab = self.main_window.data_settings_tab
        if tab is None:
            logger.warning("Data settings tab not available")
            return

        tab.activity_import_btn.setEnabled(False)
        tab.activity_import_btn.setText("Import in Progress...")
        if tab.activity_progress_label:
            tab.activity_progress_label.setText("Starting import...")
            tab.activity_progress_label.setVisible(True)
        if tab.activity_progress_bar:
            tab.activity_progress_bar.setVisible(True)
            tab.activity_progress_bar.setValue(0)

        # Build custom columns dict if using Generic CSV
        custom_columns = None
        if config.device_preset == "generic_csv":
            if config.custom_date_column:  # Only use custom columns if configured
                custom_columns = {
                    "date": config.custom_date_column,
                    "time": config.custom_time_column if not config.datetime_combined else None,
                    "activity": config.custom_activity_column or config.custom_axis_y_column,
                    "datetime_combined": config.datetime_combined,
                    # Axis columns for algorithm use (Y=vertical, X=lateral, Z=forward)
                    "axis_y": config.custom_axis_y_column,
                    "axis_x": config.custom_axis_x_column,
                    "axis_z": config.custom_axis_z_column,
                    "vector_magnitude": config.custom_vector_magnitude_column,
                }

        # Get skip_rows from config (DataSettingsTab is dumb, doesn't hold service state)
        skip_rows = config.skip_rows

        # Start worker thread with selected files
        # import_service comes from ServiceContainer (MainWindow), NOT from widget
        self.import_worker = ImportWorker(
            self.services.import_service,
            self._selected_activity_files,
            skip_rows,
            False,  # force_reimport
            include_nonwear=False,
            custom_columns=custom_columns,
        )

        # Connect worker signals with thread-safe queued connections
        self.import_worker.progress_updated.connect(self.update_activity_progress, Qt.ConnectionType.QueuedConnection)
        self.import_worker.nonwear_progress_updated.connect(self.update_nonwear_progress, Qt.ConnectionType.QueuedConnection)
        self.import_worker.import_completed.connect(self.activity_import_finished, Qt.ConnectionType.QueuedConnection)

        # Start import
        self.import_worker.start()

    def start_nonwear_import(self) -> None:
        """Start the nonwear sensor data import process."""
        from sleep_scoring_app.ui.workers import NonwearImportWorker

        # Check for selected files
        if not self._selected_nonwear_files:
            QMessageBox.warning(
                self._parent_widget,
                "No Files Selected",
                "Please select nonwear sensor files to import",
            )
            return

        tab = self.main_window.data_settings_tab
        if tab is None:
            logger.warning("Data settings tab not available")
            return

        tab.nwt_import_btn.setEnabled(False)
        tab.nwt_import_btn.setText("Import in Progress...")

        # Show progress components
        if tab.nwt_progress_label:
            tab.nwt_progress_label.setText("Starting NWT import...")
            tab.nwt_progress_label.setVisible(True)
        if tab.nwt_progress_bar:
            tab.nwt_progress_bar.setVisible(True)
            tab.nwt_progress_bar.setValue(0)

        try:
            # Create and configure the nonwear import worker with selected files
            # import_service comes from ServiceContainer (MainWindow), NOT from widget
            self.nonwear_import_worker = NonwearImportWorker(self.services.import_service, self._selected_nonwear_files)

            # Connect signals for progress updates
            self.nonwear_import_worker.progress_updated.connect(self.update_nonwear_progress, Qt.ConnectionType.QueuedConnection)
            self.nonwear_import_worker.import_completed.connect(self.nonwear_import_finished, Qt.ConnectionType.QueuedConnection)

            # Start the async import
            self.nonwear_import_worker.start()

        except Exception as e:
            QMessageBox.critical(self._parent_widget, "Import Error", f"Failed to start nonwear import: {e}")
            tab.nwt_import_btn.setEnabled(True)
            tab.nwt_import_btn.setText("Import NWT Data to Database")

    def update_activity_progress(self, progress) -> None:
        """Update activity import progress."""
        tab = self.main_window.data_settings_tab
        if tab is None:
            logger.debug("Cannot update activity progress - tab not available")
            return
        try:
            if tab.activity_progress_bar:
                tab.activity_progress_bar.setValue(int(progress.file_progress_percent))
            if tab.activity_progress_label:
                tab.activity_progress_label.setText(f"Files: {progress.processed_files}/{progress.total_files}")
        except AttributeError:
            logger.debug("Cannot update activity progress - attribute not available")

    def update_nonwear_progress(self, progress) -> None:
        """Update nonwear import progress."""
        tab = self.main_window.data_settings_tab
        if tab is None:
            logger.debug("Cannot update nonwear progress - tab not available")
            return
        try:
            if tab.nwt_progress_bar:
                tab.nwt_progress_bar.setValue(int(progress.nonwear_progress_percent))
            if tab.nwt_progress_label:
                tab.nwt_progress_label.setText(f"NWT Files: {progress.processed_nonwear_files}/{progress.total_nonwear_files}")
        except AttributeError:
            logger.debug("Cannot update nonwear progress - attribute not available")

    def activity_import_finished(self, progress) -> None:
        """Handle activity import completion."""
        tab = self.main_window.data_settings_tab
        if tab is not None:
            try:
                tab.activity_import_btn.setEnabled(False)
                tab.activity_import_btn.setText("Import")
                if tab.activity_progress_label:
                    tab.activity_progress_label.setText("Import completed")
                # Clear the file selection label and stored files
                tab._set_path_label_text(tab.activity_import_files_label, "No files selected")
                self._selected_activity_files = []
                # Hide progress components after a delay
                QTimer.singleShot(3000, lambda: self._hide_progress_components())
            except AttributeError as e:
                logger.warning("Cannot update UI after import completion: %s", e)

        # Display results with detailed error messages if applicable
        if progress.errors:
            # Build detailed error message
            error_summary = f"Import completed with {len(progress.errors)} error(s):\n\n"
            # Show first 5 errors in detail, summarize rest
            displayed_errors = progress.errors[:5]
            for i, error in enumerate(displayed_errors, 1):
                error_summary += f"{i}. {error}\n\n"

            if len(progress.errors) > 5:
                error_summary += f"... and {len(progress.errors) - 5} more error(s).\n\n"

            # Add summary of what succeeded
            if progress.imported_files:
                error_summary += f"\nSuccessfully imported: {len(progress.imported_files)} file(s)"

            QMessageBox.warning(
                self._parent_widget,
                "Import Completed with Errors",
                error_summary,
            )
        else:
            success_msg = f"Successfully imported {len(progress.imported_files)} file(s)."
            if progress.skipped_files:
                success_msg += f"\n\nSkipped {len(progress.skipped_files)} file(s) (already imported or no changes detected)."

            QMessageBox.information(
                self._parent_widget,
                "Import Successful",
                success_msg,
            )

        # Refresh file list via Redux action - EffectHandlerConnector will handle it
        from sleep_scoring_app.ui.store import Actions

        self.main_window.store.dispatch(Actions.refresh_files_requested())
        logger.info("Dispatched refresh_files_requested after import completion")

    def nonwear_import_finished(self, progress) -> None:
        """Handle nonwear import completion."""
        tab = self.main_window.data_settings_tab
        if tab is not None:
            try:
                tab.nwt_import_btn.setEnabled(False)
                tab.nwt_import_btn.setText("Import")

                # Update and hide progress components
                if tab.nwt_progress_label:
                    tab.nwt_progress_label.setText("Import completed")
                # Hide after a delay
                QTimer.singleShot(3000, lambda: self._hide_nonwear_progress_components())

                # Clear the file selection label and stored files
                tab._set_path_label_text(tab.nwt_import_files_label, "No files selected")
                self._selected_nonwear_files = []
            except AttributeError as e:
                logger.warning("Cannot update UI after nonwear import: %s", e)

        # Show results with detailed error messages if applicable
        if progress.errors:
            # Build detailed error message
            error_summary = f"Nonwear import completed with {len(progress.errors)} error(s):\n\n"
            # Show first 5 errors in detail
            displayed_errors = progress.errors[:5]
            for i, error in enumerate(displayed_errors, 1):
                error_summary += f"{i}. {error}\n\n"

            if len(progress.errors) > 5:
                error_summary += f"... and {len(progress.errors) - 5} more error(s).\n\n"

            # Add summary of what succeeded
            if progress.imported_nonwear_files:
                error_summary += f"\nSuccessfully imported: {len(progress.imported_nonwear_files)} file(s)"

            QMessageBox.warning(
                self._parent_widget,
                "Import Completed with Errors",
                error_summary,
            )
        else:
            QMessageBox.information(
                self._parent_widget,
                "Import Successful",
                f"Nonwear sensor data imported successfully. Imported {len(progress.imported_nonwear_files)} file(s).",
            )

        # Clear nonwear cache so next plot load gets fresh data
        try:
            self.services.data_service.clear_nonwear_cache()
        except Exception:
            logger.debug("Cannot clear nonwear cache - data service not available")

        # If a file is selected, reload nonwear data via main_window
        # (This is acceptable Qt glue - the cache was cleared, now we need to reload)
        state = self.main_window.store.state
        if state.current_file:
            try:
                self.main_window.load_nonwear_data_for_plot()
            except AttributeError:
                logger.debug("Cannot reload nonwear data for plot")

        # Refresh file list via Redux action
        from sleep_scoring_app.ui.store import Actions

        self.main_window.store.dispatch(Actions.refresh_files_requested())
        logger.info("Dispatched refresh_files_requested after nonwear import completion")

    def _hide_progress_components(self) -> None:
        """Hide activity progress components after import completion."""
        tab = self.main_window.data_settings_tab
        if tab is None:
            return
        try:
            if tab.activity_progress_label:
                tab.activity_progress_label.setVisible(False)
            if tab.activity_progress_bar:
                tab.activity_progress_bar.setVisible(False)
        except (AttributeError, RuntimeError) as e:
            logger.debug("Cannot hide activity progress components: %s", e)

    def _hide_nonwear_progress_components(self) -> None:
        """Hide nonwear progress components after import completion."""
        tab = self.main_window.data_settings_tab
        if tab is None:
            return
        try:
            if tab.nwt_progress_label:
                tab.nwt_progress_label.setVisible(False)
            if tab.nwt_progress_bar:
                tab.nwt_progress_bar.setVisible(False)
        except (AttributeError, RuntimeError) as e:
            logger.debug("Cannot hide nonwear progress components: %s", e)

    def load_data_folder(self) -> None:
        """Load data folder and enable UI."""
        folder_path = QFileDialog.getExistingDirectory(
            self._parent_widget,
            "Select folder containing CSV data files",
            "",  # Start in current directory
            QFileDialog.Option.ShowDirsOnly,
        )

        if folder_path:
            # Set the data folder and load files
            self.services.data_service.set_data_folder(folder_path)

            # Only load CSV files if we're in CSV mode
            if not self.services.data_service.get_database_mode():
                self.main_window.load_available_files(preserve_selection=False)
            else:
                # In database mode, load files from database with completion counts
                self.main_window.load_available_files(preserve_selection=False)

            self.main_window.set_ui_enabled(True)

            # Save to config
            self.services.config_manager.update_data_folder(folder_path)

            # Show feedback to user
            file_count = len(self.main_window.available_files)
            if file_count > 0:
                QMessageBox.information(
                    self._parent_widget,
                    "Folder Loaded",
                    f"Successfully loaded {file_count} CSV file{'s' if file_count != 1 else ''} from:\n\n{folder_path}\n\n"
                    "Files are now available in the file selector dropdown.",
                )
            else:
                QMessageBox.warning(
                    self._parent_widget,
                    "No Files Found",
                    f"No CSV files found in:\n\n{folder_path}\n\nPlease select a folder containing CSV data files.",
                )
