"""Tests for backend/services/schema_lint.py (bd polyglot-pdf-h76m.5, P2.1).

Exit-criterion 1: hand-broken fixtures trip each lint rule exactly once each.
Every fixture below is the minimal valid-but-for-one-defect schema, and each
test asserts BOTH that its rule fires exactly once AND that no other rule
fires -- a fixture that trips two rules would hide a rule regression.

Exit-criterion 2: the shipped i-90 + w7 kits lint clean (they are the
promotion gate's real traffic); the archived broken W-7 draft (the extraction
failure that triggered the epic) lints RED with the invented operators named.

ASCII only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services.schema_lint import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    has_errors,
    lint_schema,
    summarize,
)

_REPO = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _schema(fields, version=None):
    s = {"source": "pdf", "fields": fields}
    if version is not None:
        s["schema_version"] = version
    return s


def _select(fid="picker", options=("alpha", "beta")):
    return {
        "id": fid,
        "type": "select",
        "options": [{"value": v, "label": v.title()} for v in options],
    }


def _rules(findings):
    return [f.rule for f in findings]


# ---------------------------------------------------------------------------
# One hand-broken fixture per rule (each trips its rule EXACTLY once).
# ---------------------------------------------------------------------------

def test_unknown_operator_trips_once():
    fields = [
        _select(),
        {"id": "dep", "type": "text",
         "show_if": {"field": "picker", "operator": "is_selected", "value": "alpha"}},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["unknown-operator"]
    assert "is_selected" in findings[0].message
    # The message names the allowed set so the finding is actionable.
    assert "allowed:" in findings[0].message


def test_value_arity_trips_once():
    fields = [
        _select(),
        {"id": "dep", "type": "text",
         # `in` requires a LIST value; a scalar is the arity violation.
         "show_if": {"field": "picker", "operator": "in", "value": "alpha"}},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["value-arity"]


def test_option_value_missing_trips_once():
    fields = [
        {"id": "picker", "type": "select",
         "options": [{"value": "alpha", "label": "Alpha"}, {"label": "No Value"}]},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["option-value-missing"]


def test_option_value_duplicate_trips_once():
    fields = [
        {"id": "picker", "type": "select",
         "options": [{"value": "same", "label": "A"}, {"value": "same", "label": "B"}]},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["option-value-duplicate"]
    assert "'same'" in findings[0].message


def test_option_value_comma_trips_once():
    fields = [
        {"id": "picker", "type": "select",
         "options": [{"value": "a,b", "label": "A"}, {"value": "c", "label": "C"}]},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["option-value-comma"]


def test_option_value_slug_trips_once_v2_only():
    fields = [
        {"id": "picker", "type": "select",
         "options": [{"value": "Bad Slug", "label": "A"}, {"value": "ok", "label": "B"}]},
    ]
    # v1: no slug convention -- clean.
    assert lint_schema(_schema(fields)) == []
    # v2: the slug rule fires exactly once.
    findings = lint_schema(_schema(fields, version="2"))
    assert _rules(findings) == ["option-value-slug"]


def test_ref_unresolved_field_trips_once():
    fields = [
        {"id": "dep", "type": "text",
         "show_if": {"field": "ghost", "operator": "is_not_empty"}},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["ref-unresolved-field"]
    assert "'ghost'" in findings[0].message


def test_ref_option_value_trips_once():
    fields = [
        _select(),
        {"id": "dep", "type": "text",
         "show_if": {"field": "picker", "operator": "equals", "value": "zzz"}},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["ref-option-value"]


def test_condition_malformed_trips_once():
    fields = [
        {"id": "dep", "type": "text", "show_if": "when the moon is full"},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["condition-malformed"]


def test_composite_depth_trips_once():
    fields = [
        _select(),
        {"id": "dep", "type": "text",
         "show_if": {"all_of": [
             {"any_of": [{"field": "picker", "operator": "equals", "value": "alpha"}]},
         ]}},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["composite-depth"]


def test_show_if_cycle_warns_once():
    fields = [
        {"id": "a", "type": "text",
         "show_if": {"field": "b", "operator": "is_not_empty"}},
        {"id": "b", "type": "text",
         "show_if": {"field": "a", "operator": "is_not_empty"}},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["show-if-cycle"]
    assert findings[0].severity == SEVERITY_WARNING
    assert not has_errors(findings)


def test_dump_widget_multiclaim_trips_once():
    fields = [
        {"id": "a", "type": "text", "pdf_field_name": "f1[0]"},
        {"id": "b", "type": "text", "pdf_field_name": "f1[0]"},
    ]
    dump = {"fields": [{"name": "top[0].page1[0].f1[0]"}]}
    findings = lint_schema(_schema(fields), dump)
    assert _rules(findings) == ["dump-widget-multiclaim"]
    assert "a, b" in findings[0].message  # names both claimants


def test_dump_multiclaim_by_two_options_of_one_field():
    # The shipped-f1040 class of bug: one field's two options mapped to the
    # same widget -- selecting one would check both.
    fields = [
        {"id": "g", "type": "radio", "options": [
            {"value": "x", "label": "X", "pdf_field_name": "c1[0]"},
            {"value": "y", "label": "Y", "pdf_field_name": "c1[0]"},
        ]},
    ]
    dump = {"fields": [{"name": "top[0].c1[0]"}]}
    findings = lint_schema(_schema(fields), dump)
    assert _rules(findings) == ["dump-widget-multiclaim"]


# ---------------------------------------------------------------------------
# Deliberate non-findings: the tolerances that keep shipped v1 kits clean.
# ---------------------------------------------------------------------------

def test_groups_of_one_field_plus_own_option_claim_is_benign():
    # The v1 standalone-checkbox convention: field-level pdf_field_name AND a
    # single option describing the same widget. Not a multi-claim.
    fields = [
        {"id": "solo", "type": "checkbox", "pdf_field_name": "cb[0]",
         "options": [{"value": "cb[0]", "label": "Yes", "pdf_field_name": "cb[0]"}]},
    ]
    dump = {"fields": [{"name": "top[0].cb[0]"}]}
    assert lint_schema(_schema(fields), dump) == []


def test_empty_string_value_is_the_v1_emptiness_idiom_not_a_bad_option_ref():
    fields = [
        _select(),
        {"id": "dep", "type": "text",
         "show_if": {"field": "picker", "operator": "not_equals", "value": ""}},
    ]
    assert lint_schema(_schema(fields)) == []


def test_vestigial_value_on_no_value_operator_is_tolerated():
    fields = [
        _select(),
        {"id": "dep", "type": "text",
         "show_if": {"field": "picker", "operator": "is_not_empty", "value": "x"}},
    ]
    assert lint_schema(_schema(fields)) == []


def test_controls_fields_get_operator_and_action_ref_checks():
    fields = [
        {"id": "trigger", "type": "select",
         "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
         "controls_fields": [
             {"operator": "equals", "value": "a", "unlocks": ["ghost"]},
         ]},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["ref-unresolved-field"]
    assert "ghost" in findings[0].message


def test_composite_v2_group_with_valid_atoms_is_clean():
    fields = [
        _select(),
        {"id": "dep", "type": "text",
         "show_if": {
             "all_of": [{"field": "picker", "operator": "equals", "value": "alpha"}],
             "none_of": [{"field": "picker", "operator": "equals", "value": "beta"}],
         }},
    ]
    assert lint_schema(_schema(fields)) == []


def test_lint_never_raises_on_garbage():
    assert has_errors(lint_schema("not even a dict"))
    assert lint_schema({"fields": "oops"}) == []  # non-dict fields are skipped
    assert lint_schema({}) == []


# ---------------------------------------------------------------------------
# Real artifacts: shipped kits lint clean; the archived broken draft is RED.
# ---------------------------------------------------------------------------

def _load_kit_schema(kit):
    path = _REPO / "form-kits" / kit / "schema.json"
    if not path.exists():
        pytest.skip(f"{kit} kit not present")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("kit", ["i-90", "w7", "w7-2"])
def test_shipped_kits_lint_clean(kit):
    findings = lint_schema(_load_kit_schema(kit))
    assert findings == [], f"{kit}: {summarize(findings)}: " + "; ".join(
        f"{f.rule} {f.path}" for f in findings[:5]
    )


def test_f1040_duplicate_option_values_are_caught():
    # The shipped f1040 filing-status bug (plan "Additional live bugs"):
    # duplicate option values mean selecting one checks two widgets. The kit
    # stays red until repaired/re-extracted (P6.1) -- this pins that lint SEES it.
    findings = lint_schema(_load_kit_schema("f1040"))
    assert has_errors(findings)
    assert all(f.rule == "option-value-duplicate" for f in findings)


def test_archived_broken_w7_draft_lints_red():
    """The W-7 draft that triggered the epic: invented operators + an 8-option
    group whose values are all "1". Lint must be RED naming both defects --
    and must NOT crash even though this draft fails FormSchema.model_validate."""
    draft = json.loads(
        (_FIXTURES / "w7_broken_draft.json").read_text(encoding="utf-8")
    )
    findings = lint_schema(draft)
    assert has_errors(findings)
    rules = set(_rules(findings))
    assert "unknown-operator" in rules
    assert "option-value-duplicate" in rules
    named = " ".join(f.message for f in findings)
    assert "is_selected" in named and "contains_any" in named
