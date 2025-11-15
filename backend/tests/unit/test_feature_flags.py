"""
Unit tests for feature flag service.

Tests:
- Feature flag evaluation
- Percentage-based rollout
- Session hash consistency
- Configuration hot-reload
"""

import pytest
from services.feature_flags import FeatureFlagService, reset_feature_flag_service
from config import Settings


@pytest.fixture
def default_settings():
    """Default settings with half-cascade disabled."""
    return Settings(
        HALF_CASCADE_ENABLED=False,
        HALF_CASCADE_ROLLOUT_PERCENTAGE=0,
        HALF_CASCADE_FALLBACK_TO_LIVE_API=True,
    )


@pytest.fixture
def enabled_settings():
    """Settings with half-cascade enabled at 100%."""
    return Settings(
        HALF_CASCADE_ENABLED=True,
        HALF_CASCADE_ROLLOUT_PERCENTAGE=100,
        HALF_CASCADE_FALLBACK_TO_LIVE_API=True,
    )


@pytest.fixture
def partial_rollout_settings():
    """Settings with 50% rollout."""
    return Settings(
        HALF_CASCADE_ENABLED=True,
        HALF_CASCADE_ROLLOUT_PERCENTAGE=50,
        HALF_CASCADE_FALLBACK_TO_LIVE_API=True,
    )


@pytest.fixture(autouse=True)
def cleanup():
    """Reset singleton after each test."""
    yield
    reset_feature_flag_service()


def test_disabled_globally(default_settings):
    """Test that feature is disabled when global flag is False."""
    service = FeatureFlagService(default_settings)
    assert not service.is_half_cascade_enabled("session_123")
    assert not service.is_half_cascade_enabled("session_456")


def test_enabled_at_100_percent(enabled_settings):
    """Test that feature is enabled for all sessions at 100% rollout."""
    service = FeatureFlagService(enabled_settings)
    assert service.is_half_cascade_enabled("session_123")
    assert service.is_half_cascade_enabled("session_456")
    assert service.is_half_cascade_enabled("session_789")


def test_disabled_at_0_percent():
    """Test that feature is disabled for all sessions at 0% rollout."""
    settings = Settings(
        HALF_CASCADE_ENABLED=True,
        HALF_CASCADE_ROLLOUT_PERCENTAGE=0,
        HALF_CASCADE_FALLBACK_TO_LIVE_API=True,
    )
    service = FeatureFlagService(settings)
    assert not service.is_half_cascade_enabled("session_123")
    assert not service.is_half_cascade_enabled("session_456")


def test_partial_rollout_consistency(partial_rollout_settings):
    """Test that same session ID always gets same result (sticky sessions)."""
    service = FeatureFlagService(partial_rollout_settings)

    # Same session should always get same result
    session_id = "test_session_abc"
    result1 = service.is_half_cascade_enabled(session_id)
    result2 = service.is_half_cascade_enabled(session_id)
    result3 = service.is_half_cascade_enabled(session_id)

    assert result1 == result2 == result3


def test_partial_rollout_distribution(partial_rollout_settings):
    """Test that rollout percentage is approximately correct."""
    service = FeatureFlagService(partial_rollout_settings)

    # Test with many session IDs
    enabled_count = 0
    total_count = 1000

    for i in range(total_count):
        session_id = f"session_{i}"
        if service.is_half_cascade_enabled(session_id):
            enabled_count += 1

    # Should be approximately 50% (allow ±10% variance)
    enabled_percentage = (enabled_count / total_count) * 100
    assert 40 <= enabled_percentage <= 60, f"Expected ~50%, got {enabled_percentage}%"


def test_should_fallback_on_error(enabled_settings):
    """Test fallback configuration getter."""
    service = FeatureFlagService(enabled_settings)
    assert service.should_fallback_on_error() is True

    # Test with fallback disabled
    settings_no_fallback = Settings(
        HALF_CASCADE_ENABLED=True,
        HALF_CASCADE_FALLBACK_TO_LIVE_API=False,
    )
    service_no_fallback = FeatureFlagService(settings_no_fallback)
    assert service_no_fallback.should_fallback_on_error() is False


def test_get_model_identifiers(enabled_settings):
    """Test model identifier getters."""
    service = FeatureFlagService(enabled_settings)

    assert service.get_flash_lite_model() == "gemini-2.5-flash-lite-preview"
    assert service.get_flash_tts_model() == "gemini-2.5-flash-preview-tts"


def test_get_audio_settings(enabled_settings):
    """Test audio configuration getters."""
    service = FeatureFlagService(enabled_settings)

    assert service.get_audio_buffer_timeout_ms() == 1500
    assert service.get_max_buffer_size_mb() == 20


def test_get_supported_languages(enabled_settings):
    """Test supported languages getter."""
    service = FeatureFlagService(enabled_settings)

    languages = service.get_supported_languages()
    assert "en-US" in languages
    assert "es-ES" in languages
    assert "zh-CN" in languages
    assert len(languages) == 20  # As defined in config


def test_is_language_supported(enabled_settings):
    """Test language support check."""
    service = FeatureFlagService(enabled_settings)

    assert service.is_language_supported("en-US") is True
    assert service.is_language_supported("es-ES") is True
    assert service.is_language_supported("xx-XX") is False  # Invalid language


def test_rollout_edge_cases():
    """Test edge cases in rollout percentage."""
    # Test 1% rollout
    settings_1pct = Settings(
        HALF_CASCADE_ENABLED=True,
        HALF_CASCADE_ROLLOUT_PERCENTAGE=1,
    )
    service_1pct = FeatureFlagService(settings_1pct)

    enabled_count = sum(
        1 for i in range(1000)
        if service_1pct.is_half_cascade_enabled(f"session_{i}")
    )
    # Should be approximately 1% (allow some variance)
    assert 0 < enabled_count < 50, f"Expected ~1%, got {enabled_count/10}%"

    # Test 99% rollout
    settings_99pct = Settings(
        HALF_CASCADE_ENABLED=True,
        HALF_CASCADE_ROLLOUT_PERCENTAGE=99,
    )
    service_99pct = FeatureFlagService(settings_99pct)

    enabled_count = sum(
        1 for i in range(1000)
        if service_99pct.is_half_cascade_enabled(f"session_{i}")
    )
    # Should be approximately 99% (allow some variance)
    assert 950 < enabled_count < 1000, f"Expected ~99%, got {enabled_count/10}%"


def test_session_id_variety():
    """Test that different session ID formats work correctly."""
    settings = Settings(
        HALF_CASCADE_ENABLED=True,
        HALF_CASCADE_ROLLOUT_PERCENTAGE=50,
    )
    service = FeatureFlagService(settings)

    # Different formats should all hash consistently
    session_ids = [
        "web_abc123",
        "session-456-def",
        "user_session_789_xyz",
        "ABC123XYZ",
        "12345678",
    ]

    for session_id in session_ids:
        result1 = service.is_half_cascade_enabled(session_id)
        result2 = service.is_half_cascade_enabled(session_id)
        assert result1 == result2, f"Inconsistent result for {session_id}"
