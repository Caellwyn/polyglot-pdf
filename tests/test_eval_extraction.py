"""Tests for scripts/authoring/eval_extraction.py (bd polyglot-pdf-h76m.6, P2.2).

Pins the bead's exit criteria without any LLM call (the --extract path is the
manual, paid mode; everything here evaluates on-disk schemas):

1. The archived broken W-7 draft scores RED on the convention/lint columns.
2. One command emits the multi-form table including the structural assertions.
3. (The held-out form's flat-model fit is a selection-time note --
   form-kits/w9-heldout/NOTE.md -- whose presence is asserted here.)

Imports eval_extraction by file path (repo precedent: test_extract_form_*).
ASCII only.
"""

import importlib.util
import json
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "authoring" / "eval_extraction.py"
spec = importlib.util.spec_from_file_location("eval_extraction", _SCRIPT)
ev = importlib.util.module_from_spec(spec)
sys.modules["eval_extraction"] = ev
spec.loader.exec_module(ev)

_BROKEN_DRAFT = _REPO / "backend" / "tests" / "fixtures" / "w7_broken_draft.json"
_W7_KIT = _REPO / "form-kits" / "w7"

needs_w7 = pytest.mark.skipif(
    not (_W7_KIT / "form.pdf").exists(), reason="w7 kit not present"
)


# --------------------------------------------------------------------------- #
# check_widget_coverage (the structural assertion, modeling-agnostic)
# --------------------------------------------------------------------------- #

_LEAVES = ["c1_2[0]", "c1_3[0]"]


def test_coverage_passes_on_consolidated_group():
    schema = {"fields": [{
        "id": "reason", "type": "checkbox_group",
        "options": [
            {"value": "slug_a", "pdf_field_name": "top.c1_2[0]"},
            {"value": "slug_b", "pdf_field_name": "top.c1_3[0]"},
        ],
    }]}
    r = ev.check_widget_coverage(schema, _LEAVES)
    assert r["passed"] and r["consolidated"]


def test_coverage_passes_on_split_standalone_modeling():
    # Today's w7 gold shape: one one-option checkbox per box.
    schema = {"fields": [
        {"id": "reason_a", "type": "checkbox", "pdf_field_name": "c1_2[0]",
         "options": [{"value": "c1_2[0]", "pdf_field_name": "c1_2[0]"}]},
        {"id": "reason_b", "type": "checkbox", "pdf_field_name": "c1_3[0]",
         "options": [{"value": "c1_3[0]", "pdf_field_name": "c1_3[0]"}]},
    ]}
    r = ev.check_widget_coverage(schema, _LEAVES)
    assert r["passed"] and not r["consolidated"]


def test_coverage_fails_when_a_box_is_dropped():
    schema = {"fields": [{
        "id": "reason", "type": "checkbox_group",
        "options": [{"value": "slug_a", "pdf_field_name": "c1_2[0]"}],
    }]}
    r = ev.check_widget_coverage(schema, _LEAVES)
    assert not r["passed"]
    assert any("c1_3[0]" in p for p in r["problems"])


def test_coverage_fails_on_identity_collapse():
    # The live W-7 failure shape: options with NO widget mapping and one
    # shared value -- boxes unclaimed AND values indistinct.
    schema = {"fields": [{
        "id": "reason", "type": "checkbox",
        "options": [{"value": "1", "pdf_field_name": None},
                    {"value": "1", "pdf_field_name": None}],
    }]}
    r = ev.check_widget_coverage(schema, _LEAVES)
    assert not r["passed"]


def test_coverage_fails_on_double_claim():
    schema = {"fields": [
        {"id": "a", "type": "checkbox",
         "options": [{"value": "x", "pdf_field_name": "c1_2[0]"}]},
        {"id": "b", "type": "checkbox",
         "options": [{"value": "y", "pdf_field_name": "c1_2[0]"},
                     {"value": "z", "pdf_field_name": "c1_3[0]"}]},
    ]}
    r = ev.check_widget_coverage(schema, _LEAVES)
    assert not r["passed"]
    assert any("claimed 2 times" in p for p in r["problems"])


