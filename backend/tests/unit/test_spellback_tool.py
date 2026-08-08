"""
Unit tests for the deterministic spell-back tool (bd polyglot-pdf-22h1f).

name_spellback routes spelled read-backs OUT of the Live model's speech path:
the client plays a Cloud TTS letter-by-letter clip of the stored value while
the model is parked on the pending tool response. These tests pin:

- the tool handler's three response variants (delivered / interrupted / error)
  and that EVERY variant forbids the model from spelling itself (the whole
  point of the tool -- a variant that lets the model fall back to spelling
  from memory reintroduces the bd 0rpu defect exactly where it hurts);
- that the tool ignores model-supplied arguments (no field-id hallucination
  channel, bd jnjj.46);
- the flag-gated declaration (dark by default; declared only when
  SPELLBACK_TOOL_ENABLED) and the flag-gated SI addendum;
- the coordinator round-trip (payload pass-through + timeout sentinel);
- the plain-text clip builder (bd 44ywm: every character spoken, order
  preserved, session-language frame + punctuation words, whole verification
  question in the clip) and the session-language voice resolution;
- the /api/tts/spellback route gates (flag 503, empty/oversized 400, language
  passthrough; PII-free error logging is by construction -- the value never
  reaches a log call).

ASCII only.
"""
import asyncio

import pytest
from unittest.mock import AsyncMock, patch

from backend.config import Settings
from backend.services.callback_handler import CallbackHandler
from backend.services.request_coordinator import (
    CONFIRM_REQUEST_TIMEOUT,
    RequestCoordinator,
)
from backend.services.spellback_tts import (
    MAX_SPELLBACK_CHARS,
    build_spellback_text,
    resolve_spellback_locale,
    synthesize_spellback,
)


@pytest.fixture
def mock_websocket():
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
def mock_coordinator():
    coordinator = AsyncMock(spec=RequestCoordinator)
    coordinator.request_spellback = AsyncMock(
        return_value={"status": "delivered", "playback_ms": 4200, "fetch_ms": 300}
    )
    return coordinator


@pytest.fixture
def callback_handler(mock_websocket, mock_coordinator):
    handler = CallbackHandler(
        websocket=mock_websocket,
        session_id="test_session_123",
        request_coordinator=mock_coordinator,
        send_transcript=False,
        form_id="I-90",
        form_session_id="fss_test_12345",
    )
    # The dispatch is flag-gated (fail closed when the getter is absent);
    # these tests exercise the ENABLED tool's variants.
    handler._get_spellback_enabled = lambda: True
    return handler


