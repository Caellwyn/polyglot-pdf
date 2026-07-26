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


# --------------------------------------------------------------------------- #
# Trigger-correctness of condition-shaped keys (bd polyglot-pdf-eprg)
# --------------------------------------------------------------------------- #

def test_trigger_correctness_requires_the_right_resolved_trigger():
    """Presence is not correctness: a recovered show_if only counts
    trigger-correct when its (extractor-invented) trigger id RESOLVES, via the
    field match, to the same truth field the gold condition points at."""
    truth = {"fields": [
        {"id": "trig", "pdf_field_name": "T[0]"},
        {"id": "dep_ok", "pdf_field_name": "A[0]",
         "show_if": {"field": "trig", "operator": "is_checked"}},
        {"id": "dep_wrong", "pdf_field_name": "B[0]",
         "show_if": {"field": "trig", "operator": "is_checked"}},
    ]}
    draft = {"fields": [
        {"id": "x1", "pdf_field_name": "T[0]"},
        # Right trigger (x1 resolves to trig) -- correct.
        {"id": "x2", "pdf_field_name": "A[0]",
         "show_if": {"field": "x1", "operator": "is_checked"}},
        # Wrong trigger (points at itself) -- present but NOT correct.
        {"id": "x3", "pdf_field_name": "B[0]",
         "show_if": {"field": "x2", "operator": "is_checked"}},
    ]}
    match = schema_score.match_fields(truth["fields"], draft["fields"])
    conds = schema_score.score_relationships(truth, draft, match)["conditionals"]
    assert conds["show_if"]["total"] == 2
    assert conds["show_if"]["recovered"] == 2       # both PRESENT
    assert conds["show_if"]["trigger_correct"] == 1  # only one CORRECT
    # Non-condition-shaped keys carry no trigger_correct entry.
    assert "trigger_correct" not in conds["conditional_behavior"]


def test_spurious_relationship_emissions_are_counted():
    """Over-emission accounting (bd kfni outer review): a draft that INVENTS a
    relationship gold does not have -- on a matched field or on an unmatched
    extra field -- must surface in the per-key `spurious` count, because a
    spurious require_if turns an optional field required at runtime."""
    truth = {"fields": [
        {"id": "t1", "pdf_field_name": "A[0]"},          # gold: no relationships
        {"id": "t2", "pdf_field_name": "B[0]",
         "show_if": {"field": "t1", "operator": "is_checked"}},
    ]}
    draft = {"fields": [
        # matched to t1 but carries an invented require_if -> spurious.
        {"id": "d1", "pdf_field_name": "A[0]",
         "require_if": {"field": "d2", "operator": "is_checked"}},
        # matched to t2, show_if legitimately recovered -> NOT spurious.
        {"id": "d2", "pdf_field_name": "B[0]",
         "show_if": {"field": "d1", "operator": "is_checked"}},
        # unmatched extra field carrying show_if -> spurious.
        {"id": "d3", "pdf_field_name": "Z[0]",
         "show_if": {"field": "d1", "operator": "is_checked"}},
    ]}
    match = schema_score.match_fields(truth["fields"], draft["fields"])
    conds = schema_score.score_relationships(truth, draft, match)["conditionals"]
    assert conds["require_if"]["spurious"] == 1
    assert conds["show_if"]["spurious"] == 1   # d3 only; d2's is legitimate
    assert conds["show_if"]["recovered"] == 1  # recall unaffected


def test_trigger_correctness_handles_combinator_trees():
    """all_of/any_of trees flatten to their atom triggers; the full resolved
    trigger SET must match."""
    truth = {"fields": [
        {"id": "t1", "pdf_field_name": "T1[0]"},
        {"id": "t2", "pdf_field_name": "T2[0]"},
        {"id": "dep", "pdf_field_name": "D[0]",
         "show_if": {"all_of": [
             {"field": "t1", "operator": "is_checked"},
             {"field": "t2", "operator": "is_checked"}]}},
    ]}
    draft = {"fields": [
        {"id": "a", "pdf_field_name": "T1[0]"},
        {"id": "b", "pdf_field_name": "T2[0]"},
        {"id": "c", "pdf_field_name": "D[0]",
         "show_if": {"all_of": [
             {"field": "a", "operator": "is_checked"},
             {"field": "b", "operator": "is_checked"}]}},
    ]}
    match = schema_score.match_fields(truth["fields"], draft["fields"])
    conds = schema_score.score_relationships(truth, draft, match)["conditionals"]
    assert conds["show_if"]["trigger_correct"] == 1


