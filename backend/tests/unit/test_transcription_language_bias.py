"""Spec for the ASR language bias (bd polyglot-pdf-y25o).

System instructions steer only the LLM's output language; the transcription
configs' `language_codes` (BCP-47) bias the ASR listener itself. Without the
bias, multilingual ASR can transcribe a mumbled session-language word as a
neighboring language and drag the native-audio model's auto-detect with it
(live es->pt slip: "distrito quintal").

Pins:
  1. The spoken-language-name -> BCP-47 lookup (known / unknown / unset).
  2. start_session derives the codes from service._spoken_language (seeded from
     the handshake BEFORE the Gemini connect) and hands them to the adapter.
  3. _build_live_config carries language_codes on the transcription blocks when
     the flag is on and codes are set; never turns transcription on by itself;
     and stays byte-compatible (empty blocks) when the flag is off or no codes.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

from backend.utils.language_codes import (
    SPOKEN_LANGUAGE_BCP47,
    bcp47_codes_for_spoken_language,
)
from backend.config import Settings
from backend.services.form_filling_service import FormFillingService


# --- 1. Name -> BCP-47 lookup -------------------------------------------------

def test_lookup_known_language_case_insensitive():
    assert bcp47_codes_for_spoken_language("Spanish") == ["es-US"]
    assert bcp47_codes_for_spoken_language("  spanish ") == ["es-US"]
    assert bcp47_codes_for_spoken_language("PORTUGUESE") == ["pt-BR"]


def test_lookup_unknown_or_unset_returns_none():
    assert bcp47_codes_for_spoken_language("Klingon") is None
    assert bcp47_codes_for_spoken_language(None) is None
    assert bcp47_codes_for_spoken_language("") is None


def test_map_covers_all_spoken_languages():
    """ENFORCEMENT test (bd polyglot-pdf-ow1e): supported == code-backed.

    Every supported spoken language MUST have a BCP-47 code (maintainer
    decision; Quechua, the one uncoded entry, was removed from the app). This
    set mirrors frontend SPOKEN_LANGUAGES (languages.ts) exactly -- no
    exceptions: adding an app language without a code, or a code without the
    app language, fails here."""
    expected = {
        "english", "spanish", "chinese", "tagalog", "arabic", "french",
        "korean", "german", "portuguese", "hindi", "italian", "urdu",
        "persian", "dutch", "ukrainian", "russian", "swedish", "afrikaans",
    }
    assert set(SPOKEN_LANGUAGE_BCP47.keys()) == expected


# --- 2. Service wiring: handshake language -> adapter setter -------------------

@pytest.mark.asyncio
async def test_start_session_hands_derived_codes_to_adapter():
    live_ai = MagicMock()
    service = FormFillingService(live_ai=live_ai, settings=Settings())
    # The WS route seeds this from the handshake BEFORE start_session
    # (websocket_routes._handle_fill_session) -- per-connect config needs it
    # before the Gemini connect, not at change_spoken_language time.
    service._spoken_language = "Spanish"

    ws = MagicMock()
    ws.accept = AsyncMock()
    await service.start_session(
        ws, "y25o-test", accept_connection=False,
        schema={"fields": [], "form_metadata": {"form_number": "I-90"}},
    )

    live_ai.set_transcription_language_codes.assert_called_once_with(["es-US"])


@pytest.mark.asyncio
async def test_start_session_unknown_language_hands_none():
    live_ai = MagicMock()
    service = FormFillingService(live_ai=live_ai, settings=Settings())
    service._spoken_language = "Klingon"

    ws = MagicMock()
    ws.accept = AsyncMock()
    await service.start_session(
        ws, "y25o-test-2", accept_connection=False,
        schema={"fields": [], "form_metadata": {"form_number": "I-90"}},
    )

    live_ai.set_transcription_language_codes.assert_called_once_with(None)


# --- 3. Adapter config shape ---------------------------------------------------

def _adapter_with(codes, *, transcripts: bool, liveness: bool):
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini(api_key="test_key")
    adapter._enable_transcripts = transcripts

    async def _noop():
        return None

    adapter._on_user_activity = _noop if liveness else None
    adapter.set_transcription_language_codes(codes)
    return adapter


def _settings_with_flag(enabled: bool) -> Settings:
    s = Settings()
    s.TRANSCRIPTION_LANGUAGE_HINT_ENABLED = enabled
    return s


def test_config_carries_codes_on_requested_transcription_blocks():
    adapter = _adapter_with(["es-US"], transcripts=True, liveness=False)
    cfg = adapter._build_live_config(_settings_with_flag(True))
    assert cfg["input_audio_transcription"] == {"language_codes": ["es-US"]}
    assert cfg["output_audio_transcription"] == {"language_codes": ["es-US"]}


def test_bias_never_turns_transcription_on_by_itself():
    # Liveness only: input transcription is requested, output is NOT -- the
    # bias must decorate the existing blocks, not create the output one.
    adapter = _adapter_with(["es-US"], transcripts=False, liveness=True)
    cfg = adapter._build_live_config(_settings_with_flag(True))
    assert cfg["input_audio_transcription"] == {"language_codes": ["es-US"]}
    assert "output_audio_transcription" not in cfg

    # Neither requested: the bias adds nothing at all.
    adapter = _adapter_with(["es-US"], transcripts=False, liveness=False)
    cfg = adapter._build_live_config(_settings_with_flag(True))
    assert "input_audio_transcription" not in cfg
    assert "output_audio_transcription" not in cfg


def test_kill_switch_off_restores_plain_blocks():
    adapter = _adapter_with(["es-US"], transcripts=True, liveness=False)
    cfg = adapter._build_live_config(_settings_with_flag(False))
    assert cfg["input_audio_transcription"] == {}
    assert cfg["output_audio_transcription"] == {}


def test_no_codes_leaves_plain_blocks():
    adapter = _adapter_with(None, transcripts=True, liveness=False)
    cfg = adapter._build_live_config(_settings_with_flag(True))
    assert cfg["input_audio_transcription"] == {}
    assert cfg["output_audio_transcription"] == {}
