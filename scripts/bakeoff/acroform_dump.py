#!/usr/bin/env python3
"""Deterministic PyMuPDF AcroForm dump -- the machine-readable field layer.

Throwaway research tool for the extractor bake-off (bd polyglot-pdf-7a9.4). This
is NOT the old pdf_schema_extractor (which we deliberately do not reuse); it is a
fresh, minimal pass that reads ONLY what the PDF's AcroForm structure exposes
directly -- the layer OCR/multimodal tools cannot see and would otherwise
hallucinate from pixels:

  - widget name (the exact /T field name, full dotted path)
  - widget type (text / checkbox / radio / combobox / listbox / signature)
  - field flags decoded to read_only / required / multiline / comb
  - /TU tooltip (the long human-readable label embedded in the form)
  - precise rect (page + x/y/width/height, PDF points)
  - choice values/displays for combo/list boxes
  - the "on" export value for each checkbox/radio widget (its button state)

The dump is grouped by field name so radio groups and split checkbox matrices are
visible as one logical field with N option-widgets -- the "consolidated_widgets"
problem the LLM orchestrator then reasons over.

ASCII-only (cp1252 safe). Usage:

    python scripts/bakeoff/acroform_dump.py FORM.pdf [--json OUT.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from typing import Any, Optional

import pymupdf as fitz  # PyMuPDF


_TYPE_NAMES = {
    fitz.PDF_WIDGET_TYPE_TEXT: "text",
    fitz.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
    fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "radio",
    fitz.PDF_WIDGET_TYPE_COMBOBOX: "combobox",
    fitz.PDF_WIDGET_TYPE_LISTBOX: "listbox",
    fitz.PDF_WIDGET_TYPE_SIGNATURE: "signature",
    # A push-button (reset/print/submit) IS a widget but not a data field; name
    # it so downstream coverage logic can exclude it (bd polyglot-pdf-w0eq /
    # f31h -- previously fell through to "unknown(1)", defeating the button
    # exclusion in schema_lint.is_fillable_widget).
    fitz.PDF_WIDGET_TYPE_BUTTON: "button",
}

# AcroForm field-flag bits (PDF 32000-1, table 226/228). PyMuPDF exposes the raw
# /Ff integer as widget.field_flags.
_FF_READONLY = 1 << 0
_FF_REQUIRED = 1 << 1
_FF_MULTILINE = 1 << 12   # text fields
_FF_COMB = 1 << 24        # text fields


def _on_state(widget: "fitz.Widget") -> Optional[str]:
    """The 'on' export value for a checkbox/radio widget.

    For a button widget the meaningful value is its non-Off appearance state --
    e.g. a checkbox whose checked state is /Yes, or a radio kid whose state is
    /1. PyMuPDF exposes the current value via .field_value and the available
    states via .button_states(); we pull the first non-Off normal state.
    """
    try:
        states = widget.button_states() or {}
    except Exception:
        states = {}
    normal = states.get("normal") or states.get("n") or []
    for s in normal:
        if s and s != "Off":
            return s
    # Fall back to the current field_value if it is a real state.
    fv = widget.field_value
    if fv and fv != "Off":
        return str(fv)
    return None


def dump_pdf(path: str) -> dict[str, Any]:
    """Return a JSON-able AcroForm dump grouped by field name."""
    doc = fitz.open(path)
    # Preserve first-seen order so the dump reads top-to-bottom, page by page.
    groups: "OrderedDict[str, dict]" = OrderedDict()

    for pno in range(doc.page_count):
        page = doc[pno]
        for w in page.widgets():
            name = w.field_name or ""
            ftype = _TYPE_NAMES.get(w.field_type, f"unknown({w.field_type})")
            flags = int(w.field_flags or 0)
            r = w.rect
            widget_rec: dict[str, Any] = {
                "type": ftype,
                "rect": {
                    "page": pno,
                    "x": round(r.x0, 2),
                    "y": round(r.y0, 2),
                    "width": round(r.width, 2),
                    "height": round(r.height, 2),
                },
            }
            tu = getattr(w, "field_label", None) or getattr(w, "text_tooltip", None)
            if tu:
                widget_rec["tu"] = tu
            # Decode flags only where they are meaningful.
            ro = bool(flags & _FF_READONLY)
            req = bool(flags & _FF_REQUIRED)
            if ro:
                widget_rec["read_only"] = True
            if req:
                widget_rec["required"] = True
            if ftype == "text":
                if flags & _FF_MULTILINE:
                    widget_rec["multiline"] = True
                if flags & _FF_COMB:
                    widget_rec["comb"] = True
                if w.text_maxlen:
                    widget_rec["max_length"] = int(w.text_maxlen)
            if ftype in ("combobox", "listbox") and w.choice_values:
                # PyMuPDF returns choice_values as a list of (value, display)
                # tuples (older releases used parallel lists; this version is
                # already paired). Normalize both shapes to value/display dicts.
                choices = []
                for cv in w.choice_values:
                    if isinstance(cv, (list, tuple)):
                        value = str(cv[0])
                        display = str(cv[1]) if len(cv) > 1 else value
                    else:
                        value = display = str(cv)
                    choices.append({"value": value, "display": display})
                widget_rec["choices"] = choices
            if ftype in ("checkbox", "radio"):
                on = _on_state(w)
                if on:
                    widget_rec["on_value"] = on

            g = groups.setdefault(name, {"name": name, "widgets": []})
            g["widgets"].append(widget_rec)

    fields = []
    for name, g in groups.items():
        widgets = g["widgets"]
        # The logical type is the type of the group; a multi-widget group with a
        # single shared name and >1 button widget is a radio/checkbox SET.
        types = {w["type"] for w in widgets}
        logical_type = widgets[0]["type"]
        rec: dict[str, Any] = {
            "name": name,
            "logical_type": logical_type,
            "widget_count": len(widgets),
            "widgets": widgets,
        }
        if len(types) > 1:
            rec["mixed_types"] = sorted(types)
        fields.append(rec)

    return {
        "source_pdf": path,
        "page_count": doc.page_count,
        "field_count": len(fields),
        "widget_count": sum(len(f["widgets"]) for f in fields),
        "fields": fields,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic PyMuPDF AcroForm dump.")
    ap.add_argument("pdf", help="path to the source PDF")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="optional path to write the dump JSON")
    args = ap.parse_args(argv)

    dump = dump_pdf(args.pdf)
    text = json.dumps(dump, indent=2)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"[wrote {args.json_out}] {dump['field_count']} fields, "
              f"{dump['widget_count']} widgets, {dump['page_count']} pages")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
