"""Tests for the post-LLM schema repair pass (bd polyglot-pdf-h76m.13, P5.2).

Exit criteria pinned here:
1. The replayed broken W-7 output repairs to lint-ERROR-free and >= 95%
   choice fill on roundtrip (against the real w7 PDF).
2. An unknown operator is NEVER emitted -- the condition is dropped with a
   recorded ERROR (fail-open: the field stays visible).

Plus: the alias table's observed shapes (is_selected, contains_any, the
or-pseudo-group with option_id, contains-on-group compat), slug minting with
reference resolution, idempotency, hallucinated-widget loudness, and the
P5.1 ablation fixture (the candidates-on draft) repairing clean.

Imports the backend core directly; roundtrip_fill from scripts/bakeoff.
ASCII only.
"""

import copy
import json
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))

from backend.services.schema_lint import has_errors, lint_schema  # noqa: E402
from backend.services.schema_repair import (  # noqa: E402
    RepairError, alias_hit_count, repair,
)

_FIXTURES = _REPO / "backend" / "tests" / "fixtures"
_W7_PDF = _REPO / "form-kits" / "w7" / "form.pdf"

needs_w7 = pytest.mark.skipif(not _W7_PDF.exists(), reason="w7 kit not present")


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _schema(fields):
    return {"source": "pdf", "fields": fields}


def _v2_schema(fields):
    # schema_lint's legacy-trigger-side-logic rule only fires for a schema
    # CLAIMING v2 (is_v2) -- a v1/draft schema legitimately still carries
    # controls_fields mid-pipeline. These fixtures need that rule to actually
    # be RED going in, so they must be v2-stamped.
    return {"source": "pdf", "schema_version": "2", "fields": fields}


def _group(fid="grp", ftype="checkbox_group", values=("alpha", "beta")):
    return {
        "id": fid, "type": ftype,
        "options": [
            {"value": v, "label": v.title(), "pdf_field_name": f"{v}[0]"}
            for v in values
        ],
    }


# --------------------------------------------------------------------------- #
# Exit criterion 1: the replayed broken W-7 draft.
# --------------------------------------------------------------------------- #

@needs_w7
def test_broken_w7_repairs_to_lint_clean_and_fills(tmp_path):
    draft = _load("w7_broken_draft.json")
    assert has_errors(lint_schema(draft))  # RED going in

    repaired, repairs = repair(draft)
    findings = lint_schema(repaired)
    assert not has_errors(findings), [f"{f.rule} {f.path}" for f in findings[:5]]
    assert alias_hit_count(repairs) > 0  # the invented vocabulary was seen

    import roundtrip_fill
    out = tmp_path / "repaired.json"
    out.write_text(json.dumps(repaired), encoding="utf-8")
    rt = roundtrip_fill.run(str(out), str(_W7_PDF))
    choice = rt["choice_fill_success"]
    assert choice["pct"] is not None and choice["pct"] >= 95.0, choice


def test_candidates_on_ablation_draft_repairs_clean():
    # The P5.1 fixture: consolidated group, values collapsed to "1", invented
    # `or` pseudo-groups with option_id widget paths. Repair mints slugs and
    # rewrites the conditions via option_id resolution.
    draft = _load("w7_candidates_on_draft.json")
    assert has_errors(lint_schema(draft))
    repaired, repairs = repair(draft)
    assert not has_errors(lint_schema(repaired))
    # The group's options got distinct slugs.
    group = next(f for f in repaired["fields"]
                 if f.get("id") == "reason_for_submission")
    values = [o["value"] for o in group["options"]]
    assert len(set(values)) == len(values) == 8


def test_repair_is_idempotent_on_both_fixtures():
    for name in ("w7_broken_draft.json", "w7_candidates_on_draft.json"):
        once, _ = repair(_load(name))
        twice, second_repairs = repair(once)
        assert twice == once, name
        substantive = [r for r in second_repairs
                       if r["action"] != "alias-hit-rate"]
        assert substantive == [], name


# --------------------------------------------------------------------------- #
# Exit criterion 2: unknown operators are dropped, never emitted.
# --------------------------------------------------------------------------- #

