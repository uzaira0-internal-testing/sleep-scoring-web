"""
Qt-dependent services for the UI layer.

These services use PyQt6 components (QSettings, etc.) but are not
coordinators (QTimer/QThread glue) or connectors (store↔widget bridges).
"""

from sleep_scoring_app.ui.services.session_state_service import SessionStateService

__all__ = [
    "SessionStateService",
]
