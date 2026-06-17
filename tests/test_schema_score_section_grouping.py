"""Tests for the section-GROUPING metric in scripts/schema_score.py
(bd polyglot-pdf-7a9.13).

Exact section_id string matching was a broken quality signal (the I-90 gold ids
are inconsistent hand-authored noise, so every extractor scored 0%). The decision
(option b) replaced it with a partition-agreement (Rand-index) score over matched
fields: do draft and gold agree on which fields share a section, regardless of the
section NAME? These tests pin that behavior -- especially naming-independence,
which is the whole point.

Load pattern mirrors tests/test_harness_ledger.py (load the script as a module
without running its CLI main()).
"""
import importlib.util
import pathlib
import sys

SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "schema_score.py"
)
spec = importlib.util.spec_from_file_location("schema_score", SCRIPT_PATH)
schema_score = importlib.util.module_from_spec(spec)
sys.modules["schema_score"] = schema_score
spec.loader.exec_module(schema_score)

_grouping = schema_score._section_grouping_agreement


def _pairs(*specs):
    """Build matched (truth, draft) pairs from (truth_section, draft_section) tuples.

    A None truth_section means the gold never sectioned that field (it must be
    ignored by the metric).
    """
    pairs = []
    for i, (ts, ds) in enumerate(specs):
        t = {"id": f"f{i}", "section_id": ts}
        d = {"id": f"f{i}", "section_id": ds}
        pairs.append((t, d))
    return pairs


def test_perfect_grouping_scores_100():
    # Two sections, two fields each; draft mirrors the gold partition exactly.
    pairs = _pairs(("A", "X"), ("A", "X"), ("B", "Y"), ("B", "Y"))
    agree, comparable = _grouping(pairs)
    assert comparable == 6  # C(4,2)
    assert agree == 6
    assert schema_score._pct(agree, comparable) == 100.0


def test_naming_is_irrelevant_only_grouping_matters():
    # Draft uses COMPLETELY different section names but the SAME partition ->
    # still a perfect score. This is the core reason for the metric change.
    gold_names = _pairs(("Part 1 - Information About You", "part_1_info"),
                        ("Part 1 - Information About You", "part_1_info"),
                        ("part_6_interpreter", "Part 6 - Interpreter"),
                        ("part_6_interpreter", "Part 6 - Interpreter"))
    agree, comparable = _grouping(gold_names)
    assert agree == comparable == 6
    assert schema_score._pct(agree, comparable) == 100.0


def test_wrong_grouping_is_penalized():
    # Gold puts f0,f1 together and f2,f3 together. Draft splits f0 from f1 and
    # lumps f1 with f2 -> several pairwise disagreements.
    pairs = _pairs(("A", "X"), ("A", "Y"), ("B", "Y"), ("B", "Z"))
    agree, comparable = _grouping(pairs)
    assert comparable == 6
    # Pairs: (f0,f1) gold-same/draft-diff DISAGREE; (f0,f2) diff/diff agree;
    # (f0,f3) diff/diff agree; (f1,f2) gold-diff/draft-same DISAGREE;
    # (f1,f3) diff/diff agree; (f2,f3) gold-same/draft-diff DISAGREE.
    assert agree == 3
    assert schema_score._pct(agree, comparable) == 50.0


def test_all_one_section_vs_all_separate_is_total_disagreement():
    # Gold: everything in one section. Draft: every field its own section.
    pairs = _pairs(("A", "1"), ("A", "2"), ("A", "3"))
    agree, comparable = _grouping(pairs)
    assert comparable == 3  # C(3,2)
    assert agree == 0       # every pair: gold-same vs draft-diff


def test_fields_without_a_gold_section_are_ignored():
    # Only f0,f1 carry a gold section; f2 has None -> excluded entirely, so the
    # single comparable pair is (f0,f1).
    pairs = _pairs(("A", "X"), ("A", "X"), (None, "Y"))
    agree, comparable = _grouping(pairs)
    assert comparable == 1
    assert agree == 1


def test_fewer_than_two_sectioned_fields_is_not_applicable():
    # No pair to compare -> comparable 0 -> _pct yields the n/a sentinel (nan).
    import math
    agree, comparable = _grouping(_pairs(("A", "X")))
    assert (agree, comparable) == (0, 0)
    assert math.isnan(schema_score._pct(agree, comparable))


def test_score_fields_exposes_section_grouping_not_section_id():
    # The integrated score_fields output carries section_grouping (the new metric)
    # and no longer carries the old exact-match section_id attribute.
    truth = [
        {"id": "a", "name": "A", "type": "text", "pdf_field_name": "p.a", "section_id": "S1"},
        {"id": "b", "name": "B", "type": "text", "pdf_field_name": "p.b", "section_id": "S1"},
    ]
    draft = [
        {"id": "a2", "name": "A", "type": "text", "pdf_field_name": "p.a", "section_id": "whatever_1"},
        {"id": "b2", "name": "B", "type": "text", "pdf_field_name": "p.b", "section_id": "whatever_1"},
    ]
    match = schema_score.match_fields(truth, draft)
    result = schema_score.score_fields(match)
    attrs = result["attributes"]
    assert "section_grouping" in attrs
    assert "section_id" not in attrs
    # Both fields share a section in gold AND in draft -> the one pair agrees.
    assert attrs["section_grouping"]["pct"] == 100.0
