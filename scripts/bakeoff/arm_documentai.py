#!/usr/bin/env python3
"""Document AI (Form Parser) extraction arm for the bake-off (bd polyglot-pdf-7a9.4).

Sends a PDF to a GCP Document AI Form Parser processor, then fuses the OCR/layout
output with the deterministic PyMuPDF AcroForm dump and a strong LLM (Gemini 3.x
Pro) to synthesize a FormSchema -- the "documentai-hybrid" arm.

Document AI provides (a) OCR layout: printed labels associated with input boxes,
bounding boxes, and a text/checkbox classification. It does NOT read the AcroForm
layer (exact widget names, flags, choice values) and does NOT recover (b)
conditional logic. So this arm feeds BOTH the DocAI form-fields AND the PyMuPDF
AcroForm dump to the LLM, exactly like the gemini-hybrid arm but with DocAI's
label<->box associations added as an extra signal.

Auth: Application Default Credentials (gcloud auth application-default login).
Requires a provisioned Form Parser processor; pass its id via --processor (or the
DOCAI_PROCESSOR_ID env) plus --project and --location.

ASCII-only (cp1252 safe). Usage:

    python scripts/bakeoff/arm_documentai.py --pdf FORM.pdf \
        --project polyglot-demo-aa709 --location us --processor PROCESSOR_ID \
        --acroform DUMP.json --model gemini-3.1-pro-preview --out OUT.json
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Optional

from google.cloud import documentai
from google import genai
from google.genai import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema_contract import SCHEMA_CONTRACT, acroform_field_list  # noqa: E402
from arm_gemini import _extract_json  # noqa: E402  reuse the tolerant JSON parser


def docai_form_fields(pdf_path: str, project: str, location: str,
                      processor_id: str) -> dict:
    """Run the PDF through Document AI Form Parser; return a compact dump."""
    client = documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": f"{location}-documentai.googleapis.com"}
    )
    name = client.processor_path(project, location, processor_id)
    raw = documentai.RawDocument(
        content=pathlib.Path(pdf_path).read_bytes(),
        mime_type="application/pdf",
    )
    result = client.process_document(
        request=documentai.ProcessRequest(name=name, raw_document=raw)
    )
    doc = result.document

    def _text(anchor) -> str:
        """Resolve a text anchor to its substring of document.text."""
        if not anchor or not anchor.text_segments:
            return ""
        out = []
        for seg in anchor.text_segments:
            start = int(seg.start_index or 0)
            end = int(seg.end_index or 0)
            out.append(doc.text[start:end])
        return " ".join(t.strip() for t in out if t.strip())

    pages = []
    for pno, page in enumerate(doc.pages):
        fields = []
        for ff in page.form_fields:
            fields.append({
                "name": _text(ff.field_name.text_anchor) if ff.field_name else "",
                "value": _text(ff.field_value.text_anchor) if ff.field_value else "",
                "value_type": getattr(ff, "value_type", "") or "",
            })
        pages.append({"page": pno, "form_fields": fields})
    return {
        "source_pdf": pdf_path,
        "page_count": len(doc.pages),
        "form_field_count": sum(len(p["form_fields"]) for p in pages),
        "pages": pages,
    }


def _docai_field_list(dump: dict) -> str:
    lines = []
    for pg in dump.get("pages", []):
        for ff in pg["form_fields"]:
            nm = ff["name"].replace("\n", " ").strip()
            vt = f" [{ff['value_type']}]" if ff["value_type"] else ""
            lines.append(f"  page={pg['page']} label={nm!r}{vt}")
    header = (f"DOCUMENT AI FORM FIELDS ({dump.get('form_field_count')} "
              f"label/box associations across {dump.get('page_count')} pages):")
    return header + "\n" + "\n".join(lines)


def _client(http_options=None) -> genai.Client:
    """VERTEX-ONLY gemini client for the enhancement call (the DocAI client is
    separate -- project/location args).

    Every gemini call lands on Vertex (ADC + GOOGLE_CLOUD_PROJECT) on the tracked
    billing project. There is NO AI Studio / GEMINI_API_KEY path and VERTEXAI is
    NOT consulted -- the AI Studio gate is closed fleet-wide (maintainer directive
    2026-07-28; bd polyglot-pdf-f3lm / w99b / kgmn). Delegates to llm_providers so
    the whole bakeoff directory has ONE client-construction path; http_options
    threads through unchanged, and the location comes from VERTEX_LOCATION (then
    GOOGLE_CLOUD_LOCATION).
    """
    from llm_providers import _vertex_gemini_client  # noqa: PLC0415 (lazy)
    return _vertex_gemini_client(http_options)


def run(pdf_path: str, project: str, location: str, processor_id: str,
        acroform_path: str, model: str, docai_dump: Optional[dict] = None) -> dict:
    # Accept a pre-computed DocAI dump so --dump-docai does not bill a second
    # process_document call (fresh-eyes PR #101).
    if docai_dump is None:
        docai_dump = docai_form_fields(pdf_path, project, location, processor_id)
    with open(acroform_path, encoding="utf-8") as fh:
        acro = json.load(fh)

    client = _client(http_options=types.HttpOptions(timeout=480_000))
    prompt = "\n".join([
        SCHEMA_CONTRACT, "",
        "Three inputs describe the SAME PDF (attached):",
        "1) The PDF pages (printed labels, sections, conditional instructions).",
        "2) The deterministic AcroForm field list (EXACT widget names/types/flags/"
        "tooltips/choices) -- use these EXACT pdf_field_name values.",
        "3) Document AI Form Parser output (OCR label<->input-box associations).",
        "Fuse all three: AcroForm gives ground-truth field identity; DocAI + the "
        "PDF give the printed labels and conditional logic. Emit the FormSchema.",
        "",
        acroform_field_list(acro),
        "",
        _docai_field_list(docai_dump),
    ])
    resp = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=pathlib.Path(pdf_path).read_bytes(),
                                  mime_type="application/pdf"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
            max_output_tokens=65536,
        ),
    )
    schema = _extract_json(resp.text)
    if isinstance(schema, list):
        if len(schema) == 1 and isinstance(schema[0], dict) and "fields" in schema[0]:
            schema = schema[0]
        else:
            schema = {"source": "pdf", "fields": schema}
    schema.setdefault("_bakeoff", {})
    schema["_bakeoff"].update({
        "arm": "documentai-hybrid", "model": model,
        "docai_form_fields": docai_dump["form_field_count"],
    })
    usage = getattr(resp, "usage_metadata", None)
    if usage is not None:
        schema["_bakeoff"]["tokens"] = {
            "input": getattr(usage, "prompt_token_count", None),
            "output": getattr(usage, "candidates_token_count", None),
        }
    return schema


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Document AI hybrid extraction arm.")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT",
                                                   "polyglot-demo-aa709"))
    ap.add_argument("--location", default="us")
    ap.add_argument("--processor", default=os.getenv("DOCAI_PROCESSOR_ID"),
                    help="Form Parser processor id (or DOCAI_PROCESSOR_ID env)")
    ap.add_argument("--acroform", required=True)
    ap.add_argument("--model", default="gemini-3.1-pro-preview")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dump-docai", default=None,
                    help="optional path to also write the raw DocAI form-field dump")
    args = ap.parse_args(argv)

    if not args.processor:
        raise SystemExit("ERROR: no processor id (pass --processor or set "
                         "DOCAI_PROCESSOR_ID). Create a Form Parser processor "
                         "first.")

    dump = None
    if args.dump_docai:
        dump = docai_form_fields(args.pdf, args.project, args.location,
                                 args.processor)
        with open(args.dump_docai, "w", encoding="utf-8") as fh:
            json.dump(dump, fh, indent=2)
        print(f"[wrote {args.dump_docai}] {dump['form_field_count']} docai fields")

    # Reuse the dump if --dump-docai already fetched it (avoid a 2nd billed call).
    schema = run(args.pdf, args.project, args.location, args.processor,
                 args.acroform, args.model, docai_dump=dump)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2)
    nf = len(schema.get("fields", []))
    tok = schema.get("_bakeoff", {}).get("tokens", {})
    print(f"[wrote {args.out}] arm=documentai-hybrid model={args.model} "
          f"fields={nf} tokens={tok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