class TestNameSpellbackTool:
    """The tool handler's response variants. Each message is checked with an
    ALLOWLIST of the sanctioned remedy (never a banned-word blacklist) plus the
    one invariant every variant must carry: the model is told not to spell."""

    @pytest.mark.asyncio
    async def test_delivered_instructs_confirm_without_respelling(
        self, callback_handler, mock_coordinator
    ):
        response = await callback_handler.on_tool_call(
            tool_name="name_spellback", arguments={}
        )

        assert response["success"] is True
        assert response["status"] == "delivered"
        # bd 44ywm: the clip carries the whole verification question, so the
        # sanctioned behavior is SILENCE -- wait for the user's answer.
        assert "stay silent and listen" in response["message"]
        assert "Do NOT ask again" in response["message"]
        # The one invariant: the model must not repeat/spell the value itself.
        assert "repeat or spell the value" in response["message"]
        mock_coordinator.request_spellback.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_interrupted_instructs_listening(
        self, callback_handler, mock_coordinator
    ):
        mock_coordinator.request_spellback = AsyncMock(
            return_value={"status": "interrupted", "playback_ms": 900}
        )

        response = await callback_handler.on_tool_call(
            tool_name="name_spellback", arguments={}
        )

        assert response["success"] is True
        assert response["status"] == "interrupted"
        # Sanctioned remedy: the user is speaking -- listen and respond.
        assert "Listen and respond" in response["message"]
        assert "Do NOT speak the spelling yourself" in response["message"]

    @pytest.mark.asyncio
    async def test_error_instructs_reask_never_self_spell(
        self, callback_handler, mock_coordinator
    ):
        mock_coordinator.request_spellback = AsyncMock(
            return_value={"status": "error", "reason": "tts_fetch_failed"}
        )

        response = await callback_handler.on_tool_call(
            tool_name="name_spellback", arguments={}
        )

        assert response.get("success") is not True
        assert response["status"] == "error"
        # Sanctioned remedy: re-ask the user to spell the value.
        assert "ask them to spell the value again" in response["message"]
        assert "Do NOT speak the spelling yourself" in response["message"]

    @pytest.mark.asyncio
    async def test_no_value_error_instructs_fill_first(
        self, callback_handler, mock_coordinator
    ):
        mock_coordinator.request_spellback = AsyncMock(
            return_value={"status": "error", "reason": "no_value"}
        )

        response = await callback_handler.on_tool_call(
            tool_name="name_spellback", arguments={}
        )

        assert response.get("success") is not True
        # Distinct remedy for the premature call: fill the field first.
        assert "update_form_fields first" in response["message"]
        assert "Do NOT speak the spelling yourself" in response["message"]

    @pytest.mark.asyncio
    async def test_timeout_sentinel_is_error_variant(
        self, callback_handler, mock_coordinator
    ):
        """A round-trip timeout must NOT read as delivered -- the model would
        ask for confirmation of a clip the user never heard."""
        mock_coordinator.request_spellback = AsyncMock(
            return_value=CONFIRM_REQUEST_TIMEOUT
        )

        response = await callback_handler.on_tool_call(
            tool_name="name_spellback", arguments={}
        )

        assert response.get("success") is not True
        assert response["status"] == "error"
        assert "ask them to spell the value again" in response["message"]

    @pytest.mark.asyncio
    async def test_model_supplied_arguments_are_ignored(
        self, callback_handler, mock_coordinator
    ):
        """No field-id hallucination channel (bd jnjj.46): whatever the model
        sends as arguments, the round-trip is invoked argument-free and the
        client resolves the current field itself."""
        response = await callback_handler.on_tool_call(
            tool_name="name_spellback",
            arguments={"field_id": "ghost_field", "value": "JOHN"},
        )

        assert response["success"] is True
        mock_coordinator.request_spellback.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_flag_off_call_refuses_without_round_trip(
        self, mock_websocket, mock_coordinator
    ):
        """The declaration is flag-gated, so a call while the flag is off is a
        hallucinated/undeclared call: refuse in-band IMMEDIATELY -- no client
        round-trip (mic hold, receive-loop block, PII value POSTed to a 503
        route). Opus cross-surface review, bd polyglot-pdf-dtywl. The default
        (no getter injected) fails closed the same way."""
        handler = CallbackHandler(
            websocket=mock_websocket,
            session_id="test_session_123",
            request_coordinator=mock_coordinator,
            send_transcript=False,
            form_id="I-90",
            form_session_id="fss_test_12345",
        )
        for getter in (None, (lambda: False)):
            handler._get_spellback_enabled = getter
            response = await handler.on_tool_call(
                tool_name="name_spellback", arguments={}
            )
            assert response.get("success") is not True
            assert "not available" in response["message"]
            assert "Do not call it again" in response["message"]
        mock_coordinator.request_spellback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_coordinator_is_error_variant(self, mock_websocket):
        handler = CallbackHandler(
            websocket=mock_websocket,
            session_id="test_session_123",
            request_coordinator=None,
            send_transcript=False,
            form_id="I-90",
            form_session_id="fss_test_12345",
        )

        response = await handler.on_tool_call(
            tool_name="name_spellback", arguments={}
        )

        assert response.get("success") is not True
        assert response["status"] == "error"


