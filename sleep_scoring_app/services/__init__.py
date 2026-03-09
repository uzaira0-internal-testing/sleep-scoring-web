# Services package for Sleep Scoring Application
#
# Use explicit imports to avoid circular dependencies:
#   from sleep_scoring_app.services.unified_data_service import UnifiedDataService
#   from sleep_scoring_app.services.protocols import FileDiscoveryProtocol

from typing import Any

__all__ = [
    # Concrete services (import from submodules)
    "AlgorithmService",
    # Protocols (import from protocols.py)
    "AlgorithmServiceProtocol",
    "CSVDataTransformer",
    "CacheService",
    "DataSourceConfigProtocol",
    "DiaryServiceProtocol",
    "ExportServiceProtocol",
    "FileDiscoveryProtocol",
    "FileFormatDetector",
    "FileService",
    "ImportProgress",
    "ImportProgressTracker",
    "MarkerCacheProtocol",
    "MarkerService",
    "NonwearServiceProtocol",
    "UnifiedDataService",
    # Functions
    "get_algorithm_service",
]


def __getattr__(name: str) -> Any:
    """Lazy import to avoid circular dependencies."""
    if name == "AlgorithmService":
        from sleep_scoring_app.services.algorithm_service import AlgorithmService

        return AlgorithmService
    if name == "CacheService":
        from sleep_scoring_app.services.cache_service import CacheService

        return CacheService
    if name == "get_algorithm_service":
        from sleep_scoring_app.services.algorithm_service import get_algorithm_service

        return get_algorithm_service
    if name == "CSVDataTransformer":
        from sleep_scoring_app.services.csv_data_transformer import CSVDataTransformer

        return CSVDataTransformer
    if name == "FileFormatDetector":
        from sleep_scoring_app.services.file_format_detector import FileFormatDetector

        return FileFormatDetector
    if name == "FileService":
        from sleep_scoring_app.services.file_service import FileService

        return FileService
    if name in ("ImportProgress", "ImportProgressTracker"):
        from sleep_scoring_app.services import import_progress_tracker

        return getattr(import_progress_tracker, name)
    if name == "MarkerService":
        from sleep_scoring_app.services.marker_service import MarkerService

        return MarkerService
    if name == "UnifiedDataService":
        from sleep_scoring_app.services.unified_data_service import UnifiedDataService

        return UnifiedDataService
    if name in (
        "AlgorithmServiceProtocol",
        "DataSourceConfigProtocol",
        "DiaryServiceProtocol",
        "ExportServiceProtocol",
        "FileDiscoveryProtocol",
        "MarkerCacheProtocol",
        "NonwearServiceProtocol",
    ):
        from sleep_scoring_app.services import protocols

        return getattr(protocols, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
