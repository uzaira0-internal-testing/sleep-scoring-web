#!/usr/bin/env python3
"""
Memory Management Module for Sleep Scoring Application
Provides bounded caches and resource cleanup mechanisms.
"""

from __future__ import annotations

import gc
import sys
import weakref

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
import contextlib
from collections import OrderedDict
from datetime import datetime, timedelta
from threading import Lock
from typing import TYPE_CHECKING, Any, TypeVar

from sleep_scoring_app.core.constants import MemoryConstants
from sleep_scoring_app.core.exceptions import (
    ErrorCodes,
    SleepScoringMemoryError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")
K = TypeVar("K")


class BoundedCache[K, T]:
    """Thread-safe LRU cache with size limits and memory monitoring."""

    def __init__(self, max_size: int = MemoryConstants.CACHE_MAX_SIZE, max_memory_mb: int = MemoryConstants.CACHE_MAX_MEMORY_MB) -> None:
        self.max_size = max_size
        self.max_memory_mb = max_memory_mb
        self.cache: OrderedDict[K, T] = OrderedDict()
        self.access_times: dict[K, datetime] = {}
        self.memory_usage: dict[K, int] = {}
        self.lock = Lock()

    def get(self, key: K) -> T | None:
        """Get item from cache, updating access time."""
        with self.lock:
            if key in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                self.access_times[key] = datetime.now()
                return self.cache[key]
            return None

    def put(self, key: K, value: T, estimated_size_mb: int = 0) -> None:
        """Put item in cache with size estimation."""
        with self.lock:
            current_time = datetime.now()

            # If key already exists, update it
            if key in self.cache:
                self.cache.move_to_end(key)
                self.cache[key] = value
                self.access_times[key] = current_time
                self.memory_usage[key] = estimated_size_mb
                return

            # Check memory limit
            total_memory = sum(self.memory_usage.values()) + estimated_size_mb
            if total_memory > self.max_memory_mb:
                self._evict_by_memory()

                # Check again after eviction
                total_memory = sum(self.memory_usage.values()) + estimated_size_mb
                if total_memory > self.max_memory_mb:
                    msg = f"Cannot cache item: would exceed memory limit ({total_memory}MB > {self.max_memory_mb}MB)"
                    raise SleepScoringMemoryError(
                        msg,
                        ErrorCodes.MEMORY_LIMIT_EXCEEDED,
                    )

            # Add new item
            self.cache[key] = value
            self.access_times[key] = current_time
            self.memory_usage[key] = estimated_size_mb

            # Check size limit
            if len(self.cache) > self.max_size:
                self._evict_by_size()

    def _evict_by_size(self) -> None:
        """Evict oldest items to stay within size limit."""
        while len(self.cache) > self.max_size:
            key = next(iter(self.cache))
            del self.cache[key]
            del self.access_times[key]
            del self.memory_usage[key]

    def _evict_by_memory(self) -> None:
        """Evict items to stay within memory limit."""
        # Sort by access time (oldest first)
        sorted_keys = sorted(self.access_times.keys(), key=lambda k: self.access_times[k])

        while sum(self.memory_usage.values()) > self.max_memory_mb * MemoryConstants.MEMORY_UTILIZATION_THRESHOLD and sorted_keys:
            key = sorted_keys.pop(0)
            if key in self.cache:
                del self.cache[key]
                del self.access_times[key]
                del self.memory_usage[key]

    def clear(self) -> None:
        """Clear all cached items."""
        with self.lock:
            self.cache.clear()
            self.access_times.clear()
            self.memory_usage.clear()

    def invalidate(self, key: K) -> None:
        """Remove a specific item from the cache."""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                self.access_times.pop(key, None)
                self.memory_usage.pop(key, None)

    def remove(self, key: K, default: T | None = None) -> T | None:
        """Remove and return an item from the cache."""
        with self.lock:
            if key in self.cache:
                value = self.cache.pop(key)
                self.access_times.pop(key, None)
                self.memory_usage.pop(key, None)
                return value
            return default

    def __len__(self) -> int:
        """Return the number of items in the cache."""
        with self.lock:
            return len(self.cache)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "memory_usage_mb": sum(self.memory_usage.values()),
                "max_memory_mb": self.max_memory_mb,
                "utilization": self._safe_utilization_calc(),
            }

    def _safe_utilization_calc(self) -> float:
        """Safe utilization calculation that handles mock objects during testing."""
        try:
            return len(self.cache) / self.max_size if self.max_size > 0 else 0
        except (TypeError, AttributeError, ZeroDivisionError):
            # Handle mock objects or invalid values during testing
            return 0.0

    def cleanup(self) -> int:
        """Perform cleanup by removing old entries. Alias for cleanup_old_entries."""
        return self.cleanup_old_entries()

    def cleanup_old_entries(self, max_age_hours: int = MemoryConstants.DEFAULT_MAX_AGE_HOURS) -> int:
        """Remove entries older than specified age."""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        removed_count = 0

        with self.lock:
            keys_to_remove = [key for key, access_time in self.access_times.items() if access_time < cutoff_time]

            for key in keys_to_remove:
                if key in self.cache:
                    del self.cache[key]
                    del self.access_times[key]
                    del self.memory_usage[key]
                    removed_count += 1

        return removed_count

    def __contains__(self, key: K) -> bool:
        """Check if key exists in cache."""
        with self.lock:
            return key in self.cache

    def keys(self) -> list[K]:
        """Return cache keys."""
        with self.lock:
            return list(self.cache.keys())

    def pop(self, key: K, default=None) -> T | None:
        """Remove and return item from cache."""
        with self.lock:
            if key in self.cache:
                value = self.cache[key]
                del self.cache[key]
                del self.access_times[key]
                del self.memory_usage[key]
                return value
            return default