def test_unknown_operator_is_dropped_with_recorded_error():
    fields = [
        _group(),
        {"id": "dep", "type": "text",
         "show_if": {"field": "grp", "operator": "sparkles", "value": "alpha"}},
    ]
    repaired, repairs = repair(_schema(fields))
    dep = next(f for f in repaired["fields"] if f["id"] == "dep")
    assert "show_if" not in dep  # dropped -> field stays visible (fail-open)
    drops = [r for r in repairs if r["action"] == "drop-condition"]
    assert len(drops) == 1 and drops[0]["error"] is True
    assert "sparkles" in drops[0]["detail"]
    # And the repaired schema lints clean -- the unknown operator was not
    # emitted anywhere.
    assert not has_errors(lint_schema(repaired))


def test_unresolvable_value_drops_the_condition():
    fields = [
        _group(),
        {"id": "dep", "type": "text",
         "show_if": {"field": "grp", "operator": "includes", "value": "ghost"}},
    ]
    repaired, repairs = repair(_schema(fields))
    dep = next(f for f in repaired["fields"] if f["id"] == "dep")
    assert "show_if" not in dep
    assert any(r["action"] == "drop-condition" and r["error"] for r in repairs)


# --------------------------------------------------------------------------- #
# The alias table's observed shapes.
# --------------------------------------------------------------------------- #

def test_is_selected_aliases_to_registry_valid_membership():
    # checkbox_group trigger -> includes; v1 checkbox-with-options trigger ->
    # equals (the registry forbids includes there; the evaluator's array
    # branch gives equals membership semantics).
    for ftype, expected in (("checkbox_group", "includes"), ("checkbox", "equals")):
        fields = [
            _group(ftype=ftype),
            {"id": "dep", "type": "text",
             "show_if": {"field": "grp", "operator": "is_selected",
                         "value": "alpha"}},
        ]
        repaired, repairs = repair(_schema(fields))
        dep = next(f for f in repaired["fields"] if f["id"] == "dep")
        assert dep["show_if"]["operator"] == expected, ftype
        assert not has_errors(lint_schema(repaired)), ftype


def test_contains_any_becomes_any_of_membership():
    fields = [
        _group(),
        {"id": "dep", "type": "text",
         "show_if": {"field": "grp", "operator": "contains_any",
                     "value": ["alpha[0]", "beta[0]"]}},  # widget-leaf values
    ]
    repaired, _ = repair(_schema(fields))
    dep = next(f for f in repaired["fields"] if f["id"] == "dep")
    group = dep["show_if"]
    assert set(group.keys()) == {"any_of"}
    assert [a["value"] for a in group["any_of"]] == ["alpha", "beta"]  # resolved
    assert all(a["operator"] == "includes" for a in group["any_of"])
    assert not has_errors(lint_schema(repaired))


def test_or_pseudo_group_with_option_id_resolves():
    # The P5.1-observed invention: {operator: or, conditions: [{... equals,
    # value: "1", option_id: <widget path>}]}.
    fields = [
        _group(ftype="radio"),
        {"id": "dep", "type": "text",
         "show_if": {"operator": "or", "conditions": [
             {"field": "grp", "operator": "equals", "value": "1",
              "option_id": "top[0].alpha[0]"},
             {"field": "grp", "operator": "equals", "value": "1",
              "option_id": "top[0].beta[0]"},
         ]}},
    ]
    repaired, _ = repair(_schema(fields))
    dep = next(f for f in repaired["fields"] if f["id"] == "dep")
    group = dep["show_if"]
    assert set(group.keys()) == {"any_of"}
    assert [a["value"] for a in group["any_of"]] == ["alpha", "beta"]
    assert all("option_id" not in a for a in group["any_of"])
    assert not has_errors(lint_schema(repaired))


def test_unresolvable_option_id_drops_instead_of_guessing_via_value():
    """Fresh-eyes round 2 (bd furs): option_id is authoritative when present.
    An unresolvable option_id must DROP the condition -- falling back to the
    value could coincidentally match a DIFFERENT option's slug and silently
    rewire the condition."""
    fields = [
        _group(ftype="radio"),
        {"id": "dep", "type": "text",
         "show_if": {"operator": "or", "conditions": [
             # option_id names a widget that is not one of grp's options,
             # while value happens to equal a VALID sibling slug.
             {"field": "grp", "operator": "equals", "value": "beta",
              "option_id": "top[0].ghost[0]"},
         ]}},
    ]
    repaired, repairs = repair(_schema(fields))
    dep = next(f for f in repaired["fields"] if f["id"] == "dep")
    assert "show_if" not in dep  # dropped, never guessed
    drops = [r for r in repairs if r["action"] == "drop-condition"]
    assert len(drops) == 1 and drops[0]["error"] is True
    assert "ghost" in drops[0]["detail"]


