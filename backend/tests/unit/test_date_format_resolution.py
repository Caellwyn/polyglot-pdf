"""Date fields validate against their OWN declared layout, not a hardcoded ISO.

THE BUG THIS PINS (maintainer report 2026-08-03): on a form whose printed label
AND schema hint both say MM/DD/YYYY, the voice model kept asking users for
year-first dates. Two independent faults compounded:

  1. `_validate_date` read the layout ONLY from a flat `format` key and fell
     back to a hardcoded "YYYY-MM-DD". No shipped kit sets flat `format` on a
     date field -- i-90 and w7 both carry the layout in `help.format_hint`
     (the schema editor's "Format Hint" box), and i-90 also in
     `validation.hint`.
  2. `validation_handler._convert_fields_to_dicts` did not forward `format`,
     `help`, or `validation.hint` into the validator dict at all, so even a kit
     that DID set `format` could not reach the validator.

Net effect: a correctly-filled "10/25/1984" was rejected with "Invalid format
(expected YYYY-MM-DD)". The voice model is told MM/DD/YYYY via that same
help.format_hint, complies, gets contradicted by the validator's error text, and
adapts to what the error demands -- which is why prompt-side fixes never held.

Knock-on: the rejection returned BEFORE date_constraint/min/max were evaluated,
and every check lived inside `if format == "YYYY-MM-DD"`, so NO date-sanity rule
(incl. past_only) could ever fire on a real kit field.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend.utils.field_validator import _resolve_date_format, _validate_date

_KITS = Path(__file__).resolve().parents[3] / "form-kits"


def _find_field(node, field_id):
    """Depth-first search for a field dict by id anywhere in a kit schema."""
    if isinstance(node, dict):
        if node.get("id") == field_id:
            return node
        for value in node.values():
            found = _find_field(value, field_id)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_field(value, field_id)
            if found:
                return found
    return None


def _kit_field(kit, field_id):
    schema = json.loads((_KITS / kit / "schema.json").read_text(encoding="utf-8"))
    field = _find_field(schema, field_id)
    assert field is not None, f"{field_id} missing from {kit} -- kit changed?"
    return field


# --- the real shipped kits (the regression the maintainer actually hit) -------

def test_w7_date_of_birth_accepts_its_declared_mm_dd_yyyy():
    """The exact reported case: US-style date on the W-7's date_of_birth."""
    field = _kit_field("w7", "date_of_birth")
    # Guard the premise: if the kit stops declaring the hint, this test is
    # vacuous and must fail loudly rather than silently passing.
    assert field.get("help", {}).get("format_hint") == "MM/DD/YYYY"
    assert _validate_date(field, "10/25/1984", "date_of_birth", "Date of birth") == []


def test_w7_date_of_birth_rejects_iso_and_names_the_right_format():
    """ISO is WRONG for this field, and the error must name MM/DD/YYYY -- the
    error text is what the model learns from, so a stale format name in it is
    what re-taught the model to ask year-first."""
    field = _kit_field("w7", "date_of_birth")
    errors = _validate_date(field, "1984-10-25", "date_of_birth", "Date of birth")
    assert len(errors) == 1
    assert "MM/DD/YYYY" in errors[0].message
    assert "YYYY-MM-DD" not in errors[0].message


def test_layout_resolves_from_validation_hint_not_just_help():
    """The layout may live in validation.hint as well as help.format_hint.

    SYNTHETIC on purpose (bd polyglot-pdf-1mgkq): this is a fact about the
    RESOLVER's precedence, not about any one form. It used to read the i-90's
    date_of_birth, which coupled a generic rule to a kit that authors republish
    continuously -- and duly broke when that kit's field ids changed.
    """
    field = {
        "id": "dob",
        "name": "Date of birth",
        "type": "date",
        "validation": {"hint": "MM/DD/YYYY"},
    }
    assert _validate_date(field, "03/15/1985", "dob", "Date of birth") == []
    # ...and the hint is genuinely load-bearing: a mismatched value is rejected.
    assert _validate_date(field, "1985-03-15", "dob", "Date of birth") != []


def test_prose_format_hint_still_resolves_a_layout():
    """W-7's date_of_entry_us hint is prose: 'MM/DD/YYYY or "Never Entered US"'.
    The layout token must be found INSIDE the sentence."""
    field = _kit_field("w7", "date_of_entry_us")
    assert "or" in field["help"]["format_hint"]
    assert _resolve_date_format(field) == ("%m/%d/%Y", "MM/DD/YYYY")


# --- layout resolution priority + shapes -------------------------------------

@pytest.mark.parametrize(
    "field,expected",
    [
        ({"format": "mm/dd/yyyy"}, ("%m/%d/%Y", "MM/DD/YYYY")),
        ({"format": "YYYY-MM-DD"}, ("%Y-%m-%d", "YYYY-MM-DD")),
        ({"help": {"format_hint": "MM/DD/YYYY"}}, ("%m/%d/%Y", "MM/DD/YYYY")),
        ({"validation": {"hint": "MM/DD/YYYY"}}, ("%m/%d/%Y", "MM/DD/YYYY")),
        ({"format": "yyyy"}, ("%Y", "YYYY")),
        ({"format": "Mo/Yr"}, ("%m/%Y", "MM/YYYY")),
        # Case-insensitive, whitespace-tolerant.
        ({"help": {"format_hint": "  mm/dd/yyyy  "}}, ("%m/%d/%Y", "MM/DD/YYYY")),
    ],
)
def test_layout_resolution_reads_every_declared_source(field, expected):
    assert _resolve_date_format(field) == expected


