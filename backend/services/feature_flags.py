"""
Feature flag service for half-cascade architecture rollout.

Provides:
- Feature flag evaluation (enabled/disabled per session)
- Percentage-based rollout
- User override support
- Hot-reloadable configuration
"""

from __future__ import annotations

import hashlib
from typing import Optional
import structlog

# Handle both package imports and direct imports for testing
try:
    from ..config import Settings, get_settings
except ImportError:
    from config import Settings, get_settings

log = structlog.get_logger(__name__)


class FeatureFlagService:
    """Service for evaluating feature flags with rollout support."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize feature flag service.

        Args:
            settings: Optional settings object. If None, uses get_settings()
        """
        self.settings = settings or get_settings()

    def is_half_cascade_enabled(self, session_id: str) -> bool:
        """Check if half-cascade architecture should be used for this session.

        Uses percentage-based rollout with consistent session hashing.
        Same session ID always gets same result (sticky sessions).

        Args:
            session_id: Unique session identifier

        Returns:
            True if half-cascade should be enabled, False for Live API
        """
        # Check global flag first
        if not self.settings.HALF_CASCADE_ENABLED:
            log.debug("half_cascade_disabled_globally", session_id=session_id)
            return False

        # Check rollout percentage
        rollout_pct = self.settings.HALF_CASCADE_ROLLOUT_PERCENTAGE

        # 0% = disabled for all, 100% = enabled for all
        if rollout_pct <= 0:
            log.debug("half_cascade_rollout_0pct", session_id=session_id)
            return False
        if rollout_pct >= 100:
            log.debug("half_cascade_rollout_100pct", session_id=session_id)
            return True

        # Hash session ID to get consistent 0-99 bucket
        # Same session always gets same result
        session_hash = hashlib.md5(session_id.encode()).hexdigest()
        bucket = int(session_hash[:8], 16) % 100

        enabled = bucket < rollout_pct
        log.debug(
            "half_cascade_rollout_check",
            session_id=session_id,
            bucket=bucket,
            rollout_pct=rollout_pct,
            enabled=enabled
        )

        return enabled

    def should_fallback_on_error(self) -> bool:
        """Check if fallback to Live API is enabled on errors.

        Returns:
            True if should fallback, False if should fail hard
        """
        return self.settings.HALF_CASCADE_FALLBACK_TO_LIVE_API

    def get_flash_lite_model(self) -> str:
        """Get Flash-Lite model identifier.

        Returns:
            Model name for ASR
        """
        return self.settings.FLASH_LITE_MODEL

    def get_flash_tts_model(self) -> str:
        """Get Flash-TTS model identifier.

        Returns:
            Model name for TTS
        """
        return self.settings.FLASH_TTS_MODEL

    def get_audio_buffer_timeout_ms(self) -> int:
        """Get audio buffer timeout in milliseconds.

        Returns:
            Timeout value for silence detection
        """
        return self.settings.HALF_CASCADE_AUDIO_BUFFER_TIMEOUT_MS

    def get_max_buffer_size_mb(self) -> int:
        """Get maximum audio buffer size in megabytes.

        Returns:
            Max buffer size (Flash-Lite API limit)
        """
        return self.settings.HALF_CASCADE_MAX_BUFFER_SIZE_MB

    def get_supported_languages(self) -> list[str]:
        """Get list of supported languages for half-cascade.

        Returns:
            List of language codes (e.g., ["en-US", "es-ES", ...])
        """
        return self.settings.HALF_CASCADE_SUPPORTED_LANGUAGES

    def is_language_supported(self, language_code: str) -> bool:
        """Check if a language is supported in half-cascade mode.

        Args:
            language_code: Language code to check (e.g., "en-US")

        Returns:
            True if supported, False otherwise
        """
        return language_code in self.settings.HALF_CASCADE_SUPPORTED_LANGUAGES


# Singleton instance for dependency injection
_feature_flag_service: Optional[FeatureFlagService] = None


def get_feature_flag_service(settings: Optional[Settings] = None) -> FeatureFlagService:
    """Get or create feature flag service singleton.

    Args:
        settings: Optional settings object for initialization

    Returns:
        FeatureFlagService instance
    """
    global _feature_flag_service
    if _feature_flag_service is None:
        _feature_flag_service = FeatureFlagService(settings)
    return _feature_flag_service


def reset_feature_flag_service():
    """Reset singleton (for testing)."""
    global _feature_flag_service
    _feature_flag_service = None
