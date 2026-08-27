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
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
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
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
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
            {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
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
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
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
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
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
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
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
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
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
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
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
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
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
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
         "show_if": {"field": "grp", "operator": "includes", "value": "Other"}},
    ]
    repaired, repairs = repair(_schema(fields))
    dep = next(f for f in repaired["fields"] if f["id"] == "dep")
    assert "show_if" not in dep
    assert any(r["action"] == "drop-condition" and r["error"] for r in repairs)


_COMBO_DUMP = {"fields": [{
    "name": "form1[0].#subform[0].P1_Line6e_State[0]",
    "widgets": [{"choices": [
        {"value": " "}, {"value": "WY"}, {"value": "AL"}, {"value": "DC"},
    ]}],
}]}


def _combo(options):
    return [{"id": "mail_state", "type": "select",
             "pdf_field_name": "P1_Line6e_State[0]", "options": list(options)}]


def _values(repaired):
    return [o["value"] for o in repaired["fields"][0]["options"]]


def test_pdf_sanctioned_dropdown_codes_survive_repair():
    """Minting a slug over a dropdown's export code makes the PDF print wrong
    (the value is written verbatim; PyMuPDF does not validate against /Opt).
    Repair must leave PDF-declared codes alone (bd polyglot-pdf-g2fpr).
    """
    opts = [{"value": "WY", "label": "Wyoming (WY)"},
            {"value": "AL", "label": "Alabama (AL)"}]
    repaired, repairs = repair(_schema(_combo(opts)), _COMBO_DUMP)
    assert _values(repaired) == ["WY", "AL"]
    assert not any(r["action"] == "mint-option-slugs" for r in repairs)


def test_dropdown_codes_survive_a_mint_triggered_by_a_sibling_defect():
    """Minting is triggered per-FIELD: one duplicate anywhere in the dropdown
    used to rewrite EVERY option, so a single unrelated defect broke printing
    for all 62 state codes. The codes must survive their neighbour's repair.
    """
    opts = [{"value": "WY", "label": "Wyoming (WY)"},
            {"value": "AL", "label": "Alabama (AL)"},
            {"value": "AL", "label": "Alabama duplicate"}]
    repaired, _ = repair(_schema(_combo(opts)), _COMBO_DUMP)
    assert _values(repaired)[:2] == ["WY", "AL"]


def test_preserved_code_cannot_collide_with_a_minted_sibling():
    """A lowercase PDF code is itself slug-legal, so a slug minted from another
    option's label can equal a preserved code -- manufacturing the very
    duplicate this branch exists to repair. The minter must reserve them.
    """
    dump = {"fields": [{"name": "X[0]", "widgets": [
        {"choices": [{"value": "wy"}, {"value": "al"}]}]}]}
    fields = [{"id": "m", "type": "select", "pdf_field_name": "X[0]", "options": [
        {"value": "wy", "label": "Wyoming"},
        {"value": "", "label": "WY"},          # mints to 'wy' without the guard
        {"value": "al", "label": "Alabama"},
    ]}]
    repaired, _ = repair(_schema(fields), dump)
    vals = _values(repaired)
    assert len(vals) == len(set(vals)), "repair manufactured a duplicate: %r" % vals
    assert vals[0] == "wy"


def test_dumpless_repair_still_mints_over_non_slug_dropdown_values():
    """No dump means no evidence: repair keeps its old, stricter behaviour
    rather than preserving values it cannot verify.
    """
    # 2+ options: _is_choice_field only treats an option-bearing field as a
    # choice field at that size, so a single-option fixture would pass here
    # for the wrong reason (no minting attempted at all).
    opts = [{"value": "WY", "label": "Wyoming (WY)"},
            {"value": "AL", "label": "Alabama (AL)"}]
    repaired, repairs = repair(_schema(_combo(opts)), None)
    assert _values(repaired) == ["wyoming_wy", "alabama_al"]
    assert any(r["action"] == "mint-option-slugs" for r in repairs)


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
# No-name ledger check (bd polyglot-pdf-l1a9): a source=pdf field whose type
# carries its OWN widget identity but has no pdf_field_name at all is a
# phantom -- un-fillable, un-verifiable, un-fixable. RepairError, never a
# silent pass. Exempt types (identity lives below the field level) pass.
# --------------------------------------------------------------------------- #

