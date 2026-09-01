"""Regression test for the STRING "true"/"false" on a standalone checkbox
in /fill-pdf (bd polyglot-pdf-oz558).

The fill route's checkbox branch only handled a real `bool` for a
standalone checkbox; a STRING "true"/"false" (the exact-lowercase literal
boolean-intent forms config.py documents for the voice tool contract,
already treated as checked/unchecked case-insensitively by
validation.ts's boolean-intent carve-out) matched neither the comma-split
branch (explicitly excluded, since it is not an option selection) nor the
`isinstance(value, bool)` fill branch, so it fell to
`checkbox_unsupported_value` and was SKIPPED. A value that validated and
stored printed BLANK on the PDF.

Drives the REAL /fill-pdf route against the on-disk F1040 kit (same
harness as test_pdf_fill_checkbox_group_comma.py) and verifies the
widget's /AS on-state -- the round-trip the bead's exit criterion names.

ASCII only.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from backend.routes.pdf_fill_routes import PDFFillRequest, fill_pdf

_KIT_ROOT = Path(__file__).resolve().parents[2] / "form-kits" / "f1040"

# A standalone (no-options) checkbox field on the shipped F1040 kit.
_CHECKBOX_FIELD_ID = "fld_filed_301"
_CHECKBOX_LEAF = "c1_1[0]"

# An options-bearing checkbox_group on the shipped W-7 kit, used to pin that
# the boolean-intent coercion this bead adds does NOT apply to a group field
# (it must stay excluded, same as the pre-existing comma-split guard).
_W7_KIT_ROOT = Path(__file__).resolve().parents[2] / "form-kits" / "w7"
_W7_GROUP_FIELD_ID = "reason"
_W7_GROUP_LEAVES = ["c1_2[0]", "c1_3[0]", "c1_4[0]", "c1_5[0]", "c1_6[0]", "c1_7[0]"]

pytestmark = pytest.mark.skipif(
    not (_KIT_ROOT / "form.pdf").exists(), reason="f1040 kit not present"
)


def _load_gold_schema() -> dict:
    return json.loads((_KIT_ROOT / "schema.json").read_text(encoding="utf-8"))


def _load_w7_schema() -> dict:
    return json.loads((_W7_KIT_ROOT / "schema.json").read_text(encoding="utf-8"))


def _as_state_for_leaf(pdf_bytes: bytes, leaf: str) -> str | None:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for pno in range(doc.page_count):
            for w in doc[pno].widgets() or []:
                w_leaf = (w.field_name or "").split(".")[-1]
                if w_leaf == leaf:
                    as_key = doc.xref_get_key(w.xref, "AS")
                    return as_key[1] if isinstance(as_key, (list, tuple)) and len(as_key) > 1 else None
    finally:
        doc.close()
    return None


def _fill_checkbox(value) -> bytes:
    req = PDFFillRequest(
        kit_id="f1040",
        pdf_filename="form.pdf",
        field_values={_CHECKBOX_FIELD_ID: value},
        form_schema=_load_gold_schema(),
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200
    return resp.body


def test_boolean_string_true_ticks_the_box():
    """Exit criterion 1: the STRING "true" -- not the bool True -- must tick
    the box on the printed PDF, matching every frontend reader's own
    interpretation of the same value."""
    pdf = _fill_checkbox("true")
    state = _as_state_for_leaf(pdf, _CHECKBOX_LEAF)
    assert state not in ("/Off", "Off", None), (
        f"{_CHECKBOX_LEAF} did not fill from the string \"true\" -- "
        "regression of bd polyglot-pdf-oz558"
    )


def test_boolean_string_false_leaves_the_box_unticked():
    """Exit criterion 1's other half: "false" must not tick it."""
    pdf = _fill_checkbox("false")
    state = _as_state_for_leaf(pdf, _CHECKBOX_LEAF)
    assert state in ("/Off", "Off"), (
        f"{_CHECKBOX_LEAF} should not be selected from the string \"false\""
    )