def test_contains_on_group_trigger_gets_membership_reading():
    fields = [
        _group(ftype="checkbox"),
        {"id": "dep", "type": "text",
         "show_if": {"field": "grp", "operator": "contains", "value": "alpha"}},
    ]
    repaired, _ = repair(_schema(fields))
    dep = next(f for f in repaired["fields"] if f["id"] == "dep")
    assert dep["show_if"]["operator"] == "equals"  # registry-valid membership
    assert not has_errors(lint_schema(repaired))


# --------------------------------------------------------------------------- #
# Slug minting.
# --------------------------------------------------------------------------- #

def test_slug_minting_rewrites_conditional_references():
    fields = [
        {"id": "grp", "type": "checkbox_group", "options": [
            {"value": "1", "label": "First Reason", "pdf_field_name": "c1[0]"},
            {"value": "1", "label": "Second Reason", "pdf_field_name": "c2[0]"},
        ]},
        {"id": "dep", "type": "text",
         "show_if": {"field": "grp", "operator": "includes", "value": "c2[0]"}},
    ]
    repaired, repairs = repair(_schema(fields))
    group = next(f for f in repaired["fields"] if f["id"] == "grp")
    assert [o["value"] for o in group["options"]] == ["first_reason", "second_reason"]
    dep = next(f for f in repaired["fields"] if f["id"] == "dep")
    assert dep["show_if"]["value"] == "second_reason"  # leaf -> slug
    assert any(r["action"] == "mint-option-slugs" for r in repairs)
    assert not has_errors(lint_schema(repaired))


def test_colliding_alias_never_mis_resolves():
    """Fresh-eyes finding (PR review): two options sharing an old value ("1",
    the W-7 corruption) must NOT let a condition referencing that value be
    silently rewired to whichever option registered last -- the ambiguous
    reference drops fail-open with a recorded ERROR instead."""
    fields = [
        {"id": "grp", "type": "checkbox_group", "options": [
            {"value": "1", "label": "First Reason", "pdf_field_name": "c1[0]"},
            {"value": "1", "label": "Second Reason", "pdf_field_name": "c2[0]"},
        ]},
        {"id": "dep", "type": "text",
         "show_if": {"field": "grp", "operator": "includes", "value": "1"}},
    ]
    repaired, repairs = repair(_schema(fields))
    dep = next(f for f in repaired["fields"] if f["id"] == "dep")
    assert "show_if" not in dep  # dropped, not guessed
    assert any(r["action"] == "drop-condition" and r["error"] for r in repairs)
    # UNAMBIGUOUS aliases of the same field still resolve (widget leaf).
    fields[1]["show_if"] = {"field": "grp", "operator": "includes",
                            "value": "c2[0]"}
    repaired, _ = repair(_schema(fields))
    dep = next(f for f in repaired["fields"] if f["id"] == "dep")
    assert dep["show_if"]["value"] == "second_reason"


def test_colliding_labels_also_drop_ambiguous_references():
    fields = [
        {"id": "grp", "type": "checkbox_group", "options": [
            {"value": "opt_a", "label": "Other", "pdf_field_name": "c1[0]"},
            {"value": "opt_b", "label": "Other", "pdf_field_name": "c2[0]"},
        ]},
        {"id": "dep", "type": "text",
         "show_if": {"field": "grp", "operator": "includes", "value": "Other"}},
    ]
    repaired, repairs = repair(_schema(fields))
    dep = next(f for f in repaired["fields"] if f["id"] == "dep")
    assert "show_if" not in dep
    assert any(r["action"] == "drop-condition" and r["error"] for r in repairs)


def test_valid_slugs_are_left_alone():
    fields = [_group()]  # values alpha/beta are already valid slugs
    repaired, repairs = repair(_schema(fields))
    assert repaired["fields"][0]["options"][0]["value"] == "alpha"
    assert not any(r["action"] == "mint-option-slugs" for r in repairs)


