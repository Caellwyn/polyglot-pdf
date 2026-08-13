"""
Unit tests for FormField.min/max accepting a date-string bound
(bd polyglot-pdf-9ec2u).

FormField.min/max is the TOP-LEVEL numeric bound (distinct from the nested
ValidationRules.min/max the field_validator's constraint resolution actually
reads -- see test_validation_rules_date_bound_type.py for that sibling).
Currently DORMANT: backend/services/field_utils.py's build_fields_from_schema
never passes min/max through when constructing a FormField from raw kit
JSON, so no shipped code path exercises this field today.

Before this fix it was Optional[float] while:
  - the nested ValidationRules.min/max (same file) was already
    Optional[Union[float, str]] (bd polyglot-pdf-ondn), and
  - the frontend FormField.min/max TS type was already `number | string`
    (bd polyglot-pdf-hhwgi), matching shipped date-typed fields carrying a
    top-level string bound (e.g. adult_intake_demo_schema.json's dob min
    "1900-01-01").

So constructing FormField(min="1900-01-01") directly raised a Pydantic
float_parsing ValidationError, silently narrower than both the FE type and
the sibling nested model -- a landmine for any future caller that DOES
construct FormField directly from raw kit JSON carrying a string bound.

ASCII only.
"""
from backend.models.form_models import FormField


def _base_kwargs(**overrides):
    kwargs = dict(
        id="dob", name="Date of birth", spoken_name="date of birth",
        type="date", section_id="sec_1",
    )
    kwargs.update(overrides)
    return kwargs


def test_a_date_string_min_bound_constructs_the_real_pydantic_model():
    """The exact regression: this used to raise float_parsing."""
    field = FormField(**_base_kwargs(min="1900-01-01"))
    assert field.min == "1900-01-01"


def test_a_date_string_max_bound_constructs_the_real_pydantic_model():
    field = FormField(**_base_kwargs(max="2026-01-01"))
    assert field.max == "2026-01-01"


def test_a_numeric_bound_still_constructs_as_before():
    """The widening must not break the ordinary numeric-field case."""
    field = FormField(**_base_kwargs(type="number", min=18, max=120))
    assert field.min == 18.0
    assert field.max == 120.0


def test_a_numeric_string_bound_still_coerces_to_float():
    """Mirrors ValidationRules._coerce_numeric_bound's own regression guard
    (bd polyglot-pdf-ondn round 2): a digit-only string bound must coerce to
    a float, not silently stay a string under Pydantic's smart-mode union
    resolution -- else a numeric bound authored as a string enforces nothing."""
    field = FormField(**_base_kwargs(type="number", min="18"))
    assert field.min == 18.0  # coerced, not left as the string "18"


def test_field_dump_round_trips_a_date_string_bound():
    """The bound must survive a model_dump()/reconstruct cycle -- the shape
    build_fields_from_schema would need if it ever DOES pass min/max
    through from raw kit JSON."""
    field = FormField(**_base_kwargs(min="1900-01-01", max="2026-01-01"))
    dumped = field.model_dump()
    assert dumped["min"] == "1900-01-01"
    assert dumped["max"] == "2026-01-01"

    rebuilt = FormField(**dumped)
    assert rebuilt.min == "1900-01-01"
    assert rebuilt.max == "2026-01-01"
