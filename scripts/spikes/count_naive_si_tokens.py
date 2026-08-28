"""Token count for the NAIVE arm's system instruction (bd polyglot-pdf-89mt).

Builds the EXACT naive-arm system instruction -- the production full-schema SI
(FormFillingService.build_form_context_message, the same code path
measure_form_session_costs.py's --arm naive uses) with the w7 form's official
booklet text appended (apply_naive_si), imported directly from the harness
module so this script can never drift from what the harness actually sends --
plus the tool-declarations payload the session would carry (SPELLBACK_TOOL_
ENABLED defaults on, so name_spellback is included), and calls Vertex
count_tokens (a metadata call, NOT a generate call -- zero live-model spend)
against the 2.5 flash tokenizer.

count_tokens rejects Live-API model ids (the Live surface and the
Generative/count_tokens surface are different APIs); this script tries the
harness's live model id first and falls back to the base gemini-2.5-flash
tokenizer id on rejection, printing which one actually answered so a reader
never has to guess which tokenizer priced the numbers below.

Usage (from repo root, with Vertex ADC configured):
    backend/.venv/Scripts/python.exe scripts/spikes/count_naive_si_tokens.py

Do NOT run this as part of routine test collection -- it makes a real (free)
Vertex API call. The verifier runs it manually.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SPIKES_DIR = str(Path(__file__).resolve().parent)
if _SPIKES_DIR not in sys.path:
    sys.path.insert(0, _SPIKES_DIR)

from backend.config import MODEL_NATIVE_STANDARD_VERTEX  # noqa: E402
from backend.services.form_filling_service import FormFillingService  # noqa: E402

# Reuse the harness's OWN functions -- never reimplement the naive-SI shape
# here, or this script and the harness could silently price different text.
from measure_form_session_costs import (  # noqa: E402
    W7_SCHEMA_PATH,
    apply_naive_si,
    load_schema,
    naive_si_booklet_suffix,
    _make_settings,
)

# count_tokens is a separate API surface from the Live session and does not
# recognize Live-only model ids (e.g. gemini-live-2.5-flash-native-audio).
# Try the harness's actual live model id first (in case that ever changes to
# something count_tokens DOES accept), then fall back to the base tokenizer
# id every 2.5-flash variant shares.
_FALLBACK_TOKENIZER_MODEL = "gemini-2.5-flash"


def build_naive_si_and_tools() -> tuple[str, list[dict]]:
    """Build the exact naive-arm SI + tool-declarations payload, via the SAME
    code path measure_form_session_costs.py --arm naive uses: production's
    build_form_context_message (full form, one session -- the naive arm takes
    the unbounded arm's schema shape) with the w7 booklet appended."""
    schema = load_schema("w7")
    settings = _make_settings("naive", trigger=12_000, window=9_000,
                              compression=False, continuous=False,
                              derive_compression=False)
    # Multi-module get_settings patch (the CLAUDE.md jnjj.25 trap, and the
    # reason this script once over-counted by the spell-back addendum):
    # ai_context reads its OWN module-level get_settings for the
    # SPELLBACK_TOOL_ENABLED SI addendum, so without patching it this script
    # rendered the addendum per the ENV flag while the real naive run (whose
    # harness applies the full patch) renders it per the naive arm's pinned
    # False -- a ~240-token drift from what the harness actually sends.
    import backend.config as _config_mod
    import backend.services.ai_context as _ai_context_mod
    patch_targets = [_config_mod, _ai_context_mod]
    originals = [(mod, mod.get_settings) for mod in patch_targets]
    for mod, _ in originals:
        mod.get_settings = lambda s=settings: s
    try:
        service = FormFillingService(live_ai=None, settings=settings)
        arm_schema = {"form_metadata": schema.get("form_metadata", {}),
                      "fields": schema["fields"]}
        si = service.build_form_context_message(
            arm_schema, {}, section_number=1, total_sections=1,
            section_label="Full Form", previous_spoken_names=[])
        si = apply_naive_si(si, schema)
        tools = service._build_tool_declarations()
    finally:
        for mod, orig in originals:
            mod.get_settings = orig
    return si, tools


def _count_tokens(client, model: str, si: str, tools: list[dict]):
    """One count_tokens call against `model`. Returns the response, or raises
    on a rejected model id (caller handles the fallback)."""
    from google.genai import types

    tools_config = [{"function_declarations": tools}] if tools else None
    config = types.CountTokensConfig(tools=tools_config) if tools_config else None
    # count_tokens' `contents` argument is the payload whose tokens are
    # counted; the SI is passed via config.system_instruction so it prices
    # the same way it does in a real session (system_instruction tokens are
    # billed, and the Live adapter sends this text as the session's system
    # instruction, not as a content turn).
    config = types.CountTokensConfig(
        system_instruction=si,
        tools=tools_config,
    )
    return client.models.count_tokens(model=model, contents="", config=config)


def main() -> int:
    si, tools = build_naive_si_and_tools()
    print(f"naive-arm SI: {len(si)} chars "
          f"(booklet suffix: {len(naive_si_booklet_suffix(load_schema('w7')))} chars)")
    print(f"tool declarations: {len(tools)} tools "
          f"({', '.join(t.get('name', '?') for t in tools)})")

    from google import genai

    project = os.getenv("GOOGLE_CLOUD_PROJECT", "polyglot-demo-aa709")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    client = genai.Client(vertexai=True, project=project, location=location)

    tried = [MODEL_NATIVE_STANDARD_VERTEX, _FALLBACK_TOKENIZER_MODEL]
    resp = None
    model_used = None
    for model in tried:
        try:
            resp = _count_tokens(client, model, si, tools)
            model_used = model
            break
        except Exception as exc:  # noqa: BLE001
            print(f"[count_tokens] model={model!r} rejected "
                  f"({type(exc).__name__}: {exc}); trying next fallback")
    if resp is None:
        print("count_tokens FAILED against every candidate model "
              f"({tried}); cannot report a token count.")
        return 1

    print(f"tokenizer used: {model_used}")
    total = getattr(resp, "total_tokens", None)
    # CountTokensResponse doesn't split SI vs tools vs contents on its own;
    # get the SI-only and SI+tools-only counts with two more (free) calls so
    # the three numbers the docstring promises are all genuinely measured,
    # not inferred by subtraction from a single call whose config differs.
    si_only_resp = _count_tokens(client, model_used, si, [])
    si_only = getattr(si_only_resp, "total_tokens", None)
    tools_tokens = (total - si_only) if (total is not None and si_only is not None) else None

    print(f"SI tokens: {si_only}")
    print(f"tools tokens: {tools_tokens}")
    print(f"total tokens (SI + tools): {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
