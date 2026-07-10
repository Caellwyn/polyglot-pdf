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
    # Both spellings land on `includes`: a checkbox_group trigger directly,
    # and a v1 checkbox-with-options trigger via the shape normalization
    # (bd polyglot-pdf-n3mn) -- it retypes to checkbox_group FIRST (migrate
    # Pass 1 parity; a checkbox with options fails FormSchema outright), so
    # the alias sees the final group type. (Before the normalization, repair
    # left the v1 type in place and had to pick `equals`, the only
    # registry-valid reading on a bare checkbox.)
    for ftype in ("checkbox_group", "checkbox"):
        fields = [
            _group(ftype=ftype),
            {"id": "dep", "type": "text",
             "show_if": {"field": "grp", "operator": "is_selected",
                         "value": "alpha"}},
        ]
        repaired, repairs = repair(_schema(fields))
        grp = next(f for f in repaired["fields"] if f["id"] == "grp")
        assert grp["type"] == "checkbox_group", ftype  # normalized shape
        dep = next(f for f in repaired["fields"] if f["id"] == "dep")
        assert dep["show_if"]["operator"] == "includes", ftype
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
    # The v1 checkbox-with-options trigger retypes to checkbox_group first
    # (shape normalization, bd polyglot-pdf-n3mn), so the membership reading
    # is the group's canonical `includes` (was `equals` when the v1 type was
    # left in place).
    assert dep["show_if"]["operator"] == "includes"
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
    # The shape normalization (bd polyglot-pdf-n3mn) unwraps the lone-option
    # checkbox and retargets the pre-existing `equals yes` to the standalone
    # is_checked idiom -- the value vanished with the unwrap (migrate Pass 2
    # parity; both buckets now carry the SAME canonical representation, the
    # exact two-representations wart the c3y6 outer review noted).
    assert t["show_if"] == {"field": "reason_d", "operator": "is_checked"}
    # ...and the makes_required mirror is still NOT suppressed by the
    # matching show_if (key-specific suppression): require_if gets its own
    # is_checked atom.
    assert t["require_if"] == {"field": "reason_d", "operator": "is_checked"}
    trig_out = {f["id"]: f for f in repaired["fields"]}["reason_d"]
    assert "options" not in trig_out  # unwrapped standalone boolean
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


def test_equals_on_group_controls_edge_mirrors_as_membership_like_migrate():
    # Opus review gap (bd c3y6): an equals/not_equals controls_fields edge on
    # a checkbox_group trigger is the v1 membership idiom -- migrate Pass 4
    # aliases it (equals -> includes, not_equals -> not_includes) and mirrors;
    # repair's generic trigger-compat pass would instead fail-open DROP it,
    # losing the dependency. The mirroring path now applies the migration's
    # v1 reading before normalization (native v2 show_if atoms keep the
    # stricter drop policy).
    trigger = {
        "id": "grp", "type": "checkbox_group",
        "options": [
            {"value": "alpha", "label": "Alpha", "pdf_field_name": "a[0]"},
            {"value": "beta", "label": "Beta", "pdf_field_name": "b[0]"},
        ],
        "controls_fields": [
            {"operator": "equals", "value": "alpha", "shows": ["dep"]},
            {"operator": "not_equals", "value": "beta",
             "makes_required": ["dep"]},
        ],
    }
    dep = {"id": "dep", "type": "text", "pdf_field_name": "D[0]"}
    draft = _v2_schema([trigger, dep])
    repaired, repairs = repair(draft)

    dep_out = next(f for f in repaired["fields"] if f["id"] == "dep")
    assert dep_out["show_if"] == {
        "field": "grp", "operator": "includes", "value": "alpha"}
    assert dep_out["require_if"] == {
        "field": "grp", "operator": "not_includes", "value": "beta"}
    assert len(_mirror_repairs(repairs)) == 2
    assert not has_errors(lint_schema(repaired))

    # Evaluator-equivalence: migrate Pass 4 produces the same target
    # conditions for the same input.
    mig = _load_migrate_module()
    mig_out, _ = mig.migrate(_v1_equivalent([trigger, dep]))
    mig_dep = {f["id"]: f for f in mig_out["fields"]}["dep"]
    assert mig_dep["show_if"] == dep_out["show_if"]
    assert mig_dep["require_if"] == dep_out["require_if"]


