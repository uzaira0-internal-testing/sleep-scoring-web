#!/usr/bin/env python3
"""Centralized cache management service."""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.services.memory_service import BoundedCache

if TYPE_CHECKING:
    from sleep_scoring_app.data.database import DatabaseManager
    from sleep_scoring_app.services.file_service import FileService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheConfig:
    """Immutable cache configuration."""

    algorithm_results_maxsize: int = 50
    algorithm_results_memory_mb: int = 100
    marker_status_maxsize: int = 500
    marker_status_memory_mb: int = 50
    activity_data_maxsize: int = 10
    activity_data_memory_mb: int = 100
    metrics_maxsize: int = 100
    metrics_memory_mb: int = 50
    current_date_maxsize: int = 10
    current_date_memory_mb: int = 100
    diary_data_maxsize: int = 100
    diary_data_memory_mb: int = 10


class LRUCache:
    """Simple LRU cache implementation with hit/miss tracking."""

    def __init__(self, maxsize: int = 100) -> None:
        self._maxsize = maxsize
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        """Get value from cache, updating LRU order."""
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def set(self, key: str, value: Any) -> None:
        """Set value in cache with LRU eviction."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def invalidate(self, key: str) -> None:
        """Remove specific key from cache."""
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    @property
    def stats(self) -> dict[str, int | float]:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "maxsize": self._maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total * 100, 1) if total > 0 else 0.0,
        }


class CacheService:
    """
    Centralized cache management for the application.

    Consolidates cache operations previously spread across:
    - CacheCoordinationService
    - AlgorithmDataService
    - Individual caches in FileService
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        file_service: FileService,
        config: CacheConfig | None = None,
    ) -> None:
        """
        Initialize CacheService.

        Args:
            db_manager: Database manager instance
            file_service: File service for coordinated operations
            config: Optional cache configuration

        """
        self.db_manager = db_manager
        self._file_service = file_service

        cfg = config or CacheConfig()

        # Named caches using BoundedCache for memory management
        self._caches: dict[str, BoundedCache] = {
            "algorithm_results": BoundedCache(
                max_size=cfg.algorithm_results_maxsize,
                max_memory_mb=cfg.algorithm_results_memory_mb,
            ),
            "marker_status": BoundedCache(
                max_size=cfg.marker_status_maxsize,
                max_memory_mb=cfg.marker_status_memory_mb,
            ),
            "activity_data": BoundedCache(
                max_size=cfg.activity_data_maxsize,
                max_memory_mb=cfg.activity_data_memory_mb,
            ),
            "metrics": BoundedCache(
                max_size=cfg.metrics_maxsize,
                max_memory_mb=cfg.metrics_memory_mb,
            ),
        }

        # Application-level caches (previously in CacheCoordinationService)
        self.current_date_48h_cache = BoundedCache(
            max_size=cfg.current_date_maxsize,
            max_memory_mb=cfg.current_date_memory_mb,
        )
        self.diary_data_cache = BoundedCache(
            max_size=cfg.diary_data_maxsize,
            max_memory_mb=cfg.diary_data_memory_mb,
        )

    # === Named Cache Operations ===

    def get(self, cache_type: str, key: str) -> Any | None:
        """
        Get value from specified cache.

        Args:
            cache_type: One of "algorithm_results", "marker_status", "activity_data", "metrics"
            key: Cache key

        Returns:
            Cached value or None if not found

        """
        cache = self._caches.get(cache_type)
        if cache is None:
            logger.warning("Unknown cache type: %s", cache_type)
            return None
        return cache.get(key)

    def set(self, cache_type: str, key: str, value: Any, estimated_size_mb: int = 0) -> None:
        """
        Set value in specified cache.

        Args:
            cache_type: One of "algorithm_results", "marker_status", "activity_data", "metrics"
            key: Cache key
            value: Value to cache
            estimated_size_mb: Estimated size in MB for memory tracking

        """
        cache = self._caches.get(cache_type)
        if cache is None:
            logger.warning("Unknown cache type: %s", cache_type)
            return
        cache.put(key, value, estimated_size_mb)

    def invalidate(self, cache_type: str, key: str | None = None) -> None:
        """
        Invalidate cache entries.

        Args:
            cache_type: One of "algorithm_results", "marker_status", "activity_data", "metrics"
            key: Specific key to invalidate, or None to clear entire cache

        """
        cache = self._caches.get(cache_type)
        if cache is None:
            return
        if key:
            cache.invalidate(key)
        else:
            cache.clear()

    def invalidate_all(self) -> None:
        """Clear all named caches."""
        for cache in self._caches.values():
            cache.clear()

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """
        Get statistics for all caches.

        Returns:
            Dictionary mapping cache names to their statistics

        """
        stats = {name: cache.get_stats() for name, cache in self._caches.items()}
        stats["current_date_48h_cache"] = self.current_date_48h_cache.get_stats()
        stats["diary_data_cache"] = self.diary_data_cache.get_stats()
        return stats

    # === Marker Status Cache (delegates to FileService) ===

    def invalidate_marker_status_cache(self, filename: str | None = None) -> None:
        """
        Invalidate marker status cache.

        Args:
            filename: Specific file to invalidate, or None for all files

        """
        marker_cache = self._caches.get("marker_status")
        if marker_cache:
            # Clear the cache (file-specific invalidation not implemented yet)
            marker_cache.clear()
            logger.debug(f"Invalidated marker status cache (filename: {filename})")

    # === Date Ranges Cache ===

    def invalidate_date_ranges_cache(self) -> None:
        """Invalidate date ranges cache."""
        # Date ranges are stored in FileService's main cache
        self._file_service.main_48h_data_cache.clear()
        logger.debug("Invalidated date ranges cache")

    # === Main Data Cache ===

    def invalidate_main_data_cache(self) -> None:
        """Invalidate main data cache."""
        self._file_service.main_48h_data_cache.clear()
        logger.debug("Invalidated main data cache")

    # === Algorithm Caches ===

    def clear_all_algorithm_caches(self) -> None:
        """Clear all algorithm-related caches (service-owned only)."""
        self.current_date_48h_cache.clear()
        self._file_service.main_48h_data_cache.clear()
        logger.info("Cleared all service-owned algorithm caches")

    # === File-Specific Cache Clearing ===

    def clear_file_cache(self, filename: str) -> None:
        """
        Clear all cached data for a specific file.

        Args:
            filename: File to clear cache for

        """
        # Clear main data cache (contains file-specific data)
        self._file_service.main_48h_data_cache.clear()
        # Clear all algorithm caches
        self.clear_all_algorithm_caches()
        logger.debug(f"Cleared cache for file: {filename}")

    # === Diary Cache ===

    def clear_diary_cache(self) -> None:
        """Clear the diary data cache."""
        try:
            self.diary_data_cache.clear()
            logger.debug("Diary data cache cleared")
        except Exception as e:
            logger.exception("Failed to clear diary cache: %s", e)

    # === Combined Cache Operations ===

    def clear_all_caches_on_mode_change(self) -> None:
        """Clear all caches when database/CSV mode changes."""
        self.clear_all_algorithm_caches()
        self.invalidate_marker_status_cache()
        self.invalidate_date_ranges_cache()
        self.invalidate_main_data_cache()

    def clear_all_caches_on_activity_column_change(self) -> None:
        """Clear all caches when activity column preference changes."""
        self.clear_all_algorithm_caches()
        self.invalidate_marker_status_cache()
        self.invalidate_date_ranges_cache()
        self.invalidate_main_data_cache()

    # === Cache Cleanup ===

    def cleanup_caches_if_needed(self, available_files: list) -> None:
        """
        Perform periodic cache cleanup.

        Args:
            available_files: List of all available files

        """
        try:
            max_files = 1000  # Match FileService._max_files
            if len(available_files) > max_files * 0.8:
                logger.info("Files approaching limit, performing cache cleanup")
                self.invalidate_date_ranges_cache()

                # Keep only most recent 3 main data entries
                main_cache = self._file_service.main_48h_data_cache
                while len(main_cache.cache) > 3:
                    oldest_key = next(iter(main_cache.cache))
                    del main_cache.cache[oldest_key]
                    if oldest_key in main_cache.access_times:
                        del main_cache.access_times[oldest_key]
                    if oldest_key in main_cache.memory_usage:
                        del main_cache.memory_usage[oldest_key]
        except Exception as e:
            logger.warning("Error during cache cleanup: %s", e)
