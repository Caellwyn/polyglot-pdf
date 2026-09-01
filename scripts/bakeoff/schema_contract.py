#!/usr/bin/env python3
"""The FormSchema output contract handed to every extractor arm.

Extractor-facing restatement of the FormSchema wire format (bd polyglot-pdf-7a9.4,
rendered-from-registry in bd polyglot-pdf-h76m.4 / P1.2). It names exactly the
keys the pipeline consumes so a faithful extraction is graded on merits, not
penalized for a key-name mismatch, WITHOUT handing the model a real ground-truth
schema.

Contract-from-model (P1.2)
--------------------------
The MACHINE CORE -- the operator list and the canonical v2 example -- is RENDERED
from the single source of truth (backend.models.conditional_vocabulary +
FormSchema), not hand-copied, so the prompt the LLM sees and the validator that
judges its output cannot drift. tests/test_schema_contract_sync.py pins this: it
fails if the rendered operator set diverges from the registry, and the canonical
example MUST FormSchema.model_validate under the strict v2 rules.

The registry import degrades gracefully: the bake-off arms run standalone from
scripts/bakeoff/ where the backend package may be unimportable. When it is, the
module falls back to a STATIC snapshot of the same core (kept identical by the
sync test whenever the backend IS importable, which it is in CI). So the contract
always renders; it is only the drift GUARD that needs the backend.

ASCII-only (cp1252 safe).
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Registry import (graceful): add the repo root so `backend` resolves even when
# this module is imported with only scripts/bakeoff on sys.path (the arms'
# convention). A failed import is NOT fatal -- see the module docstring.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from backend.models import conditional_vocabulary as _vocab
    REGISTRY_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only in a backend-less checkout
    _vocab = None
    REGISTRY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Canonical v2 example (single source of the example block). This dict is what
# the sync test feeds to FormSchema.model_validate, and what render_example()
# embeds in the contract -- ONE object, so the prompt example and the validated
# example can never diverge. It exercises the load-bearing v2 conventions:
#   - a checkbox_group whose option.value is a SEMANTIC SLUG (not a widget leaf),
#     each option carrying its own pdf_field_name;
#   - a dependent field using the v2 membership operator `includes` against an
#     option slug (the retired equals-means-membership hack is gone).
# DIVISIONS (bd polyglot-pdf-6cfu.2): the model is told NOT to emit parts/
# sections/section_id -- boundaries are derived deterministically from the PDF
# after extraction (scripts/authoring/derive_sections.py). The object below
# KEEPS them because FormSchema requires them to validate (the sync test's
# guarantee); render_example() strips them from the PROMPT rendering so the
# example matches the instruction the model is given.
# ---------------------------------------------------------------------------
CANONICAL_EXAMPLE: Dict = {
    "source": "pdf",
    "schema_version": "2",
    "form_metadata": {
        "title": "Example Form",
        "version": "unknown",
        "form_number": "EX-1",
        "edition_date": "01/01/25",
        "page_count": 1,
    },
    "extraction_info": {
        "extracted_at": "2026-07-05T00:00:00Z",
        "extraction_confidence": 0.9,
        "extractor_version": "contract-example",
        "manual_review_required": True,
    },
    "sections": [
        {"id": "sec_main", "label": "Main", "order": 1,
         "fields": ["reason", "other_detail"]},
    ],
    "fields": [
        {
            "id": "reason", "name": "Reason for submitting",
            "spoken_name": "reason", "type": "checkbox_group",
            "section_id": "sec_main",
            "options": [
                {"value": "new_application", "label": "New application",
                 "pdf_field_name": "form1[0].P1[0].reason[0]"},
                {"value": "renewal", "label": "Renewal",
                 "pdf_field_name": "form1[0].P1[0].reason[1]"},
                {"value": "other", "label": "Other",
                 "pdf_field_name": "form1[0].P1[0].reason[2]"},
            ],
        },
        {
            "id": "other_detail", "name": "If other, explain",
            "spoken_name": "other detail", "type": "text",
            "section_id": "sec_main",
            "pdf_field_name": "form1[0].P1[0].other_detail[0]",
            # v2 membership: the dependent field shows when the group's selected
            # set INCLUDES the 'other' option slug (not equals, not a widget leaf).
            "show_if": {"field": "reason", "operator": "includes", "value": "other"},
        },
    ],
}


# ---------------------------------------------------------------------------
# Static fallbacks. These MUST equal what the registry renders -- the sync test
# enforces it whenever the backend is importable (always, in CI). They exist only
# so the contract still renders in a backend-less checkout (the bake-off arms).
# ---------------------------------------------------------------------------
_STATIC_OPERATOR_LINES: List[str] = [
    "  equals        scalar   [checkbox, date, email, number, radio, select, tel, text, textarea]  value must be a trigger option (when the trigger is a choice field)  Strict scalar equality. NOT valid on checkbox_group (use includes).",
    "  not_equals    scalar   [checkbox, date, email, number, radio, select, tel, text, textarea]  value must be a trigger option (when the trigger is a choice field)  Strict scalar inequality. NOT valid on checkbox_group (use not_includes).",
    "  contains      scalar   [email, tel, text, textarea]  Substring match on free-text triggers.",
    "  greater_than  scalar   [date, number]",
    "  less_than     scalar   [date, number]",
    "  is_checked    (no value) [checkbox]  Bool sugar on a standalone checkbox. On groups use is_not_empty.",
    "  is_empty      (no value) [checkbox, checkbox_group, date, email, number, radio, select, tel, text, textarea]",
    "  is_not_empty  (no value) [checkbox, checkbox_group, date, email, number, radio, select, tel, text, textarea]",
    "  in            list     [date, email, number, radio, select, tel, text, textarea]  value must be a trigger option (when the trigger is a choice field)  Trigger value is one of the listed values.",
    "  not_in        list     [date, email, number, radio, select, tel, text, textarea]  value must be a trigger option (when the trigger is a choice field)  Trigger value is none of the listed values.",
    "  includes      scalar   [checkbox_group]  value must be a trigger option (when the trigger is a choice field)  The named option slug is in the group's selected set.",
    "  not_includes  scalar   [checkbox_group]  value must be a trigger option (when the trigger is a choice field)  The named option slug is NOT in the group's selected set.",
]


# ---------------------------------------------------------------------------
# Renderers.
# ---------------------------------------------------------------------------

def _arity_label(arity: str) -> str:
    return "(no value)" if arity == "none" else arity


def render_operator_lines() -> List[str]:
    """One line per v2 operator: name, value arity, trigger types, notes.

    Rendered from the registry when available; else the static snapshot (kept
    identical by the sync test). Deterministic order (registry insertion order,
    which the static list mirrors) so the contract text is stable across runs.
    """
    if not REGISTRY_AVAILABLE:
        return list(_STATIC_OPERATOR_LINES)
    lines: List[str] = []
    for name, spec in _vocab.OPERATORS.items():
        triggers = ", ".join(sorted(spec.trigger_types))
        bits = [f"  {name:<13} {_arity_label(spec.value_arity):<8} [{triggers}]"]
        if spec.value_must_be_trigger_option:
            # Only enforced WHEN the trigger is a choice field with options; on a
            # text/date/number trigger (also in several of these operators' trigger
            # lists) the value is a literal, so the note must be qualified or it
            # pushes the extractor toward hallucinated options (Codex PR #316).
            bits.append("value must be a trigger option (when the trigger is a "
                        "choice field)")
        if spec.notes:
            bits.append(spec.notes)
        lines.append("  ".join(bits))
    return lines


def render_operator_block() -> str:
    """The CONDITIONAL OPERATORS section of the contract (registry-rendered)."""
    header = (
        "CONDITIONAL OPERATORS (the ONLY operators allowed in show_if / "
        "require_if -- name | value arity | valid trigger "
        "field types | notes):"
    )
    return header + "\n" + "\n".join(render_operator_lines())


def allowed_operator_names() -> List[str]:
    """The operator name list, registry-first, for the sync test + prompt."""
    if REGISTRY_AVAILABLE:
        return list(_vocab.OPERATORS.keys())
    return [ln.strip().split()[0] for ln in _STATIC_OPERATOR_LINES]


def render_example(indent: int = 2, include_divisions: bool = False) -> str:
    """The canonical v2 example, pretty-printed JSON (ASCII-safe).

    By default the PROMPT rendering strips parts/sections/section_id (the
    model is instructed not to emit them -- divisions are derived post-
    extraction, bd 6cfu.2); CANONICAL_EXAMPLE itself keeps them so it still
    FormSchema-validates (the sync test's guarantee)."""
    import copy
    import json
    ex = CANONICAL_EXAMPLE
    if not include_divisions:
        ex = copy.deepcopy(CANONICAL_EXAMPLE)
        ex.pop("parts", None)
        ex.pop("sections", None)
        for f in ex.get("fields", []):
            f.pop("section_id", None)
    return json.dumps(ex, ensure_ascii=True, indent=indent)


def render_contract() -> str:
    """Assemble the full extractor contract with the registry-rendered core."""
    return _CONTRACT_TEMPLATE.format(
        operator_block=render_operator_block(),
        example=render_example(),
    )


# ---------------------------------------------------------------------------
# The prose shell around the machine core. The {operator_block} and {example}
# placeholders are the rendered-from-registry parts; the surrounding prose is the
# stable narrative contract. (Literal JSON braces below are doubled for str.format.)
# ---------------------------------------------------------------------------
_CONTRACT_TEMPLATE = """\
You are extracting a fillable PDF form into a FormSchema JSON object. Emit ONE
JSON object and NOTHING else (no prose, no markdown fences). Target schema
version 2 (set "schema_version": "2").

TOP-LEVEL SHAPE:
{{
  "source": "pdf",
  "schema_version": "2",
  "form_metadata": {{"title": str, "version": str, "form_number": str,
                    "page_count": int, "edition_date": str}},
  "fields":   [ FIELD, ... ],
  "supplements": [ {{"id": str, "name": str, "purpose": str,
                    "fields": [str(field id), ...may be empty]}} ]
                             // only if the form overflows. ALL FOUR keys are
                             // required -- {{id, label}} alone is rejected.
}}
// Do NOT emit "parts" or "sections" arrays, and do NOT set "section_id" on
// fields: form divisions are derived DETERMINISTICALLY from the PDF after
// extraction; anything you emit for them is discarded. Spend your effort on
// the fields themselves.

FIELD SHAPE (the unit the scorer grades hardest):
{{
  "id": str,                 // your own stable id; matching never trusts it
  "name": str,               // human label / question text
  "spoken_name": str,        // short voice label
  "type": one of: "text","textarea","date","number","tel","email","radio",
                  "checkbox","checkbox_group","select","signature",
                  "address_group","table",
  "pdf_field_name": str,     // EXACT AcroForm widget name -- copy it verbatim
  // Do NOT emit "pdf_position". Widget geometry is read straight from the PDF's
  // own AcroForm widgets after extraction and OVERWRITES anything you send --
  // same as "sections"/"parts" above. Transcribing coordinates wastes your
  // effort and loses precision. Get "pdf_field_name" exactly right instead:
  // that name is the key the position is looked up by.
  "validation": {{"required": bool, "pattern": str(optional regex)}},
  "max_length": int, "read_only": bool, "multiline": bool,
  "options": [ {{"value": str(SLUG), "label": str,
                "pdf_field_name": str(optional), "pdf_on_value": str(optional)}} ],
                             // radio/checkbox_group choices -- see
                             // CHOICE-FIELD RULES; option.value is a SEMANTIC SLUG.
                             // A SELECT is different: omit options entirely --
                             // its values are the PDF's own export codes and
                             // are filled in from the PDF after extraction.

  // RELATIONSHIP / LOGIC keys (recover from printed conditional text like
  // "Yes (Proceed to Item 5)" and form structure):
  "show_if":  CONDITION,     // this field shows when CONDITION holds
  "require_if": CONDITION,   // this field is required when CONDITION holds
  "copy_to": [str(field id)],             // value mirrored to these fields
  "overflow_to_supplement": str(supplement id),  // long lists overflow here
  "multi_entry": {{...}},                  // repeating-row config (or type=table)
  // A READ-ONLY field that a choice unlocks carries the unlock descriptor ON
  // ITSELF (that is what the runtime + PDF filler read) -- conditional_behavior /
  // conditional_logic below, plus a show_if naming the choice.
  // controls_fields / conditional_fields are REMOVED v1 trigger-side mechanisms
  // -- NEVER emit either key. v2 has NO trigger-side conditional logic at all;
  // express a "show / require this field when X" dependency ONLY as show_if /
  // require_if ON THE DEPENDENT (target) field, never as an action list on the
  // trigger field.
  // On the read-only dependent field: how it unlocks when its show_if holds.
  "conditional_behavior": {{"unlock_method": "flip_readonly_bit"}},
  "conditional_logic": {{"unlock_method": "flip_readonly_bit",
                        "pdf_field_flag_change": {{...}}}}  // I-90 gold shape
}}

A CONDITION is either ONE atom  {{"field": str(other field id), "operator": str,
"value": any}}  or ONE composite group whose buckets hold atoms:
{{"all_of": [atom, ...]}}, {{"any_of": [...]}}, {{"none_of": [...]}}. A group MAY
carry MORE THAN ONE bucket at once (e.g. all_of PLUS none_of = "all these AND
none of those"); atoms never nest inside atoms (depth 1).

{operator_block}

RULES:
- Use the EXACT pdf_field_name from the provided AcroForm field list when given;
  never invent or normalize it. It is the only reliable cross-reference.
- Do NOT emit parts, sections, or field section_id -- form divisions are
  derived deterministically from the PDF after extraction (bd 6cfu.2), so any
  boundaries you produce are overwritten.
- Do NOT emit pdf_position -- widget geometry is read straight from the PDF's
  own AcroForm widgets after extraction and overwrites anything you send, so
  transcribing coordinates only loses precision. Spend that effort on getting
  pdf_field_name exactly right: it is the key the position is looked up by.
- Recover conditional logic from the PRINTED instructions on the page, not
  guesses. Express a "show / require this field when X" dependency as show_if /
  require_if ON THE DEPENDENT FIELD. For a read-only field a choice unlocks, put
  the unlock descriptor (conditional_behavior / conditional_logic) ON THAT FIELD
  with a show_if naming the choice -- that is what the runtime and PDF filler
  read. NEVER emit controls_fields or conditional_fields: both are REMOVED v1
  mechanisms with no v2 reader; a trigger-side action list does nothing at
  runtime, so any dependency must be expressed target-side instead.
- Output MUST be a single valid JSON object, UTF-8, ASCII-safe, no trailing commas.

CHOICE-FIELD RULES (radio / select / checkbox_group -- these MUST round-trip):
- Consolidate split widgets: a group of checkbox/radio widgets sharing one
  logical question is ONE field with an options[] array, each option carrying its
  widget name in option.pdf_field_name.
- A multi-select question (several boxes may be ticked) is type "checkbox_group"
  with NO field-level pdf_field_name -- per-box identity lives on
  options[].pdf_field_name. A single standalone yes/no box is type "checkbox".
  A pick-exactly-one set is type "radio"; a dropdown is "select".
- For a RADIO or CHECKBOX_GROUP, option.value MUST be a SEMANTIC SLUG minted
  from the option label: lowercase ASCII [a-z0-9_-], no commas or spaces,
  UNIQUE within the field. Do NOT use a widget-leaf identifier or a raw
  on-state as the value -- the widget identity lives in option.pdf_field_name
  (and pdf_on_value for shared-name radio kids).
- For a SELECT (dropdown) this rule does NOT apply: its option.value is the
  PDF's own EXPORT CODE (e.g. "WY"), because a dropdown writes its value
  straight into the PDF box with no separate widget mapping. Do not invent or
  slugify these. You do not need to emit a dropdown's options at all -- the
  full choice list is copied from the PDF itself after extraction, and the
  choices shown to you in the field list are only a SAMPLE. Emit the field with
  its type, name and help text; leave options[] out.
- Any show_if / require_if that references a RADIO or CHECKBOX_GROUP option MUST
  use that option's SLUG as the value, with a membership operator (includes /
  not_includes) for a checkbox_group trigger, or equals / in for a radio one.
  A condition on a SELECT trigger uses that dropdown's PDF EXPORT CODE (e.g.
  "WY") with equals / in -- there is no slug to reference, since a select's
  options are filled in from the PDF after extraction. If you cannot see the
  exact code in the sampled choice list, omit the condition rather than guess
  it: a condition naming a value the dropdown does not have is dropped.

CANONICAL v2 EXAMPLE (imitate its conventions: slug option values, per-box
pdf_field_name, and an `includes` membership show_if referencing an option
slug; divisions are absent on purpose -- they are derived after extraction):
{example}

RELATIONSHIP EMPHASIS (read carefully -- a common miss):
- show_if and require_if are DIFFERENT relationships. show_if = the field only
  APPEARS when the condition holds (conditional VISIBILITY). require_if = the
  field MUST be completed when the condition holds (conditional REQUIREDNESS).
- A field is FREQUENTLY BOTH: when the printed instruction says a field both
  appears and must be filled under the same trigger ("if you checked box d,
  complete lines 1-3"), emit BOTH show_if AND require_if with the SAME
  condition on that field. Recovering only show_if and dropping require_if is
  the most common relationship error -- do not make it.
- require_if can also stand alone (a field always visible but required only
  under a condition) and can carry a BROADER condition than show_if (required
  if ANY of several boxes, shown if one). Read the printed text for which
  boxes make the field mandatory.

EXAMPLE (shape only, not from any target form) -- a field shown AND required by
the same trigger:
  {{"id": "spouse_details", "type": "text",
   "show_if":    {{"field": "is_married", "operator": "is_checked"}},
   "require_if": {{"field": "is_married", "operator": "is_checked"}}}}
"""


# ---------------------------------------------------------------------------
# Public contract string. Rendered once at import (backwards-compatible name: the
# bake-off arms import SCHEMA_CONTRACT directly).
# ---------------------------------------------------------------------------
SCHEMA_CONTRACT: str = render_contract()


def acroform_field_list(dump: dict, max_fields: Optional[int] = None) -> str:
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
            # The list is SAMPLED, so say so (bd polyglot-pdf-hmkas). A bare
            # 12-of-63 render reads as the complete set, and asking a model to
            # emit the other 51 from it invites hallucination -- the i-90 state
            # dropdown showed 12 codes with no marker and came out with no
            # options at all. The full set is backfilled deterministically from
            # the dump (extract_form._backfill_dropdown_options), so this line
            # is only a hint that the field IS a dropdown and roughly what its
            # values look like.
            choices = w0["choices"]
            # .get(), not direct indexing (bd polyglot-pdf-r311s): a choice
            # dict missing "value" (a malformed/hand-edited dump, or a future
            # producer with a different shape) must degrade to a skipped
            # sample entry, matching this file's defensive style elsewhere --
            # not crash prompt building outright on a hot path every
            # extraction runs through. Not reachable via the current
            # acroform_dump.py producer (it always writes value+display), but
            # latent.
            # Sliced to 12 AFTER filtering, not before (bd polyglot-pdf-r311s,
            # Opus cross-surface finding): filtering the already-sliced
            # choices[:12] would shrink the SAMPLE below 12 whenever a
            # value-less dict falls within the first 12 slots, while `more`
            # still only counted entries past index 12 -- undercounting the
            # true number hidden from the model (shown + more != total),
            # exactly the unmarked-truncation failure bd hmkas exists to
            # prevent. Filtering first keeps shown + more == len(usable
            # values) always, and a value-less choice simply does not count
            # toward either shown or hidden.
            usable = [c["value"] for c in choices if isinstance(c, dict) and "value" in c]
            vals = ",".join(usable[:12])
            more = len(usable) - 12
            suffix = f", ... and {more} more" if more > 0 else ""
            bits.append(f"choices=[{vals}{suffix}]")
        if any("on_value" in w for w in f["widgets"]):
            ons = [w["on_value"] for w in f["widgets"] if w.get("on_value")]
            bits.append("on=" + ",".join(ons[:8]))
        lines.append("  " + " | ".join(bits))
    header = (f"ACROFORM FIELD LIST ({dump.get('field_count')} fields, "
              f"{dump.get('widget_count')} widgets, "
              f"{dump.get('page_count')} pages):")
    return header + "\n" + "\n".join(lines)
