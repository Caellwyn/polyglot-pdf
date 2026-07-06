"""Unclaimed PDF button widgets for the author-tier "Add from PDF widgets" picker.

bd polyglot-pdf-nivy (P5.3c). The extractor sometimes misses a checkbox/radio
box when consolidating a group -- the box exists in the PDF but no field/option
in the schema claims it. This computes, from a kit's persisted AcroForm dump (the
acroform.json artifact, bd v96b) and its schema, the BUTTON widgets (checkbox /
radio) that NO field or option already claims -- the candidates an author can add
to a group.

"Claimed" reuses the SAME dump-name matching the linter's widget-claim rule uses
(schema_lint._match_dump_names: exact, else dot-boundary suffix), so the picker
and the lint rule agree on what a pdf_field_name resolves to.

Pure functions, no I/O. ASCII only.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.services.schema_lint import _dump_names, _match_dump_names

# Dump logical types that are addable button widgets (a text/choice widget is not
# an option a checkbox_group/radio can adopt).
_BUTTON_TYPES = frozenset({"checkbox", "radio"})


def _claimed_widgets(schema: Dict[str, Any], dump_names: List[str]) -> set:
    """The set of claimed widget keys: (dump_name, on_value_or_None).

    A per-widget group / standalone box claims a whole NAME -- registered as
    (name, None), which shadows every kid of that name. A SHARED-name radio group
    (one name, N kids differing only by pdf_on_value) claims a single kid --
    registered as (name, that_on_value). So a shared-name group with only some
    kids mapped leaves the rest addable (bd nivy fresh-eyes: the whole-name claim
    used to hide them all)."""
    claimed: set = set()

    def register(claim: Any, on_value: Any) -> None:
        if not isinstance(claim, str) or not claim:
            return
        key_on = on_value if isinstance(on_value, str) and on_value else None
        for name in _match_dump_names(claim, dump_names):
            claimed.add((name, key_on))

    fields = schema.get("fields") if isinstance(schema, dict) else None
    if not isinstance(fields, list):
        return claimed
    for f in fields:
        if not isinstance(f, dict):
            continue
        # A field-level pdf_field_name (standalone checkbox / shared-name radio
        # field) claims the whole NAME -- its options' pdf_on_value pins the kid.
        field_name = f.get("pdf_field_name")
        options = f.get("options")
        if isinstance(options, list):
            for o in options:
                if not isinstance(o, dict):
                    continue
                # An option may carry its OWN pdf_field_name (per-widget group,
                # whole-name claim) or ride the field's name + a pdf_on_value
                # (shared-name group, kid claim).
                if isinstance(o.get("pdf_field_name"), str) and o["pdf_field_name"]:
                    register(o.get("pdf_field_name"), None)
                elif isinstance(field_name, str) and field_name:
                    register(field_name, o.get("pdf_on_value"))
        if isinstance(field_name, str) and field_name and not options:
            # A standalone field with no options claims its whole name.
            register(field_name, None)
    return claimed


def unclaimed_button_widgets(
    schema: Dict[str, Any], dump: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Button WIDGETS in the dump that NO field/option in the schema claims.

    One result PER unclaimed kid widget (a shared-name radio group has N kids, so
    N candidates differing by on_value): {name, on_value, tooltip, page} --
    everything the picker needs to mint an option (name -> option.pdf_field_name;
    on_value -> option.pdf_on_value; tooltip -> the suggested label). Returns []
    when there is no dump (pre-v96b kits). Deterministic dump order (top-to-bottom;
    the dump preserves first-seen order).

    Claiming is per (name, on_value): a whole-name claim (per-widget group /
    standalone) shadows every kid of that name; a kid claim (shared-name group,
    (name, on_value)) shadows only that kid -- so a partly-mapped shared-name
    radio group still offers its unmapped kids (bd nivy fresh-eyes).
    """
    if not isinstance(dump, dict):
        return []
    entries = dump.get("fields")
    if not isinstance(entries, list):
        return []
    dump_names = _dump_names(dump)
    claimed = _claimed_widgets(schema if isinstance(schema, dict) else {}, dump_names)

    out: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("logical_type") not in _BUTTON_TYPES:
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        if (name, None) in claimed:
            continue  # the whole name is claimed -> every kid is taken
        widgets = entry.get("widgets")
        if not isinstance(widgets, list) or not widgets:
            widgets = [{}]
        for w in widgets:
            w = w if isinstance(w, dict) else {}
            on_value = w.get("on_value")
            key_on = on_value if isinstance(on_value, str) and on_value else None
            # A kid is claimed by (name, its on_value); a kid with no on_value on
            # a multi-kid entry can only be matched by the whole-name claim
            # (already excluded above), so it surfaces.
            if key_on is not None and (name, key_on) in claimed:
                continue
            rect = w.get("rect") if isinstance(w.get("rect"), dict) else {}
            out.append({
                "name": name,
                "type": entry.get("logical_type"),
                "on_value": on_value,
                "tooltip": w.get("tu"),
                "page": rect.get("page"),
            })
    return out
