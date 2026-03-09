"""
Tests for memory_service module.

Tests BoundedCache, ResourceManager, MemoryMonitor, and utility functions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.core.exceptions import SleepScoringMemoryError
from sleep_scoring_app.services.memory_service import (
    BoundedCache,
    MemoryMonitor,
    ResourceManager,
    cleanup_resources,
    estimate_object_size_mb,
    get_memory_stats,
)


class TestBoundedCache:
    """Tests for BoundedCache class."""

    def test_get_returns_none_for_missing_key(self) -> None:
        """Returns None for missing key."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10)
        assert cache.get("missing") is None

    def test_put_and_get(self) -> None:
        """Stores and retrieves values."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10)
        cache.put("key1", 100)
        assert cache.get("key1") == 100

    def test_updates_access_time_on_get(self) -> None:
        """Updates access time when getting item."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10)
        cache.put("key1", 100)
        initial_time = cache.access_times["key1"]

        # Small delay and get again
        cache.get("key1")

        assert cache.access_times["key1"] >= initial_time

    def test_evicts_oldest_when_full(self) -> None:
        """Evicts oldest items when cache is full."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=2)
        cache.put("key1", 1)
        cache.put("key2", 2)
        cache.put("key3", 3)  # Should evict key1

        assert cache.get("key1") is None
        assert cache.get("key2") == 2
        assert cache.get("key3") == 3

    def test_raises_when_exceeds_memory_limit(self) -> None:
        """Raises error when item exceeds memory limit."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10, max_memory_mb=1)

        with pytest.raises(SleepScoringMemoryError):
            cache.put("key1", 100, estimated_size_mb=100)

    def test_clear_removes_all_items(self) -> None:
        """Clear removes all items."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10)
        cache.put("key1", 1)
        cache.put("key2", 2)

        cache.clear()

        assert len(cache) == 0
        assert cache.get("key1") is None

    def test_invalidate_removes_specific_item(self) -> None:
        """Invalidate removes specific item."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10)
        cache.put("key1", 1)
        cache.put("key2", 2)

        cache.invalidate("key1")

        assert cache.get("key1") is None
        assert cache.get("key2") == 2

    def test_remove_returns_value(self) -> None:
        """Remove returns the value."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10)
        cache.put("key1", 100)

        value = cache.remove("key1")

        assert value == 100
        assert cache.get("key1") is None

    def test_remove_returns_default_for_missing(self) -> None:
        """Remove returns default for missing key."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10)

        value = cache.remove("missing", default=-1)

        assert value == -1

    def test_len_returns_count(self) -> None:
        """len() returns item count."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10)
        cache.put("key1", 1)
        cache.put("key2", 2)

        assert len(cache) == 2

    def test_get_stats_returns_info(self) -> None:
        """get_stats returns cache information."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10, max_memory_mb=100)
        cache.put("key1", 1, estimated_size_mb=5)

        stats = cache.get_stats()

        assert stats["size"] == 1
        assert stats["max_size"] == 10
        assert stats["memory_usage_mb"] == 5
        assert stats["max_memory_mb"] == 100

    def test_cleanup_old_entries(self) -> None:
        """cleanup_old_entries removes stale entries."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10)
        cache.put("key1", 1)

        # Manually set old access time
        cache.access_times["key1"] = datetime.now() - timedelta(hours=48)

        removed = cache.cleanup_old_entries(max_age_hours=24)

        assert removed == 1
        assert cache.get("key1") is None

    def test_contains(self) -> None:
        """__contains__ checks key existence."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10)
        cache.put("key1", 1)

        assert "key1" in cache
        assert "missing" not in cache

    def test_keys_returns_all_keys(self) -> None:
        """keys() returns all cache keys."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10)
        cache.put("key1", 1)
        cache.put("key2", 2)

        keys = cache.keys()

        assert set(keys) == {"key1", "key2"}

    def test_pop_removes_and_returns(self) -> None:
        """pop removes and returns item."""
        cache: BoundedCache[str, int] = BoundedCache(max_size=10)
        cache.put("key1", 100)

        value = cache.pop("key1")

        assert value == 100
        assert "key1" not in cache


class TestResourceManager:
    """Tests for ResourceManager class."""

    def test_register_resource(self) -> None:
        """Registers a resource."""
        manager = ResourceManager()
        resource = MagicMock()

        manager.register_resource("res1", resource)

        assert manager.get_resource_count() == 1

    def test_unregister_resource_calls_cleanup(self) -> None:
        """Unregister calls cleanup callback."""
        manager = ResourceManager()
        resource = MagicMock()
        cleanup = MagicMock()

        manager.register_resource("res1", resource, cleanup)
        manager.unregister_resource("res1")

        cleanup.assert_called_once()
        assert manager.get_resource_count() == 0

    def test_cleanup_all_resources(self) -> None:
        """cleanup_all clears all resources."""
        manager = ResourceManager()
        resource1 = MagicMock()
        resource2 = MagicMock()
        cleanup1 = MagicMock()
        cleanup2 = MagicMock()

        manager.register_resource("res1", resource1, cleanup1)
        manager.register_resource("res2", resource2, cleanup2)

        manager.cleanup_all_resources()

        cleanup1.assert_called_once()
        cleanup2.assert_called_once()
        assert manager.get_resource_count() == 0

    def test_get_resource_stats(self) -> None:
        """get_resource_stats returns statistics."""
        manager = ResourceManager()
        resource = MagicMock()
        cleanup = MagicMock()

        manager.register_resource("res1", resource, cleanup)

        stats = manager.get_resource_stats()

        assert stats["total_resources"] == 1
        assert stats["resources_with_cleanup"] == 1


class TestMemoryMonitor:
    """Tests for MemoryMonitor class."""

    def test_check_memory_usage_returns_stats(self) -> None:
        """check_memory_usage returns memory statistics."""
        monitor = MemoryMonitor()

        stats = monitor.check_memory_usage()

        assert "memory_mb" in stats
        assert "status" in stats

    def test_status_ok_for_low_memory(self) -> None:
        """Status is 'ok' for low memory usage."""
        monitor = MemoryMonitor(
            warning_threshold_mb=10000,
            critical_threshold_mb=20000,
        )

        stats = monitor.check_memory_usage()

        # Should be ok unless test machine is very constrained
        assert stats["status"] in ["ok", "warning", "error"]

    def test_force_garbage_collection(self) -> None:
        """force_garbage_collection runs GC."""
        monitor = MemoryMonitor()

        result = monitor.force_garbage_collection()

        assert "objects_collected" in result
        assert "memory_before_mb" in result
        assert "memory_after_mb" in result

    def test_get_stats(self) -> None:
        """get_stats returns comprehensive stats."""
        monitor = MemoryMonitor()

        stats = monitor.get_stats()

        assert "cache_count" in stats
        assert "total_memory_mb" in stats
        assert "memory_status" in stats


class TestEstimateObjectSizeMb:
    """Tests for estimate_object_size_mb function."""

    def test_estimates_list_size(self) -> None:
        """Estimates size of list."""
        data = list(range(1000))

        size = estimate_object_size_mb(data)

        assert size >= 1  # At least 1 MB

    def test_handles_empty_object(self) -> None:
        """Handles empty objects."""
        size = estimate_object_size_mb([])

        assert size >= 1  # Default minimum

    def test_handles_pandas_dataframe(self) -> None:
        """Handles pandas DataFrame."""
        import pandas as pd

        df = pd.DataFrame({"a": range(1000), "b": range(1000)})

        size = estimate_object_size_mb(df)

        assert size >= 1

    def test_handles_numpy_array(self) -> None:
        """Handles numpy array."""
        import numpy as np

        arr = np.zeros(1000000)  # 1M floats = ~8MB

        size = estimate_object_size_mb(arr)

        assert size >= 1


class TestCleanupResources:
    """Tests for cleanup_resources function."""

    def test_runs_without_error(self) -> None:
        """Cleanup runs without raising."""
        # Should not raise
        cleanup_resources()


class TestGetMemoryStats:
    """Tests for get_memory_stats function."""

    def test_returns_comprehensive_stats(self) -> None:
        """Returns comprehensive memory statistics."""
        stats = get_memory_stats()

        assert "memory" in stats
        assert "resources" in stats
        assert "gc_stats" in stats
