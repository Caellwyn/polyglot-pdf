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


def test_map_values_match_the_frontend_mirror():
    """The map's VALUES are now a cross-surface contract, not just an ASR hint.

    bd polyglot-pdf-thun made the frontend hint resolver accept BCP-47 keys in a
    kit's option `label_translations`, reading them from a hand-copied mirror of
    this map (`SPOKEN_LANGUAGE_BCP47` / `kitTranslationKeys` in
    frontend/src/shared/languages.ts). If a code here drifts from that mirror,
    the frontend and backend resolve DIFFERENT keys for the same session and the
    guidance block and the next-field hint can speak different languages on one
    turn -- the exact bug bd thun exists to prevent.

    The sibling test above pinned only the key SET, and languages.test.ts
    compares the frontend map against a literal in its own file, so BOTH
    operands there are frontend-local: a value edit HERE was green on both
    surfaces (2nd Opus outer review, bd 575i PR). This literal is the backend
    end of that contract -- it and the frontend one must be updated together.
    """
    frontend_mirror = {
        "english": "en-US", "spanish": "es-US", "chinese": "cmn-CN",
        "tagalog": "fil-PH", "arabic": "ar-XA", "french": "fr-FR",
        "korean": "ko-KR", "german": "de-DE", "portuguese": "pt-BR",
        "hindi": "hi-IN", "italian": "it-IT", "urdu": "ur-PK",
        "persian": "fa-IR", "dutch": "nl-NL", "ukrainian": "uk-UA",
        "russian": "ru-RU", "swedish": "sv-SE", "afrikaans": "af-ZA",
    }
    assert SPOKEN_LANGUAGE_BCP47 == frontend_mirror


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


# --- 4. speech_config.language_code (bd polyglot-pdf-m1lg) ---------------------

def _settings_with_speech_flag(enabled: bool, voice: str = "") -> Settings:
    """Settings for the language-bias assertions. `voice` defaults to EMPTY so
    these tests isolate the language_code half of speech_config; the voice half
    is pinned separately below."""
    s = Settings()
    s.SPEECH_LANGUAGE_CODE_ENABLED = enabled
    s.LIVE_VOICE_NAME = voice
    return s


def test_speech_config_carries_primary_bias_code():
    adapter = _adapter_with(["ru-RU"], transcripts=True, liveness=False)
    cfg = adapter._build_live_config(_settings_with_speech_flag(True))
    assert cfg["speech_config"] == {"language_code": "ru-RU"}


def test_speech_config_absent_without_codes_or_with_kill_switch_off():
    # Unmapped language (no bias codes): never set.
    adapter = _adapter_with(None, transcripts=True, liveness=False)
    cfg = adapter._build_live_config(_settings_with_speech_flag(True))
    assert "speech_config" not in cfg
    # Kill-switch off: never set even with codes.
    adapter = _adapter_with(["es-US"], transcripts=True, liveness=False)
    cfg = adapter._build_live_config(_settings_with_speech_flag(False))
    assert "speech_config" not in cfg


def test_voice_config_merges_with_language_code():
    """LIVE_VOICE_NAME rides speech_config alongside language_code -- the real
    call order (language block, then voice block) keeps BOTH keys."""
    adapter = _adapter_with(["ru-RU"], transcripts=True, liveness=False)
    cfg = adapter._build_live_config(_settings_with_speech_flag(True, "Iapetus"))
    assert cfg["speech_config"] == {
        "language_code": "ru-RU",
        "voice_config": {"prebuilt_voice_config": {"voice_name": "Iapetus"}},
    }


def test_speech_config_writers_preserve_each_other_in_both_orders():
    """Both speech_config contributors must survive regardless of write order.

    Asserts the property FUNCTIONALLY, by driving the shared writer in both
    orders. An earlier version of this test grepped the source for a
    single-quoted bare assignment; a double-quoted one walked straight past it,
    so the suite stayed green while the bug was live in the tree (Opus
    fresh-eyes round 2). Behaviour, not spelling."""
    from backend.adapters.live_ai_gemini import _merge_speech_config

    voice = {"prebuilt_voice_config": {"voice_name": "Iapetus"}}

    # language first, then voice
    a: dict = {}
    _merge_speech_config(a, "language_code", "ru-RU")
    _merge_speech_config(a, "voice_config", voice)

    # voice first, then language -- the order production does NOT currently use,
    # which is exactly why it needs pinning: a reorder must stay safe.
    b: dict = {}
    _merge_speech_config(b, "voice_config", voice)
    _merge_speech_config(b, "language_code", "ru-RU")

    expected = {"language_code": "ru-RU", "voice_config": voice}
    assert a["speech_config"] == expected
    assert b["speech_config"] == expected

    # A single writer alone must not fabricate the other key.
    c: dict = {}
    _merge_speech_config(c, "voice_config", voice)
    assert c["speech_config"] == {"voice_config": voice}

    # A non-dict squatter is replaced, not crashed on.
    d: dict = {"speech_config": "garbage"}
    _merge_speech_config(d, "language_code", "es-US")
    assert d["speech_config"] == {"language_code": "es-US"}


def test_both_speech_config_writers_route_through_the_shared_helper():
    """Structural guard: _build_live_config must not write speech_config
    directly. Routing both contributors through _merge_speech_config is what
    makes the drop-the-other-key bug impossible; a direct assignment
    reintroduces it. Matches any quoting style, unlike the round-1 version."""
    import inspect
    import re
    from backend.adapters import live_ai_gemini

    src = inspect.getsource(live_ai_gemini.LiveAIGemini._build_live_config)
    direct_writes = re.findall(r"""config\[\s*['"]speech_config['"]\s*\]\s*=""", src)
    assert direct_writes == [], (
        "_build_live_config assigns config['speech_config'] directly; use "
        "_merge_speech_config so the other contributor's key survives")
    assert src.count("_merge_speech_config(") == 2, (
        "expected exactly two speech_config contributors (language + voice) "
        "routed through the shared merge helper")


def test_voice_config_set_even_when_language_bias_is_off():
    """The voice is independent of the language kill-switch: turning
    SPEECH_LANGUAGE_CODE_ENABLED off must not also drop the voice."""
    adapter = _adapter_with(["es-US"], transcripts=True, liveness=False)
    cfg = adapter._build_live_config(_settings_with_speech_flag(False, "Iapetus"))
    assert cfg["speech_config"] == {
        "voice_config": {"prebuilt_voice_config": {"voice_name": "Iapetus"}}
    }
    # ...and with no bias codes at all (unmapped language).
    adapter = _adapter_with(None, transcripts=True, liveness=False)
    cfg = adapter._build_live_config(_settings_with_speech_flag(True, "Iapetus"))
    assert cfg["speech_config"] == {
        "voice_config": {"prebuilt_voice_config": {"voice_name": "Iapetus"}}
    }


def test_empty_voice_name_leaves_speech_config_untouched():
    """Empty LIVE_VOICE_NAME falls back to the API default voice -- it must not
    write an empty voice_config (which the endpoint would reject)."""
    adapter = _adapter_with(None, transcripts=True, liveness=False)
    cfg = adapter._build_live_config(_settings_with_speech_flag(True, ""))
    assert "speech_config" not in cfg
