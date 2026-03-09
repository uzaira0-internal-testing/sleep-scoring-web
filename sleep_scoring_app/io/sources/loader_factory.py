"""
Data source loader factory for dependency injection.

Provides centralized data source loader instantiation and management.
This factory is the primary entry point for creating data source loader instances
throughout the application.

Architecture:
    - Factory pattern for loader instantiation
    - Registry for available loaders with pre-configured parameters
    - Extension-based automatic loader selection
    - Extensible for future data sources (GENEActiv, Axivity, etc.)

Example Usage:
    >>> from sleep_scoring_app.io.sources.loader_factory import DataSourceFactory
    >>>
    >>> # Create loader by ID
    >>> csv_loader = DataSourceFactory.create('csv')
    >>>
    >>> # Automatic selection by file extension
    >>> loader = DataSourceFactory.get_loader_for_extension('.csv')
    >>>
    >>> # List available loaders
    >>> available = DataSourceFactory.get_available_loaders()
    >>> # {'csv': 'CSV/XLSX File Loader', 'gt3x': 'GT3X File Loader'}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from .csv_loader import CSVDataSourceLoader
from .gt3x_loader import GT3XDataSourceLoader

# Try to import gt3x-rs module (optional high-performance backend)
# We need to check if the actual Rust module is available, not just the loader class
try:
    import gt3x_rs

    from .gt3x_rs_loader import Gt3xRsDataSourceLoader

    GT3X_RS_AVAILABLE = True
except ImportError:
    GT3X_RS_AVAILABLE = False

if TYPE_CHECKING:
    from pathlib import Path

    from sleep_scoring_app.core.backends import ComputeBackend

    from .loader_protocol import DataSourceLoader

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _LoaderEntry:
    """Internal registry entry for data source loader configuration."""

    loader_class: type[DataSourceLoader]
    display_name: str


class DataSourceFactory:
    """
    Factory for creating data source loader instances.

    Manages loader instantiation, configuration, and registration.
    Enables dependency injection throughout the application.

    Each loader is registered with its own identifier and supported file extensions.

    Class Attributes:
        _registry: Registry mapping loader identifiers to entry configurations

    Methods:
        create: Create a configured loader instance
        get_available_loaders: List all registered loaders
        get_loader_for_extension: Auto-select loader by file extension
        get_default_loader_id: Get the default loader identifier
        is_registered: Check if loader is registered
        get_supported_extensions: Get all supported file extensions
        register: Register a new loader type

    """

    _registry: ClassVar[dict[str, _LoaderEntry]] = {
        "csv": _LoaderEntry(
            loader_class=CSVDataSourceLoader,
            display_name="CSV/XLSX File Loader",
        ),
        "gt3x": _LoaderEntry(
            loader_class=GT3XDataSourceLoader,
            display_name="GT3X File Loader (pygt3x)",
        ),
    }

    # Register gt3x-rs as primary GT3X loader if available (preferred)
    if GT3X_RS_AVAILABLE:
        _registry["gt3x_rs"] = _LoaderEntry(
            loader_class=Gt3xRsDataSourceLoader,
            display_name="GT3X File Loader (Rust)",
        )
        # Override gt3x to use the faster Rust implementation
        _registry["gt3x"] = _LoaderEntry(
            loader_class=Gt3xRsDataSourceLoader,
            display_name="GT3X File Loader",
        )
        # Keep pygt3x available as fallback
        _registry["gt3x_pygt3x"] = _LoaderEntry(
            loader_class=GT3XDataSourceLoader,
            display_name="GT3X File Loader (pygt3x fallback)",
        )

    @classmethod
    def create(
        cls,
        loader_id: str,
        backend: ComputeBackend | None = None,
        **kwargs: Any,
    ) -> DataSourceLoader:
        """
        Create a data source loader instance.

        Args:
            loader_id: Loader identifier (e.g., "csv", "gt3x")
            backend: Optional compute backend for GT3X loaders (auto-selects if None)
            **kwargs: Additional arguments passed to loader constructor

        Returns:
            Configured loader instance

        Raises:
            ValueError: If loader_id is not registered

        Example:
            >>> loader = DataSourceFactory.create('csv')
            >>> loader.name
            'CSV/XLSX File Loader'
            >>>
            >>> # With custom backend
            >>> from sleep_scoring_app.core.backends import BackendFactory
            >>> backend = BackendFactory.create('gt3x_rs')
            >>> loader = DataSourceFactory.create('gt3x', backend=backend)

        """
        if loader_id not in cls._registry:
            available = ", ".join(cls._registry.keys())
            msg = f"Unknown data source loader '{loader_id}'. Available: {available}"
            raise ValueError(msg)

        entry = cls._registry[loader_id]

        # Create instance with backend if it's a GT3X loader
        if loader_id in ("gt3x", "gt3x_rs", "gt3x_pygt3x"):
            return entry.loader_class(backend=backend, **kwargs)  # pyright: ignore[reportCallIssue]
        return entry.loader_class(**kwargs)

    @classmethod
    def get_available_loaders(cls) -> dict[str, str]:
        """
        Get all available data source loaders.

        Returns:
            Dictionary mapping loader_id to display name

        Example:
            >>> DataSourceFactory.get_available_loaders()
            {'csv': 'CSV/XLSX File Loader', 'gt3x': 'GT3X File Loader'}

        """
        return {loader_id: entry.display_name for loader_id, entry in cls._registry.items()}

    @classmethod
    def get_loader_for_extension(
        cls,
        file_extension: str,
        backend: ComputeBackend | None = None,
        **kwargs: Any,
    ) -> DataSourceLoader:
        """
        Auto-select and create loader based on file extension.

        Args:
            file_extension: File extension (e.g., ".csv", ".gt3x")
            backend: Optional compute backend for GT3X loaders (auto-selects if None)
            **kwargs: Additional arguments passed to loader constructor

        Returns:
            Appropriate loader instance for the file type

        Raises:
            ValueError: If no loader supports the extension

        Example:
            >>> loader = DataSourceFactory.get_loader_for_extension('.csv')
            >>> loader.identifier
            'csv'

        """
        # Normalize extension to lowercase with leading dot
        ext = file_extension.lower()
        if not ext.startswith("."):
            ext = f".{ext}"

        # Check each loader's supported extensions using class attribute (no instantiation)
        for loader_id, entry in cls._registry.items():
            loader_class = entry.loader_class
            # Use class attribute if available, otherwise instantiate (fallback)
            if hasattr(loader_class, "SUPPORTED_EXTENSIONS"):
                supported_extensions = loader_class.SUPPORTED_EXTENSIONS
            else:
                # Fallback: instantiate to get extensions
                loader_instance = loader_class()
                supported_extensions = loader_instance.supported_extensions

            if ext in supported_extensions:
                # Create instance with backend if GT3X
                if loader_id in ("gt3x", "gt3x_rs", "gt3x_pygt3x"):
                    return loader_class(backend=backend, **kwargs)  # pyright: ignore[reportCallIssue]
                return loader_class(**kwargs)

        # No matching loader found
        supported = cls.get_supported_extensions()
        msg = f"No loader found for extension '{ext}'. Supported: {', '.join(sorted(supported))}"
        raise ValueError(msg)

    @classmethod
    def get_loader_for_file(
        cls,
        file_path: str | Path,
        backend: ComputeBackend | None = None,
        **kwargs: Any,
    ) -> DataSourceLoader:
        """
        Auto-select and create loader based on file path.

        Args:
            file_path: Path to the data file
            backend: Optional compute backend for GT3X loaders (auto-selects if None)
            **kwargs: Additional arguments passed to loader constructor

        Returns:
            Appropriate loader instance for the file type

        Raises:
            ValueError: If no loader supports the file extension

        Example:
            >>> loader = DataSourceFactory.get_loader_for_file('/data/activity.csv')
            >>> loader.identifier
            'csv'

        """
        from pathlib import Path

        path = Path(file_path)
        return cls.get_loader_for_extension(path.suffix, backend=backend, **kwargs)

    @classmethod
    def get_default_loader_id(cls) -> str:
        """
        Get the default loader identifier.

        Returns:
            Default loader ID ('csv')

        """
        return "csv"

    @classmethod
    def is_registered(cls, loader_id: str) -> bool:
        """
        Check if a loader is registered.

        Args:
            loader_id: Loader identifier to check

        Returns:
            True if loader is registered, False otherwise

        """
        return loader_id in cls._registry

    @classmethod
    def get_supported_extensions(cls) -> set[str]:
        """
        Get all supported file extensions across all loaders.

        Returns:
            Set of all supported file extensions

        Example:
            >>> DataSourceFactory.get_supported_extensions()
            {'.csv', '.xlsx', '.xls', '.gt3x'}

        """
        extensions = set()
        for entry in cls._registry.values():
            loader_class = entry.loader_class
            # Use class attribute if available, otherwise instantiate (fallback)
            if hasattr(loader_class, "SUPPORTED_EXTENSIONS"):
                extensions.update(loader_class.SUPPORTED_EXTENSIONS)
            else:
                loader_instance = loader_class()
                extensions.update(loader_instance.supported_extensions)
        return extensions

    @classmethod
    def register(
        cls,
        loader_id: str,
        loader_class: type[DataSourceLoader],
        display_name: str,
    ) -> None:
        """
        Register a new data source loader.

        Args:
            loader_id: Unique identifier for the loader
            loader_class: Loader class implementing DataSourceLoader protocol
            display_name: Human-readable name for UI display

        Raises:
            ValueError: If loader_id already registered

        Example:
            >>> DataSourceFactory.register(
            ...     'custom_loader',
            ...     CustomDataSourceLoader,
            ...     'Custom Data Loader',
            ... )

        """
        if loader_id in cls._registry:
            msg = f"Data source loader '{loader_id}' is already registered"
            raise ValueError(msg)

        cls._registry[loader_id] = _LoaderEntry(
            loader_class=loader_class,
            display_name=display_name,
        )
        logger.info("Registered new data source loader: %s", loader_id)


# Module-level initialization: Register default loaders
# (Already registered in _registry dict above, but this documents the pattern)
