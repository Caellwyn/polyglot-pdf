"""Unit tests for TextAIGemini adapter (bd polyglot-pdf-jnjj.14).

Uses a stubbed genai.Client so no real API calls are made. Tests cover:
- happy path verdict shape
- implicit cache-hit logging
- fail-open on API exception
- fail-open on unparseable JSON
- fail-open when no client is configured
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
async def test_validate_cache_hit_logged(adapter_with_client, capfd):
    """cache_hit=True appears in stdout log output when cached_tokens > 0."""
    response = _make_response(text='{"conflicts":[]}', cached_tokens=512)
    adapter = adapter_with_client(response)
    await adapter.validate({"stable_prefix": ["catalog"], "fresh_tail": ["q"]})
    out = capfd.readouterr().out
    assert "cache_hit=True" in out, (
        f"Expected 'cache_hit=True' in log output; got:\n{out}"
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
async def test_ask_raises_not_implemented():
    """ask() raises NotImplementedError until the secretary bead lands."""
    from backend.adapters.text_ai_gemini import TextAIGemini

    with patch("backend.adapters.text_ai_gemini.genai"):
        adapter = TextAIGemini(api_key="test-key", vertexai=False)

    with pytest.raises(NotImplementedError):
        await adapter.ask("what is the zip code?", {})


def test_get_text_ai_wiring():
    """get_text_ai() resolves to a TextAIGemini without import error."""
    from backend.dependencies import get_text_ai
    from backend.adapters.text_ai_gemini import TextAIGemini
    from backend.config import Settings

    settings = Settings()
    with patch("backend.adapters.text_ai_gemini.genai"):
        result = get_text_ai(settings)

    assert isinstance(result, TextAIGemini)
