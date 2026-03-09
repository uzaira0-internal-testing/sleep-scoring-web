"""Command-line interface for sleep scoring algorithms.

Future Feature: CLI interface for running sleep scoring algorithms from the command line.
This module is a placeholder for future development.

Planned features:
    - Batch processing of activity data files
    - JSON/CSV output formats
    - Progress reporting to stdout
    - Configuration via command-line arguments or config files

Example future usage:
    ```bash
    sleep-scoring-cli score --input data.csv --output results.json
    sleep-scoring-cli detect-nonwear --input data.csv --config choi.json
    ```

Dependencies:
    - argparse or click for argument parsing
    - Core algorithms from sleep_scoring_app.core.algorithms
    - No PyQt dependencies

See: /docs/cli_design.md (to be created)
"""

from __future__ import annotations

__all__: list[str] = []