def _named_text(fid="named", name="topmost[0].f1_01[0]"):
    return {"id": fid, "type": "text", "pdf_field_name": name}


def test_no_name_text_and_signature_raise():
    fields = [
        _named_text(),
        {"id": "ghost_text", "type": "text"},
        {"id": "ghost_sig", "type": "signature"},
    ]
    with pytest.raises(RepairError) as exc:
        repair(_schema(fields))
    msg = str(exc.value)
    assert "ghost_text" in msg and "ghost_sig" in msg
    assert "no PDF widget name" in msg


def test_no_name_exempt_types_pass():
    # Identity lives below the field level for these: options (choice types),
    # columns (table), slots (address_group) -- a missing FIELD-level name is
    # legitimate, not a phantom.
    fields = [
        _group(),  # checkbox_group with per-option names, no field-level name
        {"id": "tbl", "type": "table",
         "columns": [{"id": "c1", "pdf_field_name": "t[0].c1[0]"}]},
        {"id": "addr", "type": "address_group",
         "address_fields": {"street": "street_f"}},
        _named_text("street_f", "topmost[0].street[0]"),
    ]
    repaired, _ = repair(_schema(fields))
    assert [f["id"] for f in repaired["fields"]] == [
        "grp", "tbl", "addr", "street_f"]


def test_no_name_check_skipped_for_non_pdf_source():
    fields = [{"id": "ghost", "type": "text"}]
    repaired, _ = repair({"source": "web", "fields": fields})
    assert repaired["fields"][0]["id"] == "ghost"


def test_lone_option_checkbox_lift_still_passes_no_name_check():
    # A checkbox with exactly one named option is the legitimate lone-option
    # idiom: normalization lifts the option's name onto the field BEFORE the
    # no-name check runs, so it must not false-positive.
    fields = [{
        "id": "consent", "type": "checkbox",
        "options": [{"value": "yes", "label": "Yes",
                     "pdf_field_name": "top[0].consent[0]"}],
    }]
    repaired, _ = repair(_schema(fields))
    assert repaired["fields"][0]["pdf_field_name"] == "top[0].consent[0]"


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


def test_unlocks_converts_to_gold_unlock_pattern():
    # bd polyglot-pdf-xbfm: `unlocks` IS convertible -- the gold-attested
    # read-only-unlock pattern puts conditional_behavior {unlock_method:
    # flip_readonly_bit} on the TARGET plus the trigger condition as its
    # show_if (i-90 gold shape). No unmirrored entry: nothing was dropped.
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "no", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "yes",
                             "unlocks": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    draft = _v2_schema([trigger, target])
    repaired, repairs = repair(draft)
    assert "controls_fields" not in repaired["fields"][0]  # fully converted
    tgt = repaired["fields"][1]
    # The COMPLETE gold descriptor: unlock_method alone looks unlocked in the
    # editor/lint but the PDF filler early-returns without the flag change
    # (fresh-eyes round 1 on this bead).
    assert tgt["conditional_behavior"] == {
        "unlock_method": "flip_readonly_bit",
        "pdf_field_flag_change": {"bit": 0, "current_value": 1,
                                  "required_value": 0}}
    atoms = [tgt["show_if"]] if "field" in tgt["show_if"] else \
        [a for b in ("all_of", "any_of", "none_of")
         for a in tgt["show_if"].get(b, [])]
    assert any(a.get("field") == "trg" and a.get("value") == "yes"
               for a in atoms)
    assert not [r for r in repairs
                if r["action"] == "controls-fields-unmirrored"]
    mirrored = [r for r in repairs if r["action"] == "mirror-controls-fields"]
    assert any("unlocks" in r["detail"] for r in mirrored)
    assert not has_errors(lint_schema(repaired))


def test_hides_converts_to_negated_show_if():
    # bd polyglot-pdf-xbfm: `hides` = conditional visibility NEGATED -- the
    # target's show_if gains the trigger condition under none_of.
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "no", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "yes",
                             "hides": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    draft = _v2_schema([trigger, target])
    repaired, repairs = repair(draft)
    assert "controls_fields" not in repaired["fields"][0]
    tgt = repaired["fields"][1]
    none_of = tgt["show_if"]["none_of"]
    assert any(a.get("field") == "trg" and a.get("value") == "yes"
               for a in none_of)
    assert not has_errors(lint_schema(repaired))


