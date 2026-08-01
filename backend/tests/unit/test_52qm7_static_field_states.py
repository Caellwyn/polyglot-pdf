"""bd polyglot-pdf-52qm.7 -- unconditioned hidden / read_only / _ignored_fields
must stay invisible and untouchable on every backend surface.

Maintainer directive 2026-08-01. W-7 is the first shipped kit that exercises all
three states: 7 Acceptance-Agent fields carry hidden:true + read_only:true with NO
show_if (so they are statically invisible, not conditionally hidden), and one
_ignored_fields entry parks a field that still owns a real PDF widget.

These are CHARACTERIZATION tests: several assert the CURRENT (defective) behavior
so the gap is pinned and visible in CI rather than silently tolerated. Each such
test names the defect and what the fixed assertion becomes. Do not "fix" them by
loosening the assertion -- fix the code and flip the test.
"""
import json
from pathlib import Path

import pytest

from backend.services.field_utils import build_fields_from_schema
from backend.services.manifest_service import get_field_guidance
from backend.services.validation_handler import ValidationHandler

W7_SCHEMA = Path(__file__).resolve().parents[3] / "form-kits" / "w7" / "schema.json"
pytestmark = pytest.mark.skipif(not W7_SCHEMA.exists(), reason="W-7 kit not present")


def _schema():
    return json.loads(W7_SCHEMA.read_text(encoding="utf-8"))


def _hidden_ids(schema):
    return {f["id"] for f in schema["fields"] if f.get("hidden")}


def test_w7_still_has_unconditioned_hidden_read_only_fields():
    """Premise guard: the agent_* block is hidden+read_only with NO condition.

    If a future kit edit adds show_if to these, this suite is testing the wrong
    thing and should be re-pointed at whatever static-hidden fields remain.
    """
    schema = _schema()
    hidden = [f for f in schema["fields"] if f.get("hidden")]
    assert hidden, "expected statically hidden fields in W-7"
    for f in hidden:
        assert f.get("read_only") is True, f"{f['id']} hidden but not read_only"
        assert "show_if" not in f, f"{f['id']} is conditionally hidden, not static"


def test_ignored_field_is_not_in_the_live_field_list():
    """_ignored_fields entries must never be built as real fields."""
    schema = _schema()
    ignored_ids = {
        (e.get("field") or {}).get("id") for e in schema.get("_ignored_fields", [])
    }
    assert ignored_ids, "expected at least one ignored entry in W-7"
    live_ids = {f.id for f in build_fields_from_schema(schema)}
    assert not (ignored_ids & live_ids)


def test_ignored_field_widget_is_not_claimed_by_a_live_field():
    """The parked field owns a PDF widget no live field maps to.

    Pinned as a FACT, not a bug: it means that widget stays blank on a filled
    PDF. If a future edit points a live field at it, this test flags the change
    for review rather than letting the ignored entry silently come back to life.
    """
    schema = _schema()
    ignored_widgets = {
        (e.get("field") or {}).get("pdf_field_name")
        for e in schema.get("_ignored_fields", [])
    } - {None}
    live_widgets = {f.get("pdf_field_name") for f in schema["fields"]}
    assert ignored_widgets and not (ignored_widgets & live_widgets)


# ---------------------------------------------------------------------------
# Characterization: the three gaps found on 2026-08-01. Each pins CURRENT
# behavior; the docstring states the target assertion once the gap is fixed.
# ---------------------------------------------------------------------------


def test_GAP_hidden_flag_is_dropped_when_fields_are_built():
    """DEFECT: build_fields_from_schema loses hidden/read_only.

    FormField models both flags, but the built object reports False for a field
    the schema marks true -- so no downstream consumer can honor them.
    WHEN FIXED: assert built.hidden is True and built.read_only is True.
    """
    schema = _schema()
    built = {f.id: f for f in build_fields_from_schema(schema)}
    sample = sorted(_hidden_ids(schema))[0]
    assert built[sample].hidden is False, "gap closed -- flip this test"
    assert built[sample].read_only is False, "gap closed -- flip this test"


def test_GAP_read_only_hidden_field_accepts_a_voice_write():
    """DEFECT: a hidden + read_only field is writable via update_form_fields.

    There is no read-only guard in validation, so a model that targets an
    Acceptance-Agent field fills it. (A format-invalid value is rejected for
    UNRELATED type reasons -- use a format-valid one to see the real behavior.)
    WHEN FIXED: assert applied_fields == [] and the response names a read-only
    rejection reason the model can recover from.
    """
    schema = _schema()
    built = build_fields_from_schema(schema)
    target = "agent_name_and_title"
    assert target in _hidden_ids(schema)
    pool = [f for f in built if f.id == target]

    result = ValidationHandler(session_id="t").validate_field_updates(
        pool, {target: "Jane Doe CAA"}, strict_ids=True
    )

    assert result["applied_fields"] == [target], "gap closed -- flip this test"
    assert result["validation_errors"] == []


def test_GAP_hidden_field_still_produces_model_facing_guidance():
    """DEFECT: get_field_guidance builds a full block for a hidden field.

    Nothing in the guidance path filters hidden/read_only, so if a hidden field
    ever becomes the current field it is described to the model -- spoken name,
    instructions and all -- and spends SI tokens on a field the user cannot see.
    WHEN FIXED: assert get_field_guidance returns None (or is never reachable)
    for a statically hidden field.
    """
    schema = _schema()
    hidden = next(f for f in schema["fields"] if f["id"] in _hidden_ids(schema))

    guidance = get_field_guidance(hidden)

    assert guidance is not None, "gap closed -- flip this test"
    assert guidance["field_id"] == hidden["id"]
