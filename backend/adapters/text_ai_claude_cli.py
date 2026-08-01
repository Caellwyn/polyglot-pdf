"""Text-AI adapter backed by the local `claude` CLI (bd polyglot-pdf-cpiw).

WHY THIS EXISTS: local mode must behave exactly like hosted -- same lint, same
translation sweep, same guidance regeneration -- with ONE sanctioned difference,
the LLM provider. Hosted spends metered Gemini tokens; local uses the
maintainer's Claude Code subscription through the `claude` CLI, which is
effectively free in-environment. That is the same seam scripts/bakeoff/
llm_providers.py already uses for extraction (ClaudeCliProvider); this is its
ITextAI counterpart for the editor's translation / guidance paths.

DESIGN -- override the TRANSPORT ONLY. This subclasses TextAIGemini and replaces
exactly one method, `_generate`. Everything above that line (prompt assembly,
JSON-shape validation, id/option filtering, fail-open semantics, counts-only
logging) is inherited verbatim, so the two providers CANNOT drift in behavior --
which is the whole point of the bead. A reimplementation of translate_items and
friends here would recreate the local-vs-hosted divergence we are removing.

The CLI is a SUBPROCESS, so `_generate` runs it on a worker thread
(asyncio.to_thread) and never blocks the event loop.

ASCII only (cp1252 safe).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess

import structlog

from backend.adapters.text_ai_gemini import TextAIGemini

_log = structlog.get_logger(__name__)

# The CLI is interactive-scale, not API-scale: a full-form translation batch can
# take minutes. Generous default, overridable for a slow machine.
_TIMEOUT_ENV = "EDITOR_CLAUDE_TIMEOUT_S"
_DEFAULT_TIMEOUT_S = 600

# Default model for editor-side text work. A subscription-auth CLI model id,
# NOT a Gemini one -- resolve_text_ai() below never routes a gemini-* name here.
DEFAULT_CLAUDE_MODEL = "sonnet"


class TextAIClaudeCli(TextAIGemini):
    """ITextAI over the local `claude` CLI in headless print mode (-p).

    Inherits every prompt-building and response-parsing method from
    TextAIGemini and overrides ONLY `_generate`, so local and hosted produce
    the same shapes from the same prompts.
    """

    def __init__(self, model: str = DEFAULT_CLAUDE_MODEL, **_ignored) -> None:
        # Deliberately do NOT call super().__init__: that builds a google-genai
        # client and would demand Gemini credentials this path must never need.
        # We set only what the inherited methods actually read. The names match
        # the base class exactly (_model_name / _model_chain / _thinking_budget)
        # so any inherited code that reads them keeps working; _model_chain is
        # unused here because this class fully overrides _generate.
        self._model_name = model
        self._model_chain = [model]
        self._thinking_budget = None
        self._log = _log.bind(provider="claude-cli", model=model)
        # The remaining attributes the base __init__ sets. Today they are read
        # only inside that __init__, so nothing needs them -- but the class's
        # whole premise is "inherit everything, override only the transport",
        # and that premise silently would not hold for these four. Setting them
        # means a future inherited method that reads self._vertexai (say, for a
        # log line) cannot AttributeError on the local path, where test
        # coverage is thinnest.
        self._api_key = None
        self._vertexai = False
        self._project = None
        self._location = None
        # Inherited methods check `self._client is None` as their "no provider,
        # fail open" guard. A non-None sentinel keeps them on the normal path;
        # nothing in this class ever calls a method on it.
        self._client = _CLI_SENTINEL

    async def _generate(
        self,
        stable_prefix: list,
        fresh_tail: list,
        system_instruction: str | None = None,
        response_mime_type: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Run the assembled prompt through `claude -p` and return raw text.

        Mirrors the base class's contract: returns the model's text, RAISES on
        any failure so the callers' existing try/except fail-open paths handle
        it exactly as they do for Gemini.

        `temperature` has no CLI equivalent and is ignored -- the translate
        paths pass 0.0 for determinism, which the CLI cannot honor. That is a
        fidelity gap accepted for a local authoring tool, not a correctness one:
        every caller re-validates the JSON shape before using it.
        """
        prompt = "\n\n".join(
            str(p) for p in (list(stable_prefix) + list(fresh_tail)) if p
        )
        want_json = response_mime_type == "application/json"
        if want_json:
            # The CLI has no response_mime_type, so JSON-only is enforced by
            # instruction here and by _coerce_json() on the way out. Both are
            # needed: a chat model asked for a nested object will sometimes emit
            # a malformed first attempt, then self-correct in prose ("Let me
            # give the correct final JSON: {...}"). Observed live on sonnet.
            prompt += (
                "\n\nReturn ONLY the JSON object described above, as your "
                "ENTIRE response. No prose before or after it, no explanation, "
                "no markdown code fences, and no second attempt -- emit the "
                "object once, correctly."
            )
        text = await asyncio.to_thread(
            self._run_cli, prompt, system_instruction,
        )
        return _coerce_json(text) if want_json else text

    def _run_cli(self, prompt: str, system_instruction: str | None) -> str:
        exe = shutil.which("claude") or "claude"
        cmd = [
            exe, "-p",
            "--model", self._model_name,
            "--output-format", "json",
        ]
        if system_instruction:
            cmd += ["--append-system-prompt", system_instruction]
        try:
            timeout_s = int(os.getenv(_TIMEOUT_ENV, str(_DEFAULT_TIMEOUT_S)))
        except ValueError:
            timeout_s = _DEFAULT_TIMEOUT_S

        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            encoding="utf-8", timeout=timeout_s,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude CLI exited {proc.returncode}: "
                f"{(proc.stderr or proc.stdout)[:500]}"
            )
        envelope = json.loads(proc.stdout)
        if envelope.get("is_error"):
            raise RuntimeError(f"claude CLI error: {envelope.get('result')!r}")
        text = envelope.get("result") or ""
        usage = envelope.get("usage") or {}
        self._log.info(
            "text_ai_claude_cli_call",
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            chars=len(text),
        )
        return _strip_code_fence(text)


