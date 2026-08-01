"""Tests for the extractor LLM provider seam (scripts/bakeoff/llm_providers.py, bd 7a9.17).

The seam factors the extractor's single LLM out-call behind a registry so the
backend swaps by CONFIG, not code (local `claude` CLI now, a remote/hosted model
later). These tests pin the RESOLUTION behavior -- which backend a given model +
env selects -- without ever calling an LLM. The point is that:

  - the default name-dispatch preserves arm_llm_native's prior behavior
    (gemini* -> gemini, everything else -> the local claude CLI), and
  - EXTRACTOR_PROVIDER overrides it (the hosted/remote swap knob), failing loud
    on an unknown name rather than silently picking a wrong backend.

Imports the module by file path (repo precedent: test_bd_safe.py) since it lives
under scripts/bakeoff/, not an installed package.
"""

import importlib.util
import pathlib
import sys

import pytest


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "scripts" / "bakeoff" / "llm_providers.py"
)
spec = importlib.util.spec_from_file_location("llm_providers", SCRIPT_PATH)
lp = importlib.util.module_from_spec(spec)
sys.modules["llm_providers"] = lp
spec.loader.exec_module(lp)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Each test starts with EXTRACTOR_PROVIDER unset so default dispatch is the
    baseline; a test that wants the override sets it explicitly."""
    monkeypatch.delenv("EXTRACTOR_PROVIDER", raising=False)


# --- default name-based dispatch (preserves arm_llm_native's prior behavior) --- #

@pytest.mark.parametrize("model", [
    "claude-opus-4-8", "claude-sonnet-4-6", "opus", "sonnet", "haiku",
    "mysterynet",  # an UNKNOWN model still routes to the CLI, which rejects it
])
def test_non_gemini_models_route_to_claude_cli(model):
    assert lp.resolve_provider(model).name == "claude-cli"


@pytest.mark.parametrize("model", [
    "gemini-2.5-flash", "gemini-2.5-pro", "Gemini-3.5", "GEMINI-foo",
])
def test_gemini_models_route_to_gemini(model):
    # Case-insensitive prefix match, matching the prior startswith("gemini") lower().
    assert lp.resolve_provider(model).name == "gemini"


# --- EXTRACTOR_PROVIDER override (the hosted/remote swap knob) ---------------- #

def test_env_override_forces_provider_regardless_of_model(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_PROVIDER", "gemini")
    # A claude-* model name would default to claude-cli; the env wins.
    assert lp.resolve_provider("claude-opus-4-8").name == "gemini"

    monkeypatch.setenv("EXTRACTOR_PROVIDER", "claude-cli")
    # A gemini-* model name would default to gemini; the env wins.
    assert lp.resolve_provider("gemini-2.5-flash").name == "claude-cli"


def test_blank_env_falls_back_to_name_dispatch(monkeypatch):
    # An empty/whitespace value is treated as unset, not as a provider named "".
    monkeypatch.setenv("EXTRACTOR_PROVIDER", "   ")
    assert lp.resolve_provider("gemini-2.5-flash").name == "gemini"
    assert lp.resolve_provider("claude-opus-4-8").name == "claude-cli"


def test_unknown_env_provider_fails_loud(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_PROVIDER", "typo-net")
    with pytest.raises(KeyError) as exc:
        lp.resolve_provider("claude-opus-4-8")
    msg = str(exc.value)
    assert "typo-net" in msg
    assert "EXTRACTOR_PROVIDER" in msg  # says WHERE the bad name came from
    # lists the known providers so the typo is fixable from the error alone
    assert "claude-cli" in msg and "gemini" in msg


# --- registration (a hosted deployment injects its own backend) -------------- #

def test_register_provider_adds_a_resolvable_backend(monkeypatch):
    class _Fake:
        name = "fake-remote"

        def run(self, prompt, model, pdf_path):  # pragma: no cover - never called
            raise AssertionError("transport must not run in a resolution test")

    fake = _Fake()
    lp.register_provider(fake)
    try:
        monkeypatch.setenv("EXTRACTOR_PROVIDER", "fake-remote")
        assert lp.resolve_provider("anything") is fake
    finally:
        # Don't leak the fake into the module-level registry for other tests.
        lp._REGISTRY.pop("fake-remote", None)


def test_builtin_registry_has_both_backends():
    assert set(lp._REGISTRY) >= {"claude-cli", "gemini"}
    assert lp._REGISTRY["claude-cli"].name == "claude-cli"
    assert lp._REGISTRY["gemini"].name == "gemini"


# --- gemini provider rejects a non-gemini model name (Codex r2) -------------- #

def test_gemini_provider_rejects_non_gemini_model():
    """EXTRACTOR_PROVIDER=gemini with the default claude-* model must fail LOUD,
    not silently send a Claude model name to google-genai (which rejects it with
    an opaque error). The guard runs before any SDK import/network call."""
    provider = lp._REGISTRY["gemini"]
    with pytest.raises(ValueError) as exc:
        provider.run("prompt", "claude-opus-4-8", None)
    msg = str(exc.value)
    assert "gemini" in msg.lower()
    assert "EXTRACTOR_MODEL" in msg  # tells the caller how to fix it


# --- Vertex-only: no AI Studio key path anywhere in scripts/bakeoff/ --------- #
# bd polyglot-pdf-kgmn (+ f3lm / w99b). The AI Studio gate is closed fleet-wide:
# arm_gemini._client used to fall back to genai.Client(api_key=...) when
# VERTEXAI=false, silently billing off the tracked project. It now delegates to
# llm_providers._vertex_gemini_client, so NO env state can produce an api_key
# client.

def _load_arm_gemini():
    """arm_gemini imports sibling bakeoff modules by bare name, so its own
    directory must be on sys.path (it does this itself at import time)."""
    path = (pathlib.Path(__file__).resolve().parent.parent
            / "scripts" / "bakeoff" / "arm_gemini.py")
    spec_ag = importlib.util.spec_from_file_location("arm_gemini", path)
    mod = importlib.util.module_from_spec(spec_ag)
    sys.modules["arm_gemini"] = mod
    spec_ag.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("vertexai_env", [None, "true", "false", "TRUE", "0"])
def test_arm_gemini_client_is_vertex_only_under_every_env(monkeypatch,
                                                          vertexai_env):
    """No VERTEXAI value -- including the former escape hatch 'false' -- may
    produce an api_key client. Captures the kwargs genai.Client is built with."""
    if vertexai_env is None:
        monkeypatch.delenv("VERTEXAI", raising=False)
    else:
        monkeypatch.setenv("VERTEXAI", vertexai_env)
    # A key IS present in env: the point is that it must be ignored outright.
    monkeypatch.setenv("GEMINI_API_KEY", "sk-should-never-be-used")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

    captured = {}

    class _FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    ag = _load_arm_gemini()
    monkeypatch.setattr(lp.genai if hasattr(lp, "genai") else ag.genai,
                        "Client", _FakeClient, raising=False)
    # _vertex_gemini_client imports google.genai lazily inside the function.
    import google.genai as _genai
    monkeypatch.setattr(_genai, "Client", _FakeClient)

    ag._client(http_options=None)

    assert "api_key" not in captured, captured
    assert captured.get("vertexai") is True, captured
    assert captured.get("project") == "test-project", captured


def test_bakeoff_sources_have_no_api_key_client_construction():
    """Static guard: no scripts/bakeoff/ module may construct an AI-Studio
    client. Catches a NEW file reintroducing the closed gate, which the
    behavioral test above (arm_gemini only) would not see."""
    bakeoff = (pathlib.Path(__file__).resolve().parent.parent
               / "scripts" / "bakeoff")
    offenders = []
    for py in sorted(bakeoff.glob("*.py")):
        text = py.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # a comment ABOUT the closed gate is fine
            if "genai.Client(" in line and "api_key" in line:
                offenders.append(f"{py.name}:{i}: {stripped}")
            elif "api_key=" in line and "Client" in line:
                offenders.append(f"{py.name}:{i}: {stripped}")
    assert offenders == [], (
        "AI Studio api_key client construction found (the gate is closed; bd "
        "polyglot-pdf-f3lm / kgmn):\n" + "\n".join(offenders))
