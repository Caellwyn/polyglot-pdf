"""One place that decides which text model serves the EDITOR's authoring work.

bd polyglot-pdf-cpiw. The editor's translation sweep and guidance regeneration
both need an ITextAI. Hosted spends metered Gemini tokens; local uses the
maintainer's Claude Code subscription via the `claude` CLI (effectively free
in-environment). That provider choice is the ONLY sanctioned difference between
local and hosted mode -- every lint rule, gate, and UI affordance must behave
identically in both -- so it lives in exactly ONE function rather than being
re-decided at each call site.

ASCII only (cp1252 safe).
"""
from __future__ import annotations

import structlog

from backend.adapters.text_ai_claude_cli import (
    TextAIClaudeCli,
    claude_cli_available,
)
from backend.adapters.text_ai_gemini import TextAIGemini
from backend.ports.text_ai_port import ITextAI

_log = structlog.get_logger(__name__)

PROVIDER_CLAUDE_CLI = "claude-cli"
PROVIDER_GEMINI = "gemini"


class EditorTextAIUnavailable(RuntimeError):
    """The configured provider cannot run here (surfaced as a 503, not a
    silent degrade to the other provider -- a wrong-provider fallback would
    either spend money the local dev did not ask for, or fail on Cloud Run
    where no CLI exists)."""


def resolve_editor_text_ai(settings) -> tuple[ITextAI, str]:
    """Build the editor's text-AI adapter. Returns (adapter, model_label).

    `model_label` is what gets reported to the editor UI and written into the
    bake provenance, so a kit records which model actually produced its
    translations.

    Raises EditorTextAIUnavailable when the configured provider is not usable,
    so the caller can return a clear 503 instead of failing deep in a bake.
    """
    provider = (getattr(settings, "EDITOR_TEXT_PROVIDER", "") or "").strip().lower()

    if provider == PROVIDER_CLAUDE_CLI:
        if not claude_cli_available():
            raise EditorTextAIUnavailable(
                "EDITOR_TEXT_PROVIDER=claude-cli but the `claude` CLI is not "
                "on PATH. Install Claude Code, or set "
                "EDITOR_TEXT_PROVIDER=gemini."
            )
        model = getattr(settings, "EDITOR_CLAUDE_MODEL", "sonnet") or "sonnet"
        _log.info("editor_text_ai_resolved", provider=provider, model=model)
        return TextAIClaudeCli(model=model), model

    # Default: Gemini. Same constructor discipline as the call sites this
    # replaced -- an EMPTY fallback chain (a deliberately chosen tier fails
    # loud, never silently degrades to lite) and a bounded thinking budget
    # (2.5-pro cannot disable thinking).
    if not (settings.VERTEXAI or settings.GEMINI_API_KEY):
        raise EditorTextAIUnavailable(
            "Translation is not configured on this server (no Vertex project "
            "and no Gemini API key)."
        )
    model = settings.OPTION_TRANSLATION_MODEL
    _log.info("editor_text_ai_resolved", provider=PROVIDER_GEMINI, model=model)
    return (
        TextAIGemini(
            api_key=settings.GEMINI_API_KEY,
            model=model,
            vertexai=settings.VERTEXAI,
            fallback_models=(),
            thinking_budget=512 if "pro" in model else None,
        ),
        model,
    )
