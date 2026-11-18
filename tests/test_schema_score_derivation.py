"""Tests for section-grouping-via-derivation in scripts/schema_score.py
(bd polyglot-pdf-mhyt).

Context: the extractor contract (scripts/bakeoff/schema_contract.py) instructs
every LLM-native bake-off arm NOT to emit parts/sections/section_id -- form
divisions are derived deterministically post-extraction
(scripts/authoring/derive_sections.py, bd polyglot-pdf-6cfu.2). Scoring that raw
arm output as-is makes every field a section_grouping SINGLETON (see
schema_score._section_grouping_agreement), so recall/F1 come out ~0 regardless
of extraction quality -- a scorer artifact, not a real signal.

The fix: schema_score.score(..., derive_pdf_path=...) runs the SAME production
derivation entry point (derive_sections.derive_and_apply) on a COPY of a
section_id-less draft before grading section_grouping, and records the basis
("draft" vs "derived" vs "derivation-error") on the metric. These tests pin:

  1. a draft with NO section_id gets divisions derived and a non-singleton
     grouping score against a canon where the derived partition is non-trivial;
  2. a draft that DOES carry section_id keeps grading its OWN grouping
     (derivation is never applied, basis stays "draft");
  3. a derivation error (bad/unreadable PDF) marks section_grouping n/a with a
     reason, never a silent 0.

All synthetic (no LLM, no network). A real (tiny, blank) PDF is built with
PyMuPDF so derive_sections' page-fallback strategy has real pages to place
fields on -- this mirrors test_derive_sections.py's precedent of using a real
fitz document for the strategy ladder's PDF-dependent parts (headings,
page_count, page width).

Load pattern mirrors tests/test_schema_score_section_grouping.py (load the
script as a module without running its CLI main()). ASCII only.
"""
from __future__ import annotations

import importlib.util
import math
import pathlib
import sys

import pytest

fitz = pytest.importorskip("pymupdf")

_REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT_PATH = _REPO / "scripts" / "schema_score.py"
spec = importlib.util.spec_from_file_location("schema_score", SCRIPT_PATH)
schema_score = importlib.util.module_from_spec(spec)
sys.modules["schema_score"] = schema_score
spec.loader.exec_module(schema_score)


def _blank_two_page_pdf(tmp_path) -> str:
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.new_page(width=612, height=792)
    p = tmp_path / "blank.pdf"
    doc.save(str(p))
    doc.close()
    return str(p)


def _write_schema(tmp_path, name: str, schema: dict) -> str:
    import json
    p = tmp_path / name
    p.write_text(json.dumps(schema), encoding="utf-8")
    return str(p)


# Generic (non-USCIS-name-convention) fields split 2-per-page, so
# derive_sections picks the "page-fallback" strategy and groups f1/f2 (page 1)
# and f3/f4 (page 2) -- verified directly against derive_sections in this same
# test module's setup probe. The truth/canon below mirrors that SAME partition
# so the derived grouping is genuinely gradable (non-trivial true_pairs).
def _fields_no_section_id():
    return [
        {"id": "f1", "name": "A", "type": "text", "pdf_field_name": "f1",
         "pdf_position": {"page": 1, "x": 10, "y": 10}},
        {"id": "f2", "name": "B", "type": "text", "pdf_field_name": "f2",
         "pdf_position": {"page": 1, "x": 10, "y": 30}},
        {"id": "f3", "name": "C", "type": "text", "pdf_field_name": "f3",
         "pdf_position": {"page": 2, "x": 10, "y": 10}},
        {"id": "f4", "name": "D", "type": "text", "pdf_field_name": "f4",
         "pdf_position": {"page": 2, "x": 10, "y": 30}},
    ]


