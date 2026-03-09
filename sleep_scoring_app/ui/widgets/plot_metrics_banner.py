"""
Plot Metrics Banner - Thin overlay strip for displaying key metrics above the activity plot.

A dumb widget (per CLAUDE.md architecture) that receives metric items and renders them
as a horizontal strip. Does NOT access the store or services directly - a connector
feeds it data.

Usage (future - not wired up yet):
    banner = PlotMetricsBanner(parent=some_widget)
    banner.set_items([
        MetricItem(label="TST", value="412 min", color="#673ab7"),
        MetricItem(label="SE", value="89.2%"),
        MetricItem(label="WASO", value="18 min"),
    ])
    banner.clear()
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


@dataclass(frozen=True)
class MetricItem:
    """
    Single metric to display in the banner.

    Attributes:
        label: Short label (e.g. "TST", "SE", "WASO").
        value: Formatted display value (e.g. "412 min", "89.2%").
        color: Optional hex color for the value text. Defaults to foreground.

    """

    label: str
    value: str
    color: str | None = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BANNER_HEIGHT = 22
_LABEL_FONT_SIZE = 8
_VALUE_FONT_SIZE = 9
_SEPARATOR = "  \u2502  "  # thin vertical bar between items


class PlotMetricsBanner(QWidget):
    """
    Thin horizontal strip that displays a row of key-value metric items.

    The banner is designed to sit directly above (or overlaid on top of) the
    activity plot.  It is intentionally *dumb*: call ``set_items`` to populate
    it and ``clear`` to hide content.  A future connector will subscribe to the
    Redux store and feed data here.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(_BANNER_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.04); border-bottom: 1px solid rgba(0, 0, 0, 0.08);")

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 0, 8, 0)
        self._layout.setSpacing(0)

        # Permanent container label (single QLabel for the whole strip)
        self._content_label = QLabel()
        self._content_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._content_label.setTextFormat(Qt.TextFormat.RichText)

        font = QFont()
        font.setPointSize(_VALUE_FONT_SIZE)
        self._content_label.setFont(font)

        self._layout.addWidget(self._content_label, stretch=1)

        # Start hidden - nothing to show until set_items is called
        self.setVisible(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_items(self, items: list[MetricItem]) -> None:
        """
        Replace displayed metrics with *items*.

        Passing an empty list hides the banner.
        """
        if not items:
            self.clear()
            return

        parts: list[str] = []
        for item in items:
            value_style = f' style="color:{item.color};"' if item.color else ""
            parts.append(f'<span style="color:gray; font-size:{_LABEL_FONT_SIZE}pt;">{item.label}:</span> <b{value_style}>{item.value}</b>')

        self._content_label.setText(_SEPARATOR.join(parts))
        self.setVisible(True)

    def clear(self) -> None:
        """Hide the banner and clear its content."""
        self._content_label.setText("")
        self.setVisible(False)
