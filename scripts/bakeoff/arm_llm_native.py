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
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema_contract import SCHEMA_CONTRACT  # noqa: E402
from structural_enrich import (  # noqa: E402
    DEFAULT_DISABLED, SIGNALS, enrich, enriched_field_list,
)


# Anti-hallucination contract addendum (Q4): the model MUST copy widget names
# verbatim from the enriched list, never invent or normalize them.
ANTI_HALLUCINATION = """\
CRITICAL -- pdf_field_name fidelity (this is graded): every pdf_field_name you
emit MUST be copied CHARACTER-FOR-CHARACTER from the `name=` value of a field in
the ENRICHED FIELD LIST below. Do NOT invent, abbreviate, normalize, or
re-case any widget name. If you consolidate several widgets into one logical
field (e.g. a radio set), put each widget's exact `name=` value on its
option.pdf_field_name. Every field in the enriched list must appear exactly once
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

    Shows the model the TARGET conventions it should imitate: how sections are
    id'd/labeled, and a couple of fully-formed fields (a plain text field, a
    consolidated radio/checkbox set with options, and a field carrying a
    relationship key). We deliberately keep it small -- it teaches STYLE, not the
    target form's content (exactly 3 exemplar fields).
    """
    with open(truth_path, encoding="utf-8") as fh:
        truth = json.load(fh)
    parts = truth.get("parts") or []
    sections = truth.get("sections") or []
    fields = truth.get("fields") or []

    # Pick exemplar fields: 1 plain, 1 with options, 1 with a relationship.
    plain = next((f for f in fields if f.get("type") in ("text", "date", "number")
                  and not f.get("options")), None)
    with_opts = next((f for f in fields if f.get("options")), None)
    rel_keys = ("show_if", "controls_fields", "copy_to", "overflow_to_supplement",
                "conditional_logic", "conditional_behavior")
    with_rel = next((f for f in fields if any(f.get(k) for k in rel_keys)), None)

    def trim(f):
        if not f:
            return None
        keep = ("id", "name", "type", "section_id", "pdf_field_name", "options",
                "validation") + rel_keys
        return {k: f[k] for k in keep if f.get(k) is not None}

    exemplar = {
        "form_metadata": {k: truth.get("form_metadata", {}).get(k)
                          for k in ("title", "form_number") if truth.get("form_metadata", {}).get(k)},
        "parts": [{"id": p.get("id"), "label": p.get("label")} for p in parts[:3]],
        "sections": [{"id": s.get("id"), "label": s.get("label")} for s in sections[:6]],
        "fields": [trim(f) for f in (plain, with_opts, with_rel) if f],
    }
    note = (
        "FEW-SHOT CONVENTION EXAMPLE -- this is a DIFFERENT form's hand-authored "
        "gold schema, shown ONLY so you imitate its STYLE: how `id` and "
        "`section_id` strings are formed, how a consolidated options[] field is "
        "shaped, and how a relationship key (show_if/copy_to/...) is attached. "
        "Match THIS convention for section_id and field id slugs. Do NOT copy its "
        "content -- the form you are extracting is different.\n"
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
                 order_caveat: bool = True) -> str:
    """Assemble the full text prompt (contract + anti-hallucination + few-shot +
    enriched bundle). When pdf_path is given, the prompt INSTRUCTS the model to
    read that PDF (the Claude CLI reads it via its Read tool; the Gemini backend
    attaches the bytes separately and ignores this instruction's file path).
    `disabled` drops enrichment signals (DEFAULT drops row_cluster per the
    7a9.10 trim); `order_caveat` (DEFAULT True) labels the sweep rank honestly."""
    with open(acroform_path, encoding="utf-8") as fh:
        dump = json.load(fh)
    enrich(dump, disabled=disabled)

    parts = [SCHEMA_CONTRACT, "", ANTI_HALLUCINATION, ""]
    if fewshot_truth:
        parts.append(build_fewshot(fewshot_truth))
        parts.append("")
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
    return "\n".join(parts)


def _run_gemini(prompt: str, model: str, pdf_path: Optional[str]) -> tuple[dict, dict]:
    """Gemini backend (paid, google-genai SDK). Returns (schema, token_info)."""
    from google import genai  # lazy: only needed for the gemini path
    from google.genai import types

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
    schema = _normalize_schema(_extract_json(resp.text))
    tok = {}
    usage = getattr(resp, "usage_metadata", None)
    if usage is not None:
        tok = {"input": getattr(usage, "prompt_token_count", None),
               "output": getattr(usage, "candidates_token_count", None)}
    return schema, tok


