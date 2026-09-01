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
_I90_KIT = _REPO / "form-kits" / "i-90"

needs_w7 = pytest.mark.skipif(
    not (_W7_KIT / "form.pdf").exists(), reason="w7 kit not present"
)
# i-90 dropped from eval_extraction's own benchmark manifest (bd
# polyglot-pdf-hydb0, kit deprecated), so its P2_checkbox3 pin below reads the
# schema directly instead of going through ev._FORMS.
needs_i90 = pytest.mark.skipif(
    not (_I90_KIT / "schema.json").exists(),
    reason="form-kits/i-90/schema.json not present (kit deprecated, bd "
           "polyglot-pdf-hydb0)",
)


def _gold_relationship_totals():
    """Count show_if/require_if and logic keys straight from the SHIPPED w7 gold.

    These totals are ground truth that MOVES whenever the hand-verified schema is
    corrected -- they went 12+9=21 -> 19+16=35 across the gold landing (PR #519)
    and the delegate-gate fix. Hardcoding them means every gold correction reds
    the suite and tempts a blind literal-bump, so derive instead (bd
    polyglot-pdf-lzyi). Mirrors eval_extraction's counting: one per FIELD
    carrying the key, not per condition atom.
    """
    schema = json.loads((_W7_KIT / "schema.json").read_text(encoding="utf-8"))
    fields = schema["fields"]
    show_require = (sum(1 for f in fields if f.get("show_if"))
                    + sum(1 for f in fields if f.get("require_if")))
    logic = sum(1 for f in fields
                if f.get("conditional_logic") or f.get("conditional_behavior"))
    return show_require, logic


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


def test_coverage_fails_on_field_level_claims_with_unmapped_options():
    # The Opus-fallback round-1 bypass shape (PR #304): each box claimed via
    # a field-level pdf_field_name (identity preserved) while the options
    # carry NO widget mapping -- the interactive path stores option values
    # the filler cannot map to a widget, so the shape is broken even though
    # every widget is claimed exactly once.
    schema = {"fields": [
        {"id": "r2", "type": "checkbox", "pdf_field_name": "c1_2[0]",
         "options": [{"value": "1", "pdf_field_name": None}]},
        {"id": "r3", "type": "checkbox", "pdf_field_name": "c1_3[0]",
         "options": [{"value": "1", "pdf_field_name": None}]},
    ]}
    r = ev.check_widget_coverage(schema, _LEAVES)
    assert not r["passed"]
    assert any("unmapped options" in p for p in r["problems"])


def test_coverage_fails_on_within_field_value_collapse():
    # One field, two claiming options sharing a value: the filler selects by
    # option value WITHIN a field, so the two boxes are indistinguishable.
    schema = {"fields": [{
        "id": "reason", "type": "checkbox_group",
        "options": [
            {"value": "same", "pdf_field_name": "c1_2[0]"},
            {"value": "same", "pdf_field_name": "c1_3[0]"},
        ],
    }]}
    r = ev.check_widget_coverage(schema, _LEAVES)
    assert not r["passed"]
    assert any("not distinct within the field" in p for p in r["problems"])


def test_coverage_allows_shared_values_across_fields():
    # bd kak8 (Opus-fallback round 2): values may legitimately repeat ACROSS
    # fields -- radio kids / standalone bools sharing on-value "1" are each
    # uniquely addressable via their own field. Not a collapse.
    schema = {"fields": [
        {"id": "r2", "type": "checkbox",
         "options": [{"value": "1", "pdf_field_name": "c1_2[0]"}]},
        {"id": "r3", "type": "checkbox",
         "options": [{"value": "1", "pdf_field_name": "c1_3[0]"}]},
    ]}
    r = ev.check_widget_coverage(schema, _LEAVES)
    assert r["passed"], r["problems"]