def test_is_checked_on_group_controls_edge_mirrors_as_is_not_empty():
    # Opus review gap round 2 (bd c3y6): is_checked on an OPTION-BEARING
    # trigger (checkbox_group/radio/select) means "a selection exists" -- the
    # v1 dual-fate rule migrate applies (-> is_not_empty; only a standalone
    # `checkbox` keeps is_checked). Without the rewrite the mirrored atom
    # itself lints operator-trigger RED (i-90 really uses is_checked on radio
    # groups, so this is a shipped shape).
    for gtype in ("checkbox_group", "radio"):
        trigger = {
            "id": "grp", "type": gtype,
            "options": [
                {"value": "alpha", "label": "Alpha", "pdf_field_name": "a[0]"},
                {"value": "beta", "label": "Beta", "pdf_field_name": "b[0]"},
            ],
            "controls_fields": [{"operator": "is_checked", "shows": ["dep"]}],
        }
        dep = {"id": "dep", "type": "text", "pdf_field_name": "D[0]"}
        draft = _v2_schema([trigger, dep])
        repaired, repairs = repair(draft)

        dep_out = next(f for f in repaired["fields"] if f["id"] == "dep")
        assert dep_out["show_if"] == {
            "field": "grp", "operator": "is_not_empty"}, gtype
        assert not has_errors(lint_schema(repaired)), gtype

        # Evaluator-equivalence with migrate Pass 4 on the same input.
        mig = _load_migrate_module()
        mig_out, _ = mig.migrate(_v1_equivalent([trigger, dep]))
        mig_dep = {f["id"]: f for f in mig_out["fields"]}["dep"]
        assert mig_dep["show_if"] == dep_out["show_if"], gtype


def test_empty_value_controls_edge_mirrors_as_emptiness_any_trigger():
    # Opus review gap round 3 (bd c3y6): the v1 emptiness idiom (equals "" /
    # not_equals "" means "field is (not) empty") applies to ANY trigger type
    # in migrate's _rewrite_atom_value -- not just checkbox_group. On a radio
    # trigger repair used to DROP the edge ("" resolves to no option); on a
    # text trigger it kept a semantically different equals "".
    radio = {
        "id": "rad", "type": "radio",
        "options": [
            {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]",
             "pdf_on_value": "Y"},
            {"value": "no", "label": "No", "pdf_field_name": "R[1]",
             "pdf_on_value": "N"},
        ],
        "controls_fields": [{"operator": "equals", "value": "",
                             "shows": ["dep1"]}],
    }
    text = {"id": "txt", "type": "text", "pdf_field_name": "T[0]",
            "controls_fields": [{"operator": "not_equals", "value": "",
                                 "makes_required": ["dep2"]}]}
    dep1 = {"id": "dep1", "type": "text", "pdf_field_name": "D1[0]"}
    dep2 = {"id": "dep2", "type": "text", "pdf_field_name": "D2[0]"}
    draft = _v2_schema([radio, text, dep1, dep2])
    repaired, _ = repair(draft)

    out = {f["id"]: f for f in repaired["fields"]}
    assert out["dep1"]["show_if"] == {"field": "rad", "operator": "is_empty"}
    assert out["dep2"]["require_if"] == {
        "field": "txt", "operator": "is_not_empty"}
    assert not has_errors(lint_schema(repaired))

    # Evaluator-equivalence with migrate Pass 4 on the same input.
    mig = _load_migrate_module()
    mig_out, _ = mig.migrate(_v1_equivalent([radio, text, dep1, dep2]))
    mig_fields = {f["id"]: f for f in mig_out["fields"]}
    assert mig_fields["dep1"]["show_if"] == out["dep1"]["show_if"]
    assert mig_fields["dep2"]["require_if"] == out["dep2"]["require_if"]


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


