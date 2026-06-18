"""Tests for the section-GROUPING metric in scripts/schema_score.py
(bd polyglot-pdf-7a9.13).

Exact section_id string matching was a broken quality signal (the I-90 gold ids
are inconsistent hand-authored noise, so every extractor scored 0%). The decision
(option b) replaced it with PAIRWISE CO-MEMBERSHIP F1 over matched fields: of the
field-pairs the gold groups into the same section, how many does the draft also
group (recall), and of the pairs the draft groups, how many are real (precision)?
Naming-independent. NOT the Rand index -- that was rejected because it credits
cross-section true negatives, inflating a no-section draft (Codex PR #235). These
tests pin that behavior -- naming-independence AND the no-inflation property.

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


import math


def test_perfect_grouping_scores_f1_100():
    # Two sections, two fields each; draft mirrors the gold partition exactly.
    # true pairs (gold-same): (f0,f1),(f2,f3) = 2; predicted-same: same 2; all hit.
    r = _grouping(_pairs(("A", "X"), ("A", "X"), ("B", "Y"), ("B", "Y")))
    assert r["true_pairs"] == 2
    assert r["predicted_pairs"] == 2
    assert r["agree_pairs"] == 2
    assert r["precision"] == 1.0 and r["recall"] == 1.0 and r["f1"] == 1.0


def test_naming_is_irrelevant_only_grouping_matters():
    # Draft uses COMPLETELY different section names but the SAME partition -> F1 1.
    r = _grouping(_pairs(("Part 1 - Information About You", "part_1_info"),
                         ("Part 1 - Information About You", "part_1_info"),
                         ("part_6_interpreter", "Part 6 - Interpreter"),
                         ("part_6_interpreter", "Part 6 - Interpreter")))
    assert r["f1"] == 1.0


def test_wrong_grouping_is_penalized():
    # Gold: {f0,f1},{f2,f3}. Draft sections: f0=X f1=Y f2=Y f3=Z.
    # true pairs (gold-same): (f0,f1),(f2,f3) = 2. predicted (draft-same): (f1,f2) = 1.
    # overlap (gold-same AND draft-same): none -> agree 0 -> recall 0, prec 0, F1 0.
    r = _grouping(_pairs(("A", "X"), ("A", "Y"), ("B", "Y"), ("B", "Z")))
    assert r["true_pairs"] == 2
    assert r["predicted_pairs"] == 1
    assert r["agree_pairs"] == 0
    assert r["f1"] == 0.0


def test_partial_grouping_scores_between():
    # Gold: {f0,f1,f2} all together (3 true pairs). Draft groups f0,f1 only (X)
    # and f2 alone (Y): predicted-same = (f0,f1) = 1; overlap = 1.
    # recall = 1/3, precision = 1/1 -> F1 = 2*(1*1/3)/(1+1/3) = 0.5.
    r = _grouping(_pairs(("A", "X"), ("A", "X"), ("A", "Y")))
    assert r["true_pairs"] == 3
    assert r["predicted_pairs"] == 1
    assert r["agree_pairs"] == 1
    assert r["recall"] == 1 / 3
    assert r["precision"] == 1.0
    assert math.isclose(r["f1"], 0.5)


def test_over_grouping_hurts_precision():
    # Gold separates everything (0 true pairs); draft lumps all 3 into one section.
    # predicted-same = 3, overlap = 0 -> precision 0, recall n/a (no true pairs)
    # -> F1 0 (a draft that invents groupings the gold doesn't have is wrong).
    r = _grouping(_pairs(("A", "X"), ("B", "X"), ("C", "X")))
    assert r["true_pairs"] == 0
    assert r["predicted_pairs"] == 3
    assert r["f1"] == 0.0


def test_fields_without_a_gold_section_are_ignored():
    # Only f0,f1 carry a gold section; f2 has None -> excluded entirely.
    r = _grouping(_pairs(("A", "X"), ("A", "X"), (None, "Y")))
    assert r["true_pairs"] == 1
    assert r["agree_pairs"] == 1
    assert r["f1"] == 1.0


def test_unsectioned_draft_scores_f1_zero_not_inflated():
    # Codex PR #235: a draft that emits NO sections must score F1 0, NOT be
    # inflated by cross-section true-negative pairs (the Rand-index flaw). Gold has
    # MANY sections; draft none -> 0 predicted pairs -> recall 0 -> F1 0.
    r = _grouping(_pairs(("A", None), ("A", None), ("B", None), ("B", None),
                         ("C", None), ("C", None)))
    assert r["true_pairs"] == 3       # one per 2-field section
    assert r["predicted_pairs"] == 0  # singletons -> no co-membership predicted
    assert r["f1"] == 0.0


def test_unsectioned_draft_single_section_gold_is_f1_zero():
    # Gold lumps all 3 together; draft groups none -> recall 0 -> F1 0.
    r = _grouping(_pairs(("A", None), ("A", None), ("A", None)))
    assert r["true_pairs"] == 3
    assert r["predicted_pairs"] == 0
    assert r["f1"] == 0.0


def test_two_unsectioned_draft_fields_are_distinct_not_grouped():
    # Even two empty-string draft sections are NOT co-membered -> 0 predicted.
    r = _grouping(_pairs(("A", ""), ("A", "")))
    assert r["true_pairs"] == 1
    assert r["predicted_pairs"] == 0
    assert r["f1"] == 0.0


def test_no_true_and_no_predicted_pairs_is_not_applicable():
    # A single gold-sectioned field: no pairs at all on either side -> n/a (nan).
    r = _grouping(_pairs(("A", "X")))
    assert r["true_pairs"] == 0
    assert r["predicted_pairs"] == 0
    assert math.isnan(r["f1"])


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
    # Both fields share a section in gold AND in draft -> F1 100%.
    assert attrs["section_grouping"]["pct"] == 100.0
    assert attrs["section_grouping"]["f1"] == 1.0


def test_over_grouping_penalty_is_applicable_to_the_headline():
    # Codex PR #235 r2: when the gold separates fields (no true pairs) but the
    # draft lumps them together, F1 is 0 -- and `applicable` MUST be > 0 so the
    # bake-off headline (_attr_avg drops falsy-applicable attrs) actually counts
    # the penalty instead of silently ignoring a wholly-wrong grouping.
    truth = [
        {"id": "a", "name": "A", "type": "text", "pdf_field_name": "p.a", "section_id": "S1"},
        {"id": "b", "name": "B", "type": "text", "pdf_field_name": "p.b", "section_id": "S2"},
    ]
    draft = [  # draft wrongly lumps both into one section
        {"id": "a2", "name": "A", "type": "text", "pdf_field_name": "p.a", "section_id": "X"},
        {"id": "b2", "name": "B", "type": "text", "pdf_field_name": "p.b", "section_id": "X"},
    ]
    match = schema_score.match_fields(truth, draft)
    sg = schema_score.score_fields(match)["attributes"]["section_grouping"]
    assert sg["pct"] == 0.0          # wholly wrong grouping
    assert sg["applicable"] > 0       # ...and it COUNTS toward the headline
    # _attr_avg's own filter would now include it (truthy applicable + non-nan pct).
    assert sg["applicable"] and sg["pct"] == sg["pct"]