class _CliSentinel:
    """Truthy stand-in for the google-genai client (see __init__)."""

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "<claude-cli>"


_CLI_SENTINEL = _CliSentinel()


def _strip_code_fence(text: str) -> str:
    """Drop a leading ```json fence if the model added one anyway.

    Cheap and safe: the inherited callers json.loads the result, so a stray
    fence would otherwise turn a good response into a fail-open None.
    """
    s = (text or "").strip()
    if not s.startswith("```"):
        return s
    body = s.split("\n", 1)[1] if "\n" in s else ""
    if body.rstrip().endswith("```"):
        body = body.rstrip()[: -len("```")]
    return body.strip()


def _coerce_json(text: str) -> str:
    """Return the response as a bare, parseable JSON document.

    A response_mime_type='application/json' request is a HARD contract for the
    inherited callers: they json.loads() the string and fail open to None on
    anything else. The Gemini path gets that from the API; the CLI does not, so
    this recovers it.

    Handles, in order: an already-clean document; a fenced one; and the
    self-correction shape observed live on sonnet, where a malformed first
    attempt is followed by prose and then a correct object. For that last case
    the LAST balanced top-level object wins -- the model's own final answer.
    Returns the input unchanged when nothing parses, so the caller still sees a
    JSONDecodeError and fail-opens exactly as before.
    """
    s = _strip_code_fence(text)
    if not s:
        return s
    try:
        json.loads(s)
        return s
    except ValueError:
        pass
    candidates = [c for c in _balanced_objects(s) if _parses(c)]
    return candidates[-1] if candidates else s


def _parses(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except ValueError:
        return False


def _balanced_objects(s: str):
    """Yield every balanced {...} span in `s`, brace-counted outside strings."""
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    yield s[start:i + 1]


def claude_cli_available() -> bool:
    """True when the `claude` CLI is on PATH (the local-provider precondition)."""
    return shutil.which("claude") is not None