# --------------------------------------------------------------------------- #
# Strict-model validity fixes (bd polyglot-pdf-n3mn -- surfaced by the 6s71
# paid verification: i-90 invented an overflow_to_supplement value and a
# contract-shaped supplements entry; f1040 emitted 37 lone-option checkboxes).
# --------------------------------------------------------------------------- #

def _validatable(fields, supplements=None):
    """A draft that passes FormSchema.model_validate once its fields do --
    all the schema-level required plumbing filled in."""
    schema = {
        "source": "pdf", "schema_version": "2",
        "form_metadata": {"title": "T", "version": "1"},
        "sections": [{"id": "s1", "label": "S1", "order": 0,
                      "fields": [f["id"] for f in fields]}],
        "fields": copy.deepcopy(fields),
        "extraction_info": {"extracted_at": "2026-07-10T00:00:00Z",
                            "extraction_confidence": 0.9,
                            "extractor_version": "test",
                            "manual_review_required": True},
    }
    for f in schema["fields"]:
        f.setdefault("section_id", "s1")
        f.setdefault("spoken_name", f.get("name", f["id"]))
        f.setdefault("read_only", False)
    if supplements is not None:
        schema["supplements"] = supplements
    return schema


def _model_validates(schema) -> str:
    from backend.models.form_models import FormSchema
    try:
        FormSchema.model_validate(schema)
        return ""
    except Exception as exc:  # noqa: BLE001 -- the message IS the assertion aid
        return str(exc)


def test_invalid_overflow_supplement_string_aliases_to_enum():
    # i-90 emitted 'additional_information' where SupplementType allows only
    # 'supplement_a' -- same intent, invented name. Alias, never drop.
    f = {"id": "t1", "name": "T1", "type": "text", "pdf_field_name": "T[0]",
         "overflow_to_supplement": "additional_information"}
    draft = _validatable([f])
    assert "overflow_to_supplement" in _model_validates(draft)  # RED going in

    repaired, repairs = repair(draft)
    assert repaired["fields"][0]["overflow_to_supplement"] == "supplement_a"
    assert any(r["action"] == "alias-overflow-supplement" for r in repairs)
    assert _model_validates(repaired) == ""


def test_valid_overflow_supplement_untouched_nonstring_dropped():
    ok = {"id": "t1", "name": "T1", "type": "text", "pdf_field_name": "T[0]",
          "overflow_to_supplement": "supplement_a"}
    bad = {"id": "t2", "name": "T2", "type": "text", "pdf_field_name": "T[1]",
           "overflow_to_supplement": {"weird": True}}
    repaired, repairs = repair(_validatable([ok, bad]))
    assert repaired["fields"][0]["overflow_to_supplement"] == "supplement_a"
    assert "overflow_to_supplement" not in repaired["fields"][1]
    acts = [r["action"] for r in repairs]
    assert "drop-overflow-supplement" in acts
    assert "alias-overflow-supplement" not in acts  # the valid one untouched


def test_lone_option_checkbox_unwraps_to_standalone_boolean():
    # f1040's 37x shape: {"value": "1", "pdf_on_value": "1"} single option,
    # no label, on a type=checkbox field -- v2 forbids options on a checkbox
    # entirely, so the unwrap (migrate Pass 1 parity) is the repair, not a
    # synthesized label.
    chk = {"id": "chk", "name": "Filed pursuant to section", "type": "checkbox",
           "options": [{"value": "1", "pdf_on_value": "1",
                        "pdf_field_name": "c[0]"}]}
    dep = {"id": "dep", "name": "Dep", "type": "text", "pdf_field_name": "D[0]",
           "show_if": {"field": "chk", "operator": "equals", "value": "1"}}
    draft = _validatable([chk, dep])
    assert _model_validates(draft) != ""  # RED going in

    repaired, repairs = repair(draft)
    out = {f["id"]: f for f in repaired["fields"]}
    assert "options" not in out["chk"]
    assert out["chk"]["pdf_field_name"] == "c[0]"  # lifted from the option
    # The native condition that referenced the vanished option value moved to
    # the standalone idiom (migrate Pass 2 parity).
    assert out["dep"]["show_if"] == {"field": "chk", "operator": "is_checked"}
    assert any(r["action"] == "unwrap-standalone-checkbox" for r in repairs)
    assert _model_validates(repaired) == ""
    assert not has_errors(lint_schema(repaired))

    # Idempotent: a second pass has nothing left to do.
    again, repairs2 = repair(repaired)
    assert again == repaired
    assert not any(r["action"] == "unwrap-standalone-checkbox" for r in repairs2)


