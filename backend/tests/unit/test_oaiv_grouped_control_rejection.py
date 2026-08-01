"""Repro + guard for bd polyglot-pdf-oaiv: the W-7 checkbox_group fill rejection.

Live evidence (2026-08-01, gemini-live-2.5-flash-native-audio, W-7 kit): with the
section-1 `reason` checkbox_group active, the model called update_form_fields and
the backend answered success=false / applied_count=0 / unknown_count=1, then fell
back to switch_to_field. The rejected field id was NOT logged, so the live logs
could not say WHICH id the model sent.

These tests pin the two halves of that:

1. The observability fix -- validate_field_updates now records the rejected KEYS
   (schema field ids, never values) on the validation_failures line.
2. The mechanism -- in DTI strict mode an id that is real-but-not-the-current-field
   is rejected as unknown rather than fuzzy-matched. That is the designed behavior
   (it prevents the PR #251 mis-fill trap), and it is what a grouped-control turn
   trips when the model names a sibling id.

The tests read the SHIPPED W-7 schema so they track the real kit, not a mock of it.
"""
import json
from pathlib import Path

import pytest

from backend.services.ai_context import render_field_guidance
from backend.services.field_utils import build_fields_from_schema
from backend.services.validation_handler import ValidationHandler

W7_SCHEMA = Path(__file__).resolve().parents[3] / "form-kits" / "w7" / "schema.json"


def _w7_fields():
    schema = json.loads(W7_SCHEMA.read_text(encoding="utf-8"))
    return schema, build_fields_from_schema(schema)


@pytest.mark.skipif(not W7_SCHEMA.exists(), reason="W-7 kit not present")
def test_w7_has_the_grouped_controls_that_triggered_oaiv():
    """Guard the premise: W-7 section 1 really does open with grouped controls."""
    schema, _ = _w7_fields()
    by_id = {f["id"]: f for f in schema["fields"]}
    assert by_id["application_type"]["type"] == "radio"
    assert by_id["reason"]["type"] == "checkbox_group"
    # Both live in the FIRST section -- so a real user hits them before any text
    # field, which is why this path was never exercised by the i-90 demo.
    first_section = schema["parts"][0]["section_ids"][0]
    assert by_id["application_type"]["section_id"] == first_section
    assert by_id["reason"]["section_id"] == first_section


@pytest.mark.skipif(not W7_SCHEMA.exists(), reason="W-7 kit not present")
def test_strict_mode_rejects_a_sibling_id_as_unknown():
    """The oaiv mechanism, on the real schema.

    In DTI strict mode only an EXACT id match counts. When the current field is
    the checkbox_group but the model names a sibling (a real W-7 id), the update
    is rejected as unknown -- it is not fuzzy-matched onto the active field.
    """
    _, fields = _w7_fields()
    # The DTI validation pool holds the active field only.
    pool = [f for f in fields if f.id == "reason"]
    handler = ValidationHandler(session_id="test-oaiv")

    result = handler.validate_field_updates(
        pool, {"application_type": "a"}, strict_ids=True
    )

    assert result["applied_fields"] == []
    assert result["unknown_fields"] == ["application_type"]


@pytest.mark.skipif(not W7_SCHEMA.exists(), reason="W-7 kit not present")
def test_validation_failures_logs_the_rejected_field_id():
    """The observability fix: the rejected id reaches the log (the value never does).

    Without this, an unknown-field rejection is undiagnosable from logs alone --
    the gap that stalled oaiv's root cause.

    Patches the module logger's .warning directly rather than using
    structlog.testing.capture_logs -- the latter is sensitive to global structlog
    config that other suite tests mutate, so it captures nothing under full-suite
    ordering (same trap already documented in test_callback_handler.py).
    """
    from unittest.mock import patch

    import backend.services.validation_handler as vh

    schema, fields = _w7_fields()
    known = {f["id"] for f in schema["fields"]}
    # Pool holds the active field only; the model names a SIBLING id -> unknown.
    pool = [f for f in fields if f.id == "reason"]
    handler = ValidationHandler(session_id="test-oaiv")

    with patch.object(vh._log, "warning") as warn:
        result = handler.validate_field_updates(
            pool, {"application_type": "SENTINEL_VALUE"}, strict_ids=True,
            is_known_field=lambda k: k in known,
        )

    assert result["unknown_fields"] == ["application_type"]
    warn.assert_called_once()
    event, kwargs = warn.call_args[0][0], warn.call_args[1]
    assert event == "validation_failures"
    assert kwargs["unknown_field_ids"] == ["application_type"]
    # The VALUE must never appear anywhere on the line (no-PII policy).
    assert "SENTINEL_VALUE" not in repr(warn.call_args)