def test_locks_and_makes_optional_are_retained_for_lint_not_dropped():
    # bd polyglot-pdf-xbfm: the two GENUINELY unconvertible actions are
    # RETAINED on the field (a reduced controls_fields rump), so schema_lint's
    # legacy-trigger-side-logic ERROR flags them for a human -- loud in the
    # report AND the lint, never a silent drop.
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "no", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "yes",
                             "locks": ["tgt"], "makes_optional": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    draft = _v2_schema([trigger, target])
    repaired, repairs = repair(draft)
    rump = repaired["fields"][0]["controls_fields"]
    assert rump == [{"operator": "equals", "value": "yes",
                     "locks": ["tgt"], "makes_optional": ["tgt"]}]
    unconv = [r for r in repairs if r["action"] == "controls-fields-unmirrored"]
    assert len(unconv) == 1 and "RETAINED" in unconv[0]["detail"]
    findings = lint_schema(repaired)
    assert any(fnd.rule == "legacy-trigger-side-logic" for fnd in findings)


def test_all_six_trigger_actions_end_to_end():
    # bd polyglot-pdf-xbfm exit criterion: every trigger-side relationship is
    # either canonicalized into a v2 key or surfaced in the repair report +
    # lint -- all six action kinds in ONE control, end to end through repair().
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "no", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "yes",
                             "shows": ["t_show"], "makes_required": ["t_req"],
                             "unlocks": ["t_unlock"], "hides": ["t_hide"],
                             "locks": ["t_lock"],
                             "makes_optional": ["t_opt"]}]}
    targets = [{"id": t, "type": "text", "pdf_field_name": f"{t}[0]"}
               for t in ("t_show", "t_req", "t_unlock", "t_hide", "t_lock",
                         "t_opt")]
    draft = _v2_schema([trigger] + targets)
    repaired, repairs = repair(draft)
    by_id = {f["id"]: f for f in repaired["fields"]}
    # Converted four:
    assert by_id["t_show"]["show_if"]["field"] == "trg"
    assert by_id["t_req"]["require_if"]["field"] == "trg"
    assert by_id["t_unlock"]["conditional_behavior"]["unlock_method"] == \
        "flip_readonly_bit"
    assert by_id["t_unlock"]["conditional_behavior"]["pdf_field_flag_change"] \
        == {"bit": 0, "current_value": 1, "required_value": 0}
    assert by_id["t_unlock"]["show_if"]["field"] == "trg"
    assert any(a["field"] == "trg"
               for a in by_id["t_hide"]["show_if"]["none_of"])
    # Retained two (rump strips converted actions, keeps the condition):
    rump = by_id["trg"]["controls_fields"]
    assert rump == [{"operator": "equals", "value": "yes",
                     "locks": ["t_lock"], "makes_optional": ["t_opt"]}]
    # Loud on both surfaces:
    assert any(r["action"] == "controls-fields-unmirrored" and
               "RETAINED" in r["detail"] for r in repairs)
    assert any(fnd.rule == "legacy-trigger-side-logic"
               for fnd in lint_schema(repaired))
    # And repair is idempotent on its own output (the rump does not multiply).
    repaired2, _ = repair(repaired)
    assert repaired2["fields"][0]["controls_fields"] == rump
    assert repaired2["fields"][4] == by_id["t_hide"]


def _assert_depth1(schema):
    """Every condition in the schema honors the v2 DEPTH-1 rule: a composite
    group's buckets hold ATOMS only (dicts with a 'field' key), never nested
    groups -- the invalid shape the old wrap branches emitted."""
    for f in schema.get("fields", []):
        for key in ("show_if", "require_if"):
            cond = f.get(key)
            if not isinstance(cond, dict) or "field" in cond:
                continue
            for bucket in ("all_of", "any_of", "none_of"):
                for member in cond.get(bucket) or []:
                    assert isinstance(member, dict) and "field" in member, \
                        f"nested group in {f.get('id')}.{key}.{bucket}: {member}"