def _canon_matching_page_partition():
    # Gold groups (f1,f2) and (f3,f4) -- the SAME partition page-fallback
    # derivation produces, so grouping recall/precision/F1 are all non-trivial
    # (neither 0 nor n/a) when scored on the derived divisions.
    return {
        "fields": [
            {"id": "f1", "name": "A", "type": "text", "pdf_field_name": "f1",
             "section_id": "gold_page1"},
            {"id": "f2", "name": "B", "type": "text", "pdf_field_name": "f2",
             "section_id": "gold_page1"},
            {"id": "f3", "name": "C", "type": "text", "pdf_field_name": "f3",
             "section_id": "gold_page2"},
            {"id": "f4", "name": "D", "type": "text", "pdf_field_name": "f4",
             "section_id": "gold_page2"},
        ]
    }


# --------------------------------------------------------------------------- #
# 1. No section_id anywhere -> derive, non-singleton, non-trivial grouping.
# --------------------------------------------------------------------------- #

def test_no_section_id_draft_derives_divisions_and_scores_non_singleton(tmp_path):
    pdf_path = _blank_two_page_pdf(tmp_path)
    draft = {"fields": _fields_no_section_id()}
    truth = _canon_matching_page_partition()
    draft_path = _write_schema(tmp_path, "draft.json", draft)
    truth_path = _write_schema(tmp_path, "truth.json", truth)

    result = schema_score.score(draft_path, truth_path, derive_pdf_path=pdf_path)
    sg = result["field_extraction"]["attributes"]["section_grouping"]

    assert sg["basis"] == "derived"
    # The derived partition groups f1/f2 and f3/f4 -- the SAME as the gold
    # canon, so this is NOT the spurious singleton-vs-nothing 0: both sides
    # have real pairs and they agree. ("correct" is the metric's agree_pairs,
    # per score_fields's attr_scores shape.)
    assert sg["true_pairs"] == 2   # (f1,f2) + (f3,f4)
    assert sg["predicted_pairs"] == 2
    assert sg["correct"] == 2
    assert sg["f1"] == 1.0
    assert sg["pct"] == 100.0


def test_derivation_is_scored_on_a_copy_not_the_original_draft_dict(tmp_path):
    # The raw arm output on disk (and the in-memory draft dict handed to
    # score()) must be UNCHANGED -- derivation runs on a deep copy at scoring
    # time only (bd mhyt constraint: never mutate the recorded arm output).
    pdf_path = _blank_two_page_pdf(tmp_path)
    draft = {"fields": _fields_no_section_id()}
    truth = _canon_matching_page_partition()
    draft_path = _write_schema(tmp_path, "draft.json", draft)
    truth_path = _write_schema(tmp_path, "truth.json", truth)

    schema_score.score(draft_path, truth_path, derive_pdf_path=pdf_path)

    # Re-load the draft straight from disk: still has no section_id anywhere.
    reloaded = schema_score.load_schema(draft_path)
    assert all(not f.get("section_id") for f in reloaded["fields"])


# --------------------------------------------------------------------------- #
# 2. Draft WITH section_id keeps its own grouping (derivation not applied).
# --------------------------------------------------------------------------- #

