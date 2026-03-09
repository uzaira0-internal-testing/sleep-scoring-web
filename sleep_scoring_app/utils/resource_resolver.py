"""
Resource path resolver for PyInstaller executable compatibility.

This module provides utilities to resolve file paths correctly in both
development and packaged executable environments.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import ClassVar, Self

try:
    from sleep_scoring_app.core.constants import FileName
except ImportError:
    # Direct import for testing
    from sleep_scoring_app.core.constants import FileName


class ResourceResolver:
    """
    Resolves resource paths for both development and executable environments.

    This class handles the differences between running from source code and
    running from a PyInstaller-packaged executable, ensuring that config files,
    database files, and other resources can be found correctly.
    """

    _instance: ClassVar[ResourceResolver | None] = None
    _base_path: Path
    _is_executable: bool
    _app_data_dir: Path

    def __new__(cls) -> Self:
        """Singleton pattern to ensure consistent path resolution."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize the resource resolver with appropriate paths."""
        # Detect if running as PyInstaller executable
        self._is_executable = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

        if self._is_executable:
            # Running as executable - use temporary extraction directory
            self._base_path = Path(getattr(sys, "_MEIPASS", ""))
            # Use platform-specific application data directory for persistent files
            self._app_data_dir = self._get_app_data_directory()
        else:
            # Running from source - use project root
            # Go up from utils/resource_resolver.py to project root
            self._base_path = Path(__file__).parent.parent.parent
            self._app_data_dir = self._base_path

    def _get_app_data_directory(self) -> Path:
        """Get platform-specific application data directory."""
        app_name = "SleepScoringApp"

        if sys.platform == "win32":
            # Windows: %APPDATA%/SleepScoringApp
            base_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            # macOS: ~/Library/Application Support/SleepScoringApp
            base_dir = Path.home() / "Library" / "Application Support"
        else:
            # Linux/Unix: ~/.local/share/SleepScoringApp
            base_dir = Path.home() / ".local" / "share"

        app_dir = base_dir / app_name
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir

    def get_bundled_resource_path(self, relative_path: str | Path) -> Path:
        """
        Get path to a bundled resource file.

        Args:
            relative_path: Path relative to the project root

        Returns:
            Absolute path to the resource file

        """
        return self._base_path / relative_path

    def get_user_data_path(self, filename: str) -> Path:
        """
        Get path for user data files (database, config, etc.).

        Args:
            filename: Name of the user data file

        Returns:
            Path in the appropriate user data directory

        """
        return self._app_data_dir / filename

    def get_database_path(self) -> Path:
        """Get the database file path."""
        return self.get_user_data_path(FileName.SLEEP_SCORING_DB)

    def get_config_path(self) -> Path:
        """Get the configuration file path."""
        return self.get_user_data_path(FileName.CONFIG_JSON)

    def get_diary_config_path(self, config_filename: str = "diary_mapping.json") -> Path:
        """
        Get the diary configuration file path.

        Args:
            config_filename: Name of the diary config file

        Returns:
            Path to the diary config file

        """
        if self._is_executable:
            # In executable mode, first check user data directory
            user_config = self.get_user_data_path(config_filename)
            if user_config.exists():
                return user_config

            # Fall back to bundled default config
            bundled_config = self.get_bundled_resource_path(f"config/{config_filename}")
            if bundled_config.exists():
                # Copy bundled config to user directory for future use
                user_config.parent.mkdir(parents=True, exist_ok=True)
                user_config.write_text(bundled_config.read_text(encoding="utf-8"), encoding="utf-8")
                return user_config

            # Last resort: check root directory
            return self.get_user_data_path(config_filename)
        # Development mode: check multiple locations

        # First try config subdirectory
        config_dir_path = self._base_path / "config" / config_filename
        if config_dir_path.exists():
            return config_dir_path

        # Then try project root
        root_path = self._base_path / config_filename
        if root_path.exists():
            return root_path

        # Default to config directory (will be created if needed)
        config_dir_path.parent.mkdir(parents=True, exist_ok=True)
        return config_dir_path

    def is_executable_environment(self) -> bool:
        """Check if running in a PyInstaller executable environment."""
        return self._is_executable

    def get_temp_directory(self) -> Path:
        """Get a temporary directory for the application."""
        import tempfile

        temp_dir = Path(tempfile.gettempdir()) / "SleepScoringApp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir


# Global instance for easy access
resource_resolver = ResourceResolver()


def get_database_path() -> Path:
    """Get the database file path (replacement for constants function)."""
    return resource_resolver.get_database_path()


def get_config_path() -> Path:
    """Get the configuration file path (replacement for constants function)."""
    return resource_resolver.get_config_path()


def get_diary_config_path(config_filename: str = "diary_mapping.json") -> Path:
    """Get the diary configuration file path."""
    return resource_resolver.get_diary_config_path(config_filename)


def get_settings_backup_path() -> Path:
    """Get the settings backup JSON file path (always in system app data directory)."""
    # Always use system app data directory for settings backup, regardless of dev/prod mode
    # This keeps it alongside QSettings data for consistency
    app_data_dir = resource_resolver._get_app_data_directory()
    return app_data_dir / "settings_backup.json"
