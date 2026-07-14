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
    schema to ground the answer in) fail-opens to "" rather than raising. The
    full implemented behavior is covered by the test_ask_* block below."""
    from backend.adapters.text_ai_gemini import TextAIGemini

    with patch("backend.adapters.text_ai_gemini.genai"):
        adapter = TextAIGemini(api_key="test-key", vertexai=False)

    assert await adapter.ask("what is the zip code?", {}) == ""


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
    """ask() returns the secretary's `answer` prose from the JSON response."""
    response = _make_response(
        text='{"answer": "Their first name is Ada.", "sourced_from": ["f_first"]}')
    adapter = adapter_with_client(response)
    out = await adapter.ask("what is their first name?", {
        "schema": _ASK_SCHEMA,
        "field_values": {"f_first": "Ada"},
        "shown_map": {"f_first": True, "f_last": True},
    })
    assert out == "Their first name is Ada."


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
    """An API exception fail-opens to "" so the principal asks the user directly."""
    response = _make_response(text='{"answer": "x", "sourced_from": []}')
    adapter = adapter_with_client(response)
    adapter._client.aio.models.generate_content = AsyncMock(
        side_effect=RuntimeError("boom"))
    out = await adapter.ask("q", {"schema": _ASK_SCHEMA, "field_values": {},
                                  "shown_map": {}})
    assert out == ""


@pytest.mark.asyncio
async def test_ask_fail_open_on_bad_json(adapter_with_client):
    """Unparseable JSON fail-opens to ""."""
    response = _make_response(text="not json at all")
    adapter = adapter_with_client(response)
    out = await adapter.ask("q", {"schema": _ASK_SCHEMA, "field_values": {},
                                  "shown_map": {}})
    assert out == ""


@pytest.mark.asyncio
async def test_ask_fail_open_on_missing_schema(adapter_with_client):
    """No catalog to ground in -> fail-open "" (cannot retrieve)."""
    response = _make_response(text='{"answer": "x", "sourced_from": []}')
    adapter = adapter_with_client(response)
    out = await adapter.ask("q", {"schema": None, "field_values": {}})
    assert out == ""


@pytest.mark.asyncio
async def test_ask_fail_open_on_no_client():
    """No configured client -> fail-open "" without raising."""
    from backend.adapters.text_ai_gemini import TextAIGemini
    with patch("backend.adapters.text_ai_gemini.genai"):
        adapter = TextAIGemini(api_key="k", vertexai=False)
    adapter._client = None
    out = await adapter.ask("q", {"schema": _ASK_SCHEMA})
    assert out == ""


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