def test_coverage_ignores_unrelated_mapped_options_on_field_claimants():
    # bd kak8: a field-level claimant's UNRELATED but PDF-mapped options must
    # not collide with another field's (the round-2 global-pool false
    # positive).
    schema = {"fields": [
        {"id": "r2", "type": "checkbox", "pdf_field_name": "c1_2[0]",
         "options": [{"value": "other", "pdf_field_name": "zz[0]"}]},
        {"id": "r3", "type": "checkbox", "pdf_field_name": "c1_3[0]",
         "options": [{"value": "other", "pdf_field_name": "yy[0]"}]},
    ]}
    r = ev.check_widget_coverage(schema, _LEAVES)
    assert r["passed"], r["problems"]


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
    # do_repair=False: this pins the PRE-repair defect profile (the P2.2 exit
    # criterion); the post-repair outcome is pinned separately below and in
    # tests/test_schema_repair.py (bd h76m.13).
    form = next(f for f in ev._FORMS if f["name"] == "w7")
    row = ev.evaluate_form(form, str(_BROKEN_DRAFT), extract=False, model="-",
                           do_repair=False)
    assert row["verdict"] == "RED"
    # The two columns the exit criterion names:
    assert row["lint_errors"] > 0
    assert row["value_convention"]["pct"] < 100.0
    # And the structural anchor catches the identity collapse too.
    assert row["structural"]["passed"] is False


@needs_w7
def test_broken_w7_draft_repairs_clean_in_the_default_pipeline():
    # bd h76m.13 (P5.2): with the repair step active (the default), the same
    # broken draft comes out lint-ERROR-free -- the extract -> repair -> lint
    # pipeline working end to end inside the harness.
    form = next(f for f in ev._FORMS if f["name"] == "w7")
    row = ev.evaluate_form(form, str(_BROKEN_DRAFT), extract=False, model="-")
    assert row["lint_errors"] == 0
    assert row["repair"] != "-"  # the repair step actually ran


# --------------------------------------------------------------------------- #
# A RepairError scores the draft RED -- it never crashes the sweep (bd ah76)
# --------------------------------------------------------------------------- #

def _no_name_pdf_draft() -> dict:
    """The defect _check_no_name_non_choice (bd l1a9) raises on, DUMP-LESS: a
    source=pdf text field carrying no pdf_field_name at all. `text` is outside
    FIELD_LEVEL_NAME_EXEMPT_TYPES, so its widget identity must live on the
    field itself."""
    return {
        "source": "pdf", "schema_version": "2",
        "fields": [{"id": "fld_phantom", "type": "text", "label": "Phantom"}],
    }


def test_try_repair_records_a_repair_error_instead_of_raising(tmp_path):
    draft = tmp_path / "phantom.json"
    draft.write_text(json.dumps(_no_name_pdf_draft()), encoding="utf-8")
    out, note, harvest = ev._try_repair(str(draft))
    assert note.startswith("FAILED: ")
    # The UNREPAIRED draft is handed back so lint/roundtrip/score still run.
    assert out == str(draft)
    assert harvest == {}


def test_the_repair_ran_guard_still_excludes_a_failed_repair_SOURCE_PIN():
    """SOURCE-TEXT pin, not a behavioural one -- named so no reader mistakes it.

    `repair_ran` gates a post-repair RED exemption; a FAILED repair leaves the
    draft UNREPAIRED, so the exemption must not apply. That guard is not
    behaviourally isolatable on any reachable input: `_try_repair` calls
    `repair()` with NO dump, so only `_check_no_name_non_choice` can raise, and
    that shape always produces a `field-unbacked` lint ERROR which forces RED via
    `lint_errors > 0` regardless of this term. The guard is correct-but-defensive,
    so this asserts the source spelling rather than an observable outcome.

    Consequence to know: an equivalent refactor (`"FAILED:" not in repair_note`)
    will fail this test even though behaviour is unchanged. Update the literal.
    """
    src = pathlib.Path(_SCRIPT).read_text(encoding="utf-8")
    assert 'not repair_note.startswith("FAILED:")' in src


@needs_w7
def test_one_bad_draft_does_not_discard_the_whole_sweep(tmp_path, capsys):
    """The bead's exit criterion: a multi-form sweep containing a draft that
    repair() rejects runs to completion and still reports EVERY row -- rather
    than losing all rows (potentially after paid --extract calls) to one
    uncaught RepairError."""
    draft_dir = tmp_path / "drafts"
    draft_dir.mkdir()
    # Poison exactly one form's draft; the others fall back to their gold.
    (draft_dir / "w7.json").write_text(
        json.dumps(_no_name_pdf_draft()), encoding="utf-8")

    out_json = tmp_path / "rows.json"
    ev.main(["--draft-dir", str(draft_dir), "--json", str(out_json)])
    capsys.readouterr()

    rows = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(rows) == 3  # every benchmark form still reported (i-90 dropped,
                            # bd polyglot-pdf-hydb0 -- kit deprecated)
    w7 = next(r for r in rows if r["form"] == "w7")
    assert w7["repair"].startswith("FAILED: ")
    # Scored RED like any other defective draft -- not skipped, not crashed.
    assert w7["verdict"] == "RED"