class TestSpellbackDeclarationGating:
    def _names(self, enabled: bool):
        from backend.services.form_filling_service import FormFillingService

        settings = Settings()
        settings.SPELLBACK_TOOL_ENABLED = enabled
        svc = FormFillingService(live_ai=None, settings=settings)
        return {d.get("name") for d in svc._build_tool_declarations()}

    def test_flag_off_keeps_tool_dark(self):
        assert "name_spellback" not in self._names(enabled=False)

    def test_flag_on_declares_tool_with_parameters_schema(self):
        from backend.services.form_filling_service import FormFillingService

        settings = Settings()
        settings.SPELLBACK_TOOL_ENABLED = True
        svc = FormFillingService(live_ai=None, settings=settings)
        decls = svc._build_tool_declarations()
        spellback = [d for d in decls if d.get("name") == "name_spellback"]
        assert len(spellback) == 1
        # The declaration must carry a `parameters` schema: a name-only
        # declaration (no parameters key) is the wire-verified 2.5
        # native-audio 1011 hazard (bd daa/h04c).
        assert spellback[0].get("parameters", {}).get("type") == "object"

    def test_flag_off_declared_set_is_byte_identical_to_default(self):
        """The dark tool must not perturb the default declared contract."""
        from backend.services.form_filling_service import FormFillingService

        settings = Settings()
        settings.SPELLBACK_TOOL_ENABLED = False
        svc = FormFillingService(live_ai=None, settings=settings)
        assert svc._build_tool_declarations() == [
            d for d in Settings().TOOL_DECLARATIONS
            if not (getattr(settings, "CONTINUOUS_SESSION", False)
                    and d.get("name") == "switch_section")
        ]


class TestSpellbackSiAddendum:
    def _si(self, enabled: bool) -> str:
        from backend.services import ai_context

        settings = Settings()
        settings.USE_DTI = True
        settings.SPELLBACK_TOOL_ENABLED = enabled
        with patch.object(ai_context, "get_settings", return_value=settings):
            return ai_context.build_form_context(
                schema={"fields": [], "jit_mode": True},
                current_values={},
            )

    def test_flag_on_appends_addendum(self):
        si = self._si(enabled=True)
        assert "name_spellback" in si
        assert "call the name_spellback tool instead" in si
        # bd 44ywm: the clip asks the question; the model's job is silence.
        assert "stay SILENT and listen" in si
        # The letters-only scope is load-bearing (Opus review, bd j6fxt): the
        # SPEECH STYLE block in the same assembled SI requires digit-by-digit
        # number read-back, and the addendum must not suppress it.
        assert "digit by digit yourself" in si

    def test_flag_on_appends_addendum_in_legacy_si_mode_too(self):
        """The tool declaration gates only on SPELLBACK_TOOL_ENABLED, not on
        USE_DTI -- so the addendum must ride BOTH SI modes, or a legacy-SI
        session with the flag on keeps its spell-it-yourself NAMES wording
        while the tool is live: double delivery, the exact failure the
        addendum prevents (fresh-eyes round 1)."""
        from backend.services import ai_context

        settings = Settings()
        settings.USE_DTI = False
        settings.SPELLBACK_TOOL_ENABLED = True
        with patch.object(ai_context, "get_settings", return_value=settings):
            si = ai_context.build_form_context(
                schema={"fields": []},  # legacy (non-jit) branch
                current_values={},
            )
        assert "name_spellback" in si
        assert "call the name_spellback tool instead" in si
        # bd 44ywm: the clip asks the question; the model's job is silence.
        assert "stay SILENT and listen" in si
        # The letters-only scope is load-bearing (Opus review, bd j6fxt): the
        # SPEECH STYLE block in the same assembled SI requires digit-by-digit
        # number read-back, and the addendum must not suppress it.
        assert "digit by digit yourself" in si

    def test_flag_off_leaves_si_untouched(self):
        si = self._si(enabled=False)
        assert "name_spellback" not in si
        assert si == Settings().DTI_SYSTEM_INSTRUCTION


