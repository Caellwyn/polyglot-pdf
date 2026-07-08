"""Tests for scripts/migrate_schema_v2.py (bd polyglot-pdf-4lqi, P6.1a).

The deterministic v1 -> v2 migration. Exit criteria:
1. migrate() is idempotent, and its output on the i-90 schema validates as v2 +
   lints clean.
2. The is_checked DUAL FATE matches the SHARED fixture
   (backend/tests/fixtures/is_checked_dual_fate.json) -- the SAME fixture the
   P1.1 validator tests consume, so migration + validator agree by construction.
   An unmirrored controls_fields edge is REPORTED, not silently dropped.

Imports migrate_schema_v2 + acroform_dump by file path (repo precedent:
test_extract_form_lint.py). ASCII only.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


mig = _load("migrate_schema_v2", _REPO / "scripts" / "migrate_schema_v2.py")

from backend.models.form_models import FormSchema  # noqa: E402
from backend.models import conditional_vocabulary as vocab  # noqa: E402
from backend.services.schema_lint import lint_schema, has_errors  # noqa: E402

_FIXTURES = _REPO / "backend" / "tests" / "fixtures"
_I90 = _REPO / "form-kits" / "i-90" / "schema.json"
_I90_PDF = _REPO / "form-kits" / "i-90" / "form.pdf"


def _v1(fields, **extra):
    s = {"source": "pdf", "form_metadata": {"title": "T", "version": "unknown"},
         "sections": [], "fields": fields}
    s.update(extra)
    return s


# --- classification ---------------------------------------------------------

def test_checkbox_with_2plus_options_becomes_checkbox_group():
    f = {"id": "g", "type": "checkbox", "pdf_field_name": "F[0]", "options": [
        {"value": "A[0]", "label": "Apple", "pdf_field_name": "F[0]"},
        {"value": "A[1]", "label": "Banana", "pdf_field_name": "F[1]"}]}
    out, rep = mig.migrate(_v1([f]))
    mf = out["fields"][0]
    assert mf["type"] == "checkbox_group"
    assert "pdf_field_name" not in mf  # a group carries no field-level name
    assert [o["value"] for o in mf["options"]] == ["apple", "banana"]  # slugs
    assert "g" in rep["checkbox_groups"]


def test_checkbox_with_one_option_becomes_standalone_checkbox():
    f = {"id": "c", "type": "checkbox", "options": [
        {"value": "C[0]", "label": "Agree", "pdf_field_name": "form.C[0]"}]}
    out, rep = mig.migrate(_v1([f]))
    mf = out["fields"][0]
    assert mf["type"] == "checkbox"
    assert "options" not in mf
    assert mf["pdf_field_name"] == "form.C[0]"  # lifted from the single option
    assert "c" in rep["standalone_unwrapped"]


def test_equals_on_a_standalone_unwrapped_checkbox_becomes_is_checked():
    # bd c5r8: when a 1-option checkbox unwraps to standalone, its option value
    # vanishes -- a dependent's `equals <that value>` would DANGLE (never fire on
    # the now-boolean trigger). It must become is_checked (the standalone idiom).
    trigger = {"id": "cb", "type": "checkbox", "options": [
        {"value": "CB[0]", "label": "Yes", "pdf_field_name": "form.CB[0]"}]}
    dep = {"id": "d", "type": "text", "pdf_field_name": "D[0]",
           "show_if": {"field": "cb", "operator": "equals", "value": "CB[0]"}}
    out, _ = mig.migrate(_v1([trigger, dep]))
    si = out["fields"][1]["show_if"]
    assert si["operator"] == "is_checked"
    assert "value" not in si


def test_not_equals_on_a_standalone_unwrapped_checkbox_is_reported():
    # not_equals on a standalone checkbox has no clean v2 idiom -> REPORTED for a
    # human, not mis-rewritten (bd c5r8). i-90 has none.
    trigger = {"id": "cb", "type": "checkbox", "options": [
        {"value": "CB[0]", "label": "Yes", "pdf_field_name": "form.CB[0]"}]}
    dep = {"id": "d", "type": "text", "pdf_field_name": "D[0]",
           "show_if": {"field": "cb", "operator": "not_equals", "value": "CB[0]"}}
    out, rep = mig.migrate(_v1([trigger, dep]))
    assert rep.get("standalone_not_equals_refs")
    # The atom is left for the human (unchanged operator).
    assert out["fields"][1]["show_if"]["operator"] == "not_equals"


# --- the SHARED is_checked dual-fate fixture (agree by construction) ---------

def test_is_checked_dual_fate_matches_shared_fixture():
    fixture = json.loads((_FIXTURES / "is_checked_dual_fate.json").read_text(encoding="utf-8"))
    for case in fixture["cases"]:
        trigger_type = case["trigger_type"]
        expected_op = case["migration"]["operator"]
        # Build a trigger of the right type + a dependent whose show_if uses
        # is_checked on it, then migrate and read the rewritten operator.
        if trigger_type == "checkbox":
            trigger = {"id": "trg", "type": "checkbox", "pdf_field_name": "T[0]"}
        else:  # checkbox_group
            trigger = {"id": "trg", "type": "checkbox", "pdf_field_name": "T[0]",
                       "options": [
                           {"value": "T[0]", "label": "One", "pdf_field_name": "T[0]"},
                           {"value": "T[1]", "label": "Two", "pdf_field_name": "T[1]"}]}
        dep = {"id": "dep", "type": "text", "pdf_field_name": "D[0]",
               "show_if": {"field": "trg", "operator": "is_checked", "value": True}}
        out, _ = mig.migrate(_v1([trigger, dep]))
        got_op = out["fields"][1]["show_if"]["operator"]
        assert got_op == expected_op, (
            f"{case['name']}: is_checked on {trigger_type} -> {got_op}, "
            f"fixture expects {expected_op}"
        )


def test_equals_on_group_trigger_becomes_includes():
    trigger = {"id": "g", "type": "checkbox", "pdf_field_name": "G[0]", "options": [
        {"value": "G[0]", "label": "Alpha", "pdf_field_name": "G[0]"},
        {"value": "G[1]", "label": "Beta", "pdf_field_name": "G[1]"}]}
    dep = {"id": "d", "type": "text", "pdf_field_name": "D[0]",
           "show_if": {"field": "g", "operator": "equals", "value": "G[0]"}}
    out, _ = mig.migrate(_v1([trigger, dep]))
    si = out["fields"][1]["show_if"]
    assert si["operator"] == "includes"
    assert si["value"] == "alpha"  # value rewritten to the new slug


def test_empty_string_equals_becomes_is_empty():
    trigger = {"id": "t", "type": "text", "pdf_field_name": "T[0]"}
    dep = {"id": "d", "type": "text", "pdf_field_name": "D[0]",
           "show_if": {"field": "t", "operator": "not_equals", "value": ""}}
    out, _ = mig.migrate(_v1([trigger, dep]))
    si = out["fields"][1]["show_if"]
    assert si["operator"] == "is_not_empty"
    assert "value" not in si


# --- conditional_logic fold + conditional_fields drop -----------------------

def test_conditional_logic_folds_into_behavior_keeping_flag_change():
    f = {"id": "f", "type": "text", "pdf_field_name": "F[0]",
         "conditional_logic": {"unlock_method": "flip_readonly_bit",
                               "pdf_field_flag_change": {"bit": 0}, "show_method": "x"},
         "conditional_behavior": {"unlock_method": "flip_readonly_bit"}}
    out, rep = mig.migrate(_v1([f]))
    mf = out["fields"][0]
    assert "conditional_logic" not in mf
    cb = mf["conditional_behavior"]
    assert cb["unlock_method"] == "flip_readonly_bit"
    assert cb["pdf_field_flag_change"] == {"bit": 0}  # kept (the fillable descriptor)
    assert "show_method" not in cb  # dropped: no reader
    assert rep["behaviors_folded"] >= 1


def test_conditional_fields_is_dropped():
    f = {"id": "f", "type": "text", "pdf_field_name": "F[0]",
         "conditional_fields": ["a", "b"]}
    out, rep = mig.migrate(_v1([f]))
    assert "conditional_fields" not in out["fields"][0]
    assert rep["conditional_fields_dropped"] == 1


# --- controls_fields drop-if-mirrored / report-if-unmirrored ----------------

def test_shows_edge_mirrored_by_target_show_if_is_dropped():
    # A `shows` edge whose target ALREADY carries the matching show_if is a no-op:
    # controls_fields is removed and nothing is re-added (dropped, not re-mirrored).
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "R[0]", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "R[1]", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "R[0]",
                             "shows": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]",
              "show_if": {"field": "trg", "operator": "equals", "value": "R[0]"}}
    out, rep = mig.migrate(_v1([trigger, target]))
    assert "controls_fields" not in out["fields"][0]  # always removed
    assert rep["controls_fields_dropped"] == 1
    assert rep["controls_mirrored"] == 0  # target already mirrored it
    assert rep["unmirrored_controls"] == []


def test_unmirrored_shows_edge_is_mirrored_into_target_show_if():
    # A `shows` edge whose target has no matching condition is MIRRORED into the
    # target's show_if (v2 has no trigger-side logic), then controls_fields is
    # dropped -- the behavior survives (bd h76m.16, fixing the P6.2 over-strip).
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "R[0]", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "R[1]", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "R[0]",
                             "shows": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    out, rep = mig.migrate(_v1([trigger, target]))
    assert "controls_fields" not in out["fields"][0]  # always removed
    tgt = out["fields"][1]
    assert tgt["show_if"] == {"field": "trg", "operator": "equals", "value": "yes"}
    assert rep["controls_mirrored"] == 1


def test_unmirrored_makes_required_edge_is_mirrored_into_require_if():
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "R[0]", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "R[1]", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "R[0]",
                             "makes_required": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    out, rep = mig.migrate(_v1([trigger, target]))
    assert "controls_fields" not in out["fields"][0]
    assert out["fields"][1]["require_if"] == {
        "field": "trg", "operator": "equals", "value": "yes"}


def test_same_trigger_show_if_does_not_suppress_that_triggers_require_if():
    # fresh-eyes r2/r3: the EXACT w7 relationship_d shape. reason_d's edge
    # makes_required:[relationship_d], and relationship_d ALREADY has a show_if
    # naming reason_d with the SAME value -- so the key-blind "already mirrored"
    # check saw the matching show_if and dropped require_if to None. The mirror
    # must be KEY-SPECIFIC: a show_if match must NOT satisfy a makes_required edge.
    trig = {"id": "reason_d", "type": "checkbox", "pdf_field_name": "R[0]",
            "options": [{"value": "R[0]", "label": "D", "pdf_field_name": "R[0]"}],
            "controls_fields": [{"operator": "equals", "value": "R[0]",
                                 "makes_required": ["rel_d"]}]}
    # rel_d is SHOWN when reason_d==R[0] AND (per the edge) REQUIRED under the same
    # condition. Both buckets must be populated.
    rel_d = {"id": "rel_d", "type": "text", "pdf_field_name": "T[0]",
             "show_if": {"field": "reason_d", "operator": "equals", "value": "R[0]"}}
    out, rep = mig.migrate(_v1([trig, rel_d]))
    t = {f["id"]: f for f in out["fields"]}["rel_d"]
    # show_if is a single-option checkbox trigger -> equals R[0] became is_checked.
    assert t["show_if"] == {"field": "reason_d", "operator": "is_checked"}
    # require_if MUST be populated (the r2 bug left it None because show_if matched).
    assert t["require_if"] == {"field": "reason_d", "operator": "is_checked"}


def test_pre_existing_show_if_does_not_suppress_a_makes_required_mirror():
    # A target with a show_if from trigger X must STILL gain a require_if when a
    # DIFFERENT trigger Y's makes_required edge names it (the cross-trigger case).
    x = {"id": "x", "type": "checkbox", "pdf_field_name": "X[0]", "options": [
        {"value": "X[0]", "label": "X", "pdf_field_name": "X[0]"}]}
    y = {"id": "y", "type": "checkbox", "pdf_field_name": "Y[0]", "options": [
        {"value": "Y[0]", "label": "Y", "pdf_field_name": "Y[0]"}],
        "controls_fields": [{"operator": "is_checked", "makes_required": ["tgt"]}]}
    tgt = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]",
           "show_if": {"field": "x", "operator": "is_checked"}}
    out, rep = mig.migrate(_v1([x, y, tgt]))
    t = {f["id"]: f for f in out["fields"]}["tgt"]
    assert t["show_if"] == {"field": "x", "operator": "is_checked"}  # kept
    assert t["require_if"] == {"field": "y", "operator": "is_checked"}  # NOT dropped


def test_makes_required_from_two_triggers_where_one_also_shows_merges_correctly():
    # The exact w7 shape: reason_d SHOWS + REQUIRES tgt, reason_e also REQUIRES it.
    # require_if must be the OR of BOTH (any_of), not just one.
    d = {"id": "rd", "type": "checkbox", "pdf_field_name": "D[0]", "options": [
        {"value": "D[0]", "label": "D", "pdf_field_name": "D[0]"}],
        "controls_fields": [{"operator": "is_checked",
                             "shows": ["tgt"], "makes_required": ["tgt"]}]}
    e = {"id": "re", "type": "checkbox", "pdf_field_name": "E[0]", "options": [
        {"value": "E[0]", "label": "E", "pdf_field_name": "E[0]"}],
        "controls_fields": [{"operator": "is_checked", "makes_required": ["tgt"]}]}
    tgt = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    out, rep = mig.migrate(_v1([d, e, tgt]))
    t = {f["id"]: f for f in out["fields"]}["tgt"]
    assert t["show_if"] == {"field": "rd", "operator": "is_checked"}
    assert "any_of" in t["require_if"]
    assert {a["field"] for a in t["require_if"]["any_of"]} == {"rd", "re"}


def test_two_triggers_requiring_one_target_merge_into_any_of():
    # reason_a AND reason_f both require treaty_country -> require_if is the OR
    # (any_of) of both conditions, not a last-writer-wins overwrite.
    a = {"id": "a", "type": "checkbox", "pdf_field_name": "A[0]", "options": [
        {"value": "A[0]", "label": "Reason A", "pdf_field_name": "A[0]"}],
        "controls_fields": [{"operator": "is_checked", "makes_required": ["tc"]}]}
    f = {"id": "f", "type": "checkbox", "pdf_field_name": "F[0]", "options": [
        {"value": "F[0]", "label": "Reason F", "pdf_field_name": "F[0]"}],
        "controls_fields": [{"operator": "is_checked", "makes_required": ["tc"]}]}
    tc = {"id": "tc", "type": "text", "pdf_field_name": "TC[0]"}
    out, rep = mig.migrate(_v1([a, f, tc]))
    req = out["fields"][2]["require_if"]
    assert "any_of" in req and len(req["any_of"]) == 2
    fields = {atom["field"] for atom in req["any_of"]}
    assert fields == {"a", "f"}


def test_unconvertible_action_is_reported_not_silently_lost():
    # unlocks/locks/hides/makes_optional have no clean v2 target-side equivalent;
    # they are REPORTED as unconverted (the human still reviews them), and
    # controls_fields is still removed.
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "R[0]", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "R[1]", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "R[0]",
                             "unlocks": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    out, rep = mig.migrate(_v1([trigger, target]))
    assert "controls_fields" not in out["fields"][0]
    assert "show_if" not in out["fields"][1] and "require_if" not in out["fields"][1]
    unconv = [u for u in rep["unmirrored_controls"] if u.get("unconverted_actions")]
    assert unconv and unconv[0]["unconverted_actions"] == ["tgt"]


def test_duplicate_option_values_are_reported_not_collapsed():
    # fresh-eyes: two options sharing a v1 value are ambiguous to rewrite; the
    # collision is REPORTED and the value is left OUT of the rewrite map (so a
    # referencing condition is preserved verbatim, not silently mis-slugged).
    f = {"id": "g", "type": "checkbox", "pdf_field_name": "G[0]", "options": [
        {"value": "DUP", "label": "Alpha", "pdf_field_name": "G[0]"},
        {"value": "DUP", "label": "Beta", "pdf_field_name": "G[1]"}]}
    out, rep = mig.migrate(_v1([f]))
    assert rep["duplicate_option_values"] == [{"field": "g", "values": ["DUP"]}]
    # The map does NOT contain the ambiguous 'DUP' key.
    assert "DUP" not in rep["slug_maps"].get("g", {})


# --- idempotency + version stamp --------------------------------------------

def test_migrate_stamps_v2_and_is_idempotent():
    f = {"id": "g", "type": "checkbox", "pdf_field_name": "G[0]", "options": [
        {"value": "G[0]", "label": "Alpha", "pdf_field_name": "G[0]"},
        {"value": "G[1]", "label": "Beta", "pdf_field_name": "G[1]"}]}
    once, _ = mig.migrate(_v1([f]))
    assert once["schema_version"] == vocab.SCHEMA_VERSION_V2
    twice, rep = mig.migrate(once)
    assert twice == once  # idempotent
    assert rep["checkbox_groups"] == []  # a no-op on an already-v2 schema


# --- the real i-90 schema (exit criterion 1) --------------------------------

def _i90_dump():
    import acroform_dump  # from scripts/bakeoff on sys.path
    return acroform_dump.dump_pdf(str(_I90_PDF))


_ARCHIVED = _REPO / "form-kits" / "i-90" / "schema_archived.json"


@pytest.mark.skipif(not _ARCHIVED.exists(), reason="i-90 v1 archive not present")
def test_migrated_i90_validates_v2_lints_clean_and_is_idempotent():
    # Migrate from the ARCHIVED v1 original (the committed schema.json is now the
    # migrated v2 result, bd c5r8 -- migrating IT would hit the idempotent no-op).
    orig = json.loads(_ARCHIVED.read_text(encoding="utf-8"))
    dump = _i90_dump()
    migrated, report = mig.migrate(orig, dump)
    # Validates as v2.
    FormSchema.model_validate(migrated)
    # Lints clean (dump-aware).
    assert not has_errors(lint_schema(migrated, dump))
    # Field count preserved (baseline 132).
    assert len(migrated["fields"]) == 132
    # Idempotent.
    assert mig.migrate(migrated, dump)[0] == migrated
    # controls_fields is DELETED from v2 (bd h76m.16): every i-90 edge is an
    # `unlocks` action, which has no target-side show_if/require_if equivalent, so
    # each is REPORTED as unconverted (never silently lost). They are behaviorally
    # redundant here anyway -- every target already carries its own show_if plus
    # conditional_behavior.unlock_method=flip_readonly_bit, which does the actual
    # unlocking -- so the migrated schema has ZERO controls_fields left.
    assert all("controls_fields" not in f for f in migrated["fields"])
    assert report["unmirrored_controls"]  # the unlocks are reported for review
    assert all(u["unconverted_actions"] for u in report["unmirrored_controls"])
    # No ambiguous duplicate option values or unresolved trigger refs on i-90.
    assert report["duplicate_option_values"] == []
    assert report.get("unresolved_trigger_refs", []) == []
