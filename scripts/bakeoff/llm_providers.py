#!/usr/bin/env python3
"""Pluggable LLM backends for the PDF -> FormSchema extractor (bd 7a9.17).

The extractor's single LLM out-call is factored behind a small provider seam so
the backend can be swapped by CONFIG, not code: the local `claude` CLI today
(free in the maintainer's environment), a remote/paid API (Gemini) as a
fallback, and -- the point of the seam -- whatever better/hosted model is wanted
later when schema prep is outsourced. Adding a backend is registering a provider,
not adding an `if` to the call site.

A provider takes a fully-assembled text prompt (built by arm_llm_native.build_prompt)
plus the model name and optional PDF path, and returns the parsed FormSchema dict
and a token-info dict. Prompt assembly stays in arm_llm_native -- providers own
ONLY the transport (how the bytes reach a model and come back).

Resolution order (resolve_provider):
  1. EXTRACTOR_PROVIDER env var, if set, names the provider explicitly
     (e.g. "claude-cli", "gemini") -- this is the hosted/remote swap knob.
  2. Otherwise the model name picks it: "gemini*" -> gemini, everything else
     -> the local claude CLI (which itself rejects a name it doesn't know, so an
     unknown model surfaces as a CLI error, not a silent wrong backend). This
     preserves arm_llm_native's prior name-dispatch behavior exactly.

ASCII only (cp1252 safe).
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
from typing import Callable, Optional, Protocol

# token_info shape: {"input": int|None, "output": int|None, optionally
# "cost_usd_equiv": float|None}. schema is the parsed FormSchema dict.
ProviderResult = tuple[dict, dict]


class LLMProvider(Protocol):
    """Transport for one LLM backend. Implementations own ONLY how the prompt
    reaches a model and how the response becomes a (schema, token_info) pair."""

    #: stable id used by EXTRACTOR_PROVIDER and recorded in schema._bakeoff.backend
    name: str

    def run(self, prompt: str, model: str, pdf_path: Optional[str]) -> ProviderResult:
        ...


# _extract_json / _normalize_schema live in arm_llm_native (prompt-side parsing
# helpers). Providers import them lazily to avoid a circular import at module
# load (arm_llm_native imports THIS module for resolve_provider).
def _parse_helpers() -> tuple[Callable, Callable]:
    import arm_llm_native  # noqa: PLC0415 (lazy, intentional -- see above)
    return arm_llm_native._extract_json, arm_llm_native._normalize_schema


class ClaudeCliProvider:
    """The local `claude` CLI in headless print mode (-p). Uses the maintainer's
    Claude Code subscription auth, so it is effectively FREE in-environment (no
    metered API cost) -- the DEFAULT for in-environment authoring.

    The CLI reads the PDF itself via its Read tool; we grant directory access
    with --add-dir so it can reach the form. The schema for a real form is ~30K+
    output tokens, which overflows the CLI's per-message output ceiling, so the
    model WRITES the JSON to a scratch file and we read it back."""

    name = "claude-cli"

    def run(self, prompt: str, model: str, pdf_path: Optional[str]) -> ProviderResult:
        extract_json, normalize_schema = _parse_helpers()
        exe = shutil.which("claude") or "claude"
        outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        # acceptEdits auto-approves the model's Write to the scratch file in
        # outputs/ (an --add-dir grants READ; a headless write would otherwise
        # hang on a permission prompt the -p session cannot answer -- bd 7a9.10).
        cmd = [exe, "-p", "--model", model, "--output-format", "json",
               "--permission-mode", "acceptEdits", "--add-dir", outputs_dir]
        if pdf_path:
            cmd += ["--add-dir", os.path.dirname(os.path.abspath(pdf_path))]
        # The schema for a real form is ~30K+ output tokens -- piping it through
        # the CLI's final message hits the per-message output ceiling and yields
        # truncated/pointer results (observed on I-90, bd 7a9.10; certain on
        # I-589). So the model WRITES the JSON to a scratch file and we read it
        # back.
        scratch = os.path.join(outputs_dir, f"_cli_schema_{os.getpid()}.json")
        if os.path.exists(scratch):
            os.remove(scratch)
        wrapped = (
            prompt
            + "\n\nIMPORTANT -- how to deliver your output: the FormSchema JSON "
            "is far too large for a chat message, so do NOT print it. Instead, "
            "use your Write tool to write the COMPLETE FormSchema JSON object "
            "(and nothing else -- no fences, no commentary) to this exact file "
            "path:\n  "
            + scratch
            + "\nThen end with a final message of just: WROTE OK"
        )
        timeout_s = int(os.getenv("BAKEOFF_CLAUDE_TIMEOUT_S", "1200"))
        try:
            proc = subprocess.run(
                cmd, input=wrapped, capture_output=True, text=True,
                encoding="utf-8", timeout=timeout_s,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"claude CLI exited {proc.returncode}: "
                                   f"{(proc.stderr or proc.stdout)[:500]}")
            envelope = json.loads(proc.stdout)
            if envelope.get("is_error"):
                raise RuntimeError(f"claude CLI error: {envelope.get('result')!r}")
            result_text = envelope.get("result", "")

            schema = None
            if os.path.exists(scratch):
                with open(scratch, encoding="utf-8") as fh:
                    schema = normalize_schema(extract_json(fh.read()))
            else:
                # Older-behavior fallback: the model printed the JSON instead.
                try:
                    schema = normalize_schema(extract_json(result_text))
                except json.JSONDecodeError:
                    schema = None
            if not (isinstance(schema, dict) and schema.get("fields")):
                # Reject empty/fragment parses (a truncated message can "parse"
                # as a single field object). Dump the envelope for diagnosis.
                dbg = os.path.join(outputs_dir, "_claude_cli_fail_envelope.json")
                with open(dbg, "w", encoding="utf-8") as fh:
                    json.dump(envelope, fh, indent=2)
                raise RuntimeError(
                    f"claude CLI produced no usable schema "
                    f"(scratch_file_existed={os.path.exists(scratch)} "
                    f"[deleted on cleanup], "
                    f"subtype={envelope.get('subtype')!r}, "
                    f"num_turns={envelope.get('num_turns')}, "
                    f"result_chars={len(result_text)}); envelope dumped to {dbg}")
        finally:
            if os.path.exists(scratch):
                os.remove(scratch)
        usage = envelope.get("usage") or {}
        tok = {"input": usage.get("input_tokens"),
               "output": usage.get("output_tokens"),
               "cost_usd_equiv": envelope.get("total_cost_usd")}
        return schema, tok


class GeminiProvider:
    """Gemini backend (paid, google-genai SDK, GEMINI_API_KEY). Kept as a
    fallback for when external help is hired and the Gemini path is useful."""

    name = "gemini"

    def run(self, prompt: str, model: str, pdf_path: Optional[str]) -> ProviderResult:
        from google import genai  # lazy: only needed for the gemini path
        from google.genai import types
        extract_json, normalize_schema = _parse_helpers()

        timeout_ms = int(os.getenv("BAKEOFF_GEMINI_TIMEOUT_MS", "600000"))
        client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
        contents: list = []
        if pdf_path:
            contents.append(types.Part.from_bytes(
                data=pathlib.Path(pdf_path).read_bytes(),
                mime_type="application/pdf",
            ))
        contents.append(prompt)

        resp = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=65536,
            ),
        )
        schema = normalize_schema(extract_json(resp.text))
        tok = {}
        usage = getattr(resp, "usage_metadata", None)
        if usage is not None:
            tok = {"input": getattr(usage, "prompt_token_count", None),
                   "output": getattr(usage, "candidates_token_count", None)}
        return schema, tok


# Registry of provider instances by name. A new backend (a hosted API, a better
# model) is added here -- the call site (arm_llm_native.run) never changes.
_REGISTRY: dict[str, LLMProvider] = {
    ClaudeCliProvider.name: ClaudeCliProvider(),
    GeminiProvider.name: GeminiProvider(),
}


def register_provider(provider: LLMProvider) -> None:
    """Register (or override) a provider by its .name. Lets a hosted deployment
    inject its own backend without editing this module."""
    _REGISTRY[provider.name] = provider


def _provider_for_model(model: str) -> str:
    """Name-based default dispatch (preserves arm_llm_native's prior behavior):
    gemini* -> gemini; everything else -> the local claude CLI."""
    return "gemini" if model.lower().startswith("gemini") else "claude-cli"


def resolve_provider(model: str) -> LLMProvider:
    """Pick the backend. EXTRACTOR_PROVIDER overrides (the hosted/remote swap
    knob); otherwise the model name decides. Raises KeyError-with-context for an
    unknown EXTRACTOR_PROVIDER so a typo fails loud, not silently wrong."""
    explicit = os.getenv("EXTRACTOR_PROVIDER")
    name = explicit.strip() if explicit and explicit.strip() else _provider_for_model(model)
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        src = "EXTRACTOR_PROVIDER" if explicit else "model-name dispatch"
        raise KeyError(
            f"unknown LLM provider {name!r} (from {src}); known: {known}") from None