class ResourceManager:
    """Manages application resources and prevents resource leaks."""

    def __init__(self) -> None:
        self.resource_registry: dict[str, Any] = {}
        self.cleanup_callbacks: dict[str, Callable] = {}
        self.weak_refs: dict[str, weakref.ref] = {}
        self.lock = Lock()

    def register_resource(self, resource_id: str, resource: Any, cleanup_callback: Callable | None = None) -> None:
        """Register a resource for tracking and cleanup."""
        with self.lock:
            self.resource_registry[resource_id] = resource

            if cleanup_callback:
                self.cleanup_callbacks[resource_id] = cleanup_callback

            # Create weak reference for automatic cleanup
            def cleanup_ref(ref) -> None:
                with self.lock:
                    if resource_id in self.resource_registry:
                        del self.resource_registry[resource_id]
                    if resource_id in self.cleanup_callbacks:
                        del self.cleanup_callbacks[resource_id]
                    if resource_id in self.weak_refs:
                        del self.weak_refs[resource_id]

            self.weak_refs[resource_id] = weakref.ref(resource, cleanup_ref)

    def unregister_resource(self, resource_id: str) -> None:
        """Unregister and cleanup a resource."""
        with self.lock:
            if resource_id in self.cleanup_callbacks:
                with contextlib.suppress(Exception):
                    self.cleanup_callbacks[resource_id]()
                del self.cleanup_callbacks[resource_id]

            if resource_id in self.resource_registry:
                del self.resource_registry[resource_id]

            if resource_id in self.weak_refs:
                del self.weak_refs[resource_id]

    def cleanup_all_resources(self) -> None:
        """Cleanup all registered resources."""
        with self.lock:
            for resource_id in list(self.cleanup_callbacks.keys()):
                with contextlib.suppress(Exception):
                    self.cleanup_callbacks[resource_id]()

            self.cleanup_callbacks.clear()
            self.resource_registry.clear()
            self.weak_refs.clear()

    def get_resource_count(self) -> int:
        """Get number of registered resources."""
        with self.lock:
            return len(self.resource_registry)

    def get_resource_stats(self) -> dict[str, Any]:
        """Get resource statistics."""
        with self.lock:
            return {
                "total_resources": len(self.resource_registry),
                "resources_with_cleanup": len(self.cleanup_callbacks),
                "weak_references": len(self.weak_refs),
            }