def test_depth_limit_hides_onto_any_of_target_is_retained_not_nested():
    # Outer review (bd xbfm): v2 conditions are DEPTH-1 -- bucket members must
    # be atoms. `(a OR b) AND NOT c` cannot be expressed, so a hides edge onto
    # a target whose show_if is an any_of composite must be RETAINED in the
    # rump (loud), never emitted as the model-invalid all_of:[{any_of:[...]}]
    # nest the old wrap produced. Reproduces seat B's two-shows-plus-one-hides
    # scenario.
    triggers = [
        {"id": f"trg{i}", "type": "checkbox", "pdf_field_name": f"R{i}[0]"}
        for i in range(3)]
    triggers[0]["controls_fields"] = [{"operator": "is_checked",
                                       "shows": ["tgt"]}]
    triggers[1]["controls_fields"] = [{"operator": "is_checked",
                                       "shows": ["tgt"]}]
    triggers[2]["controls_fields"] = [{"operator": "is_checked",
                                       "hides": ["tgt"]}]
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    draft = _v2_schema(triggers + [target])
    repaired, repairs = repair(draft)
    tgt = next(f for f in repaired["fields"] if f["id"] == "tgt")
    # The two shows composed into a flat any_of; the hides edge did NOT nest.
    assert sorted(a["field"] for a in tgt["show_if"]["any_of"]) == \
        ["trg0", "trg1"]
    assert "all_of" not in tgt["show_if"] and "none_of" not in tgt["show_if"]
    # The hides edge is retained loudly on its trigger.
    trg2 = next(f for f in repaired["fields"] if f["id"] == "trg2")
    assert trg2["controls_fields"] == [{"operator": "is_checked",
                                        "hides": ["tgt"]}]
    unconv = [r for r in repairs if r["action"] == "controls-fields-unmirrored"]
    assert any("depth-1" in r["detail"] for r in unconv)
    _assert_depth1(repaired)  # no nested groups anywhere
    # And the rump keeps the schema loud under lint.
    assert any(fnd.rule == "legacy-trigger-side-logic"
               for fnd in lint_schema(repaired))


def test_depth_limit_unlocks_onto_composite_target_is_retained_whole():
    # The unlocks edge is all-or-nothing: when its visibility pairing cannot
    # compose at depth 1, NO half-paired descriptor is written and the edge is
    # retained in the rump.
    trigger = {"id": "trg", "type": "checkbox", "pdf_field_name": "R[0]",
               "controls_fields": [{"operator": "is_checked",
                                    "unlocks": ["tgt"]}]}
    other = {"id": "oth", "type": "checkbox", "pdf_field_name": "O[0]"}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]",
              "read_only": True,
              "show_if": {"all_of": [
                  {"field": "oth", "operator": "is_checked"}],
                  "none_of": [{"field": "trg", "operator": "is_empty"}]}}
    draft = _v2_schema([trigger, other, target])
    repaired, _ = repair(draft)
    tgt = next(f for f in repaired["fields"] if f["id"] == "tgt")
    assert "conditional_behavior" not in tgt  # no half-paired descriptor
    assert tgt["show_if"] == {  # existing condition untouched
        "all_of": [{"field": "oth", "operator": "is_checked"}],
        "none_of": [{"field": "trg", "operator": "is_empty"}]}
    trg = next(f for f in repaired["fields"] if f["id"] == "trg")
    assert trg["controls_fields"] == [{"operator": "is_checked",
                                       "unlocks": ["tgt"]}]
    _assert_depth1(repaired)


def test_mirror_alias_is_reported_exactly_once():
    # Outer review (bd xbfm): the conversion pass re-normalizes each
    # unlocks/hides-bearing control QUIETLY -- a loud second pass would
    # double-log every alias-operator entry and double alias_hit_count (the
    # P6 decay metric). Pin exact cardinality for both a plain shows edge and
    # an unlocks-bearing edge on a checkbox_group trigger (whose v1 `equals`
    # aliases to `includes`).
    def _draft(actions):
        trigger = {"id": "trg", "type": "checkbox_group", "options": [
            {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]"},
            {"value": "no", "label": "No", "pdf_field_name": "R[1]"}],
            "controls_fields": [dict({"operator": "equals", "value": "yes"},
                                     **actions)]}
        target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
        return _v2_schema([trigger, target])

    for actions in ({"shows": ["tgt"]},
                    {"shows": ["tgt"], "unlocks": ["tgt"]},
                    {"hides": ["tgt"]}):
        _, repairs = repair(_draft(actions))
        aliases = [r for r in repairs if r["action"] == "alias-operator"]
        assert len(aliases) == 1, (actions, aliases)


