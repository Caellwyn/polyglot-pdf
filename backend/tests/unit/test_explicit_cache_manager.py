"""
Unit Tests for ExplicitCacheManager

Tests for explicit context caching, shared cache management,
automatic refresh, and metrics tracking.
"""

import pytest
import asyncio
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, mock_open

from backend.services.explicit_cache_manager import (
    ExplicitCacheManager,
    CacheInfo,
    initialize_global_cache_manager,
    get_cache_manager,
    shutdown_cache_manager
)


@pytest.fixture
def mock_form_kits_root(tmp_path):
    """Create mock form kits directory structure."""
    # Create i-90 form kit
    i90_dir = tmp_path / "i-90"
    i90_dir.mkdir()

    # Create schema
    i90_schema = {
        "id": "i-90",
        "title": "Application to Replace Permanent Resident Card",
        "version": "1.0",
        "fields": [
            {"id": "firstName", "type": "text", "label": "First Name"},
            {"id": "lastName", "type": "text", "label": "Last Name"}
        ]
    }

    with open(i90_dir / "schema.json", "w") as f:
        json.dump(i90_schema, f)

    # Create annotations
    i90_annotations = {
        "form_type": "i-90",
        "field_annotations": {
            "firstName": {
                "help_text": "Legal first name as on green card",
                "common_mistakes": ["Using nickname"]
            }
        }
    }

    with open(i90_dir / "i-90-annotations.json", "w") as f:
        json.dump(i90_annotations, f)

    return tmp_path


@pytest.fixture
def cache_manager(mock_form_kits_root):
    """Create ExplicitCacheManager instance."""
    return ExplicitCacheManager(form_kits_root=mock_form_kits_root)


class TestCacheInfo:
    """Test CacheInfo class."""

    def test_initialization(self):
        """Test CacheInfo initialization."""
        now = datetime.now()
        expires_at = now + timedelta(hours=24)

        info = CacheInfo(
            cache_id="cache_abc123",
            form_type="i-90",
            created_at=now,
            expires_at=expires_at,
            version="1.0",
            schema_hash="hash123"
        )

        assert info.cache_id == "cache_abc123"
        assert info.form_type == "i-90"
        assert info.created_at == now
        assert info.expires_at == expires_at
        assert info.version == "1.0"
        assert info.schema_hash == "hash123"
        assert info.access_count == 0
        assert info.last_accessed == now

    def test_record_access(self):
        """Test access counting."""
        now = datetime.now()
        info = CacheInfo(
            cache_id="cache_123",
            form_type="i-90",
            created_at=now,
            expires_at=now + timedelta(hours=24),
            version="1.0",
            schema_hash="hash"
        )

        assert info.access_count == 0

        info.record_access()
        assert info.access_count == 1
        assert info.last_accessed > now

        info.record_access()
        assert info.access_count == 2

    def test_time_until_expiry(self):
        """Test expiry time calculation."""
        now = datetime.now()
        expires_in_hours = 12

        info = CacheInfo(
            cache_id="cache_123",
            form_type="i-90",
            created_at=now,
            expires_at=now + timedelta(hours=expires_in_hours),
            version="1.0",
            schema_hash="hash"
        )

        time_left = info.time_until_expiry()
        # Allow small margin for execution time
        assert 11.9 < time_left.total_seconds() / 3600 < 12.1

    def test_should_refresh_within_threshold(self):
        """Test refresh decision when within threshold."""
        now = datetime.now()

        # Cache expires in 1 hour (within 2-hour threshold)
        info = CacheInfo(
            cache_id="cache_123",
            form_type="i-90",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            version="1.0",
            schema_hash="hash"
        )

        assert info.should_refresh(refresh_threshold_hours=2) is True

    def test_should_not_refresh_outside_threshold(self):
        """Test refresh decision when outside threshold."""
        now = datetime.now()

        # Cache expires in 10 hours (outside 2-hour threshold)
        info = CacheInfo(
            cache_id="cache_123",
            form_type="i-90",
            created_at=now,
            expires_at=now + timedelta(hours=10),
            version="1.0",
            schema_hash="hash"
        )

        assert info.should_refresh(refresh_threshold_hours=2) is False


