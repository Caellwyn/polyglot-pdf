"""
Digit read-back through the deterministic clip (bd polyglot-pdf-r3ham.26).

In the 2026-11-20 gemini-3.8-live benchmark a mobile number asked right after
a similar daytime number was stored as a blend of the two: Cloud STT heard the
model's VOICE read back the earlier number while its transcript said the new
one. Identifier numbers therefore move to the name_spellback clip, built from
the STORED value, so what the user hears is what is saved.

What these tests pin:

1. The model is told to use the clip for numbers -- the tool declaration AND
   the SI addendum route identifier numbers to name_spellback (the SI side is
   pinned in test_spellback_tool.py's addendum tests).
2. For EVERY locale in spellback_frames.json (enumerated from the file, never
   hand-listed), a clip built from a digit value voices each digit as its own
   token -- never a multi-digit run the voice could read as one number.
3. The clip's locale and voice follow the session language for every
   code-backed language, and a digit clip NEVER falls back to English: an
   unmapped language, a locale with no voice, or an unavailable voice listing
   raises SpellbackLanguageUnavailable -> the route answers 406 -> the client
   acks 'tts_http_406' -> the tool tells the model to read the digits itself
   in the session language.

ASCII only (scar #6).
"""
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.config import Settings
from backend.services import spellback_tts
from backend.services.callback_handler import (
    SPELLBACK_NO_SESSION_VOICE_REASON,
    CallbackHandler,
)
from backend.services.request_coordinator import RequestCoordinator
from backend.services.spellback_tts import (
    SPELLBACK_NO_SESSION_VOICE_STATUS,
    SpellbackLanguageUnavailable,
    build_spellback_text,
    contains_digit,
    resolve_spellback_voice,
    synthesize_spellback,
)
from backend.utils.language_codes import SPOKEN_LANGUAGE_BCP47

_FRAMES_FILE = (Path(__file__).resolve().parents[2]
                / "services" / "spellback_frames.json")
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _frames() -> dict:
    data = json.loads(_FRAMES_FILE.read_text(encoding="utf-8"))
    data.pop("_comment", None)
    return data


def _frame_locales():
    """Every locale the frames file carries -- the set criterion 1 names."""
    return sorted(_frames())


def _code_backed_languages():
    """Every code-backed spoken language -- the set criterion 2 names."""
    return sorted(SPOKEN_LANGUAGE_BCP47.items())


def _voices_for(*locales) -> set:
    """A fake list_voices result carrying one persona voice per locale."""
    return {"%s-Chirp3-HD-Algieba" % loc for loc in locales}


def _settings(persona="Algieba", explicit=""):
    s = Settings()
    s.LIVE_VOICE_NAME = persona
    s.SPELLBACK_TTS_VOICE = explicit
    return s


def _slot(locale: str, text: str) -> str:
    """The {letters} span of a built clip, cut out using the frame itself."""
    frame = _frames()[locale]["frame"]
    prefix, suffix = frame.split("{letters}")
    assert text.startswith(prefix) and text.endswith(suffix), (
        "clip for %s does not wear its own frame" % locale)
    return text[len(prefix):len(text) - len(suffix)]


# ---------------------------------------------------------------------------
# Criterion 1: the model is told to use the clip for numbers.
# ---------------------------------------------------------------------------

class TestModelIsToldToUseTheClipForNumbers:
    def test_declaration_routes_identifier_numbers_to_the_tool(self):
        desc = Settings().SPELLBACK_TOOL_DECLARATION["description"]
        assert "IDENTIFIER NUMBER" in desc
        for kind in ("phone", "ZIP", "A-number", "Social Security"):
            assert kind in desc, "declaration no longer names %r" % kind
        assert "identifier-number field" in desc
        # The pre-r3ham.26 exemption ("keep reading numbers back digit by
        # digit yourself") must be gone, not merely outvoted.
        assert "unaffected" not in desc
        assert "yourself.)" not in desc
        # The read_back_yourself tool variant is only obeyed if the
        # declaration allows the tool to hand the read-back back.
        assert "If the tool tells you to read the value back yourself" in desc

    def test_workflow_step_3_yields_numbers_to_a_later_instruction(self):
        """WORKFLOW step 3 is the base SI's numbered procedure and told the
        model to read numbers digit by digit UNCONDITIONALLY. With the clip
        taking numbers, that would contradict the addendum -- the same
        two-unqualified-rules shape bd polyglot-pdf-5s3pp fixed for names."""
        si = Settings().DTI_SYSTEM_INSTRUCTION
        idx = si.find("read identifier numbers digit by digit")
        assert idx != -1, "the flag-off number read-back rule is gone"
        preceding = si[max(0, idx - 160):idx]
        assert ("Unless a later instruction gives you a different way to "
                "verify a name or an identifier number") in preceding


