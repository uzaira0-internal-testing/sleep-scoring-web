#!/usr/bin/env python3
"""
Application bootstrap utilities.

Provides shared, UI-agnostic setup for logging and runtime configuration.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging() -> Path | None:
    """
    Set up logging with proper path handling for app bundles.

    Returns:
        Path to log file, or None if using default stderr.

    """
    log_file: Path | None = None

    if getattr(sys, "frozen", False):
        bundle_dir = Path(sys.executable).parent
        if sys.platform.startswith("darwin"):
            log_dir = Path.home() / "Library" / "Logs" / "SleepScoringApp"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "sleep_scoring_app.log"
        else:
            log_file = bundle_dir / "sleep_scoring_app.log"

        logging.basicConfig(
            level=logging.WARNING,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
        )
    else:
        logging.basicConfig(
            level=logging.WARNING,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    return log_file