# --------------------------------------------------------------------------- #
# Exit criterion 1: the archived broken W-7 draft scores RED.
# --------------------------------------------------------------------------- #

@needs_w7
def test_broken_w7_draft_scores_red_on_convention_and_lint():
    form = next(f for f in ev._FORMS if f["name"] == "w7")
    row = ev.evaluate_form(form, str(_BROKEN_DRAFT), extract=False, model="-")
    assert row["verdict"] == "RED"
    # The two columns the exit criterion names:
    assert row["lint_errors"] > 0
    assert row["value_convention"]["pct"] < 100.0
    # And the structural anchor catches the identity collapse too.
    assert row["structural"]["passed"] is False


@needs_w7
def test_gold_w7_scores_ok_with_structural_pass():
    form = next(f for f in ev._FORMS if f["name"] == "w7")
    row = ev.evaluate_form(form, None, extract=False, model="-")
    assert row["verdict"] == "OK"
    assert row["lint_errors"] == 0
    assert row["structural"]["passed"] is True
    assert row["structural"]["consolidated"] is False  # today's split modeling


# --------------------------------------------------------------------------- #
# Exit criterion 2: one command emits the multi-form table.
# --------------------------------------------------------------------------- #

@needs_w7
def test_one_command_emits_the_multi_form_table(capsys, tmp_path):
    out_json = tmp_path / "rows.json"
    rc = ev.main(["--json", str(out_json)])
    table = capsys.readouterr().out
    # Every benchmark form has a row.
    for name in ("w7", "w7-2", "f1040", "w9-heldout"):
        assert name in table
    # Structural assertion column is rendered.
    assert "PASS (8w" in table
    # The held-out form (no draft, no gold -- by design) is explicit, not silent.
    assert "held-out" in table
    # f1040's shipped duplicate bug keeps the baseline table RED -> exit 1.
    assert "RED" in table and rc == 1
    rows = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(rows) == 4


# --------------------------------------------------------------------------- #
# Exit criterion 3: the held-out form is committed with its fit note.
# --------------------------------------------------------------------------- #

def test_held_out_form_and_note_are_committed():
    kit = _REPO / "form-kits" / "w9-heldout"
    assert (kit / "form.pdf").exists()
    note = (kit / "NOTE.md").read_text(encoding="utf-8")
    assert "HELD OUT" in note
    assert "flat" in note.lower()  # the flat-model fit analysis
    # The fit check's ONE documented exception (line 3b's nested condition,
    # fresh-eyes round 1) must stay disclosed -- a note claiming total
    # flatness would be factually wrong against the form's own instructions.
    assert "all_of(llc" in note
    # No schema may ever ship for it (tuning against it defeats the purpose).
    assert not (kit / "schema.json").exists()


def test_held_out_note_widget_claims_match_the_real_pdf():
    """Anchor the NOTE's widget claims to the actual PDF so the analysis can
    never silently drift from the form it describes (fresh-eyes round 1: the
    first draft of the note had the LLC box mis-mapped)."""
    fitz = pytest.importorskip("fitz")
    kit = _REPO / "form-kits" / "w9-heldout"
    note = (kit / "NOTE.md").read_text(encoding="utf-8")

    doc = fitz.open(str(kit / "form.pdf"))
    try:
        checkboxes = {
            (w.field_name or "").split(".")[-1]
            for page in doc for w in (page.widgets() or [])
            if w.field_type_string == "CheckBox"
        }
    finally:
        doc.close()

    expected = {f"c1_1[{i}]" for i in range(7)} | {"c1_2[0]"}
    assert checkboxes == expected  # the form IS what the note says it is
    for leaf in sorted(expected):
        assert leaf in note, f"NOTE.md no longer names {leaf}"