@pytest.mark.parametrize(
    "hint,expected_label",
    [
        # A hint naming TWO layouts must resolve to the one mentioned FIRST --
        # picking the other would silently choose the layout the author
        # explicitly ruled out. Position dominates token length.
        ("Use MM/DD/YYYY not DD/MM/YYYY", "MM/DD/YYYY"),
        ("Use DD/MM/YYYY not MM/DD/YYYY", "DD/MM/YYYY"),
        # ...while length still breaks ties, so a bare "yyyy" cannot shadow a
        # longer layout that starts at the same place.
        ("yyyy-mm-dd then notes", "YYYY-MM-DD"),
        ("Year only (yyyy)", "YYYY"),
    ],
)
def test_prose_hint_prefers_the_earliest_named_layout(hint, expected_label):
    assert _resolve_date_format({"format": hint})[1] == expected_label


def test_validation_hint_survives_the_real_pydantic_model():
    """validation.hint is one of the three declared layout sources, but it only
    works if ValidationRules DECLARES the field -- Pydantic silently drops an
    undeclared key at construction, so the hint would never reach the validator
    and the field would fall back to ISO (Opus fresh-eyes round 1).

    Drives the REAL model + the REAL handler, not a hand-built dict, because a
    dict-only test passes even when the model drops the key."""
    from backend.models.form_models import FieldType, FormField, ValidationRules
    from backend.services.validation_handler import ValidationHandler

    assert "hint" in ValidationRules.model_fields, (
        "ValidationRules dropped `hint` -- validation.hint layout resolution is dead")

    field = FormField(
        id="dob", type=FieldType.DATE, name="Date of birth",
        spoken_name="date of birth", section_id="s1",
        validation=ValidationRules(hint="MM/DD/YYYY"),
    )
    result = ValidationHandler(session_id="t").validate_field_updates(
        [field], {"dob": "10/25/1984"})
    assert result["validation_errors"] == []
    assert result["applied_fields"] == ["dob"]


def test_unrecognizable_prose_falls_back_to_iso():
    """A spelled-out hint with no layout token must not guess."""
    assert _resolve_date_format({"format": "month/day/year"})[1] == "YYYY-MM-DD"


def test_flat_format_wins_over_nested_hint():
    """Priority order is format -> help.format_hint -> validation.hint."""
    field = {"format": "YYYY-MM-DD", "help": {"format_hint": "MM/DD/YYYY"}}
    assert _resolve_date_format(field) == ("%Y-%m-%d", "YYYY-MM-DD")


def test_format_less_field_still_defaults_to_iso():
    """Back-compat: a field declaring no layout keeps the historical ISO
    behaviour, so existing callers and fixtures are unaffected."""
    field = {"id": "x", "type": "date"}
    assert _resolve_date_format(field) == ("%Y-%m-%d", "YYYY-MM-DD")
    assert _validate_date(field, "1984-10-25", "x", "X") == []
    assert _validate_date(field, "10/25/1984", "x", "X") != []


def test_impossible_dates_are_rejected_in_the_declared_layout():
    """strptime is the single gate: it catches a wrong layout AND a calendar
    impossibility (month 13, day 45) without a separate regex."""
    field = {"help": {"format_hint": "MM/DD/YYYY"}}
    assert _validate_date(field, "13/45/2020", "x", "X") != []
    assert _validate_date(field, "02/30/2020", "x", "X") != []


# --- date sanity now actually reachable --------------------------------------

def test_past_only_now_fires_on_a_non_iso_field():
    """THE KNOCK-ON FIX: date_constraint used to live inside
    `if format == "YYYY-MM-DD"`, so a MM/DD/YYYY field skipped it entirely --
    a future date sailed through. It must now be caught."""
    future = (datetime.now() + timedelta(days=3650)).strftime("%m/%d/%Y")
    field = {
        "help": {"format_hint": "MM/DD/YYYY"},
        "validation": {"date_constraint": "past_only"},
    }
    errors = _validate_date(field, future, "dob", "Date of birth")
    assert len(errors) == 1
    assert errors[0].constraint == "date_constraint"


def test_min_max_bounds_accept_the_fields_own_layout_or_iso():
    """A bound may be authored in the field's layout or in ISO; both parse."""
    field_own = {
        "help": {"format_hint": "MM/DD/YYYY"},
        "validation": {"min": "01/01/2000"},
    }
    assert _validate_date(field_own, "06/15/1999", "x", "X") != []
    assert _validate_date(field_own, "06/15/2001", "x", "X") == []

    field_iso = {
        "help": {"format_hint": "MM/DD/YYYY"},
        "validation": {"min": "2000-01-01"},
    }
    assert _validate_date(field_iso, "06/15/1999", "x", "X") != []
    assert _validate_date(field_iso, "06/15/2001", "x", "X") == []


def test_unparseable_bound_is_skipped_not_reported_as_user_error():
    """A malformed min/max is an AUTHORING mistake -- it must not surface to the
    user as though their answer were wrong."""
    field = {
        "help": {"format_hint": "MM/DD/YYYY"},
        "validation": {"min": "not-a-date"},
    }
    assert _validate_date(field, "06/15/2001", "x", "X") == []
