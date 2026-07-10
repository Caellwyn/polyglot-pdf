#!/usr/bin/env python3
"""LLM-native extractor arm (bd polyglot-pdf-7a9.9 prototype).

The 7a9.9 thesis, made runnable: RETIRE the USCIS heuristic layer and move ALL
structural reasoning onto a strong LLM fed a deliberately-assembled bundle of
generic structural signals. This arm differs from the existing
`*-hybrid` bake-off arms (arm_gemini.py --mode hybrid) on exactly the variables
the thesis proposes to change, so a head-to-head isolates the architecture:

  hybrid  (baseline): raw AcroForm field list (name order) + PDF + generic contract
  llm-native (this) : ENRICHED field list (tab order, row clusters, name tokens)
                      + PDF + contract + optional FEW-SHOT exemplar distilled from a
                      DIFFERENT form's gold schema + explicit anti-hallucination rule

Few-shot source is cross-form on purpose: scoring on I-90 uses an I-589-derived
exemplar (and vice versa), so we never train on the test form's own gold schema.

Pluggable model via --model. Two backends, dispatched by model name:

  claude* / opus* / sonnet* / haiku*  -> the local `claude` CLI in headless
      print mode (-p). This uses the maintainer's existing Claude Code
      subscription auth, so it is effectively FREE in-environment (no metered
      API token cost). This is the DEFAULT (claude-opus-4-8) because schema
      extraction runs in the maintainer's environment.
  gemini*                             -> the google-genai SDK with GEMINI_API_KEY
      (metered/paid). Kept as a fallback in case external help is hired and the
      Gemini path is useful for them.

ASCII only (cp1252 safe).

Usage:
    python scripts/bakeoff/arm_llm_native.py --pdf FORM.pdf \
        --acroform DUMP.json --fewshot-truth OTHER_FORM_TRUTH.json \
        --model claude-opus-4-8 --out OUT.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_providers import resolve_provider  # noqa: E402
from schema_contract import SCHEMA_CONTRACT, acroform_field_list  # noqa: E402
from structural_enrich import (  # noqa: E402
    DEFAULT_DISABLED, SIGNALS, enrich, enriched_field_list,
)


# Anti-hallucination contract addendum (Q4): the model MUST copy widget names
# verbatim from the field list, never invent or normalize them. Mode-neutral
# wording ("FIELD LIST", not "ENRICHED FIELD LIST") so it is accurate for BOTH
# the plain claude-hybrid list and the enriched bundle (bd 7a9.12 -- the plain
# mode does not present an "enriched" list, and a contradictory label in this
# graded instruction could confuse a literal model).
ANTI_HALLUCINATION = """\
CRITICAL -- pdf_field_name fidelity (this is graded): every pdf_field_name you
emit MUST be copied CHARACTER-FOR-CHARACTER from the `name=` value of a field in
the FIELD LIST below. Do NOT invent, abbreviate, normalize, or
re-case any widget name. If you consolidate several widgets into one logical
field (e.g. a radio set), put each widget's exact `name=` value on its
option.pdf_field_name. Every field in the field list must appear exactly once
in your output (as a field or as an option of a consolidated field).
"""


def _extract_json(text: str) -> dict:
    t = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # The CLI model can wrap the schema in PROSE -- narration before the JSON
        # ("Let me build the schema directly.\n{...}") and/or a trailing remark
        # after it. A naive "first { or [" grabs a bracket inside the prose and
        # parses a tiny fragment. So scan EVERY { and [ position, raw_decode each,
        # and keep the BEST parse: a dict carrying "fields" wins; otherwise the
        # one spanning the most characters (the real schema, not a stray fragment).
        dec = json.JSONDecoder()
        best = None  # (priority, length, obj): priority 1 = has "fields"
        for i, ch in enumerate(t):
            if ch not in "{[":
                continue
            try:
                obj, end = dec.raw_decode(t[i:])
            except json.JSONDecodeError:
                continue
            has_fields = isinstance(obj, dict) and "fields" in obj
            cand = (1 if has_fields else 0, end, obj)
            if best is None or cand[:2] > best[:2]:
                best = cand
        if best is not None:
            return best[2]
        raise


def build_fewshot(truth_path: str) -> str:
    """Distill a few-shot convention exemplar from a DIFFERENT form's gold schema.

    Shows the model the TARGET conventions it should imitate: a couple of
    fully-formed fields (a plain text field, a consolidated radio/checkbox set
    with options, and a field carrying a relationship key). We deliberately
    keep it small -- it teaches STYLE, not the target form's content (exactly 3
    exemplar fields). Divisions (parts/sections/section_id) are stripped: the
    contract tells the model NOT to emit them (derived post-extraction, bd
    6cfu.2), so the exemplar must not showcase them either.
    """
    with open(truth_path, encoding="utf-8") as fh:
        truth = json.load(fh)
    fields = truth.get("fields") or []

    # Pick exemplar fields: 1 plain, 1 with options, 1 with a relationship.
    plain = next((f for f in fields if f.get("type") in ("text", "date", "number")
                  and not f.get("options")), None)
    with_opts = next((f for f in fields if f.get("options")), None)
    # controls_fields / conditional_fields are REMOVED v1 mechanisms (bd
    # polyglot-pdf-c3y6) -- excluded here so the few-shot exemplar never
    # showcases a populated controls_fields example to imitate.
    rel_keys = ("show_if", "copy_to", "overflow_to_supplement",
                "conditional_logic", "conditional_behavior")
    with_rel = next((f for f in fields if any(f.get(k) for k in rel_keys)), None)

    def trim(f):
        if not f:
            return None
        keep = ("id", "name", "type", "pdf_field_name", "options",
                "validation") + rel_keys
        return {k: f[k] for k in keep if f.get(k) is not None}

    exemplar = {
        "form_metadata": {k: truth.get("form_metadata", {}).get(k)
                          for k in ("title", "form_number") if truth.get("form_metadata", {}).get(k)},
        "fields": [trim(f) for f in (plain, with_opts, with_rel) if f],
    }
    note = (
        "FEW-SHOT CONVENTION EXAMPLE -- this is a DIFFERENT form's hand-authored "
        "gold schema, shown ONLY so you imitate its STYLE: how `id` strings are "
        "formed, how a consolidated options[] field is shaped, and how a "
        "relationship key (show_if/copy_to/...) is attached. Match THIS "
        "convention for field id slugs. Do NOT copy its content -- the form you "
        "are extracting is different.\n"
    )
    return note + json.dumps(exemplar, ensure_ascii=True, indent=2)


def _normalize_schema(schema) -> dict:
    """Normalize a model's JSON output to the {..., "fields": [...]} dict shape."""
    if isinstance(schema, list):
        if len(schema) == 1 and isinstance(schema[0], dict) and "fields" in schema[0]:
            return schema[0]
        return {"source": "pdf", "fields": schema}
    if isinstance(schema, dict) and "fields" not in schema:
        for k in ("schema", "form_schema", "FormSchema", "result"):
            inner = schema.get(k)
            if isinstance(inner, dict) and "fields" in inner:
                return inner
    return schema


