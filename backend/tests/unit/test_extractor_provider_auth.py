"""Provider-level auth for the Gemini extractor (bd polyglot-pdf-fyq4;
VERTEX-ONLY since bd polyglot-pdf-f3lm).

Every gemini call goes through Vertex on the tracked billing project -- there
is NO AI Studio / GEMINI_API_KEY path (maintainer directive 2026-07-28: the
AI Studio gate is closed). That construction lives in
scripts/bakeoff/llm_providers.py's _vertex_gemini_client(), shared by
GeminiProvider.run() and run_json_gemini(); the route-level tests in
test_editor_kit_routes.py cover the config GATE, but this pins the PROVIDER's
own client construction directly, by stubbing genai.Client and asserting which
kwargs it receives -- no network, no real SDK call.

These tests previously pinned a dual-path (VERTEXAI=true -> Vertex, else an
AI Studio key); they now pin the INVERSE invariant -- Vertex regardless of
the VERTEXAI env, and never an api_key -- so a regression that reintroduces
the key path fails here.
"""
import importlib.util
import pathlib
import sys
import types

import pytest

# scripts/bakeoff/ is imported by sys.path in production (its modules do bare
# `import arm_llm_native`), but pytest's importlib import-mode does not honor
# sys.path for bare imports, so load llm_providers by FILE PATH here.
_BAKEOFF_DIR = pathlib.Path(__file__).resolve().parents[3] / "scripts" / "bakeoff"
_LLM_PROVIDERS_PY = _BAKEOFF_DIR / "llm_providers.py"


def _load_llm_providers():
    spec = importlib.util.spec_from_file_location(
        "llm_providers_under_test", str(_LLM_PROVIDERS_PY)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def provider_with_stubbed_genai(monkeypatch):
    """Import GeminiProvider with google.genai stubbed so run() records the
    Client kwargs instead of making a call. Yields (provider, calls)."""
    calls = {}

    class _StubModels:
        def generate_content(self, **kwargs):
            # Return an object exposing .text and .usage_metadata=None.
            return types.SimpleNamespace(text='{"fields": []}', usage_metadata=None)

    class _StubClient:
        def __init__(self, **kwargs):
            calls["client_kwargs"] = kwargs
            self.models = _StubModels()

    stub_types = types.SimpleNamespace(
        HttpOptions=lambda **kw: ("HttpOptions", kw),
        Part=types.SimpleNamespace(from_bytes=lambda **kw: ("Part", kw)),
        GenerateContentConfig=lambda **kw: ("cfg", kw),
    )
    # `from google.genai import types` resolves `types` as an ATTRIBUTE of the
    # google.genai module object, so the stub module must expose it directly.
    stub_genai = types.SimpleNamespace(Client=_StubClient, types=stub_types)
    stub_google = types.SimpleNamespace(genai=stub_genai)

    monkeypatch.setitem(sys.modules, "google", stub_google)
    monkeypatch.setitem(sys.modules, "google.genai", stub_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", stub_types)

    llm_providers = _load_llm_providers()
    # normalize_schema/extract_json are resolved lazily from arm_llm_native;
    # stub the parse helpers so run() does not need the real pipeline.
    monkeypatch.setattr(
        llm_providers, "_parse_helpers",
        lambda: (lambda s: {"fields": []}, lambda d: {"fields": []}),
    )
    provider = llm_providers.GeminiProvider()
    yield provider, calls


def test_provider_uses_vertex_when_VERTEXAI_true_and_no_key(
    provider_with_stubbed_genai, monkeypatch
):
    provider, calls = provider_with_stubbed_genai
    monkeypatch.setenv("VERTEXAI", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)  # the Cloud Run reality
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-x")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    provider.run("prompt", "gemini-2.5-pro", None)

    kw = calls["client_kwargs"]
    assert kw.get("vertexai") is True
    assert kw.get("project") == "proj-x"
    assert kw.get("location") == "us-central1"
    assert "api_key" not in kw  # no key demanded on the Vertex path


def test_provider_uses_vertex_even_when_VERTEXAI_UNSET(
    provider_with_stubbed_genai, monkeypatch
):
    """The bug this fixed (bd f3lm): VERTEXAI unset used to mean "AI Studio
    key", so a bare local run with ADC decided it had no credentials and
    dropped guidance. Vertex is now unconditional -- a present key is
    IGNORED, never used to build the client."""
    provider, calls = provider_with_stubbed_genai
    monkeypatch.delenv("VERTEXAI", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "local-key")  # must be ignored
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-x")

    provider.run("prompt", "gemini-2.5-flash", None)

    kw = calls["client_kwargs"]
    assert kw.get("vertexai") is True
    assert kw.get("project") == "proj-x"
    assert "api_key" not in kw  # the AI Studio gate is CLOSED


def test_provider_uses_vertex_even_when_VERTEXAI_false_and_no_key(
    provider_with_stubbed_genai, monkeypatch
):
    """Even the explicit VERTEXAI=false opt-out no longer routes to AI Studio
    (the directive removed the escape hatch, not just the default), and a
    missing key no longer KeyErrors -- there is no key path to fail."""
    provider, calls = provider_with_stubbed_genai
    monkeypatch.setenv("VERTEXAI", "false")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    provider.run("prompt", "gemini-2.5-pro", None)

    kw = calls["client_kwargs"]
    assert kw.get("vertexai") is True
    assert "api_key" not in kw


def test_provider_rejects_non_gemini_model_before_any_client(
    provider_with_stubbed_genai, monkeypatch
):
    # The model guard fires before client construction, on either auth path.
    provider, calls = provider_with_stubbed_genai
    monkeypatch.setenv("VERTEXAI", "true")
    with pytest.raises(ValueError, match="gemini"):
        provider.run("prompt", "claude-opus-4-8", None)
    assert "client_kwargs" not in calls  # never reached the SDK