class TestExplicitCacheManager:
    """Test ExplicitCacheManager class."""

    def test_initialization(self, mock_form_kits_root):
        """Test cache manager initialization."""
        manager = ExplicitCacheManager(form_kits_root=mock_form_kits_root)

        assert manager.form_kits_root == mock_form_kits_root
        assert manager.cache_registry == {}
        assert manager._refresh_task is None
        assert manager._enabled is False

    @pytest.mark.asyncio
    async def test_initialize_caches_success(self, cache_manager):
        """Test successful cache initialization."""
        with patch.object(cache_manager, '_create_gemini_cache', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "cache_test123"

            await cache_manager.initialize_caches()

            assert cache_manager._enabled is True
            assert "i-90" in cache_manager.cache_registry
            assert cache_manager._refresh_task is not None

            # Verify cache info
            i90_cache = cache_manager.cache_registry["i-90"]
            assert i90_cache.form_type == "i-90"
            assert i90_cache.cache_id == "cache_test123"
            assert i90_cache.version == "1.0"

    @pytest.mark.asyncio
    async def test_initialize_caches_missing_form(self, cache_manager):
        """Test cache initialization with missing form kit."""
        with patch.object(cache_manager, '_create_gemini_cache', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "cache_test123"

            # Initialize will skip i-589 and i-485 (not present)
            await cache_manager.initialize_caches()

            # Should still succeed with i-90
            assert cache_manager._enabled is True
            assert "i-90" in cache_manager.cache_registry
            assert "i-589" not in cache_manager.cache_registry
            assert "i-485" not in cache_manager.cache_registry

    @pytest.mark.asyncio
    async def test_get_cache_id(self, cache_manager):
        """Test getting cache ID for form type."""
        with patch.object(cache_manager, '_create_gemini_cache', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "cache_abc123"

            await cache_manager.initialize_caches()

            # Get cache ID
            cache_id = cache_manager.get_cache_id("i-90")
            assert cache_id == "cache_abc123"

            # Verify access was recorded
            assert cache_manager.cache_registry["i-90"].access_count == 1

    def test_get_cache_id_not_found(self, cache_manager):
        """Test getting cache ID for non-existent form."""
        cache_id = cache_manager.get_cache_id("i-999")
        assert cache_id is None

    def test_load_form_schema(self, cache_manager):
        """Test loading form schema from disk."""
        schema = cache_manager._load_form_schema("i-90")

        assert schema["id"] == "i-90"
        assert schema["title"] == "Application to Replace Permanent Resident Card"
        assert len(schema["fields"]) == 2

    def test_load_form_schema_not_found(self, cache_manager):
        """Test loading non-existent form schema."""
        with pytest.raises(FileNotFoundError):
            cache_manager._load_form_schema("i-999")

    def test_load_annotated_pdf_json(self, cache_manager):
        """Test loading JSON annotations."""
        annotations = cache_manager._load_annotated_pdf("i-90")

        assert annotations is not None
        assert annotations["form_type"] == "i-90"
        assert "firstName" in annotations["field_annotations"]

    def test_load_annotated_pdf_not_found(self, cache_manager):
        """Test loading annotations when none exist."""
        # Remove annotations file
        annotations_path = cache_manager.form_kits_root / "i-90" / "i-90-annotations.json"
        annotations_path.unlink()

        annotations = cache_manager._load_annotated_pdf("i-90")
        assert annotations is None

    def test_hash_content(self, cache_manager):
        """Test content hashing for consistency tracking."""
        content1 = '{"field": "value"}'
        content2 = '{"field": "value"}'
        content3 = '{"field": "different"}'

        hash1 = cache_manager._hash_content(content1)
        hash2 = cache_manager._hash_content(content2)
        hash3 = cache_manager._hash_content(content3)

        # Same content = same hash
        assert hash1 == hash2

        # Different content = different hash
        assert hash1 != hash3

        # Hash is hex string
        assert len(hash1) == 64
        assert all(c in "0123456789abcdef" for c in hash1)

    @pytest.mark.asyncio
    async def test_create_gemini_cache_placeholder(self, cache_manager):
        """Test Gemini cache creation (placeholder implementation)."""
        content = {
            "schema": {"id": "test"},
            "form_type": "i-90",
            "version": "1.0"
        }

        cache_id = await cache_manager._create_gemini_cache(
            content=content,
            ttl_hours=24
        )

        # Placeholder returns deterministic ID
        assert cache_id.startswith("cache_")
        assert len(cache_id) == 22  # "cache_" + 16-char hash

    @pytest.mark.asyncio
    async def test_shutdown(self, cache_manager):
        """Test cache manager shutdown."""
        with patch.object(cache_manager, '_create_gemini_cache', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "cache_test123"

            await cache_manager.initialize_caches()

            assert cache_manager._refresh_task is not None
            refresh_task = cache_manager._refresh_task

            await cache_manager.shutdown()

            assert refresh_task.cancelled()

    def test_get_metrics(self, cache_manager):
        """Test metrics retrieval."""
        # Before initialization
        metrics = cache_manager.get_metrics()
        assert metrics["enabled"] is False
        assert metrics["cached_forms"] == 0
        assert metrics["total_cache_accesses"] == 0

    @pytest.mark.asyncio
    async def test_get_metrics_after_initialization(self, cache_manager):
        """Test metrics after cache initialization and usage."""
        with patch.object(cache_manager, '_create_gemini_cache', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "cache_test123"

            await cache_manager.initialize_caches()

            # Access cache multiple times
            cache_manager.get_cache_id("i-90")
            cache_manager.get_cache_id("i-90")
            cache_manager.get_cache_id("i-90")

            metrics = cache_manager.get_metrics()

            assert metrics["enabled"] is True
            assert metrics["cached_forms"] == 1
            assert metrics["total_cache_accesses"] == 3
            assert metrics["storage_cost_per_hour"] == 1.00
            assert metrics["estimated_token_savings"] == 15000  # 3 accesses * 5000 tokens
            assert "i-90" in metrics["caches"]

            i90_metrics = metrics["caches"]["i-90"]
            assert i90_metrics["cache_id"] == "cache_test123"
            assert i90_metrics["access_count"] == 3
            assert i90_metrics["version"] == "1.0"


class TestGlobalCacheManager:
    """Test global cache manager functions."""

    @pytest.mark.asyncio
    async def test_initialize_global_cache_manager(self, mock_form_kits_root):
        """Test global cache manager initialization."""
        with patch('backend.services.explicit_cache_manager.ExplicitCacheManager.initialize_caches', new_callable=AsyncMock):
            await initialize_global_cache_manager(mock_form_kits_root)

            manager = get_cache_manager()
            assert manager is not None
            assert manager.form_kits_root == mock_form_kits_root

    @pytest.mark.asyncio
    async def test_shutdown_global_cache_manager(self, mock_form_kits_root):
        """Test global cache manager shutdown."""
        with patch('backend.services.explicit_cache_manager.ExplicitCacheManager.initialize_caches', new_callable=AsyncMock):
            await initialize_global_cache_manager(mock_form_kits_root)

            manager = get_cache_manager()
            assert manager is not None

            await shutdown_cache_manager()

            manager_after = get_cache_manager()
            assert manager_after is None


class TestCacheRefresh:
    """Test cache refresh logic."""

    @pytest.mark.asyncio
    async def test_refresh_loop_refreshes_expiring_caches(self, cache_manager):
        """Test that refresh loop refreshes caches near expiry."""
        with patch.object(cache_manager, '_create_gemini_cache', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "cache_old123"

            await cache_manager.initialize_caches()

            # Manually set cache to expire soon
            i90_cache = cache_manager.cache_registry["i-90"]
            i90_cache.expires_at = datetime.now() + timedelta(hours=1)  # Within 2-hour threshold

            # Create new cache ID for refresh
            mock_create.return_value = "cache_new456"

            # Manually trigger refresh check
            with patch.object(cache_manager, '_create_form_cache', return_value=CacheInfo(
                cache_id="cache_new456",
                form_type="i-90",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=24),
                version="1.0",
                schema_hash="newhash"
            )) as mock_create_form_cache:
                # Simulate refresh check
                if i90_cache.should_refresh(cache_manager.REFRESH_THRESHOLD_HOURS):
                    new_cache_info = await cache_manager._create_form_cache("i-90")
                    cache_manager.cache_registry["i-90"] = new_cache_info

                assert cache_manager.cache_registry["i-90"].cache_id == "cache_new456"

    @pytest.mark.asyncio
    async def test_refresh_loop_skips_fresh_caches(self, cache_manager):
        """Test that refresh loop skips caches far from expiry."""
        with patch.object(cache_manager, '_create_gemini_cache', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "cache_old123"

            await cache_manager.initialize_caches()

            # Cache expires in 10 hours (outside threshold)
            i90_cache = cache_manager.cache_registry["i-90"]
            i90_cache.expires_at = datetime.now() + timedelta(hours=10)

            # Simulate refresh check
            should_refresh = i90_cache.should_refresh(cache_manager.REFRESH_THRESHOLD_HOURS)

            assert should_refresh is False


class TestCostModel:
    """Test cost calculation and scaling."""

    @pytest.mark.asyncio
    async def test_cost_scaling_with_concurrent_users(self, cache_manager):
        """Test cost amortization across concurrent users."""
        with patch.object(cache_manager, '_create_gemini_cache', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "cache_test123"

            await cache_manager.initialize_caches()

            # Simulate 100 concurrent users accessing cache
            for _ in range(100):
                cache_manager.get_cache_id("i-90")

            metrics = cache_manager.get_metrics()

            # Storage cost amortized across 100 users
            storage_cost = metrics["storage_cost_per_hour"]
            per_user_storage_cost = storage_cost / 100

            assert per_user_storage_cost == 0.01  # $0.01 per user per hour

            # Token savings
            assert metrics["total_cache_accesses"] == 100
            assert metrics["estimated_token_savings"] == 500_000  # 100 * 5000 tokens
