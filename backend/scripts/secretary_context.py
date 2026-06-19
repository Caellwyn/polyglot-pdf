"""Secretary context renderer -- the form info the cheap secretary model reads.

bd polyglot-pdf-jnjj.26 (Secretary Gate 1, RECALL). The secretary
(gemini-2.5-flash-lite) is a pure retrieval+reasoning specialist: it holds the
form's per-field context plus the client's current values and answers the
principal's prose queries. This module renders that context, ALGORITHMICALLY, from
the same inputs the secretary would get in production:

  - the form schema (form-kits/i-90/schema.json) -- the STATIC catalog (metadata
    that never changes within a session: ideal cache-prefix content), and
  - the client's current form state -- the DYNAMIC tail: a flat field_values map
    (FormSession.field_values) plus a SEPARATE shown_map (applicability).

Why shown_map is a separate input (not derived from value): the real frontend
tracks shown/hidden INDEPENDENTLY of whether a field has a value (conditional UI).
The value-vs-applicability query class ("have they answered X?" when X is hidden
vs. empty-but-applicable) is only measurable if the renderer can represent that
distinction. Deriving shown from "has a value" collapses it.

Format here is the single feasibility-first format: GROUPED BY SECTION (parts ->
sections -> fields). Comparing alternative formats is a deferred follow-up
(bd polyglot-pdf-jnjj.37).

CONTRACT (what the secretary sees / does not see), from
docs/standards/validation-delegation.md + the secretary research plan:
  INCLUDE per field: id, spoken_name, name/label, type, options (radio/select),
    help.instructions (+ help.format_hint), section label, current value, shown.
  EXCLUDE: PDF mechanics (pdf_position, pdf_field_name, consolidated_widgets,
    is_comb), validation.pattern/regex, raw show_if/controls_fields logic.

PII: this module renders whatever values it is handed. In the probe the values are
fabricated (synthetic corpus); in production the rendered context is PHI and must
never be logged. Callers log field ids / counts / token sizes, never the rendered
text or values.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Keys excluded from the secretary's view (PDF mechanics + validation internals +
# raw conditional logic). The renderer reads only the allowed keys explicitly, so
# this list is documentation of intent rather than a filter -- but kept here so the
# exclusion is auditable.
EXCLUDED_KEYS = (
    "pdf_position", "pdf_field_name", "consolidated_widgets", "is_comb",
    "validation", "show_if", "hide_if", "controls_fields", "conditional_fields",
    "conditional_behavior", "conditional_logic", "copy_to", "copy_from",
    "question_number", "read_only", "multiline", "max_length", "placeholder",
)

EMPTY = "<empty>"


def _field_index(schema: dict) -> dict:
    """Map field_id -> full field object (the flat top-level `fields` array is the
    source of the full objects; sections reference fields by id)."""
    return {f["id"]: f for f in schema.get("fields", [])}


def _section_label_map(schema: dict) -> dict:
    """Map section id -> human label."""
    return {sec["id"]: sec.get("label", sec["id"]) for sec in schema.get("sections", [])}


def _ordered_groups(schema: dict) -> list:
    """Yield (part_label, section_label, [field_id, ...]) in form order.

    Grouping walks `sections[].fields` (id reference lists), NOT each field's
    own section_id: the section arrays are authoritative for ORDER and for
    ASSIGNMENT (some fields carry a section_id that is not present in sections[],
    e.g. 'Part 3 - Biographic Information' -- a known schema drift; the reference
    lists place every referenced field correctly regardless). Parts are matched to
    sections via parts[].section_ids; sections a part does not claim (part_7 has an
    empty section_ids in this schema) fall back to a best-effort part match by id
    prefix, else an 'Other' part.
    """
    sec_label = _section_label_map(schema)

    # section_id -> part_label
    sec_to_part = {}
    for part in schema.get("parts", []):
        for sid in part.get("section_ids", []):
            sec_to_part[sid] = part.get("label", part["id"])

    groups = []
    for sec in schema.get("sections", []):
        sid = sec["id"]
        part_label = sec_to_part.get(sid)
        if part_label is None:
            # Best-effort: part_7's sections are not listed under part_7 in this
            # schema (empty section_ids). Recover the part by the section label's
            # leading "Part N" token (e.g. "Part 7.1 ..." -> "Part 7") and reuse
            # the real parts[] label for that part number when available, so all of
            # Part 7's sections group under one header.
            label = sec.get("label", sid) or "Other"
            part_num = None
            toks = label.split()
            if len(toks) >= 2 and toks[0].lower() == "part":
                part_num = toks[1].split(".")[0]  # "7.1" -> "7"
            part_label = "Other"
            if part_num is not None:
                part_label = "Part " + part_num
                for p in schema.get("parts", []):
                    if p.get("label", "").lower().startswith("part " + part_num + "."):
                        part_label = p["label"]
                        break
        field_ids = [fid for fid in sec.get("fields", [])]
        groups.append((part_label, sec_label.get(sid, sid), field_ids))
    return groups


def _value_str(field_values: dict, fid: str) -> str:
    v = field_values.get(fid, None)
    if v is None or v == "":
        return EMPTY
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _options_str(field: dict) -> str:
    opts = field.get("options")
    if not opts:
        return ""
    labels = []
    for o in opts:
        if isinstance(o, dict):
            labels.append(str(o.get("label", o.get("value", ""))))
        else:
            labels.append(str(o))
    return " | options: [" + "; ".join(labels) + "]"


def _render_field(field: dict, fid: str, field_values: dict, shown_map: dict) -> str:
    spoken = field.get("spoken_name", "")
    name = field.get("name", "") or field.get("label", "")
    ftype = field.get("type", "")
    help_obj = field.get("help") or {}
    instr = (help_obj.get("instructions") or "").strip()
    fmt_hint = (help_obj.get("format_hint") or "").strip()
    value = _value_str(field_values, fid)
    # shown: explicit map wins; default True (applicable) when unspecified.
    shown = shown_map.get(fid, True)

    head = '  - id={fid} | "{spoken}"'.format(fid=fid, spoken=spoken)
    if name and name != spoken:
        head += ' ({name})'.format(name=name)
    head += ' | type={t}{opts}'.format(t=ftype, opts=_options_str(field))

    lines = [head]
    state = '    value={v} | shown={s}'.format(
        v=('"%s"' % value if value != EMPTY else EMPTY),
        s=("true" if shown else "false"),
    )
    lines.append(state)
    if instr:
        h = "    help: " + instr
        if fmt_hint:
            h += " (format: " + fmt_hint + ")"
        lines.append(h)
    elif fmt_hint:
        lines.append("    help: (format: " + fmt_hint + ")")
    return "\n".join(lines)


def render_secretary_context(schema: dict, field_values: dict, shown_map: dict) -> str:
    """Render the grouped-by-section secretary context as plain text.

    field_values: flat {field_id: value} (FormSession.field_values shape).
    shown_map:    {field_id: bool} applicability, SEPARATE from value.
    """
    field_values = field_values or {}
    shown_map = shown_map or {}
    idx = _field_index(schema)

    out = []
    last_part = None
    for part_label, section_label, field_ids in _ordered_groups(schema):
        if part_label != last_part:
            out.append("=== {p} ===".format(p=part_label))
            last_part = part_label
        out.append("Section: {s}".format(s=section_label))
        for fid in field_ids:
            field = idx.get(fid)
            if field is None:
                continue
            out.append(_render_field(field, fid, field_values, shown_map))
        out.append("")  # blank line between sections
    return "\n".join(out).rstrip() + "\n"


def estimate_tokens(text: str) -> int:
    """Best-effort token estimate. Uses tiktoken if available, else chars/4."""
    try:
        import tiktoken  # type: ignore

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


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
        text = render_secretary_context(schema, field_values, shown_map)
        sys.stdout.write(text)
        sys.stdout.write(
            "\n--- rendered token estimate: {n} ---\n".format(n=estimate_tokens(text))
        )
        return

    ap.print_help()


if __name__ == "__main__":
    main()
