"""
Compute backend factory for dependency injection.

Provides centralized backend instantiation and automatic selection.
This factory is the primary entry point for creating compute backend instances
throughout the application.

Architecture:
    - Factory pattern for backend instantiation
    - Registry with priority-based selection
    - Automatic fallback to available backends
    - Extensible for future backends

Example Usage:
    >>> from sleep_scoring_app.core.backends import BackendFactory
    >>>
    >>> # Create best available backend
    >>> backend = BackendFactory.create()
    >>>
    >>> # Create specific backend
    >>> backend = BackendFactory.create('gt3x_rs')
    >>>
    >>> # List available backends
    >>> available = BackendFactory.get_available_backends()
    >>> # {'gt3x_rs': 'gt3x-rs (Rust)', 'pygt3x': 'PyGt3x (Python)'}
    >>>
    >>> # Get backends with specific capability
    >>> parsers = BackendFactory.get_backends_with_capability(BackendCapability.PARSE_GT3X)

"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from .capabilities import BackendCapability

if TYPE_CHECKING:
    from .protocol import ComputeBackend

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _BackendEntry:
    """
    Internal registry entry for backend configuration.

    Attributes:
        backend_class: Backend class implementing ComputeBackend protocol
        display_name: Human-readable name for UI display
        priority: Priority for auto-selection (lower = higher priority)
        description: Optional description of backend

    """

    backend_class: type[ComputeBackend]
    display_name: str
    priority: int
    description: str | None = None


class BackendFactory:
    """
    Factory for creating compute backend instances.

    Manages backend instantiation, configuration, and automatic selection.
    Enables dependency injection throughout the application.

    Backends are registered with priority values. When create() is called
    without a backend_id, the factory selects the highest priority available
    backend (lowest priority number).

    Priority Guidelines:
        - 10: Preferred backends (gt3x-rs)
        - 50: Fallback backends (pygt3x)
        - 100: Legacy/deprecated backends

    Class Attributes:
        _registry: Registry mapping backend identifiers to entry configurations

    Methods:
        create: Create a backend instance (auto-selects if no ID provided)
        get_available_backends: List all available backends
        get_backends_with_capability: Filter backends by capability
        is_registered: Check if backend is registered
        register: Register a new backend type
        get_default_backend_id: Get highest priority available backend ID

    """

    _registry: ClassVar[dict[str, _BackendEntry]] = {}

    @classmethod
    def create(cls, backend_id: str | None = None) -> ComputeBackend:
        """
        Create a compute backend instance.

        If backend_id is not specified, automatically selects the highest
        priority available backend.

        Args:
            backend_id: Backend identifier (e.g., "gt3x_rs", "pygt3x")
                       If None, auto-selects best available backend

        Returns:
            Configured backend instance

        Raises:
            ValueError: If backend_id is not registered or no backends available
            RuntimeError: If backend is registered but not available

        Example:
            >>> # Auto-select best available
            >>> backend = BackendFactory.create()
            >>>
            >>> # Explicit selection
            >>> backend = BackendFactory.create('gt3x_rs')

        """
        # Auto-select if no ID provided
        if backend_id is None:
            backend_id = cls.get_default_backend_id()

        if backend_id not in cls._registry:
            available = ", ".join(cls._registry.keys())
            msg = f"Unknown backend '{backend_id}'. Available: {available}"
            raise ValueError(msg)

        entry = cls._registry[backend_id]

        # Create instance
        backend = entry.backend_class()

        # Verify backend is available
        if not backend.is_available:
            msg = f"Backend '{backend_id}' is registered but not available (missing dependencies)"
            raise RuntimeError(msg)

        logger.info(f"Created compute backend: {entry.display_name} (priority={entry.priority})")
        return backend

    @classmethod
    def get_available_backends(cls) -> dict[str, str]:
        """
        Get all available compute backends.

        Only returns backends that are currently available (is_available=True).

        Returns:
            Dictionary mapping backend_id to display name

        Example:
            >>> BackendFactory.get_available_backends()
            {'gt3x_rs': 'gt3x-rs (Rust)', 'pygt3x': 'PyGt3x (Python)'}

        """
        available = {}
        for backend_id, entry in cls._registry.items():
            try:
                backend = entry.backend_class()
                if backend.is_available:
                    available[backend_id] = entry.display_name
            except Exception as e:
                logger.warning(f"Error checking availability of backend '{backend_id}': {e}")

        return available

    @classmethod
    def get_backends_with_capability(cls, capability: BackendCapability) -> dict[str, str]:
        """
        Get backends that support a specific capability.

        Args:
            capability: Capability to filter by

        Returns:
            Dictionary mapping backend_id to display name for matching backends

        Example:
            >>> from sleep_scoring_app.core.backends import BackendCapability
            >>> BackendFactory.get_backends_with_capability(BackendCapability.PARSE_GT3X)
            {'gt3x_rs': 'gt3x-rs (Rust)', 'pygt3x': 'PyGt3x (Python)'}

        """
        matching = {}
        for backend_id, entry in cls._registry.items():
            try:
                backend = entry.backend_class()
                if backend.is_available and backend.supports(capability):
                    matching[backend_id] = entry.display_name
            except Exception as e:
                logger.warning(f"Error checking capability for backend '{backend_id}': {e}")

        return matching

    @classmethod
    def get_default_backend_id(cls) -> str:
        """
        Get the default (highest priority available) backend identifier.

        Selects the available backend with the lowest priority number.

        Returns:
            Default backend ID

        Raises:
            RuntimeError: If no backends are available

        Example:
            >>> BackendFactory.get_default_backend_id()
            'gt3x_rs'  # If gt3x-rs is available, otherwise 'pygt3x'

        """
        # Find available backends sorted by priority
        available = []
        for backend_id, entry in cls._registry.items():
            try:
                backend = entry.backend_class()
                if backend.is_available:
                    available.append((entry.priority, backend_id, entry.display_name))
            except Exception as e:
                logger.warning(f"Error checking backend '{backend_id}': {e}")

        if not available:
            msg = "No compute backends are available. Please install gt3x-rs or pygt3x."
            raise RuntimeError(msg)

        # Sort by priority (lowest number = highest priority)
        available.sort(key=lambda x: x[0])

        priority, backend_id, display_name = available[0]
        logger.info(f"Default backend: {display_name} (priority={priority})")
        return backend_id

    @classmethod
    def is_registered(cls, backend_id: str) -> bool:
        """
        Check if a backend is registered.

        Args:
            backend_id: Backend identifier to check

        Returns:
            True if backend is registered, False otherwise

        """
        return backend_id in cls._registry

    @classmethod
    def register(
        cls,
        backend_id: str,
        backend_class: type[ComputeBackend],
        display_name: str,
        priority: int = 50,
        description: str | None = None,
    ) -> None:
        """
        Register a new compute backend.

        Args:
            backend_id: Unique identifier for the backend
            backend_class: Backend class implementing ComputeBackend protocol
            display_name: Human-readable name for UI display
            priority: Priority for auto-selection (lower = higher priority)
            description: Optional backend description

        Raises:
            ValueError: If backend_id already registered

        Example:
            >>> BackendFactory.register(
            ...     'custom_backend',
            ...     CustomBackend,
            ...     'Custom Backend',
            ...     priority=75,
            ... )

        """
        if backend_id in cls._registry:
            msg = f"Backend '{backend_id}' is already registered"
            raise ValueError(msg)

        cls._registry[backend_id] = _BackendEntry(
            backend_class=backend_class,
            display_name=display_name,
            priority=priority,
            description=description,
        )
        logger.info(f"Registered compute backend: {display_name} (id={backend_id}, priority={priority})")

    @classmethod
    def get_backend_info(cls, backend_id: str) -> dict[str, Any]:
        """
        Get detailed information about a backend.

        Args:
            backend_id: Backend identifier

        Returns:
            Dictionary with backend information

        Raises:
            ValueError: If backend_id is not registered

        """
        if backend_id not in cls._registry:
            available = ", ".join(cls._registry.keys())
            msg = f"Unknown backend '{backend_id}'. Available: {available}"
            raise ValueError(msg)

        entry = cls._registry[backend_id]

        # Try to get availability and capabilities
        try:
            backend = entry.backend_class()
            is_available = backend.is_available
            capabilities = [cap for cap in BackendCapability if backend.supports(cap)]
        except Exception as e:
            logger.warning(f"Error getting backend info for '{backend_id}': {e}")
            is_available = False
            capabilities = []

        return {
            "backend_id": backend_id,
            "display_name": entry.display_name,
            "priority": entry.priority,
            "description": entry.description,
            "is_available": is_available,
            "capabilities": capabilities,
        }


# Module-level initialization: Import and auto-register backends
def _auto_register_backends() -> None:
    """Auto-register available backends on module import."""
    # Import backends and register them
    # This is done at module level to ensure they're available when factory is used

    # Try to register gt3x-rs backend (preferred, priority=10)
    try:
        from .gt3x_rs_backend import Gt3xRsBackend

        BackendFactory.register(
            backend_id="gt3x_rs",
            backend_class=Gt3xRsBackend,
            display_name="gt3x-rs (Rust)",
            priority=10,
            description="High-performance Rust implementation (52x faster than Python)",
        )
    except ImportError:
        logger.debug("gt3x-rs backend not available (import failed)")

    # Try to register pygt3x backend (fallback, priority=50)
    try:
        from .pygt3x_backend import PyGt3xBackend

        BackendFactory.register(
            backend_id="pygt3x",
            backend_class=PyGt3xBackend,
            display_name="PyGt3x (Python)",
            priority=50,
            description="Python fallback implementation using pygt3x and numpy",
        )
    except ImportError:
        logger.debug("pygt3x backend not available (import failed)")


# Auto-register backends on module import
_auto_register_backends()