# --------------------------------------------------------------------------- #
# Trigger-side harvest-residue accounting (bd polyglot-pdf-eprg)
# --------------------------------------------------------------------------- #

def _rels(truth, draft):
    match = schema_score.MatchResult(
        pairs=[], unmatched_truth=truth["fields"],
        unmatched_draft=draft["fields"])
    return schema_score.score_relationships(truth, draft, match)


def test_trigger_action_vocab_stays_in_sync_with_the_mirror_contract():
    """schema_score stays standalone (no backend import), so its local copy of
    the trigger-side action vocabulary must be pinned against the real contract
    in backend/services/controls_fields_mirror.py -- if the R4 harvest bead
    (polyglot-pdf-xbfm) moves an action between the mirrorable and
    unconvertible sets, this test forces the scorer's copy to follow."""
    from backend.services import controls_fields_mirror as cfm

    assert set(schema_score._TRIGGER_ACTIONS) == set(cfm.ACTION_KEYS)
    assert (set(schema_score._TRIGGER_MIRRORABLE)
            == {k for k, _ in cfm.MIRRORABLE_ACTIONS})
    assert (set(schema_score._TRIGGER_UNCONVERTIBLE)
            == set(cfm.UNCONVERTIBLE_ACTIONS))


def test_trigger_side_residue_counts_unharvested_edges():
    """A draft still carrying legacy trigger-side keys after the harvest is
    residue -- counted per action kind, split mirrorable vs unconvertible,
    never silently ignored."""
    truth = {"fields": [{"id": "t1"}]}
    draft = {"fields": [
        {"id": "d1", "controls_fields": [
            {"field": "x", "operator": "is_checked",
             "shows": ["a", "b"], "hides": ["c"], "locks": ["d"]}]},
        {"id": "d2", "conditional_fields": ["e"]},
    ]}
    t = _rels(truth, draft)["trigger_side_residue"]
    assert t["mirrorable"] == 2      # shows: a, b
    assert t["unconvertible"] == 2   # hides: c; locks: d
    assert t["total"] == 4
    assert t["per_action"]["shows"] == 2
    assert t["per_action"]["hides"] == 1
    assert t["per_action"]["locks"] == 1
    assert t["per_action"]["makes_required"] == 0
    assert t["fields_with_trigger_keys"] == 1
    assert t["legacy_conditional_fields"] == 1


def test_trigger_side_residue_zero_on_a_clean_v2_draft():
    truth = {"fields": [{"id": "t1"}]}
    draft = {"fields": [
        {"id": "d1", "show_if": {"field": "x", "operator": "is_checked"}}]}
    t = _rels(truth, draft)["trigger_side_residue"]
    assert t["total"] == 0
    assert t["mirrorable"] == 0 and t["unconvertible"] == 0
    assert t["fields_with_trigger_keys"] == 0
    assert t["legacy_conditional_fields"] == 0


def test_render_report_names_the_trigger_residue():
    """The human-readable report must surface residue when present and say
    'none' when clean -- residue is the zero-silent-drops audit line."""
    truth = {"fields": [{"id": "t1"}]}
    dirty = {"fields": [{"id": "d1", "controls_fields": [
        {"field": "x", "shows": ["a"], "unlocks": ["b"]}]}]}
    clean = {"fields": [{"id": "d1"}]}

    b_dirty = _rels(truth, dirty)
    a_stub = {"detection": {"precision": float("nan"), "recall": float("nan"),
                            "f1": float("nan"), "true_positive": 0,
                            "false_negative": 0, "false_positive": 0},
              "attributes": {}}
    report = schema_score.render_report("x", a_stub, b_dirty)
    assert "trigger-side residue" in report
    assert "unconvertible 1" in report and "shows=1" in report

    b_clean = _rels(truth, clean)
    report_clean = schema_score.render_report("x", a_stub, b_clean)
    assert "trigger-side residue: none" in report_clean
