"""Unit tests for TextAIGemini adapter (bd polyglot-pdf-jnjj.14).

Uses a stubbed genai.Client so no real API calls are made. Tests cover:
- happy path verdict shape
- implicit cache-hit logging
- fail-open on API exception
- fail-open on unparseable JSON
- fail-open when no client is configured
- fail-open on non-dict payload
- fail-open when conflicts is not a list
- field_count coerced to int before logging
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_response(text, cached_tokens=0, prompt_tokens=10, output_tokens=5):
    usage = SimpleNamespace(
        cached_content_token_count=cached_tokens,
        prompt_token_count=prompt_tokens,
        candidates_token_count=output_tokens,
    )
    return SimpleNamespace(text=text, usage_metadata=usage)


def _make_mock_client(response):
    """Build a mock genai.Client whose aio.models.generate_content returns response."""
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=response)
    return mock_client


@pytest.fixture
def adapter_with_client(monkeypatch):
    """TextAIGemini wired to a mock genai.Client."""
    from backend.adapters.text_ai_gemini import TextAIGemini

    def _make(response):
        mock_client = _make_mock_client(response)
        with patch("backend.adapters.text_ai_gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            adapter = TextAIGemini(api_key="test-key", vertexai=False)
        # Replace the constructed client directly so post-init mock still works.
        adapter._client = mock_client
        return adapter

    return _make


@pytest.mark.asyncio
async def test_validate_happy_path_no_conflicts(adapter_with_client):
    """Clean verdict returns {"conflicts": []}."""
    response = _make_response(text='{"conflicts":[]}', cached_tokens=0)
    adapter = adapter_with_client(response)
    payload = {
        "stable_prefix": ["catalog text"],
        "fresh_tail": ["values + query"],
        "field_count": 3,
    }
    result = await adapter.validate(payload)
    assert result == {"conflicts": []}


@pytest.mark.asyncio
async def test_validate_happy_path_with_conflicts(adapter_with_client):
    """Verdict with conflicts is returned as-is."""
    verdict = {
        "conflicts": [
            {"field_ids": ["addr_state", "addr_zip"], "reason": "mismatch"}
        ]
    }
    response = _make_response(text=json.dumps(verdict), cached_tokens=0)
    adapter = adapter_with_client(response)
    result = await adapter.validate({"stable_prefix": [], "fresh_tail": []})
    assert result == verdict


@pytest.mark.asyncio
async def test_validate_cache_hit_logged(adapter_with_client):
    """cache_hit=True is emitted in structured logs when cached_tokens > 0."""
    import structlog.testing

    response = _make_response(text='{"conflicts":[]}', cached_tokens=512)
    adapter = adapter_with_client(response)
    with structlog.testing.capture_logs() as logs:
        await adapter.validate({"stable_prefix": ["catalog"], "fresh_tail": ["q"]})
    usage_events = [e for e in logs if e.get("event") == "text_ai_usage"]
    assert any(e.get("cache_hit") is True for e in usage_events), (
        f"Expected cache_hit=True in text_ai_usage log; got: {logs}"
    )


@pytest.mark.asyncio
async def test_validate_fail_open_on_exception(adapter_with_client):
    """Any API exception returns fail-open {"conflicts": []}."""
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=Exception("network error")
    )
    from backend.adapters.text_ai_gemini import TextAIGemini
    adapter = TextAIGemini(api_key="test-key", vertexai=False)
    adapter._client = mock_client

    result = await adapter.validate({"stable_prefix": [], "fresh_tail": []})
    assert result == {"conflicts": []}


@pytest.mark.asyncio
async def test_validate_fail_open_on_bad_json(adapter_with_client):
    """Unparseable response returns fail-open {"conflicts": []}."""
    response = _make_response(text="not valid json at all", cached_tokens=0)
    adapter = adapter_with_client(response)
    result = await adapter.validate({"stable_prefix": [], "fresh_tail": []})
    assert result == {"conflicts": []}


@pytest.mark.asyncio
async def test_validate_fail_open_when_no_client():
    """No configured client (test construction) returns fail-open."""
    from backend.adapters.text_ai_gemini import TextAIGemini

    with patch("backend.adapters.text_ai_gemini.genai") as mock_genai:
        # Simulate genai.Client construction raising (test/stub environment)
        mock_genai.Client.side_effect = Exception("no credentials")
        adapter = TextAIGemini(api_key=None, vertexai=False)

    assert adapter._client is None
    result = await adapter.validate({"stable_prefix": [], "fresh_tail": []})
    assert result == {"conflicts": []}


@pytest.mark.asyncio
async def test_ask_empty_context_fails_open():
    """ask() is implemented now (bd polyglot-pdf-jnjj.45b): an empty context (no
    schema to ground the answer in) fail-opens to ("", [], True) rather than
    raising. The full implemented behavior is covered by the test_ask_* block
    below."""
    from backend.adapters.text_ai_gemini import TextAIGemini

    with patch("backend.adapters.text_ai_gemini.genai"):
        adapter = TextAIGemini(api_key="test-key", vertexai=False)

    assert await adapter.ask("what is the zip code?", {}) == ("", [], True)


@pytest.mark.asyncio
async def test_validate_fail_open_on_non_dict_payload(adapter_with_client):
    """Non-dict payload (None, string, etc.) returns fail-open {"conflicts": []}."""
    response = _make_response(text='{"conflicts":[]}', cached_tokens=0)
    adapter = adapter_with_client(response)
    result = await adapter.validate(None)
    assert result == {"conflicts": []}


@pytest.mark.asyncio
async def test_validate_fail_open_on_non_list_conflicts(adapter_with_client):
    """Conflicts field that is not a list returns fail-open {"conflicts": []}."""
    response = _make_response(text='{"conflicts": "oops"}', cached_tokens=0)
    adapter = adapter_with_client(response)
    result = await adapter.validate({"stable_prefix": [], "fresh_tail": []})
    assert result == {"conflicts": []}


@pytest.mark.asyncio
async def test_validate_field_count_coerced_to_int(adapter_with_client):
    """field_count from payload is coerced to int before logging."""
    import structlog.testing

    response = _make_response(text='{"conflicts":[]}', cached_tokens=0)
    adapter = adapter_with_client(response)
    with structlog.testing.capture_logs() as logs:
        await adapter.validate({
            "stable_prefix": [],
            "fresh_tail": [],
            "field_count": "5",
        })
    complete_events = [e for e in logs if e.get("event") == "text_ai_validate_complete"]
    assert complete_events, f"Expected text_ai_validate_complete log; got: {logs}"
    assert complete_events[0].get("field_count") == 5


@pytest.mark.asyncio
async def test_validate_fail_open_on_bad_field_count(adapter_with_client):
    """Non-numeric field_count (e.g. empty string) does not raise; validate returns normally."""
    response = _make_response(text='{"conflicts":[]}', cached_tokens=0)
    adapter = adapter_with_client(response)
    result = await adapter.validate({
        "stable_prefix": [],
        "fresh_tail": [],
        "field_count": "",
    })
    assert result == {"conflicts": []}


@pytest.mark.asyncio
async def test_validate_fail_open_on_non_dict_conflict_items(adapter_with_client):
    """Conflicts list with non-dict items returns fail-open {"conflicts": []}."""
    response = _make_response(text='{"conflicts": ["not a dict"]}', cached_tokens=0)
    adapter = adapter_with_client(response)
    result = await adapter.validate({"stable_prefix": [], "fresh_tail": []})
    assert result == {"conflicts": []}


def test_get_text_ai_wiring():
    """get_text_ai() resolves to a TextAIGemini without import error."""
    from backend.dependencies import get_text_ai
    from backend.adapters.text_ai_gemini import TextAIGemini
    from backend.config import Settings

    settings = Settings()
    with patch("backend.adapters.text_ai_gemini.genai"):
        result = get_text_ai(settings)

    assert isinstance(result, TextAIGemini)


# --------------------------------------------------------------------------- #
# ask() -- the secretary path (bd polyglot-pdf-jnjj.45b).
# --------------------------------------------------------------------------- #

# A tiny 2-field schema is enough to exercise the catalog/tail rendering and the
# byte-stable-prefix invariant without depending on the real I-90 file.
_ASK_SCHEMA = {
    "fields": [
        {"id": "f_first", "spoken_name": "first name", "name": "First Name",
         "type": "text", "help": {"instructions": "Your given name."}},
        {"id": "f_last", "spoken_name": "last name", "name": "Last Name",
         "type": "text", "help": {"instructions": "Your family name."}},
    ],
    "sections": [{"id": "s1", "label": "Names", "fields": ["f_first", "f_last"]}],
    "parts": [{"id": "p1", "label": "Part 1", "section_ids": ["s1"]}],
}


@pytest.mark.asyncio
async def test_ask_returns_prose_answer(adapter_with_client):
    """ask() returns the secretary's `answer` prose from the JSON response, plus the
    resolved `sources` list (bd polyglot-pdf-2af7/3vby)."""
    response = _make_response(
        text='{"answer": "Their first name is Ada.", "sourced_from": ["f_first"]}')
    adapter = adapter_with_client(response)
    answer, sources, resolved = await adapter.ask("what is their first name?", {
        "schema": _ASK_SCHEMA,
        "field_values": {"f_first": "Ada"},
        "shown_map": {"f_first": True, "f_last": True},
    })
    assert answer == "Their first name is Ada."
    assert sources == [{"field_id": "f_first", "spoken_name": "first name"}]
    assert resolved is True


@pytest.mark.asyncio
async def test_ask_returns_resolved_false_on_pushback(adapter_with_client):
    """When the secretary deliberately cannot identify a requested navigation
    field, it sets "resolved": false; ask() must surface that as the third
    tuple element (answer preserved, sources empty) rather than fail-opening
    (bd polyglot-pdf-y76q)."""
    response = _make_response(text=json.dumps({
        "answer": "I could not find a 12-digit government ID field",
        "sourced_from": [],
        "resolved": False,
    }))
    adapter = adapter_with_client(response)
    out = await adapter.ask("switch to the 12-digit government id field", {
        "schema": _ASK_SCHEMA,
        "field_values": {},
        "shown_map": {},
    })
    assert out == (
        "I could not find a 12-digit government ID field", [], False,
    )


@pytest.mark.asyncio
async def test_ask_sources_dedupe_cap_and_skip_unknown_ids(adapter_with_client):
    """sourced_from ids not present in the schema are dropped; duplicates are
    de-duped (order preserved); the resolved list is capped at 8 entries."""
    # 10 duplicate/unknown ids referencing only the 2 real schema fields, plus a
    # ghost id that does not exist in the schema.
    sourced_from = (
        ["f_first", "f_first", "f_ghost", "f_last"]
        + ["f_first"] * 10  # excess duplicates -- must not blow the cap by count
    )
    response = _make_response(
        text=json.dumps({"answer": "ok", "sourced_from": sourced_from}))
    adapter = adapter_with_client(response)
    answer, sources, resolved = await adapter.ask("q", {
        "schema": _ASK_SCHEMA,
        "field_values": {},
        "shown_map": {},
    })
    assert answer == "ok"
    # Only the two real, de-duped fields resolve -- order preserved, no ghost id.
    assert sources == [
        {"field_id": "f_first", "spoken_name": "first name"},
        {"field_id": "f_last", "spoken_name": "last name"},
    ]
    assert len(sources) <= 8
    assert resolved is True


@pytest.mark.asyncio
async def test_ask_sources_truncates_to_eight(adapter_with_client):
    """When the secretary sources MORE than 8 distinct real fields, the resolved
    list truncates to the first 8 in order (the cap actually fires)."""
    schema = {
        "fields": [
            {"id": f"f{i}", "spoken_name": f"field {i}", "type": "text"}
            for i in range(12)
        ],
    }
    sourced_from = [f"f{i}" for i in range(12)]  # 12 distinct real fields
    response = _make_response(
        text=json.dumps({"answer": "ok", "sourced_from": sourced_from}))
    adapter = adapter_with_client(response)
    _answer, sources, _resolved = await adapter.ask("q", {
        "schema": schema, "field_values": {}, "shown_map": {},
    })
    assert len(sources) == 8
    assert [s["field_id"] for s in sources] == [f"f{i}" for i in range(8)]


@pytest.mark.asyncio
async def test_ask_stable_prefix_is_byte_identical_across_value_changes(adapter_with_client):
    """The cache precondition: the stable_prefix (SI + value-free catalog) sent as
    contents[0] is BYTE-IDENTICAL across two ask() calls whose field VALUES differ
    -- only the appended fresh tail (contents[1]) changes. If this breaks, Gemini's
    implicit cache stops firing (bd polyglot-pdf-jnjj.45, maintainer 2026-06-27)."""
    response = _make_response(text='{"answer": "ok", "sourced_from": []}')
    adapter = adapter_with_client(response)
    gen = adapter._client.aio.models.generate_content

    await adapter.ask("q1", {
        "schema": _ASK_SCHEMA,
        "field_values": {"f_first": "Ada"},
        "shown_map": {"f_first": True},
    })
    contents_1 = gen.call_args.kwargs["contents"]

    await adapter.ask("a DIFFERENT question", {
        "schema": _ASK_SCHEMA,
        "field_values": {"f_first": "Grace", "f_last": "Hopper"},
        "shown_map": {"f_first": True, "f_last": False},
    })
    contents_2 = gen.call_args.kwargs["contents"]

    # contents[0] = stable prefix (SI + catalog); MUST be byte-identical.
    assert contents_1[0] == contents_2[0], "stable prefix drifted -> cache breaks"
    # contents[1] = fresh tail (values + query); SHOULD differ (values changed).
    assert contents_1[1] != contents_2[1], "fresh tail did not change with values"


@pytest.mark.asyncio
async def test_ask_logs_no_pii(adapter_with_client):
    """ask() must never log the query, the rendered values/context, or the answer
    prose -- only ids/counts/lengths (validation-delegation contract 6)."""
    secret_query = "SECRET_QUERY_TOKEN"
    secret_value = "SECRET_VALUE_TOKEN"
    secret_answer = "SECRET_ANSWER_TOKEN"
    response = _make_response(
        text='{"answer": "%s", "sourced_from": ["f_first"]}' % secret_answer)
    adapter = adapter_with_client(response)

    logged = []
    # Capture every structured-log call (event + kwargs) made during ask().
    for level in ("info", "warning", "error"):
        setattr(adapter._log, level,
                (lambda *a, **k: logged.append((a, k))))

    await adapter.ask(secret_query, {
        "schema": _ASK_SCHEMA,
        "field_values": {"f_first": secret_value},
        "shown_map": {"f_first": True},
    })

    # Guard against a vacuous pass: if the setattr patch failed to shadow the
    # bound logger's methods, `logged` would be empty and the PII checks below
    # would pass without ever inspecting a real log call (fresh-eyes PR finding).
    # ask() emits text_ai_ask_complete on the happy path, so at least one call
    # MUST have been captured.
    assert logged, "no log calls captured -- the PII check would pass vacuously"

    blob = repr(logged)
    assert secret_query not in blob
    assert secret_value not in blob
    assert secret_answer not in blob


@pytest.mark.asyncio
async def test_ask_fail_open_on_api_error(adapter_with_client):
    """An API exception fail-opens to ("", [], True) so the principal asks the
    user directly."""
    response = _make_response(text='{"answer": "x", "sourced_from": []}')
    adapter = adapter_with_client(response)
    adapter._client.aio.models.generate_content = AsyncMock(
        side_effect=RuntimeError("boom"))
    out = await adapter.ask("q", {"schema": _ASK_SCHEMA, "field_values": {},
                                  "shown_map": {}})
    assert out == ("", [], True)


@pytest.mark.asyncio
async def test_ask_fail_open_on_bad_json(adapter_with_client):
    """Unparseable JSON fail-opens to ("", [], True)."""
    response = _make_response(text="not json at all")
    adapter = adapter_with_client(response)
    out = await adapter.ask("q", {"schema": _ASK_SCHEMA, "field_values": {},
                                  "shown_map": {}})
    assert out == ("", [], True)


@pytest.mark.asyncio
async def test_ask_fail_open_on_missing_schema(adapter_with_client):
    """No catalog to ground in -> fail-open ("", [], True) (cannot retrieve)."""
    response = _make_response(text='{"answer": "x", "sourced_from": []}')
    adapter = adapter_with_client(response)
    out = await adapter.ask("q", {"schema": None, "field_values": {}})
    assert out == ("", [], True)


@pytest.mark.asyncio
async def test_ask_fail_open_on_no_client():
    """No configured client -> fail-open ("", [], True) without raising."""
    from backend.adapters.text_ai_gemini import TextAIGemini
    with patch("backend.adapters.text_ai_gemini.genai"):
        adapter = TextAIGemini(api_key="k", vertexai=False)
    adapter._client = None
    out = await adapter.ask("q", {"schema": _ASK_SCHEMA})
    assert out == ("", [], True)


# --------------------------------------------------------------------------- #
# W6 (bd polyglot-pdf-gbus): the optional bounded thinking_config for the
# 2.5-pro whole-form validator. Wired only when thinking_budget is set; the lite
# path (budget None) sends NO thinking_config (byte-stable prefix preserved).
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_thinking_budget_wires_thinking_config():
    from backend.adapters.text_ai_gemini import TextAIGemini
    response = _make_response(text='{"conflicts":[]}')
    mock_client = _make_mock_client(response)
    with patch("backend.adapters.text_ai_gemini.genai") as mock_genai:
        mock_genai.Client.return_value = mock_client
        adapter = TextAIGemini(api_key="k", vertexai=False,
                               model="gemini-2.5-pro", thinking_budget=512)
    adapter._client = mock_client
    await adapter.validate({"stable_prefix": ["si"], "fresh_tail": ["state"]})
    # The config passed to generate_content carries a thinking_config with budget 512.
    call = mock_client.aio.models.generate_content.await_args
    config = call.kwargs["config"]
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_budget == 512


@pytest.mark.asyncio
async def test_no_thinking_budget_sends_no_thinking_config():
    from backend.adapters.text_ai_gemini import TextAIGemini
    response = _make_response(text='{"conflicts":[]}')
    mock_client = _make_mock_client(response)
    with patch("backend.adapters.text_ai_gemini.genai") as mock_genai:
        mock_genai.Client.return_value = mock_client
        adapter = TextAIGemini(api_key="k", vertexai=False)  # lite default, no budget
    adapter._client = mock_client
    await adapter.validate({"stable_prefix": ["si"], "fresh_tail": ["state"]})
    call = mock_client.aio.models.generate_content.await_args
    config = call.kwargs["config"]
    # No thinking_config on the lite path (attribute is None / unset).
    assert getattr(config, "thinking_config", None) is None


# --- translate_labels (bd polyglot-pdf-ow1e) ----------------------------------

@pytest.mark.asyncio
async def test_translate_labels_happy_path_sets_temperature_and_json(adapter_with_client):
    response = _make_response(text='{"Male": "Masculino", "Female": "Femenino"}')
    adapter = adapter_with_client(response)
    result = await adapter.translate_labels(["Male", "Female"], "Spanish", "es-US")
    assert result == {"Male": "Masculino", "Female": "Femenino"}

    call = adapter._client.aio.models.generate_content.await_args
    config = call.kwargs["config"]
    # Determinism levers: temperature 0.0 (deterministic legal translation,
    # bd polyglot-pdf-ch7j) + JSON mime; name AND code in the prompt.
    assert config.temperature == pytest.approx(0.0)
    assert config.response_mime_type == "application/json"
    prompt = call.kwargs["contents"][0]
    assert "Spanish (es-US)" in prompt
    assert "UNMISTAKABLY in Spanish" in prompt


@pytest.mark.asyncio
async def test_translate_labels_drops_unrequested_and_non_str_entries(adapter_with_client):
    response = _make_response(
        text='{"Male": "Masculino", "Ghost": "X", "Female": 3, "Yes": "  "}')
    adapter = adapter_with_client(response)
    result = await adapter.translate_labels(
        ["Male", "Female", "Yes"], "Spanish", "es-US")
    # Not-requested keys, non-str values, and blank values are dropped.
    assert result == {"Male": "Masculino"}


@pytest.mark.asyncio
async def test_translate_labels_none_on_bad_json(adapter_with_client):
    adapter = adapter_with_client(_make_response(text="not json"))
    assert await adapter.translate_labels(["Male"], "Spanish", "es-US") is None


@pytest.mark.asyncio
async def test_translate_labels_none_on_non_dict_shape(adapter_with_client):
    adapter = adapter_with_client(_make_response(text='["Masculino"]'))
    assert await adapter.translate_labels(["Male"], "Spanish", "es-US") is None


@pytest.mark.asyncio
async def test_translate_labels_none_on_api_error(adapter_with_client):
    adapter = adapter_with_client(_make_response(text="{}"))
    adapter._client.aio.models.generate_content = AsyncMock(
        side_effect=RuntimeError("boom"))
    assert await adapter.translate_labels(["Male"], "Spanish", "es-US") is None


@pytest.mark.asyncio
async def test_translate_labels_none_when_no_client():
    from backend.adapters.text_ai_gemini import TextAIGemini
    with patch("backend.adapters.text_ai_gemini.genai") as mock_genai:
        mock_genai.Client.side_effect = Exception("no creds")
        adapter = TextAIGemini(api_key=None, vertexai=False)
    assert await adapter.translate_labels(["Male"], "Spanish", "es-US") is None


@pytest.mark.asyncio
async def test_translate_labels_empty_input_returns_empty_without_call(adapter_with_client):
    adapter = adapter_with_client(_make_response(text="{}"))
    assert await adapter.translate_labels([], "Spanish", "es-US") == {}
    adapter._client.aio.models.generate_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_sends_no_temperature(adapter_with_client):
    """The validator/secretary requests must stay byte-unchanged (implicit-cache
    prefix stability): the new temperature param is None by default and must not
    appear in their config."""
    adapter = adapter_with_client(_make_response(text='{"conflicts":[]}'))
    await adapter.validate({"stable_prefix": ["si"], "fresh_tail": ["state"]})
    call = adapter._client.aio.models.generate_content.await_args
    assert getattr(call.kwargs["config"], "temperature", None) is None


# --- verify-loop methods (bd polyglot-pdf-9ikj) -------------------------------

_GLOSSARY_CONTEXT = {
    "register": "Formal 'usted' throughout.",
    "pins": {"head of household": "cabeza de familia"},
    "do_not_translate": ["USCIS"],
    "digits_policy": "ASCII digits only.",
}


@pytest.mark.asyncio
async def test_back_translate_happy_path_and_filtering(adapter_with_client):
    response = _make_response(
        text='{"translations": {"a": "Name", "ghost": "X", "b": 3}}')
    adapter = adapter_with_client(response)
    result = await adapter.back_translate(
        {"a": "Nombre", "b": "Apellido", "empty": "  "}, "Spanish", "es-US")
    # Unknown ids and non-str values dropped; empty inputs never requested.
    assert result == {"a": "Name"}
    call = adapter._client.aio.models.generate_content.await_args
    assert call.kwargs["config"].temperature == pytest.approx(0.0)
    prompt = call.kwargs["contents"][0]
    assert "Spanish (es-US)" in prompt and "Nombre" in prompt
    assert "empty" not in json.loads(
        prompt.split("Strings:\n", 1)[1])


@pytest.mark.asyncio
async def test_back_translate_fail_open_paths(adapter_with_client):
    adapter = adapter_with_client(_make_response(text="not json"))
    assert await adapter.back_translate({"a": "X"}, "Spanish", "es-US") is None
    adapter = adapter_with_client(_make_response(text='{"no": 1}'))
    assert await adapter.back_translate({"a": "X"}, "Spanish", "es-US") is None
    adapter = adapter_with_client(_make_response(text="{}"))
    assert await adapter.back_translate({}, "Spanish", "es-US") == {}
    adapter._client.aio.models.generate_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_judge_translations_verdicts_and_prompt(adapter_with_client):
    response = _make_response(text=json.dumps({"verdicts": [
        {"id": "a", "drift": True, "reason": "negation lost"},
        {"id": "b", "drift": False},
        {"id": "ghost", "drift": True, "reason": "x"},
    ]}))
    adapter = adapter_with_client(response)
    items = [
        {"id": "a", "en": "Do not file", "translation": "Presente",
         "back_translation": "File it"},
        {"id": "b", "en": "Name", "translation": "Nombre",
         "back_translation": "Name"},
    ]
    result = await adapter.judge_translations(
        items, "Spanish", "es-US", glossary_context=_GLOSSARY_CONTEXT)
    assert result == {
        "a": {"drift": True, "reason": "negation lost"},
        "b": {"drift": False, "reason": ""},
    }
    call = adapter._client.aio.models.generate_content.await_args
    assert call.kwargs["config"].temperature == pytest.approx(0.0)
    prompt = call.kwargs["contents"][0]
    # The V1-hardened rules block + glossary injection reach the prompt.
    assert "SUPPORTING evidence ONLY" in prompt
    assert "Never flag a rendering you would yourself propose" in prompt
    assert "Formal 'usted' throughout." in prompt
    assert "cabeza de familia" in prompt
    assert "USCIS" in prompt


@pytest.mark.asyncio
async def test_judge_translations_fail_open_paths(adapter_with_client):
    items = [{"id": "a", "en": "X", "translation": "Y",
              "back_translation": ""}]
    adapter = adapter_with_client(_make_response(text="not json"))
    assert await adapter.judge_translations(items, "Spanish", "es") is None
    adapter = adapter_with_client(_make_response(text='{"verdicts": {}}'))
    assert await adapter.judge_translations(items, "Spanish", "es") is None
    adapter = adapter_with_client(_make_response(text="{}"))
    assert await adapter.judge_translations([], "Spanish", "es") == {}
    adapter._client.aio.models.generate_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_rectify_translations_corrections_and_prompt(adapter_with_client):
    response = _make_response(text=json.dumps({"corrections": {
        "a": "  No presente  ", "ghost": "X", "b": "",
    }}))
    adapter = adapter_with_client(response)
    items = [
        {"id": "a", "en": "Do not file", "translation": "Presente",
         "back_translation": "File it", "problem": "negation lost"},
        {"id": "b", "en": "Name", "translation": "Nombre",
         "back_translation": "", "problem": "x"},
    ]
    result = await adapter.rectify_translations(
        items, "Spanish", "es-US", glossary_context=_GLOSSARY_CONTEXT)
    # Trimmed; unknown ids and empty corrections dropped.
    assert result == {"a": "No presente"}
    prompt = adapter._client.aio.models.generate_content \
        .await_args.kwargs["contents"][0]
    assert "FIXES the stated problem" in prompt
    assert "negation lost" in prompt
    assert "Formal 'usted' throughout." in prompt


@pytest.mark.asyncio
async def test_rectify_translations_fail_open_paths(adapter_with_client):
    items = [{"id": "a", "en": "X", "translation": "Y",
              "back_translation": "", "problem": "p"}]
    adapter = adapter_with_client(_make_response(text="not json"))
    assert await adapter.rectify_translations(items, "Spanish", "es") is None
    adapter = adapter_with_client(_make_response(text='{"corrections": []}'))
    assert await adapter.rectify_translations(items, "Spanish", "es") is None
    adapter = adapter_with_client(_make_response(text="{}"))
    assert await adapter.rectify_translations([], "Spanish", "es") == {}
    adapter._client.aio.models.generate_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_methods_none_when_no_client():
    from backend.adapters.text_ai_gemini import TextAIGemini
    with patch("backend.adapters.text_ai_gemini.genai") as mock_genai:
        mock_genai.Client.side_effect = Exception("no creds")
        adapter = TextAIGemini(api_key=None, vertexai=False)
    assert await adapter.back_translate({"a": "X"}, "Spanish", "es") is None
    assert await adapter.judge_translations(
        [{"id": "a"}], "Spanish", "es") is None
    assert await adapter.rectify_translations(
        [{"id": "a"}], "Spanish", "es") is None


def test_judge_rules_carry_the_language_lock_framing():
    """bd polyglot-pdf-g0ka: the judge prompt is reframed to the language-
    lock bar (memory translations-are-drift-anchors-not-display) -- the
    strings' consumer is the voice model, the bar is intelligible-and-in-
    language, and wrong/mixed language leads the DRIFT list. The V1-
    evidence clauses (anti-anchoring, never-flag-own-proposal) must
    survive the rewrite."""
    from backend.adapters.text_ai_gemini import TextAIGemini

    rules = TextAIGemini._JUDGE_RULES
    # Purpose + bar.
    assert "VOICE MODEL" in rules
    assert "INTELLIGIBLE AND IN-LANGUAGE" in rules
    # Reweighted NOT-drift: imperfect word choice is explicitly tolerated.
    assert "imperfect-but-intelligible word choice" in rules
    # Reprioritized DRIFT: wrong/mixed language leads the list.
    assert "WRONG LANGUAGE" in rules
    assert rules.index("WRONG LANGUAGE") < rules.index("inverted meaning")
    # V1-evidence clauses survive (zh-g07 anchoring, zh-g11 own-proposal +
    # conventional-rendering).
    assert "NEVER flag a translation because its back_translation" in rules
    assert "Never flag a rendering you would yourself propose" in rules
    assert "conventional rendering as under-specific" in rules
    # NOT-drift conventions retained.
    assert "proper nouns, codes and form numbers kept in English" in rules
    assert "official glossary" in rules
    # DRIFT criteria retained: register, negation, option-mismatch,
    # form-domain terms, numbers.
    assert "register rule" in rules
    assert "especially negation" in rules
    assert "does not correspond to its English option" in rules
    assert "different form-domain term" in rules
    assert "numbers or identifiers that disagree" in rules


def test_probe_judges_with_the_production_rules():
    """The V1 probe must exercise the SHIPPED judge prompt -- a stale local
    copy silently measured the old prompt (bd g0ka fresh-eyes gap). The
    probe now imports the adapter constant; pin the aliasing so the copies
    can never diverge again."""
    import importlib.util
    from pathlib import Path

    from backend.adapters.text_ai_gemini import TextAIGemini

    probe_path = (Path(__file__).resolve().parents[3] / "scripts" / "spikes"
                  / "translation_gate_probe.py")
    spec = importlib.util.spec_from_file_location("tg_probe", probe_path)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    assert probe._JUDGE_RULES is TextAIGemini._JUDGE_RULES


def test_vertex_text_client_is_built_at_the_global_location():
    """The 3.x lite models are served on Vertex ONLY at `global` (404 at
    us-central1, endpoint-verified 2026-10-21, bd polyglot-pdf-bd1zs). A text
    client built at a regional location would 404 the default model on every
    call -- and fail the whole lite chain over to fail-open, silently. Pinned
    at the SDK boundary, through the same construction every call site uses
    (no explicit location)."""
    from backend.adapters.text_ai_gemini import TextAIGemini

    with patch("backend.adapters.text_ai_gemini.genai") as mock_genai:
        TextAIGemini(vertexai=True, project="p")
    assert mock_genai.Client.call_args.kwargs["location"] == "global"


def test_default_text_model_is_the_3p1_lite_tier():
    from backend.adapters.text_ai_gemini import TextAIGemini
    from backend.config import Settings

    assert Settings().MODEL_LABELING == "gemini-3.1-flash-lite"
    with patch("backend.adapters.text_ai_gemini.genai"):
        a = TextAIGemini(vertexai=True, project="p")
    assert a._model_chain[0] == "gemini-3.1-flash-lite"
    # The outage fallback stays in the lite tier and never repeats the primary.
    assert all("lite" in m for m in a._model_chain)
    assert a._model_chain.count("gemini-3.1-flash-lite") == 1
