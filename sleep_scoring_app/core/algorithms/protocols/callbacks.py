"""
Framework-agnostic callback protocols for sleep scoring algorithms.

This module defines Protocol types for callbacks used by sleep scoring algorithms.
These protocols enable the algorithms to be completely framework-independent while
still supporting progress reporting, cancellation, and logging.

Protocols allow any framework (PyQt, CLI, web, etc.) to provide compatible callbacks
without the core algorithms depending on that framework.
"""

from __future__ import annotations

from typing import Protocol


class ProgressCallback(Protocol):
    """
    Protocol for reporting algorithm progress.

    This protocol defines the interface for progress reporting callbacks.
    Any callable matching this signature can be used for progress updates.

    Example implementations:
        - GUI: Update progress bar and labels
        - CLI: Print progress percentage
        - Web: Send websocket progress update
        - Silent: No-op for batch processing
    """

    def __call__(self, progress: int, current: int, total: int) -> None:
        """
        Report progress for a running algorithm.

        Args:
            progress: Percentage complete (0-100)
            current: Current item/epoch being processed
            total: Total number of items/epochs to process

        """
        ...


class CancellationCheck(Protocol):
    """
    Protocol for checking if an operation should be cancelled.

    This protocol enables algorithms to check for user-initiated cancellation
    without depending on any specific framework's signaling mechanism.

    Example implementations:
        - GUI: Check if cancel button was clicked
        - CLI: Check for Ctrl+C signal
        - Web: Check if client disconnected
        - Batch: Always return False
    """

    def __call__(self) -> bool:
        """
        Check if the current operation should be cancelled.

        Returns:
            True if the operation should be cancelled, False to continue

        """
        ...


class LogCallback(Protocol):
    """
    Protocol for logging algorithm events and errors.

    This protocol provides a framework-independent way to log messages
    from algorithms without coupling to specific logging frameworks.

    Example implementations:
        - GUI: Write to log widget or status bar
        - CLI: Print to stdout/stderr
        - Web: Send to logging service
        - Standard: Use Python logging module
    """

    def __call__(self, level: str, message: str) -> None:
        """
        Log a message at the specified level.

        Args:
            level: Log level - one of: 'debug', 'info', 'warning', 'error', 'critical'
            message: Message to log

        """
        ...
