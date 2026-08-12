"""
Unit tests for ValidationRules.min/max accepting a date-string bound
(bd polyglot-pdf-ondn).

backend/utils/field_validator.py's _validate_date (bd polyglot-pdf-3t3l)
supports authoring a date field's min/max bound as either the field's own
layout ('01/01/2000') or ISO ('2000-01-01') -- but that path was previously
exercised ONLY via a hand-built raw dict (test_date_format_resolution.py),
never through the real Pydantic FormField/ValidationRules model.
ValidationRules.min/max were declared Optional[float], so constructing the
REAL model with a date-string bound raised a float_parsing ValidationError --
the model rearward-rejected exactly the input field_validator.py was written
to accept. These tests build the real Pydantic model, per this repo's
"verify claims against code, not the brief" convention.

ASCII only.
"""
from backend.models.form_models import FormField, ValidationRules
from backend.utils.field_validator import validate_field_value


def _date_field(min_bound=None, max_bound=None):
    return FormField(
        id="dob",
        name="Date of birth",
        spoken_name="date of birth",
        type="date",
        section_id="sec_1",
        help={"format_hint": "MM/DD/YYYY"},
        validation=ValidationRules(min=min_bound, max=max_bound),
    )


def test_a_date_string_min_bound_constructs_the_real_pydantic_model():
    """The exact regression: this used to raise float_parsing."""
    field = _date_field(min_bound="01/01/2000")
    assert field.validation.min == "01/01/2000"


def test_a_date_string_max_bound_constructs_the_real_pydantic_model():
    field = _date_field(max_bound="2000-01-01")
    assert field.validation.max == "2000-01-01"


def test_a_numeric_bound_still_constructs_and_validates_as_before():
    """The widening must not break the ordinary numeric-field case."""
    field = FormField(
        id="age",
        name="Age",
        spoken_name="age",
        type="number",
        section_id="sec_1",
        validation=ValidationRules(min=18, max=120),
    )
    errors = validate_field_value(field.model_dump(), 10)
    assert any(e.constraint == "min" for e in errors)


def test_the_real_model_enforces_a_date_string_min_bound_end_to_end():
    """Not just "constructs" -- the bound the model now accepts must actually
    be enforced by validate_field_value, exercised through model_dump() the
    way a real caller (e.g. /api/fill-pdf) would use it."""
    field = _date_field(min_bound="01/01/2000")
    field_dict = field.model_dump()

    errors = validate_field_value(field_dict, "06/15/1999")
    assert any(e.constraint == "min" for e in errors)

    errors_ok = validate_field_value(field_dict, "06/15/2001")
    assert not any(e.constraint == "min" for e in errors_ok)


def test_a_string_bound_on_a_number_field_is_skipped_not_a_crash():
    """A date-string bound is only meaningful on a DATE field. On a NUMBER
    field it is an authoring mistake -- _validate_number must skip it
    (matching field_validator's documented 'unparseable bound is skipped'
    convention) rather than raising TypeError comparing float to str."""
    field = FormField(
        id="x",
        name="X",
        spoken_name="x",
        type="number",
        section_id="sec_1",
        validation=ValidationRules(min="01/01/2000"),
    )
    # Must not raise.
    errors = validate_field_value(field.model_dump(), 5)
    assert errors == []


def test_a_numeric_string_bound_still_coerces_and_enforces_on_a_number_field():
    """bd polyglot-pdf-ondn, round 2 (Opus cross-surface review): widening
    min/max to Optional[Union[float, str]] made Pydantic's SMART-MODE union
    resolution pick the str arm for ANY string input without first trying
    to parse it as a number -- so a NUMERIC-STRING bound authored on a
    NUMBER field (e.g. min="18", a plausible authoring habit) silently
    stayed a str, then _validate_number's isinstance guard (added to stop a
    genuinely non-numeric bound from crashing) SKIPPED it entirely. That
    turned "reject values under 18" into "no bound at all", with no error
    anywhere -- confirmed as a genuine regression against origin/dev, where
    plain Optional[float] coerced "18" -> 18.0 and enforced it. A
    ValidationRules field_validator now tries float() first, falling back
    to leaving the value as a string only when that fails (a genuine date
    string), which restores the pre-widening numeric-coercion behavior
    while still accepting a real date-string bound for a date field."""
    field = FormField(
        id="age",
        name="Age",
        spoken_name="age",
        type="number",
        section_id="sec_1",
        validation=ValidationRules(min="18"),
    )
    assert field.validation.min == 18.0  # coerced, not left as the string "18"

    errors = validate_field_value(field.model_dump(), 10)
    assert any(e.constraint == "min" for e in errors), (
        "a numeric-STRING min bound on a number field must still be "
        "enforced, not silently skipped"
    )

    errors_ok = validate_field_value(field.model_dump(), 25)
    assert not any(e.constraint == "min" for e in errors_ok)