def test_lint_warns_on_unlock_method_without_flag_change():
    # Fresh-eyes round 1 (bd xbfm): an unlock_method with no
    # pdf_field_flag_change is invisible-broken -- editor UI + the
    # readonly-conditional-no-unlock check read unlock_method alone, but the
    # PDF filler early-returns without the flag change. The new WARNING makes
    # the failure mode visible to a human; repair's own synthesis emits the
    # full descriptor, so a fresh conversion never trips it.
    field = {"id": "f1", "type": "text", "pdf_field_name": "F[0]",
             "read_only": True,
             "show_if": {"field": "f0", "operator": "is_checked"},
             "conditional_behavior": {"unlock_method": "flip_readonly_bit"}}
    trigger = {"id": "f0", "type": "checkbox", "pdf_field_name": "C[0]"}
    schema = _v2_schema([trigger, field])
    findings = lint_schema(schema)
    assert any(fnd.rule == "unlock-missing-flag-change" for fnd in findings)
    # The complete descriptor (what repair now synthesizes) is clean.
    field["conditional_behavior"] = {
        "unlock_method": "flip_readonly_bit",
        "pdf_field_flag_change": {"bit": 0, "current_value": 1,
                                  "required_value": 0}}
    findings2 = lint_schema(schema)
    assert not any(fnd.rule == "unlock-missing-flag-change"
                   for fnd in findings2)


def test_hides_polarity_guard_existing_positive_atom_does_not_suppress():
    # A POSITIVE occurrence of the same atom in the target's show_if must not
    # count as "already hidden" -- polarity matters (cfm.negated_atom_present
    # checks none_of buckets only). The existing positive condition is
    # preserved as an all_of arm beside the new none_of.
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "no", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "yes",
                             "hides": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]",
              "show_if": {"field": "trg", "operator": "equals", "value": "yes"}}
    draft = _v2_schema([trigger, target])
    repaired, _ = repair(draft)
    cond = repaired["fields"][1]["show_if"]
    assert cond["all_of"] == [
        {"field": "trg", "operator": "equals", "value": "yes"}]
    assert cond["none_of"] == [
        {"field": "trg", "operator": "equals", "value": "yes"}]


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


def test_supplements_entry_missing_id_gets_one_synthesized():
    # Fresh-eyes gap: id is required too; a label-only entry must complete
    # ALL FOUR FormSupplement keys, not three.
    f = {"id": "t1", "name": "T1", "type": "text", "pdf_field_name": "T[0]"}
    draft = _validatable([f], supplements=[{"label": "Extra Space"}])
    assert "supplements" in _model_validates(draft)

    repaired, _ = repair(draft)
    supp = repaired["supplements"][0]
    assert supp["id"] == "extra_space"  # slugified from the label
    assert supp["name"] == "Extra Space"
    assert _model_validates(repaired) == ""


# --------------------------------------------------------------------------- #
# Bundled nit fixes (bd polyglot-pdf-v76t + polyglot-pdf-pofh).
# --------------------------------------------------------------------------- #

def test_section_condition_retargeted_after_standalone_unwrap():
    # bd v76t: a SECTION's show_if referencing an unwrapped lone-option
    # checkbox by its old option value stayed model-valid but semantically
    # dead (a boolean trigger never equals the vanished value). Sections now
    # get the same equals-old -> is_checked retarget as fields.
    chk = {"id": "chk", "name": "Standalone", "type": "checkbox",
           "options": [{"value": "yes", "pdf_on_value": "Y",
                        "pdf_field_name": "c[0]"}]}
    draft = _validatable([chk])
    draft["sections"][0]["show_if"] = {
        "field": "chk", "operator": "equals", "value": "yes"}

    repaired, repairs = repair(draft)
    assert repaired["sections"][0]["show_if"] == {
        "field": "chk", "operator": "is_checked"}
    assert any(r["action"] == "alias-operator"
               and r["path"].startswith("sections[0]") for r in repairs)
    assert _model_validates(repaired) == ""


