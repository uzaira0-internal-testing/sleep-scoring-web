"""
UI integration for algorithm-data compatibility enforcement.

This module provides helpers to integrate compatibility checking into the
PyQt6 UI, including:
- Detecting data source type from loaded files
- Updating UI to show compatibility status
- Disabling/enabling controls based on compatibility
- Showing user-friendly messages

Example Usage:
    >>> from sleep_scoring_app.ui.algorithm_compatibility_ui import (
    ...     AlgorithmCompatibilityUIHelper,
    ... )
    >>>
    >>> helper = AlgorithmCompatibilityUIHelper(main_window)
    >>>
    >>> # When file is loaded
    >>> helper.on_file_loaded("data.gt3x")
    >>>
    >>> # Check current compatibility
    >>> if helper.is_current_combination_compatible():
    ...     # Enable scoring
    ...     pass

References:
    - CLAUDE.md: PyQt6 patterns, Protocol-first design
    - core/algorithms/compatibility.py: Compatibility checking logic
    - core/pipeline/detector.py: Data source detection

"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sleep_scoring_app.core.pipeline.types import DataSourceType
    from sleep_scoring_app.ui.main_window import SleepScoringMainWindow

from sleep_scoring_app.core.algorithms.compatibility import (
    AlgorithmCompatibilityRegistry,
    AlgorithmDataCompatibilityChecker,
    CompatibilityResult,
    CompatibilityStatus,
)
from sleep_scoring_app.core.pipeline.detector import DataSourceDetector

logger = logging.getLogger(__name__)


class AlgorithmCompatibilityUIHelper:
    """
    Helper class for integrating compatibility checking into the UI.

    This class manages the interaction between file loading, data source
    detection, and UI updates to enforce algorithm compatibility.

    Attributes:
        main_window: Reference to the main window
        detector: Data source type detector
        checker: Compatibility checker
        current_data_source: Currently loaded data source type (None if no file loaded)
        current_algorithm_id: Currently selected algorithm ID

    Example:
        >>> helper = AlgorithmCompatibilityUIHelper(main_window)
        >>> helper.on_file_loaded("participant_data.gt3x")
        >>> if not helper.is_current_combination_compatible():
        ...     helper.show_incompatibility_warning()

    """

    def __init__(self, main_window: SleepScoringMainWindow) -> None:
        """
        Initialize the UI helper.

        Args:
            main_window: Reference to the main application window

        """
        self.main_window = main_window
        self.detector = DataSourceDetector()
        self.checker = AlgorithmDataCompatibilityChecker()

        # Track current state
        self.current_data_source: DataSourceType | None = None
        self.current_algorithm_id: str | None = None

    def on_file_loaded(self, file_path: str | Path) -> None:
        """
        Handle file loading and update compatibility state.

        This method should be called whenever a new data file is loaded.
        It detects the data source type and updates the UI accordingly.

        Args:
            file_path: Path to the loaded file

        Example:
            >>> helper.on_file_loaded("data/participant_001.gt3x")
            # Updates internal state and UI

        """
        try:
            # Detect data source type
            self.current_data_source = self.detector.detect_from_file(file_path)

            # Get current algorithm from config
            if self.main_window.config_manager is not None:  # Guaranteed after Phase 2
                config = self.main_window.config_manager.config
                self.current_algorithm_id = config.sleep_algorithm_id if config else None

            logger.info(
                f"File loaded: {Path(file_path).name}, "
                f"Data source: {self.current_data_source.value if self.current_data_source else 'unknown'}, "
                f"Algorithm: {self.current_algorithm_id}"
            )

            # Update UI based on compatibility
            self._update_ui_for_compatibility()

        except Exception as e:
            logger.warning(f"Could not detect data source type for {file_path}: {e}")
            self.current_data_source = None
            self._update_ui_for_compatibility()

    def on_algorithm_changed(self, algorithm_id: str) -> None:
        """
        Handle algorithm selection change.

        This method should be called whenever the user changes the algorithm
        in Study Settings.

        Args:
            algorithm_id: ID of the newly selected algorithm

        Example:
            >>> helper.on_algorithm_changed('van_hees_2015_sib')
            # Checks compatibility and updates UI

        """
        self.current_algorithm_id = algorithm_id

        logger.info(f"Algorithm changed to: {algorithm_id}")

        # Update UI based on new compatibility
        self._update_ui_for_compatibility()

    def is_current_combination_compatible(self) -> bool:
        """
        Check if current data source and algorithm are compatible.

        Returns:
            True if compatible or no data loaded, False if incompatible

        Example:
            >>> if not helper.is_current_combination_compatible():
            ...     print("Cannot score with this combination!")

        """
        # If no file loaded, assume compatible (nothing to check)
        if self.current_data_source is None:
            return True

        # If no algorithm selected, assume compatible
        if self.current_algorithm_id is None:
            return True

        # Check compatibility
        result = self.checker.check(
            self.current_data_source,
            self.current_algorithm_id,
        )

        return result.status != CompatibilityStatus.INCOMPATIBLE

    def get_current_compatibility_result(self) -> CompatibilityResult | None:
        """
        Get detailed compatibility result for current combination.

        Returns:
            CompatibilityResult or None if no data loaded

        Example:
            >>> result = helper.get_current_compatibility_result()
            >>> if result and result.status == CompatibilityStatus.INCOMPATIBLE:
            ...     print(result.reason)
            ...     print("Try these instead:", result.suggested_alternatives)

        """
        if self.current_data_source is None or self.current_algorithm_id is None:
            return None

        return self.checker.check(
            self.current_data_source,
            self.current_algorithm_id,
        )

    def show_incompatibility_warning(self) -> None:
        """
        Show a warning dialog explaining the incompatibility.

        This method displays a user-friendly message with:
        - Explanation of why the combination is incompatible
        - Suggested alternative algorithms
        - Option to change algorithm

        Example:
            >>> if not helper.is_current_combination_compatible():
            ...     helper.show_incompatibility_warning()

        """
        from PyQt6.QtWidgets import QMessageBox

        result = self.get_current_compatibility_result()
        if not result or result.status != CompatibilityStatus.INCOMPATIBLE:
            return

        # Get algorithm display name
        algo_info = AlgorithmCompatibilityRegistry.get(self.current_algorithm_id)
        algo_name = algo_info.display_name if algo_info else self.current_algorithm_id

        # Build message
        message = "<b>Incompatible Algorithm Selection</b><br><br>"
        message += f"<b>Current Algorithm:</b> {algo_name}<br>"
        message += f"<b>Data Type:</b> {result.data_source.value if result.data_source else 'Unknown'}<br><br>"
        message += f"<b>Issue:</b><br>{result.reason}<br><br>"

        # Add suggested alternatives
        if result.suggested_alternatives:
            message += "<b>Compatible Algorithms:</b><br>"
            for alt_id in result.suggested_alternatives[:5]:  # Show top 5
                alt_info = AlgorithmCompatibilityRegistry.get(alt_id)
                if alt_info:
                    message += f"• {alt_info.display_name}<br>"
            message += "<br>Please select a compatible algorithm in Study Settings."

        QMessageBox.warning(
            self.main_window,
            "Incompatible Algorithm",
            message,
        )

    def _update_ui_for_compatibility(self) -> None:
        """
        Update UI elements based on current compatibility status.

        This private method:
        - Enables/disables the Save Markers button
        - Shows/hides compatibility warnings
        - Updates tooltips

        """
        # Get compatibility result
        result = self.get_current_compatibility_result()

        # Update Save Markers button
        # MainWindowProtocol guarantees save_markers_btn exists
        save_btn = self.main_window.save_markers_btn
        if save_btn:
            if result and result.status == CompatibilityStatus.INCOMPATIBLE:
                # Disable button and update tooltip
                save_btn.setEnabled(False)
                algo_info = AlgorithmCompatibilityRegistry.get(self.current_algorithm_id)
                algo_name = algo_info.display_name if algo_info else self.current_algorithm_id

                save_btn.setToolTip(
                    f"❌ Scoring Blocked: {algo_name} cannot process this data type.\n\n"
                    f"{result.reason}\n\n"
                    f"Please select a compatible algorithm in Study Settings."
                )

                logger.warning(f"Save Markers button disabled: {result.reason}")

            elif result and result.status == CompatibilityStatus.REQUIRES_PREPROCESSING:
                # Enable button but update tooltip to inform about preprocessing
                save_btn.setEnabled(True)
                save_btn.setToolTip(f"✅ Compatible (with preprocessing)\n\n{result.reason}\n\nClick to score and save sleep markers.")

                logger.info(f"Save Markers button enabled with preprocessing: {result.reason}")

            elif result and result.status == CompatibilityStatus.COMPATIBLE:
                # Enable button with standard tooltip
                save_btn.setEnabled(True)
                save_btn.setToolTip("✅ Compatible\n\nClick to score and save sleep markers.")

                logger.info("Save Markers button enabled: Compatible combination")

            else:
                # No data loaded - enable button with default tooltip
                save_btn.setEnabled(True)
                save_btn.setToolTip("Score and save sleep markers for the current day")

        # Update status bar or other UI elements if needed
        self._update_status_indicator(result)

    def _update_status_indicator(self, result) -> None:
        """
        Update the status bar indicator to show compatibility status.

        Shows a colored indicator in the main window's status bar:
        - Green: Compatible
        - Yellow: Requires preprocessing
        - Red: Incompatible
        - Gray: No data loaded

        Args:
            result: CompatibilityResult or None

        """
        # Check if main window has the compatibility label
        if self.main_window.algorithm_compat_label is None:  # Guaranteed after setup_ui
            return

        label = self.main_window.algorithm_compat_label

        if result is None:
            # No data loaded or no algorithm selected
            label.setText("")
            label.setToolTip("Load a file to check algorithm compatibility")
            label.setStyleSheet("padding: 0 10px; font-weight: bold;")
            return

        # Get algorithm display name
        algo_info = AlgorithmCompatibilityRegistry.get(self.current_algorithm_id)
        algo_name = algo_info.display_name if algo_info else self.current_algorithm_id

        if result.status == CompatibilityStatus.COMPATIBLE:
            label.setText("✓ Compatible")
            label.setStyleSheet("padding: 0 10px; font-weight: bold; color: #27ae60;")  # Green
            label.setToolTip(f"Algorithm '{algo_name}' is compatible with the loaded data")

        elif result.status == CompatibilityStatus.REQUIRES_PREPROCESSING:
            label.setText("⚙ Preprocessing")
            label.setStyleSheet("padding: 0 10px; font-weight: bold; color: #f39c12;")  # Yellow/Orange
            label.setToolTip(
                f"Algorithm '{algo_name}' requires preprocessing\n\n{result.reason}\n\nData will be automatically preprocessed before scoring."
            )

        elif result.status == CompatibilityStatus.INCOMPATIBLE:
            label.setText("✗ Incompatible")
            label.setStyleSheet("padding: 0 10px; font-weight: bold; color: #e74c3c;")  # Red
            tooltip = f"Algorithm '{algo_name}' cannot process this data type\n\n{result.reason}"
            if result.suggested_alternatives:
                tooltip += "\n\nCompatible alternatives:\n"
                for alt_id in result.suggested_alternatives[:3]:
                    alt_info = AlgorithmCompatibilityRegistry.get(alt_id)
                    if alt_info:
                        tooltip += f"  • {alt_info.display_name}\n"
            label.setToolTip(tooltip)

        else:
            # Unknown status
            label.setText("")
            label.setToolTip("")
            label.setStyleSheet("padding: 0 10px; font-weight: bold;")

    def get_compatible_algorithm_ids(self) -> list[str]:
        """
        Get list of algorithm IDs compatible with current data source.

        Returns:
            List of compatible algorithm IDs, or all if no data loaded

        Example:
            >>> compatible_ids = helper.get_compatible_algorithm_ids()
            >>> # Use to filter dropdown in UI

        """
        if self.current_data_source is None:
            # No data loaded - return all algorithms
            all_algos = AlgorithmCompatibilityRegistry.get_all()
            return [algo.algorithm_id for algo in all_algos]

        # Get compatible algorithms for current data source
        compatible_infos = AlgorithmCompatibilityRegistry.get_compatible(self.current_data_source)
        return [info.algorithm_id for info in compatible_infos]

    def get_incompatible_algorithm_ids(self) -> list[str]:
        """
        Get list of algorithm IDs incompatible with current data source.

        Returns:
            List of incompatible algorithm IDs, or empty if no data loaded

        Example:
            >>> incompatible_ids = helper.get_incompatible_algorithm_ids()
            >>> # Use to gray out options in UI

        """
        if self.current_data_source is None:
            return []

        # Get all algorithms
        all_algos = AlgorithmCompatibilityRegistry.get_all()
        all_ids = {algo.algorithm_id for algo in all_algos}

        # Get compatible ones
        compatible_ids = set(self.get_compatible_algorithm_ids())

        # Return the difference
        return list(all_ids - compatible_ids)
