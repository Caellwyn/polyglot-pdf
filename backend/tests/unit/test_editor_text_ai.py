"""Editor text-AI provider seam (bd polyglot-pdf-cpiw).

The editor's authoring-time text work (translation sweep, guidance
regeneration) runs on Gemini when hosted and on the local `claude` CLI when
local. That provider choice is the ONE sanctioned difference between the two
modes, so these tests pin the resolution rules and the CLI adapter's transport
contract -- everything ABOVE the transport is inherited from TextAIGemini and
covered by its own tests.

ASCII only.
"""
from __future__ import annotations

import json

import pytest

from backend.adapters.text_ai_claude_cli import (
    TextAIClaudeCli,
    _coerce_json,
)
from backend.services import editor_text_ai as eta


class _Settings:
    """Minimal stand-in for the real Settings object."""

    def __init__(self, provider="gemini", claude_model="sonnet",
                 vertexai=True, api_key=None,
                 translation_model="gemini-2.5-pro"):
        self.EDITOR_TEXT_PROVIDER = provider
        self.EDITOR_CLAUDE_MODEL = claude_model
        self.VERTEXAI = vertexai
        self.GEMINI_API_KEY = api_key
        self.OPTION_TRANSLATION_MODEL = translation_model


# --- provider resolution ---------------------------------------------------- #

def test_defaults_to_gemini(monkeypatch):
    built = {}

    class _FakeGemini:
        def __init__(self, **kw):
            built.update(kw)

    monkeypatch.setattr(eta, "TextAIGemini", _FakeGemini)
    ai, model = eta.resolve_editor_text_ai(_Settings())
    assert isinstance(ai, _FakeGemini)
    assert model == "gemini-2.5-pro"
    # The constructor discipline the call sites relied on must survive the move:
    # an EMPTY fallback chain (a chosen tier fails loud rather than silently
    # degrading to lite) and a bounded thinking budget for pro.
    assert built["fallback_models"] == ()
    assert built["thinking_budget"] == 512


def test_claude_cli_selected_when_configured(monkeypatch):
    monkeypatch.setattr(eta, "claude_cli_available", lambda: True)
    ai, model = eta.resolve_editor_text_ai(
        _Settings(provider="claude-cli", claude_model="haiku"))
    assert isinstance(ai, TextAIClaudeCli)
    assert model == "haiku"


def test_claude_cli_without_the_cli_raises_rather_than_falling_back(monkeypatch):
    # A silent fall back to Gemini would spend metered tokens the local dev did
    # not ask for -- the whole point of choosing claude-cli. Fail loud instead.
    monkeypatch.setattr(eta, "claude_cli_available", lambda: False)
    with pytest.raises(eta.EditorTextAIUnavailable) as exc:
        eta.resolve_editor_text_ai(_Settings(provider="claude-cli"))
    assert "claude" in str(exc.value).lower()


def test_gemini_without_credentials_raises(monkeypatch):
    with pytest.raises(eta.EditorTextAIUnavailable):
        eta.resolve_editor_text_ai(
            _Settings(vertexai=False, api_key=None))


def test_provider_name_is_case_and_space_insensitive(monkeypatch):
    monkeypatch.setattr(eta, "claude_cli_available", lambda: True)
    ai, _ = eta.resolve_editor_text_ai(
        _Settings(provider="  Claude-CLI  "))
    assert isinstance(ai, TextAIClaudeCli)


# --- the CLI adapter's JSON contract ---------------------------------------- #
#
# response_mime_type='application/json' is a HARD contract for every inherited
# caller: they json.loads() the string and fail open to None on anything else.
# Gemini gets that from the API; the CLI has no such knob, so _coerce_json has
# to recover it.

def test_coerce_passes_clean_json_through():
    assert _coerce_json('{"a": 1}') == '{"a": 1}'


def test_coerce_strips_a_code_fence():
    assert json.loads(_coerce_json('```json\n{"a": 1}\n```')) == {"a": 1}


def test_coerce_recovers_the_self_correction_shape():
    # Observed live on sonnet: a malformed first attempt, prose, then a correct
    # object. The model's FINAL answer is the one to take.
    raw = (
        '{"items": {"f1": {"translation": "X"}}}, "ambiguous": []}\n\n'
        'Let me give the correct final JSON:\n\n'
        '{"items": {"f1": {"translation": "Fecha"}}, "ambiguous": []}'
    )
    assert json.loads(_coerce_json(raw)) == {
        "items": {"f1": {"translation": "Fecha"}}, "ambiguous": [],
    }


def test_coerce_ignores_braces_inside_strings():
    raw = 'noise {"a": "a } brace", "b": 2} trailing'
    assert json.loads(_coerce_json(raw)) == {"a": "a } brace", "b": 2}


def test_coerce_returns_input_when_nothing_parses():
    # The caller must still see a JSONDecodeError and fail open exactly as it
    # does for a bad Gemini response -- never a silently swallowed empty result.
    assert _coerce_json("no json here") == "no json here"


@pytest.mark.asyncio
async def test_generate_coerces_only_for_json_requests(monkeypatch):
    ai = TextAIClaudeCli()
    monkeypatch.setattr(
        ai, "_run_cli",
        lambda prompt, si: 'chatter {"a": 1}',
    )
    # A JSON request recovers the object...
    out = await ai._generate(
        stable_prefix=["p"], fresh_tail=[],
        response_mime_type="application/json")
    assert json.loads(out) == {"a": 1}
    # ...a plain-text request is returned verbatim.
    out = await ai._generate(stable_prefix=["p"], fresh_tail=[])
    assert out == 'chatter {"a": 1}'


@pytest.mark.asyncio
async def test_generate_joins_prefix_and_tail(monkeypatch):
    ai = TextAIClaudeCli()
    seen = {}

    def _capture(prompt, si):
        seen["prompt"] = prompt
        return "ok"

    monkeypatch.setattr(ai, "_run_cli", _capture)
    await ai._generate(stable_prefix=["A", "B"], fresh_tail=["C"])
    assert seen["prompt"] == "A\n\nB\n\nC"


def test_inherits_the_gemini_prompt_layer():
    # The class must NOT reimplement translate_items and friends -- inheriting
    # them is what keeps local and hosted from drifting (the bead's whole
    # point). Assert the methods resolve to the base class's implementation.
    from backend.adapters.text_ai_gemini import TextAIGemini
    for name in ("translate_items", "translate_labels", "judge_translations",
                 "rectify_translations", "back_translate"):
        assert getattr(TextAIClaudeCli, name) is getattr(TextAIGemini, name), (
            f"{name} was overridden -- local and hosted can now drift"
        )