def build_prompt(acroform_path: str, fewshot_truth: Optional[str],
                 pdf_path: Optional[str],
                 disabled: frozenset[str] = DEFAULT_DISABLED,
                 order_caveat: bool = True,
                 plain: bool = False,
                 group_candidates: bool = False) -> str:
    """Assemble the full text prompt (contract + anti-hallucination + few-shot +
    field list). When pdf_path is given, the prompt INSTRUCTS the model to
    read that PDF (the Claude CLI reads it via its Read tool; the Gemini backend
    attaches the bytes separately and ignores this instruction's file path).
    `disabled` drops enrichment signals (DEFAULT drops row_cluster per the
    7a9.10 trim); `order_caveat` (DEFAULT True) labels the sweep rank honestly.

    `plain` (bd 7a9.12 / B1) renders the PLAIN AcroForm field list
    (acroform_field_list, name order) instead of the enriched bundle -- the
    "claude-hybrid" arm, on the SAME Claude-CLI backend + scorer as the enriched
    arm, so the I-90 prompt bake-off is apples-to-apples. 7a9.11 found the
    enriched bundle REGRESSES vs plain hybrid on the (a)/relationship metrics;
    B1 re-confirms which wins on I-90 and ships it."""
    with open(acroform_path, encoding="utf-8") as fh:
        dump = json.load(fh)

    parts = [SCHEMA_CONTRACT, "", ANTI_HALLUCINATION, ""]
    if fewshot_truth:
        parts.append(build_fewshot(fewshot_truth))
        parts.append("")

    # Deterministic pre-grouping candidates (bd h76m.12): suggest, don't
    # decide -- the block presents structurally-mined widget families for the
    # model to adopt as one field or split. Flag-gated (default OFF) so
    # eval_extraction can run the with/without ablation.
    candidates_block = ""
    if group_candidates:
        from group_candidates import (  # noqa: E402 (sibling module)
            find_group_candidates, render_candidates_block,
        )
        candidates_block = render_candidates_block(find_group_candidates(dump))

    if plain:
        # Plain claude-hybrid: raw AcroForm field list, no enrichment.
        if pdf_path:
            parts.append(
                "Below is the deterministic PyMuPDF AcroForm field list (exact "
                "widget names, types, flags, tooltips). The source PDF is at: "
                + os.path.abspath(pdf_path) + " -- READ IT for the printed labels "
                "and conditional text. Reason over BOTH.\n"
            )
        else:
            parts.append(
                "Below is the deterministic PyMuPDF AcroForm field list. No PDF "
                "pixels are provided -- reason from the list alone.\n"
            )
        parts.append(acroform_field_list(dump))
        if candidates_block:
            parts.append("")
            parts.append(candidates_block)
        return "\n".join(parts)

    enrich(dump, disabled=disabled)
    if pdf_path:
        parts.append(
            "Below is the ENRICHED, generic structural bundle extracted "
            "deterministically from the PDF -- no form-specific heuristics, just "
            "the machine-readable AcroForm layer plus generic geometry signals. "
            "The source PDF is at: " + os.path.abspath(pdf_path) + " -- READ IT "
            "for the printed labels and conditional text. Reason over BOTH: use "
            "the enriched list for exact field structure and the PDF for meaning "
            "and relationships.\n"
        )
    else:
        parts.append(
            "Below is the ENRICHED, generic structural bundle extracted "
            "deterministically from the PDF. No PDF pixels are provided (ablation) "
            "-- reason from the bundle alone.\n"
        )
    parts.append(enriched_field_list(dump, order_caveat=order_caveat))
    if candidates_block:
        parts.append("")
        parts.append(candidates_block)
    return "\n".join(parts)


