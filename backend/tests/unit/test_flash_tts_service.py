"""
Unit tests for Flash TTS Service (Phase 1D & 2C)

Tests cover:
- Multi-language support (20+ languages)
- Language configuration management
- Audio streaming
- Language switching
- Graceful degradation
- Segment synthesis with language tags
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from backend.services.flash_tts_service import (
    FlashTTSService,
    VoiceConfig,
    LANGUAGE_CONFIGS,
    DEFAULT_LANGUAGE,
    text_to_speech
)


@pytest.fixture
def mock_genai_client():
    """Mock genai.Client for testing."""
    with patch('backend.services.flash_tts_service.genai.Client') as mock_client:
        yield mock_client


@pytest.fixture
def tts_service(mock_genai_client):
    """Create a TTS service instance for testing."""
    service = FlashTTSService(use_vertex=True)
    return service


class TestLanguageConfiguration:
    """Test language configuration management."""

    def test_all_required_languages_supported(self):
        """Test that all 20+ required languages are configured."""
        required_languages = [
            "en-US", "es-ES", "zh-CN", "zh-TW", "ko-KR",
            "ar-SA", "fr-FR", "pt-BR", "ru-RU", "ja-JP",
            "hi-IN", "de-DE", "it-IT", "vi-VN", "tl-PH",
            "bn-BD", "ur-PK", "fa-IR", "tr-TR", "pl-PL"
        ]

        for lang in required_languages:
            assert lang in LANGUAGE_CONFIGS, f"Language {lang} not configured"

    def test_language_config_structure(self):
        """Test that all language configs have proper structure."""
        for lang, config in LANGUAGE_CONFIGS.items():
            assert isinstance(config, VoiceConfig)
            assert 0.5 <= config.rate <= 2.0, f"{lang}: rate out of range"
            assert -20.0 <= config.pitch <= 20.0, f"{lang}: pitch out of range"
            assert isinstance(config.voice, str)
            assert isinstance(config.rtl, bool)

    def test_rtl_languages_flagged(self):
        """Test that RTL languages are properly flagged."""
        rtl_languages = ["ar-SA", "fa-IR"]

        for lang in rtl_languages:
            assert LANGUAGE_CONFIGS[lang].rtl is True, f"{lang} should be RTL"

    def test_chinese_variants_slower_rate(self):
        """Test that Chinese variants have slightly slower rate."""
        chinese_langs = ["zh-CN", "zh-TW"]

        for lang in chinese_langs:
            assert LANGUAGE_CONFIGS[lang].rate == 0.95

    def test_default_language_exists(self):
        """Test that default fallback language is configured."""
        assert DEFAULT_LANGUAGE in LANGUAGE_CONFIGS
        assert DEFAULT_LANGUAGE == "en-US"


class TestLanguageResolution:
    """Test language resolution and fallback logic."""

    def test_exact_language_match(self, tts_service):
        """Test resolution of exact language match."""
        lang, config = tts_service.get_language_config("es-ES")

        assert lang == "es-ES"
        assert config == LANGUAGE_CONFIGS["es-ES"]

    def test_base_language_fallback(self, tts_service):
        """Test fallback to base language variant."""
        # Request "es" should resolve to first Spanish variant
        lang, config = tts_service.get_language_config("es")

        assert lang.startswith("es-")
        assert lang in LANGUAGE_CONFIGS

    def test_unsupported_language_fallback(self, tts_service):
        """Test fallback to English for unsupported languages."""
        lang, config = tts_service.get_language_config("xx-XX")

        assert lang == DEFAULT_LANGUAGE
        assert config == LANGUAGE_CONFIGS[DEFAULT_LANGUAGE]

    def test_variant_fallback(self, tts_service):
        """Test fallback from unsupported variant to base language."""
        # es-AR (Argentina) should fall back to es-ES or es-MX
        lang, config = tts_service.get_language_config("es-AR")

        assert lang.startswith("es-")
        assert lang in LANGUAGE_CONFIGS


class TestTTSInitialization:
    """Test TTS service initialization."""

    def test_vertex_ai_initialization(self, mock_genai_client):
        """Test initialization with Vertex AI."""
        service = FlashTTSService(use_vertex=True)

        assert service.use_vertex is True
        assert service.model == "gemini-2.5-flash-preview-tts"
        mock_genai_client.assert_called_once_with(vertexai=True)

    def test_api_key_initialization(self, mock_genai_client):
        """Test initialization with API key."""
        service = FlashTTSService(api_key="test_key", use_vertex=False)

        assert service.use_vertex is False
        mock_genai_client.assert_called_once_with(api_key="test_key")

    def test_custom_model(self, mock_genai_client):
        """Test initialization with custom model."""
        service = FlashTTSService(model="custom-model")

        assert service.model == "custom-model"


class TestPreloading:
    """Test language pre-loading functionality."""

    @pytest.mark.asyncio
    async def test_preload_language(self, tts_service):
        """Test pre-loading a language."""
        await tts_service.preload_language("es-ES")

        assert tts_service._preloaded_language == "es-ES"

    @pytest.mark.asyncio
    async def test_preload_with_fallback(self, tts_service):
        """Test pre-loading with language fallback."""
        await tts_service.preload_language("es-AR")

        # Should resolve to a Spanish variant
        assert tts_service._preloaded_language.startswith("es-")

    @pytest.mark.asyncio
    async def test_preload_unsupported_language(self, tts_service):
        """Test pre-loading unsupported language falls back to English."""
        await tts_service.preload_language("xx-XX")

        assert tts_service._preloaded_language == DEFAULT_LANGUAGE


class TestSpeechSynthesis:
    """Test speech synthesis functionality."""

    @pytest.mark.asyncio
    async def test_empty_text_handling(self, tts_service):
        """Test that empty text is handled gracefully."""
        chunks = []
        async for chunk in tts_service.synthesize_speech("", "en-US"):
            chunks.append(chunk)

        assert len(chunks) == 0

    @pytest.mark.asyncio
    async def test_whitespace_only_text(self, tts_service):
        """Test that whitespace-only text is handled gracefully."""
        chunks = []
        async for chunk in tts_service.synthesize_speech("   ", "en-US"):
            chunks.append(chunk)

        assert len(chunks) == 0

    @pytest.mark.asyncio
    async def test_language_switching_tracked(self, tts_service):
        """Test that language switching is properly tracked."""
        # Mock the genai client's live.connect
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock receive to return some audio chunks
        async def mock_receive():
            yield Mock(data=b"audio_chunk_1")
            yield Mock(data=b"audio_chunk_2")

        mock_session.receive = mock_receive
        mock_session.send_client_content = AsyncMock()

        tts_service.client.aio.live.connect = Mock(return_value=mock_session)

        # First synthesis in English
        chunks = []
        async for chunk in tts_service.synthesize_speech("Hello", "en-US"):
            chunks.append(chunk)

        assert tts_service._current_language == "en-US"
        assert len(chunks) == 2

        # Second synthesis in Spanish (should trigger language switch)
        chunks = []
        async for chunk in tts_service.synthesize_speech("Hola", "es-ES"):
            chunks.append(chunk)

        assert tts_service._current_language == "es-ES"


class TestSegmentSynthesis:
    """Test multi-segment synthesis with language switching (Phase 2C)."""

    @pytest.mark.asyncio
    async def test_synthesize_empty_segments(self, tts_service):
        """Test handling of empty segment list."""
        chunks = []
        async for chunk in tts_service.synthesize_segments([]):
            chunks.append(chunk)

        assert len(chunks) == 0

    @pytest.mark.asyncio
    async def test_synthesize_single_segment(self, tts_service):
        """Test synthesis of single segment."""
        # Mock the session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        async def mock_receive():
            yield Mock(data=b"audio_chunk")

        mock_session.receive = mock_receive
        mock_session.send_client_content = AsyncMock()

        tts_service.client.aio.live.connect = Mock(return_value=mock_session)

        segments = [
            {"text": "Hello", "language": "en-US"}
        ]

        chunks = []
        async for chunk in tts_service.synthesize_segments(segments):
            chunks.append(chunk)

        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_synthesize_multilingual_segments(self, tts_service):
        """Test synthesis with language switching."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        async def mock_receive():
            yield Mock(data=b"audio_chunk")

        mock_session.receive = mock_receive
        mock_session.send_client_content = AsyncMock()

        tts_service.client.aio.live.connect = Mock(return_value=mock_session)

        segments = [
            {"text": "Hello", "language": "en-US"},
            {"text": "Hola", "language": "es-ES"},
            {"text": "你好", "language": "zh-CN"}
        ]

        chunks = []
        async for chunk in tts_service.synthesize_segments(segments):
            chunks.append(chunk)

        # Should have chunks from all segments
        assert len(chunks) >= 3

    @pytest.mark.asyncio
    async def test_skip_empty_segment_text(self, tts_service):
        """Test that segments with empty text are skipped."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        async def mock_receive():
            yield Mock(data=b"audio_chunk")

        mock_session.receive = mock_receive
        mock_session.send_client_content = AsyncMock()

        tts_service.client.aio.live.connect = Mock(return_value=mock_session)

        segments = [
            {"text": "Hello", "language": "en-US"},
            {"text": "", "language": "es-ES"},  # Empty - should be skipped
            {"text": "   ", "language": "fr-FR"},  # Whitespace - should be skipped
            {"text": "World", "language": "en-US"}
        ]

        chunks = []
        async for chunk in tts_service.synthesize_segments(segments):
            chunks.append(chunk)

        # Should only have chunks from non-empty segments
        assert len(chunks) >= 2


class TestConvenienceFunction:
    """Test the convenience text_to_speech function."""

    @pytest.mark.asyncio
    async def test_text_to_speech_returns_bytes(self, mock_genai_client):
        """Test that text_to_speech returns complete audio as bytes."""
        # Mock the session
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        async def mock_receive():
            yield Mock(data=b"chunk1")
            yield Mock(data=b"chunk2")

        mock_session.receive = mock_receive
        mock_session.send_client_content = AsyncMock()

        # Mock the client
        mock_client_instance = Mock()
        mock_client_instance.aio.live.connect = Mock(return_value=mock_session)
        mock_genai_client.return_value = mock_client_instance

        result = await text_to_speech("Hello", "en-US")

        assert isinstance(result, bytes)
        assert result == b"chunk1chunk2"


class TestErrorHandling:
    """Test error handling in TTS service."""

    @pytest.mark.asyncio
    async def test_synthesis_error_propagated(self, tts_service):
        """Test that synthesis errors are properly propagated."""
        # Mock session that raises an error
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.send_client_content = AsyncMock(side_effect=Exception("API Error"))

        tts_service.client.aio.live.connect = Mock(return_value=mock_session)

        with pytest.raises(Exception, match="API Error"):
            async for chunk in tts_service.synthesize_speech("Hello", "en-US"):
                pass

    @pytest.mark.asyncio
    async def test_close_service(self, tts_service):
        """Test closing the service."""
        await tts_service.close()
        # Should complete without errors
