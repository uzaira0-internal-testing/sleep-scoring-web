#!/usr/bin/env python3
"""
Drag-and-Drop List Widget
Reusable list widget with drag-and-drop reordering and inline editing.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QListWidget, QListWidgetItem, QMessageBox, QWidget

logger = logging.getLogger(__name__)


class DragDropListWidget(QListWidget):
    """Custom list widget with drag-and-drop reordering and inline editing."""

    items_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        # Enable inline editing on double-click
        self.itemDoubleClicked.connect(self._edit_item)

        # Track changes for validation and auto-save
        self.model().rowsMoved.connect(self.items_changed.emit)
        self.model().rowsInserted.connect(self.items_changed.emit)
        self.model().rowsRemoved.connect(self.items_changed.emit)
        self.itemChanged.connect(self.items_changed.emit)  # For inline edits

    def _edit_item(self, item: QListWidgetItem) -> None:
        """Enable inline editing for an item."""
        if item:
            # Get the current text
            current_text = item.text()

            # Open input dialog for editing
            text, ok = QInputDialog.getText(
                self,
                "Edit Item",
                "Edit item name:",
                text=current_text,
            )

            if ok and text.strip():
                new_text = text.strip().upper()

                # Check for duplicates (excluding current item)
                existing_items = []
                for i in range(self.count()):
                    if i != self.row(item):
                        existing_items.append(self.item(i).text())

                if new_text not in existing_items:
                    item.setText(new_text)
                    self.items_changed.emit()
                    logger.debug("Edited item: %s -> %s", current_text, new_text)
                else:
                    QMessageBox.information(self, "Duplicate Item", f"Item '{new_text}' already exists.")

    def add_item_with_validation(self, text: str) -> bool:
        """Add an item with duplicate validation."""
        text = text.strip().upper()

        # Check for duplicates
        existing_items = [self.item(i).text() for i in range(self.count())]
        if text in existing_items:
            return False

        self.addItem(text)
        self.items_changed.emit()
        return True

    def get_all_items(self) -> list[str]:
        """Get all items as a list of strings."""
        return [self.item(i).text() for i in range(self.count())]