@needs_w7
def test_gold_w7_scores_ok_with_structural_pass():
    form = next(f for f in ev._FORMS if f["name"] == "w7")
    row = ev.evaluate_form(form, None, extract=False, model="-")
    assert row["verdict"] == "OK"
    assert row["lint_errors"] == 0
    assert row["structural"]["passed"] is True
    assert row["structural"]["problems"] == []
    # The eight reason boxes (c1_2..c1_9) are ONE consolidated `reason`
    # checkbox_group in the hand-verified gold. This asserted False while they
    # were modeled as eight standalone checkboxes; the gold (PR #519) moved w7 to
    # the same consolidated shape the i-90 entry above calls the v2 target, so
    # True is the CORRECT value, not a loosened one (bd polyglot-pdf-lzyi).
    # coverage stays modeling-agnostic -- `passed` above is what guards a drop.
    assert row["structural"]["consolidated"] is True


# --------------------------------------------------------------------------- #
# Relationship columns + trigger-side harvest accounting (bd polyglot-pdf-eprg)
# --------------------------------------------------------------------------- #

@needs_w7
def test_scored_draft_carries_relationship_summaries():
    """A scored (non-baseline) row must summarize the sprint-15 headline
    relationship metrics: sh/rq (show_if + require_if, combined) and logic
    (conditional_logic + conditional_behavior).

    Totals come from the GOLD, so they move whenever the hand-verified schema is
    corrected -- 21 (12+9) before PR #519, 35 (19+16) after it and the
    delegate-gate fix. Derived from the shipped schema rather than hardcoded, so
    a future correction does not red this test (bd polyglot-pdf-lzyi). What is
    pinned is the CONTRACT: the tool's total equals the gold's own count, and
    recovered never exceeds it.
    """
    expected_sr, expected_logic = _gold_relationship_totals()
    assert expected_sr > 0, "gold carries no show_if/require_if -- check the kit"

    form = next(f for f in ev._FORMS if f["name"] == "w7")
    row = ev.evaluate_form(form, str(_BROKEN_DRAFT), extract=False, model="-")
    assert row["rel_show_require"]["total"] == expected_sr
    assert 0 <= row["rel_show_require"]["recovered"] <= expected_sr
    assert row["rel_logic"]["total"] == expected_logic == 0
    assert row["rel_logic"]["pct"] is None  # nothing to recover -> n/a, not 0%


def test_harvest_counts_bucket_the_mirror_actions():
    """_harvest_counts maps the repair report's controls_fields action names
    into mirrored vs unconverted -- the zero-silent-drops accounting."""
    repairs = [
        {"action": "mirror-controls-fields"},
        {"action": "mirror-controls-fields"},
        {"action": "controls-fields-unmirrored"},
        {"action": "controls-fields-dangling"},
        {"action": "drop-conditional-fields"},
        {"action": "alias-operator"},  # unrelated repair: counted in neither
    ]
    h = ev._harvest_counts(repairs)
    assert h == {"mirrored": 2, "unconverted": 3}


def test_table_renders_relationship_columns_and_harvest_note():
    rows = [{
        "form": "x", "verdict": "OK", "lint_errors": 0, "lint_warnings": 0,
        "value_convention": {"pct": 100.0}, "choice_fill": {"pct": 100.0},
        "text_fill": {"pct": 100.0}, "field_f1": 96.0,
        "rel_show_require": {"recovered": 9, "total": 20, "pct": 45.0},
        "rel_logic": {"recovered": 0, "total": 19, "pct": 0.0},
        "trigger_harvest": {"mirrored": 3, "unconverted": 1},
        "repair": "4 repair(s)",
    }]
    table = ev.render_table(rows)
    assert "sh/rq%" in table and "logic%" in table
    assert "45.0" in table
    assert "[ts 3m/1u]" in table
    # A baseline-style row WITHOUT the new keys still renders ("-" cells:
    # metric absent), and a scored row whose gold has nothing to recover
    # (pct None) renders "n/a" -- the two blank shapes stay distinct.
    rows.append({"form": "y", "verdict": "OK", "lint_errors": 0,
                 "lint_warnings": 0, "value_convention": {"pct": 100.0},
                 "choice_fill": {"pct": 100.0}, "text_fill": {"pct": 100.0},
                 "field_f1": None, "repair": "-"})
    rows.append({"form": "z", "verdict": "OK", "lint_errors": 0,
                 "lint_warnings": 0, "value_convention": {"pct": 100.0},
                 "choice_fill": {"pct": 100.0}, "text_fill": {"pct": 100.0},
                 "field_f1": 96.0,
                 "rel_show_require": {"recovered": 0, "total": 0, "pct": None},
                 "rel_logic": {"recovered": 0, "total": 0, "pct": None},
                 "repair": "-"})
    table2 = ev.render_table(rows)
    assert "n/a" in table2


