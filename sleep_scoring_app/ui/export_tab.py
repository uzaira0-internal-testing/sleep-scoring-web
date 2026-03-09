#!/usr/bin/env python3
"""
Export Tab Component
Contains export functionality and configuration options.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from sleep_scoring_app.core.constants import ButtonText
from sleep_scoring_app.ui.column_selection_dialog import ColumnSelectionDialog
from sleep_scoring_app.utils.column_registry import column_registry

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import (
        AppStateInterface,
        MarkerOperationsInterface,
        ServiceContainer,
    )
    from sleep_scoring_app.ui.store import UIStore

logger = logging.getLogger(__name__)


# TODO(refactor): pattern-violation ExportTab uses services as state bag (11 service call sites).
# Event handlers should emit signals; connectors should bridge to services/store.
class ExportTab(QWidget):
    """Export Tab for data export functionality."""

    def __init__(
        self,
        store: UIStore,
        marker_ops: MarkerOperationsInterface,
        app_state: AppStateInterface,
        services: ServiceContainer,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.marker_ops = marker_ops
        self.app_state = app_state
        self.services = services
        self.main_window_ref = parent  # Keep reference for transition

        # UI members
        self._cached_config = None
        self.summary_label = None  # Will be initialized in setup_ui

        self.setup_ui()

    def setup_ui(self) -> None:
        """Create the export tab UI."""
        logger.debug("=== ExportTab.setup_ui() START ===")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Initialize export configuration
        self._init_export_config()

        # Create scroll area with always-visible scrollbars
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        # Create content widget that will be scrollable
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(15)

        # Data summary section
        summary_group = self._create_data_summary_section()
        content_layout.addWidget(summary_group)

        # Column selection section
        columns_group = self._create_column_selection_section()
        content_layout.addWidget(columns_group)

        # Grouping options section
        grouping_group = self._create_grouping_options_section()
        content_layout.addWidget(grouping_group)

        # Output directory section
        output_group = self._create_output_directory_section()
        content_layout.addWidget(output_group)

        # Export options section
        options_group = self._create_export_options_section()
        content_layout.addWidget(options_group)

        # Export button
        self.export_btn = QPushButton("Export Data")
        # Delegate export via marker_ops interface (protocol guarantees method exists)
        self.export_btn.clicked.connect(self.marker_ops.perform_direct_export)

        self.export_btn.setToolTip("Export sleep markers and metrics to CSV with selected options")
        self.export_btn.setStyleSheet("font-weight: bold; padding: 12px; font-size: 14px; background-color: #2c3e50; color: white;")
        content_layout.addWidget(self.export_btn)

        content_layout.addStretch()

        # Set the content widget in the scroll area
        scroll_area.setWidget(content_widget)

        # Add scroll area to main layout
        layout.addWidget(scroll_area)

    def _init_export_config(self) -> None:
        """Initialize export configuration."""
        # Use services interface for config access
        if not getattr(self.services, "_export_config_initialized", False):
            # Get ALL possible export columns from column registry
            exportable_columns = column_registry.get_exportable()
            self.services.selected_export_columns = [col.export_column for col in exportable_columns if col.export_column]
            config = self.services.config_manager.config
            self.services.export_output_path = (config.export_directory if config else None) or str(Path.cwd() / "sleep_data_exports")

            # Ensure export directory exists
            Path(self.services.export_output_path).mkdir(parents=True, exist_ok=True)
            self.services._export_config_initialized = True

    def _create_data_summary_section(self) -> QGroupBox:
        """Create data summary section."""
        group = QGroupBox("Data Summary")
        layout = QVBoxLayout(group)

        # Create label and store reference for updates
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("padding: 10px; background-color: #f0f0f0; border-radius: 5px; font-weight: bold;")
        layout.addWidget(self.summary_label)

        # Populate with initial data
        self.refresh_data_summary()

        return group

    def refresh_data_summary(self) -> None:
        """Refresh the data summary section with current metrics from database."""
        if self.summary_label is None:
            return

        try:
            # Load metrics from database via services
            all_metrics = self.services.db_manager.load_sleep_metrics() if self.services.db_manager else []

            summary_lines = [f"Total records: {len(all_metrics)}"]

            if all_metrics:
                participants = set()
                groups = set()
                timepoints = set()

                for metrics in all_metrics:
                    # JUSTIFIED hasattr: Metrics structure may vary, participant may be None
                    if metrics.participant is not None:  # participant is a dataclass field
                        # JUSTIFIED hasattr: ParticipantInfo attributes may vary by version
                        if metrics.participant.numerical_id is not None:  # numerical_id is a dataclass field
                            participants.add(metrics.participant.numerical_id)
                        if metrics.participant.group_str is not None:  # group_str is a dataclass field
                            groups.add(metrics.participant.group_str)
                        if metrics.participant.timepoint_str is not None:  # timepoint_str is a dataclass field
                            timepoints.add(metrics.participant.timepoint_str)

                summary_lines.append(f"Participants: {len(participants)}")
                summary_lines.append(f"Groups: {len(groups)}")
                summary_lines.append(f"Timepoints: {len(timepoints)}")

            summary_text = " | ".join(summary_lines)
        except Exception as e:
            summary_text = f"Error loading data: {e}"

        self.summary_label.setText(summary_text)

    def _create_column_selection_section(self) -> QGroupBox:
        """Create column selection section with button to open dialog."""
        group = QGroupBox("Export Columns")
        layout = QHBoxLayout(group)

        self.column_count_label = QLabel()
        self._update_column_count()
        layout.addWidget(self.column_count_label)

        layout.addStretch()

        select_columns_btn = QPushButton("Select Columns...")
        select_columns_btn.clicked.connect(self._open_column_selection_dialog)
        select_columns_btn.setStyleSheet("font-weight: bold; padding: 8px 15px;")
        layout.addWidget(select_columns_btn)

        return group

    def _open_column_selection_dialog(self) -> None:
        """Open the column selection dialog."""
        dialog = ColumnSelectionDialog(self, self.services.selected_export_columns)
        if dialog.exec():
            self.services.selected_export_columns = dialog.get_selected_columns()
            self._update_column_count()

    def _update_column_count(self) -> None:
        """Update the column count label."""
        selected = len(self.services.selected_export_columns)
        # Count only toggleable columns (not always_exported)
        toggleable = len([c for c in column_registry.get_exportable() if c.export_column and not c.is_always_exported])
        always_exported = len([c for c in column_registry.get_exportable() if c.export_column and c.is_always_exported])
        self.column_count_label.setText(f"{selected}/{toggleable + always_exported} columns selected for export ({always_exported} always included)")

    def _create_grouping_options_section(self) -> QGroupBox:
        """Create grouping options section."""
        group = QGroupBox("Grouping Options")
        layout = QVBoxLayout(group)

        self.export_grouping_group = QButtonGroup()

        options = [
            (
                0,
                "All data in one file",
                "Export all participants and timepoints to a single CSV file",
            ),
            (
                1,
                "Separate file for each participant",
                "Create one CSV file per participant (e.g., 4001.csv, 4002.csv)",
            ),
            (
                2,
                "Separate file for each group",
                "Create one CSV file per participant group (e.g., G1.csv, G2.csv)",
            ),
            (
                3,
                "Separate file for each timepoint",
                "Create one CSV file per timepoint (e.g., BO.csv, P1.csv, P2.csv)",
            ),
        ]

        for i, (id, text, tooltip) in enumerate(options):
            radio = QRadioButton(text)
            radio.setChecked(i == 0)  # Default to first option
            radio.setToolTip(tooltip)
            self.export_grouping_group.addButton(radio, id)
            layout.addWidget(radio)

        # Restore saved preference via services
        config = self.services.config_manager.config
        saved_grouping = config.export_grouping if config else 0
        if 0 <= saved_grouping <= 3:
            button = self.export_grouping_group.button(saved_grouping)
            if button:
                button.setChecked(True)

        # Store reference in services for access
        self.services.export_grouping_group = self.export_grouping_group

        return group

    def _create_output_directory_section(self) -> QGroupBox:
        """Create output directory section."""
        group = QGroupBox("Output Directory")
        layout = QVBoxLayout(group)

        # Initialize with saved export directory or default via services
        config = self.services.config_manager.config
        saved_dir = config.export_directory if config else None
        dir_display = saved_dir if saved_dir else "No directory selected"
        self.export_output_label = QLabel(dir_display)
        self.export_output_label.setStyleSheet("padding: 8px; background-color: white; border: 1px solid #ccc; border-radius: 3px;")
        layout.addWidget(self.export_output_label)

        browse_btn = QPushButton(ButtonText.BROWSE)
        # MainWindowProtocol guarantees this method exists
        if self.main_window_ref is not None:
            browse_fn = getattr(self.main_window_ref, "browse_export_output_directory", None)
            if browse_fn is not None:
                browse_btn.clicked.connect(browse_fn)

        browse_btn.setStyleSheet("font-weight: bold; padding: 5px 10px;")
        layout.addWidget(browse_btn)

        # Set initial directory if saved
        if self.services.export_output_path and Path(self.services.export_output_path).exists():
            self.export_output_label.setText(self.services.export_output_path)

        # Store reference in services for access
        self.services.export_output_label = self.export_output_label

        return group

    def _create_export_options_section(self) -> QGroupBox:
        """Create export options section."""
        group = QGroupBox("Export Options")
        layout = QVBoxLayout(group)

        config = self.services.config_manager.config
        save_fn = getattr(self.main_window_ref, "save_export_options", None) if self.main_window_ref else None

        self.include_headers_checkbox = QCheckBox("Include column headers")
        self.include_headers_checkbox.setChecked(bool(config.include_headers if config else True))
        if save_fn is not None:
            self.include_headers_checkbox.stateChanged.connect(save_fn)
        layout.addWidget(self.include_headers_checkbox)

        self.include_metadata_checkbox = QCheckBox("Include metadata (participant info, dates)")
        self.include_metadata_checkbox.setChecked(bool(config.include_metadata if config else True))
        if save_fn is not None:
            self.include_metadata_checkbox.stateChanged.connect(save_fn)
        layout.addWidget(self.include_metadata_checkbox)

        self.separate_nonwear_file_checkbox = QCheckBox("Export nonwear markers to separate file")
        self.separate_nonwear_file_checkbox.setChecked(bool(getattr(config, "export_nonwear_separate", True) if config else True))
        self.separate_nonwear_file_checkbox.setToolTip(
            "When enabled, manual nonwear markers will be exported to a separate CSV file\n"
            "instead of being included as columns in the sleep data export."
        )
        if save_fn is not None:
            self.separate_nonwear_file_checkbox.stateChanged.connect(save_fn)
        layout.addWidget(self.separate_nonwear_file_checkbox)

        # Store references in services for access
        self.services.include_headers_checkbox = self.include_headers_checkbox
        self.services.include_metadata_checkbox = self.include_metadata_checkbox
        self.services.separate_nonwear_file_checkbox = self.separate_nonwear_file_checkbox

        return group
