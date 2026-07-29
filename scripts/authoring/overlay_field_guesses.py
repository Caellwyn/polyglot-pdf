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
    """widget name -> the label(s) claiming it. Includes option-level claims,
    which is where choice fields carry their real widget identity.

    A LIST, not a first-wins scalar: two DIFFERENT fields claiming one widget is
    a real defect (schema_lint's dump-widget-multiclaim) and exactly the shape
    this overlay exists to make visible. Collapsing it would render a
    multiclaimed widget identically to a correctly single-claimed one.

    Claimants are tracked as (owner field id, kind) pairs, mirroring BOTH ERROR
    branches of schema_lint's _check_dump_claims -- not raw label count, and not
    owner alone. That rule flags two distinct shapes and carves out exactly one:
      - ERROR: more than one DIFFERENT field claims the widget;
      - ERROR: more than one OPTION of the SAME field claims it (selecting one
        would tick both -- the shipped-f1040 class of bug, pinned by
        backend/tests/test_schema_lint.py::test_dump_multiclaim_by_two_options_of_one_field);
      - BENIGN: field-level + a SINGLE option of the same field (the
        groups-of-one convention -- a standalone checkbox restating its widget
        in both places). This one alone must stay unflagged.

    An option dict carrying its own `id` is yielded by _iter_fields as a field in
    its own right; its claim belongs to its PARENT, so it is excluded by object
    IDENTITY. Excluding by id STRING would drop a genuine top-level field whose
    id merely collides with some option's id elsewhere in the schema (option ids
    are short generic slugs -- `yes`, `no`, `other`), silently rendering that
    field's widget as a false coverage gap.
    """
    # Collect the option dicts FIRST: the walk order is not guaranteed to reach a
    # parent before its option, so this cannot be unwound after the fact.
    option_dict_ids: set[int] = set()
    for f in _iter_fields(schema):
        options = f.get("options")
        if not isinstance(options, list):
            continue
        for o in options:
            if isinstance(o, dict):
                option_dict_ids.add(id(o))

    # widget -> {(owner field id, kind): label}. `kind` is "field" for a
    # field-level claim and "option[<idx>]" for an option-level one -- the same
    # key space lint uses. So a field + one option gives two entries under one
    # owner (benign, see below) while two options give two distinct option kinds
    # (an ERROR shape). Indices, not values: see the note at the assignment.
    claimants: dict[str, dict[tuple[str, str], str]] = {}
    for f in _iter_fields(schema):
        fid = f.get("id")
        if not isinstance(fid, str) or id(f) in option_dict_ids:
            continue  # an option is claimed BY its parent field, not by itself
        label = _label_for(f, mode)
        claim = f.get("pdf_field_name")
        if isinstance(claim, str) and claim:
            claimants.setdefault(claim, {}).setdefault((fid, "field"), label)
        options = f.get("options")
        if not isinstance(options, list):
            continue
        for idx, o in enumerate(options):
            if not isinstance(o, dict):
                continue
            oc = o.get("pdf_field_name")
            if not isinstance(oc, str) or not oc:
                continue
            val = o.get("value")
            suffix = f"={val}" if isinstance(val, (str, int)) else ""
            # Key on the option's INDEX, exactly as lint's option_kinds does.
            # Deriving `kind` from the option's VALUE would let a value of
            # "field" collide with the field-level key above and overwrite it,
            # silently turning an option+option ERROR into a benign-looking
            # single claim -- and no other lint rule catches that shape, since
            # "field" is a perfectly legal option slug. The index is
            # collision-free by construction; `val` is display only.
            claimants.setdefault(oc, {})[(fid, f"option[{idx}]")] = (
                f"{label}{suffix}")

    out: dict[str, list[str]] = {}
    for name, by_claimant in claimants.items():
        owners = {fid for fid, _ in by_claimant}
        option_kinds = [k for _, k in by_claimant if k != "field"]
        if len(owners) > 1 or len(option_kinds) > 1:
            # A real multiclaim: surface every claimant so the collision shows.
            out[name] = list(by_claimant.values())
        else:
            # One owner, at most one option -> single claim OR the benign
            # groups-of-one pair. Prefer the option-level label: it is the more
            # specific of the two and names the value that ticks this widget.
            option_labels = [v for (_, k), v in by_claimant.items() if k != "field"]
            out[name] = [option_labels[0]] if option_labels else list(by_claimant.values())
    return out


def annotate(schema: dict, pdf_path: str, out_path: str, mode: str = "spoken",
             png_dir: Optional[str] = None) -> dict:
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover - env-dependent
        return {"error": "PyMuPDF (fitz) is required"}

    claims = _claims(schema, mode)
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # unreadable/missing PDF is a USAGE error (rc 2)
        return {"error": f"cannot open PDF {pdf_path!r}: {exc}"}
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

    try:
        doc.save(out_path)
    except Exception as exc:  # unwritable --out is a USAGE error (rc 2)
        doc.close()
        return {"error": f"cannot write {out_path!r}: {exc}"}

    pngs: list[str] = []
    if png_dir:
        # Guarded like every other IO path: makedirs raises FileExistsError when
        # png_dir names an existing FILE, and pix.save can fail per page. Either
        # would otherwise traceback AFTER the review PDF was already written.
        try:
            os.makedirs(png_dir, exist_ok=True)
            zoom = _PNG_DPI / 72.0
            for pno, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                p = os.path.join(png_dir, f"page{pno + 1}.png")
                pix.save(p)
                pngs.append(p)
        except OSError as exc:
            doc.close()
            return {"error": f"cannot write PNGs to {png_dir!r}: {exc}"}

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
