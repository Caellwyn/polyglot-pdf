"""
Unit tests for the deterministic spell-back tool (bd polyglot-pdf-22h1f).

name_spellback routes spelled read-backs OUT of the Live model's speech path:
the client plays a Cloud TTS letter-by-letter clip of the stored value while
the tool response stays open for the playback duration. Holding the response
open does NOT park the model, though (bd polyglot-pdf-kvrfq, wire-verified
2026-08-26): under barge-in pressure the model can keep emitting further
name_spellback calls while earlier ones are unanswered, and those queue
behind the in-flight round-trip (see docs/components/voice-ai.md's
name_spellback bullet). These tests pin:

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

    def test_addendum_reasserts_the_ask_after_its_prohibitions(self):
        """The model's LAST naming instruction must tell it to ASK.

        bd polyglot-pdf-ku69b: this addendum is the final text in the assembled
        SI, and every earlier revision was pure prohibition ("do NOT read the
        value back", "stop speaking") opening with "For a NAME". The DTI names
        block's ask-for-the-spelling instruction lands thousands of characters
        EARLIER, so the model's last and most specific naming instruction said
        only "be silent" -- and on the live demo it stopped asking for
        spellings altogether, filling whatever name it heard. That makes the
        spell-back clip verify a value that may already be wrong.

        So this pins ORDER, not mere presence: an ask-instruction must survive
        AFTER the last prohibition. Asserting "the ask appears somewhere"
        would pass on exactly the broken SI this bead fixed -- the ask was
        always present, just buried.
        """
        si = self._si(enabled=True)

        last_prohibition = max(
            si.rfind("do NOT read the value back"),
            si.rfind("stay SILENT and listen"),
        )
        assert last_prohibition != -1, "the addendum's prohibitions are gone"

        tail = si[last_prohibition:]
        assert "ASK for the spelling" in tail, (
            "nothing tells the model to ASK for the spelling after the "
            "addendum's do-NOT-speak block -- the last naming instruction it "
            "reads is a prohibition, which is exactly the state that stopped "
            "it asking on the live demo (bd polyglot-pdf-ku69b)"
        )

        # The addendum must also SCOPE itself: without this it reads as the
        # whole naming policy rather than a read-back rule.
        assert "changes only how a spelling is READ BACK" in si
        assert "does NOT change how you ASK" in si

    def test_dti_names_block_forbids_filling_a_guessed_spelling(self):
        """The names block must refuse a spoken-name-only answer.

        The failure mode is not just "did not ask" -- it is filling a GUESS
        when the user answers with the name alone. Pinned separately from the
        addendum because it is the base SI's job, and the two texts drifted
        apart once the addendum took over the read-back (bd ku69b).
        """
        names_block = Settings().DTI_SYSTEM_INSTRUCTION
        assert "ask for the spelling before you fill anything" in names_block

    def test_every_name_read_back_instruction_yields_to_the_addendum(self):
        """ENUMERATE THE SET, do not fix one instance (CLAUDE.md scar #7).

        bd polyglot-pdf-5s3pp was filed against ONE unconditional
        verify-a-name-by-word sentence in the DTI names block. Fixing only
        that left a sibling 3,377 chars away in WORKFLOW step 3 -- in the
        MORE authoritative numbered-procedure block -- which the Opus
        cross-surface review then found (bd polyglot-pdf-wvjpo).

        So this derives the set MECHANICALLY from the shipped SI rather than
        trusting a hand-list: every instruction telling the model to speak a
        NAME back must carry the yields-to clause, or the assembled SI
        contradicts the spell-back addendum whenever the tool is on.

        Deliberately NOT in scope (the addendum's own preamble already
        overrides these in so many words):
          - verify-by-SPELLING wording ("read the SPELLING back") -- the
            preamble names it explicitly.
          - digit-by-digit NUMBER read-back -- the addendum preserves it.
        """
        import re

        si = Settings().DTI_SYSTEM_INSTRUCTION
        # Instructions to speak a NAME back as a word. Derived by pattern, so
        # a newly-added sibling is caught instead of silently joining the set.
        # Broad on purpose: any speak/say/read verb, any determiner, reaching
        # "as a word" / "as one word". A guard matching only the CURRENT
        # phrasing silently shrinks when a site is reworded -- which reads as
        # coverage while covering nothing (Opus cross-surface, bd
        # polyglot-pdf-9rauk: "say THEIR name back as a word" escaped the
        # first version and left the guard green with a live unqualified site).
        name_readback = re.compile(
            r"(say|saying|speak|speaking|read|reading|repeat)\b[^.;]{0,40}"
            r"\bname\b[^.;]{0,40}\bas (a|one) word", re.I)
        hits = list(name_readback.finditer(si))

        # CARDINALITY IS PART OF THE PIN. Without it, a reword that escapes the
        # pattern drops the set from 2 to 1 and the guard still reports "0
        # unqualified" -- green while an unqualified instruction ships. If this
        # number needs changing, re-derive the set FIRST and confirm every site
        # is qualified; do not just bump it to make the suite pass.
        EXPECTED_SITES = 2  # WORKFLOW step 3, and the NAMES block.
        assert len(hits) == EXPECTED_SITES, (
            "expected %d name-read-back instruction(s) in the DTI SI, found "
            "%d -- a site was added, removed, or REWORDED past this pattern. "
            "Re-derive the set (search the SI for read-back verbs near "
            "'name') and confirm each carries the yields-to clause before "
            "changing this number.\n  found: %s"
            % (EXPECTED_SITES, len(hits),
               [si[max(0, m.start() - 40):m.end() + 10] for m in hits])
        )

        unqualified = []
        for m in hits:
            preceding = si[max(0, m.start() - 130):m.start()]
            if "Unless a later instruction" not in preceding:
                unqualified.append(si[max(0, m.start() - 90):m.end() + 40])
        assert not unqualified, (
            "%d name-read-back instruction(s) are stated UNCONDITIONALLY, so "
            "they contradict the spell-back addendum when the tool is on "
            "(bd polyglot-pdf-5s3pp / wvjpo). Each needs the 'Unless a later "
            "instruction' clause:\n  %s"
            % (len(unqualified), "\n  ".join(repr(u) for u in unqualified))
        )

    def test_verify_by_word_yields_to_the_spellback_addendum(self):
        """The two verification rules must not flatly contradict each other.

        The names block says to verify a name by saying it back as a word; the
        addendum (appended whenever SPELLBACK_TOOL_ENABLED, which is the
        demo's shipped state) says do NOT read the value back at all and call
        the tool instead. Opus cross-surface review, bd polyglot-pdf-5s3pp:
        with the flag ON the assembled SI carried both, unqualified.

        The names-block sentence must therefore be CONDITIONAL -- it still
        governs flag-off sessions, where no addendum ever arrives, so deleting
        it would leave those with no name verification at all.
        """
        names_block = Settings().DTI_SYSTEM_INSTRUCTION
        idx = names_block.find("verify by saying the name back as a word")
        assert idx != -1, "the flag-off verification rule is gone"
        # It must be qualified by a yields-to clause, not stated absolutely.
        preceding = names_block[max(0, idx - 120):idx]
        assert "Unless a later instruction" in preceding, (
            "the verify-by-word rule is stated unconditionally, so it "
            "contradicts the spell-back addendum whenever the tool is on "
            "(bd polyglot-pdf-5s3pp)"
        )

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

        # An UNKNOWN language resolves to the en-US locale upstream, and its
        # persona voice is used when it exists.
        with patch.object(spellback_tts, "_voice_exists",
                          side_effect=lambda n: n.startswith("en-US")), \
             patch.object(spellback_tts, "_any_chirp3_voice_for",
                          return_value=None):
            assert resolve_spellback_voice(s, "Klingon") == (
                "en-US-Chirp3-HD-Iapetus", "en-US")

        # TERMINAL rung: NOTHING matches, including in en-US (a misconfigured
        # LIVE_VOICE_NAME). The ladder must return the locale's DEFAULT voice
        # -- an empty name is always valid -- and must NEVER hand back the
        # persona name rung 1 already proved nonexistent, which would 502
        # every clip in the session (fresh-eyes round 2).
        with patch.object(spellback_tts, "_voice_exists", return_value=False), \
             patch.object(spellback_tts, "_any_chirp3_voice_for",
                          return_value=None):
            assert resolve_spellback_voice(s, None) == ("", "en-US")
            assert resolve_spellback_voice(s, "English") == ("", "en-US")
            assert resolve_spellback_voice(s, "Spanish") == ("", "es-US")

        # Explicit override wins outright; its locale rides its prefix.
        s.SPELLBACK_TTS_VOICE = "en-US-Chirp3-HD-Algieba"
        assert resolve_spellback_voice(s, "Spanish") == (
            "en-US-Chirp3-HD-Algieba", "en-US")

        # No persona at all -> locale default voice.
        s.SPELLBACK_TTS_VOICE = ""
        s.LIVE_VOICE_NAME = ""
        assert resolve_spellback_voice(s, "Spanish") == ("", "es-US")

    def test_no_doc_or_comment_claims_the_pre_44ywm_clip_design(self):
        """Pin the SET, not the instance (CLAUDE.md scar #7).

        The bd 44ywm redesign invalidated two claims that were restated in
        several places: that the clip's voice is hardcoded `en-US-Chirp3-HD-*`
        (it follows the SESSION language now) and that a missing persona 502s
        the clip (the ladder degrades). The Opus cross-surface review found a
        surviving restatement in voice-ai.md AFTER the sibling block in the
        same file had been corrected -- exactly the one-per-round pattern this
        rule exists to stop. Assert the whole set is clean so the next
        omission fails here instead of in review.
        """
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        # The surface is DERIVED, not hand-listed (a hand-list is the same
        # omission bug one level up): every non-journal doc/source file that
        # mentions the feature by name is in scope.
        candidates = []
        for pattern in ("docs/**/*.md", "backend/**/*.py",
                        "frontend/src/**/*.ts"):
            candidates.extend(root.glob(pattern))
        targets = []
        for path in candidates:
            parts = path.as_posix()
            if "/journal/" in parts or "/node_modules/" in parts:
                continue  # journal is the chronological record; exempt
            if path.name == Path(__file__).name:
                continue  # this test names the stale claims on purpose
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "spellback" in text.lower() or "spell-back" in text.lower():
                targets.append((path, text))
        assert len(targets) >= 8, (
            "surface enumeration found only %d files -- the glob is wrong"
            % len(targets))

        # Claim A: the clip's voice locale is hardcoded to en-US. Matches any
        # phrasing that puts en-US next to the Chirp3 voice pattern, or that
        # says the clip is always/regardless-of-session English.
        hardcoded_en_us = re.compile(
            r"en-US-Chirp3-HD-[<{`]?(?:persona|name|LIVE_VOICE_NAME)"
            r"|(?:ALWAYS|always)\s+en-US\b"
            r"|en-US\s+regardless of (?:the )?session",
            re.IGNORECASE)
        # Claim B: a persona with no twin in the locale 502s the clip. Matches
        # any sentence tying 502/fail to a missing persona/voice/twin --
        # EXCEPT a negation ("never 502s", "can NOT 502"), which is the
        # corrected prose asserting the opposite.
        persona_502 = re.compile(
            r"(?<!never )(?<!cannot )(?<!can not )(?<!no longer )502s?"
            r"[^.\n]{0,80}(?:persona|voice|twin)"
            r"|(?:persona|voice|twin)[^.\n]{0,80}"
            r"(?<!never )(?<!cannot )(?<!can not )(?<!no longer )502s?\b",
            re.IGNORECASE)

        offenders = []
        for path, text in targets:
            for label, pattern in (("hardcoded en-US voice", hardcoded_en_us),
                                   ("persona-miss 502 claim", persona_502)):
                hit = pattern.search(text)
                if hit:
                    offenders.append("%s: %s (%r)"
                                     % (path.name, label, hit.group(0)[:60]))

        assert not offenders, (
            "pre-44ywm clip design still asserted in: %s" % offenders)

    def test_clip_is_loudness_leveled_against_the_model_voice(self):
        """The encode must carry the measured gain (bd polyglot-pdf-9oejl).

        Without it the clip plays ~5 dB under the model's voice and sounds odd
        mid-conversation, and the client cannot compensate -- an
        HTMLAudioElement's volume only ATTENUATES and is already at 1.0. So
        the gain lives in the encode, and a drop back to the API default is a
        silent audio regression no other test would catch.
        """
        from unittest.mock import MagicMock

        from backend.services import spellback_tts

        assert spellback_tts.spellback_gain_db("en-US-Chirp3-HD-Algieba") > 0, (
            "the clip must be boosted, not attenuated")

        captured = {}

        class _FakeTTS:
            AudioEncoding = MagicMock(MP3="MP3")

            @staticmethod
            def SynthesisInput(**kw):
                return kw

            @staticmethod
            def VoiceSelectionParams(**kw):
                return kw

            @staticmethod
            def AudioConfig(**kw):
                captured.update(kw)
                return kw

        fake_client = MagicMock()
        fake_client.synthesize_speech.return_value = MagicMock(
            audio_content=b"MP3")
        with patch.dict("sys.modules",
                        {"google.cloud": MagicMock(texttospeech=_FakeTTS)}), \
             patch.object(spellback_tts, "_get_client", lambda: fake_client):
            spellback_tts._synthesize_sync(
                "You said J, O.", "en-US-Chirp3-HD-Algieba", "en-US")

        assert captured.get("volume_gain_db") == (
            spellback_tts.spellback_gain_db("en-US-Chirp3-HD-Algieba")), (
            "the synthesis request dropped the loudness gain")

    def test_gain_follows_the_voice_that_actually_speaks(self):
        """The gain must track the RESOLVED voice, at runtime.

        Voices differ in base loudness: measured 2026-08-11, Algieba starts at
        72% of the model's level where Iapetus starts at 57%, so Iapetus's
        +7.0 dB drives Algieba past full scale and CLIPS (peak 1.025) --
        audibly worse than the quiet clip the leveling was added to fix.

        This pins the RUNTIME property, not a pair of compile-time defaults
        (fresh-eyes round 1): the gain is looked up FROM the voice, so an
        operator overriding LIVE_VOICE_NAME on Cloud Run cannot ship a
        mismatch, and a fallback persona (rung 2/3 of the ladder, a locale
        without the configured persona) gets ITS own gain rather than the
        configured voice's.
        """
        from backend.services import spellback_tts

        assert spellback_tts.spellback_gain_db("en-US-Chirp3-HD-Algieba") == 4.0
        assert spellback_tts.spellback_gain_db("en-US-Chirp3-HD-Iapetus") == 7.0
        # A DIFFERENT locale, same persona -> same measured gain (the ladder's
        # rung 1 for a non-English session).
        assert spellback_tts.spellback_gain_db("es-US-Chirp3-HD-Algieba") == 4.0

        # An UNMEASURED persona (a fallback rung, or a voice nobody has
        # measured yet) must take the CONSERVATIVE end of the table: too quiet
        # is the defect we started from, but too loud CLIPS, which is worse
        # and cannot be undone downstream.
        quiet_end = min(spellback_tts._MEASURED_GAIN_DB.values())
        assert spellback_tts.spellback_gain_db("ru-RU-Chirp3-HD-Charon") == quiet_end
        assert spellback_tts.spellback_gain_db("") == quiet_end

    def test_env_override_wins_over_the_measured_table(self, monkeypatch):
        """The escape hatch must actually work.

        SPELLBACK_VOLUME_GAIN_DB exists so a new voice can be tuned BY EAR
        before its measurement lands in the table. Fresh-eyes round 2 deleted
        the whole override block and every test still passed -- an untested
        claim in a docstring is not a proven one (scar #8), so pin it: the
        override beats the table, a malformed value falls back to the table
        rather than crashing a session, and it is read per call (an operator
        setting it on Cloud Run must not need a code change).
        """
        from backend.services import spellback_tts

        algieba = "en-US-Chirp3-HD-Algieba"
        assert spellback_tts.spellback_gain_db(algieba) == 4.0

        monkeypatch.setenv("SPELLBACK_VOLUME_GAIN_DB", "2.5")
        assert spellback_tts.spellback_gain_db(algieba) == 2.5, (
            "the env override did not win over the measured table")
        # It overrides for EVERY persona, including an unmeasured one.
        assert spellback_tts.spellback_gain_db("ru-RU-Chirp3-HD-Charon") == 2.5

        # A typo must not break the session: fall back to the measured value.
        monkeypatch.setenv("SPELLBACK_VOLUME_GAIN_DB", "loud")
        assert spellback_tts.spellback_gain_db(algieba) == 4.0, (
            "a malformed override should fall back to the table, not crash")

        # Cleared -> back to the table (proves it is read per call, not cached
        # at import).
        monkeypatch.delenv("SPELLBACK_VOLUME_GAIN_DB")
        assert spellback_tts.spellback_gain_db(algieba) == 4.0

    def test_the_default_voice_has_a_measured_gain(self):
        """A voice-default change must not outrun its measurement.

        Swapping LIVE_VOICE_NAME to a persona nobody has measured would
        silently fall back to the conservative gain -- safe, but quiet, which
        is the very defect bd polyglot-pdf-9oejl fixed. Fail loudly instead,
        naming the command that produces the missing number.
        """
        from backend.services import spellback_tts

        persona = Settings().LIVE_VOICE_NAME
        assert persona in spellback_tts._MEASURED_GAIN_DB, (
            "LIVE_VOICE_NAME default is %r but no loudness measurement is "
            "recorded for it. Run:\n"
            "  SPELLBACK_TTS_VOICE=en-US-Chirp3-HD-%s backend/.venv/Scripts/"
            "python.exe scripts/spikes/measure_spellback_loudness.py\n"
            "and add the result to _MEASURED_GAIN_DB in spellback_tts.py"
            % (persona, persona)
        )

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
    async def test_all_blocking_work_runs_off_the_event_loop(self):
        """Voice RESOLUTION as well as synthesis must run in a worker thread.

        The ladder's first call per process fetches list_voices -- a network
        RPC. /ws/fill and /api/tts/spellback share one event loop, so
        resolving on the loop would freeze EVERY concurrent session's control
        channel, the same defect class bd 4hnyq fixes on the handshake path
        (Opus cross-surface review). Pinned by thread identity: neither call
        may happen on the loop's thread.
        """
        import threading

        from backend.services import spellback_tts

        loop_thread = threading.get_ident()
        seen = {}

        def fake_resolve(settings, language_name=None):
            seen["resolve_thread"] = threading.get_ident()
            return "", "en-US"

        def fake_synth(text, voice_name, locale):
            seen["synth_thread"] = threading.get_ident()
            return b"MP3"

        with patch.object(spellback_tts, "resolve_spellback_voice", fake_resolve), \
             patch.object(spellback_tts, "_synthesize_sync", fake_synth):
            await spellback_tts.synthesize_spellback("Jose", Settings(), "English")

        assert seen["resolve_thread"] != loop_thread, (
            "voice resolution ran on the event loop -- its list_voices RPC "
            "would stall every concurrent session")
        assert seen["synth_thread"] != loop_thread

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
        # The TTS routes moved to the STRICTER dependency (bd
        # polyglot-pdf-ugm6): they spend money, so a completed client link
        # must buy no more synthesis. Override THAT, or every request here
        # 401s on a real token check.
        from backend.services.auth import require_paid_client_work as require_auth
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
            # Wire-compat: a client one deploy behind omits `language`
            # entirely; the route must still synthesize (en-US fallback),
            # never 422 on the missing optional field.
            seen = {}

            async def fake_synth_no_lang(value, settings, language_name=None):
                seen["language_name"] = language_name
                return b"MP3BYTES"

            monkeypatch.setattr(
                "backend.routes.tts_routes.synthesize_spellback",
                fake_synth_no_lang)
            resp2 = client.post("/api/tts/spellback", json={"value": "Jose"})
            assert resp2.status_code == 200
            assert seen["language_name"] is None
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


class TestSpellbackDefaultIsOn:
    """The DEFAULT, not the explicitly-set flag (bd polyglot-pdf-apkdl).

    Every other test in this file assigns SPELLBACK_TOOL_ENABLED before
    asserting, so the whole suite passed identically with the default off and
    the default on. Nothing pinned the default -- which is exactly how the
    local-vs-deployed divergence survived: deploy-demo.sh set the env var,
    nothing local did, and the model silently had no tool to call.

    These pin the shipped default so a future edit flipping it back fails here
    rather than being rediscovered from a voice session.
    """

    def test_default_settings_enable_the_spellback_tool(self):
        # A Settings() built with no env override -- the local-run shape.
        assert Settings().SPELLBACK_TOOL_ENABLED is True, (
            "the spell-back tool must be ON by default; a default-off feature "
            "that only deploy-demo.sh turns on makes every local session "
            "diverge from the demo"
        )

    def test_a_default_session_declares_the_tool(self):
        """End-to-end through the real builder, not just the flag value."""
        from backend.services.form_filling_service import FormFillingService

        svc = FormFillingService(live_ai=None, settings=Settings())
        names = {d.get("name") for d in svc._build_tool_declarations()}
        assert "name_spellback" in names, (
            "a default local session must be given the tool -- without it the "
            "model falls back to speaking the spelling aloud, which is the "
            "audio defect bd polyglot-pdf-22h1f exists to remove"
        )

    def test_a_default_session_carries_the_SI_addendum(self, monkeypatch):
        """Declaring the tool is not enough: the addendum is what TELLS the
        model to call it instead of spelling aloud. Both must ride the same
        default, or the model holds a tool it was never told to use -- which is
        arguably worse than not having it, since the spoken fallback still
        fires."""
        from backend.services import ai_context

        # build_form_context reads settings via get_settings(), so patch the
        # module's own reference rather than passing an argument.
        monkeypatch.setattr(ai_context, "get_settings", lambda: Settings())
        si = ai_context.build_form_context(
            schema={"fields": [], "form_title": "W-7"},
            current_values={},
        )
        assert "SPELL-BACK AUDIO TOOL" in si, (
            "a default session must carry the spell-back addendum; without it "
            "the model has the tool but is never told to prefer it over "
            "spelling the name aloud itself"
        )

    def test_the_env_var_still_disables_it(self, monkeypatch):
        """The flag remains a real rollback. Flipping the default must not
        remove the ability to turn the feature off in an emergency."""
        import importlib

        monkeypatch.setenv("SPELLBACK_TOOL_ENABLED", "false")
        import backend.config as config_module

        reloaded = importlib.reload(config_module)
        try:
            assert reloaded.Settings().SPELLBACK_TOOL_ENABLED is False
        finally:
            # Restore the module for every later test in the session.
            monkeypatch.delenv("SPELLBACK_TOOL_ENABLED", raising=False)
            importlib.reload(config_module)
