#!/usr/bin/env python3
"""Gemini extraction arm for the bake-off (bd polyglot-pdf-7a9.4).

Runs a PDF through a strong Gemini model and emits a draft FormSchema. Two modes:

  --mode multimodal : send ONLY the PDF (pixels). Tests pure multimodal extraction
                      -- the model must recover field structure from the rendered
                      page, with no AcroForm layer. (a)+(b) from pixels alone.
  --mode hybrid     : send the PDF AND the deterministic PyMuPDF AcroForm field
                      list. Tests the predicted-strongest arm: ground-truth field
                      structure (a) handed to a top model to fuse + reason (b).

Gemini reads PDFs natively (types.Part.from_bytes, mime application/pdf), so no
pre-render step is needed for the multimodal input.

ASCII-only (cp1252 safe). Usage:

    python scripts/bakeoff/arm_gemini.py --pdf FORM.pdf --mode hybrid \
        --acroform DUMP.json --model gemini-3.1-pro-preview --out OUT.json
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from typing import Optional

from google import genai
from google.genai import types

# Local imports (run from repo root or with this dir on sys.path).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema_contract import SCHEMA_CONTRACT, acroform_field_list  # noqa: E402


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of a model response, tolerating stray fences."""
    t = text.strip()
    # Strip a leading/trailing markdown fence if the model added one.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # Last resort: grab the outermost JSON value, object {...} OR array [...].
        candidates = []
        for o, c in (("{", "}"), ("[", "]")):
            start, end = t.find(o), t.rfind(c)
            if start != -1 and end != -1 and end > start:
                candidates.append((start, t[start:end + 1]))
        # Prefer whichever delimiter appears first in the text.
        for _, frag in sorted(candidates):
            try:
                return json.loads(frag)
            except json.JSONDecodeError:
                continue
        raise


def _client(http_options=None) -> genai.Client:
    """VERTEX-ONLY: every gemini call lands on Vertex (ADC +
    GOOGLE_CLOUD_PROJECT) on the tracked billing project.

    There is NO AI Studio / GEMINI_API_KEY path, and VERTEXAI is NOT consulted --
    the AI Studio gate is closed fleet-wide (maintainer directive 2026-07-28; bd
    polyglot-pdf-f3lm / w99b / kgmn). Delegates to llm_providers so there is ONE
    client-construction path for the whole bakeoff directory; http_options (the
    per-request timeout) threads through unchanged, and the location comes from
    VERTEX_LOCATION (then GOOGLE_CLOUD_LOCATION).
    """
    from llm_providers import _vertex_gemini_client  # noqa: PLC0415 (lazy)
    return _vertex_gemini_client(http_options)


def run(pdf_path: str, mode: str, model: str,
        acroform_path: Optional[str] = None) -> dict:
    # Per-request HTTP timeout (ms) so a stalled call fails fast instead of
    # hanging indefinitely. The i-589 hybrid call (460 widgets, ~129KB field
    # list, 64K output budget) is heavy on Gemini 3.1 Pro and exceeded 8 min;
    # override via BAKEOFF_GEMINI_TIMEOUT_MS. Default 8 min bounds the common case.
    timeout_ms = int(os.getenv("BAKEOFF_GEMINI_TIMEOUT_MS", "480000"))
    client = _client(http_options=types.HttpOptions(timeout=timeout_ms))

    parts: list = [
        types.Part.from_bytes(
            data=pathlib.Path(pdf_path).read_bytes(),
            mime_type="application/pdf",
        )
    ]

    prompt = [SCHEMA_CONTRACT, ""]
    if mode == "hybrid":
        if not acroform_path:
            raise SystemExit("--mode hybrid requires --acroform DUMP.json")
        with open(acroform_path, encoding="utf-8") as fh:
            dump = json.load(fh)
        prompt.append(
            "The PDF is attached AND below is the deterministic AcroForm field "
            "list extracted from the PDF's machine-readable structure (exact "
            "widget names, types, flags, tooltips, choices). Use these EXACT "
            "pdf_field_name values; the attached PDF gives you the printed labels "
            "and conditional logic the AcroForm layer does not carry.\n"
        )
        prompt.append(acroform_field_list(dump))
    else:  # multimodal
        prompt.append(
            "The PDF is attached. Extract the full FormSchema from what is printed "
            "on the pages: every fillable field, its type, label, options, section, "
            "and any conditional logic stated in the instructions."
        )
    parts.append("\n".join(prompt))

    resp = client.models.generate_content(
        model=model,
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
            max_output_tokens=65536,
        ),
    )
    schema = _extract_json(resp.text)
    # A multimodal model sometimes wraps its output. Normalize to the dict the
    # scorer + provenance expect, distinguishing two list cases:
    #   [ {full schema} ]            -> unwrap the single schema object
    #   [ {field}, {field}, ... ]    -> a bare fields array
    if isinstance(schema, list):
        if len(schema) == 1 and isinstance(schema[0], dict) and \
                "fields" in schema[0]:
            schema = schema[0]
        else:
            schema = {"source": "pdf", "fields": schema}
    elif isinstance(schema, dict) and "fields" not in schema:
        for k in ("schema", "form_schema", "FormSchema", "result"):
            inner = schema.get(k)
            if isinstance(inner, dict) and "fields" in inner:
                schema = inner
                break
    # Stamp arm provenance (ignored by the scorer; useful in the output file).
    schema.setdefault("_bakeoff", {})
    schema["_bakeoff"].update({"arm": f"gemini-{mode}", "model": model})
    usage = getattr(resp, "usage_metadata", None)
    if usage is not None:
        schema["_bakeoff"]["tokens"] = {
            "input": getattr(usage, "prompt_token_count", None),
            "output": getattr(usage, "candidates_token_count", None),
        }
    return schema


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Gemini extraction arm.")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--mode", choices=["multimodal", "hybrid"], required=True)
    ap.add_argument("--acroform", default=None, help="AcroForm dump JSON (hybrid)")
    ap.add_argument("--model", default="gemini-3.1-pro-preview")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    schema = run(args.pdf, args.mode, args.model, args.acroform)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2)
    nf = len(schema.get("fields", []))
    tok = schema.get("_bakeoff", {}).get("tokens", {})
    print(f"[wrote {args.out}] arm=gemini-{args.mode} model={args.model} "
          f"fields={nf} tokens={tok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