# --------------------------------------------------------------------------- #
# Hallucinated widgets fail loudly (dump supplied).
# --------------------------------------------------------------------------- #

def test_hallucinated_widget_raises():
    fields = [_group()]
    dump = {"fields": [{"name": "top[0].alpha[0]"}]}  # beta[0] does not exist
    with pytest.raises(RepairError) as exc:
        repair(_schema(fields), dump)
    assert "beta[0]" in str(exc.value)


def test_real_widgets_pass_the_dump_check():
    fields = [_group()]
    dump = {"fields": [{"name": "top[0].alpha[0]"}, {"name": "top[0].beta[0]"}]}
    repaired, _ = repair(_schema(fields), dump)
    assert repaired["fields"][0]["options"][1]["pdf_field_name"] == "beta[0]"


def test_repair_never_mutates_its_input():
    original = _load("w7_broken_draft.json")
    snapshot = copy.deepcopy(original)
    repair(original)
    assert original == snapshot


# --------------------------------------------------------------------------- #
# controls_fields mirroring (bd polyglot-pdf-c3y6): repair() now converts the
# removed trigger-side controls_fields into target-side show_if/require_if,
# using the SAME shared core (backend/services/controls_fields_mirror.py) that
# scripts/migrate_schema_v2.py Pass 4 uses -- the scenarios below are the
# repair-side counterparts of tests/test_migrate_schema_v2.py's Pass-4 cases.
# --------------------------------------------------------------------------- #

def _mirror_repairs(repairs):
    return [r for r in repairs if r["action"] == "mirror-controls-fields"]


def test_shows_edge_mirrored_by_target_show_if_is_a_noop_drop():
    # A `shows` edge whose target ALREADY carries the matching show_if: dropped
    # silently (no re-mirror), and the schema lints clean afterward.
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "no", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "yes",
                             "shows": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]",
              "show_if": {"field": "trg", "operator": "equals", "value": "yes"}}
    draft = _v2_schema([trigger, target])
    assert has_errors(lint_schema(draft))  # RED going in

    repaired, repairs = repair(draft)
    assert "controls_fields" not in repaired["fields"][0]
    assert _mirror_repairs(repairs) == []  # already mirrored -> no-op
    tgt = repaired["fields"][1]
    assert tgt["show_if"] == {"field": "trg", "operator": "equals", "value": "yes"}
    assert not has_errors(lint_schema(repaired))
    assert not any(f.rule == "legacy-trigger-side-logic" for f in lint_schema(repaired))


def test_unmirrored_shows_edge_is_mirrored_into_target_show_if():
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "no", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "yes",
                             "shows": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    draft = _v2_schema([trigger, target])
    assert has_errors(lint_schema(draft))

    repaired, repairs = repair(draft)
    assert "controls_fields" not in repaired["fields"][0]
    tgt = repaired["fields"][1]
    assert tgt["show_if"] == {"field": "trg", "operator": "equals", "value": "yes"}
    assert len(_mirror_repairs(repairs)) == 1
    assert not has_errors(lint_schema(repaired))

    # Compare against migrate_schema_v2's Pass 4 on the SAME input (imported by
    # file path, matching tests/test_migrate_schema_v2.py's own convention).
    mig = _load_migrate_module()
    mig_out, _ = mig.migrate(_v1_equivalent([trigger, target]))
    mig_tgt = {f["id"]: f for f in mig_out["fields"]}["tgt"]
    assert mig_tgt["show_if"] == tgt["show_if"]


def test_unmirrored_makes_required_edge_is_mirrored_into_require_if():
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "no", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "yes",
                             "makes_required": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    draft = _v2_schema([trigger, target])
    assert has_errors(lint_schema(draft))

    repaired, repairs = repair(draft)
    assert "controls_fields" not in repaired["fields"][0]
    assert repaired["fields"][1]["require_if"] == {
        "field": "trg", "operator": "equals", "value": "yes"}
    assert not has_errors(lint_schema(repaired))


