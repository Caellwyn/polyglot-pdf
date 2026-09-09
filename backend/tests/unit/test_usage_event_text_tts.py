"""Text + TTS usage-event plumbing (bd polyglot-pdf-t86oz, E3.3).

WHAT THIS PINS. TextAIGemini is a per-process SINGLETON
(backend/dependencies.py), so the firm/employee/link/kit/channel ids for a
call must never live on `self` -- they would leak across concurrent
sessions. This bead threads them through an optional `session_ctx` kwarg on
validate/ask/translate_labels/translate_items instead, all the way to
_generate -> _log_usage -> log_text_ai_usage. The TTS side has no singleton
concern (each request is its own coroutine), but the ids still come from the
route's claims dict rather than any stored state.

THREE LAYERS, matching the bead's three exit criteria:
  1. EMIT PROOF -- each of the three text usage_kinds and three TTS
     usage_kinds emits ONE usage event per call, through the real call path
     (validate()/ask()/translate_labels()/translate_items()/
     synthesize_spellback()/synthesize_notice()/synthesize_intro()) with the
     SDK client mocked, cost computed, and ids carried. Mutation-verified per
     kind by removing the emit (see MUTATION VERIFICATION below).
  2. CONCURRENCY -- two TextAIGemini.validate() calls on the SAME adapter
     instance, given different session_ctx, never see each other's ids: the
     ids ride the call/session_ctx, never self.
  3. (test_usage_event_coverage.py's xfails removed -- proven by that file's
     own green run, not repeated here.)

MUTATION VERIFICATION (done by hand during authoring, reverted after):
  - Commenting out `self._log_usage(..., usage_kind=usage_kind,
    session_ctx=session_ctx)`'s two new kwargs in text_ai_gemini.py's
    _generate turns test_validate_emits_text_validator_usage_event (and its
    ask/translate siblings) red -- the mocked log_text_ai_usage is never
    called.
  - Commenting out `_log_tts_usage_event(...)` in spellback_tts.py /
    notice_tts.py / intro_tts.py turns the matching TTS emit test red.
  - Storing session_ctx on `self` in TextAIGemini.__init__ (instead of
    threading it through the call) turns
    test_concurrent_sessions_never_leak_ids_on_the_singleton red: the second
    call's event would carry the FIRST call's ids.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Text side: validate / ask / translate_labels / translate_items
# ---------------------------------------------------------------------------

def _make_response(text, cached_tokens=0, prompt_tokens=100, output_tokens=20):
    usage = SimpleNamespace(
        cached_content_token_count=cached_tokens,
        prompt_token_count=prompt_tokens,
        candidates_token_count=output_tokens,
        total_token_count=prompt_tokens + output_tokens,
    )
    return SimpleNamespace(text=text, usage_metadata=usage)


def _make_adapter(response_or_responses):
    """A real TextAIGemini with genai.Client patched at the SDK boundary
    (same pattern as test_text_ai_gemini.py's adapter_with_client fixture).
    Accepts either one response (every call returns it) or a list (one per
    call, in order) for the concurrency test.
    """
    from backend.adapters.text_ai_gemini import TextAIGemini

    mock_client = MagicMock()
    if isinstance(response_or_responses, list):
        mock_client.aio.models.generate_content = AsyncMock(
            side_effect=response_or_responses
        )
    else:
        mock_client.aio.models.generate_content = AsyncMock(
            return_value=response_or_responses
        )
    with patch("backend.adapters.text_ai_gemini.genai") as mock_genai:
        mock_genai.Client.return_value = mock_client
        adapter = TextAIGemini(
            api_key="test-key", vertexai=False, model="gemini-2.5-flash-lite"
        )
    adapter._client = mock_client
    return adapter


SESSION_CTX = {
    "firm_id": "firm-1",
    "employee_id": "emp-1",
    "link_jti": "jti-1",
    "kit_id": "i-90",
    "channel": "staging",
    "form_session_id": "fs-1",
}


@pytest.mark.asyncio
async def test_validate_emits_text_validator_usage_event():
    """validate() emits ONE log_text_ai_usage(usage_kind="text_validator")
    carrying the session_ctx ids and a positive cost."""
    response = _make_response('{"conflicts":[]}')
    adapter = _make_adapter(response)
    payload = {"stable_prefix": ["catalog"], "fresh_tail": ["state"]}

    with patch("backend.adapters.text_ai_gemini.get_structured_logger") as mock_get:
        mock_logger = MagicMock()
        mock_get.return_value = mock_logger
        await adapter.validate(payload, session_ctx=SESSION_CTX)

    mock_logger.log_text_ai_usage.assert_called_once()
    kwargs = mock_logger.log_text_ai_usage.call_args.kwargs
    assert kwargs["usage_kind"] == "text_validator"
    assert kwargs["firm_id"] == "firm-1"
    assert kwargs["employee_id"] == "emp-1"
    assert kwargs["link_jti"] == "jti-1"
    assert kwargs["kit_id"] == "i-90"
    assert kwargs["channel"] == "staging"
    assert kwargs["form_session_id"] == "fs-1"
    assert kwargs["model"] == "gemini-2.5-flash-lite"
    assert kwargs["metadata"]["cost_estimate_usd"] > 0


@pytest.mark.asyncio
async def test_ask_emits_text_secretary_usage_event():
    """ask() emits ONE log_text_ai_usage(usage_kind="text_secretary")."""
    verdict = json.dumps({"answer": "42", "sourced_from": [], "resolved": True})
    response = _make_response(verdict)
    adapter = _make_adapter(response)
    context = {
        "schema": {"fields": [{"id": "f1", "name": "Field 1"}]},
        "field_values": {},
        "shown_map": {},
    }

    with patch("backend.adapters.text_ai_gemini.get_structured_logger") as mock_get:
        mock_logger = MagicMock()
        mock_get.return_value = mock_logger
        await adapter.ask("what is field 1", context, session_ctx=SESSION_CTX)

    mock_logger.log_text_ai_usage.assert_called_once()
    kwargs = mock_logger.log_text_ai_usage.call_args.kwargs
    assert kwargs["usage_kind"] == "text_secretary"
    assert kwargs["firm_id"] == "firm-1"
    assert kwargs["metadata"]["cost_estimate_usd"] > 0


@pytest.mark.asyncio
async def test_translate_labels_emits_text_translation_usage_event():
    """translate_labels() emits ONE
    log_text_ai_usage(usage_kind="text_translation")."""
    response = _make_response(json.dumps({"Yes": "Si", "No": "No"}))
    adapter = _make_adapter(response)

    with patch("backend.adapters.text_ai_gemini.get_structured_logger") as mock_get:
        mock_logger = MagicMock()
        mock_get.return_value = mock_logger
        await adapter.translate_labels(
            ["Yes", "No"], "Spanish", "es", session_ctx=SESSION_CTX
        )

    mock_logger.log_text_ai_usage.assert_called_once()
    kwargs = mock_logger.log_text_ai_usage.call_args.kwargs
    assert kwargs["usage_kind"] == "text_translation"
    assert kwargs["kit_id"] == "i-90"
    assert kwargs["metadata"]["cost_estimate_usd"] > 0


@pytest.mark.asyncio
async def test_translate_items_emits_text_translation_usage_event():
    """translate_items() emits ONE
    log_text_ai_usage(usage_kind="text_translation") -- the context-carrying
    translation path shares the same usage_kind as translate_labels (both
    bill the same product: the plain generate_content translation call)."""
    response = _make_response(json.dumps({
        "items": {"fn:0": {"translation": "Nombre"}}, "ambiguous": [],
    }))
    adapter = _make_adapter(response)
    items = [{"id": "fn:0", "kind": "field-name", "text": "Name"}]

    with patch("backend.adapters.text_ai_gemini.get_structured_logger") as mock_get:
        mock_logger = MagicMock()
        mock_get.return_value = mock_logger
        await adapter.translate_items(
            items, "Spanish", "es", session_ctx=SESSION_CTX
        )

    mock_logger.log_text_ai_usage.assert_called_once()
    kwargs = mock_logger.log_text_ai_usage.call_args.kwargs
    assert kwargs["usage_kind"] == "text_translation"
    assert kwargs["metadata"]["cost_estimate_usd"] > 0


@pytest.mark.asyncio
async def test_unmigrated_caller_still_emits_with_null_context():
    """A call with NO session_ctx (an authoring-time bake, or a legacy
    caller) still emits a usage event -- every context key null, per the v2
    envelope contract (bd polyglot-pdf-wio6m: a missing key and a null are
    different things at the BigQuery sink)."""
    response = _make_response('{"conflicts":[]}')
    adapter = _make_adapter(response)

    with patch("backend.adapters.text_ai_gemini.get_structured_logger") as mock_get:
        mock_logger = MagicMock()
        mock_get.return_value = mock_logger
        await adapter.validate({"stable_prefix": [], "fresh_tail": []})

    mock_logger.log_text_ai_usage.assert_called_once()
    kwargs = mock_logger.log_text_ai_usage.call_args.kwargs
    assert kwargs["firm_id"] is None
    assert kwargs["employee_id"] is None
    assert kwargs["link_jti"] is None
    assert kwargs["kit_id"] is None
    assert kwargs["channel"] is None
    assert kwargs["form_session_id"] is None


@pytest.mark.asyncio
async def test_unknown_model_emits_null_cost_not_a_guess():
    """A model with no TEXT_GENERATION_PRICING row emits cost_estimate_usd
    None, never a guessed number (docs/standards/logging-and-cost.md: an
    explicit gap beats a confident wrong number)."""
    from backend.adapters.text_ai_gemini import TextAIGemini

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        return_value=_make_response('{"conflicts":[]}')
    )
    with patch("backend.adapters.text_ai_gemini.genai") as mock_genai:
        mock_genai.Client.return_value = mock_client
        adapter = TextAIGemini(
            api_key="test-key", vertexai=False,
            model="some-unpriced-model", fallback_models=(),
        )
    adapter._client = mock_client

    with patch("backend.adapters.text_ai_gemini.get_structured_logger") as mock_get:
        mock_logger = MagicMock()
        mock_get.return_value = mock_logger
        await adapter.validate({"stable_prefix": [], "fresh_tail": []})

    kwargs = mock_logger.log_text_ai_usage.call_args.kwargs
    assert kwargs["metadata"]["cost_estimate_usd"] is None


# ---------------------------------------------------------------------------
# Exit criterion 2: concurrent sessions never leak ids on the singleton
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_sessions_never_leak_ids_on_the_singleton():
    """TWO validate() calls on the SAME adapter instance (the singleton
    shape -- backend/dependencies.py constructs exactly one TextAIGemini per
    process), given DIFFERENT session_ctx, run concurrently and each event
    carries ONLY its own call's ids -- never the other call's.

    The mocked generate_content call AWAITS (a real asyncio.sleep, staggered
    A-slower-than-B), so the two validate() calls actually INTERLEAVE at the
    point after the SDK call returns: A starts, suspends on its await; B
    starts, runs to completion (including ITS OWN usage-event emit) while A
    is still suspended; A then resumes and emits. A synchronous/instant mock
    would let both calls run back-to-back with no real interleaving, which
    would make this test pass even under the leak mutation below -- verified
    by hand (an earlier version of this fixture used a plain AsyncMock with
    no await inside, and the mutation hook did NOT turn it red).

    MUTATION HOOK: storing session_ctx (or any of its ids) on `self` inside
    TextAIGemini instead of threading it through the call/kwarg chain makes
    A's LATE emit carry B's ids (B overwrote self between A's suspend and
    resume) -- verified by hand during authoring: temporarily setting
    `self._leaked_session_ctx = session_ctx` in _generate and reading it back
    in _log_usage (`session_ctx = getattr(self, '_leaked_session_ctx', None)`)
    instead of the parameter turned this test red (A's emitted firm_id came
    back "firm-B" instead of "firm-A").
    """
    calls_seen: list = []

    async def fake_generate_content(**kwargs):
        # A is the FIRST call scheduled and the SLOWER one, so it is the one
        # suspended-then-resumed-after-B -- exactly the leak window.
        is_first_call = len(calls_seen) == 0
        calls_seen.append(1)
        await asyncio.sleep(0.02 if is_first_call else 0.0)
        return _make_response('{"conflicts":[]}')

    adapter = _make_adapter(_make_response('{"conflicts":[]}'))
    adapter._client.aio.models.generate_content = AsyncMock(
        side_effect=fake_generate_content
    )

    ctx_a = {**SESSION_CTX, "firm_id": "firm-A", "kit_id": "kit-A"}
    ctx_b = {**SESSION_CTX, "firm_id": "firm-B", "kit_id": "kit-B"}

    with patch("backend.adapters.text_ai_gemini.get_structured_logger") as mock_get:
        mock_logger = MagicMock()
        mock_get.return_value = mock_logger
        results = await asyncio.gather(
            adapter.validate({"stable_prefix": ["a"], "fresh_tail": []}, session_ctx=ctx_a),
            adapter.validate({"stable_prefix": ["b"], "fresh_tail": []}, session_ctx=ctx_b),
        )

    assert results == [{"conflicts": []}, {"conflicts": []}]
    assert mock_logger.log_text_ai_usage.call_count == 2
    firm_ids = [
        call.kwargs["firm_id"] for call in mock_logger.log_text_ai_usage.call_args_list
    ]
    kit_ids = [
        call.kwargs["kit_id"] for call in mock_logger.log_text_ai_usage.call_args_list
    ]
    # B's emit lands FIRST (it does not sleep); A's emit lands SECOND, after
    # resuming from its sleep -- this is the exact ordering the leak mutation
    # corrupts, so assert per-position, not just as a set.
    assert firm_ids == ["firm-B", "firm-A"], (
        f"got {firm_ids}; the singleton is leaking one call's ids into the "
        "other's event"
    )
    assert kit_ids == ["kit-B", "kit-A"]
    # No attribute on the adapter itself carries either session's ids -- the
    # singleton stays clean between calls.
    assert not hasattr(adapter, "_session_ctx")
    assert not hasattr(adapter, "_firm_id")


@pytest.mark.asyncio
async def test_concurrent_sessions_one_with_ctx_one_without():
    """The mixed case: one caller passes session_ctx, a concurrent one does
    not. Neither call's presence/absence of ids affects the other's event."""
    async def fake_generate_content(**kwargs):
        await asyncio.sleep(0)
        return _make_response('{"conflicts":[]}')

    adapter = _make_adapter(_make_response('{"conflicts":[]}'))
    adapter._client.aio.models.generate_content = AsyncMock(
        side_effect=fake_generate_content
    )

    with patch("backend.adapters.text_ai_gemini.get_structured_logger") as mock_get:
        mock_logger = MagicMock()
        mock_get.return_value = mock_logger
        await asyncio.gather(
            adapter.validate({"stable_prefix": ["a"], "fresh_tail": []},
                             session_ctx={**SESSION_CTX, "firm_id": "firm-A"}),
            adapter.validate({"stable_prefix": ["b"], "fresh_tail": []}),
        )

    calls = mock_logger.log_text_ai_usage.call_args_list
    assert len(calls) == 2
    firm_ids = {c.kwargs["firm_id"] for c in calls}
    assert firm_ids == {"firm-A", None}


# ---------------------------------------------------------------------------
# TTS side: spellback / notice / intro
# ---------------------------------------------------------------------------

TTS_SESSION_CTX = {
    "firm_id": "firm-2",
    "employee_id": "emp-2",
    "link_jti": "jti-2",
    "kit_id": "w-7",
    "channel": "demo",
}


@pytest.mark.asyncio
async def test_synthesize_spellback_emits_tts_spellback_usage_event(monkeypatch):
    """synthesize_spellback() emits ONE
    log_tts_usage(usage_kind="tts_spellback") with a positive character_count
    and the route's claims-derived ids."""
    from backend.config import Settings
    from backend.services import spellback_tts

    def fake_synth(text, voice_name, locale, gain_db=None):
        return b"MP3BYTES"

    monkeypatch.setattr(spellback_tts, "_synthesize_sync", fake_synth)
    monkeypatch.setattr(
        spellback_tts, "resolve_spellback_voice",
        lambda settings, language_name=None: ("en-US-Chirp3-HD-Algieba", "en-US"),
    )

    with patch("backend.services.spellback_tts.get_structured_logger") as mock_get:
        mock_logger = MagicMock()
        mock_get.return_value = mock_logger
        await spellback_tts.synthesize_spellback(
            "Jose", Settings(), language_name="English",
            session_ctx=TTS_SESSION_CTX,
        )

    mock_logger.log_tts_usage.assert_called_once()
    kwargs = mock_logger.log_tts_usage.call_args.kwargs
    assert kwargs["usage_kind"] == "tts_spellback"
    assert kwargs["firm_id"] == "firm-2"
    assert kwargs["employee_id"] == "emp-2"
    assert kwargs["link_jti"] == "jti-2"
    assert kwargs["kit_id"] == "w-7"
    assert kwargs["channel"] == "demo"
    assert kwargs["form_session_id"] is None  # no WS session on an HTTP route
    assert kwargs["model"] == "en-US-Chirp3-HD-Algieba"
    assert kwargs["metadata"]["character_count"] > 0


@pytest.mark.asyncio
async def test_synthesize_notice_emits_tts_notice_usage_event(monkeypatch):
    """synthesize_notice() emits ONE log_tts_usage(usage_kind="tts_notice")
    on an actual synthesis."""
    from backend.config import Settings
    from backend.services import notice_tts

    def fake_synth(text, voice_name, locale, gain_db=None):
        return b"MP3BYTES"

    monkeypatch.setattr(notice_tts, "_synthesize_sync", fake_synth)
    monkeypatch.setattr(notice_tts, "_cache", {})
    monkeypatch.setattr(
        notice_tts, "resolve_spellback_voice",
        lambda settings, language_name=None: ("en-US-Chirp3-HD-Algieba", "en-US"),
    )

    with patch("backend.services.spellback_tts.get_structured_logger") as mock_get:
        mock_logger = MagicMock()
        mock_get.return_value = mock_logger
        await notice_tts.synthesize_notice(
            "English", notice_tts.NOTICE_SAVE_EARLY, Settings(),
            session_ctx=TTS_SESSION_CTX,
        )

    mock_logger.log_tts_usage.assert_called_once()
    kwargs = mock_logger.log_tts_usage.call_args.kwargs
    assert kwargs["usage_kind"] == "tts_notice"
    assert kwargs["firm_id"] == "firm-2"
    assert kwargs["metadata"]["character_count"] > 0


@pytest.mark.asyncio
async def test_synthesize_notice_cache_hit_emits_nothing(monkeypatch):
    """A cache hit calls Cloud TTS zero times, so it must emit ZERO usage
    events -- a usage event on a cache hit would record cost never billed."""
    from backend.config import Settings
    from backend.services import notice_tts

    calls = []

    def fake_synth(text, voice_name, locale, gain_db=None):
        calls.append(1)
        return b"MP3BYTES"

    monkeypatch.setattr(notice_tts, "_synthesize_sync", fake_synth)
    monkeypatch.setattr(notice_tts, "_cache", {})
    monkeypatch.setattr(
        notice_tts, "resolve_spellback_voice",
        lambda settings, language_name=None: ("en-US-Chirp3-HD-Algieba", "en-US"),
    )

    with patch("backend.services.spellback_tts.get_structured_logger") as mock_get:
        mock_logger = MagicMock()
        mock_get.return_value = mock_logger
        settings = Settings()
        await notice_tts.synthesize_notice(
            "English", notice_tts.NOTICE_SAVE_EARLY, settings,
            session_ctx=TTS_SESSION_CTX,
        )
        await notice_tts.synthesize_notice(
            "English", notice_tts.NOTICE_SAVE_EARLY, settings,
            session_ctx=TTS_SESSION_CTX,
        )

    assert len(calls) == 1  # ONE real synthesis
    assert mock_logger.log_tts_usage.call_count == 1  # ONE usage event


@pytest.mark.asyncio
async def test_synthesize_intro_emits_tts_intro_usage_event(monkeypatch):
    """synthesize_intro() emits ONE log_tts_usage(usage_kind="tts_intro")
    on an actual synthesis."""
    from backend.config import Settings
    from backend.services import intro_tts

    def fake_synth(text, voice_name, locale, gain_db=None):
        return b"MP3BYTES"

    monkeypatch.setattr(intro_tts, "_synthesize_sync", fake_synth)
    monkeypatch.setattr(intro_tts, "_cache", {})
    monkeypatch.setattr(
        intro_tts, "resolve_spellback_voice",
        lambda settings, language_name=None: ("en-US-Chirp3-HD-Algieba", "en-US"),
    )

    with patch("backend.services.spellback_tts.get_structured_logger") as mock_get:
        mock_logger = MagicMock()
        mock_get.return_value = mock_logger
        await intro_tts.synthesize_intro(
            "English", "I-90", Settings(), session_ctx=TTS_SESSION_CTX,
        )

    mock_logger.log_tts_usage.assert_called_once()
    kwargs = mock_logger.log_tts_usage.call_args.kwargs
    assert kwargs["usage_kind"] == "tts_intro"
    assert kwargs["firm_id"] == "firm-2"
    assert kwargs["metadata"]["character_count"] > 0


@pytest.mark.asyncio
async def test_tts_cost_is_null_while_the_chirp3_rate_is_unverified():
    """TODAY, TTS_PRICING_USD_PER_CHAR["Chirp3-HD"] is None (unverified --
    see test_pricing_tables.py's xfail(strict) TODO gate), so
    cost_estimate_usd is None rather than a computed number -- an explicit
    gap, not a guess. This pins the CURRENT, honest state; the moment an
    operator fills the rate in, the next test below starts asserting a
    positive number automatically (no rate is hand-typed here)."""
    from backend.config import TTS_PRICING_USD_PER_CHAR
    from backend.services.spellback_tts import _tts_cost_estimate_usd

    if TTS_PRICING_USD_PER_CHAR.get("Chirp3-HD") is not None:
        pytest.skip("Chirp3-HD rate has been filled in -- see the test below")
    cost, tier = _tts_cost_estimate_usd(10, "en-US-Chirp3-HD-Algieba")
    assert cost is None
    assert tier == "Chirp3-HD"


def test_tts_cost_computes_positive_once_a_rate_exists():
    """Cost computation ITSELF is correct and produces a positive number once
    a rate is present -- proven with a locally patched rate so this does not
    wait on the real Chirp3-HD rate being filled in, and does not require
    typing an unverified number into product code."""
    from backend.services import spellback_tts

    with patch.dict(
        spellback_tts.TTS_PRICING_USD_PER_CHAR, {"Chirp3-HD": 0.000016},
    ):
        cost, tier = spellback_tts._tts_cost_estimate_usd(
            100, "en-US-Chirp3-HD-Algieba"
        )
    assert tier == "Chirp3-HD"
    assert cost == pytest.approx(100 * 0.000016)
    assert cost > 0


def test_tts_cost_is_null_for_an_unrecognized_voice_tier():
    """A voice name that resolves to no known tier (empty locale-default
    voice, or a future non-Chirp3 tier) emits cost_estimate_usd=None rather
    than a guess."""
    from backend.services.spellback_tts import _tts_cost_estimate_usd

    cost, tier = _tts_cost_estimate_usd(10, "")
    assert cost is None
    assert tier is None