def test_synthesized_supplement_ids_deduplicate():
    # bd v76t: two id-less entries sharing a label used to collide on the
    # slugified id; and a synthesized id must not collide with an explicit one.
    f = {"id": "t1", "name": "T1", "type": "text", "pdf_field_name": "T[0]"}
    draft = _validatable([f], supplements=[
        {"label": "Extra Space"},
        {"label": "Extra Space"},
        {"id": "extra_space_2", "name": "N", "purpose": "P", "fields": []},
    ])
    repaired, _ = repair(draft)
    ids = [s["id"] for s in repaired["supplements"]]
    assert len(set(ids)) == 3, ids
    assert ids[0] == "extra_space"
    assert ids[1] not in ("extra_space", "extra_space_2")
    assert _model_validates(repaired) == ""


def test_multi_entry_overflow_supplement_aliases_like_field_level():
    # bd pofh: the SAME SupplementType enum lives on the multi_entry
    # sub-config; an invented value there also failed model_validate.
    f = {"id": "t1", "name": "T1", "type": "text", "pdf_field_name": "T[0]",
         "multi_entry": {"min_entries": 1, "initial_rows": 1,
                         "overflow_to_supplement": "additional_children"}}
    draft = _validatable([f])
    assert "overflow_to_supplement" in _model_validates(draft)  # RED going in

    repaired, repairs = repair(draft)
    assert repaired["fields"][0]["multi_entry"]["overflow_to_supplement"] == \
        "supplement_a"
    assert any(r["action"] == "alias-overflow-supplement"
               and r["path"].endswith(".multi_entry") for r in repairs)
    assert _model_validates(repaired) == ""


# --------------------------------------------------------------------------- #
# Top-level `required` migration (bd polyglot-pdf-0x10.4).
# --------------------------------------------------------------------------- #

def _text_field(fid, **extra):
    f = {"id": fid, "type": "text", "pdf_field_name": f"{fid}[0]"}
    f.update(extra)
    return f


def test_truthy_top_level_required_moves_into_validation():
    schema = _v2_schema([_text_field("a", required=True)])
    assert has_errors(lint_schema(schema))  # required-top-level is RED going in
    repaired, repairs = repair(schema)
    field = repaired["fields"][0]
    assert "required" not in field
    assert field["validation"]["required"] is True
    assert any(r["action"] == "migrate-top-level-required" for r in repairs)
    assert not has_errors(lint_schema(repaired))


def test_truthy_top_level_required_merges_into_existing_validation():
    schema = _v2_schema([
        _text_field("a", required=True, validation={"max_length": 5}),
    ])
    repaired, _ = repair(schema)
    field = repaired["fields"][0]
    assert "required" not in field
    # Sibling validation keys survive the merge.
    assert field["validation"] == {"max_length": 5, "required": True}


def test_top_level_required_never_clobbers_explicit_validation_required():
    schema = _v2_schema([
        _text_field("a", required=True, validation={"required": False}),
    ])
    repaired, repairs = repair(schema)
    field = repaired["fields"][0]
    assert "required" not in field
    # The canonical key wins; the legacy key is dropped, recorded.
    assert field["validation"]["required"] is False
    assert any(r["action"] == "migrate-top-level-required" for r in repairs)


def test_falsy_top_level_required_is_dropped_without_inventing_validation():
    schema = _v2_schema([_text_field("a", required=False)])
    repaired, repairs = repair(schema)
    field = repaired["fields"][0]
    assert "required" not in field
    assert "validation" not in field  # nothing invented for a dead falsy key
    assert any(r["action"] == "migrate-top-level-required" for r in repairs)


def test_required_migration_is_idempotent():
    schema = _v2_schema([_text_field("a", required=True)])
    once, _ = repair(schema)
    twice, repairs2 = repair(once)
    assert twice["fields"][0]["validation"]["required"] is True
    assert not any(
        r["action"] == "migrate-top-level-required" for r in repairs2
    )


