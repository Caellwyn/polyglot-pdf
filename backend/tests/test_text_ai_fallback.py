"""TextAIGemini model-fallback chain (bd polyglot-pdf-jnjj.42).

Verifies _generate() degrades to the next Gemini model on a transient
AVAILABILITY error (5xx, or 404/429) and fails fast on auth/config (other 4xx).
A single cheap-model outage (2.5-flash-lite was 503 for 1hr+ on 2026-06-25) must
not take the secretary/validator down when a sibling lite model is up.

ASCII only (CLAUDE.md scar #6).
"""
import types as pytypes

import pytest
from google.genai import errors

from backend.adapters.text_ai_gemini import TextAIGemini


def _server_error(code=503):
    return errors.ServerError(code, {"error": {"code": code, "message": "x"}}, None)


def _client_error(code=404):
    return errors.ClientError(code, {"error": {"code": code, "message": "x"}}, None)


class _FakeResponse:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = pytypes.SimpleNamespace(
            cached_content_token_count=0,
            prompt_token_count=10,
            candidates_token_count=3,
        )


class _FakeModels:
    """Records the models tried; raises per-model from `behavior` or returns text."""
    def __init__(self, behavior):
        self.behavior = behavior  # dict: model_name -> Exception | str
        self.tried = []

    async def generate_content(self, *, model, contents, config=None):
        self.tried.append(model)
        outcome = self.behavior.get(model, "default answer")
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResponse(outcome)


class _FakeAio:
    def __init__(self, models):
        self.models = models


class _FakeClient:
    def __init__(self, behavior):
        self.aio = _FakeAio(_FakeModels(behavior))


def _adapter(behavior, **kw):
    a = TextAIGemini(api_key="test-key", model="gemini-2.5-flash-lite", **kw)
    a._client = _FakeClient(behavior)
    return a


@pytest.mark.asyncio
async def test_chain_is_configured_model_then_fallbacks():
    a = _adapter({})
    assert a._model_chain[0] == "gemini-2.5-flash-lite"
    assert "gemini-3.1-flash-lite" in a._model_chain
    # no duplicate of the configured model
    assert a._model_chain.count("gemini-2.5-flash-lite") == 1


@pytest.mark.asyncio
async def test_503_on_primary_falls_back_to_next_model():
    a = _adapter({"gemini-2.5-flash-lite": _server_error(503)})
    out = await a._generate(stable_prefix=["sys"], fresh_tail=["q"])
    assert out == "default answer"
    # primary tried then the first fallback served it
    assert a._client.aio.models.tried[0] == "gemini-2.5-flash-lite"
    assert a._client.aio.models.tried[1] == "gemini-3.1-flash-lite"


@pytest.mark.asyncio
async def test_404_clienterror_also_falls_back():
    a = _adapter({"gemini-2.5-flash-lite": _client_error(404)})
    out = await a._generate(stable_prefix=["sys"], fresh_tail=["q"])
    assert out == "default answer"
    assert len(a._client.aio.models.tried) == 2


@pytest.mark.asyncio
async def test_429_clienterror_falls_back():
    a = _adapter({"gemini-2.5-flash-lite": _client_error(429)})
    out = await a._generate(stable_prefix=["sys"], fresh_tail=["q"])
    assert out == "default answer"


@pytest.mark.asyncio
async def test_auth_clienterror_403_does_NOT_fall_back():
    # 403 = config/auth: every model would fail the same way -> fail fast, do not
    # mask by trying siblings.
    a = _adapter({"gemini-2.5-flash-lite": _client_error(403)})
    with pytest.raises(errors.ClientError):
        await a._generate(stable_prefix=["sys"], fresh_tail=["q"])
    assert a._client.aio.models.tried == ["gemini-2.5-flash-lite"]


@pytest.mark.asyncio
async def test_400_bad_request_does_NOT_fall_back():
    a = _adapter({"gemini-2.5-flash-lite": _client_error(400)})
    with pytest.raises(errors.ClientError):
        await a._generate(stable_prefix=["sys"], fresh_tail=["q"])
    assert a._client.aio.models.tried == ["gemini-2.5-flash-lite"]


@pytest.mark.asyncio
async def test_all_models_unavailable_reraises():
    # Every model 503 -> the last one's error propagates (caller fail-opens).
    behavior = {m: _server_error(503) for m in
                ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite",
                 "gemini-flash-lite-latest"]}
    a = _adapter(behavior)
    with pytest.raises(errors.ServerError):
        await a._generate(stable_prefix=["sys"], fresh_tail=["q"])
    assert len(a._client.aio.models.tried) == 3


@pytest.mark.asyncio
async def test_validate_fails_open_when_all_models_down():
    # validate() wraps _generate in try/except -> a total outage returns the
    # fail-open empty verdict, not an exception.
    behavior = {m: _server_error(503) for m in
                ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite",
                 "gemini-flash-lite-latest"]}
    a = _adapter(behavior)
    verdict = await a.validate({"stable_prefix": ["sys"], "fresh_tail": ["vals"]})
    assert verdict == {"conflicts": []}


@pytest.mark.asyncio
async def test_validate_succeeds_via_fallback():
    # primary down, fallback returns valid JSON -> validate parses it (fallback
    # reduces how often fail-open fires).
    a = _adapter({
        "gemini-2.5-flash-lite": _server_error(503),
        "gemini-3.1-flash-lite": '{"conflicts": []}',
    })
    verdict = await a.validate({"stable_prefix": ["sys"], "fresh_tail": ["vals"]})
    assert verdict == {"conflicts": []}
    assert a._client.aio.models.tried[:2] == [
        "gemini-2.5-flash-lite", "gemini-3.1-flash-lite"]


@pytest.mark.asyncio
async def test_custom_fallback_models_override():
    a = _adapter({"gemini-2.5-flash-lite": _server_error(503)},
                 fallback_models=["my-fallback-model"])
    out = await a._generate(stable_prefix=["sys"], fresh_tail=["q"])
    assert out == "default answer"
    assert a._client.aio.models.tried == ["gemini-2.5-flash-lite", "my-fallback-model"]