def _run_claude_cli(prompt: str, model: str, pdf_path: Optional[str]) -> tuple[dict, dict]:
    """Claude backend via the local `claude` CLI in headless print mode.

    Uses the maintainer's Claude Code subscription auth (free in-environment).
    The CLI reads the PDF itself via its Read tool; we grant directory access
    with --add-dir so it can reach the form. Returns (schema, token_info).
    """
    exe = shutil.which("claude") or "claude"
    outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "outputs")
    # acceptEdits auto-approves the model's Write to the scratch file in
    # outputs/ (an --add-dir grants READ; a headless write would otherwise hang
    # on a permission prompt the -p session cannot answer -- bd 7a9.10).
    cmd = [exe, "-p", "--model", model, "--output-format", "json",
           "--permission-mode", "acceptEdits", "--add-dir", outputs_dir]
    if pdf_path:
        cmd += ["--add-dir", os.path.dirname(os.path.abspath(pdf_path))]
    # The schema for a real form is ~30K+ output tokens -- piping it through the
    # CLI's final message hits the per-message output ceiling and yields
    # truncated/pointer results (observed on I-90, bd 7a9.10; certain on I-589).
    # So the model WRITES the JSON to a scratch file and we read it back.
    scratch = os.path.join(outputs_dir, f"_cli_schema_{os.getpid()}.json")
    if os.path.exists(scratch):
        os.remove(scratch)
    wrapped = (
        prompt
        + "\n\nIMPORTANT -- how to deliver your output: the FormSchema JSON is "
        "far too large for a chat message, so do NOT print it. Instead, use "
        "your Write tool to write the COMPLETE FormSchema JSON object (and "
        "nothing else -- no fences, no commentary) to this exact file path:\n  "
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
                schema = _normalize_schema(_extract_json(fh.read()))
        else:
            # Older-behavior fallback: the model printed the JSON instead.
            try:
                schema = _normalize_schema(_extract_json(result_text))
            except json.JSONDecodeError:
                schema = None
        if not (isinstance(schema, dict) and schema.get("fields")):
            # Reject empty/fragment parses (a truncated message can "parse" as
            # a single field object). Dump the envelope for diagnosis.
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


def run(pdf_path: str, acroform_path: str, model: str,
        fewshot_truth: Optional[str] = None,
        send_pdf: bool = True,
        disabled: frozenset[str] = DEFAULT_DISABLED,
        order_caveat: bool = True) -> dict:
    pdf_for_prompt = pdf_path if send_pdf else None
    prompt = build_prompt(acroform_path, fewshot_truth, pdf_for_prompt,
                          disabled=disabled, order_caveat=order_caveat)

    # Only `gemini*` takes the SDK path; EVERY other model name (claude/opus/
    # sonnet/haiku -- or anything else) routes to the local `claude` CLI, which
    # will itself reject a name it doesn't recognize. So an unknown model surfaces
    # as a CLI error, not a silent wrong backend.
    is_gemini = model.lower().startswith("gemini")
    backend = "gemini" if is_gemini else "claude-cli"
    if is_gemini:
        schema, tok = _run_gemini(prompt, model, pdf_for_prompt)
    else:
        schema, tok = _run_claude_cli(prompt, model, pdf_for_prompt)

    schema.setdefault("_bakeoff", {})
    schema["_bakeoff"].update({
        "arm": "llm-native", "model": model, "backend": backend,
        "enriched": True, "fewshot": bool(fewshot_truth), "pdf_sent": send_pdf,
        "disabled_signals": sorted(disabled),
        "order_caveat": order_caveat,
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
                 disabled=disabled, order_caveat=not args.no_order_caveat)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2)
    nf = len(schema.get("fields", []))
    tok = schema.get("_bakeoff", {}).get("tokens", {})
    print(f"[wrote {args.out}] arm=llm-native model={args.model} "
          f"fewshot={bool(args.fewshot_truth)} pdf={not args.no_pdf} "
          f"disabled={sorted(disabled)} order_caveat={not args.no_order_caveat} "
          f"fields={nf} tokens={tok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
