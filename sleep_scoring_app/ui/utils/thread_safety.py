"""
Thread safety utilities for PyQt6 applications.

This module provides utilities for ensuring UI operations run on the main thread.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from PyQt6.QtCore import QThread, QTimer

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def ensure_main_thread[**P, T](func: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator to ensure a QWidget method runs on the main thread.

    If called from a worker thread, the method is deferred to the main thread
    using QTimer.singleShot(0, ...). This is the recommended PyQt6 pattern
    for thread-safe UI updates.

    Usage:
        class MyWidget(QWidget):
            @ensure_main_thread
            def update_ui(self, value: str) -> None:
                self.label.setText(value)

    Note: The decorated method must be a bound method of a QWidget subclass.
    The return value is lost when deferring to the main thread.
    """

    @functools.wraps(func)
    def wrapper(self: QWidget, *args: P.args, **kwargs: P.kwargs) -> T | None:
        if QThread.currentThread() != self.thread():
            logger.debug(
                "%s.%s called from non-main thread, deferring to main thread",
                self.__class__.__name__,
                func.__name__,
            )
            # Capture args/kwargs in lambda closure
            QTimer.singleShot(0, lambda: func(self, *args, **kwargs))
            return None
        return func(self, *args, **kwargs)

    return wrapper


def is_main_thread(widget: QWidget) -> bool:
    """
    Check if the current thread is the main thread for a widget.

    Args:
        widget: The QWidget to check against.

    Returns:
        True if running on the widget's thread (main thread), False otherwise.

    """
    return QThread.currentThread() == widget.thread()
