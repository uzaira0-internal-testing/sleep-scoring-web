#!/usr/bin/env python
"""
Module entry point for the sleep scoring demo application.

This allows the application to be run as:
    python -m sleep_scoring_app
or via the installed console script:
    sleep-scoring-demo
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)


def main() -> int:
    """Main entry point for the module."""
    try:
        from sleep_scoring_app.main import main as app_main

        logger.info("Starting Sleep Scoring Application via module entry point")
        return app_main()
    except ImportError as e:
        logger.exception(f"Failed to import application: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        return 130
    except Exception:
        logger.exception("Unexpected error during application startup")
        return 1


if __name__ == "__main__":
    sys.exit(main())
