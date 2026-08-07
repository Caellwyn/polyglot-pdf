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
- the SSML builder (every character spoken, order preserved, XML-safe);
- the /api/tts/spellback route gates (flag 503, empty/oversized 400, PII-free
  error logging is by construction -- the value never reaches a log call).

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
    build_spellback_ssml,
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
    return CallbackHandler(
        websocket=mock_websocket,
        session_id="test_session_123",
        request_coordinator=mock_coordinator,
        send_transcript=False,
        form_id="I-90",
        form_session_id="fss_test_12345",
    )


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
        # Sanctioned remedy: ask the user whether the spelling is correct.
        assert "whether the spelling is correct" in response["message"]
        # The one invariant: the model must not repeat/spell the value itself.
        assert "Do NOT repeat or spell the value yourself" in response["message"]
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
        assert "NEVER speak a spelling letter by letter" in si

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
        assert "NEVER speak a spelling letter by letter" in si

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


class TestSpellbackSsml:
    def test_letters_spoken_individually_in_order(self):
        ssml = build_spellback_ssml("Jose")
        blocks = [
            '<say-as interpret-as="characters">J</say-as>',
            '<say-as interpret-as="characters">o</say-as>',
            '<say-as interpret-as="characters">s</say-as>',
            '<say-as interpret-as="characters">e</say-as>',
        ]
        pos = -1
        for block in blocks:
            nxt = ssml.find(block, pos + 1)
            assert nxt > pos, f"missing/misordered block: {block}"
            pos = nxt

    def test_every_character_is_voiced_never_dropped(self):
        """A dropped character would make the clip verify a DIFFERENT string
        than the stored value -- the defect class this tool eliminates."""
        ssml = build_spellback_ssml("O'Neil-Smith Jr.")
        assert "apostrophe" in ssml
        assert "hyphen" in ssml
        assert "space" in ssml
        assert "period" in ssml
        # Unknown characters are voiced as a placeholder, not dropped.
        assert "symbol" in build_spellback_ssml("A<B")

    def test_xml_is_escaped_not_injected(self):
        ssml = build_spellback_ssml("A<B")
        assert "<B" not in ssml.replace(
            '<say-as interpret-as="characters">B</say-as>', "")
        assert "A&B" not in build_spellback_ssml("A&B")

    def test_digits_are_spoken_as_characters(self):
        ssml = build_spellback_ssml("A1")
        assert '<say-as interpret-as="characters">1</say-as>' in ssml

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
        with pytest.raises(ValueError):
            await synthesize_spellback("")
        with pytest.raises(ValueError):
            await synthesize_spellback("   ")
        with pytest.raises(ValueError):
            await synthesize_spellback("x" * (MAX_SPELLBACK_CHARS + 1))


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

        async def fake_synth(value, voice_name=""):
            assert value == "Jose"
            return b"MP3BYTES"

        monkeypatch.setattr(
            "backend.routes.tts_routes.synthesize_spellback", fake_synth)
        try:
            resp = client.post("/api/tts/spellback", json={"value": "Jose"})
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
