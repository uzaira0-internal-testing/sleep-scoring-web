# Command Pattern Integration Guide

This document describes how to integrate the command pattern with `ActivityPlotWidget` for undo/redo functionality.

## Overview

The command pattern provides undo/redo for discrete marker operations:
- **PlaceMarkerCommand** - User clicked to place a marker (final position)
- **DeleteMarkerCommand** - User deleted a marker
- **MoveMarkerCommand** - User FINISHED dragging (from → to, not every pixel)
- **ClearAllMarkersCommand** - User cleared all markers

## Integration Steps

### 1. Add CommandHistory to ActivityPlotWidget

```python
from sleep_scoring_app.ui.commands import CommandHistory

class ActivityPlotWidget(pg.PlotWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(...)

        # Add command history
        self._command_history = CommandHistory(max_history=50)

        # Drag tracking for MoveMarkerCommand
        self._drag_start_timestamp: float | None = None
        self._dragging_marker_info: tuple[int, bool] | None = None  # (period_idx, is_onset)
```

### 2. Implement Keyboard Shortcuts

Add to `keyPressEvent`:

```python
def keyPressEvent(self, ev: QKeyEvent) -> None:
    """Handle keyboard shortcuts including undo/redo."""
    # Undo: Ctrl+Z
    if ev.modifiers() == Qt.KeyboardModifier.ControlModifier and ev.key() == Qt.Key.Key_Z:
        if self._command_history.undo():
            self.update_marker_visuals()
            self.sleep_markers_changed.emit(self.daily_sleep_markers)
        ev.accept()
        return

    # Redo: Ctrl+Shift+Z or Ctrl+Y
    if ev.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
        if ev.key() == Qt.Key.Key_Z:
            if self._command_history.redo():
                self.update_marker_visuals()
                self.sleep_markers_changed.emit(self.daily_sleep_markers)
            ev.accept()
            return
    elif ev.modifiers() == Qt.KeyboardModifier.ControlModifier and ev.key() == Qt.Key.Key_Y:
        if self._command_history.redo():
            self.update_marker_visuals()
            self.sleep_markers_changed.emit(self.daily_sleep_markers)
        ev.accept()
        return

    # ... existing key handling ...
    super().keyPressEvent(ev)
```

### 3. Update Marker Placement

Replace direct marker placement with command execution:

```python
from sleep_scoring_app.ui.commands import PlaceMarkerCommand

def place_marker(self, timestamp: float, is_onset: bool, period_index: int) -> None:
    """Place a marker using command pattern."""
    cmd = PlaceMarkerCommand(
        markers=self.daily_sleep_markers,
        timestamp=timestamp,
        is_onset=is_onset,
        period_index=period_index,
    )
    self._command_history.execute(cmd)
    self.update_marker_visuals()
    self.sleep_markers_changed.emit(self.daily_sleep_markers)
```

### 4. Implement Drag Handling

**CRITICAL**: Commands are ONLY for completed actions, not every pixel during drag.

```python
def on_mouse_down(self, event):
    """Record start of drag operation."""
    marker_info = self.find_marker_at(event.pos())
    if marker_info:
        period_idx, is_onset = marker_info
        period = self.daily_sleep_markers.get_period_by_slot(period_idx)
        if period:
            self._drag_start_timestamp = (
                period.onset_timestamp if is_onset else period.offset_timestamp
            )
            self._dragging_marker_info = marker_info

def on_mouse_move(self, event):
    """Update visual ONLY during drag - NO command."""
    if self._dragging_marker_info:
        # Just update visual, NO command
        new_ts = self.x_to_timestamp(event.x())
        period_idx, is_onset = self._dragging_marker_info
        period = self.daily_sleep_markers.get_period_by_slot(period_idx)
        if period:
            if is_onset:
                period.onset_timestamp = new_ts
            else:
                period.offset_timestamp = new_ts
            self.update_marker_visuals()

def on_mouse_up(self, event):
    """Create ONE MoveMarkerCommand for entire drag."""
    if self._dragging_marker_info and self._drag_start_timestamp:
        final_ts = self.x_to_timestamp(event.x())
        if final_ts != self._drag_start_timestamp:
            period_idx, is_onset = self._dragging_marker_info

            from sleep_scoring_app.ui.commands import MoveMarkerCommand

            cmd = MoveMarkerCommand(
                markers=self.daily_sleep_markers,
                period_index=period_idx,
                is_onset=is_onset,
                from_timestamp=self._drag_start_timestamp,
                to_timestamp=final_ts,
            )
            self._command_history.execute(cmd)
            self.sleep_markers_changed.emit(self.daily_sleep_markers)

    self._dragging_marker_info = None
    self._drag_start_timestamp = None
```

