"""
Marker connectors.

Connects marker mode, markers, adjacent markers, and autosave to the Redux store.
"""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.core.constants import MarkerCategory

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses_markers import DailyNonwearMarkers, DailySleepMarkers
    from sleep_scoring_app.ui.protocols import MainWindowProtocol
    from sleep_scoring_app.ui.store import UIState, UIStore

logger = logging.getLogger(__name__)


class MarkerModeConnector:
    """Connects the marker mode radio buttons to the store."""

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial update
        self._update_ui(store.state.marker_mode)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to marker mode changes."""
        if old_state.marker_mode != new_state.marker_mode:
            self._update_ui(new_state.marker_mode)

    def _update_ui(self, category: MarkerCategory) -> None:
        """Update radio buttons, plot widget mode, and deselect opposite markers."""
        tab = self.main_window.analysis_tab
        if not tab:
            return

        # Update radio buttons (temporarily block signals)
        tab.sleep_mode_btn.blockSignals(True)
        tab.nonwear_mode_btn.blockSignals(True)

        tab.sleep_mode_btn.setChecked(category == MarkerCategory.SLEEP)
        tab.nonwear_mode_btn.setChecked(category == MarkerCategory.NONWEAR)

        tab.sleep_mode_btn.blockSignals(False)
        tab.nonwear_mode_btn.blockSignals(False)

        # Update plot widget
        pw = self.main_window.plot_widget
        if pw:
            pw.set_active_marker_category(category)

            renderer = pw.marker_renderer
            if category == MarkerCategory.SLEEP:
                # Switching TO sleep mode:
                # 1. Deselect nonwear markers
                renderer.selected_nonwear_marker_index = 0
                renderer._update_nonwear_marker_visual_state_no_auto_select()
                # 2. Auto-select first sleep marker
                renderer.auto_select_marker_set()
            elif category == MarkerCategory.NONWEAR:
                # Switching TO nonwear mode:
                # 1. Deselect sleep markers AND clear sleep arrows
                renderer.selected_marker_set_index = 0
                renderer._update_marker_visual_state_no_auto_select()
                pw.clear_sleep_onset_offset_markers()  # Remove sleep rule arrows
                # 2. Auto-select first nonwear marker
                renderer.auto_select_nonwear_marker()

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class AdjacentMarkersConnector:
    """
    Connects adjacent markers checkbox to store and handles display.

    ARCHITECTURE: This connector:
    - Subscribes to store state changes
    - Calls MarkerService to load adjacent day markers (headless)
    - Updates plot widget directly (widget updates are connector's job)
    - Does NOT go through UIStateCoordinator
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial update
        self._update_checkbox(store.state.show_adjacent_markers)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """
        React to adjacent markers visibility or activity data changes.

        Reacts to activity data being loaded (not date changes) since the plot
        must have data before markers can be placed.
        """
        visibility_changed = old_state.show_adjacent_markers != new_state.show_adjacent_markers
        # React to activity data being loaded, not date changes
        # This ensures adjacent markers are added AFTER set_data_and_restrictions clears the plot
        data_loaded = old_state.activity_timestamps != new_state.activity_timestamps and len(new_state.activity_timestamps) > 0

        if visibility_changed:
            self._update_checkbox(new_state.show_adjacent_markers)
            self._toggle_markers(new_state)
        elif data_loaded and new_state.show_adjacent_markers:
            # Data loaded with checkbox checked - display adjacent markers
            self._toggle_markers(new_state)

    def _update_checkbox(self, enabled: bool) -> None:
        """Update checkbox state without triggering signals."""
        tab = self.main_window.analysis_tab
        if not tab:
            return

        tab.show_adjacent_day_markers_checkbox.blockSignals(True)
        tab.show_adjacent_day_markers_checkbox.setChecked(enabled)
        tab.show_adjacent_day_markers_checkbox.blockSignals(False)

    def _toggle_markers(self, state: UIState) -> None:
        """Toggle adjacent markers display on plot using service for data loading."""
        pw = self.main_window.plot_widget
        if not pw:
            return

        if not state.show_adjacent_markers:
            # Clear adjacent markers from plot
            try:
                pw.clear_adjacent_day_markers()
            except AttributeError:
                logger.debug("Plot widget does not have clear_adjacent_day_markers method")
            return

        # Load adjacent markers via service (headless)
        if not state.current_file or state.current_date_index < 0:
            return

        marker_service = getattr(self.main_window, "marker_service", None)
        if not marker_service:
            logger.warning("MarkerService not available for adjacent markers")
            return

        available_dates = list(state.available_dates)
        adjacent_markers = marker_service.load_adjacent_day_markers(
            filename=state.current_file,
            available_dates=available_dates,
            current_date_index=state.current_date_index,
        )

        # Update plot widget with loaded markers
        if adjacent_markers:
            try:
                pw.display_adjacent_day_markers(adjacent_markers)
                logger.info(f"Displayed {len(adjacent_markers)} adjacent day markers")
            except AttributeError:
                logger.debug("Plot widget does not have display_adjacent_day_markers method")

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class AutoSaveConnector:
    """Connects the auto-save checkbox, status label, and save time to the store."""

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial update
        self._update_enabled_ui(store.state.auto_save_enabled)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to auto-save state changes."""
        # Handle auto-save enabled toggle
        if old_state.auto_save_enabled != new_state.auto_save_enabled:
            self._update_enabled_ui(new_state.auto_save_enabled)

        # Handle date changes - reset label to default
        if old_state.current_date_index != new_state.current_date_index:
            self._reset_to_default_label()

        # Handle save time changes (update the "Saved at HH:MM:SS" label)
        if old_state.last_markers_save_time != new_state.last_markers_save_time:
            if new_state.last_markers_save_time is not None and new_state.auto_save_enabled:
                self._update_save_time_label(new_state.last_markers_save_time)

        # Handle dirty state changes (show "Unsaved" indicator)
        old_dirty = old_state.sleep_markers_dirty or old_state.nonwear_markers_dirty
        new_dirty = new_state.sleep_markers_dirty or new_state.nonwear_markers_dirty
        if old_dirty != new_dirty and new_state.auto_save_enabled:
            if new_dirty:
                self._show_unsaved_indicator()
            # Note: When saved, _update_save_time_label will be called which overwrites the label

    def _update_enabled_ui(self, enabled: bool) -> None:
        """
        Update checkbox and status label visibility.

        NOTE: Save button visibility is handled by SaveButtonConnector.
        This connector only manages the checkbox and autosave status label.
        """
        tab = self.main_window.analysis_tab
        if not tab:
            return

        # Update checkbox (Protocol-guaranteed attribute)
        tab.auto_save_checkbox.blockSignals(True)
        tab.auto_save_checkbox.setChecked(enabled)
        tab.auto_save_checkbox.blockSignals(False)

        # Update status label visibility (Protocol-guaranteed attribute)
        tab.autosave_status_label.setVisible(enabled)
        if enabled:
            # Reset to default when enabling
            tab.autosave_status_label.setText("Saved at N/A")
            tab.autosave_status_label.setStyleSheet("color: #333; font-size: 11px;")

    def _update_save_time_label(self, save_time: float) -> None:
        """Update the autosave status label with the save timestamp."""
        from datetime import datetime

        tab = self.main_window.analysis_tab
        if not tab:
            return

        # Convert Unix timestamp to readable time (Protocol-guaranteed attribute)
        timestamp = datetime.fromtimestamp(save_time).strftime("%H:%M:%S")
        tab.autosave_status_label.setText(f"Saved at {timestamp}")
        tab.autosave_status_label.setStyleSheet("color: #28a745; font-size: 11px;")  # Green when saved

    def _show_unsaved_indicator(self) -> None:
        """Show 'Unsaved' indicator when markers are modified."""
        tab = self.main_window.analysis_tab
        if not tab:
            return

        # Protocol-guaranteed attribute
        tab.autosave_status_label.setText("Unsaved changes...")
        tab.autosave_status_label.setStyleSheet("color: #dc3545; font-size: 11px;")  # Red when unsaved

    def _reset_to_default_label(self) -> None:
        """Reset the autosave status label to default state."""
        tab = self.main_window.analysis_tab
        if not tab:
            return

        # Protocol-guaranteed attribute
        tab.autosave_status_label.setText("Saved at N/A")
        tab.autosave_status_label.setStyleSheet("color: #333; font-size: 11px;")  # Black default

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class MarkersConnector:
    """
    Connects the marker state in Redux to the plot widget.

    Subscribes to marker changes and updates the plot widget accordingly.
    Handles clean load (dirty=False) vs manual changes (dirty=True).

    Also connects widget signals to dispatch actions (Widget -> Signal -> Connector -> Store).
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window

        # Track when THIS connector dispatches from widget signals.
        # Without these flags, the deepcopy in _load_markers_into_widget creates
        # an object identity mismatch: widget holds a copy, Redux holds the original.
        # When the widget dispatches its copy back, _on_state_change sees a new
        # identity and misclassifies it as an "external change" (diary, etc.),
        # triggering a full reload on every drag pixel.
        self._widget_dispatched_sleep = False
        self._widget_dispatched_nonwear = False

        self._unsubscribe = store.subscribe(self._on_state_change)

        # Connect widget signals to dispatch actions (Widget -> Connector -> Store)
        pw = main_window.plot_widget
        if pw:
            pw.sleep_period_selection_changed.connect(self._on_sleep_selection_signal)
            pw.nonwear_selection_changed.connect(self._on_nonwear_selection_signal)
            pw.sleep_markers_changed.connect(self._on_sleep_markers_signal)
            pw.nonwear_markers_changed.connect(self._on_nonwear_markers_signal)

        # Initial update
        self._update_plot(store.state)

    # ========== Widget Signal Handlers (Widget -> Connector -> Store) ==========

    def _on_sleep_selection_signal(self, index: int) -> None:
        """Handle sleep period selection signal from widget. Dispatch to store."""
        from sleep_scoring_app.ui.store import Actions

        logger.debug(f"MARKERS CONNECTOR: Widget emitted sleep selection: {index}")
        self.store.dispatch_async(Actions.selected_period_changed(index))

    def _on_nonwear_selection_signal(self, index: int) -> None:
        """Handle nonwear selection signal from widget. Dispatch to store."""
        from sleep_scoring_app.ui.store import Actions

        logger.debug(f"MARKERS CONNECTOR: Widget emitted nonwear selection: {index}")
        self.store.dispatch_async(Actions.selected_nonwear_changed(index))

    def _on_sleep_markers_signal(self, markers: Any) -> None:
        """Handle sleep markers changed signal from widget. Dispatch to store."""
        from sleep_scoring_app.ui.store import Actions

        logger.debug("MARKERS CONNECTOR: Widget emitted sleep_markers_changed")
        self._widget_dispatched_sleep = True
        try:
            self.store.dispatch(Actions.sleep_markers_changed(markers))
        finally:
            self._widget_dispatched_sleep = False

    def _on_nonwear_markers_signal(self, markers: Any) -> None:
        """Handle nonwear markers changed signal from widget. Dispatch to store."""
        from sleep_scoring_app.ui.store import Actions

        logger.debug("MARKERS CONNECTOR: Widget emitted nonwear_markers_changed")
        self._widget_dispatched_nonwear = True
        try:
            self.store.dispatch(Actions.nonwear_markers_changed(markers))
        finally:
            self._widget_dispatched_nonwear = False

    # ========== Store State Change Handler (Store -> Connector -> Widget) ==========

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """
        React to marker state changes.

        Key distinction:
        - markers_loaded (dirty stays False): Load markers FROM Redux INTO widget
        - sleep_markers_changed (dirty becomes True): Widget already has data, just update visuals
        - selection_changed: Update marker visual state (colors) without redrawing

        We use last_marker_update_time to detect changes since the same object
        may be dispatched (identity check would fail).
        """
        # Detect if markers were updated (timestamp changed)
        markers_updated = old_state.last_marker_update_time != new_state.last_marker_update_time

        # Also detect identity changes for initial loads
        sleep_markers_identity_changed = old_state.current_sleep_markers is not new_state.current_sleep_markers
        nonwear_markers_identity_changed = old_state.current_nonwear_markers is not new_state.current_nonwear_markers

        # Detect selection changes
        sleep_selection_changed = old_state.selected_period_index != new_state.selected_period_index
        nonwear_selection_changed = old_state.selected_nonwear_index != new_state.selected_nonwear_index

        # Detect save state changes
        sleep_dirty_changed = old_state.sleep_markers_dirty != new_state.sleep_markers_dirty
        nonwear_dirty_changed = old_state.nonwear_markers_dirty != new_state.nonwear_markers_dirty

        # LOAD: Identity changed AND not dirty (from DB)
        sleep_was_loaded = sleep_markers_identity_changed and not new_state.sleep_markers_dirty
        nonwear_was_loaded = nonwear_markers_identity_changed and not new_state.nonwear_markers_dirty

        # WIDGET CHANGE: Dispatched by this connector from widget signal (flag is set),
        # OR identity unchanged with dirty+updated (legacy same-object path).
        # The _widget_dispatched flags are needed because deepcopy in _load_markers_into_widget
        # makes widget and Redux hold different objects, so identity always differs on dispatch.
        sleep_widget_change = (self._widget_dispatched_sleep and new_state.sleep_markers_dirty) or (
            markers_updated and new_state.sleep_markers_dirty and not sleep_markers_identity_changed
        )
        nonwear_widget_change = (self._widget_dispatched_nonwear and new_state.nonwear_markers_dirty) or (
            markers_updated and new_state.nonwear_markers_dirty and not nonwear_markers_identity_changed
        )

        # EXTERNAL CHANGE: Identity changed AND dirty, but NOT from widget signal
        # (e.g., diary coordinator created new markers, manual time field entry)
        sleep_external_change = sleep_markers_identity_changed and new_state.sleep_markers_dirty and not self._widget_dispatched_sleep
        nonwear_external_change = nonwear_markers_identity_changed and new_state.nonwear_markers_dirty and not self._widget_dispatched_nonwear

        if sleep_was_loaded or nonwear_was_loaded or sleep_external_change or nonwear_external_change:
            # Markers loaded from DB OR created externally - sync FROM Redux TO widget
            logger.info(
                f"MARKERS CONNECTOR: Markers need widget sync. Loaded: sleep={sleep_was_loaded}, nonwear={nonwear_was_loaded}. External: sleep={sleep_external_change}, nonwear={nonwear_external_change}"
            )
            self._load_markers_into_widget(new_state, sleep_was_loaded or sleep_external_change, nonwear_was_loaded or nonwear_external_change)

        elif sleep_widget_change or nonwear_widget_change:
            # Markers changed by widget (mutation) - widget already has data, just update visual elements
            logger.info(f"MARKERS CONNECTOR: Markers CHANGED by widget. Sleep: {sleep_widget_change}, Nonwear: {nonwear_widget_change}")
            self._update_visual_elements(new_state, sleep_widget_change, nonwear_widget_change)

        # SELECTION: Update visual state (colors) and widget local state when selection changes
        if sleep_selection_changed:
            logger.info("MARKERS CONNECTOR: Sleep selection CHANGED")
            self._sync_sleep_selection_to_widget(new_state)
            self._update_sleep_selection_visual_state()

        if nonwear_selection_changed:
            logger.info("MARKERS CONNECTOR: Nonwear selection CHANGED")
            self._sync_nonwear_selection_to_widget(new_state)
            self._update_nonwear_selection_visual_state()

        # SAVE STATE: Sync dirty state to widget local state
        if sleep_dirty_changed:
            self._sync_sleep_saved_state_to_widget(new_state)

        if nonwear_dirty_changed:
            self._sync_nonwear_saved_state_to_widget(new_state)

    def _update_plot(self, state: UIState) -> None:
        """Initial load - update plot widget markers based on state."""
        self._load_markers_into_widget(state, load_sleep=True, load_nonwear=True)

    def _load_markers_into_widget(self, state: UIState, load_sleep: bool, load_nonwear: bool) -> None:
        """
        Load markers FROM Redux INTO widget (for DB loads, date navigation).

        Creates defensive copies and filters out-of-bounds periods BEFORE
        passing to the widget, so Redux state is never mutated by reference.
        """
        pw = self.main_window.plot_widget
        if not pw:
            return

        logger.info(f"MARKERS CONNECTOR: Loading markers into widget. Sleep: {load_sleep}, Nonwear: {load_nonwear}")

        # Collect warnings to emit AFTER blockSignals(False),
        # otherwise marker_limit_exceeded is suppressed.
        deferred_warnings: list[str] = []

        # Block signals to prevent widget from re-emitting changes
        pw.blockSignals(True)
        try:
            # Load Sleep Markers
            if load_sleep:
                if state.current_sleep_markers:
                    filtered, removed = self._copy_and_filter_sleep_markers(
                        state.current_sleep_markers,
                        pw.actual_data_bounds,
                    )
                    pw.load_daily_sleep_markers(filtered)
                    if removed > 0:
                        deferred_warnings.append(f"Warning: {removed} sleep period(s) were outside the data range and have been removed")
                    # Apply visual rules (arrows) if complete
                    selected_period = pw.get_selected_marker_period()
                    if selected_period and selected_period.is_complete:
                        pw.apply_sleep_scoring_rules(selected_period)
                else:
                    # Clear markers if new state has none
                    pw.clear_sleep_markers()
                    # Also clear sleep rule arrows
                    pw.clear_sleep_onset_offset_markers()

            # Load Nonwear Markers (use `is not None` — empty DailyNonwearMarkers is falsy due to __len__)
            if load_nonwear:
                if state.current_nonwear_markers is not None and len(state.current_nonwear_markers) > 0:
                    filtered, removed = self._copy_and_filter_nonwear_markers(
                        state.current_nonwear_markers,
                        pw.actual_data_bounds,
                    )
                    pw.load_daily_nonwear_markers(filtered)
                    if removed > 0:
                        deferred_warnings.append(f"Warning: {removed} nonwear period(s) were outside the data range and have been removed")
                else:
                    # Clear nonwear markers if new state has none
                    pw.clear_nonwear_markers()
        finally:
            pw.blockSignals(False)

        # Emit warnings after signals are unblocked
        for warning in deferred_warnings:
            pw.marker_limit_exceeded.emit(warning)

    def _copy_and_filter_sleep_markers(
        self,
        markers: DailySleepMarkers,
        data_bounds: tuple[float, float] | None,
    ) -> tuple[DailySleepMarkers, int]:
        """
        Deep-copy sleep markers and remove periods outside data bounds.

        Returns (filtered_copy, removed_count). The copy is safe to mutate
        without affecting Redux state.
        """
        markers_copy = copy.deepcopy(markers)
        if data_bounds is None:
            return markers_copy, 0

        data_start, data_end = data_bounds
        removed = 0
        for i in range(1, 5):
            period = markers_copy.get_period_by_slot(i)
            if period is None:
                continue
            if period.onset_timestamp is not None and not (data_start <= period.onset_timestamp <= data_end):
                logger.warning(
                    f"Sleep period {i} onset {period.onset_timestamp} outside data bounds [{data_start}, {data_end}] — removing from view copy"
                )
                markers_copy.set_period_by_slot(i, None)
                removed += 1
            elif period.offset_timestamp is not None and not (data_start <= period.offset_timestamp <= data_end):
                logger.warning(
                    f"Sleep period {i} offset {period.offset_timestamp} outside data bounds [{data_start}, {data_end}] — removing from view copy"
                )
                markers_copy.set_period_by_slot(i, None)
                removed += 1

        if removed > 0:
            markers_copy.update_classifications()
            logger.warning(f"Removed {removed} sleep period(s) outside data bounds (Redux state unchanged)")

        return markers_copy, removed

    def _copy_and_filter_nonwear_markers(
        self,
        markers: DailyNonwearMarkers,
        data_bounds: tuple[float, float] | None,
    ) -> tuple[DailyNonwearMarkers, int]:
        """
        Deep-copy nonwear markers and remove periods outside data bounds.

        Returns (filtered_copy, removed_count). The copy is safe to mutate
        without affecting Redux state.
        """
        markers_copy = copy.deepcopy(markers)
        if data_bounds is None:
            return markers_copy, 0

        data_start, data_end = data_bounds
        removed = 0
        for i in range(1, 11):
            period = markers_copy.get_period_by_slot(i)
            if period is None:
                continue
            if period.start_timestamp is not None and not (data_start <= period.start_timestamp <= data_end):
                logger.warning(
                    f"Nonwear period {i} start {period.start_timestamp} outside data bounds [{data_start}, {data_end}] — removing from view copy"
                )
                markers_copy.remove_period_by_slot(i)
                removed += 1
            elif period.end_timestamp is not None and not (data_start <= period.end_timestamp <= data_end):
                logger.warning(
                    f"Nonwear period {i} end {period.end_timestamp} outside data bounds [{data_start}, {data_end}] — removing from view copy"
                )
                markers_copy.remove_period_by_slot(i)
                removed += 1

        if removed > 0:
            logger.warning(f"Removed {removed} nonwear period(s) outside data bounds (Redux state unchanged)")

        return markers_copy, removed

    def _update_visual_elements(self, state: UIState, sleep_changed: bool, nonwear_changed: bool) -> None:
        """
        Update visual elements (arrows, tables) without reloading markers.

        Called when user changes markers - widget already has the data,
        just need to update dependent visual elements.
        """
        pw = self.main_window.plot_widget
        if not pw:
            return

        logger.debug(f"MARKERS CONNECTOR: Updating visuals only. Sleep: {sleep_changed}, Nonwear: {nonwear_changed}")

        if sleep_changed:
            # Update sleep scoring rule arrows for selected period
            selected_period = pw.get_selected_marker_period()
            if selected_period and selected_period.is_complete:
                pw.apply_sleep_scoring_rules(selected_period)

    def _update_sleep_selection_visual_state(self) -> None:
        """
        Update marker visual state (colors) when sleep selection changes.

        Called when selected_period_index changes.
        Updates marker colors to reflect selection without redrawing all markers.

        CRITICAL: When selection is 0 (intentional deselection), we MUST use
        _update_marker_visual_state_no_auto_select() to prevent auto-selection
        from re-selecting a marker.
        """
        pw = self.main_window.plot_widget
        if not pw:
            return

        logger.debug("MARKERS CONNECTOR: Updating sleep selection visual state")

        # Check if this is an intentional deselection (index 0)
        if self.store.state.selected_period_index == 0:
            # Use no-auto-select to prevent re-selection
            pw.marker_renderer._update_marker_visual_state_no_auto_select()
        else:
            pw.marker_renderer.update_marker_visual_state()
            # Only update arrows if a period is actually selected
            selected_period = pw.get_selected_marker_period()
            if selected_period and selected_period.is_complete:
                pw.apply_sleep_scoring_rules(selected_period)

    def _update_nonwear_selection_visual_state(self) -> None:
        """
        Update nonwear marker visual state (colors) when nonwear selection changes.

        Called when selected_nonwear_index changes.
        Updates marker colors to reflect selection without redrawing all markers.

        NOTE: Nonwear markers don't have auto-select, but we use the same pattern
        as sleep for consistency.
        """
        pw = self.main_window.plot_widget
        if not pw:
            return

        logger.debug("MARKERS CONNECTOR: Updating nonwear selection visual state")

        # Use consistent pattern with sleep markers
        if self.store.state.selected_nonwear_index == 0:
            pw.marker_renderer._update_nonwear_marker_visual_state_no_auto_select()
        else:
            pw.marker_renderer.update_nonwear_marker_visual_state()

    # ========== Sync Store State to Widget Local State ==========

    def _sync_sleep_selection_to_widget(self, state: UIState) -> None:
        """Sync sleep selection from store to widget local state."""
        pw = self.main_window.plot_widget
        if not pw:
            return
        if state.selected_period_index is not None:
            pw.set_selected_marker_set_index_from_store(state.selected_period_index)

    def _sync_nonwear_selection_to_widget(self, state: UIState) -> None:
        """Sync nonwear selection from store to widget local state."""
        pw = self.main_window.plot_widget
        if not pw:
            return
        pw.set_selected_nonwear_marker_index_from_store(state.selected_nonwear_index)

    def _sync_sleep_saved_state_to_widget(self, state: UIState) -> None:
        """Sync sleep saved state from store to widget local state."""
        pw = self.main_window.plot_widget
        if not pw:
            return
        pw.set_sleep_markers_saved_from_store(not state.sleep_markers_dirty)

    def _sync_nonwear_saved_state_to_widget(self, state: UIState) -> None:
        """Sync nonwear saved state from store to widget local state."""
        pw = self.main_window.plot_widget
        if not pw:
            return
        pw.set_nonwear_markers_saved_from_store(not state.nonwear_markers_dirty)

    def disconnect(self) -> None:
        """Cleanup subscription and signal connections."""
        self._unsubscribe()
        # Disconnect widget signals
        pw = self.main_window.plot_widget
        if pw:
            try:
                pw.sleep_period_selection_changed.disconnect(self._on_sleep_selection_signal)
                pw.nonwear_selection_changed.disconnect(self._on_nonwear_selection_signal)
                pw.sleep_markers_changed.disconnect(self._on_sleep_markers_signal)
                pw.nonwear_markers_changed.disconnect(self._on_nonwear_markers_signal)
            except (TypeError, RuntimeError):
                pass  # Already disconnected