def run(pdf_path: str, acroform_path: str, model: str,
        fewshot_truth: Optional[str] = None,
        send_pdf: bool = True,
        disabled: frozenset[str] = DEFAULT_DISABLED,
        order_caveat: bool = True,
        plain: bool = False,
        group_candidates: bool = False) -> dict:
    pdf_for_prompt = pdf_path if send_pdf else None
    prompt = build_prompt(acroform_path, fewshot_truth, pdf_for_prompt,
                          disabled=disabled, order_caveat=order_caveat,
                          plain=plain, group_candidates=group_candidates)

    # The LLM out-call is behind a provider seam (bd 7a9.17, llm_providers.py):
    # EXTRACTOR_PROVIDER overrides; otherwise the model name dispatches (gemini*
    # -> the paid SDK, everything else -> the local `claude` CLI, which itself
    # rejects a name it doesn't recognize -- so an unknown model surfaces as a
    # CLI error, not a silent wrong backend). The seam is the swap point for a
    # remote/hosted/better-model backend later.
    provider = resolve_provider(model)
    backend = provider.name
    schema, tok = provider.run(prompt, model, pdf_for_prompt)

    schema.setdefault("_bakeoff", {})
    schema["_bakeoff"].update({
        "arm": "claude-hybrid-plain" if plain else "llm-native",
        "model": model, "backend": backend,
        "enriched": not plain, "fewshot": bool(fewshot_truth), "pdf_sent": send_pdf,
        "disabled_signals": [] if plain else sorted(disabled),
        "order_caveat": False if plain else order_caveat,
        "group_candidates": group_candidates,
    })
    if tok:
        schema["_bakeoff"]["tokens"] = tok
    return schema


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="LLM-native extractor arm (7a9.9).")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--acroform", required=True, help="acroform_dump.py JSON")
    ap.add_argument("--fewshot-truth", default=None,
                    help="a DIFFERENT form's gold schema, for the convention few-shot")
    ap.add_argument("--no-pdf", action="store_true",
                    help="ablation: send ONLY the enriched bundle, no PDF pixels")
    # DEFAULT signal set is the 7a9.10 trim: row_cluster dropped (DEFAULT_DISABLED),
    # honest geometric-sweep order labeling on. The ablation flags below override.
    ap.add_argument("--disable", action="append", choices=SIGNALS, default=None,
                    help="ablation: drop this enrichment signal on TOP of the "
                         "default trim (repeatable; bd 7a9.10)")
    ap.add_argument("--full-bundle", action="store_true",
                    help="ablation: re-enable ALL signals incl. row_cluster "
                         "(undo the 7a9.10 default trim)")
    ap.add_argument("--no-order-caveat", action="store_true",
                    help="ablation: drop the honest geometric-sweep framing and "
                         "label the rank as 'reading order' (the old 7a9.9 text)")
    ap.add_argument("--plain", action="store_true",
                    help="claude-hybrid mode (bd 7a9.12/B1): plain AcroForm field "
                         "list, no enrichment -- the prompt B1 bakes against the "
                         "enriched arm on I-90 (same backend + scorer)")
    ap.add_argument("--model", default="claude-opus-4-8",
                    help="claude-* (local CLI, free in-env; DEFAULT) or "
                         "gemini-* (paid SDK, fallback)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    if args.full_bundle:
        disabled = frozenset(args.disable or [])
    else:
        disabled = DEFAULT_DISABLED | frozenset(args.disable or [])

    schema = run(args.pdf, args.acroform, args.model,
                 fewshot_truth=args.fewshot_truth, send_pdf=not args.no_pdf,
                 disabled=disabled, order_caveat=not args.no_order_caveat,
                 plain=args.plain)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2)
    nf = len(schema.get("fields", []))
    tok = schema.get("_bakeoff", {}).get("tokens", {})
    arm = "claude-hybrid-plain" if args.plain else "llm-native"
    print(f"[wrote {args.out}] arm={arm} model={args.model} "
          f"fewshot={bool(args.fewshot_truth)} pdf={not args.no_pdf} "
          f"plain={args.plain} "
          f"fields={nf} tokens={tok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