@pytest.mark.skipif(not W7_SCHEMA.exists(), reason="W-7 kit not present")
def test_a_rejected_key_that_is_not_a_schema_id_is_redacted():
    """PII guard: the rejected key is RAW MODEL INPUT, not necessarily an id.

    If the model swaps args, the user's ANSWER lands in the field_id slot -- the
    documented failure mode behind the no-PII scrubs in form_filling_service and
    callback_handler (Codex PR #264 P0). This log line must not reintroduce that
    leak, so a key that is not a real schema id is reduced to a length-only
    shape. Found by fresh-eyes review of the first cut of this logging, which
    echoed the raw key.
    """
    from unittest.mock import patch

    import backend.services.validation_handler as vh

    schema, fields = _w7_fields()
    known = {f["id"] for f in schema["fields"]}
    pool = [f for f in fields if f.id == "reason"]
    handler = ValidationHandler(session_id="test-oaiv")
    leaked = "my SSN is 123-45-6789"

    with patch.object(vh._log, "warning") as warn:
        handler.validate_field_updates(
            pool, {leaked: "x"}, strict_ids=True,
            is_known_field=lambda k: k in known,
        )

    logged = warn.call_args[1]["unknown_field_ids"]
    assert logged == [f"<unrecognized:{len(leaked)} chars>"]
    assert "123-45-6789" not in repr(warn.call_args)


@pytest.mark.skipif(not W7_SCHEMA.exists(), reason="W-7 kit not present")
def test_without_a_known_field_predicate_nothing_is_echoed():
    """Fail SAFE: a caller that passes no predicate leaks nothing.

    The predicate is optional, so the default must be the conservative one --
    otherwise a future call site gets the leak back by omission.
    """
    from unittest.mock import patch

    import backend.services.validation_handler as vh

    _, fields = _w7_fields()
    pool = [f for f in fields if f.id == "reason"]
    handler = ValidationHandler(session_id="test-oaiv")

    with patch.object(vh._log, "warning") as warn:
        handler.validate_field_updates(
            pool, {"application_type": "x"}, strict_ids=True
        )

    assert warn.call_args[1]["unknown_field_ids"] == ["<unrecognized:16 chars>"]


@pytest.mark.skipif(not W7_SCHEMA.exists(), reason="W-7 kit not present")
def test_checkbox_group_accepts_scalar_list_and_csv_option_values():
    """Control: the backend accepts every reasonable multi-select shape.

    This is the load-bearing negative result for oaiv -- grouped-control
    VALIDATION is not the defect. The model must send the option `value`
    (a_treaty_benefit), which is exactly what render_field_guidance tells it to
    send ('"<label>" (use value: <value>)'). So the live rejection came from what
    the model chose to send on that turn, not from a backend gap.
    """
    schema, fields = _w7_fields()
    raw = next(f for f in schema["fields"] if f["id"] == "reason")
    values = [o["value"] for o in raw["options"]]
    pool = [f for f in fields if f.id == "reason"]
    handler = ValidationHandler(session_id="test-oaiv")

    for payload in (values[0], [values[0]], values[:2], ",".join(values[:2])):
        result = handler.validate_field_updates(
            pool, {"reason": payload}, strict_ids=True
        )
        assert "reason" in result["applied_fields"], f"rejected {payload!r}"


@pytest.mark.skipif(not W7_SCHEMA.exists(), reason="W-7 kit not present")
def test_radio_takes_a_scalar_and_rejects_a_list():
    """A radio is single-valued: a list is correctly refused.

    Pinned because it is the one real shape difference between W-7's two grouped
    controls -- a fix that teaches the model "grouped controls take a list" would
    break this field.
    """
    schema, fields = _w7_fields()
    raw = next(f for f in schema["fields"] if f["id"] == "application_type")
    values = [o["value"] for o in raw["options"]]
    pool = [f for f in fields if f.id == "application_type"]
    handler = ValidationHandler(session_id="test-oaiv")

    assert "application_type" in handler.validate_field_updates(
        pool, {"application_type": values[0]}, strict_ids=True
    )["applied_fields"]

    assert handler.validate_field_updates(
        pool, {"application_type": [values[0]]}, strict_ids=True
    )["applied_fields"] == []


@pytest.mark.skipif(not W7_SCHEMA.exists(), reason="W-7 kit not present")
def test_guidance_tells_the_model_the_option_value_to_send():
    """The SI text carries the exact token the validator requires.

    Guards the contract end-to-end: whatever the model is shown for an option
    must be a value the validator then accepts.
    """
    schema, fields = _w7_fields()
    raw = next(f for f in schema["fields"] if f["id"] == "reason")
    rendered = render_field_guidance(raw)
    pool = [f for f in fields if f.id == "reason"]
    handler = ValidationHandler(session_id="test-oaiv")

    for opt in raw["options"]:
        value = opt["value"]
        assert f"use value: {value}" in rendered
        assert "reason" in handler.validate_field_updates(
            pool, {"reason": value}, strict_ids=True
        )["applied_fields"]
