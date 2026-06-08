#!/usr/bin/env python3
"""The FormSchema output contract handed to every extractor arm.

Throwaway research helper for the extractor bake-off (bd polyglot-pdf-7a9.4). This
is a COMPACT restatement of docs/schema_format.md -- enough for an LLM to emit a
schema the scorer (scripts/schema_score.py) can grade, WITHOUT handing the model a
real ground-truth schema (that would be circular for a bake-off). It deliberately
names exactly the keys the scorer reads, so a faithful extraction is graded on its
merits and not penalized for a key-name mismatch.

ASCII-only (cp1252 safe).
"""
from __future__ import annotations

# Keys the scorer (schema_score.py) actually grades. Spelled out so the model
# emits the right shape and the bake-off measures extraction quality, not format
# guessing.
SCHEMA_CONTRACT = """\
You are extracting a fillable PDF form into a FormSchema JSON object. Emit ONE
JSON object and NOTHING else (no prose, no markdown fences).

TOP-LEVEL SHAPE:
{
  "source": "pdf",
  "form_metadata": {"title": str, "form_number": str, "page_count": int,
                    "edition_date": str},
  "parts":    [ {"id": str, "label": str, "order": int, "section_ids": [str]} ],
  "sections": [ {"id": str, "label": str, "order": int, "fields": [str(field id)],
                 "page_numbers": [int], "show_if": {...optional...}} ],
  "fields":   [ FIELD, ... ],
  "supplements": [ {"id": str, "label": str} ]   // only if the form has overflow
                                                 // supplement pages
}

FIELD SHAPE (the unit the scorer grades hardest):
{
  "id": str,                 // your own stable id; matching never trusts it
  "name": str,               // human label / question text
  "spoken_name": str,        // short voice label
  "type": one of: "text","textarea","date","number","radio","checkbox",
                  "select","signature","table",
  "section_id": str,         // which section.id this field is in
  "pdf_field_name": str,     // EXACT AcroForm widget name -- the join key the
                             // scorer matches on; copy it verbatim, do not invent
  "pdf_position": {"page": int, "x": num, "y": num, "width": num, "height": num},
  "validation": {"required": bool, "pattern": str(optional regex)},
  "options": [ {"value": str, "label": str, "pdf_field_name": str(optional)} ],
                             // radio/checkbox/select choices. Each option carries
                             // its OWN widget name in option.pdf_field_name, and
                             // option.value MUST be that widget's leaf name (see
                             // CHOICE-FIELD RULES below) -- NOT a semantic label.
  "max_length": int, "read_only": bool, "multiline": bool,

  // RELATIONSHIP / LOGIC keys (the hard half -- recover these from printed
  // conditional text like "Yes (Proceed to Item 5)" and form structure):
  "show_if": {"field": str(other field id), "operator": str, "value": any},
  "controls_fields": [ {"operator": str, "value": any,   // a chosen option.value
                        "unlocks": [str(field id)], "shows": [str(field id)],
                        "makes_required": [str(field id)]} ],  // what selecting
                                                  // this field's option triggers
  "conditional_fields": [str],            // fields shown based on this one
  "conditional_logic": {...}, "conditional_behavior": {...},
  "copy_to": [str(field id)],             // value mirrored to these fields
  "overflow_to_supplement": str(supplement id),  // long lists overflow here
  "multi_entry": {...}                    // repeating-row config (or type=table)
}

RULES:
- Use the EXACT pdf_field_name from the provided AcroForm field list when given;
  never invent or normalize it. It is the only reliable cross-reference.
- Consolidate split widgets: a group of checkbox/radio widgets sharing one logical
  question is ONE field with an options[] array, each option carrying its widget
  name in option.pdf_field_name.
- Recover conditional logic (show_if / controls_fields / overflow) from the
  PRINTED instructions on the page, not guesses.
- Output MUST be a single valid JSON object, UTF-8, ASCII-safe, no trailing commas.

CHOICE-FIELD RULES (checkbox / radio -- these MUST round-trip into the PDF):
- A "radio" field has pdf_field_name=null at field level; the widget names live
  ONLY on each option.pdf_field_name. A logical radio may span DIFFERENT widget
  names presented as one choice (e.g. a Male widget + a Female widget) -- group by
  MEANING, putting each widget's exact name on its option.
- option.value MUST be the WIDGET LEAF identifier (the last dotted segment of that
  option's pdf_field_name, INCLUDING its [n] index) -- e.g. for widget
  "form1[0].#subform[0].P1_checkbox4[0]" the option.value is "P1_checkbox4[0]".
  Do NOT use a semantic value ("Yes"/"No"/"Male"). The filler selects the widget
  by matching the app-sent value against option.value, and any controls_fields /
  show_if that references this option MUST use the SAME widget-leaf string -- a
  semantic value breaks BOTH selection and conditional logic.
- A single standalone checkbox (no choice set) keeps a field-level pdf_field_name
  AND a one-element options[] carrying that same widget's leaf as option.value.
- READ-ONLY choice widgets that the form unlocks on selection carry BOTH keys, to
  match the I-90 gold shape exactly:
  conditional_behavior={"unlock_method":"flip_readonly_bit"} AND
  conditional_logic={"unlock_method":"flip_readonly_bit","pdf_field_flag_change":
  {"bit":int,"current_value":int,"required_value":int}}.
  (NOTE: the production filler currently reads pdf_field_flag_change from
  conditional_behavior, but the gold puts it under conditional_logic -- so the
  unlock does NOT actually fire today; that is a known production bug, tracked
  separately. Emit the gold shape regardless so the extracted schema matches.)
- Do NOT depend on on/off appearance values: the filler derives a checkbox's "on"
  state live from the widget; you only need the correct option.value + name.

CHOICE-FIELD EXAMPLE (the exact shape a radio must take -- note value==leaf):
{
  "id": "name_changed", "name": "Has your name legally changed?",
  "type": "radio", "section_id": "...", "pdf_field_name": null,
  "options": [
    {"value": "P1_checkbox4[0]", "label": "Yes (Proceed to Item 5)",
     "pdf_field_name": "form1[0].#subform[0].P1_checkbox4[0]"},
    {"value": "P1_checkbox4[1]", "label": "No (Proceed to Item 6)",
     "pdf_field_name": "form1[0].#subform[0].P1_checkbox4[1]"}
  ],
  "controls_fields": [
    {"operator": "equals", "value": "P1_checkbox4[0]", "unlocks": ["..."]}
  ]
}
Note: controls_fields[].value reuses the SAME widget-leaf string "P1_checkbox4[0]"
as option.value. This illustration is canonical -- imitate it even if a few-shot
example schema happens to use a different (non-conforming) value style.
"""