# ---------------------------------------------------------------------------
# Criterion 1: every frames locale voices each digit as its own token.
# ---------------------------------------------------------------------------

class TestEveryLocaleVoicesEachDigitSeparately:
    @pytest.mark.parametrize("locale", _frame_locales())
    def test_each_digit_is_its_own_token(self, locale):
        value = "5035550297"
        tokens = _slot(locale, build_spellback_text(value, locale)).split(", ")
        # One token per digit, in order: a multi-digit token ("503") is what
        # a voice reads as ONE number ("five hundred three").
        assert tokens == list(value), (
            "%s clip does not voice each digit separately: %r" % (locale, tokens))

    @pytest.mark.parametrize("locale", _frame_locales())
    def test_grouped_phone_keeps_digits_separate_and_voices_the_separator(self, locale):
        punct = _frames()[locale]["punctuation"]
        tokens = _slot(locale, build_spellback_text("503-555-0297", locale)).split(", ")
        digits = [t for t in tokens if t.isdigit()]
        assert digits == list("5035550297")
        assert all(len(t) == 1 for t in digits)
        # The separator is the LOCALE's word for it, never dropped (a dropped
        # character would verify a different string than the stored one).
        assert tokens.count(punct["-"]) == 2

    def test_the_frames_set_is_enumerated_from_the_file(self):
        """Guard against the parametrization silently shrinking: the set is
        the file's own keys, and it covers every code-backed locale."""
        assert set(SPOKEN_LANGUAGE_BCP47.values()) <= set(_frame_locales())

    def test_contains_digit(self):
        assert contains_digit("5035550297")
        assert contains_digit("A123456789")
        assert contains_digit("97201")
        assert not contains_digit("JOSE")
        assert not contains_digit("O'Neil-Smith")


# ---------------------------------------------------------------------------
# Criterion 2: session language, never an English digit clip.
# ---------------------------------------------------------------------------