class TestRequestSpellbackRoundTrip:
    @pytest.mark.asyncio
    async def test_payload_passes_through(self, mock_websocket):
        coordinator = RequestCoordinator(
            websocket=mock_websocket, session_id="s1")

        task = asyncio.create_task(coordinator.request_spellback())
        await asyncio.sleep(0)  # let the request send

        # The request carries ONLY type + request_id -- never a field value.
        sent = mock_websocket.send_json.await_args.args[0]
        assert sent["type"] == "spellback"
        assert set(sent.keys()) == {"type", "request_id"}

        coordinator.handle_spellback_response(
            sent["request_id"],
            {"status": "delivered", "playback_ms": 5100, "fetch_ms": 250},
        )
        result = await task
        assert result == {
            "status": "delivered", "playback_ms": 5100, "fetch_ms": 250}

    @pytest.mark.asyncio
    async def test_timeout_returns_sentinel(self, mock_websocket, monkeypatch):
        coordinator = RequestCoordinator(
            websocket=mock_websocket, session_id="s1")
        monkeypatch.setattr(
            RequestCoordinator, "SPELLBACK_ROUNDTRIP_TIMEOUT", 0.01)

        result = await coordinator.request_spellback()
        assert result is CONFIRM_REQUEST_TIMEOUT

    @pytest.mark.asyncio
    async def test_no_websocket_returns_sentinel(self):
        coordinator = RequestCoordinator(websocket=None, session_id="s1")
        result = await coordinator.request_spellback()
        assert result is CONFIRM_REQUEST_TIMEOUT


