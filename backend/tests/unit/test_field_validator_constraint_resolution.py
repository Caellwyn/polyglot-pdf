"""
Unit tests for backend/utils/field_validator.py's _resolve_constraint fallback
chain (bd polyglot-pdf-1dz2).

_resolve_constraint reads a validation constraint from THREE possible shapes,
in order: validation.<snake_case> (canonical), validation.<camelCase>
(tolerant), then a flattened top-level key. The final top-level fallback used
to try ONLY the camelCase form (e.g. "maxLength"), so a real on-disk kit that
carries the constraint as a top-level SNAKE_CASE key with no nested
`validation` block at all (form-kits/w7/schema.json's date_of_entry_us,
"max_length": 16) silently lost its length constraint -- validate_field_value
returned VALID for any length. Loads the REAL on-disk schema rather than a
hand-built dict, per this repo's "verify claims against code, not the brief"
convention: a hand-built fixture could accidentally encode the same
assumption the bug depended on.

ASCII only.
"""
import json
from pathlib import Path

import pytest

from backend.utils.field_validator import validate_field_value

W7_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "form-kits" / "w7" / "schema.json"
)


def _load_w7_field(field_id: str) -> dict:
    data = json.loads(W7_SCHEMA_PATH.read_text(encoding="utf-8"))
    for field in data.get("fields", []):
        if field.get("id") == field_id:
            return field
    raise AssertionError(
        "field %r not found in %s -- schema may have been restructured; "
        "update this test's target field" % (field_id, W7_SCHEMA_PATH)
    )


def test_top_level_snake_case_max_length_is_enforced_on_the_real_w7_schema():
    """The exact regression: form-kits/w7/schema.json's date_of_entry_us
    carries a top-level snake_case max_length. Its `validation` block (if
    any) does not itself carry a length constraint, so the top-level key is
    the ONLY source -- confirming this test exercises the top-level fallback
    path, not the nested one. A value exceeding it must be rejected."""
    field = _load_w7_field("date_of_entry_us")
    validation = field.get("validation")
    if isinstance(validation, dict):
        assert "max_length" not in validation and "maxLength" not in validation, (
            "fixture assumption changed: date_of_entry_us's nested "
            "validation block now carries its own length constraint, which "
            "would mask the top-level-only code path this test targets -- "
            "pick a different real field or adjust"
        )
    max_length = field.get("max_length")
    assert isinstance(max_length, int) and max_length > 0, (
        "fixture assumption changed: date_of_entry_us no longer carries a "
        "top-level max_length"
    )

    too_long_value = "X" * (max_length + 5)
    errors = validate_field_value(field, too_long_value)

    assert any(e.constraint == "maxLength" for e in errors), (
        "a value exceeding the real w7 kit's top-level snake_case max_length "
        "was NOT rejected -- the top-level fallback in _resolve_constraint "
        "must try both maxLength and max_length"
    )


def test_top_level_snake_case_max_length_still_allows_a_conforming_value():
    """The fix must not become overzealous -- a value within the real
    constraint stays valid."""
    field = _load_w7_field("date_of_entry_us")
    max_length = field["max_length"]

    errors = validate_field_value(field, "X" * max_length)

    assert not any(e.constraint == "maxLength" for e in errors)


@pytest.mark.parametrize(
    "field,value,should_error",
    [
        # Top-level snake_case min_length, no validation block.
        ({"id": "a", "type": "text", "min_length": 5}, "abc", True),
        ({"id": "a", "type": "text", "min_length": 5}, "abcde", False),
        # Top-level camelCase still works (pre-existing behavior, not broken
        # by widening the fallback to try both).
        ({"id": "a", "type": "text", "maxLength": 3}, "abcd", True),
        ({"id": "a", "type": "text", "maxLength": 3}, "abc", False),
        # Nested validation.snake_case still takes priority over a top-level
        # key when both are present (canonical location wins).
        (
            {
                "id": "a",
                "type": "text",
                "validation": {"max_length": 2},
                "max_length": 100,
            },
            "abc",
            True,
        ),
    ],
)
def test_snake_case_and_camel_case_top_level_constraints_both_resolve(
    field, value, should_error
):
    errors = validate_field_value(field, value)
    has_length_error = any(
        e.constraint in ("maxLength", "minLength") for e in errors
    )
    assert has_length_error is should_error
