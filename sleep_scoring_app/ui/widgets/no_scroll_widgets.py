"""
No-Scroll Widgets.

Custom Qt widgets that only respond to wheel events when explicitly focused (clicked).
Prevents accidental value changes when scrolling past widgets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox, QTimeEdit

if TYPE_CHECKING:
    from PyQt6.QtGui import QWheelEvent


class NoScrollSpinBox(QSpinBox):
    """SpinBox that ignores wheel events unless explicitly focused by clicking."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # StrongFocus = can receive focus via Tab or clicking, but NOT by mouse hover
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, e: QWheelEvent | None) -> None:
        """Only handle wheel events if widget has focus (was clicked)."""
        if e is None:
            return
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            # Pass event to parent for scrolling
            e.ignore()


class NoScrollDoubleSpinBox(QDoubleSpinBox):
    """DoubleSpinBox that ignores wheel events unless explicitly focused by clicking."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, e: QWheelEvent | None) -> None:
        """Only handle wheel events if widget has focus (was clicked)."""
        if e is None:
            return
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class NoScrollComboBox(QComboBox):
    """ComboBox that ignores wheel events unless explicitly focused by clicking."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, e: QWheelEvent | None) -> None:
        """Only handle wheel events if widget has focus (was clicked)."""
        if e is None:
            return
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class NoScrollTimeEdit(QTimeEdit):
    """TimeEdit that ignores wheel events unless explicitly focused by clicking."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, e: QWheelEvent | None) -> None:
        """Only handle wheel events if widget has focus (was clicked)."""
        if e is None:
            return
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()
