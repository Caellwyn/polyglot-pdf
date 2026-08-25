"""build_fields_from_schema property passthrough (bd polyglot-pdf-mpfmr).

build_fields_from_schema constructs FormField from an explicit ALLOWLIST of
schema keys. Anything not named there is silently dropped -- no error, no log,
and every downstream layer then operates correctly on a field that has lost the
data. That shape has now produced at least three separate defects:

  - help.format_hint (this bead): every date field reached the validator with
    no declared layout, fell back to the ISO default, and rejected a correct
    "10/12/2005" as "Invalid date (expected YYYY-MM-DD)". The voice model read
    that error text and started demanding year-first dates from users.
  - hidden / read_only (test_52qm7_static_field_states.py).
  - min / max (documented dormant in form_models.py).

So the SET is pinned here, not the instance. EXPECTED_PASSED_THROUGH is checked
against FormField's DECLARED fields, so adding a property to the model without
deciding its passthrough status fails CI instead of becoming defect number four.
Deriving from the model rather than hand-listing is deliberate (bd memory
enumerate-the-block-dont-hand-list-it).
"""

import pytest

from backend.models.form_models import FormField
from backend.services.field_utils import build_fields_from_schema
from backend.services.validation_handler import ValidationHandler
from backend.utils import field_validator as fv


# Properties build_fields_from_schema is EXPECTED to carry from raw schema
# JSON onto the constructed FormField.
EXPECTED_PASSED_THROUGH = {
    "id",
    "name",
    "spoken_name",
    "spoken_aliases",
    "type",
    "section_id",
    "validation",
    "options",
    "help",
    "format",
}

# Properties deliberately NOT passed through, each with the reason it is out of
# scope. Kept as a mapping so the exclusion is a documented decision rather than
# an accident. Removing a key from here without adding it above fails the
# partition assertion below.
#
# NOTE: the reactive/visibility group (hidden, read_only, show_if, require_if,
# conditional_behavior) is a KNOWN defect deliberately left for a follow-up --
# turning those on inside a date bugfix could change form behavior in ways that
# are not obviously bugfixes. They are excluded here on purpose, not forgotten.
EXPECTED_DROPPED = {
    "address_fields": "layout/composite metadata; not used by backend validation",
    "auto_fill_na": "client-side fill behavior",
    "columns": "presentation only",
    "conditional_behavior": "reactive logic -- follow-up, see module docstring",
    "date_precision": "client-side widget precision; layout comes from format_hint",
    "description": "presentation only",
    "group_id": "presentation grouping",
    "group_label": "presentation grouping",
    "hidden": "reactive/visibility -- follow-up, see module docstring",
    "max": "nested validation.max is the carrier the backend reads",
    "max_date": "unread by field_validator (0 refs); no ValidationRules carrier exists either",
    "max_length": "nested validation.max_length is the carrier the backend reads",
    "min": "nested validation.min is the carrier the backend reads",
    "min_date": "unread by field_validator (0 refs); no ValidationRules carrier exists either",
    "multi_entry": "client-side repeat behavior",
    "overflow_to_supplement": "PDF render concern, not session validation",
    "pdf_field_name": "PDF render concern, not session validation",
    "pdf_position": "PDF render concern, not session validation",
    "placeholder": "presentation only",
    "read_only": "reactive/visibility -- follow-up, see module docstring",
    "require_if": "reactive logic -- follow-up, see module docstring",
    "rows": "presentation only",
    "section_label": "presentation grouping",
    "show_if": "reactive logic -- follow-up, see module docstring",
    "signature_box_style": "PDF render concern",
    "signature_method": "PDF render concern",
    "spoken_name_translations": "delivered via guidance rendering, not validation",
    "step": "presentation only (number spinner)",
    "textarea_size": "presentation only",
}


def test_expected_sets_partition_the_model_exactly():
    """The two expectation sets must together cover FormField exactly.

    This is the guard that makes the whole file self-maintaining: a NEW
    FormField property belongs to neither set and fails here, forcing a
    deliberate passthrough decision.
    """
    declared = set(FormField.model_fields.keys())
    covered = EXPECTED_PASSED_THROUGH | set(EXPECTED_DROPPED)

    assert not (EXPECTED_PASSED_THROUGH & set(EXPECTED_DROPPED)), (
        "a property cannot be both passed through and dropped"
    )
    assert covered == declared, (
        "FormField properties not classified: "
        f"{sorted(declared - covered)}; "
        f"classified but no longer on the model: {sorted(covered - declared)}"
    )


def _schema_with_all_properties():
    """A field declaring every passed-through property with a distinctive value."""
    return {
        "fields": [
            {
                "id": "dob",
                "name": "Date of birth",
                "spoken_name": "date of birth",
                "spoken_aliases": ["birthday"],
                "type": "date",
                "section_id": "sec1",
                "validation": {"required": True},
                "help": {"format_hint": "MM/DD/YYYY"},
                "format": "mm/dd/yyyy",
            }
        ]
    }