class TestDigitClipLanguage:
    @pytest.mark.parametrize("language,code", _code_backed_languages())
    def test_digit_clip_follows_the_session_language(self, language, code):
        """Every code-backed language whose locale has a voice gets a digit
        clip in THAT locale with THAT locale's voice."""
        voices = _voices_for(*SPOKEN_LANGUAGE_BCP47.values())
        with patch.object(spellback_tts, "_known_voices", return_value=voices):
            voice, locale = resolve_spellback_voice(
                _settings(), language, for_digits=True)
        assert locale == code
        assert voice == "%s-Chirp3-HD-Algieba" % code

    @pytest.mark.parametrize("language,code", [
        (lang, code) for lang, code in _code_backed_languages()
        if code != "en-US"])
    def test_voiceless_locale_never_falls_back_to_english(self, language, code):
        """A code-backed language whose locale lists NO voice (ur-PK and
        fa-IR today). The locale-default rung is not safe there: live
        2026-11-21 a voiceless ur-PK request came back in an ENGLISH voice.
        Parametrized over EVERY non-English language, so the rule cannot hold
        for the two known cases only."""
        everything_but = _voices_for(
            *[c for c in SPOKEN_LANGUAGE_BCP47.values() if c != code])
        with patch.object(spellback_tts, "_known_voices",
                          return_value=everything_but):
            with pytest.raises(SpellbackLanguageUnavailable):
                resolve_spellback_voice(_settings(), language, for_digits=True)

    @pytest.mark.parametrize("language", ["Klingon", "", None, "  "])
    def test_unmapped_language_never_falls_back_to_english(self, language):
        voices = _voices_for(*SPOKEN_LANGUAGE_BCP47.values())
        with patch.object(spellback_tts, "_known_voices", return_value=voices):
            with pytest.raises(SpellbackLanguageUnavailable):
                resolve_spellback_voice(_settings(), language, for_digits=True)

    def test_unavailable_voice_listing_fails_closed_for_digits(self):
        """No listing = cannot prove the locale has a voice = no digit clip.
        (Letters fail OPEN on the same condition; that is unchanged.)"""
        with patch.object(spellback_tts, "_known_voices", return_value=set()):
            with pytest.raises(SpellbackLanguageUnavailable):
                resolve_spellback_voice(_settings(), "Spanish", for_digits=True)
            assert resolve_spellback_voice(_settings(), "Spanish") == (
                "es-US-Chirp3-HD-Algieba", "es-US")

    def test_explicit_voice_override_cannot_make_a_digit_clip_english(self):
        voices = _voices_for(*SPOKEN_LANGUAGE_BCP47.values())
        s = _settings(explicit="en-US-Chirp3-HD-Algieba")
        with patch.object(spellback_tts, "_known_voices", return_value=voices):
            assert resolve_spellback_voice(s, "Spanish", for_digits=True) == (
                "es-US-Chirp3-HD-Algieba", "es-US")
            # Same-locale override is still honored for digits...
            assert resolve_spellback_voice(s, "English", for_digits=True) == (
                "en-US-Chirp3-HD-Algieba", "en-US")
            # ...and letters keep the override outright (unchanged).
            assert resolve_spellback_voice(s, "Spanish") == (
                "en-US-Chirp3-HD-Algieba", "en-US")

    def test_letters_keep_their_en_us_fallback_for_an_unmapped_language(self):
        """Recorded decision (bd r3ham.26): a NAME in an unmapped language
        still gets the en-US clip. Names are stored in Latin characters, and
        the alternative -- the model speaking the spelling -- is the measured
        bd 0rpu defect. Only digits lose the English fallback."""
        voices = _voices_for(*SPOKEN_LANGUAGE_BCP47.values())
        with patch.object(spellback_tts, "_known_voices", return_value=voices):
            assert resolve_spellback_voice(_settings(), "Klingon") == (
                "en-US-Chirp3-HD-Algieba", "en-US")

    @pytest.mark.asyncio
    async def test_synthesis_gates_on_the_value_never_synthesizing_english_digits(self):
        """Through the real entry point: a digit value in an unmapped language
        never reaches Cloud TTS; a letter value in the same session does, in
        en-US."""
        calls = []

        def fake_synth(text, voice_name, locale, gain_db=None):
            calls.append(locale)
            return b"MP3"

        voices = _voices_for(*SPOKEN_LANGUAGE_BCP47.values())
        with patch.object(spellback_tts, "_known_voices", return_value=voices), \
             patch.object(spellback_tts, "_synthesize_sync", fake_synth), \
             patch.object(spellback_tts, "_log_tts_usage_event"):
            with pytest.raises(SpellbackLanguageUnavailable):
                await synthesize_spellback("5035550297", _settings(), "Klingon")
            assert calls == []
            await synthesize_spellback("JOSE", _settings(), "Klingon")
            assert calls == ["en-US"]
            await synthesize_spellback("5035550297", _settings(), "Spanish")
            assert calls == ["en-US", "es-US"]

    def test_a_failed_voice_listing_is_retried_not_cached(self):
        """Caching a failed listing would pin every digit read-back on the
        instance to the model-speaks fallback for its whole lifetime."""
        class _Voice:
            def __init__(self, name):
                self.name = name

        class _Resp:
            voices = [_Voice("es-US-Chirp3-HD-Algieba")]

        client = type("C", (), {})()
        attempts = {"n": 0}

        def list_voices():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("blip")
            return _Resp()

        client.list_voices = list_voices
        with patch.object(spellback_tts, "_available_voices", None), \
             patch.object(spellback_tts, "_get_client", return_value=client):
            assert spellback_tts._known_voices() == set()
            assert spellback_tts._known_voices() == {"es-US-Chirp3-HD-Algieba"}
        assert attempts["n"] == 2