# --------------------------------------------------------------------------- #
# Exit criterion 2: one command emits the multi-form table.
# --------------------------------------------------------------------------- #

@needs_w7
def test_one_command_emits_the_multi_form_table(capsys, tmp_path):
    # i-90 dropped from the benchmark manifest (bd polyglot-pdf-hydb0, kit
    # deprecated); its P2_checkbox3 pin now lives in
    # test_i90_pins_the_p2_checkbox3_select_one_group below, guarded to skip
    # if form-kits/i-90/ is absent.
    out_json = tmp_path / "rows.json"
    rc = ev.main(["--json", str(out_json)])
    table = capsys.readouterr().out
    # Every benchmark form has a row.
    for name in ("w7", "f1040", "w9-heldout"):
        assert name in table
    # Structural assertion column is rendered.
    assert "PASS (8w" in table
    # The held-out form (no draft, no gold -- by design) is explicit, not silent.
    assert "held-out" in table
    # Post the P6.2 flip (bd h76m.16) every shipped kit is migrated to v2 and
    # clean -- the f1040 duplicate-option bug that used to keep the baseline RED
    # is resolved by the migration, so the whole table is GREEN -> exit 0.
    assert "RED" not in table and rc == 0
    rows = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(rows) == 3
    # The two real kits score OK; the held-out row carries no verdict.
    assert all(r.get("verdict", "OK") == "OK" for r in rows)


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


# --------------------------------------------------------------------------- #
# bd ox6y: i-90's select-one group is pinned + measured (the qmxb regression guard)
# --------------------------------------------------------------------------- #

@needs_i90
def test_i90_pins_the_p2_checkbox3_select_one_group():
    # i-90 was dropped from ev._FORMS (bd polyglot-pdf-hydb0, kit deprecated),
    # so this reads the gold schema directly rather than through the manifest.
    widgets = [f"P2_checkbox3[{i}]" for i in range(5)]
    # The shipped gold models it as ONE consolidated field (the 0nxh fix). The
    # coverage check is modeling-agnostic: a DROP/de-identification fails it (the
    # regression qmxb prevents), while a clean split still passes but is flagged
    # consolidated=False. So assert the gold both passes AND is consolidated.
    gold = json.loads((_I90_KIT / "schema.json").read_text(encoding="utf-8"))
    r = ev.check_widget_coverage(gold, widgets)
    assert r["passed"] and r["consolidated"] and r["widgets"] == 5


def test_i90_pin_catches_a_dropped_widget_but_allows_a_clean_split():
    """Pin the guard's ACTUAL semantics (modeling-agnostic): a DROP fails the
    check (the qmxb regression); a clean split into standalone checkboxes still
    passes but is flagged consolidated=False."""
    leaves = [f"P2_checkbox3[{i}]" for i in range(5)]
    # DROP: a radio modeling only 1 of the 5 -> the other 4 unclaimed -> FAIL.
    dropped = {"fields": [{"id": "reason", "type": "radio", "options": [
        {"value": "v0", "pdf_field_name": "top.P2_checkbox3[0]"}]}]}
    assert not ev.check_widget_coverage(dropped, leaves)["passed"]
    # SPLIT: 5 standalone checkboxes each claiming one widget -> passes, but NOT
    # consolidated (the row surfaces that it was not recognized as one field).
    split = {"fields": [
        {"id": f"r{i}", "type": "checkbox", "pdf_field_name": f"top.P2_checkbox3[{i}]",
         "options": [{"value": f"P2_checkbox3[{i}]",
                      "pdf_field_name": f"top.P2_checkbox3[{i}]"}]}
        for i in range(5)]}
    rs = ev.check_widget_coverage(split, leaves)
    assert rs["passed"] and not rs["consolidated"]
