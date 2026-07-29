#!/usr/bin/env python3
"""Render the PDF with the extractor's OWN field guesses drawn on the widget each
one claims -- a visual review surface for field<->widget assignment.

Companion to check_line_binding.py, which grades a draft against the form's
printed line markers. That oracle is exact but NARROW: it can only judge a field
that states a line number and claims a widget on a marked row. W-7 prints no
gutter markers at all, so the oracle abstains on it entirely -- and abstention is
precisely where a human (or a vision model) has to look instead.

This is that second surface. Where the oracle asks "is this widget on the row
this field names?", the overlay asks the question no numbering scheme can:
does the label sitting on this box actually MEAN what the box is for? A
"signature" drawn on top of a phone-number box is obvious to an eye and
invisible to every deterministic check we have.

The direction matters. scripts/bakeoff/prior_extractor/pdf_annotator.py draws
WIDGET NAMES onto the form -- grounding INPUT, telling a model what the boxes
are called. This draws the extractor's OUTPUT -- what the model decided each box
means -- so the drawing is the thing under review, not the aid.

Label modes (--label):
    spoken   spoken_name, the voice-facing phrase (DEFAULT -- this is what a
             user actually hears asked of them, so a mismatch here is the
             user-visible bug)
    id       field id, best for cross-referencing a finding back to the schema
    name     the display label

Usage:
    python scripts/authoring/overlay_field_guesses.py \
        --schema DRAFT.json --pdf FORM.pdf --out REVIEW.pdf [--label spoken]
    ... [--png-dir DIR]   also rasterize each page (for a vision model)
Exit: 0 on success, 2 on usage/IO error.

ASCII only (cp1252 safe).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

_FONT_SIZE = 6.5
_TEXT_COLOR = (0.75, 0.0, 0.0)     # dark red -- distinct from black form print
_BOX_COLOR = (0.85, 0.1, 0.1)      # widget outline
_UNCLAIMED_COLOR = (0.0, 0.35, 0.9)  # blue -- a widget NO field claims
_MULTICLAIM_COLOR = (0.9, 0.45, 0.0)  # orange -- a widget MORE THAN ONE field claims
_PNG_DPI = 140


def _iter_fields(schema: dict):
    """Every dict carrying an id, at any nesting depth (parts/sections/fields)."""
    seen: set[int] = set()

    def walk(o: Any):
        if isinstance(o, dict):
            if id(o) in seen:
                return
            seen.add(id(o))
            if isinstance(o.get("id"), str):
                yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)

    yield from walk(schema)


def _label_for(field: dict, mode: str) -> str:
    order = {
        "spoken": ("spoken_name", "name", "id"),
        "name": ("name", "spoken_name", "id"),
        "id": ("id", "spoken_name", "name"),
    }[mode]
    for key in order:
        v = field.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "?"


def _claims(schema: dict, mode: str) -> dict[str, list[str]]:
    """widget name -> EVERY label claiming it. Includes option-level claims,
    which is where choice fields carry their real widget identity.

    Deliberately a LIST, not a first-wins scalar: two fields claiming one widget
    is a real defect class (schema_lint's dump-widget-multiclaim), and it is
    exactly the shape this overlay exists to make visible. Collapsing it would
    render a multiclaimed widget identically to a correctly single-claimed one --
    hiding the bug the reviewer is looking for."""
    out: dict[str, list[str]] = {}
    for f in _iter_fields(schema):
        label = _label_for(f, mode)
        claim = f.get("pdf_field_name")
        if isinstance(claim, str) and claim:
            out.setdefault(claim, []).append(label)
        options = f.get("options")
        if isinstance(options, list):
            for o in options:
                if not isinstance(o, dict):
                    continue
                oc = o.get("pdf_field_name")
                if isinstance(oc, str) and oc:
                    val = o.get("value")
                    suffix = f"={val}" if isinstance(val, (str, int)) else ""
                    out.setdefault(oc, []).append(f"{label}{suffix}")
    return out


def annotate(schema: dict, pdf_path: str, out_path: str, mode: str = "spoken",
             png_dir: Optional[str] = None) -> dict:
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover - env-dependent
        return {"error": "PyMuPDF (fitz) is required"}

    claims = _claims(schema, mode)
    doc = fitz.open(pdf_path)
    drawn = unclaimed = multiclaimed = 0

    for page in doc:
        for w in page.widgets():
            name = w.field_name
            if not isinstance(name, str):
                continue
            rect = w.rect
            labels = claims.get(name)
            if not labels:
                # A widget the draft claims for NO field. Marked distinctly:
                # it is a coverage gap, not a mislabel, and the two failure
                # modes must not look alike on the review sheet.
                page.draw_rect(rect, color=_UNCLAIMED_COLOR, width=0.8)
                unclaimed += 1
                continue

            if len(labels) > 1:
                # Two or more fields claim this ONE widget -- a real defect
                # (schema_lint's dump-widget-multiclaim). Draw every claimant,
                # flagged, so the reviewer sees the collision instead of a
                # plausible-looking single label.
                label = "!! " + " | ".join(labels)
                box_color = _MULTICLAIM_COLOR
                multiclaimed += 1
            else:
                label = labels[0]
                box_color = _BOX_COLOR

            page.draw_rect(rect, color=box_color, width=0.6)
            # Short boxes get their label ABOVE (drawing inside would cover the
            # form's own printed text); tall boxes take it inside at the top.
            if (rect.y1 - rect.y0) > _FONT_SIZE + 5:
                origin = fitz.Point(rect.x0 + 1.5, rect.y0 + _FONT_SIZE + 1.5)
            else:
                origin = fitz.Point(rect.x0 + 0.5, rect.y0 - 1.5)
            # White plate behind the text so it stays legible over form rules.
            width = len(label) * _FONT_SIZE * 0.52
            page.draw_rect(
                fitz.Rect(origin.x - 1, origin.y - _FONT_SIZE - 1,
                          origin.x + width + 1, origin.y + 1.5),
                color=None, fill=(1, 1, 1),
            )
            page.insert_text(origin, label, fontsize=_FONT_SIZE,
                             color=(box_color if len(labels) > 1 else _TEXT_COLOR))
            drawn += 1

    doc.save(out_path)

    pngs: list[str] = []
    if png_dir:
        os.makedirs(png_dir, exist_ok=True)
        zoom = _PNG_DPI / 72.0
        for pno, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            p = os.path.join(png_dir, f"page{pno + 1}.png")
            pix.save(p)
            pngs.append(p)

    doc.close()
    return {"drawn": drawn, "unclaimed": unclaimed,
            "multiclaimed": multiclaimed, "out": out_path, "pngs": pngs}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--schema", required=True, help="draft/kit schema.json")
    ap.add_argument("--pdf", required=True, help="the form PDF")
    ap.add_argument("--out", required=True, help="annotated PDF output path")
    ap.add_argument("--label", choices=("spoken", "id", "name"),
                    default="spoken", help="which field text to draw")
    ap.add_argument("--png-dir", default=None,
                    help="also rasterize pages here (for a vision model)")
    args = ap.parse_args(argv)

    try:
        with open(args.schema, encoding="utf-8") as fh:
            schema = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot read schema: {exc}", file=sys.stderr)
        return 2

    result = annotate(schema, args.pdf, args.out, args.label, args.png_dir)
    if result.get("error"):
        print(f"ERROR: {result['error']}", file=sys.stderr)
        return 2

    print(f"[OK] {result['out']} -- {result['drawn']} labelled widget(s), "
          f"{result['unclaimed']} unclaimed (blue), "
          f"{result['multiclaimed']} multiclaimed (orange)")
    for p in result["pngs"]:
        print(f"  {p}")
    print("Review question: does the label drawn on each box MEAN what that "
          "box is for? (a numbering check cannot see this -- see "
          "check_line_binding.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
