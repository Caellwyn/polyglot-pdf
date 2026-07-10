"""Tests for v2-dialect reconciliation in scripts/schema_score.py
(bd polyglot-pdf-d9lz).

After the v1->v2 gold migration (bd polyglot-pdf-h76m.15), the scorer had two
v1-isms that corrupted bake-off scores for any arm run against the v2 contract:

1. _opts_match keyed options on value-FIRST. v2 option `value` is a semantic slug
   ('new_application') the extractor derives from the label, so two correct
   extractions -- or the independently-slugged gold -- can carry different slugs
   for the same option and score as a MISMATCH. The label is the dialect-stable
   key.
2. rel_keys included 'conditional_fields', a v1-legacy key that is NOT a v2
   FormField model field and is not advertised by the v2 contract, so a v2 arm
   could never emit it (0-recall noise). It also MISSED 'require_if', a live v2
   target-side relationship key.

Load pattern mirrors tests/test_schema_score_section_grouping.py (load the script
as a module without running its CLI main()).
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

_opts_match = schema_score._opts_match


def _field(options):
    return {"options": options}


def test_opts_match_on_label_despite_divergent_slugs():
    """The v2 regression: gold and draft carry the SAME labels but DIFFERENT
    semantic slugs for the same options. Value-first keying scored this as a
    mismatch; label-first must score it a match."""
    truth = _field([
        {"value": "yes_proceed_to_item_numbers_5_a_5_c",
         "label": "Yes (Proceed to Item Numbers 5.a. - 5.c.)"},
        {"value": "no_proceed_to_item_numbers_6_a_6_c",
         "label": "No (Proceed to Item Numbers 6.a. - 6.c.)"},
    ])
    # A correct extraction with its OWN slugging of the identical labels.
    draft = _field([
        {"value": "yes", "label": "Yes (Proceed to Item Numbers 5.a. - 5.c.)"},
        {"value": "no", "label": "No (Proceed to Item Numbers 6.a. - 6.c.)"},
    ])
    assert _opts_match(truth, draft) is True


def test_opts_match_still_penalizes_wrong_labels():
    """Label-first must not become a free pass: genuinely different option
    labels still fail the Jaccard>=0.8 bar."""
    truth = _field([
        {"value": "a", "label": "Married"},
        {"value": "b", "label": "Single"},
        {"value": "c", "label": "Divorced"},
    ])
    draft = _field([
        {"value": "a", "label": "Married"},
        {"value": "x", "label": "Employed"},
        {"value": "y", "label": "Student"},
    ])
    assert _opts_match(truth, draft) is False


def test_opts_match_falls_back_to_value_when_no_label():
    """Bare-value options (no label) must still match on value -- the fallback
    half of label-first keying, so v1-style value-only fixtures still work."""
    truth = _field([{"value": "x"}, {"value": "y"}])
    draft = _field([{"value": "x"}, {"value": "y"}])
    assert _opts_match(truth, draft) is True


def test_opts_match_empty_truth_is_vacuous_pass():
    """A field with no options to recover scores True (nothing to recover) --
    unchanged behavior, guards the refactor did not break the short-circuit."""
    assert _opts_match(_field([]), _field([{"value": "x", "label": "X"}])) is True


def test_rel_keys_reflect_v2_vocabulary():
    """score_relationships must count require_if (live v2 key) and NOT
    conditional_fields (dead v1 key). Drive a minimal scored run and inspect the
    reported conditional buckets."""
    truth = {
        "fields": [
            {"id": "f1", "show_if": {"field": "x", "operator": "equals", "value": "1"}},
            {"id": "f2", "require_if": {"field": "y", "operator": "equals", "value": "2"}},
        ]
    }
    draft = {
        "fields": [
            {"id": "f1", "show_if": {"field": "x", "operator": "equals", "value": "1"}},
            {"id": "f2", "require_if": {"field": "y", "operator": "equals", "value": "2"}},
        ]
    }
    # Build a MatchResult pairing f1<->f1, f2<->f2 (id-equal here for simplicity).
    match = schema_score.MatchResult(
        pairs=[(truth["fields"][0], draft["fields"][0]),
               (truth["fields"][1], draft["fields"][1])],
        unmatched_truth=[],
        unmatched_draft=[],
    )
    result = schema_score.score_relationships(truth, draft, match)
    conds = result["conditionals"]
    assert "require_if" in conds
    # BOTH v1-legacy trigger-side keys must be gone (deleted from the v2 model,
    # lint-ERRORed, 0/0 across every v2 gold kit) -- grading them is dead-bucket
    # noise. conditional_fields AND controls_fields.
    assert "conditional_fields" not in conds
    assert "controls_fields" not in conds
    # require_if recall recovered (1 present in gold, 1 recovered in draft).
    assert conds["require_if"]["recovered"] == 1
    assert conds["require_if"]["total"] == 1
    # show_if likewise recovered -- the pre-existing key still works.
    assert conds["show_if"]["recovered"] == 1
