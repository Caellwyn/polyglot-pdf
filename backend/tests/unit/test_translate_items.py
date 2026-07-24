"""Unit tests for TextAIGemini.translate_items (bd polyglot-pdf-ch7j).

The context-carrying successor to translate_labels' bare string list: pins
the payload structure (kinds, option-sets-as-units, parent_question), the
glossary/register prompt injection, temperature 0.0, the ambiguity
self-flag, and every fail-open path. Stubbed genai.Client -- zero live
calls. Non-ASCII fixture strings use escapes (CLAUDE.md scar #6).
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_response(text):
    usage = SimpleNamespace(
        cached_content_token_count=0,
        prompt_token_count=10,
        candidates_token_count=5,
    )
    return SimpleNamespace(text=text, usage_metadata=usage)


def _make_mock_client(response):
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=response)
    return mock_client


@pytest.fixture
def adapter_with_client():
    from backend.adapters.text_ai_gemini import TextAIGemini

    def _make(response):
        mock_client = _make_mock_client(response)
        with patch("backend.adapters.text_ai_gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            adapter = TextAIGemini(api_key="test-key", vertexai=False)
        adapter._client = mock_client
        return adapter

    return _make


_ITEMS = [
    {"id": "f1", "kind": "field-name", "text": "Head of household"},
    {"id": "s1", "kind": "section-title", "text": "Filing Status"},
    {
        "id": "set1",
        "kind": "option-set",
        "parent_question": "Filing status",
        "options": ["Single", "Married filing jointly"],
    },
]

_GLOSSARY_CONTEXT = {
    "register": "Formal 'usted' throughout; never 'tu'.",
    "pins": {"head of household": "cabeza de familia"},
    "do_not_translate": ["USCIS", "ITIN"],
    "digits_policy": "Always render numerals with ASCII digits 0-9.",
}

_GOOD_RESPONSE = json.dumps({
    "items": {
        "f1": {"translation": "Cabeza de familia"},
        "s1": {"translation": "Estado civil"},
        "set1": {"options": {
            "Single": "Soltero(a)",
            "Married filing jointly":
                "Casado con presentacion conjunta",
        }},
    },
    "ambiguous": ["s1"],
})


@pytest.mark.asyncio
async def test_happy_path_shape_and_config(adapter_with_client):
    adapter = adapter_with_client(_make_response(_GOOD_RESPONSE))
    result = await adapter.translate_items(
        _ITEMS, "Spanish", "es-US",
        form_name="Form 1040", glossary_context=_GLOSSARY_CONTEXT,
    )
    assert result == {
        "items": {
            "f1": {"translation": "Cabeza de familia"},
            "s1": {"translation": "Estado civil"},
            "set1": {"options": {
                "Single": "Soltero(a)",
                "Married filing jointly":
                    "Casado con presentacion conjunta",
            }},
        },
        "ambiguous": ["s1"],
    }
    call = adapter._client.aio.models.generate_content.await_args
    config = call.kwargs["config"]
    assert config.temperature == pytest.approx(0.0)
    assert config.response_mime_type == "application/json"


@pytest.mark.asyncio
async def test_prompt_carries_context_and_glossary(adapter_with_client):
    """The context payload is the whole point: language name+code, form
    name, register line, pins, DNT list, digits policy, and the structured
    items (incl. parent_question) all reach the prompt; items ride as JSON
    data."""
    adapter = adapter_with_client(_make_response(_GOOD_RESPONSE))
    await adapter.translate_items(
        _ITEMS, "Spanish", "es-US",
        form_name="Form 1040", glossary_context=_GLOSSARY_CONTEXT,
    )
    prompt = adapter._client.aio.models.generate_content.await_args \
        .kwargs["contents"][0]
    assert "Spanish (es-US)" in prompt
    assert "UNMISTAKABLY in Spanish" in prompt
    assert json.dumps("Form 1040") in prompt
    assert "Formal 'usted' throughout" in prompt
    assert "cabeza de familia" in prompt          # pins injected
    assert "USCIS" in prompt                      # DNT injected
    assert "ASCII digits 0-9" in prompt           # digits policy injected
    # The structured items enter as JSON data (hygiene rule N1), option set
    # intact as a unit with its parent question.
    payload = json.dumps([
        {"id": "f1", "kind": "field-name", "text": "Head of household"},
        {"id": "s1", "kind": "section-title", "text": "Filing Status"},
        {"id": "set1", "kind": "option-set",
         "options": ["Single", "Married filing jointly"],
         "parent_question": "Filing status"},
    ], ensure_ascii=False)
    assert payload in prompt


@pytest.mark.asyncio
async def test_works_without_form_name_or_glossary(adapter_with_client):
    """glossary_context/form_name are optional (fail-open when the glossary
    file is unavailable): no crash, no stray sections in the prompt."""
    adapter = adapter_with_client(_make_response(_GOOD_RESPONSE))
    result = await adapter.translate_items(_ITEMS, "Spanish", "es-US")
    assert result is not None and "f1" in result["items"]
    prompt = adapter._client.aio.models.generate_content.await_args \
        .kwargs["contents"][0]
    assert "Register:" not in prompt
    assert "Official terminology" not in prompt


@pytest.mark.asyncio
async def test_drops_unknown_ids_options_and_empty_values(adapter_with_client):
    response = json.dumps({
        "items": {
            "f1": {"translation": "  "},                 # blank -> dropped
            "ghost": {"translation": "X"},               # unknown id
            "set1": {"options": {
                "Single": "Soltero(a)",
                "Ghost option": "X",                     # unknown source
                "Married filing jointly": 3,             # non-str
            }},
        },
        "ambiguous": ["ghost", "set1", 7],
    })
    adapter = adapter_with_client(_make_response(response))
    result = await adapter.translate_items(_ITEMS, "Spanish", "es-US")
    assert result == {
        "items": {"set1": {"options": {"Single": "Soltero(a)"}}},
        # unknown/non-str ambiguous entries dropped, known id kept
        "ambiguous": ["set1"],
    }


@pytest.mark.asyncio
async def test_skips_malformed_request_items(adapter_with_client):
    """Malformed input items (no id, empty text, empty option set, dupes)
    are dropped BEFORE the call; only well-formed items are requested."""
    adapter = adapter_with_client(_make_response(
        json.dumps({"items": {"ok": {"translation": "Bien"}},
                    "ambiguous": []})))
    result = await adapter.translate_items(
        [
            {"id": "ok", "kind": "field-name", "text": "Good"},
            {"id": "ok", "kind": "field-name", "text": "Duplicate id"},
            {"kind": "field-name", "text": "No id"},
            {"id": "empty", "kind": "field-name", "text": "   "},
            {"id": "noopts", "kind": "option-set", "options": []},
            "not-a-dict",
        ],
        "Spanish", "es-US",
    )
    assert result == {"items": {"ok": {"translation": "Bien"}},
                      "ambiguous": []}
    payload_prompt = adapter._client.aio.models.generate_content.await_args \
        .kwargs["contents"][0]
    assert "Duplicate id" not in payload_prompt
    assert "No id" not in payload_prompt


@pytest.mark.asyncio
async def test_empty_items_returns_empty_without_call(adapter_with_client):
    adapter = adapter_with_client(_make_response("{}"))
    assert await adapter.translate_items([], "Spanish", "es-US") \
        == {"items": {}, "ambiguous": []}
    adapter._client.aio.models.generate_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_none_on_bad_json(adapter_with_client):
    adapter = adapter_with_client(_make_response("not json"))
    assert await adapter.translate_items(_ITEMS, "Spanish", "es-US") is None


@pytest.mark.asyncio
async def test_none_on_bad_shape(adapter_with_client):
    adapter = adapter_with_client(_make_response('["x"]'))
    assert await adapter.translate_items(_ITEMS, "Spanish", "es-US") is None
    adapter = adapter_with_client(_make_response('{"no_items": true}'))
    assert await adapter.translate_items(_ITEMS, "Spanish", "es-US") is None


@pytest.mark.asyncio
async def test_none_on_api_error(adapter_with_client):
    adapter = adapter_with_client(_make_response("{}"))
    adapter._client.aio.models.generate_content = AsyncMock(
        side_effect=RuntimeError("boom"))
    assert await adapter.translate_items(_ITEMS, "Spanish", "es-US") is None


@pytest.mark.asyncio
async def test_none_when_no_client():
    from backend.adapters.text_ai_gemini import TextAIGemini
    with patch("backend.adapters.text_ai_gemini.genai") as mock_genai:
        mock_genai.Client.side_effect = Exception("no creds")
        adapter = TextAIGemini(api_key=None, vertexai=False)
    assert await adapter.translate_items(_ITEMS, "Spanish", "es-US") is None


@pytest.mark.asyncio
async def test_translate_labels_unchanged_for_existing_callers(
        adapter_with_client):
    """The exit-criterion guard: translate_labels keeps its contract
    (bare-list in, flat map out) -- translate_items is a SIBLING, not a
    rewrite."""
    adapter = adapter_with_client(
        _make_response('{"Male": "Masculino"}'))
    assert await adapter.translate_labels(["Male"], "Spanish", "es-US") \
        == {"Male": "Masculino"}
