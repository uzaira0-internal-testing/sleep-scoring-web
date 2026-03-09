#!/usr/bin/env python3
"""
Sleep Scoring Demo - Package Main Entry Point.

This module provides the entry point for the installed package.
It wraps the root main.py functionality for use with:
    python -m sleep_scoring_app
    sleep-scoring-demo (console script)
"""

from __future__ import annotations

import logging
import sys

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")
pg.setConfigOption("antialias", True)

from sleep_scoring_app.app_bootstrap import setup_logging
from sleep_scoring_app.ui.main_window import SleepScoringMainWindow


def create_splash_screen() -> QSplashScreen:
    """Create a splash screen with loading message."""
    pixmap = QPixmap(500, 300)
    pixmap.fill(QColor(45, 85, 125))

    splash = QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)

    splash.setStyleSheet("""
        QSplashScreen {
            background-color: #2d557d;
            color: white;
        }
    """)

    splash.show()

    splash.showMessage(
        "Sleep Scoring App\n\nLoading application...",
        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
        Qt.GlobalColor.white,
    )

    return splash


_global_splash = None
_global_app = None


def main() -> int:
    """
    Main application entry point.

    Returns:
        Exit code (0 for success, non-zero for errors).

    """
    global _global_splash, _global_app

    log_file = setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Sleep Scoring Application")
    if log_file:
        logger.info(f"Log file location: {log_file}")

    if sys.platform.startswith("win"):
        sys.argv += ["-platform", "windows:darkmode=1"]
        sys.argv += ["--style=Fusion"]
    elif sys.platform.startswith("darwin"):
        sys.argv += ["-platform", "cocoa"]
        logger.info("Using cocoa platform for macOS")

    app = QApplication(sys.argv)
    _global_app = app

    splash = create_splash_screen()
    _global_splash = splash
    app.processEvents()

    splash.showMessage(
        "Sleep Scoring App\n\nInitializing database...",
        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
        Qt.GlobalColor.white,
    )
    app.processEvents()

    window = SleepScoringMainWindow()

    window.show()
    app.processEvents()
    splash.finish(window)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