def test_multi_option_checkbox_retypes_to_checkbox_group():
    grp = {"id": "grp", "name": "Grp", "type": "checkbox",
           "pdf_field_name": "G[0]",  # a group must NOT carry one -- dropped
           "options": [
               {"value": "alpha", "label": "Alpha", "pdf_field_name": "a[0]"},
               {"value": "beta", "label": "Beta", "pdf_field_name": "b[0]"},
           ]}
    repaired, repairs = repair(_validatable([grp]))
    out = repaired["fields"][0]
    assert out["type"] == "checkbox_group"
    assert "pdf_field_name" not in out
    assert any(r["action"] == "retype-checkbox-group" for r in repairs)
    assert _model_validates(repaired) == ""


def test_option_label_synthesis_for_groups():
    # A group option missing its label: humanized slug when the value has
    # words; the numeric-only value falls through to "Option N".
    grp = {"id": "grp", "name": "Grp", "type": "checkbox_group",
           "options": [
               {"value": "married_filing_jointly", "pdf_field_name": "a[0]"},
               {"value": "2", "pdf_on_value": "2", "pdf_field_name": "b[0]"},
           ]}
    repaired, repairs = repair(_validatable([grp]))
    opts = repaired["fields"][0]["options"]
    assert opts[0]["label"] == "Married filing jointly"
    assert opts[1]["label"] == "Option 2"
    assert sum(1 for r in repairs
               if r["action"] == "synthesize-option-label") == 2
    assert _model_validates(repaired) == ""


def test_option_label_synthesis_prefers_dump_tooltip():
    grp = {"id": "grp", "name": "Grp", "type": "checkbox_group",
           "options": [
               {"value": "opt_a", "pdf_field_name": "boxes.a[0]"},
           ]}
    dump = {"fields": [{"name": "boxes.a[0]", "tu": "Reason A tooltip"}]}
    repaired, _ = repair(_validatable([grp]), dump)
    assert repaired["fields"][0]["options"][0]["label"] == "Reason A tooltip"


def test_single_option_radio_label_falls_back_to_field_name():
    # A lone-option NON-checkbox keeps its options (only the checkbox
    # unwraps); its missing label reuses the field's own question.
    rad = {"id": "rad", "name": "Are you exempt?", "type": "radio",
           "options": [{"value": "yes", "pdf_field_name": "r[0]",
                        "pdf_on_value": "Y"}]}
    repaired, _ = repair(_schema([rad]))
    assert repaired["fields"][0]["options"][0]["label"] == "Are you exempt?"


def test_contract_shaped_supplements_entry_is_completed():
    # i-90 followed the contract's OLD {id, label} supplements shape;
    # FormSupplement requires {id, name, purpose, fields}.
    f = {"id": "t1", "name": "T1", "type": "text", "pdf_field_name": "T[0]"}
    draft = _validatable([f], supplements=[
        {"id": "additional_information",
         "label": "Part 8. Additional Information"}])
    assert "supplements" in _model_validates(draft)  # RED going in

    repaired, repairs = repair(draft)
    supp = repaired["supplements"][0]
    assert supp["name"] == "Part 8. Additional Information"
    assert supp["purpose"] == supp["name"]
    assert supp["fields"] == []
    assert any(r["action"] == "complete-supplement" for r in repairs)
    assert _model_validates(repaired) == ""
