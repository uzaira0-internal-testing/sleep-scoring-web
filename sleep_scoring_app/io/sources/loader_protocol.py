"""
Data source loader protocol for dependency injection.

This protocol defines the interface that all data source loaders must implement.
Enables swapping between CSV/XLSX and GT3X file sources without changing core application logic.

Architecture:
    - Protocol defines the contract for data source loaders
    - Implementations: CSVDataSourceLoader, GT3XDataSourceLoader
    - Factory creates instances based on file extension or configuration
    - Services accept protocol type, not concrete implementations

Example Usage:
    >>> from sleep_scoring_app.io.sources import DataSourceFactory
    >>>
    >>> # Create loader from factory by extension
    >>> loader = DataSourceFactory.get_loader_for_extension(".csv")
    >>>
    >>> # Load data
    >>> result = loader.load_file("/path/to/data.csv")
    >>>
    >>> # Use protocol type for dependency injection
    >>> def process_file(loader: DataSourceLoader, file_path: str):
    ...     result = loader.load_file(file_path)
    ...     return result.activity_data

References:
    - ActiGraph CSV format specification
    - GT3X binary format specification (ActiGraph)

"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd

    from sleep_scoring_app.core.dataclasses import ColumnMapping


@runtime_checkable
class DataSourceLoader(Protocol):
    """
    Protocol for data source loaders.

    All data source loaders (CSV/XLSX, GT3X, etc.) must implement this interface.
    The protocol is runtime_checkable to allow isinstance() checks for validation.

    Properties:
        name: Human-readable loader name for display
        identifier: Unique identifier for storage and configuration
        supported_extensions: Set of file extensions this loader supports

    Methods:
        load_file: Load activity data from file
        detect_columns: Detect and map column names
        validate_data: Validate loaded data structure
        get_file_metadata: Extract metadata from file

    """

    @property
    def name(self) -> str:
        """
        Loader name for display and identification.

        Returns:
            Human-readable loader name (e.g., "CSV/XLSX File Loader", "GT3X File Loader")

        """
        ...

    @property
    def identifier(self) -> str:
        """
        Unique loader identifier for storage and configuration.

        Returns:
            Snake_case identifier (e.g., "csv", "gt3x")

        """
        ...

    @property
    def supported_extensions(self) -> frozenset[str]:
        """
        File extensions supported by this loader.

        Returns:
            Set of supported extensions (e.g., {".csv", ".xlsx", ".xls"})

        """
        ...

    def load_file(self, file_path: str | Path) -> dict[str, Any]:
        """
        Load activity data from file.

        Args:
            file_path: Path to the data file

        Returns:
            Dictionary containing:
                - activity_data: pd.DataFrame with datetime and activity columns
                - metadata: dict with file metadata
                - column_mapping: dict mapping standard names to actual column names

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file format is invalid or unsupported
            IOError: If file cannot be read

        """
        ...

    def detect_columns(self, df: pd.DataFrame) -> ColumnMapping:
        """
        Detect and map column names to standard names.

        Args:
            df: DataFrame to analyze

        Returns:
            ColumnMapping with detected source-to-standard column mappings.

        Raises:
            ValueError: If required columns cannot be detected

        """
        ...

    def validate_data(self, df: pd.DataFrame) -> tuple[bool, list[str]]:
        """
        Validate loaded data structure and content.

        Args:
            df: DataFrame to validate

        Returns:
            Tuple of `(is_valid, errors)` where `errors` is empty when valid.

        Raises:
            ValueError: If data validation fails with specific error message

        """
        ...

    def get_file_metadata(self, file_path: str | Path) -> dict[str, Any]:
        """
        Extract metadata from file without loading full data.

        Args:
            file_path: Path to the data file

        Returns:
            Dictionary containing:
                - file_size: File size in bytes
                - date_range: tuple of (start_date, end_date)
                - epoch_length: Epoch length in seconds
                - device_info: dict with device information (if available)
                - total_records: Estimated or exact record count

        Raises:
            FileNotFoundError: If file does not exist
            IOError: If file cannot be read

        """
        ...