def test_draft_with_section_id_keeps_its_own_grouping_not_derived(tmp_path):
    pdf_path = _blank_two_page_pdf(tmp_path)
    # This draft carries section_id, and deliberately does NOT match the
    # page-fallback partition (it groups everything into ONE section) -- if
    # derivation were (wrongly) applied, the score would come out as the
    # page-fallback 2-group answer instead. Proves the "has section_id -> use
    # as-is" branch actually short-circuits derivation.
    draft = {"fields": [
        {"id": "f1", "name": "A", "type": "text", "pdf_field_name": "f1",
         "pdf_position": {"page": 1, "x": 10, "y": 10}, "section_id": "one_big_sec"},
        {"id": "f2", "name": "B", "type": "text", "pdf_field_name": "f2",
         "pdf_position": {"page": 1, "x": 10, "y": 30}, "section_id": "one_big_sec"},
        {"id": "f3", "name": "C", "type": "text", "pdf_field_name": "f3",
         "pdf_position": {"page": 2, "x": 10, "y": 10}, "section_id": "one_big_sec"},
        {"id": "f4", "name": "D", "type": "text", "pdf_field_name": "f4",
         "pdf_position": {"page": 2, "x": 10, "y": 30}, "section_id": "one_big_sec"},
    ]}
    truth = _canon_matching_page_partition()
    draft_path = _write_schema(tmp_path, "draft.json", draft)
    truth_path = _write_schema(tmp_path, "truth.json", truth)

    result = schema_score.score(draft_path, truth_path, derive_pdf_path=pdf_path)
    sg = result["field_extraction"]["attributes"]["section_grouping"]

    assert sg["basis"] == "draft"
    # Draft lumps ALL 4 fields into one section -> predicted_pairs = C(4,2) = 6,
    # true_pairs = 2 (gold's page split), agree = 2 (both true pairs are also
    # predicted, since one giant group contains every gold pair too).
    assert sg["true_pairs"] == 2
    assert sg["predicted_pairs"] == 6
    assert sg["correct"] == 2
    # precision 2/6, recall 2/2=1.0 -> not the derived-basis 1.0/1.0 result.
    assert math.isclose(sg["recall"], 1.0)
    assert math.isclose(sg["precision"], 2 / 6)


def test_no_derive_pdf_path_given_defaults_to_draft_basis(tmp_path):
    # Without derive_pdf_path at all, behavior is unchanged from before mhyt:
    # a section_id-less draft is scored as-is (singleton), basis "draft".
    draft = {"fields": _fields_no_section_id()}
    truth = _canon_matching_page_partition()
    draft_path = _write_schema(tmp_path, "draft.json", draft)
    truth_path = _write_schema(tmp_path, "truth.json", truth)

    result = schema_score.score(draft_path, truth_path)
    sg = result["field_extraction"]["attributes"]["section_grouping"]
    assert sg["basis"] == "draft"
    assert sg["predicted_pairs"] == 0  # every field a singleton
    assert sg["f1"] == 0.0


# --------------------------------------------------------------------------- #
# 3. Derivation error -> n/a with a reason, never a silent 0.
# --------------------------------------------------------------------------- #

def test_derivation_error_marks_na_not_zero(tmp_path):
    draft = {"fields": _fields_no_section_id()}
    truth = _canon_matching_page_partition()
    draft_path = _write_schema(tmp_path, "draft.json", draft)
    truth_path = _write_schema(tmp_path, "truth.json", truth)

    bad_pdf_path = str(tmp_path / "does_not_exist.pdf")
    result = schema_score.score(draft_path, truth_path, derive_pdf_path=bad_pdf_path)
    sg = result["field_extraction"]["attributes"]["section_grouping"]

    assert sg["basis"] == "derivation-error"
    assert "error" in sg and sg["error"]
    assert math.isnan(sg["pct"])
    assert math.isnan(sg["f1"])
    # NOT the spurious 0 a silently-failed derivation would otherwise produce.
    assert sg["pct"] != 0.0


def test_derive_divisions_for_grouping_helper_returns_original_on_error(tmp_path):
    draft = {"fields": _fields_no_section_id()}
    bad_pdf_path = str(tmp_path / "nope.pdf")
    out, basis, reason = schema_score.derive_divisions_for_grouping(draft, bad_pdf_path)
    assert basis == "derivation-error"
    assert reason
    assert out is draft  # unchanged original returned, not a mangled copy


def test_derive_divisions_for_grouping_helper_success(tmp_path):
    pdf_path = _blank_two_page_pdf(tmp_path)
    draft = {"fields": _fields_no_section_id()}
    out, basis, reason = schema_score.derive_divisions_for_grouping(draft, pdf_path)
    assert basis == "derived"
    assert reason is None
    assert out is not draft  # a copy, not the original
    ids = {f["id"]: f.get("section_id") for f in out["fields"]}
    assert ids["f1"] == ids["f2"]
    assert ids["f3"] == ids["f4"]
    assert ids["f1"] != ids["f3"]
    # The original draft handed in is untouched.
    assert all(not f.get("section_id") for f in draft["fields"])


