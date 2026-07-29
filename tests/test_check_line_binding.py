"""Tests for scripts/authoring/check_line_binding.py (bd polyglot-pdf-3ave).

The oracle detects the off-by-N field->widget assignment class that no existing
gate can see (three shipped instances: bd 13vo i-90, bd ivh9 w7, bd 3ave f1040).
It grades a draft against the PDF's own printed line markers -- no gold schema
and no model in the loop.

Pins, in order: the real f1040 corruption is caught, the fresh extraction's
residual shift is caught, a correct binding is silent, the gutter-column rule
that kills body-text false positives holds, and abstention is honest (a form it
cannot verify reports so rather than passing).

Imports by file path (repo precedent: test_eval_extraction).
ASCII only.
"""

import importlib.util
import json
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "authoring" / "check_line_binding.py"
spec = importlib.util.spec_from_file_location("check_line_binding", _SCRIPT)
clb = importlib.util.module_from_spec(spec)
sys.modules["check_line_binding"] = clb
spec.loader.exec_module(clb)

_F1040_PDF = _REPO / "form-kits" / "f1040" / "form.pdf"
_F1040_SCHEMA = _REPO / "form-kits" / "f1040" / "schema.json"

needs_f1040 = pytest.mark.skipif(
    not _F1040_PDF.exists(), reason="f1040 kit not present")

pytest.importorskip("fitz", reason="PyMuPDF required for the geometry oracle")


# --------------------------------------------------------------------------- #
# Unit: the line number a field claims to be
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("field,expected", [
    ({"id": "fld_1a"}, "1a"),
    ({"id": "line_11a"}, "11a"),
    ({"id": "line_9"}, "9"),
    ({"id": "whatever", "name": "2b Taxable interest"}, "2b"),
    ({"id": "whatever", "name": "Line 16 Other"}, "16"),
    # No stated line -> not judged at all (the conservative contract).
    ({"id": "mailing_street"}, None),
    ({"id": "p1_extra_75"}, None),
    # A year/form number in a label must not be read as a line marker.
    ({"id": "x", "name": "Form 1099-R distributions"}, None),
])
def test_stated_line_parsing(field, expected):
    assert clb._stated_line(field) == expected


def test_iter_fields_walks_nested_parts_and_sections():
    schema = {"parts": [{"sections": [{"fields": [
        {"id": "a", "pdf_field_name": "w1"},
        {"id": "b", "pdf_field_name": "w2"},
    ]}]}]}
    assert {f["id"] for f in clb._iter_fields(schema)} == {"a", "b"}


# --------------------------------------------------------------------------- #
# The real forms: catches the known corruption, stays quiet on correct bindings
# --------------------------------------------------------------------------- #

@needs_f1040
def test_catches_the_shipped_f1040_line_shift():
    """The shipped kit's page-1 income block is shifted (bd 3ave). Every finding
    must name a field whose claimed widget is printed on a DIFFERENT line."""
    schema = json.loads(_F1040_SCHEMA.read_text(encoding="utf-8"))
    result = clb.check(schema, str(_F1040_PDF))
    found = {f["field_id"] for f in result["findings"]}
    # Spot-pin the hand-verified worst cases (see bd 3ave):
    #   fld_9 (total income) sits on the printed line 6a box.
    assert "fld_9" in found
    assert "fld_11a" in found
    by_id = {f["field_id"]: f for f in result["findings"]}
    assert by_id["fld_9"]["widget_is_on_line"] == "6a"
    assert by_id["fld_10"]["widget_is_on_line"] == "6b"
    # It is a real detection, not a blanket failure: most fields are fine.
    assert 0 < len(result["findings"]) < result["checked"]


@needs_f1040
def test_a_correct_binding_produces_no_finding():
    """Rebinding a field to the widget printed on its OWN line clears it --
    the oracle keys on the printed marker, not on the field being suspicious."""
    schema = json.loads(_F1040_SCHEMA.read_text(encoding="utf-8"))
    before = {f["field_id"] for f in clb.check(schema, str(_F1040_PDF))["findings"]}
    assert "fld_9" in before

    # f1_73 is the widget printed on line 9 (verified against the PDF).
    def fix(o):
        if isinstance(o, dict):
            if o.get("id") == "fld_9":
                o["pdf_field_name"] = "topmostSubform[0].Page1[0].f1_73[0]"
            for v in o.values():
                fix(v)
        elif isinstance(o, list):
            for v in o:
                fix(v)
    fix(schema)
    after = {f["field_id"] for f in clb.check(schema, str(_F1040_PDF))["findings"]}
    assert "fld_9" not in after


# --------------------------------------------------------------------------- #
# The false-positive regression that shaped the gutter rule
# --------------------------------------------------------------------------- #