class TestSpellbackText:
    """The plain-text clip builder (bd 44ywm): natural sentence, session
    language, whole verification question -- never SSML (Chirp 3 HD renders
    markup mechanically; the maintainer's notebook A/B drove this design)."""

    def test_letters_uppercased_comma_joined_inside_the_frame(self):
        text = build_spellback_text("Jose", "en-US")
        assert text == "You said J, O, S, E. Is that correct?"

    def test_no_ssml_markup_ever(self):
        assert "<" not in build_spellback_text("Jose", "en-US")

    def test_session_language_frame_and_punctuation(self):
        text = build_spellback_text("O'Neil-A", "es-US")
        # Spanish frame carries the question...
        assert text.startswith("Usted dijo ")
        assert "Es correcto?" in text
        # ...and the Spanish punctuation words from the frames DATA file, so
        # the regional voice never code-switches mid-clip. Asserted via the
        # data (not literals) to keep this SOURCE file ASCII per scar #6.
        import json
        from pathlib import Path

        frames = json.loads(
            (Path(__file__).resolve().parents[2] /
             "services/spellback_frames.json").read_text(encoding="utf-8"))
        es_punct = frames["es-US"]["punctuation"]
        assert es_punct["'"] != "apostrophe"  # genuinely localized, not English
        assert es_punct["'"] in text
        assert es_punct["-"] in text

    def test_every_character_is_voiced_never_dropped(self):
        """A dropped character would make the clip verify a DIFFERENT string
        than the stored value -- the defect class this tool eliminates."""
        text = build_spellback_text("O'Neil-Smith Jr.", "en-US")
        assert "apostrophe" in text
        assert "dash" in text
        assert "space" in text
        assert "dot" in text
        # A character with no punctuation word rides as ITSELF, not dropped.
        assert "<" in build_spellback_text("A<B", "en-US")

    def test_digits_ride_as_characters(self):
        assert "A, 1" in build_spellback_text("A1", "en-US")

    def test_unknown_locale_falls_back_to_english_frame(self):
        assert build_spellback_text("AB", "xx-XX").startswith("You said ")

    def test_every_supported_language_has_a_complete_frame(self):
        """Enumerate the SET (repo rule): every spoken language the app
        offers must have a frame entry with the {letters} slot and a
        punctuation map -- a missing one silently degrades that language to
        English at runtime."""
        import json
        from pathlib import Path

        from backend.utils.language_codes import SPOKEN_LANGUAGE_BCP47

        frames = json.loads(
            (Path(__file__).resolve().parents[2] /
             "services/spellback_frames.json").read_text(encoding="utf-8"))
        for lang, code in SPOKEN_LANGUAGE_BCP47.items():
            entry = frames.get(code)
            assert entry, f"no spellback frame for {lang} ({code})"
            assert "{letters}" in entry["frame"], f"frame for {code} lacks slot"
            assert entry.get("punctuation"), f"no punctuation map for {code}"

    def test_locale_resolution(self):
        assert resolve_spellback_locale("Spanish") == "es-US"
        assert resolve_spellback_locale("spanish") == "es-US"
        assert resolve_spellback_locale("Klingon") == "en-US"
        assert resolve_spellback_locale(None) == "en-US"

    def test_voice_resolution_follows_session_language_and_persona(self):
        """Default: {session-locale}-Chirp3-HD-{LIVE_VOICE_NAME} (maintainer
        ruling 2026-08-08 -- the clip speaks the user's language in the
        model's persona). Explicit SPELLBACK_TTS_VOICE wins; a locale whose
        derived voice does not exist falls back to en-US, availability from
        the runtime voice list (never a hand-pinned language list)."""
        from backend.services import spellback_tts
        from backend.services.spellback_tts import resolve_spellback_voice

        s = Settings()
        s.SPELLBACK_TTS_VOICE = ""
        s.LIVE_VOICE_NAME = "Iapetus"
        with patch.object(spellback_tts, "_voice_exists", return_value=True):
            assert resolve_spellback_voice(s, "Spanish") == (
                "es-US-Chirp3-HD-Iapetus", "es-US")
            assert resolve_spellback_voice(s, None) == (
                "en-US-Chirp3-HD-Iapetus", "en-US")
            # Whitespace-padded env values strip (bd vx0q4).
            s.LIVE_VOICE_NAME = " Iapetus "
            assert resolve_spellback_voice(s, "Spanish") == (
                "es-US-Chirp3-HD-Iapetus", "es-US")

        # LANGUAGE-FIRST ladder (live probe 2026-08-08: ru-RU has 8 of the 30
        # Chirp3 personas and no Iapetus). Rung 2: keep the language, take
        # another persona -- never drop to English just to keep ours.
        s.LIVE_VOICE_NAME = "Iapetus"
        with patch.object(spellback_tts, "_voice_exists",
                          side_effect=lambda n: n.startswith("en-US")), \
             patch.object(spellback_tts, "_any_chirp3_voice_for",
                          side_effect=lambda loc: (
                              "ru-RU-Chirp3-HD-Zephyr" if loc == "ru-RU" else None)):
            assert resolve_spellback_voice(s, "Russian") == (
                "ru-RU-Chirp3-HD-Zephyr", "ru-RU")

        # Rung 3: no Chirp3 at all in that locale -> the locale's DEFAULT
        # voice, still the user's language (Tagalog/Urdu/Persian/Afrikaans
        # carry zero Chirp3 voices today).
        with patch.object(spellback_tts, "_voice_exists",
                          side_effect=lambda n: n.startswith("en-US")), \
             patch.object(spellback_tts, "_any_chirp3_voice_for",
                          return_value=None):
            assert resolve_spellback_voice(s, "Tagalog") == ("", "fil-PH")

        # Rung 4: only an UNKNOWN language lands on the English clip.
        with patch.object(spellback_tts, "_voice_exists",
                          side_effect=lambda n: n.startswith("en-US")), \
             patch.object(spellback_tts, "_any_chirp3_voice_for",
                          return_value=None):
            assert resolve_spellback_voice(s, "Klingon") == (
                "en-US-Chirp3-HD-Iapetus", "en-US")

        # Explicit override wins outright; its locale rides its prefix.
        s.SPELLBACK_TTS_VOICE = "en-US-Chirp3-HD-Algieba"
        assert resolve_spellback_voice(s, "Spanish") == (
            "en-US-Chirp3-HD-Algieba", "en-US")

        # No persona at all -> locale default voice.
        s.SPELLBACK_TTS_VOICE = ""
        s.LIVE_VOICE_NAME = ""
        assert resolve_spellback_voice(s, "Spanish") == ("", "es-US")

    def test_char_cap_matches_frontend_mirror(self):
        """MAX_SPELLBACK_CHARS is mirrored (not shared) as SPELLBACK_MAX_CHARS
        in frontend/src/shared/spellbackPlayer.ts -- the client's fail-fast
        pre-check. Drift would either reintroduce the wasted round-trip (FE cap
        too low) or surface backend 400s the client didn't anticipate (BE cap
        lowered alone). Pin them to each other (fresh-eyes round 3)."""
        import re
        from pathlib import Path

        ts = Path(__file__).resolve().parents[3] / (
            "frontend/src/shared/spellbackPlayer.ts")
        match = re.search(
            r"SPELLBACK_MAX_CHARS\s*=\s*(\d+)", ts.read_text(encoding="utf-8"))
        assert match, "SPELLBACK_MAX_CHARS constant missing from spellbackPlayer.ts"
        assert int(match.group(1)) == MAX_SPELLBACK_CHARS

    @pytest.mark.asyncio
    async def test_empty_and_oversized_values_are_rejected(self):
        s = Settings()
        with pytest.raises(ValueError):
            await synthesize_spellback("", s)
        with pytest.raises(ValueError):
            await synthesize_spellback("   ", s)
        with pytest.raises(ValueError):
            await synthesize_spellback("x" * (MAX_SPELLBACK_CHARS + 1), s)


