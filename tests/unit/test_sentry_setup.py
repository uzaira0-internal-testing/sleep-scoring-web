"""
Tests for sleep_scoring_web.sentry_setup module.

Covers Sentry initialization with and without DSN,
event filtering for HTTPException, and crash-safe guards.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestInitSentry:
    """Tests for init_sentry()."""

    def test_no_sentry_sdk_installed(self):
        """When sentry_sdk is not installed, init_sentry should be a no-op."""
        import sleep_scoring_web.sentry_setup as module

        original = module.sentry_sdk
        try:
            module.sentry_sdk = None
            # Should not raise
            module.init_sentry()
        finally:
            module.sentry_sdk = original

    @patch.dict("os.environ", {"SENTRY_DSN": ""}, clear=False)
    def test_no_dsn_configured(self):
        """When SENTRY_DSN is empty, should not call sentry_sdk.init."""
        import sleep_scoring_web.sentry_setup as module

        mock_sdk = MagicMock()
        original = module.sentry_sdk
        try:
            module.sentry_sdk = mock_sdk
            module.init_sentry()
            mock_sdk.init.assert_not_called()
        finally:
            module.sentry_sdk = original

    @patch.dict("os.environ", {"SENTRY_DSN": "https://key@sentry.io/123", "ENVIRONMENT": "testing"}, clear=False)
    def test_dsn_configured_calls_init(self):
        """When SENTRY_DSN is set, should call sentry_sdk.init with correct args."""
        import sleep_scoring_web.sentry_setup as module

        mock_sdk = MagicMock()
        original = module.sentry_sdk
        try:
            module.sentry_sdk = mock_sdk
            module.init_sentry()
            mock_sdk.init.assert_called_once()
            call_kwargs = mock_sdk.init.call_args
            assert call_kwargs.kwargs["dsn"] == "https://key@sentry.io/123"
            assert call_kwargs.kwargs["environment"] == "testing"
            assert call_kwargs.kwargs["traces_sample_rate"] == 0.1
            assert call_kwargs.kwargs["profiles_sample_rate"] == 0.1
            assert call_kwargs.kwargs["before_send"] is not None
        finally:
            module.sentry_sdk = original

    @patch.dict("os.environ", {"SENTRY_DSN": "https://key@sentry.io/123"}, clear=False)
    def test_default_environment(self):
        """When ENVIRONMENT is not set, should default to 'development'."""
        import sleep_scoring_web.sentry_setup as module

        # Remove ENVIRONMENT if present
        import os
        env_val = os.environ.pop("ENVIRONMENT", None)

        mock_sdk = MagicMock()
        original = module.sentry_sdk
        try:
            module.sentry_sdk = mock_sdk
            module.init_sentry()
            call_kwargs = mock_sdk.init.call_args
            assert call_kwargs.kwargs["environment"] == "development"
        finally:
            module.sentry_sdk = original
            if env_val is not None:
                os.environ["ENVIRONMENT"] = env_val

    @patch.dict("os.environ", {"SENTRY_DSN": "https://key@sentry.io/123"}, clear=False)
    def test_init_failure_logged_not_raised(self):
        """When sentry_sdk.init raises, should log warning but not propagate."""
        import sleep_scoring_web.sentry_setup as module

        mock_sdk = MagicMock()
        mock_sdk.init.side_effect = RuntimeError("connection failed")
        original = module.sentry_sdk
        try:
            module.sentry_sdk = mock_sdk
            # Should not raise
            module.init_sentry()
        finally:
            module.sentry_sdk = original


class TestFilterEvents:
    """Tests for _filter_events()."""

    def test_http_exception_below_500_filtered(self):
        """HTTPException with status < 500 should be filtered (return None)."""
        from fastapi import HTTPException

        from sleep_scoring_web.sentry_setup import _filter_events

        exc = HTTPException(status_code=404)
        event = {"type": "error"}
        hint = {"exc_info": (type(exc), exc, None)}

        result = _filter_events(event, hint)
        assert result is None

    def test_http_exception_422_filtered(self):
        """HTTPException 422 (validation) should be filtered."""
        from fastapi import HTTPException

        from sleep_scoring_web.sentry_setup import _filter_events

        exc = HTTPException(status_code=422)
        event = {"type": "error"}
        hint = {"exc_info": (type(exc), exc, None)}

        result = _filter_events(event, hint)
        assert result is None

    def test_http_exception_500_not_filtered(self):
        """HTTPException with status >= 500 should NOT be filtered."""
        from fastapi import HTTPException

        from sleep_scoring_web.sentry_setup import _filter_events

        exc = HTTPException(status_code=500)
        event = {"type": "error"}
        hint = {"exc_info": (type(exc), exc, None)}

        result = _filter_events(event, hint)
        assert result is event

    def test_non_http_exception_not_filtered(self):
        """Non-HTTPException errors should pass through."""
        from sleep_scoring_web.sentry_setup import _filter_events

        exc = ValueError("something broke")
        event = {"type": "error"}
        hint = {"exc_info": (type(exc), exc, None)}

        result = _filter_events(event, hint)
        assert result is event

    def test_no_exc_info_returns_event(self):
        """When hint has no exc_info, event should pass through."""
        from sleep_scoring_web.sentry_setup import _filter_events

        event = {"type": "error"}
        hint = {}

        result = _filter_events(event, hint)
        assert result is event

    def test_none_exc_info_returns_event(self):
        """When exc_info is None, event should pass through."""
        from sleep_scoring_web.sentry_setup import _filter_events

        event = {"type": "error"}
        hint = {"exc_info": None}

        result = _filter_events(event, hint)
        assert result is event

    def test_filter_never_crashes(self):
        """Even with bad hint data, the filter should never raise."""
        from sleep_scoring_web.sentry_setup import _filter_events

        event = {"type": "error"}
        # Malformed hint — exc_info is not a tuple
        hint = {"exc_info": "bad_data"}

        # Should not raise, should return event
        result = _filter_events(event, hint)
        assert result is event
