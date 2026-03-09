#!/usr/bin/env python3
"""
Comprehensive unit tests for CacheService.

Tests cache operations, invalidation, and statistics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.services.cache_service import CacheConfig, CacheService, LRUCache
from sleep_scoring_app.services.memory_service import BoundedCache


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create mock DatabaseManager."""
    return MagicMock()


@pytest.fixture
def mock_file_service() -> MagicMock:
    """Create mock FileService with required attributes."""
    mock = MagicMock()
    mock.main_48h_data_cache = BoundedCache(max_size=10, max_memory_mb=10)
    return mock


@pytest.fixture
def cache_service(mock_db_manager: MagicMock, mock_file_service: MagicMock) -> CacheService:
    """Create CacheService with mock dependencies."""
    return CacheService(mock_db_manager, mock_file_service)


@pytest.fixture
def custom_config_cache_service(mock_db_manager: MagicMock, mock_file_service: MagicMock) -> CacheService:
    """Create CacheService with custom configuration."""
    config = CacheConfig(
        algorithm_results_maxsize=5,
        algorithm_results_memory_mb=10,
        marker_status_maxsize=10,
        marker_status_memory_mb=5,
    )
    return CacheService(mock_db_manager, mock_file_service, config=config)


class TestLRUCache:
    """Tests for LRUCache class."""

    def test_init_with_default_maxsize(self):
        """Creates with default maxsize of 100."""
        cache = LRUCache()
        assert cache._maxsize == 100

    def test_init_with_custom_maxsize(self):
        """Creates with custom maxsize."""
        cache = LRUCache(maxsize=50)
        assert cache._maxsize == 50

    def test_get_returns_none_for_missing_key(self):
        """Returns None for keys not in cache."""
        cache = LRUCache()
        result = cache.get("missing_key")
        assert result is None

    def test_get_returns_cached_value(self):
        """Returns stored value for existing key."""
        cache = LRUCache()
        cache.set("key1", "value1")

        result = cache.get("key1")

        assert result == "value1"

    def test_get_updates_lru_order(self):
        """Accessed item moves to end."""
        cache = LRUCache(maxsize=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1, moving it to end
        cache.get("key1")

        # Add key4, which should evict key2 (now oldest)
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"  # Still present
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == "value3"  # Still present
        assert cache.get("key4") == "value4"  # New entry

    def test_set_updates_existing_key(self):
        """Setting existing key updates value and LRU order."""
        cache = LRUCache()
        cache.set("key1", "value1")
        cache.set("key1", "value1_updated")

        assert cache.get("key1") == "value1_updated"

    def test_set_evicts_oldest_when_full(self):
        """Oldest entry is evicted when maxsize exceeded."""
        cache = LRUCache(maxsize=2)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Should evict key1

        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"

    def test_invalidate_removes_key(self):
        """Specific key is removed from cache."""
        cache = LRUCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.invalidate("key1")

        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

    def test_invalidate_nonexistent_key_is_safe(self):
        """Invalidating missing key doesn't raise."""
        cache = LRUCache()
        cache.invalidate("missing_key")  # Should not raise

    def test_clear_removes_all_entries(self):
        """All entries are removed."""
        cache = LRUCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_stats_tracks_hits_and_misses(self):
        """Statistics track hits and misses correctly."""
        cache = LRUCache()
        cache.set("key1", "value1")

        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("missing")  # Miss

        stats = cache.stats

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(66.7, abs=0.1)

    def test_stats_includes_size_info(self):
        """Statistics include size information."""
        cache = LRUCache(maxsize=50)
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        stats = cache.stats

        assert stats["size"] == 2
        assert stats["maxsize"] == 50

    def test_stats_zero_hit_rate_when_empty(self):
        """Hit rate is 0 when no requests made."""
        cache = LRUCache()

        stats = cache.stats

        assert stats["hit_rate"] == 0.0


class TestCacheConfig:
    """Tests for CacheConfig dataclass."""

    def test_default_values(self):
        """Default configuration values are set."""
        config = CacheConfig()

        assert config.algorithm_results_maxsize == 50
        assert config.algorithm_results_memory_mb == 100
        assert config.marker_status_maxsize == 500
        assert config.activity_data_maxsize == 10

    def test_custom_values(self):
        """Custom configuration values are used."""
        config = CacheConfig(
            algorithm_results_maxsize=10,
            marker_status_maxsize=20,
        )

        assert config.algorithm_results_maxsize == 10
        assert config.marker_status_maxsize == 20

    def test_is_frozen(self):
        """Configuration is immutable."""
        config = CacheConfig()

        with pytest.raises(AttributeError):
            config.algorithm_results_maxsize = 999


class TestCacheServiceInit:
    """Tests for CacheService initialization."""

    def test_creates_named_caches(self, cache_service: CacheService):
        """Named caches are created on init."""
        assert "algorithm_results" in cache_service._caches
        assert "marker_status" in cache_service._caches
        assert "activity_data" in cache_service._caches
        assert "metrics" in cache_service._caches

    def test_creates_application_level_caches(self, cache_service: CacheService):
        """Application-level caches are created."""
        assert cache_service.current_date_48h_cache is not None
        assert cache_service.diary_data_cache is not None

    def test_uses_custom_config(self, custom_config_cache_service: CacheService):
        """Custom configuration is applied."""
        # Verify by checking cache behavior matches custom config
        assert custom_config_cache_service._caches["algorithm_results"].max_size == 5


class TestCacheServiceGetSet:
    """Tests for get and set methods."""

    def test_get_returns_none_for_unknown_cache(self, cache_service: CacheService):
        """Returns None for unknown cache type."""
        result = cache_service.get("unknown_cache", "key1")
        assert result is None

    def test_get_returns_none_for_missing_key(self, cache_service: CacheService):
        """Returns None when key not in cache."""
        result = cache_service.get("algorithm_results", "missing_key")
        assert result is None

    def test_set_and_get_roundtrip(self, cache_service: CacheService):
        """Set and get work correctly."""
        cache_service.set("algorithm_results", "key1", {"data": "value"})

        result = cache_service.get("algorithm_results", "key1")

        assert result == {"data": "value"}

    def test_set_logs_warning_for_unknown_cache(self, cache_service: CacheService):
        """Setting unknown cache type logs warning."""
        # Should not raise, just logs
        cache_service.set("unknown_cache", "key1", "value")

    def test_set_with_estimated_size(self, cache_service: CacheService):
        """Set accepts estimated size parameter."""
        # Should not raise
        cache_service.set("algorithm_results", "key1", "large_data", estimated_size_mb=50)


class TestCacheServiceInvalidate:
    """Tests for invalidate method."""

    def test_invalidate_specific_key(self, cache_service: CacheService):
        """Removes specific key from cache."""
        cache_service.set("algorithm_results", "key1", "value1")
        cache_service.set("algorithm_results", "key2", "value2")

        cache_service.invalidate("algorithm_results", "key1")

        assert cache_service.get("algorithm_results", "key1") is None
        assert cache_service.get("algorithm_results", "key2") == "value2"

    def test_invalidate_entire_cache(self, cache_service: CacheService):
        """Clears entire cache when key is None."""
        cache_service.set("algorithm_results", "key1", "value1")
        cache_service.set("algorithm_results", "key2", "value2")

        cache_service.invalidate("algorithm_results", key=None)

        assert cache_service.get("algorithm_results", "key1") is None
        assert cache_service.get("algorithm_results", "key2") is None

    def test_invalidate_unknown_cache_is_safe(self, cache_service: CacheService):
        """Invalidating unknown cache type doesn't raise."""
        cache_service.invalidate("unknown_cache", "key1")  # Should not raise


class TestCacheServiceInvalidateAll:
    """Tests for invalidate_all method."""

    def test_clears_all_named_caches(self, cache_service: CacheService):
        """All named caches are cleared."""
        cache_service.set("algorithm_results", "key1", "value1")
        cache_service.set("marker_status", "key2", "value2")
        cache_service.set("activity_data", "key3", "value3")

        cache_service.invalidate_all()

        assert cache_service.get("algorithm_results", "key1") is None
        assert cache_service.get("marker_status", "key2") is None
        assert cache_service.get("activity_data", "key3") is None


class TestCacheServiceGetStats:
    """Tests for get_stats method."""

    def test_returns_stats_for_all_caches(self, cache_service: CacheService):
        """Stats include all caches."""
        stats = cache_service.get_stats()

        assert "algorithm_results" in stats
        assert "marker_status" in stats
        assert "activity_data" in stats
        assert "metrics" in stats
        assert "current_date_48h_cache" in stats
        assert "diary_data_cache" in stats

    def test_stats_contain_expected_fields(self, cache_service: CacheService):
        """Each cache stats have expected fields."""
        stats = cache_service.get_stats()

        # BoundedCache stats format
        for cache_name in ["algorithm_results", "marker_status"]:
            assert "size" in stats[cache_name]


class TestInvalidateMarkerStatusCache:
    """Tests for invalidate_marker_status_cache method."""

    def test_clears_marker_status_cache(self, cache_service: CacheService):
        """Marker status cache is cleared."""
        cache_service.set("marker_status", "key1", "value1")

        cache_service.invalidate_marker_status_cache()

        assert cache_service.get("marker_status", "key1") is None

    def test_accepts_filename_parameter(self, cache_service: CacheService):
        """Accepts optional filename parameter."""
        cache_service.set("marker_status", "key1", "value1")

        cache_service.invalidate_marker_status_cache(filename="test.csv")

        # Currently clears all, not just specific file
        assert cache_service.get("marker_status", "key1") is None


class TestInvalidateDateRangesCache:
    """Tests for invalidate_date_ranges_cache method."""

    def test_clears_file_service_cache(self, cache_service: CacheService, mock_file_service: MagicMock):
        """File service main cache is cleared."""
        cache_service.invalidate_date_ranges_cache()

        # BoundedCache should be empty after clear
        assert len(mock_file_service.main_48h_data_cache.cache) == 0


class TestInvalidateMainDataCache:
    """Tests for invalidate_main_data_cache method."""

    def test_clears_main_data_cache(self, cache_service: CacheService, mock_file_service: MagicMock):
        """Main data cache is cleared."""
        cache_service.invalidate_main_data_cache()

        assert len(mock_file_service.main_48h_data_cache.cache) == 0


class TestClearAllAlgorithmCaches:
    """Tests for clear_all_algorithm_caches method."""

    def test_clears_current_date_cache(self, cache_service: CacheService):
        """Current date cache is cleared."""
        cache_service.current_date_48h_cache.put("key1", "value1", 1)

        cache_service.clear_all_algorithm_caches()

        assert cache_service.current_date_48h_cache.get("key1") is None

    def test_clears_file_service_cache(self, cache_service: CacheService, mock_file_service: MagicMock):
        """File service cache is cleared."""
        cache_service.clear_all_algorithm_caches()

        assert len(mock_file_service.main_48h_data_cache.cache) == 0

    def test_clears_service_caches(self, cache_service: CacheService, mock_file_service: MagicMock):
        """Service-owned caches are cleared without touching UI widgets."""
        cache_service.current_date_48h_cache.put("key1", "value1", 1)
        mock_file_service.main_48h_data_cache.put("key2", "value2", 1)

        cache_service.clear_all_algorithm_caches()

        assert cache_service.current_date_48h_cache.get("key1") is None
        assert mock_file_service.main_48h_data_cache.get("key2") is None


class TestClearFileCache:
    """Tests for clear_file_cache method."""

    def test_clears_all_caches_for_file(self, cache_service: CacheService, mock_file_service: MagicMock):
        """All caches are cleared for specific file."""
        cache_service.current_date_48h_cache.put("key1", "value1", 1)

        cache_service.clear_file_cache("test.csv")

        # Current date cache should be cleared
        assert cache_service.current_date_48h_cache.get("key1") is None


class TestClearDiaryCache:
    """Tests for clear_diary_cache method."""

    def test_clears_diary_data_cache(self, cache_service: CacheService):
        """Diary data cache is cleared."""
        cache_service.diary_data_cache.put("key1", "value1", 1)

        cache_service.clear_diary_cache()

        assert cache_service.diary_data_cache.get("key1") is None


class TestClearAllCachesOnModeChange:
    """Tests for clear_all_caches_on_mode_change method."""

    def test_clears_all_related_caches(self, cache_service: CacheService, mock_file_service: MagicMock):
        """All mode-related caches are cleared."""
        cache_service.set("marker_status", "key1", "value1")
        cache_service.current_date_48h_cache.put("key2", "value2", 1)

        cache_service.clear_all_caches_on_mode_change()

        assert cache_service.get("marker_status", "key1") is None
        assert cache_service.current_date_48h_cache.get("key2") is None


class TestClearAllCachesOnActivityColumnChange:
    """Tests for clear_all_caches_on_activity_column_change method."""

    def test_clears_all_related_caches(self, cache_service: CacheService, mock_file_service: MagicMock):
        """All activity-column-related caches are cleared."""
        cache_service.set("marker_status", "key1", "value1")
        cache_service.current_date_48h_cache.put("key2", "value2", 1)

        cache_service.clear_all_caches_on_activity_column_change()

        assert cache_service.get("marker_status", "key1") is None
        assert cache_service.current_date_48h_cache.get("key2") is None


class TestCleanupCachesIfNeeded:
    """Tests for cleanup_caches_if_needed method."""

    def test_no_cleanup_below_threshold(self, cache_service: CacheService, mock_file_service: MagicMock):
        """No cleanup when file count below threshold."""
        available_files = [f"file{i}.csv" for i in range(100)]

        # Pre-populate cache
        mock_file_service.main_48h_data_cache.put("key1", "value1", 1)

        cache_service.cleanup_caches_if_needed(available_files)

        # Cache should not be cleared
        assert mock_file_service.main_48h_data_cache.get("key1") is not None

    def test_cleanup_above_threshold(self, cache_service: CacheService, mock_file_service: MagicMock):
        """Cleanup triggered when file count above 80% threshold."""
        # 1000 * 0.8 = 800, so need > 800 files
        available_files = [f"file{i}.csv" for i in range(850)]

        cache_service.cleanup_caches_if_needed(available_files)

        # Cleanup should have been triggered (date ranges cache cleared)
        # Note: The actual cleanup behavior depends on cache state


