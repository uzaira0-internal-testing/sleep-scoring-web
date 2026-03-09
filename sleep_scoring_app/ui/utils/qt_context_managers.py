"""
Context managers for Qt operations that require paired enable/disable calls.

This module provides context managers to safely handle Qt operations that require
cleanup, ensuring resources are properly released even if exceptions occur.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget


@contextmanager
def blocked_signals(widget: QWidget):
    """
    Context manager to safely block and unblock widget signals.

    Ensures signals are always unblocked even if an exception occurs,
    preventing UI freezes from permanently blocked signals.

    Args:
        widget: Qt widget whose signals should be temporarily blocked

    Example:
        with blocked_signals(self.combo_box):
            self.combo_box.clear()
            self.combo_box.addItems(items)

    """
    widget.blockSignals(True)
    try:
        yield
    finally:
        widget.blockSignals(False)


@contextmanager
def updates_disabled(widget: QWidget):
    """
    Context manager to safely disable and re-enable widget updates.

    Ensures updates are always re-enabled even if an exception occurs,
    preventing UI freezes from permanently disabled updates.

    Args:
        widget: Qt widget whose updates should be temporarily disabled

    Example:
        with updates_disabled(self.table):
            # Perform bulk table updates
            for row in rows:
                self.table.setItem(row, col, item)

    """
    widget.setUpdatesEnabled(False)
    try:
        yield
    finally:
        widget.setUpdatesEnabled(True)