# --------------------------------------------------------------------------- #
# 4. The derived section_ids are OVERLAID on the original match's pairs --
#    never obtained via a re-match (whose Pass-2 fuzzy key bakes in section_id
#    and could pair a DIFFERENT field set once derivation stamps ids).
# --------------------------------------------------------------------------- #
def test_overlay_keeps_the_exact_pair_set_and_swaps_only_section_id():
    orig = _fields_no_section_id()
    derived = [dict(f) for f in orig]
    for f, sid in zip(derived, ["s1", "s1", "s2", "s2"]):
        f["section_id"] = sid
    truth = _canon_matching_page_partition()["fields"]
    # Pairs reference the ORIGINAL field dict objects, as match_fields does.
    pairs = list(zip(truth, orig))

    out = schema_score._overlay_derived_section_ids(pairs, orig, derived)

    # Same pair COUNT and same truth sides, by construction.
    assert len(out) == len(pairs)
    assert [t for t, _ in out] == [t for t, _ in pairs]
    # Draft sides carry the derived section_id...
    assert [d["section_id"] for _, d in out] == ["s1", "s1", "s2", "s2"]
    # ...and the original draft dicts were NOT mutated.
    assert all("section_id" not in f for f in orig)


def test_overlay_leaves_unknown_draft_dicts_untouched():
    orig = _fields_no_section_id()
    derived = [dict(f, section_id="s1") for f in orig]
    truth = _canon_matching_page_partition()["fields"]
    stranger = {"id": "zz", "name": "Z", "section_id": "keep_me"}
    pairs = [(truth[0], orig[0]), (truth[1], stranger)]

    out = schema_score._overlay_derived_section_ids(pairs, orig, derived)

    assert out[0][1]["section_id"] == "s1"
    # A draft dict not in orig_fields (no positional counterpart) keeps its own.
    assert out[1][1]["section_id"] == "keep_me"


# --- pdf_position: not-asked is not-applicable (bd polyglot-pdf-icyi) -------- #

def test_absent_draft_position_is_NA_not_a_miss():
    """The SAME scorer-artifact class this file already fixes for sections.

    The extraction contract no longer asks the model for pdf_position -- widget
    geometry is read from the PDF's own AcroForm widgets after extraction,
    because a model transcribing coordinates rounds them and its page base is
    non-deterministic (that shipped a real bug: 48 of 54 w7 fields on page 0,
    every text overlay invisible in the editor). Raw arms are scored on DRAFT
    output, which never goes through that back-fill, so a draft legitimately
    carries no positions now. Grading that absence as a MISS would peg
    pdf_position at 0% for every future arm and drag down the headline attribute
    average -- a metric change nobody chose."""
    gold = {"pdf_position": {"page": 1, "x": 10, "y": 10}}
    assert schema_score._pos_match(gold, {}) is None            # not asked
    assert schema_score._pos_match({}, gold) is None            # gold silent


def test_a_present_but_WRONG_draft_position_is_still_a_miss():
    """The metric keeps its teeth for an arm that does emit coordinates -- only
    ABSENCE is excused, never a wrong value (page or coords out of tolerance)."""
    gold = {"pdf_position": {"page": 1, "x": 10, "y": 10}}
    assert schema_score._pos_match(
        gold, {"pdf_position": {"page": 1, "x": 10, "y": 10}}) is True
    assert schema_score._pos_match(
        gold, {"pdf_position": {"page": 2, "x": 10, "y": 10}}) is False
    assert schema_score._pos_match(
        gold, {"pdf_position": {"page": 1, "x": 999, "y": 10}}) is False
