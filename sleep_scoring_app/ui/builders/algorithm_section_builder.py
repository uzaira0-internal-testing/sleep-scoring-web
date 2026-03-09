"""
Algorithm Section Builder
Constructs the algorithm configuration UI section.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTime
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sleep_scoring_app.core.constants import (
    ActivityDataPreference,
    AlgorithmHelpText,
    AlgorithmTooltip,
    ParadigmStyle,
    SettingsSection,
    StudyDataParadigm,
)
from sleep_scoring_app.services.algorithm_service import get_algorithm_service
from sleep_scoring_app.ui.widgets.no_scroll_widgets import NoScrollComboBox, NoScrollTimeEdit

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QComboBox, QTimeEdit

    from sleep_scoring_app.ui.utils.config import ConfigManager

logger = logging.getLogger(__name__)


class AlgorithmSectionBuilder:
    """Builder for the algorithm configuration section."""

    def __init__(self, config_manager: ConfigManager) -> None:
        """
        Initialize the builder.

        Args:
            config_manager: Configuration manager for accessing current settings

        """
        self.config_manager = config_manager

        # Algorithm widgets
        self.sleep_algorithm_combo: QComboBox | None = None
        self.sleep_period_detector_combo: QComboBox | None = None
        self.night_start_time: QTimeEdit | None = None
        self.night_end_time: QTimeEdit | None = None
        self.nonwear_algorithm_combo: QComboBox | None = None
        self.choi_axis_combo: QComboBox | None = None
        self.choi_axis_widget: QWidget | None = None

    def build(self) -> QGroupBox:
        """
        Build the algorithm configuration section.

        Returns:
            QGroupBox containing the algorithm configuration UI

        """
        group_box = QGroupBox(SettingsSection.ALGORITHM_SETTINGS)
        layout = QVBoxLayout(group_box)
        layout.setSpacing(15)

        # Sleep/Wake Algorithm Selection
        algorithm_layout = self._create_sleep_algorithm_section()
        layout.addLayout(algorithm_layout)

        # Onset/Offset Rule Selection
        rule_layout = self._create_sleep_period_detector_section()
        layout.addLayout(rule_layout)

        # Night Hours Configuration
        night_hours_layout = self._create_night_hours_section()
        layout.addLayout(night_hours_layout)

        # Nonwear Detection Algorithm Selection
        nonwear_layout = self._create_nonwear_algorithm_section()
        layout.addLayout(nonwear_layout)

        # Choi Algorithm Axis Selection
        self.choi_axis_widget = self._create_choi_axis_section()
        layout.addWidget(self.choi_axis_widget)
        logger.info(
            "=== AlgorithmSectionBuilder.build(): choi_axis_widget created: %s, visible=%s ===",
            self.choi_axis_widget,
            self.choi_axis_widget.isVisible() if self.choi_axis_widget else "N/A",
        )

        return group_box

    def _create_sleep_algorithm_section(self) -> QVBoxLayout:
        """Create the sleep/wake algorithm selection section."""
        algorithm_layout = QVBoxLayout()

        algorithm_label = QLabel("<b>Sleep/Wake Algorithm:</b>")
        algorithm_label.setStyleSheet(ParadigmStyle.LABEL)
        algorithm_layout.addWidget(algorithm_label)

        algorithm_row = QHBoxLayout()
        self.sleep_algorithm_combo = NoScrollComboBox()

        # Populate from factory - will be filtered by paradigm later
        self._populate_algorithm_combo()

        self.sleep_algorithm_combo.setSizeAdjustPolicy(NoScrollComboBox.SizeAdjustPolicy.AdjustToContents)
        self.sleep_algorithm_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.sleep_algorithm_combo.setToolTip(AlgorithmTooltip.SLEEP_ALGORITHM_COMBO)
        algorithm_row.addWidget(self.sleep_algorithm_combo)
        algorithm_row.addStretch()
        algorithm_layout.addLayout(algorithm_row)

        # Algorithm info label
        algorithm_help = QLabel(AlgorithmHelpText.SLEEP_ALGORITHM)
        algorithm_help.setWordWrap(True)
        algorithm_help.setStyleSheet("QLabel { color: #7f8c8d; font-size: 11px; font-style: italic; }")
        algorithm_layout.addWidget(algorithm_help)

        return algorithm_layout

    def _create_sleep_period_detector_section(self) -> QVBoxLayout:
        """Create the sleep period detector selection section."""
        rule_layout = QVBoxLayout()

        rule_label = QLabel("<b>Onset/Offset Detection Rule:</b>")
        rule_label.setStyleSheet("QLabel { color: #2c3e50; margin-bottom: 5px; }")
        rule_layout.addWidget(rule_label)

        rule_row = QHBoxLayout()
        self.sleep_period_detector_combo = NoScrollComboBox()

        # Populate from factory - will be filtered by paradigm later
        self._populate_sleep_period_detector_combo()

        self.sleep_period_detector_combo.setSizeAdjustPolicy(NoScrollComboBox.SizeAdjustPolicy.AdjustToContents)
        self.sleep_period_detector_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.sleep_period_detector_combo.setToolTip(
            "Select the rule for detecting sleep onset and offset times.\n"
            "• Epoch-based paradigm: Consecutive 3/5, Consecutive 5/10, Tudor-Locke (2014)\n"
            "• Raw accelerometer paradigm: HDCZA (automatic SPT detection from z-angle)"
        )
        rule_row.addWidget(self.sleep_period_detector_combo)
        rule_row.addStretch()
        rule_layout.addLayout(rule_row)

        # Rule info label
        rule_help = QLabel(
            "The onset/offset rule determines how sleep start and end times are refined within the marked period. "
            "Tudor-Locke uses a different approach that looks for consecutive wake epochs for offset detection."
        )
        rule_help.setWordWrap(True)
        rule_help.setStyleSheet("QLabel { color: #7f8c8d; font-size: 11px; font-style: italic; }")
        rule_layout.addWidget(rule_help)

        return rule_layout

    def _create_night_hours_section(self) -> QVBoxLayout:
        """Create the night hours configuration section."""
        night_hours_layout = QVBoxLayout()

        night_hours_label = QLabel("<b>Night Hours Definition:</b>")
        night_hours_label.setStyleSheet("QLabel { color: #2c3e50; margin-bottom: 5px; }")
        night_hours_layout.addWidget(night_hours_label)

        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Start:"))

        self.night_start_time = NoScrollTimeEdit()
        self.night_start_time.setDisplayFormat("HH:mm")
        self.night_start_time.setToolTip("Start of night period (default: 22:00)")
        self.night_start_time.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        time_layout.addWidget(self.night_start_time)

        time_layout.addWidget(QLabel("End:"))

        self.night_end_time = NoScrollTimeEdit()
        self.night_end_time.setDisplayFormat("HH:mm")
        self.night_end_time.setToolTip("End of night period (default: 07:00)")
        self.night_end_time.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        time_layout.addWidget(self.night_end_time)

        time_layout.addStretch()
        night_hours_layout.addLayout(time_layout)

        # Info label
        night_help = QLabel("Used for night period classification in sleep analysis")
        night_help.setStyleSheet("QLabel { color: #7f8c8d; font-size: 11px; font-style: italic; }")
        night_hours_layout.addWidget(night_help)

        return night_hours_layout

    def _create_nonwear_algorithm_section(self) -> QVBoxLayout:
        """Create the nonwear algorithm selection section."""
        nonwear_layout = QVBoxLayout()

        nonwear_label = QLabel("<b>Nonwear Detection Algorithm:</b>")
        nonwear_label.setStyleSheet("QLabel { color: #2c3e50; margin-bottom: 5px; }")
        nonwear_layout.addWidget(nonwear_label)

        nonwear_row = QHBoxLayout()
        self.nonwear_algorithm_combo = NoScrollComboBox()

        # Populate from algorithm service
        available_nonwear = get_algorithm_service().get_available_nonwear_algorithms()
        for algo_id, algo_name in available_nonwear.items():
            self.nonwear_algorithm_combo.addItem(algo_name, algo_id)

        self.nonwear_algorithm_combo.setSizeAdjustPolicy(NoScrollComboBox.SizeAdjustPolicy.AdjustToContents)
        self.nonwear_algorithm_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.nonwear_algorithm_combo.setToolTip(
            "Select the algorithm for detecting nonwear periods.\n• Choi (2011): Standard algorithm using 90-minute windows with spike tolerance"
        )
        nonwear_row.addWidget(self.nonwear_algorithm_combo)
        nonwear_row.addStretch()
        nonwear_layout.addLayout(nonwear_row)

        # Nonwear algorithm info label
        nonwear_help = QLabel(
            "The nonwear detection algorithm identifies periods when the device was not worn. "
            "Choi (2011) is the standard validated algorithm for ActiGraph devices."
        )
        nonwear_help.setWordWrap(True)
        nonwear_help.setStyleSheet("QLabel { color: #7f8c8d; font-size: 11px; font-style: italic; }")
        nonwear_layout.addWidget(nonwear_help)

        return nonwear_layout

    def _create_choi_axis_section(self) -> QWidget:
        """Create the Choi axis selection section."""
        choi_axis_widget = QWidget()
        choi_layout = QVBoxLayout(choi_axis_widget)
        choi_layout.setContentsMargins(0, 0, 0, 0)

        choi_label = QLabel("<b>Choi Nonwear Detection Axis:</b>")
        choi_label.setStyleSheet("QLabel { color: #2c3e50; margin-bottom: 5px; }")
        choi_layout.addWidget(choi_label)

        choi_row = QHBoxLayout()
        self.choi_axis_combo = NoScrollComboBox()

        choi_axis_display_names = {
            ActivityDataPreference.VECTOR_MAGNITUDE: "Vector Magnitude (Recommended)",
            ActivityDataPreference.AXIS_Y: "Y-Axis (Vertical)",
            ActivityDataPreference.AXIS_X: "X-Axis (Lateral)",
            ActivityDataPreference.AXIS_Z: "Z-Axis (Forward)",
        }
        for axis in ActivityDataPreference:
            self.choi_axis_combo.addItem(choi_axis_display_names[axis], axis.value)

        self.choi_axis_combo.setSizeAdjustPolicy(NoScrollComboBox.SizeAdjustPolicy.AdjustToContents)
        self.choi_axis_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        choi_row.addWidget(self.choi_axis_combo)
        choi_row.addStretch()
        choi_layout.addLayout(choi_row)

        # Info label
        choi_help = QLabel(
            "Select which activity axis the Choi nonwear detection algorithm should use. Vector Magnitude is recommended for most devices."
        )
        choi_help.setWordWrap(True)
        choi_help.setStyleSheet("QLabel { color: #7f8c8d; font-size: 11px; font-style: italic; }")
        choi_layout.addWidget(choi_help)

        return choi_axis_widget

    def _populate_algorithm_combo(self) -> None:
        """Populate sleep algorithm combo with all available algorithms."""
        if self.sleep_algorithm_combo is None:
            return

        available_algorithms = get_algorithm_service().get_available_sleep_algorithms()
        for algo_id, algo_name in available_algorithms.items():
            self.sleep_algorithm_combo.addItem(algo_name, algo_id)

    def _populate_sleep_period_detector_combo(self) -> None:
        """Populate sleep period detector combo with all available detectors."""
        if self.sleep_period_detector_combo is None:
            return

        available_detectors = get_algorithm_service().get_available_sleep_period_detectors()
        for detector_id, detector_name in available_detectors.items():
            self.sleep_period_detector_combo.addItem(detector_name, detector_id)

    def update_for_paradigm(self, paradigm: StudyDataParadigm) -> None:
        """
        Update algorithm options based on selected paradigm.

        Args:
            paradigm: The selected data paradigm

        """
        if self.sleep_algorithm_combo is None or self.sleep_period_detector_combo is None:
            return

        # Block signals to prevent triggering change handlers during repopulation
        self.sleep_algorithm_combo.blockSignals(True)
        self.sleep_period_detector_combo.blockSignals(True)
        try:
            # Store current selections
            current_algo_id = self.sleep_algorithm_combo.currentData()
            current_detector_id = self.sleep_period_detector_combo.currentData()

            # Repopulate sleep algorithm combo with compatible algorithms
            self.sleep_algorithm_combo.clear()
            available_algorithms = get_algorithm_service().get_available_sleep_algorithms()
            for algo_id, algo_name in available_algorithms.items():
                if paradigm.is_algorithm_compatible(algo_id):
                    self.sleep_algorithm_combo.addItem(algo_name, algo_id)

            # Try to restore previous selection if still compatible
            if current_algo_id and paradigm.is_algorithm_compatible(current_algo_id):
                for i in range(self.sleep_algorithm_combo.count()):
                    if self.sleep_algorithm_combo.itemData(i) == current_algo_id:
                        self.sleep_algorithm_combo.setCurrentIndex(i)
                        break

            # Repopulate sleep period detector combo with compatible detectors
            self.sleep_period_detector_combo.clear()
            available_detectors = get_algorithm_service().get_available_sleep_period_detectors()
            for detector_id, detector_name in available_detectors.items():
                if paradigm.is_sleep_period_detector_compatible(detector_id):
                    self.sleep_period_detector_combo.addItem(detector_name, detector_id)

            # Try to restore previous selection if still compatible
            if current_detector_id and paradigm.is_sleep_period_detector_compatible(current_detector_id):
                for i in range(self.sleep_period_detector_combo.count()):
                    if self.sleep_period_detector_combo.itemData(i) == current_detector_id:
                        self.sleep_period_detector_combo.setCurrentIndex(i)
                        break
        finally:
            self.sleep_algorithm_combo.blockSignals(False)
            self.sleep_period_detector_combo.blockSignals(False)

    def get_combo_boxes(
        self,
    ) -> tuple[QComboBox, QComboBox, QComboBox, QComboBox]:
        """
        Get the algorithm combo box widgets.

        Returns:
            Tuple of (sleep_algorithm_combo, sleep_period_detector_combo, nonwear_algorithm_combo, choi_axis_combo)

        """
        if (
            self.sleep_algorithm_combo is None
            or self.sleep_period_detector_combo is None
            or self.nonwear_algorithm_combo is None
            or self.choi_axis_combo is None
        ):
            msg = "Builder must be built before accessing combo boxes"
            raise RuntimeError(msg)
        return (
            self.sleep_algorithm_combo,
            self.sleep_period_detector_combo,
            self.nonwear_algorithm_combo,
            self.choi_axis_combo,
        )

    def get_time_edits(self) -> tuple[QTimeEdit, QTimeEdit]:
        """
        Get the night hours time edit widgets.

        Returns:
            Tuple of (night_start_time, night_end_time)

        """
        if self.night_start_time is None or self.night_end_time is None:
            msg = "Builder must be built before accessing time edits"
            raise RuntimeError(msg)
        return self.night_start_time, self.night_end_time

    def load_from_config(self) -> None:
        """Load algorithm settings from config."""
        config = self.config_manager.config
        if config is None:
            return

        # Load sleep algorithm
        if self.sleep_algorithm_combo is not None:
            for i in range(self.sleep_algorithm_combo.count()):
                if self.sleep_algorithm_combo.itemData(i) == config.sleep_algorithm:
                    self.sleep_algorithm_combo.setCurrentIndex(i)
                    break

        # Load sleep period detector
        if self.sleep_period_detector_combo is not None:
            for i in range(self.sleep_period_detector_combo.count()):
                if self.sleep_period_detector_combo.itemData(i) == config.sleep_period_detector_algorithm:
                    self.sleep_period_detector_combo.setCurrentIndex(i)
                    break

        # Load night hours
        if self.night_start_time is not None and self.night_end_time is not None:
            self.night_start_time.setTime(QTime(config.night_start_hour, config.night_start_minute))
            self.night_end_time.setTime(QTime(config.night_end_hour, config.night_end_minute))

        # Load nonwear algorithm
        if self.nonwear_algorithm_combo is not None:
            for i in range(self.nonwear_algorithm_combo.count()):
                if self.nonwear_algorithm_combo.itemData(i) == config.nonwear_algorithm:
                    self.nonwear_algorithm_combo.setCurrentIndex(i)
                    break

        # Load Choi axis
        if self.choi_axis_combo is not None:
            for i in range(self.choi_axis_combo.count()):
                if self.choi_axis_combo.itemData(i) == config.choi_nonwear_axis:
                    self.choi_axis_combo.setCurrentIndex(i)
                    break
