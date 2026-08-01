"""Integration tests for the derived-division extraction step (bd 6cfu.2).

Exercises derive_and_apply -- the exact call extract_form.py makes at
pipeline step 3e -- against REAL checked-in kits (no LLM, no network):

- the applied schema's sections/parts are 100% derivation output and every
  field's section_id points into them (exit criterion 1);
- re-running derivation on the same PDF + schema is section-stable
  (exit criterion 2);
- derived sections carry 1-based page numbers matching field
  pdf_position.page;
- the applied schema still passes FormSchema.model_validate.

Imports the scripts by file path (repo precedent:
test_extract_form_backfill.py). ASCII only.
"""

import copy
import importlib.util
import json
import pathlib
import sys
import warnings

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))
_SCRIPT = _REPO / "scripts" / "authoring" / "derive_sections.py"
spec = importlib.util.spec_from_file_location("derive_sections_it", _SCRIPT)
ds = importlib.util.module_from_spec(spec)
sys.modules["derive_sections_it"] = ds
spec.loader.exec_module(ds)

_W7 = _REPO / "form-kits" / "w7"
_I90 = _REPO / "form-kits" / "i-90"
_F1040 = _REPO / "form-kits" / "f1040"

pytestmark = pytest.mark.skipif(
    not (_W7 / "form.pdf").exists() or not (_I90 / "form.pdf").exists()
    or not (_F1040 / "form.pdf").exists(),
    reason="checked-in form kits unavailable",
)


