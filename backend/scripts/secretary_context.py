"""Secretary context renderer -- research/CLI shim over the production module.

bd polyglot-pdf-jnjj.26 (Gate 1 RECALL) / jnjj.27 (Gate 2 LATENCY) created the
renderers here; bd polyglot-pdf-jnjj.45a PROMOTED them to a production module
(backend/services/secretary_context.py) so production code (TextAIGemini.ask /
the ask_secretary handler) does not import from backend/scripts/.

This file is now a THIN SHIM over the production module:
  - it re-exports the PRODUCTION renderers + shared helpers (single source of
    truth -- the rendered bytes are guaranteed identical to what the Gate-1/2
    probes measured); and
  - it keeps the RESEARCH-ONLY format variants (render_flat_json, render_prose,
    render_context / CONTEXT_FORMATS) from the jnjj.37 format-comparison study,
    which are NOT used in production and therefore stay here. They are built on
    the SAME shared helpers imported from the production module, so the grouped
    baseline they compare against is byte-identical to production.

The probe scripts import render_secretary_context / render_static_catalog /
render_values_tail / estimate_tokens from here unchanged; the jnjj.37 comparison
imports render_context / CONTEXT_FORMATS from here unchanged.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Single source of truth: re-export the production renderers + the shared helpers
# the research variants below reuse (jnjj.45a). Importing them here keeps every
# existing `from backend.scripts.secretary_context import ...` (the probes)
# working with byte-identical output, and lets the jnjj.37 format variants build
# on the exact same grouping/value logic as production.
from backend.services.secretary_context import (  # noqa: F401
    EMPTY,
    EXCLUDED_KEYS,
    estimate_tokens,
    render_secretary_context,
    render_static_catalog,
    render_values_tail,
    _field_index,
    _ordered_groups,
    _value_str,
)


# --------------------------------------------------------------------------- #
# Research-only format variants (jnjj.37 format comparison). NOT used in
# production -- kept here, built on the production helpers above so the grouped
# baseline they are compared against is byte-identical to what ships.
# --------------------------------------------------------------------------- #

def render_flat_json(schema: dict, field_values: dict, shown_map: dict) -> str:
    """Format (a) -- a FLAT JSON array of field objects (no section grouping).

    Max reference fidelity: every field is a discrete JSON object with its exact
    id, so prose->field grounding has the cleanest handle; weakest on structure
    (the model must reconstruct which fields form an address cluster, etc.). One
    of the candidate formats compared in jnjj.37."""
    field_values = field_values or {}
    shown_map = shown_map or {}
    # Authoritative field->section label, from _ordered_groups (which walks
    # sections[].fields), NOT each field's own section_id -- the latter is
    # non-authoritative (some I-90 fields point to a section not in sections[]),
    # and using it would feed flat DIFFERENT section metadata than grouped/prose,
    # corrupting the apples-to-apples format comparison (Codex jnjj.37 finding).
    fid_section = {}
    for _part, section_label, field_ids in _ordered_groups(schema):
        for fid in field_ids:
            fid_section[fid] = section_label
    objs = []
    for f in schema.get("fields", []):
        fid = f["id"]
        obj = {
            "id": fid,
            "spoken_name": f.get("spoken_name", ""),
            "name": f.get("name", "") or f.get("label", ""),
            "type": f.get("type", ""),
            "section": fid_section.get(fid, ""),
            "value": _value_str(f, field_values, fid),
            "shown": bool(shown_map.get(fid, True)),
        }
        help_obj = f.get("help") or {}
        instr = (help_obj.get("instructions") or "").strip()
        if instr:
            obj["help"] = instr
        fmt_hint = (help_obj.get("format_hint") or "").strip()
        if fmt_hint:
            obj["format_hint"] = fmt_hint
        opts = f.get("options")
        if opts:
            obj["options"] = [
                (o.get("label", o.get("value", "")) if isinstance(o, dict) else str(o))
                for o in opts
            ]
        objs.append(obj)
    return json.dumps(objs, indent=1, ensure_ascii=True) + "\n"


def render_prose(schema: dict, field_values: dict, shown_map: dict) -> str:
    """Format (c) -- PROSE / markdown: each field as a natural-language sentence,
    grouped by section under markdown headings.

    Max reasoning fluency (reads like documentation the model can reason over);
    weakest on precise id reference (the model must echo an id embedded in prose).
    One of the candidate formats compared in jnjj.37."""
    field_values = field_values or {}
    shown_map = shown_map or {}
    idx = _field_index(schema)
    out = []
    last_part = None
    for part_label, section_label, field_ids in _ordered_groups(schema):
        if part_label != last_part:
            out.append("# {p}".format(p=part_label))
            last_part = part_label
        out.append("## {s}".format(s=section_label))
        for fid in field_ids:
            field = idx.get(fid)
            if field is None:
                continue
            spoken = field.get("spoken_name", "") or field.get("name", "")
            ftype = field.get("type", "")
            value = _value_str(field, field_values, fid)
            shown = shown_map.get(fid, True)
            if not shown:
                state = "is not applicable to this applicant"
            elif value == EMPTY:
                state = "has not been answered yet"
            else:
                state = 'is "%s"' % value
            # Include the field TYPE -- grouped/flat both carry it, so prose must too
            # for an apples-to-apples comparison (Codex jnjj.37 round 2).
            type_clause = (" (a %s field)" % ftype) if ftype else ""
            sent = "The %s (field `%s`%s) %s." % (spoken, fid, type_clause, state)
            help_obj = field.get("help") or {}
            instr = (help_obj.get("instructions") or "").strip()
            if instr:
                sent += " " + instr
            opts = field.get("options")
            if opts:
                labels = [(o.get("label", o.get("value", "")) if isinstance(o, dict)
                           else str(o)) for o in opts]
                sent += " Options: " + ", ".join(labels) + "."
            out.append(sent)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# Format registry: name -> renderer(schema, field_values, shown_map) -> str.
CONTEXT_FORMATS = {
    "grouped": render_secretary_context,   # jnjj.26 baseline (grouped-by-section)
    "flat": render_flat_json,              # flat JSON array
    "prose": render_prose,                 # prose / markdown
}


def render_context(schema: dict, field_values: dict, shown_map: dict,
                   fmt: str = "grouped") -> str:
    """Dispatch to one of the CONTEXT_FORMATS renderers by name (jnjj.37)."""
    try:
        renderer = CONTEXT_FORMATS[fmt]
    except KeyError:
        raise ValueError("unknown context format %r; valid: %s"
                         % (fmt, sorted(CONTEXT_FORMATS)))
    return renderer(schema, field_values, shown_map)


# --------------------------------------------------------------------------- #
# CLI (research/inspection only).
# --------------------------------------------------------------------------- #

def _load_schema(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _default_schema_path() -> str:
    # repo root = three levels up from backend/scripts/this_file
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "form-kits", "i-90", "schema.json")


def main() -> None:
    ap = argparse.ArgumentParser(description="Render / inspect the secretary context.")
    ap.add_argument("--schema", default=_default_schema_path(),
                    help="Path to the form schema JSON (default: real I-90).")
    ap.add_argument("--format", default="grouped",
                    choices=sorted(CONTEXT_FORMATS),
                    help="Context format to render (jnjj.37 comparison).")
    ap.add_argument("--print-context", action="store_true",
                    help="Render the schema + a small built-in fixture and print it "
                         "plus the estimated token count.")
    args = ap.parse_args()

    schema = _load_schema(args.schema)

    if args.print_context:
        # A tiny fixture exercising the tier-6 distinction: an applicable-but-empty
        # field next to a hidden field, plus a couple of filled values.
        field_values = {
            "p1_line3a_familyname": "Smith",
            "p1_line3b_givenname": "John",
            "p1_line9_dateofbirth": "1990-04-02",
        }
        shown_map = {
            "p1_line5a_familyname": True,    # applicable but unanswered (tier-6)
            "p1_line6a_incareofname": False,  # hidden / not applicable (tier-6)
        }
        text = render_context(schema, field_values, shown_map, fmt=args.format)
        sys.stdout.write(text)
        sys.stdout.write(
            "\n--- rendered token estimate: {n} ---\n".format(n=estimate_tokens(text))
        )
        return

    ap.print_help()


if __name__ == "__main__":
    main()
