#!/usr/bin/env python3
"""
Sleep Scoring Application - Main Entry Point.

Allows running as: python main.py.
"""

import sys

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

# Configure PyQtGraph
pg.setConfigOption("background", "w")  # White background
pg.setConfigOption("foreground", "k")  # Black foreground
pg.setConfigOption("antialias", True)  # Better line rendering

# Import the main window
from sleep_scoring_app.ui.main_window import SleepScoringMainWindow


def create_splash_screen() -> QSplashScreen:
    """Create a splash screen with loading message."""
    # Create a simple colored pixmap for the splash screen
    pixmap = QPixmap(500, 300)
    pixmap.fill(QColor(45, 85, 125))  # Professional blue color

    splash = QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)

    # Add text styling
    splash.setStyleSheet("""
        QSplashScreen {
            background-color: #2d557d;
            color: white;
        }
    """)

    # Show splash immediately
    splash.show()

    # Add loading message
    splash.showMessage(
        "Sleep Scoring App\n\nLoading application...", Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom, Qt.GlobalColor.white
    )

    return splash


# Global variable to hold splash screen reference for main window to access
_global_splash = None
_global_app = None


def main() -> None:
    """Main application entry point."""
    global _global_splash, _global_app

    if sys.platform == "win32":
        sys.argv += ["-platform", "windows:darkmode=1"]
        sys.argv += ["--style=Fusion"]
    app = QApplication(sys.argv)
    _global_app = app

    # Create and show splash screen immediately
    splash = create_splash_screen()
    _global_splash = splash
    app.processEvents()  # Ensure splash is rendered

    # Update splash message
    splash.showMessage(
        "Sleep Scoring App\n\nInitializing database...", Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom, Qt.GlobalColor.white
    )
    app.processEvents()

    # Create the main window (this is where the 1-minute freeze happens)
    # The window will update splash directly via global reference
    window = SleepScoringMainWindow()

    # Show main window and close splash
    window.show()
    app.processEvents()
    splash.finish(window)

    # Start the Qt event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