class MemoryMonitor:
    """Monitors memory usage and provides alerts."""

    def __init__(
        self,
        warning_threshold_mb: int = MemoryConstants.MEMORY_WARNING_THRESHOLD_MB,
        critical_threshold_mb: int = MemoryConstants.MEMORY_CRITICAL_THRESHOLD_MB,
    ) -> None:
        self.warning_threshold_mb = warning_threshold_mb
        self.critical_threshold_mb = critical_threshold_mb
        self.last_warning_time = datetime.min
        self.last_critical_time = datetime.min

    def check_memory_usage(self) -> dict[str, Any]:
        """Check current memory usage and return status."""
        try:
            if not HAS_PSUTIL:
                return {
                    "memory_mb": 0,
                    "warning_threshold": self.warning_threshold_mb,
                    "critical_threshold": self.critical_threshold_mb,
                    "status": "ok",
                    "error": "psutil not available",
                }

            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            status = {
                "memory_mb": memory_mb,
                "warning_threshold": self.warning_threshold_mb,
                "critical_threshold": self.critical_threshold_mb,
                "status": "ok",
            }

            current_time = datetime.now()

            if memory_mb > self.critical_threshold_mb:
                status["status"] = "critical"
                # Only alert once per minute
                if (current_time - self.last_critical_time).total_seconds() > 60:
                    self.last_critical_time = current_time

            elif memory_mb > self.warning_threshold_mb:
                status["status"] = "warning"
                # Only alert once per 5 minutes
                if (current_time - self.last_warning_time).total_seconds() > 300:
                    self.last_warning_time = current_time

            return status

        except (OSError, AttributeError, ValueError) as e:
            return {"error": str(e), "status": "error"}

    def force_garbage_collection(self) -> dict[str, Any]:
        """Force garbage collection and return stats."""
        before_stats = self.check_memory_usage()

        # Force garbage collection
        collected = gc.collect()

        after_stats = self.check_memory_usage()

        return {
            "objects_collected": collected,
            "memory_before_mb": before_stats.get("memory_mb", 0),
            "memory_after_mb": after_stats.get("memory_mb", 0),
            "memory_freed_mb": before_stats.get("memory_mb", 0) - after_stats.get("memory_mb", 0),
        }

    def get_stats(self) -> dict[str, Any]:
        """Get memory and cache statistics."""
        memory_stats = self.check_memory_usage()

        # Count active cache instances (from global registries)
        cache_count = 0
        try:
            # Try to count cache instances from global variables
            for obj in sys.modules.get(__name__, {}).__dict__.values():
                if isinstance(obj, BoundedCache):
                    cache_count += 1
        except (AttributeError, TypeError, ValueError):
            # Fallback if introspection fails
            cache_count = 0

        return {
            "cache_count": cache_count,
            "total_memory_mb": memory_stats.get("memory_mb", 0),
            "memory_status": memory_stats.get("status", "unknown"),
            "warning_threshold_mb": self.warning_threshold_mb,
            "critical_threshold_mb": self.critical_threshold_mb,
        }


# Global instances
memory_monitor = MemoryMonitor()
resource_manager = ResourceManager()


def estimate_object_size_mb(obj: Any) -> int:
    """
    Estimate object size in MB.

    Args:
        obj: Object to estimate size for

    Returns:
        Estimated size in MB

    """
    try:
        size_bytes = sys.getsizeof(obj)

        # For containers, estimate contents
        if hasattr(obj, "__len__"):
            size_bytes += len(obj) * 100  # Rough estimate

        # For pandas objects
        if hasattr(obj, "memory_usage"):
            with contextlib.suppress(Exception):
                size_bytes = obj.memory_usage(deep=True).sum()

        # For numpy arrays
        if hasattr(obj, "nbytes"):
            size_bytes = obj.nbytes

        return max(1, size_bytes // (1024 * 1024))

    except (AttributeError, TypeError, ValueError):
        return 1  # Default to 1MB if estimation fails


def cleanup_resources() -> None:
    """Cleanup all managed resources and force garbage collection."""
    resource_manager.cleanup_all_resources()
    memory_monitor.force_garbage_collection()


def get_memory_stats() -> dict[str, Any]:
    """
    Get comprehensive memory statistics.

    Returns:
        Dictionary with memory statistics

    """
    memory_stats = memory_monitor.check_memory_usage()
    resource_stats = resource_manager.get_resource_stats()

    return {
        "memory": memory_stats,
        "resources": resource_stats,
        "gc_stats": {
            "counts": gc.get_count(),
            "stats": gc.get_stats() if hasattr(gc, "get_stats") else None,
        },
    }