def test_boolean_string_is_case_insensitive():
    """config.py's documented literal forms are lowercase, but the guard
    should not be brittle to an AI-applied "True"/"FALSE"."""
    pdf = _fill_checkbox("True")
    state = _as_state_for_leaf(pdf, _CHECKBOX_LEAF)
    assert state not in ("/Off", "Off", None)


def test_real_boolean_true_still_fills():
    """The pre-existing, already-working path must not regress."""
    pdf = _fill_checkbox(True)
    state = _as_state_for_leaf(pdf, _CHECKBOX_LEAF)
    assert state not in ("/Off", "Off", None)


def test_real_boolean_false_still_leaves_unticked():
    pdf = _fill_checkbox(False)
    state = _as_state_for_leaf(pdf, _CHECKBOX_LEAF)
    assert state in ("/Off", "Off")


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "form-kits" / "w7" / "form.pdf").exists(),
    reason="w7 kit not present",
)
def test_boolean_intent_string_is_not_coerced_on_an_options_bearing_group(monkeypatch):
    """The new coercion this bead adds is scoped to STANDALONE checkboxes
    only -- an options-bearing checkbox_group's "true" is not a real option
    value either way, and must NOT be silently coerced to a bool and ticked
    onto every widget in the group.

    Asserts on the DIAGNOSTIC, not just "nothing got ticked": a group field
    has no top-level pdf_field_name, so if the string WERE wrongly coerced
    to a bool, the isinstance(value, bool) branch would still fail closed
    (checkbox_no_pdf_mapping) and produce the SAME "nothing ticked" outcome
    as the correct behavior -- a widget-state-only assertion would pass
    under either the correct code or the regression, pinning nothing (first
    version of this test, caught during its own mutation-verification: a
    reviewer's mutation dropping the options-exclusion guard left this test
    green). The two paths differ only in WHICH warning fires:
    checkbox_unsupported_value (correct: the string was never coerced) vs.
    checkbox_no_pdf_mapping (regressed: the string WAS wrongly coerced, then
    failed for the unrelated reason of having no field-level mapping).

    Monkeypatches the MODULE's _log directly (test_kit_guarded_delete.py's
    documented pattern) rather than structlog.testing.capture_logs(): _log
    is bound at import time (`structlog.get_logger().bind(...)`) with
    cache_logger_on_first_use=True (backend/utils/logging.py), so
    capture_logs()'s reconfiguration never reaches an already-cached
    logger -- this passed standalone but failed under the full suite
    (caught by the full backend run, not by this file alone)."""
    import backend.routes.pdf_fill_routes as pfr

    names: list[str] = []

    class _Spy:
        def _record(self, event, **kw):
            names.append(event)
        info = warning = error = debug = _record

    monkeypatch.setattr(pfr, "_log", _Spy())

    req = PDFFillRequest(
        kit_id="w7",
        pdf_filename="form.pdf",
        field_values={_W7_GROUP_FIELD_ID: "true"},
        form_schema=_load_w7_schema(),
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200

    assert "checkbox_unsupported_value" in names, (
        f"expected the accurate checkbox_unsupported_value diagnostic, "
        f"got events={names} -- if checkbox_no_pdf_mapping fired instead, "
        "the boolean-intent string was wrongly coerced before reaching the "
        "(unrelated) missing-mapping check, meaning the options-bearing "
        "exclusion guard regressed"
    )
    assert "checkbox_no_pdf_mapping" not in names, names

    doc = fitz.open(stream=resp.body, filetype="pdf")
    try:
        states: dict[str, str | None] = {}
        for pno in range(doc.page_count):
            for w in doc[pno].widgets() or []:
                leaf = (w.field_name or "").split(".")[-1]
                if leaf in _W7_GROUP_LEAVES:
                    as_key = doc.xref_get_key(w.xref, "AS")
                    states[leaf] = as_key[1] if isinstance(as_key, (list, tuple)) and len(as_key) > 1 else None
    finally:
        doc.close()

    for leaf in _W7_GROUP_LEAVES:
        assert states.get(leaf) in ("/Off", "Off", None), (
            f"{leaf} was ticked by a bare \"true\" on the options-bearing "
            "group field -- the boolean-intent coercion must not apply here"
        )
