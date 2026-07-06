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


def _claimed_widget_names(schema: Dict[str, Any], dump_names: List[str]) -> set:
    """Every dump widget name a field or option pdf_field_name resolves to."""
    claimed: set = set()

    def register(claim: Any) -> None:
        if isinstance(claim, str) and claim:
            claimed.update(_match_dump_names(claim, dump_names))

    fields = schema.get("fields") if isinstance(schema, dict) else None
    if not isinstance(fields, list):
        return claimed
    for f in fields:
        if not isinstance(f, dict):
            continue
        register(f.get("pdf_field_name"))
        options = f.get("options")
        if isinstance(options, list):
            for o in options:
                if isinstance(o, dict):
                    register(o.get("pdf_field_name"))
    return claimed


def unclaimed_button_widgets(
    schema: Dict[str, Any], dump: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Button widgets in the dump that NO field/option in the schema claims.

    Each result: {name, on_value, tooltip, page} -- everything the picker needs
    to render a choice and mint an option (name -> option.pdf_field_name;
    on_value -> option.pdf_on_value; tooltip -> the suggested label). Returns []
    when there is no dump (the pre-v96b kits) -- the picker simply shows nothing.
    Deterministic dump order (top-to-bottom, page by page -- the dump preserves
    first-seen order).
    """
    if not isinstance(dump, dict):
        return []
    entries = dump.get("fields")
    if not isinstance(entries, list):
        return []
    dump_names = _dump_names(dump)
    claimed = _claimed_widget_names(schema if isinstance(schema, dict) else {}, dump_names)

    out: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("logical_type") not in _BUTTON_TYPES:
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name or name in claimed:
            continue
        widgets = entry.get("widgets")
        widget0 = widgets[0] if isinstance(widgets, list) and widgets else {}
        widget0 = widget0 if isinstance(widget0, dict) else {}
        rect = widget0.get("rect") if isinstance(widget0.get("rect"), dict) else {}
        out.append({
            "name": name,
            "type": entry.get("logical_type"),
            "on_value": widget0.get("on_value"),
            "tooltip": widget0.get("tu"),
            "page": rect.get("page"),
        })
    return out
