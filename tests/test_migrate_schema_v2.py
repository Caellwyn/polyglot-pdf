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

def test_mirrored_controls_field_is_dropped():
    # trigger controls target; target's show_if MATCHES on field+operator+value.
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "R[0]", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "R[1]", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "R[0]",
                             "unlocks": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]",
              "show_if": {"field": "trg", "operator": "equals", "value": "R[0]"}}
    out, rep = mig.migrate(_v1([trigger, target]))
    assert "controls_fields" not in out["fields"][0]  # mirrored -> dropped
    assert rep["controls_fields_dropped"] == 1
    assert rep["unmirrored_controls"] == []


def test_controls_edge_on_a_DIFFERENT_value_is_not_mirrored():
    # fresh-eyes: the edge gates on option R[0] but the target's show_if gates on
    # a DIFFERENT option R[1] -- these are distinct conditions, NOT a mirror, so
    # the edge must be REPORTED + kept (a value-blind check would drop it).
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "R[0]", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "R[1]", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "R[0]",
                             "unlocks": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]",
              "show_if": {"field": "trg", "operator": "equals", "value": "R[1]"}}
    out, rep = mig.migrate(_v1([trigger, target]))
    assert out["fields"][0].get("controls_fields"), "distinct-value edge must be kept"
    assert rep["controls_fields_dropped"] == 0
    assert rep["unmirrored_controls"] and rep["unmirrored_controls"][0]["targets"] == ["tgt"]
    # The surviving edge is MIGRATED to v2 (value -> new slug), not stale.
    kept = out["fields"][0]["controls_fields"][0]
    assert kept["value"] == "yes"  # slug for R[0]'s label "Yes"


def test_unmirrored_controls_field_is_reported_and_kept():
    # target has NO condition at all -> the edge is reported, not silently lost.
    trigger = {"id": "trg", "type": "radio", "pdf_field_name": "R[0]", "options": [
        {"value": "R[0]", "label": "Yes", "pdf_field_name": "R[0]"},
        {"value": "R[1]", "label": "No", "pdf_field_name": "R[1]"}],
        "controls_fields": [{"operator": "equals", "value": "R[0]",
                             "unlocks": ["tgt"]}]}
    target = {"id": "tgt", "type": "text", "pdf_field_name": "T[0]"}
    out, rep = mig.migrate(_v1([trigger, target]))
    assert out["fields"][0].get("controls_fields")  # kept for the human
    assert rep["controls_fields_dropped"] == 0
    assert rep["unmirrored_controls"] and rep["unmirrored_controls"][0]["targets"] == ["tgt"]


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


@pytest.mark.skipif(not _I90.exists(), reason="i-90 kit not present")
def test_migrated_i90_validates_v2_lints_clean_and_is_idempotent():
    orig = json.loads(_I90.read_text(encoding="utf-8"))
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
    # The i-90 has 3 controls_fields edges whose target-side condition gates on a
    # DIFFERENT option value than the edge (genuinely distinct conditions on the
    # same 12-option group) -- these are correctly REPORTED (not silently dropped,
    # fresh-eyes) and KEPT (migrated to v2 slugs, so still lint-clean above).
    assert len(report["unmirrored_controls"]) == 3
    # No ambiguous duplicate option values or unresolved trigger refs on i-90.
    assert report["duplicate_option_values"] == []
    assert report.get("unresolved_trigger_refs", []) == []