@needs_f1040
def test_body_text_numerals_are_not_read_as_line_markers():
    """f1040's line-4c row prints a checkbox legend '1 Rollover 2 QCD 3' whose
    trailing '3' sits ~50pt left of the row's widget. A proximity-only rule read
    that as 'line 3' and reported three bogus mismatches. Only markers in a
    RECURRING gutter column count, so no finding may claim line '3' here."""
    schema = json.loads(_F1040_SCHEMA.read_text(encoding="utf-8"))
    result = clb.check(schema, str(_F1040_PDF))
    assert all(f["widget_is_on_line"] != "3" for f in result["findings"]), \
        "a body-text numeral was mistaken for a printed gutter marker"


def test_collect_markers_requires_a_recurring_column():
    """A lone marker-shaped token is body text, not a gutter."""
    class _Page:
        def __init__(self, words):
            self._w = words

        def get_text(self, _kind):
            return self._w

    # One stray "3" -> no column -> no markers.
    stray = _Page([(0, 100, 422, 110, "3", 0, 0, 0)])
    assert clb.collect_markers(stray) == []

    # Four tokens sharing a right edge -> a real gutter column.
    col = _Page([(0, 100 + 12 * i, 498, 110 + 12 * i, f"{i + 1}a", 0, 0, 0)
                 for i in range(4)])
    assert len(clb.collect_markers(col)) == 4


# --------------------------------------------------------------------------- #
# Honest abstention: silence is never reported as a clean bill of health
# --------------------------------------------------------------------------- #

def test_a_form_with_no_markers_abstains_loudly():
    result = {"findings": [], "checked": 0, "markers": 0}
    text = clb.render(result)
    assert "NOT a clean bill of health" in text


def test_abstention_does_not_lead_with_the_ok_token():
    """A caller grepping for 'OK:' -- or reading only the first line of a
    truncated log -- must not read abstention as a pass. Text twin of the
    exit-code contract (rc 3)."""
    text = clb.render({"findings": [], "checked": 0, "markers": 10})
    assert text.splitlines()[0].startswith("ABSTAINED:")
    assert "OK:" not in text
    # w7 abstains WITH markers present, so the message must not claim the form
    # prints none -- it reports the marker count and the real precondition.
    assert "10 printed marker(s)" in text


def test_an_unreadable_pdf_is_a_usage_error_not_a_traceback(tmp_path, capsys):
    schema = tmp_path / "s.json"
    schema.write_text(json.dumps({"fields": []}), encoding="utf-8")
    rc = clb.main(["--schema", str(schema),
                   "--pdf", str(tmp_path / "does-not-exist.pdf")])
    capsys.readouterr()
    assert rc == 2, "a missing PDF must exit 2, not raise or collide with rc 1"


def test_a_verified_clean_form_says_so():
    result = {"findings": [], "checked": 12, "markers": 30}
    text = clb.render(result)
    assert "OK:" in text and "NOT a clean bill of health" not in text


def test_total_abstention_does_not_exit_zero(tmp_path, capsys, monkeypatch):
    """rc==0 must mean VERIFIED-clean, never 'I checked nothing'. A lint-style
    caller gating on `rc == 0` would otherwise read total abstention as a pass --
    the exact failure mode this tool exists to prevent."""
    monkeypatch.setattr(clb, "check",
                        lambda *a, **k: {"findings": [], "checked": 0,
                                         "markers": 0})
    schema = tmp_path / "s.json"
    schema.write_text(json.dumps({"fields": []}), encoding="utf-8")

    rc = clb.main(["--schema", str(schema), "--pdf", "unused.pdf"])
    capsys.readouterr()
    assert rc == 3, "abstention must be distinguishable from a verified pass"

    rc_ci = clb.main(["--schema", str(schema), "--pdf", "unused.pdf",
                      "--require-verified"])
    capsys.readouterr()
    assert rc_ci == 1, "--require-verified must make abstention a hard failure"


def test_a_verified_clean_run_exits_zero(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(clb, "check",
                        lambda *a, **k: {"findings": [], "checked": 7,
                                         "markers": 20})
    schema = tmp_path / "s.json"
    schema.write_text(json.dumps({"fields": []}), encoding="utf-8")
    rc = clb.main(["--schema", str(schema), "--pdf", "unused.pdf",
                   "--require-verified"])
    capsys.readouterr()
    assert rc == 0


@needs_f1040
def test_exit_code_signals_findings(tmp_path, capsys):
    rc = clb.main(["--schema", str(_F1040_SCHEMA), "--pdf", str(_F1040_PDF),
                   "--json", str(tmp_path / "out.json")])
    capsys.readouterr()
    assert rc == 1  # the shipped kit is known-corrupt
    payload = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert payload["findings"] and payload["checked"] > 0
