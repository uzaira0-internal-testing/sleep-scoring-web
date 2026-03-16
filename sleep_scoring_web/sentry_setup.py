"""Sentry SDK initialization for error tracking."""

import logging
import os

logger = logging.getLogger(__name__)

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None  # type: ignore[assignment]


def init_sentry() -> None:
    """Initialize Sentry if DSN is configured. No-op on failure."""
    if sentry_sdk is None:
        return

    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("ENVIRONMENT", "development"),
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            before_send=_filter_events,
        )
    except Exception:
        logger.warning("Sentry initialization failed", exc_info=True)


def _filter_events(event, hint):
    """Filter out expected errors (404s, validation errors)."""
    try:
        exc_info = hint.get("exc_info")
        if exc_info is not None:
            _, exc_value, _ = exc_info
            from fastapi import HTTPException

            if isinstance(exc_value, HTTPException) and exc_value.status_code < 500:
                return None
    except Exception:
        pass  # Never let the filter crash — return event unchanged
    return event
