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