# ---------------------------------------------------------------------------
# The fallback contract across surfaces: route 406 -> client reason -> tool.
# ---------------------------------------------------------------------------

class TestNoSessionVoiceContract:
    def test_route_maps_unavailable_language_to_406(self, monkeypatch):
        from fastapi.testclient import TestClient

        import backend.routes.tts_routes as tts_routes
        from backend.main import app
        from backend.services.auth import require_paid_client_work

        settings = Settings()
        settings.SPELLBACK_TOOL_ENABLED = True
        monkeypatch.setattr(tts_routes, "get_settings", lambda: settings)

        async def raising_synth(value, settings, language_name=None, session_ctx=None):
            raise SpellbackLanguageUnavailable("no voice")

        monkeypatch.setattr(tts_routes, "synthesize_spellback", raising_synth)
        app.dependency_overrides[require_paid_client_work] = lambda: {"uid": "t"}
        try:
            resp = TestClient(app).post(
                "/api/tts/spellback",
                json={"value": "5035550297", "language": "Persian"})
        finally:
            app.dependency_overrides.pop(require_paid_client_work, None)
        assert resp.status_code == SPELLBACK_NO_SESSION_VOICE_STATUS == 406

    def test_client_forwards_the_status_as_the_reason_the_tool_matches(self):
        """The tool matches 'tts_http_406'. That token exists only because
        spellbackPlayer.ts reports a non-OK fetch as 'tts_http_' + status --
        pin the client half so a reshaped reason breaks here, not live."""
        ts = (_REPO_ROOT / "frontend/src/shared/spellbackPlayer.ts").read_text(
            encoding="utf-8")
        assert re.search(r"reason:\s*'tts_http_'\s*\+\s*resp\.status", ts)
        assert SPELLBACK_NO_SESSION_VOICE_REASON == "tts_http_406"

    @pytest.mark.asyncio
    async def test_tool_tells_the_model_to_read_digits_in_the_session_language(self):
        coordinator = AsyncMock(spec=RequestCoordinator)
        coordinator.request_spellback = AsyncMock(return_value={
            "status": "error", "reason": SPELLBACK_NO_SESSION_VOICE_REASON})
        handler = CallbackHandler(
            websocket=AsyncMock(), session_id="s", request_coordinator=coordinator,
            send_transcript=False, form_id="W-7", form_session_id="fss_t")
        handler._get_spellback_enabled = lambda: True

        response = await handler.on_tool_call(tool_name="name_spellback", arguments={})

        assert response["success"] is False
        assert response["status"] == "read_back_yourself"
        msg = response["message"]
        # Allowlist of the sanctioned remedy (never a banned-word blacklist).
        assert "YOU read it back now" in msg
        assert "STORED value" in msg
        assert "say every digit separately" in msg
        assert "SESSION LANGUAGE's own word for that digit" in msg
        assert "never in English" in msg
        assert "never grouped into larger numbers" in msg
        assert "Do not call name_spellback again for this value" in msg

    @pytest.mark.asyncio
    async def test_other_errors_keep_the_reask_variant(self):
        """Only the 406 reason hands the read-back to the model; any other
        HTTP failure keeps the never-self-spell error variant."""
        coordinator = AsyncMock(spec=RequestCoordinator)
        coordinator.request_spellback = AsyncMock(return_value={
            "status": "error", "reason": "tts_http_502"})
        handler = CallbackHandler(
            websocket=AsyncMock(), session_id="s", request_coordinator=coordinator,
            send_transcript=False, form_id="W-7", form_session_id="fss_t")
        handler._get_spellback_enabled = lambda: True

        response = await handler.on_tool_call(tool_name="name_spellback", arguments={})

        assert response["status"] == "error"
        assert "Do NOT speak the spelling yourself" in response["message"]