class TestSpellbackTtsRoute:
    def _client(self, monkeypatch, enabled: bool):
        from fastapi.testclient import TestClient
        from backend.main import app
        from backend.services.auth import require_auth
        import backend.routes.tts_routes as tts_routes

        settings = Settings()
        settings.SPELLBACK_TOOL_ENABLED = enabled
        monkeypatch.setattr(tts_routes, "get_settings", lambda: settings)
        app.dependency_overrides[require_auth] = lambda: {"uid": "test"}
        client = TestClient(app)
        return client, app, require_auth

    def test_flag_off_is_503(self, monkeypatch):
        client, app, require_auth = self._client(monkeypatch, enabled=False)
        try:
            resp = client.post("/api/tts/spellback", json={"value": "Jose"})
            assert resp.status_code == 503
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_flag_on_returns_audio(self, monkeypatch):
        client, app, require_auth = self._client(monkeypatch, enabled=True)

        async def fake_synth(value, settings, language_name=None):
            assert value == "Jose"
            # The session language must ride the request into synthesis
            # (bd 44ywm: the clip speaks the user's language).
            assert language_name == "Spanish"
            return b"MP3BYTES"

        monkeypatch.setattr(
            "backend.routes.tts_routes.synthesize_spellback", fake_synth)
        try:
            resp = client.post(
                "/api/tts/spellback",
                json={"value": "Jose", "language": "Spanish"})
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("audio/mpeg")
            assert resp.content == b"MP3BYTES"
        finally:
            app.dependency_overrides.pop(require_auth, None)

    def test_empty_and_oversized_are_400(self, monkeypatch):
        client, app, require_auth = self._client(monkeypatch, enabled=True)
        try:
            assert client.post(
                "/api/tts/spellback", json={"value": "  "}
            ).status_code == 400
            assert client.post(
                "/api/tts/spellback",
                json={"value": "x" * (MAX_SPELLBACK_CHARS + 1)},
            ).status_code == 400
        finally:
            app.dependency_overrides.pop(require_auth, None)