# --------------------------------------------------------------------------- #
# Voice-facing spoken_name disambiguation stripping (bd polyglot-pdf-che4).
# --------------------------------------------------------------------------- #

def test_disambiguation_counter_stripped_from_clustered_spoken_names():
    # Two fields whose spoken_names differ only by a trailing counter (the
    # i-90 alien-number shape) -- both lose the counter.
    schema = _schema([
        _text_field("a1", spoken_name="alien registration number 1"),
        _text_field("a2", spoken_name="alien registration number 2"),
    ])
    repaired, repairs = repair(schema)
    names = [f["spoken_name"] for f in repaired["fields"]]
    assert names == ["alien registration number", "alien registration number"]
    stripped = [r for r in repairs
                if r["action"] == "strip-spoken-name-disambiguation"]
    assert len(stripped) == 2
    # Duplicate spoken_names are intended -- the voice model never sees two.


def test_semantic_trailing_number_is_never_stripped():
    # A YEAR and a lone number: no sibling shares the base, so neither is a
    # disambiguation cluster -- both survive untouched (the f1040 shape).
    schema = _schema([
        _text_field("y1", spoken_name="Line 12d you born before 1961"),
        _text_field("y2", spoken_name="Line 12d spouse born before 1961"),
        _text_field("reg", spoken_name="Filed pursuant to 301.9100-2"),
    ])
    repaired, repairs = repair(schema)
    names = [f["spoken_name"] for f in repaired["fields"]]
    assert names == [
        "Line 12d you born before 1961",
        "Line 12d spouse born before 1961",
        "Filed pursuant to 301.9100-2",
    ]
    assert not any(r["action"] == "strip-spoken-name-disambiguation"
                   for r in repairs)


def test_lone_counter_suffix_is_left_alone():
    # A single 'field 1' with no sibling '... 2' is not a proven disambiguation
    # cluster -- left untouched (conservative; a real numbered name like
    # 'child 1' stays intact until a sibling proves otherwise).
    schema = _schema([_text_field("solo", spoken_name="child 1")])
    repaired, repairs = repair(schema)
    assert repaired["fields"][0]["spoken_name"] == "child 1"
    assert not any(r["action"] == "strip-spoken-name-disambiguation"
                   for r in repairs)


def test_spoken_name_strip_is_idempotent():
    schema = _schema([
        _text_field("a1", spoken_name="alien registration number 1"),
        _text_field("a2", spoken_name="alien registration number 2"),
    ])
    once, _ = repair(schema)
    twice, repairs2 = repair(once)
    assert [f["spoken_name"] for f in twice["fields"]] == [
        "alien registration number", "alien registration number"]
    assert not any(r["action"] == "strip-spoken-name-disambiguation"
                   for r in repairs2)


def test_strip_clears_stale_translations_for_rebake():
    # fresh-eyes hardening: stripping the counter also drops the now-stale
    # suffixed translations so a repair-only caller can never ship a
    # digit-bearing translation (the re-bake refills them).
    schema = _schema([
        _text_field("a1", spoken_name="alien registration number 1",
                    spoken_name_translations={"spanish":
                                              "numero de registro 1"}),
        _text_field("a2", spoken_name="alien registration number 2",
                    spoken_name_translations={"spanish":
                                              "numero de registro 2"}),
    ])
    repaired, repairs = repair(schema)
    for f in repaired["fields"]:
        assert f["spoken_name"] == "alien registration number"
        assert "spoken_name_translations" not in f  # cleared for re-bake
    assert all("cleared stale spoken_name_translations" in r["detail"]
               for r in repairs
               if r["action"] == "strip-spoken-name-disambiguation")


def test_strip_leaves_untouched_field_translations_intact():
    # A semantic-number field (not stripped) keeps its translations.
    schema = _schema([
        _text_field("y1", spoken_name="born before 1961",
                    spoken_name_translations={"spanish": "nacido antes de 1961"}),
    ])
    repaired, _ = repair(schema)
    f = repaired["fields"][0]
    assert f["spoken_name"] == "born before 1961"
    assert f["spoken_name_translations"] == {"spanish": "nacido antes de 1961"}