def _schema_help_only():
    """A date field whose ONLY layout source is help.format_hint.

    This mirrors the SHIPPED kits: form-kits/w7 and i-90 set help.format_hint
    and do NOT set the flat `format` key. The distinction is load-bearing for
    the end-to-end tests below -- a fixture that also sets `format` keeps
    passing when the `help` passthrough is removed, because the flat key masks
    the loss. That would make these tests green for the wrong reason under
    exactly the regression they exist to catch (bd memory
    mutation-verify-the-mutation-that-matters).
    """
    return {
        "fields": [
            {
                "id": "dob",
                "name": "Date of birth",
                "spoken_name": "date of birth",
                "type": "date",
                "section_id": "sec1",
                "validation": {"required": True},
                "help": {"format_hint": "MM/DD/YYYY"},
            }
        ]
    }


def _schema_with_options():
    """A SELECT field, so the `options` passthrough has something to carry.

    Options are meaningless on a date field, so the date fixture above cannot
    exercise them -- this is the second half of the parametrized coverage.
    """
    return {
        "fields": [
            {
                "id": "country",
                "name": "Country",
                "spoken_name": "country",
                "spoken_aliases": ["nation"],
                "type": "select",
                "section_id": "sec1",
                "validation": {"required": True},
                "help": {"format_hint": "pick one"},
                "format": "mm/dd/yyyy",
                "options": [{"value": "US", "label": "United States"}],
            }
        ]
    }


@pytest.mark.parametrize("prop", sorted(EXPECTED_PASSED_THROUGH))
def test_each_expected_property_survives_construction(prop):
    """Every property in the allowlist actually lands on the FormField.

    Parametrized per property (not one assertion over a dict) so a mutation
    dropping ONE key reddens exactly that case -- bd memory
    mutation-verify-per-parametrization.

    Uses whichever fixture can legitimately carry the property: `options` is
    only meaningful on a SELECT, every other property rides the date field.
    """
    schema = _schema_with_options() if prop == "options" else _schema_with_all_properties()
    built = build_fields_from_schema(schema)
    assert len(built) == 1
    field = built[0]

    value = getattr(field, prop, None)
    assert value is not None, (
        f"build_fields_from_schema dropped '{prop}' -- it is in "
        "EXPECTED_PASSED_THROUGH but did not survive construction"
    )


def test_help_format_hint_survives_with_its_value():
    """The specific payload this bead is about, not just presence of `help`."""
    field = build_fields_from_schema(_schema_with_all_properties())[0]
    assert field.help is not None, "help block dropped"
    assert field.help.format_hint == "MM/DD/YYYY"


def test_declared_date_layout_reaches_the_validator_end_to_end():
    """The REAL regression: kit JSON -> FormField -> validator dict -> layout.

    This is the property that actually broke. It is asserted through the real
    call chain rather than a hand-built dict, because every layer in that chain
    was individually correct while the end-to-end behavior was wrong -- a unit
    test on the layout resolver passed throughout the outage.
    """
    field = build_fields_from_schema(_schema_help_only())[0]

    handler = ValidationHandler.__new__(ValidationHandler)
    handler._session_id = "test"
    field_dict = handler._convert_fields_to_dicts([field])[0]

    directive, label = fv._resolve_date_format(field_dict)
    assert (directive, label) == ("%m/%d/%Y", "MM/DD/YYYY"), (
        "date layout did not survive to the validator; "
        f"got {label!r} (ISO here means the hint was dropped again)"
    )


def test_us_format_date_is_accepted_and_iso_is_rejected():
    """A correctly-filled MM/DD/YYYY date must not be rejected.

    Pins the user-visible symptom: the model submitted "10/12/2005", the
    backend rejected it as "expected YYYY-MM-DD", and the model then adapted to
    that error string and began demanding year-first dates.
    """
    field = build_fields_from_schema(_schema_help_only())[0]
    handler = ValidationHandler.__new__(ValidationHandler)
    handler._session_id = "test"
    field_dict = handler._convert_fields_to_dicts([field])[0]

    ok = fv._validate_date(field_dict, "10/12/2005", "dob", "Date of birth")
    assert ok == [], f"a valid MM/DD/YYYY date was rejected: {[e.message for e in ok]}"

    # The declared layout is enforced, so ISO input is the one that fails now.
    iso = fv._validate_date(field_dict, "2005-10-12", "dob", "Date of birth")
    assert iso, "ISO input should not satisfy a field declaring MM/DD/YYYY"
    assert "MM/DD/YYYY" in iso[0].message, (
        "the error must name the field's OWN declared layout -- the model reads "
        f"this string and adapts to it; got {iso[0].message!r}"
    )


