"""
Field utility functions for form schema processing.

Pure functions for building field objects, fuzzy matching field names,
and extracting field metadata from schemas. These functions are stateless
and can be used independently of the FormFillingService.
"""
import re
from typing import Any, Dict, List, Optional
from backend.models.form_models import FormField, FieldType


# The frontend's formatNextFieldHint (frontend/src/navigation.ts) appends a
# technical parenthetical to the SPOKEN hint, e.g.
#   "Next field to fill is #1: 'Alien Registration Number' (field_id: 'p1_line1_aliennumber', type: text, required, options: [Brown, Blue])"
# Gemini reads that parenthetical aloud, so the user hears the raw field_id
# (bd polyglot-pdf-dx7). The field_id is NOT needed in the spoken hint: Gemini
# already gets every field_id from the FIELDS block of the system instruction
# (ai_context.fields_text -> "ID: <field_id>"), which is what it passes to
# update_form_fields. So we strip the parenthetical before any hint reaches the
# SPOKEN path.
#
# The parenthetical begins with "(field_id:". It USED to be the frontend's last
# group (so an end-anchored "...\)\s*$" removed it whole -- important because an
# option LABEL inside the group can itself contain ")", e.g. "Other (specify)",
# so we must run to the LAST ")" not the first). But formatNextFieldHint now
# appends an OPTIONAL note tail AFTER the group (bd polyglot-pdf-bo4m):
#   "... (field_id: 'x', type: text). Context to briefly convey when asking: <help.instructions>"
# The note is the FINE PRINT the model must SPEAK, so we strip ONLY the field_id
# group and KEEP the note (dx7 removes the id; bo4m keeps the context).
#
# Two problems with a naive fix: end-anchoring to $ fails once a note follows;
# and the note text itself can contain ")" (e.g. "(A-Number)"), so we cannot just
# find the last ")" in the whole string. Solution: peel the note tail off FIRST
# by its fixed, unambiguous lead-in ". Context to briefly convey when asking:",
# strip the field_id group from the (note-free) head with the original
# end-anchored, last-")" pattern, then re-append the note. This preserves the
# dx7 "run to the last ) so an option's own ) doesn't end the match early"
# guarantee on the head, while keeping the bo4m note intact. The spoken name's
# own parens (e.g. "(A-Number)") come BEFORE "(field_id:" and are left intact.
_NOTE_TAIL_RE = re.compile(r"\.\s*Context to briefly convey when asking:.*\Z", re.DOTALL)
_SPOKEN_HINT_FIELD_ID_RE = re.compile(r"\s*\(field_id:\s*'[^']*'.*\)\s*$")


def strip_field_id_from_hint(hint: Optional[str]) -> Optional[str]:
    """Remove the technical "(field_id: ...)" parenthetical from a spoken hint.

    Safe to call on any hint (returns None/empty unchanged). Only affects the
    SPOKEN path -- the field_id Gemini needs for the tool call comes from the
    system instruction's FIELDS block, not the hint (bd polyglot-pdf-dx7).

    Removes ONLY the field_id parenthetical -- any "Context to briefly convey
    when asking: ..." note tail the frontend appended after it
    (bd polyglot-pdf-bo4m) is deliberately KEPT (it is the fine print the model
    must speak). The note is peeled off first so the end-anchored field_id strip
    (which runs to the LAST ")" so an option label's own ")" does not end it
    early) operates on the note-free head, then the note is re-appended.
    """
    if not hint:
        return hint
    note_match = _NOTE_TAIL_RE.search(hint)
    if note_match:
        head = hint[: note_match.start()]
        note = hint[note_match.start():]
    else:
        head, note = hint, ""
    stripped_head = _SPOKEN_HINT_FIELD_ID_RE.sub("", head).strip()
    return (stripped_head + note).strip()


def build_fields_from_schema(schema: Dict[str, Any]) -> List[FormField]:
    """Build field list from schema (stateless).

    Constructs FormField objects from a form schema dictionary.
    Used by web sessions to build field objects for validation.

    Args:
        schema: Form schema dictionary with 'fields' array

    Returns:
        List of FormField objects with populated metadata

    Note:
        The backend doesn't persist these fields - they're rebuilt each time.
    """
    fields = []

    for field_data in schema.get("fields", []):
        try:
            # Build FormField object from schema
            # Extract only the properties that exist in the current FormField model
            field_type_str = field_data.get("type", "text")

            # Convert string type to FieldType enum
            try:
                field_type = FieldType(field_type_str)
            except ValueError:
                field_type = FieldType.TEXT

            # Handle SELECT/RADIO fields that require options
            options = field_data.get("options")
            if field_type in [FieldType.SELECT, FieldType.RADIO]:
                # If options are missing, skip this field
                # This shouldn't happen in production, but prevents crashes
                if not options:
                    print(f"WARNING: Skipping field {field_data.get('id')} - type {field_type} requires options but none provided")
                    continue

            field = FormField(
                id=field_data.get("id"),
                name=field_data.get("name"),
                spoken_name=field_data.get("spoken_name") or field_data.get("name"),
                spoken_aliases=field_data.get("spoken_aliases") or [],
                type=field_type,
                section_id=field_data.get("section_id", ""),  # Required field
                validation=field_data.get("validation"),
                options=options,
                # Date/format LAYOUT sources (bd polyglot-pdf-mpfmr). This
                # constructor passes an explicit ALLOWLIST of keys, so anything
                # absent here is silently dropped from the session's FormField
                # -- and `help` was absent. help.format_hint is the CANONICAL
                # layout carrier (the schema editor's "Format Hint" box writes
                # it, and the shipped i-90 / w7 kits populate it for dates), so
                # every date field reached field_validator with no declared
                # layout and fell back to the ISO default: a correct
                # "10/12/2005" came back "Invalid date (expected YYYY-MM-DD)",
                # and the voice model then adapted to that error text and
                # started demanding year-first dates from users.
                #
                # validation_handler._convert_fields_to_dicts already forwards
                # both of these downstream, and field_validator's layout
                # resolution already reads format -> help.format_hint ->
                # validation.hint. Those layers were correct; they were just
                # operating on a FormField that no longer carried the hint.
                # The flat `format` key rides along because it is the FIRST
                # source in that same priority chain.
                help=field_data.get("help"),
                format=field_data.get("format"),
            )
            fields.append(field)
        except Exception as e:
            # Log field that failed to build but continue processing others
            field_id = field_data.get("id", "unknown")
            print(f"ERROR: Failed to build field {field_id}: {e}")
            continue

    return fields
