"""resolve_edition_marker's fallback fingerprint must cover the answerable
CONSTRAINTS of a form, not just its field ids/types/option values
(bd polyglot-pdf-8x56).

bd polyglot-pdf-47r3 shipped the fingerprint hashing only field id + type +
option values. Measured on the shipped W-7 kit, 0 of 53 fields carry a
top-level 'required' key but 27 of 53 carry a 'validation' block -- so over
half the answerable constraints in a real kit were invisible to the marker,
and each of these left the fingerprint byte-identical:
  - changing a field's validation rules (pattern, min/max length, required_if)
  - flipping a field's top-level 'required' flag
  - remapping pdf_field_name (the same answers now print into a DIFFERENT
    PDF widget)

Separately, the option-value list was built with sorted(<generator>), which
PRESERVES duplicates -- a false-positive drift signal for a kit with a
duplicated option value (lower-impact: duplicate option values are already a
lint ERROR).

These tests exercise resolve_edition_marker's FALLBACK branch directly (no
edition_date, no author_version) so the fingerprint is what's under test, not
the higher-priority sources.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

from backend.utils.confirmation_logger import resolve_edition_marker


def _schema(fields: list) -> dict:
    return {"fields": fields}


def _base_field(**overrides) -> dict:
    field = {"id": "f1", "type": "text"}
    field.update(overrides)
    return field


def test_a_changed_validation_rule_changes_the_fingerprint():
    before = _schema([_base_field(validation={"pattern": "^[0-9]{5}$"})])
    after = _schema([_base_field(validation={"pattern": "^[0-9]{9}$"})])

    assert resolve_edition_marker(None, before) != resolve_edition_marker(None, after)


def test_a_flipped_required_flag_changes_the_fingerprint():
    before = _schema([_base_field(required=False)])
    after = _schema([_base_field(required=True)])

    assert resolve_edition_marker(None, before) != resolve_edition_marker(None, after)


def test_a_remapped_pdf_field_name_changes_the_fingerprint():
    """The SAME answers now print into a DIFFERENT PDF widget -- a real
    revision of what document was produced, even though nothing about the
    voice-facing field itself changed."""
    before = _schema([_base_field(pdf_field_name="topmostSubform[0].Page1[0].f1_01[0]")])
    after = _schema([_base_field(pdf_field_name="topmostSubform[0].Page1[0].f1_02[0]")])

    assert resolve_edition_marker(None, before) != resolve_edition_marker(None, after)


def test_an_unchanged_field_still_fingerprints_identically():
    """Sanity check: two structurally-identical schemas (built independently,
    not the same object) still yield the SAME marker -- the point of a
    fingerprint is stability across reconnects, not just sensitivity to
    change (mirrors test_edition_marker_is_stable_across_a_reconnect)."""
    a = _schema([_base_field(
        validation={"required": True, "min_length": 3}, required=False,
        pdf_field_name="f1_01[0]",
        options=[{"value": "x", "label": "X"}, {"value": "y", "label": "Y"}],
    )])
    b = _schema([_base_field(
        validation={"required": True, "min_length": 3}, required=False,
        pdf_field_name="f1_01[0]",
        options=[{"value": "x", "label": "X"}, {"value": "y", "label": "Y"}],
    )])

    assert resolve_edition_marker(None, a) == resolve_edition_marker(None, b)


def test_a_duplicated_option_value_does_not_fingerprint_differently_from_deduped():
    """bd polyglot-pdf-8x56 (minor): sorted(<generator>) preserved duplicates,
    so a kit with a duplicated option value fingerprinted differently from
    the de-duplicated equivalent -- a false-positive drift signal for a defect
    that is ALREADY a separate lint ERROR, not a genuine form revision."""
    deduped = _schema([_base_field(
        options=[{"value": "x", "label": "X"}, {"value": "y", "label": "Y"}],
    )])
    duplicated = _schema([_base_field(
        options=[
            {"value": "x", "label": "X"},
            {"value": "x", "label": "X (dup)"},
            {"value": "y", "label": "Y"},
        ],
    )])

    assert resolve_edition_marker(None, deduped) == resolve_edition_marker(None, duplicated)


def test_validation_key_order_does_not_change_the_fingerprint():
    """The validation dict's own key order must not matter -- only its
    content. json.dumps(sort_keys=True) makes the shape canonical."""
    a = _schema([_base_field(validation={"pattern": "^[0-9]+$", "required": True})])
    b = _schema([_base_field(validation={"required": True, "pattern": "^[0-9]+$"})])

    assert resolve_edition_marker(None, a) == resolve_edition_marker(None, b)


def test_still_returns_none_for_a_schema_with_no_usable_fields():
    """No regression to the existing empty/malformed-schema fallback path."""
    assert resolve_edition_marker(None, {"fields": []}) is None
    assert resolve_edition_marker(None, {}) is None
    assert resolve_edition_marker(None, None) is None