### 5. Update Delete Operation

```python
from sleep_scoring_app.ui.commands import DeleteMarkerCommand

def delete_marker(self, period_index: int, is_onset: bool) -> None:
    """Delete a marker using command pattern."""
    period = self.daily_sleep_markers.get_period_by_slot(period_index)
    if period is None:
        return

    # Get current timestamp before deletion
    deleted_timestamp = (
        period.onset_timestamp if is_onset else period.offset_timestamp
    )

    if deleted_timestamp is None:
        return  # Nothing to delete

    cmd = DeleteMarkerCommand(
        markers=self.daily_sleep_markers,
        period_index=period_index,
        is_onset=is_onset,
        deleted_timestamp=deleted_timestamp,
    )
    self._command_history.execute(cmd)
    self.update_marker_visuals()
    self.sleep_markers_changed.emit(self.daily_sleep_markers)
```

### 6. Implement Clear All

```python
from sleep_scoring_app.ui.commands import ClearAllMarkersCommand

def clear_all_markers(self) -> None:
    """Clear all markers using command pattern."""
    cmd = ClearAllMarkersCommand(self.daily_sleep_markers)
    self._command_history.execute(cmd)
    self.update_marker_visuals()
    self.sleep_markers_changed.emit(self.daily_sleep_markers)
```

### 7. Clear History on File/Date Change

```python
def load_new_file(self, file_path: str) -> None:
    """Load new file and clear command history."""
    # ... load file logic ...
    self._command_history.clear()
    # ... rest of load logic ...

def navigate_to_date(self, new_date: date) -> None:
    """Navigate to new date and clear command history."""
    # ... navigation logic ...
    self._command_history.clear()
    # ... rest of navigation logic ...
```

## Important Notes

1. **Commands are for COMPLETED actions only** - not every pixel during drag
2. **Always call update_marker_visuals()** after command execution/undo/redo
3. **Always emit sleep_markers_changed** signal to update UI
4. **Clear history** when loading new file or changing dates
5. **Check can_undo()/can_redo()** to enable/disable UI buttons if needed

## Example Menu Integration

If you have Edit menu:

```python
def setup_edit_menu(self):
    """Setup Edit menu with undo/redo."""
    edit_menu = self.menuBar().addMenu("&Edit")

    # Undo action
    undo_action = QAction("&Undo", self)
    undo_action.setShortcut(QKeySequence.StandardKey.Undo)  # Ctrl+Z
    undo_action.triggered.connect(self.undo)
    edit_menu.addAction(undo_action)

    # Redo action
    redo_action = QAction("&Redo", self)
    redo_action.setShortcut(QKeySequence.StandardKey.Redo)  # Ctrl+Y or Ctrl+Shift+Z
    redo_action.triggered.connect(self.redo)
    edit_menu.addAction(redo_action)

def undo(self):
    """Undo last command."""
    if self.plot_widget._command_history.undo():
        self.plot_widget.update_marker_visuals()
        # Update any UI state if needed

def redo(self):
    """Redo last undone command."""
    if self.plot_widget._command_history.redo():
        self.plot_widget.update_marker_visuals()
        # Update any UI state if needed
```

## Testing Checklist

- [ ] Ctrl+Z undoes last marker placement
- [ ] Ctrl+Y or Ctrl+Shift+Z redoes
- [ ] Drag creates ONE command on mouse_up, not per-pixel
- [ ] Undo/redo works for: place, move, delete, clear all
- [ ] History clears on file/date change
- [ ] Can_undo/can_redo return correct values
- [ ] Multiple undo/redo in sequence works correctly
- [ ] Redo stack clears when new action is performed