def test_show_if_does_not_suppress_a_makes_required_mirror_same_trigger():
    # Key-specific suppression (fresh-eyes r2): a target's pre-existing show_if
    # naming the SAME trigger/value must NOT suppress a makes_required mirror
    # into require_if -- the two buckets are different effects.
    trig = {"id": "reason_d", "type": "checkbox", "pdf_field_name": "R[0]",
            "options": [{"value": "yes", "label": "D", "pdf_field_name": "R[0]"}],
            "controls_fields": [{"operator": "equals", "value": "yes",
                                 "makes_required": ["rel_d"]}]}
    rel_d = {"id": "rel_d", "type": "text", "pdf_field_name": "T[0]",
             "show_if": {"field": "reason_d", "operator": "equals", "value": "yes"}}
    draft = _v2_schema([trig, rel_d])
    repaired, repairs = repair(draft)
    t = {f["id"]: f for f in repaired["fields"]}["rel_d"]
    # The pre-existing show_if is NOT touched by the controls_fields-specific
    # standalone fixup (that fixup only normalizes the MIRRORED atom); equals
    # is registry-valid on a checkbox trigger so repair's generic atom rewrite
    # leaves it as-is.
    assert t["show_if"] == {"field": "reason_d", "operator": "equals", "value": "yes"}
    # The MIRRORED require_if (a fresh atom repair had to build from the
    # controls_fields edge) gets the standalone-checkbox idiom fixup applied:
    # the trigger's lone option's raw value has no v2 referent once mirrored.
    assert t["require_if"] == {"field": "reason_d", "operator": "is_checked"}
    assert not has_errors(lint_schema(repaired))


def test_two_triggers_requiring_one_target_merge_into_any_of():
    a = {"id": "a", "type": "checkbox", "pdf_field_name": "A[0]", "options": [
        {"value": "yes", "label": "Reason A", "pdf_field_name": "A[0]"}],
        "controls_fields": [{"operator": "is_checked", "makes_required": ["tc"]}]}
    f2 = {"id": "f2", "type": "checkbox", "pdf_field_name": "F[0]", "options": [
        {"value": "yes", "label": "Reason F", "pdf_field_name": "F[0]"}],
        "controls_fields": [{"operator": "is_checked", "makes_required": ["tc"]}]}
    tc = {"id": "tc", "type": "text", "pdf_field_name": "TC[0]"}
    draft = _v2_schema([a, f2, tc])
    repaired, _ = repair(draft)
    req = repaired["fields"][2]["require_if"]
    assert "any_of" in req and len(req["any_of"]) == 2
    assert {atom["field"] for atom in req["any_of"]} == {"a", "f2"}
    assert not has_errors(lint_schema(repaired))


def test_unconvertible_action_is_reported_not_silently_lost():
    # unlocks/locks/hides/makes_optional have no v2 target-side equivalent;
    # controls_fields is still removed and the schema still lints clean (the
    # legacy-trigger-side-logic rule is satisfied by the key's removal; a
    # human still needs to review the reported unconverted action).
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "no", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "yes",
                             "unlocks": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    draft = _v2_schema([trigger, target])
    repaired, repairs = repair(draft)
    assert "controls_fields" not in repaired["fields"][0]
    assert "show_if" not in repaired["fields"][1]
    assert "require_if" not in repaired["fields"][1]
    unconv = [r for r in repairs if r["action"] == "controls-fields-unmirrored"]
    assert len(unconv) == 1
    assert "unlocks" in unconv[0]["detail"] and "tgt" in unconv[0]["detail"]
    assert not has_errors(lint_schema(repaired))


def test_dangling_shows_target_is_reported_not_dropped_silently():
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "no", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "yes",
                             "makes_required": ["ghost_field"]}]}
    draft = _v2_schema([trigger])
    repaired, repairs = repair(draft)
    assert "controls_fields" not in repaired["fields"][0]
    dangling = [r for r in repairs if r["action"] == "controls-fields-dangling"]
    assert len(dangling) == 1
    assert "ghost_field" in dangling[0]["detail"]
    assert not has_errors(lint_schema(repaired))


def test_conditional_fields_is_dropped_and_logged():
    fields = [
        {"id": "f", "type": "text", "pdf_field_name": "F[0]",
         "conditional_fields": ["a", "b"]},
    ]
    draft = _v2_schema(fields)
    repaired, repairs = repair(draft)
    assert "conditional_fields" not in repaired["fields"][0]
    assert any(r["action"] == "drop-conditional-fields" for r in repairs)
    assert not has_errors(lint_schema(repaired))