def test_error_message_never_names_iso_for_a_us_declared_field():
    """No path may hand the model 'expected YYYY-MM-DD' for an MM/DD/YYYY field.

    Guards the PROPERTY (what the model is told) rather than the code shape --
    bd memory guard-the-property-not-the-code-shape. This is the string that
    retrained the model into year-first.
    """
    field = build_fields_from_schema(_schema_help_only())[0]
    handler = ValidationHandler.__new__(ValidationHandler)
    handler._session_id = "test"
    field_dict = handler._convert_fields_to_dicts([field])[0]

    for bad in ["2005-10-12", "13/45/2020", "not a date"]:
        for err in fv._validate_date(field_dict, bad, "dob", "Date of birth"):
            assert "YYYY-MM-DD" not in err.message, (
                f"input {bad!r} produced an ISO-naming error: {err.message!r}"
            )


# --- flat `format` coercion -------------------------------------------------
#
# FormField.format is a CLOSED DateFormat enum of 4 case-sensitive literals, and
# FormField construction sits inside a broad `except` that DROPS THE WHOLE FIELD
# on any error. So passing an unrecognized `format` string straight through does
# not merely lose the layout -- it removes the field from the session entirely,
# a strictly worse failure than the ISO-fallback bug this bead fixes. Caught by
# the fresh-eyes review of this diff: "MM/DD/YYYY" (the natural authoring
# casing, and the exact string help.format_hint uses on the shipped kits) is NOT
# a valid enum value.
#
# No shipped kit sets the flat key today, so these pin a hazard rather than a
# live break -- which is precisely when it is cheap to pin.

@pytest.mark.parametrize(
    "raw_format,expected_value",
    [
        ("mm/dd/yyyy", "mm/dd/yyyy"),   # exact enum literal
        ("MM/DD/YYYY", "mm/dd/yyyy"),   # natural authoring casing
        ("YYYY-MM-DD", "YYYY-MM-DD"),   # exact enum literal
        ("yyyy-mm-dd", "YYYY-MM-DD"),   # lowercased ISO
        ("Mo/Yr", "Mo/Yr"),             # exact enum literal
        ("mo/yr", "Mo/Yr"),             # lowercased
        ("  MM/DD/YYYY  ", "mm/dd/yyyy"),  # surrounding whitespace
    ],
)
def test_flat_format_resolves_case_insensitively(raw_format, expected_value):
    """Any casing of a real layout resolves, and the field always survives.

    Parametrized per casing so a mutation that handles only the exact-match
    branch reddens the case-insensitive rows specifically.
    """
    schema = {
        "fields": [
            {
                "id": "dob",
                "name": "Date of birth",
                "type": "date",
                "section_id": "sec1",
                "format": raw_format,
            }
        ]
    }
    built = build_fields_from_schema(schema)
    assert len(built) == 1, (
        f"format={raw_format!r} DROPPED THE ENTIRE FIELD from the session -- "
        "an unrecognized enum value must degrade to None, never delete the field"
    )
    assert built[0].format is not None
    assert built[0].format.value == expected_value


@pytest.mark.parametrize("raw_format", ["garbage", "dd/mm/yyyy", "", "   ", 42])
def test_unresolvable_flat_format_degrades_to_none_and_keeps_the_field(raw_format):
    """An unusable `format` must not cost the field, and must not mask the hint.

    Degrading to None leaves help.format_hint as the layout source -- exactly
    the behavior before the flat key was passed through at all.
    """
    schema = {
        "fields": [
            {
                "id": "dob",
                "name": "Date of birth",
                "type": "date",
                "section_id": "sec1",
                "help": {"format_hint": "MM/DD/YYYY"},
                "format": raw_format,
            }
        ]
    }
    built = build_fields_from_schema(schema)
    assert len(built) == 1, (
        f"format={raw_format!r} dropped the whole field instead of degrading"
    )
    assert built[0].format is None
    # The hint must still be the usable layout source.
    assert built[0].help is not None
    assert built[0].help.format_hint == "MM/DD/YYYY"


def test_unresolvable_flat_format_still_validates_dates_by_the_hint():
    """End-to-end: a junk `format` must not break date validation.

    The hint carries the layout, so a correct MM/DD/YYYY date is still accepted.
    """
    schema = {
        "fields": [
            {
                "id": "dob",
                "name": "Date of birth",
                "type": "date",
                "section_id": "sec1",
                "help": {"format_hint": "MM/DD/YYYY"},
                "format": "not-a-layout",
            }
        ]
    }
    field = build_fields_from_schema(schema)[0]
    handler = ValidationHandler.__new__(ValidationHandler)
    handler._session_id = "test"
    field_dict = handler._convert_fields_to_dicts([field])[0]

    assert fv._resolve_date_format(field_dict) == ("%m/%d/%Y", "MM/DD/YYYY")
    assert fv._validate_date(field_dict, "10/12/2005", "dob", "Date of birth") == []
