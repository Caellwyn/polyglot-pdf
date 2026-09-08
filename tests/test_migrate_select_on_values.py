"""scripts/migrate_select_on_values.py (bd polyglot-pdf-g2fpr, PR 3a / bead ub7om).

The bead's exit criteria, each pinned directly:
  1. run twice on a copy of a kit shaped like i-90_v2 -> identical output;
     every option's pdf_on_value == its OLD value; a numeric option gains
     ONLY pdf_on_value; metadata.json is untouched.
  2. a show_if / require_if on a select value is retargeted (fields AND
     sections; scalar and list); the report names every change.

ASCII only.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "migrate_select_on_values.py"
PY = sys.executable


def _load():
    spec = importlib.util.spec_from_file_location("migrate_select_on_values", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


mod = _load()
migrate_selects = mod.migrate_selects

# The real 62-entry state table the i-90_v2 dropdowns carry (extract_form's
# _US_STATE_NAMES is the source; a subset is enough to prove the shape).
STATES = [("AL", "Alabama"), ("AK", "Alaska"), ("AA", "Armed Forces Americas"),
          ("DC", "District of Columbia"), ("WY", "Wyoming")]


def _legacy_select(fid, pairs, labels_with_code=True):
    return {
        "id": fid, "type": "select", "pdf_field_name": f"{fid}[0]", "section_id": "s1",
        "options": [
            {"value": code, "label": f"{name} ({code})" if labels_with_code else name}
            for code, name in pairs
        ],
    }


def _kit_like_i90():
    """4 state dropdowns + the two height dropdowns, plus a dependent with
    conditions on one of them at field level and at section level."""
    fields = [_legacy_select(f"state_{i}", STATES) for i in range(4)]
    fields.append({
        "id": "height_feet", "type": "select", "pdf_field_name": "hf[0]", "section_id": "s1",
        "options": [{"value": str(n), "label": str(n)} for n in range(3, 8)],
    })
    fields.append({
        "id": "height_inches", "type": "select", "pdf_field_name": "hi[0]", "section_id": "s1",
        "options": [{"value": str(n), "label": str(n)} for n in range(0, 12)],
    })
    fields.append({
        "id": "dep", "type": "text", "pdf_field_name": "dep[0]", "section_id": "s1",
        "show_if": {"field": "state_0", "operator": "equals", "value": "WY"},
        "require_if": {"all_of": [
            {"field": "state_1", "operator": "in", "value": ["AL", "AK", "ZZ"]},
            {"field": "height_feet", "operator": "equals", "value": "5"},
        ]},
    })
    return {
        "schema_version": "2",
        "form_metadata": {"form_number": "I-90", "version": "1"},
        "fields": fields,
        "sections": [{
            "id": "s1", "label": "S1", "order": 1,
            "fields": [f["id"] for f in fields],
            "show_if": {"field": "state_2", "operator": "not_equals", "value": "DC"},
        }, {
            "id": "s2", "label": "S2", "order": 2, "fields": [],
            "require_if": {"any_of": [{"field": "state_3", "operator": "equals", "value": "AA"}]},
        }],
    }


# ---------------------------------------------------------------------------
# Exit criterion 1: idempotent; pdf_on_value == old value; numeric keeps value
# ---------------------------------------------------------------------------

def test_every_migrated_option_carries_its_OLD_value_as_pdf_on_value():
    kit = _kit_like_i90()
    out, report = migrate_selects(kit)
    for f_old, f_new in zip(kit["fields"], out["fields"]):
        if f_old["type"] != "select":
            continue
        for o_old, o_new in zip(f_old["options"], f_new["options"]):
            assert o_new["pdf_on_value"] == o_old["value"]
            assert o_new["label"] == o_old["label"]
    assert report["options_migrated"] == 4 * len(STATES) + 5 + 12


def test_state_options_mint_the_bare_name_and_the_code_moves():
    out, _ = migrate_selects(_kit_like_i90())
    opts = out["fields"][0]["options"]
    assert [o["value"] for o in opts] == [
        "alabama", "alaska", "armed_forces_americas", "district_of_columbia", "wyoming"]
    assert [o["pdf_on_value"] for o in opts] == [c for c, _ in STATES]


def test_a_numeric_option_gains_ONLY_pdf_on_value():
    kit = _kit_like_i90()
    out, report = migrate_selects(kit)
    hf = next(f for f in out["fields"] if f["id"] == "height_feet")
    assert [o["value"] for o in hf["options"]] == ["3", "4", "5", "6", "7"]
    assert [o["pdf_on_value"] for o in hf["options"]] == ["3", "4", "5", "6", "7"]
    entry = next(e for e in report["fields"] if e["field"] == "height_feet")
    assert entry["kept_as_slug"] == 5 and entry["slug_map"] == {}


def test_running_twice_is_a_no_op():
    once, r1 = migrate_selects(_kit_like_i90())
    twice, r2 = migrate_selects(once)
    assert twice == once
    assert r2["options_migrated"] == 0
    assert r2["conditions_retargeted"] == 0
    assert r2["fields"] == []
    assert r1["options_migrated"] > 0  # non-vacuity


def test_the_input_is_never_mutated():
    kit = _kit_like_i90()
    before = copy.deepcopy(kit)
    migrate_selects(kit)
    assert kit == before


# ---------------------------------------------------------------------------
# Exit criterion 2: conditions retargeted; the report names every change
# ---------------------------------------------------------------------------

def test_conditions_on_a_select_are_retargeted_on_fields_and_sections_scalar_and_list():
    out, report = migrate_selects(_kit_like_i90())
    dep = next(f for f in out["fields"] if f["id"] == "dep")
    assert dep["show_if"]["value"] == "wyoming"
    atoms = dep["require_if"]["all_of"]
    assert atoms[0]["value"] == ["alabama", "alaska", "ZZ"]   # unknown member left alone
    assert atoms[1]["value"] == "5"                            # numeric: unchanged
    s1, s2 = out["sections"]
    assert s1["show_if"]["value"] == "district_of_columbia"
    assert s2["require_if"]["any_of"][0]["value"] == "armed_forces_americas"
    # dep.show_if, dep.require_if list atom, s1.show_if, s2.require_if atom
    assert report["conditions_retargeted"] == 4


def test_the_report_names_every_slug_change_per_field():
    _, report = migrate_selects(_kit_like_i90())
    entry = next(e for e in report["fields"] if e["field"] == "state_0")
    assert entry["migrated"] == len(STATES)
    assert entry["slug_map"] == {
        "AL": "alabama", "AK": "alaska", "AA": "armed_forces_americas",
        "DC": "district_of_columbia", "WY": "wyoming"}
    assert entry["already_v2"] == 0 and entry["duplicate_codes"] == []


# ---------------------------------------------------------------------------
# Edges the reviewers will look for
# ---------------------------------------------------------------------------

def test_an_option_already_in_v2_shape_is_untouched_and_reserves_its_slug():
    kit = {"schema_version": "2", "fields": [{
        "id": "f", "type": "select", "pdf_field_name": "f[0]", "section_id": "s",
        "options": [
            {"value": "alabama", "label": "Alabama", "pdf_on_value": "AL"},   # v2, hand-authored
            {"value": "XX", "label": "Alabama (XX)"},                          # legacy sibling, same name
        ]}], "sections": []}
    out, report = migrate_selects(kit)
    o1, o2 = out["fields"][0]["options"]
    assert o1 == {"value": "alabama", "label": "Alabama", "pdf_on_value": "AL"}
    assert o2["pdf_on_value"] == "XX"
    assert o2["value"] == "alabama_2"           # reserved: cannot collide with the v2 slug
    entry = report["fields"][0]
    assert entry["already_v2"] == 1 and entry["migrated"] == 1


def test_an_EMPTY_pdf_on_value_is_a_CLEARED_v2_code_left_alone_and_reported():
    """Round 3 reversed round 1's contract. Legacy means the key is ABSENT (the
    editor's convert-on-touch rule, PR 2); an empty code is a v2 option whose
    author cleared it. Treating it as legacy fabricated a code from a
    slug-shaped value -- 'alabama' as pdf_on_value, which is in no /Opt."""
    kit = {"schema_version": "2", "fields": [{
        "id": "f", "type": "select", "pdf_field_name": "f[0]", "section_id": "s",
        "options": [
            {"value": "alabama", "label": "Alabama", "pdf_on_value": ""},   # cleared, slug value
            {"value": "AL", "label": "Alabama (AL)", "pdf_on_value": ""},   # cleared, code-shaped value
            {"value": "AK", "label": "Alaska (AK)"},                        # legacy: key absent
        ]}], "sections": []}
    out, report = migrate_selects(kit)
    o = out["fields"][0]["options"]
    assert o[0] == {"value": "alabama", "label": "Alabama", "pdf_on_value": ""}
    assert o[1] == {"value": "AL", "label": "Alabama (AL)", "pdf_on_value": ""}
    assert o[2] == {"value": "alaska", "label": "Alaska (AK)", "pdf_on_value": "AK"}
    entry = report["fields"][0]
    assert entry["no_code"] == ["alabama", "AL"]      # named for the human
    assert entry["migrated"] == 1 and entry["already_v2"] == 2


def test_a_second_run_still_reports_outstanding_human_work_and_nothing_else():
    """Round 4: idempotence means migrate NOTHING twice, not report nothing.
    A cleared code the tool cannot supply is reported on every run, the same
    way each time; a migrated option is reported once."""
    kit = {"schema_version": "2", "fields": [{
        "id": "f", "type": "select", "pdf_field_name": "f[0]", "section_id": "s",
        "options": [
            {"value": "alabama", "label": "Alabama", "pdf_on_value": ""},   # cleared
            {"value": "AK", "label": "Alaska (AK)"},                        # legacy
        ]}], "sections": []}
    once, r1 = migrate_selects(kit)
    twice, r2 = migrate_selects(once)
    assert twice == once
    assert r1["options_migrated"] == 1 and r2["options_migrated"] == 0
    assert r1["fields"][0]["no_code"] == ["alabama"]
    assert r2["fields"][0]["no_code"] == ["alabama"]           # same list, every run
    assert r2["fields"][0]["migrated"] == 0 and r2["conditions_retargeted"] == 0


def test_cli_warns_about_cleared_codes_and_never_says_nothing_to_do_while_work_remains(tmp_path):
    kit = {"schema_version": "2", "fields": [{
        "id": "f", "type": "select", "pdf_field_name": "f[0]", "section_id": "s",
        "options": [{"value": "alabama", "label": "Alabama", "pdf_on_value": ""}]}],
        "sections": []}
    src = tmp_path / "a.json"
    src.write_text(json.dumps(kit), encoding="utf-8")
    r = subprocess.run([PY, str(SCRIPT), "--in", str(src), "--out", str(tmp_path / "b.json")],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    assert "WARNING" in r.stderr and "CLEARED" in r.stderr and "alabama" in r.stderr
    assert "nothing to do" not in r.stdout
    # ...whereas a fully migrated kit with no outstanding work does say so.
    clean = {"schema_version": "2", "fields": [{
        "id": "f", "type": "select", "pdf_field_name": "f[0]", "section_id": "s",
        "options": [{"value": "alabama", "label": "Alabama", "pdf_on_value": "AL"}]}],
        "sections": []}
    src.write_text(json.dumps(clean), encoding="utf-8")
    r2 = subprocess.run([PY, str(SCRIPT), "--in", str(src), "--out", str(tmp_path / "c.json")],
                        capture_output=True, text=True, cwd=str(REPO))
    assert r2.returncode == 0 and "nothing to do" in r2.stdout and "WARNING" not in r2.stderr


def test_a_legacy_code_equal_to_a_v2_siblings_CODE_is_reported_as_ambiguous():
    """Two options writing one widget state (round 3). Reported; the options
    still migrate (the code moves verbatim), but no condition is retargeted."""
    kit = {"schema_version": "2", "fields": [
        {"id": "f", "type": "select", "pdf_field_name": "f[0]", "section_id": "s",
         "options": [
             {"value": "alabama", "label": "Alabama", "pdf_on_value": "AL"},
             {"value": "AL", "label": "Assembly Line"},
         ]},
        {"id": "dep", "type": "text", "pdf_field_name": "d[0]", "section_id": "s",
         "show_if": {"field": "f", "operator": "equals", "value": "AL"}},
    ], "sections": []}
    out, report = migrate_selects(kit)
    assert report["fields"][0]["duplicate_codes"] == ["AL"]
    assert report["fields_with_duplicate_codes"] == ["f"]
    assert report["conditions_retargeted"] == 0
    assert out["fields"][1]["show_if"]["value"] == "AL"
    assert [o["pdf_on_value"] for o in out["fields"][0]["options"]] == ["AL", "AL"]


def test_a_duplicate_code_is_reported_and_its_conditions_are_NOT_retargeted():
    kit = {"schema_version": "2", "fields": [
        {"id": "f", "type": "select", "pdf_field_name": "f[0]", "section_id": "s",
         "options": [{"value": "AL", "label": "Alabama"}, {"value": "AL", "label": "Alabama North"}]},
        {"id": "dep", "type": "text", "pdf_field_name": "d[0]", "section_id": "s",
         "show_if": {"field": "f", "operator": "equals", "value": "AL"}},
    ], "sections": []}
    out, report = migrate_selects(kit)
    assert report["fields_with_duplicate_codes"] == ["f"]
    assert report["fields"][0]["duplicate_codes"] == ["AL"]
    assert report["conditions_retargeted"] == 0
    assert out["fields"][1]["show_if"]["value"] == "AL"     # left for a human
    # the options themselves still migrate (both keep the code)
    assert [o["pdf_on_value"] for o in out["fields"][0]["options"]] == ["AL", "AL"]


def test_non_select_fields_and_string_options_are_left_alone_and_string_options_are_REPORTED():
    kit = {"schema_version": "2", "fields": [
        {"id": "r", "type": "radio", "pdf_field_name": "r[0]", "section_id": "s",
         "options": [{"value": "yes", "label": "Yes", "pdf_on_value": "Y"}]},
        {"id": "s", "type": "select", "pdf_field_name": "s[0]", "section_id": "s",
         "options": ["AL", "AK"]},
    ], "sections": []}
    out, report = migrate_selects(kit)
    assert out["fields"] == kit["fields"]
    assert report["options_migrated"] == 0
    # Round 5: a string option is work the tool cannot do; it is named, not
    # silently counted into nothing.
    assert [(e["field"], e["non_dict_options"]) for e in report["fields"]] == [("s", 2)]


@pytest.mark.parametrize("kind,option,expect_line", [
    ("no_code",
     {"value": "alabama", "label": "Alabama", "pdf_on_value": ""},
     "alabama"),
    ("duplicate_codes",
     None,  # two legacy options sharing a code -- built below
     "AL"),
    ("non_dict_options",
     "AL",  # a plain-string option
     "1 string option(s)"),
])
def test_cli_prints_EVERY_kind_of_outstanding_work_one_line_per_field_capped(tmp_path, kind, option, expect_line):
    """Round 6 (scar #8): the three kinds must print the SAME shape -- a
    header, one line per field, and a "... more" trailer past the cap. Twelve
    fields of one kind: ten lines, then the trailer naming two more."""
    def field(i):
        if kind == "duplicate_codes":
            opts = [{"value": "AL", "label": "Alabama"}, {"value": "AL", "label": "Alabama North"}]
        else:
            opts = [option]
        return {"id": f"f{i:02d}", "type": "select", "pdf_field_name": f"f{i}[0]",
                "section_id": "x", "options": opts}
    kit = {"schema_version": "2", "fields": [field(i) for i in range(12)], "sections": []}
    src = tmp_path / "a.json"
    src.write_text(json.dumps(kit), encoding="utf-8")
    r = subprocess.run([PY, str(SCRIPT), "--in", str(src), "--out", str(tmp_path / "b.json")],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr            # warnings never fail the run
    lines = [l.strip() for l in r.stderr.splitlines()]
    assert sum(1 for l in lines if l.startswith("WARNING:")) == 1
    per_field = [l for l in lines if l.startswith("f") and ": " in l]
    assert per_field == [f"f{i:02d}: {expect_line}" for i in range(10)]   # capped at 10
    assert "... and 2 more field(s); see the report" in lines
    assert "nothing to do" not in r.stdout


def test_cli_warns_about_string_options_one_line_per_field(tmp_path):
    kit = {"schema_version": "2", "fields": [
        {"id": "s", "type": "select", "pdf_field_name": "s[0]", "section_id": "x",
         "options": ["AL", "AK"]},
        {"id": "f0", "type": "select", "pdf_field_name": "f0[0]", "section_id": "x",
         "options": [{"value": "alabama", "label": "Alabama", "pdf_on_value": ""},
                     {"value": "alaska", "label": "Alaska", "pdf_on_value": ""}]},
        {"id": "f1", "type": "select", "pdf_field_name": "f1[0]", "section_id": "x",
         "options": [{"value": "wyoming", "label": "Wyoming", "pdf_on_value": ""}]},
    ], "sections": []}
    src = tmp_path / "a.json"
    src.write_text(json.dumps(kit), encoding="utf-8")
    r = subprocess.run([PY, str(SCRIPT), "--in", str(src), "--out", str(tmp_path / "b.json")],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr            # warnings never fail the run
    lines = [l.strip() for l in r.stderr.splitlines()]
    assert "f0: alabama, alaska" in lines         # one line per field, values joined
    assert "f1: wyoming" in lines
    assert "s: 2 string option(s)" in lines
    assert "nothing to do" not in r.stdout


def test_a_condition_on_another_field_with_the_same_literal_is_not_touched():
    """Retargeting is keyed on the TRIGGER: 'WY' on a text field stays 'WY'."""
    kit = _kit_like_i90()
    kit["fields"].append({
        "id": "other", "type": "text", "pdf_field_name": "o[0]", "section_id": "s1",
        "show_if": {"field": "dep", "operator": "equals", "value": "WY"}})
    out, _ = migrate_selects(kit)
    assert out["fields"][-1]["show_if"]["value"] == "WY"


# ---------------------------------------------------------------------------
# The CLI: --kit archives, reports, never touches metadata.json
# ---------------------------------------------------------------------------

def test_cli_kit_mode_rewrites_in_place_archives_reports_and_leaves_metadata_alone(tmp_path):
    kit_dir = tmp_path / "i-90_copy"
    kit_dir.mkdir()
    (kit_dir / "schema.json").write_text(json.dumps(_kit_like_i90()), encoding="utf-8")
    meta = {"status": "complete", "readiness": {"sha": "abc"}}
    (kit_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    meta_mtime = os.stat(kit_dir / "metadata.json").st_mtime_ns

    r = subprocess.run([PY, str(SCRIPT), "--kit", str(kit_dir)],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    assert "options migrated: 37" in r.stdout

    migrated = json.loads((kit_dir / "schema.json").read_text(encoding="utf-8"))
    assert migrated["fields"][0]["options"][0] == {
        "value": "alabama", "label": "Alabama (AL)", "pdf_on_value": "AL"}
    archived = json.loads((kit_dir / "schema_pre_select_migration.json").read_text(encoding="utf-8"))
    assert archived == _kit_like_i90()
    report = json.loads((kit_dir / "select_migration_report.json").read_text(encoding="utf-8"))
    assert report["options_migrated"] == 37 and report["conditions_retargeted"] == 4
    # metadata.json: byte-identical AND never opened for writing.
    assert json.loads((kit_dir / "metadata.json").read_text(encoding="utf-8")) == meta
    assert os.stat(kit_dir / "metadata.json").st_mtime_ns == meta_mtime

    # Second run: no-op, says so.
    r2 = subprocess.run([PY, str(SCRIPT), "--kit", str(kit_dir)],
                        capture_output=True, text=True, cwd=str(REPO))
    assert r2.returncode == 0 and "nothing to do" in r2.stdout
    assert json.loads((kit_dir / "schema.json").read_text(encoding="utf-8")) == migrated


def test_cli_in_out_mode(tmp_path):
    src = tmp_path / "a.json"
    src.write_text(json.dumps(_kit_like_i90()), encoding="utf-8")
    r = subprocess.run([PY, str(SCRIPT), "--in", str(src), "--out", str(tmp_path / "b.json"),
                        "--report", str(tmp_path / "r.json")],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    assert json.loads(src.read_text(encoding="utf-8")) == _kit_like_i90()   # input untouched
    assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["options_migrated"] == 37


def test_cli_refuses_both_modes_at_once(tmp_path):
    r = subprocess.run([PY, str(SCRIPT), "--kit", str(tmp_path), "--in", "x", "--out", "y"],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode != 0


# ---------------------------------------------------------------------------
# Fresh-eyes round 1 (g2fpr.3)
# ---------------------------------------------------------------------------

def test_a_legacy_code_that_equals_an_already_v2_value_does_not_collide():
    """The THIRD state: a field the editor half-migrated. A legacy option whose
    code is itself a valid slug ('5') must not be handed the same value as the
    already-v2 sibling that carries '5' -- it is minted from its label."""
    kit = {"schema_version": "2", "fields": [{
        "id": "f", "type": "select", "pdf_field_name": "f[0]", "section_id": "s",
        "options": [
            {"value": "5", "label": "5", "pdf_on_value": "5"},     # v2 already
            {"value": "5", "label": "Five", },                     # legacy, same code
        ]}], "sections": []}
    out, report = migrate_selects(kit)
    values = [o["value"] for o in out["fields"][0]["options"]]
    assert values == ["5", "five"]
    assert len(set(values)) == 2
    assert out["fields"][0]["options"][1]["pdf_on_value"] == "5"


def test_the_report_NAMES_every_kept_code_not_just_counts_them():
    """Criterion: the report names every change. A numeric option that keeps
    its value still gains pdf_on_value; the report lists it by code."""
    _, report = migrate_selects(_kit_like_i90())
    hf = next(e for e in report["fields"] if e["field"] == "height_feet")
    assert hf["kept_codes"] == ["3", "4", "5", "6", "7"]
    assert hf["kept_as_slug"] == len(hf["kept_codes"])
    # Every migrated option is named exactly once: in slug_map OR kept_codes.
    for e in report["fields"]:
        assert e["migrated"] == len(e["slug_map"]) + len(e["kept_codes"]), e["field"]


def test_an_id_less_select_migrates_its_options_but_is_never_a_retarget_key():
    kit = {"schema_version": "2", "fields": [
        {"type": "select", "pdf_field_name": "a[0]", "section_id": "s",
         "options": [{"value": "AL", "label": "Alabama"}]},
        {"type": "select", "pdf_field_name": "b[0]", "section_id": "s",
         "options": [{"value": "AL", "label": "Alabama"}]},
        {"id": "dep", "type": "text", "pdf_field_name": "d[0]", "section_id": "s",
         "show_if": {"field": "None", "operator": "equals", "value": "AL"}},
    ], "sections": []}
    out, report = migrate_selects(kit)
    assert [f["options"][0]["pdf_on_value"] for f in out["fields"][:2]] == ["AL", "AL"]
    assert out["fields"][2]["show_if"]["value"] == "AL"      # not retargeted via "None"
    assert report["conditions_retargeted"] == 0


# ---------------------------------------------------------------------------
# Fresh-eyes round 2 (g2fpr.3)
# ---------------------------------------------------------------------------

def test_a_legacy_code_equal_to_a_v2_siblings_VALUE_is_ambiguous_and_not_retargeted():
    """A condition naming '5' may mean the v2 option whose value is '5', not
    the legacy option coded '5'. Report it; do not repoint it to the new slug."""
    kit = {"schema_version": "2", "fields": [
        {"id": "f", "type": "select", "pdf_field_name": "f[0]", "section_id": "s",
         "options": [
             {"value": "5", "label": "5", "pdf_on_value": "5"},   # v2
             {"value": "5", "label": "Five"},                     # legacy, same code
         ]},
        {"id": "dep", "type": "text", "pdf_field_name": "d[0]", "section_id": "s",
         "show_if": {"field": "f", "operator": "equals", "value": "5"}},
    ], "sections": []}
    out, report = migrate_selects(kit)
    assert out["fields"][1]["show_if"]["value"] == "5"            # left for a human
    assert report["conditions_retargeted"] == 0
    assert report["fields"][0]["duplicate_codes"] == ["5"]
    assert report["fields_with_duplicate_codes"] == ["f"]
    assert [o["value"] for o in out["fields"][0]["options"]] == ["5", "five"]


def test_two_legacy_options_sharing_a_slug_shaped_code_do_not_share_a_value():
    kit = {"schema_version": "2", "fields": [{
        "id": "f", "type": "select", "pdf_field_name": "f[0]", "section_id": "s",
        "options": [{"value": "5", "label": "5"}, {"value": "5", "label": "Five North"}]}],
        "sections": []}
    out, report = migrate_selects(kit)
    values = [o["value"] for o in out["fields"][0]["options"]]
    assert values == ["5", "five_north"] and len(set(values)) == 2
    assert [o["pdf_on_value"] for o in out["fields"][0]["options"]] == ["5", "5"]
    assert report["fields"][0]["duplicate_codes"] == ["5"]