def test_controls_fields_mirroring_is_idempotent():
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "no", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "yes",
                             "shows": ["tgt"], "makes_required": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    draft = _v2_schema([trigger, target])
    once, _ = repair(draft)
    twice, repairs2 = repair(once)
    assert twice == once
    substantive = [r for r in repairs2 if r["action"] not in ("alias-hit-rate",)]
    assert substantive == []


def test_controls_fields_atom_routed_through_repairs_own_slug_resolution():
    # The mirrored atom must get the SAME alias/slug rewriting every other
    # repaired atom gets: an is_selected-invented operator on the trigger AND
    # a stale option-value reference in the controls_fields edge both resolve
    # via repair's OWN machinery, not a bespoke path.
    trigger = {
        "id": "grp", "type": "checkbox_group",
        "options": [
            {"value": "1", "label": "First Reason", "pdf_field_name": "c1[0]"},
            {"value": "1", "label": "Second Reason", "pdf_field_name": "c2[0]"},
        ],
        "controls_fields": [{"operator": "is_selected", "value": "c2[0]",
                             "shows": ["dep"]}],
    }
    dep = {"id": "dep", "type": "text", "pdf_field_name": "D[0]"}
    draft = _v2_schema([trigger, dep])
    repaired, repairs = repair(draft)
    dep_out = next(f for f in repaired["fields"] if f["id"] == "dep")
    # is_selected -> includes (checkbox_group trigger); c2[0] (widget leaf) ->
    # its minted slug second_reason -- the exact resolution _mint_slugs +
    # _rewrite_atom give every other repaired condition.
    assert dep_out["show_if"] == {
        "field": "grp", "operator": "includes", "value": "second_reason"}
    assert not has_errors(lint_schema(repaired))


def test_already_mirrored_suppression_with_trigger_before_raw_target():
    # Fresh-eyes finding (bd c3y6): mirroring must run AFTER the show_if/
    # require_if rewrite pass has normalized ALL fields (migrate's Pass 2 ->
    # Pass 4 ordering). A fused single loop compared the normalized mirrored
    # atom against the target's RAW, not-yet-rewritten condition whenever the
    # trigger preceded its target in field order -- missing the match and
    # duplicating the edge into a spurious {any_of: [X, X]} plus a misleading
    # mirror-controls-fields audit entry. Here the target's pre-existing
    # show_if uses the invented is_selected operator that only becomes equal
    # to the mirrored atom after repair's own aliasing.
    trigger = {
        "id": "grp", "type": "checkbox_group",
        "options": [
            {"value": "alpha", "label": "Alpha", "pdf_field_name": "a[0]"},
            {"value": "beta", "label": "Beta", "pdf_field_name": "b[0]"},
        ],
        "controls_fields": [{"operator": "includes", "value": "alpha",
                             "shows": ["dep"]}],
    }
    dep = {"id": "dep", "type": "text", "pdf_field_name": "D[0]",
           "show_if": {"field": "grp", "operator": "is_selected",
                       "value": "alpha"}}
    draft = _v2_schema([trigger, dep])  # trigger BEFORE target: the bad order
    repaired, repairs = repair(draft)

    dep_out = next(f for f in repaired["fields"] if f["id"] == "dep")
    # The normalized pre-existing condition IS the mirrored edge: stays a
    # single atom, never wrapped into an any_of duplicate.
    assert dep_out["show_if"] == {
        "field": "grp", "operator": "includes", "value": "alpha"}
    assert _mirror_repairs(repairs) == []  # suppressed, no spurious entry
    assert not has_errors(lint_schema(repaired))


def _load_migrate_module():
    import importlib.util
    path = _REPO / "scripts" / "migrate_schema_v2.py"
    spec = importlib.util.spec_from_file_location("migrate_schema_v2_x", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["migrate_schema_v2_x"] = mod
    spec.loader.exec_module(mod)
    return mod


def _v1_equivalent(fields):
    return {"source": "pdf", "form_metadata": {"title": "T", "version": "unknown"},
            "sections": [], "fields": copy.deepcopy(fields)}