def acroform_field_list(dump: dict, max_fields: int | None = None) -> str:
    """Render the AcroForm dump as a compact text field list for the prompt.

    One line per logical field: name, type, flags, /TU, page, and choices. This is
    the deterministic ground-truth structure the LLM cannot see from pixels.
    """
    lines = []
    fields = dump.get("fields", [])
    if max_fields:
        fields = fields[:max_fields]
    for f in fields:
        w0 = f["widgets"][0]
        bits = [f"name={f['name']}", f"type={f['logical_type']}"]
        if f["widget_count"] > 1:
            bits.append(f"widgets={f['widget_count']}")
        flags = []
        for w in f["widgets"]:
            for k in ("read_only", "required", "multiline", "comb"):
                if w.get(k) and k not in flags:
                    flags.append(k)
        if flags:
            bits.append("flags=" + ",".join(flags))
        if w0.get("max_length"):
            bits.append(f"maxlen={w0['max_length']}")
        bits.append(f"page={w0['rect']['page']}")
        if w0.get("tu"):
            bits.append(f"tu={w0['tu']!r}")
        if w0.get("choices"):
            vals = ",".join(c["value"] for c in w0["choices"][:12])
            bits.append(f"choices=[{vals}]")
        if any("on_value" in w for w in f["widgets"]):
            ons = [w["on_value"] for w in f["widgets"] if w.get("on_value")]
            bits.append("on=" + ",".join(ons[:8]))
        lines.append("  " + " | ".join(bits))
    header = (f"ACROFORM FIELD LIST ({dump.get('field_count')} fields, "
              f"{dump.get('widget_count')} widgets, "
              f"{dump.get('page_count')} pages):")
    return header + "\n" + "\n".join(lines)