def _load_kit(kit_dir):
    with open(kit_dir / "schema.json", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def w7_applied():
    schema = _load_kit(_W7)
    summary = ds.derive_and_apply(schema, str(_W7 / "form.pdf"))
    return schema, summary


def test_apply_replaces_divisions_and_files_every_field(w7_applied):
    schema, summary = w7_applied
    section_ids = {s["id"] for s in schema["sections"]}
    # Every field's section_id points at a derived section, and every
    # section's fields[] entry is a real field (bidirectional consistency).
    field_ids = {f["id"] for f in schema["fields"]}
    for f in schema["fields"]:
        assert f["section_id"] in section_ids
    listed = [fid for s in schema["sections"] for fid in s["fields"]]
    assert set(listed) == field_ids
    assert len(listed) == len(field_ids)  # each field filed exactly once
    # Parts reference derived sections only.
    for p in schema["parts"]:
        assert set(p["section_ids"]) <= section_ids
    assert summary["strategy"] == "printed-heading"  # w7 = IRS margin headings


def test_derived_pages_are_one_based_and_match_field_positions(w7_applied):
    schema, _ = w7_applied
    by_id = {s["id"]: s for s in schema["sections"]}
    for f in schema["fields"]:
        pos = f.get("pdf_position") or {}
        sec = by_id[f["section_id"]]
        if pos.get("page") is not None and "page_number" in sec:
            assert sec["page_number"] == pos["page"]  # 1-based on both sides
    assert all(s.get("page_number", 1) >= 1 for s in schema["sections"])


def test_rerun_is_section_stable(w7_applied):
    """Exit criterion 2: deriving again from the SAME PDF + the already-derived
    schema reproduces identical sections/parts and section_id assignments."""
    schema, _ = w7_applied
    again = copy.deepcopy(schema)
    ds.derive_and_apply(again, str(_W7 / "form.pdf"))
    assert again["sections"] == schema["sections"]
    assert again["parts"] == schema["parts"]
    assert [f["section_id"] for f in again["fields"]] == \
           [f["section_id"] for f in schema["fields"]]


def test_applied_w7_schema_validates(w7_applied):
    from backend.models.form_models import FormSchema
    schema, _ = w7_applied
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        FormSchema.model_validate(schema)


def test_i90_uses_name_convention_with_no_spurious_to_review():
    """The USCIS family: P{N}_ names drive the division -- INCLUDING
    consolidated options[] fields whose widget name lives on the options,
    not the field (fresh-eyes regression, 6cfu.2: without the option-name
    fallback 18 real i-90 fields -- sex, ethnicity, race, ... -- were
    misfiled into 'To review'). Every i-90 kit field derives a real home."""
    schema = _load_kit(_I90)
    summary = ds.derive_and_apply(schema, str(_I90 / "form.pdf"))
    assert summary["strategy"] == "name-convention"
    assert summary["to_review_field_ids"] == []
    assert summary["to_review_section_ids"] == []
    by_field = {f["id"]: f["section_id"] for f in schema["fields"]}
    # The consolidated option-bearing fields land in real derived sections.
    for fid in ("p3_race", "p3_ethnicity", "p1_line8_male", "p5_checkbox1a"):
        assert not by_field[fid].startswith("sec_to_review"), fid
    # Recorded review ids (none here) would have to sit in review sections;
    # the invariant is pinned synthetically in test_derive_sections.py.
    section_ids = {s["id"] for s in schema["sections"]}
    assert not any(sid.startswith("sec_to_review") for sid in section_ids)


def test_i90_part8_repeat_rows_not_filed_under_name_subheading():
    """A sub-heading governs exactly one USCIS part (bd polyglot-pdf-h1eo).

    i-90 page 7 prints the Part-1 name-reverification block under a "Your
    Full Name" sub-heading, immediately followed by Part-8's Page/Part/Item-
    Number continuation rows -- which have NO sub-heading of their own and no
    intervening part heading, so the geometric barrier never fires. Before the
    fix those Part-8 fields inherited the "Your Full Name" label; now they
    fall through to their part label ("Part 8. ...")."""
    schema = _load_kit(_I90)
    ds.derive_and_apply(schema, str(_I90 / "form.pdf"))
    by_section = {s["id"]: s for s in schema["sections"]}
    p8_fields = ("p8_line3a_pagenumber", "p8_line3d_additionalinfo",
                 "p8_line5d_additionalinfo[1]")
    for fid in p8_fields:
        sid = next(f["section_id"] for f in schema["fields"] if f["id"] == fid)
        label = by_section[sid]["label"]
        assert "Your Full Name" not in label, (fid, label)
        assert label.startswith("Part 8"), (fid, label)
    # The legitimate page-7 name-reverification fields keep the Name heading.
    for fid in ("p1_line3a_familyname[1]", "p1_line3c_middlename[1]"):
        sid = next(f["section_id"] for f in schema["fields"] if f["id"] == fid)
        assert by_section[sid]["label"] == "Your Full Name", (fid, sid)


def test_f1040_dependents_cap_split_is_balanced():
    """The motivating real-kit case for the balanced-split policy (maintainer
    feedback at the 6cfu.1 checkpoint): f1040's 'Dependents' block (42 fields
    at cap 40) splits 21+21, never greedy 40+2. Pins _balanced_chunks +
    _row_family + printed-heading bucketing end-to-end against the real PDF."""
    schema = _load_kit(_F1040)
    summary = ds.derive_and_apply(schema, str(_F1040 / "form.pdf"))
    assert summary["strategy"] == "printed-heading"
    dep = [s for s in schema["sections"] if s["label"].startswith("Dependents")]
    assert [s["label"] for s in dep] == ["Dependents (1 of 2)",
                                         "Dependents (2 of 2)"]
    assert [len(s["fields"]) for s in dep] == [21, 21]


@pytest.mark.parametrize("kit", [_W7, _I90, _F1040],
                         ids=["w7", "i90", "f1040"])
def test_derive_then_repair_keeps_sections_and_fields_consistent(kit):
    """derive_and_apply THEN repair leaves every section/field reference intact
    on the real checked-in kits (bd polyglot-pdf-n2t3). No LLM, no network.

    SCOPE, precisely: this calls the two functions in the order extract_form
    happens to call them (derive at step 3e ~line 1490, repair at step 4 ~line
    1520). It does NOT invoke extract_form itself, so it does NOT detect a
    future refactor that REORDERS the pipeline -- swapping those two calls in
    extract_form.py leaves this file green. What it guards is that repair does
    not break references derivation established.

    NOTE: the committed kits are already clean, so repair() is a NO-OP here (0
    repairs on all three) and this case pins the composition's SHAPE only. The
    mutating case -- where repair actually re-mints values and rewrites
    conditions -- is pinned by test_derive_then_MUTATING_repair_* below, which
    is the one that catches a real regression.
    """
    from backend.services.schema_repair import repair

    schema = _load_kit(kit)
    ds.derive_and_apply(schema, str(kit / "form.pdf"))
    repaired, _repairs = repair(copy.deepcopy(schema), None)

    section_ids = {s["id"] for s in repaired["sections"]}
    field_ids = {f["id"] for f in repaired["fields"]}

    # Every field still resolves to a real section...
    for f in repaired["fields"]:
        assert f["section_id"] in section_ids, (f["id"], f["section_id"])
    # ...and every id a section lists is still a real field, filed exactly once.
    listed = [fid for s in repaired["sections"] for fid in s["fields"]]
    assert set(listed) == field_ids
    assert len(listed) == len(field_ids)
    # Parts still reference only real sections, with unique ids (n2t3 item 1).
    part_ids = [p["id"] for p in repaired["parts"]]
    assert len(part_ids) == len(set(part_ids)), part_ids
    for p in repaired["parts"]:
        assert set(p["section_ids"]) <= section_ids


def test_derive_then_MUTATING_repair_keeps_section_references_intact():
    """A repair that ACTUALLY rewrites the schema must not break the section
    references derivation established (bd polyglot-pdf-n2t3).

    The committed kits are clean, so repair() no-ops on them -- a consistency
    assertion over that composition pins nothing (fresh-eyes review). This case
    forces real mutation: a choice field whose option values collide ("1"/"1")
    and violate the slug convention, which drives _mint_slugs to re-mint them
    and rewrite the show_if conditions that referenced the old values.

    What must survive: every section_id still resolves, and every id listed in a
    section's fields[] is still a real field. Like its sibling above, this does
    NOT invoke extract_form, so it does not detect a pipeline REORDER -- it
    guards repair's behavior, not the call order.
    """
    from backend.services.schema_repair import repair

    schema = {
        "form_id": "synthetic",
        "title": "Synthetic",
        "fields": [
            {"id": "choice", "type": "radio", "label": "Pick one",
             "section_id": "sec_only",
             "options": [
                 {"value": "1", "label": "Alpha", "pdf_field_name": "w_a"},
                 {"value": "1", "label": "Beta", "pdf_field_name": "w_b"},
             ]},
            {"id": "dependent", "type": "text", "label": "Why?",
             "section_id": "sec_only",
             "show_if": {"field": "choice", "equals": "1"}},
        ],
        "sections": [
            {"id": "sec_only", "label": "Only", "order": 1,
             "fields": ["choice", "dependent"]},
        ],
        "parts": [
            {"id": "part_only", "label": "Only", "order": 1,
             "section_ids": ["sec_only"]},
        ],
    }

    repaired, repairs = repair(copy.deepcopy(schema), None)

    # The premise: this repair really did mutate (otherwise the test is vacuous).
    substantive = [r for r in repairs if r.get("action") != "alias-hit-rate"]
    assert substantive, "expected repair() to re-mint the colliding option values"
    values = [o["value"] for o in repaired["fields"][0]["options"]]
    assert len(set(values)) == 2, values  # the "1"/"1" collision is resolved

    # The contract: section <-> field references survive the rewrite.
    section_ids = {s["id"] for s in repaired["sections"]}
    field_ids = {f["id"] for f in repaired["fields"]}
    for f in repaired["fields"]:
        assert f["section_id"] in section_ids, (f["id"], f["section_id"])
    listed = [fid for s in repaired["sections"] for fid in s["fields"]]
    assert set(listed) == field_ids
    assert len(listed) == len(field_ids)
    for p in repaired["parts"]:
        assert set(p["section_ids"]) <= section_ids
