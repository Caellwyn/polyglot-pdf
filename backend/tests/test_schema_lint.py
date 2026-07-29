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
    field_id_of,
    has_errors,
    lint_schema,
    summarize,
)

_REPO = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).resolve().parent / "fixtures"



def _lint_structural(schema, dump=None):
    """lint_schema minus the standing guidance-coverage/quality worklist
    (help-* WARNINGs, bd wsao.3): these structural-defect tests assert on
    schema DEFECTS, and a fixture without authored help.instructions now
    legitimately carries the aggregated coverage warning -- orthogonal to
    what each test pins. The guidance rules have their own suite
    (backend/tests/unit/test_guidance_contract.py)."""
    return [f for f in lint_schema(schema, dump)
            if not f.rule.startswith("help-")]

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
    """Rule ids minus the standing guidance worklist (help-*, bd wsao.3):
    these structural tests pin exact defect lists, and a fixture without
    authored help.instructions legitimately carries the aggregated coverage
    warning -- orthogonal noise here. The guidance rules have their own suite
    (backend/tests/unit/test_guidance_contract.py)."""
    return [f.rule for f in findings if not f.rule.startswith("help-")]


# ---------------------------------------------------------------------------
# One hand-broken fixture per rule (each trips its rule EXACTLY once).
# ---------------------------------------------------------------------------

def test_unknown_operator_trips_once():
    fields = [
        _select(),
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
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
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
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
    assert _lint_structural(_schema(fields)) == []
    # v2: the slug rule fires exactly once.
    findings = lint_schema(_schema(fields, version="2"))
    assert _rules(findings) == ["option-value-slug"]


def test_ref_unresolved_field_trips_once():
    fields = [
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
         "show_if": {"field": "ghost", "operator": "is_not_empty"}},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["ref-unresolved-field"]
    assert "'ghost'" in findings[0].message


def test_operator_trigger_trips_once():
    fields = [
        {"id": "freetext", "type": "text", "pdf_field_name": "freetext[0]"},
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
         # includes is a checkbox_group membership operator; a text trigger
         # has no evaluator branch for it (Codex PR #302).
         "show_if": {"field": "freetext", "operator": "includes", "value": "x"}},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["operator-trigger"]
    assert "'includes'" in findings[0].message


def test_v1_is_checked_on_option_bearing_trigger_is_tolerated():
    # The shipped vq4m-era idiom (i-90 uses is_checked on radio groups);
    # P6.1 migrates it to is_not_empty. Tolerated on v1, an error on v2.
    fields = [
        {"id": "grp", "type": "radio",
         "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]},
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
         "show_if": {"field": "grp", "operator": "is_checked"}},
    ]
    assert _lint_structural(_schema(fields)) == []
    findings = lint_schema(_schema(fields, version="2"))
    assert _rules(findings) == ["operator-trigger"]


def test_ref_option_value_trips_once():
    fields = [
        _select(),
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
         "show_if": {"field": "picker", "operator": "equals", "value": "zzz"}},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["ref-option-value"]


def test_condition_malformed_trips_once():
    fields = [
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]", "show_if": "when the moon is full"},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["condition-malformed"]


def test_composite_depth_trips_once():
    fields = [
        _select(),
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
         "show_if": {"all_of": [
             {"any_of": [{"field": "picker", "operator": "equals", "value": "alpha"}]},
         ]}},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["composite-depth"]


def test_show_if_cycle_warns_once():
    fields = [
        {"id": "a", "type": "text", "pdf_field_name": "a[0]",
         "show_if": {"field": "b", "operator": "is_not_empty"}},
        {"id": "b", "type": "text", "pdf_field_name": "b[0]",
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
# Under-claim: a dump widget NO field maps to (extraction dropped it).
# bd polyglot-pdf-w0eq, P6.1c.
# ---------------------------------------------------------------------------

def test_unclaimed_fillable_widget_warns():
    # The stochastic-drop bug: the dump has a text widget no field claims. A
    # WARNING (not ERROR) so it never breaks the store-with-issues exit code.
    fields = [{"id": "a", "type": "text", "pdf_field_name": "f1[0]"}]
    dump = {"fields": [
        {"name": "top[0].f1[0]", "logical_type": "text"},
        {"name": "top[0].f2[0]", "logical_type": "text"},  # unclaimed
    ]}
    findings = lint_schema(_schema(fields), dump)
    assert _rules(findings) == ["dump-widget-unclaimed"]
    unclaimed = [f for f in findings if f.rule == "dump-widget-unclaimed"][0]
    assert unclaimed.severity == "WARNING"
    assert "f2[0]" in unclaimed.path
    assert not has_errors(findings)


def test_unclaimed_button_widget_is_not_a_finding():
    # A decorative reset/print button is legitimately unmodeled -- not a gap.
    fields = [{"id": "a", "type": "text", "pdf_field_name": "f1[0]"}]
    dump = {"fields": [
        {"name": "top[0].f1[0]", "logical_type": "text"},
        {"name": "top[0].reset[0]", "logical_type": "button"},
    ]}
    assert _lint_structural(_schema(fields), dump) == []


def test_all_widgets_claimed_emits_no_unclaimed_finding():
    fields = [
        {"id": "a", "type": "text", "pdf_field_name": "f1[0]"},
        {"id": "b", "type": "text", "pdf_field_name": "f2[0]"},
    ]
    dump = {"fields": [
        {"name": "top[0].f1[0]", "logical_type": "text"},
        {"name": "top[0].f2[0]", "logical_type": "text"},
    ]}
    assert _lint_structural(_schema(fields), dump) == []


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
    assert _lint_structural(_schema(fields), dump) == []


def test_empty_string_value_is_the_v1_emptiness_idiom_not_a_bad_option_ref():
    fields = [
        _select(),
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
         "show_if": {"field": "picker", "operator": "not_equals", "value": ""}},
    ]
    assert _lint_structural(_schema(fields)) == []


def test_vestigial_value_on_no_value_operator_is_tolerated_on_v1_only():
    fields = [
        _select(),
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
         "show_if": {"field": "picker", "operator": "is_not_empty", "value": "x"}},
    ]
    # v1: the operator ignores the stray value -- tolerated.
    assert _lint_structural(_schema(fields)) == []
    # v2: the model rejects this exact shape as an arity error, and lint must
    # agree on the Pydantic-rejected raw-draft path (Codex PR #302).
    findings = lint_schema(_schema(fields, version="2"))
    assert _rules(findings) == ["value-arity"]


def test_empty_composite_buckets_are_malformed():
    # ConditionGroup requires at least one non-empty bucket; the raw-draft
    # path must report the same shape instead of passing it clean.
    fields = [
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]", "show_if": {"all_of": []}},
    ]
    findings = lint_schema(_schema(fields))
    assert _rules(findings) == ["condition-malformed"]


def test_plain_string_options_get_value_hygiene_checks():
    # Legacy options: ["A", "B"] -- the string IS the value (the frontend's
    # optionValue() contract), so duplicates and commas must still be caught.
    dup = [{"id": "p", "type": "select", "options": ["same", "same"]}]
    findings = lint_schema(_schema(dup))
    assert _rules(findings) == ["option-value-duplicate"]

    comma = [{"id": "p", "type": "select", "options": ["a,b", "c"]}]
    findings = lint_schema(_schema(comma))
    assert _rules(findings) == ["option-value-comma"]

    # And condition values resolve against string options too.
    fields = [
        {"id": "p", "type": "select", "options": ["alpha", "beta"]},
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
         "show_if": {"field": "p", "operator": "equals", "value": "alpha"}},
    ]
    assert _lint_structural(_schema(fields)) == []


def test_readonly_conditional_no_unlock_warns():
    # bd 3fz7: a read_only field shown by a show_if but with no unlock_method is
    # permanently non-fillable when shown. WARNING (guardrail-first inventory).
    fields = [
        _select("trig"),
        {"id": "dep", "type": "checkbox", "read_only": True,
         "show_if": {"field": "trig", "operator": "equals", "value": "alpha"}},
    ]
    findings = lint_schema(_schema(fields))
    rel = [f for f in findings if f.rule == "readonly-conditional-no-unlock"]
    assert rel and rel[0].severity == SEVERITY_WARNING
    assert "id=dep" in rel[0].path


def test_readonly_conditional_WITH_unlock_is_clean():
    # The same field WITH conditional_behavior.unlock_method is fine (it unlocks
    # when shown -- i-90's 20 real read-only-text fields work this way).
    fields = [
        _select("trig"),
        {"id": "dep", "type": "checkbox", "read_only": True,
         "conditional_behavior": {"unlock_method": "flip_readonly_bit"},
         "show_if": {"field": "trig", "operator": "equals", "value": "alpha"}},
    ]
    findings = lint_schema(_schema(fields))
    assert "readonly-conditional-no-unlock" not in _rules(findings)


def test_readonly_but_NOT_conditional_does_not_warn():
    # A read_only field with NO show_if/require_if (e.g. a signature) is read-only
    # by nature, not a stuck-conditional -- must NOT trip the rule.
    fields = [
        {"id": "sig", "type": "signature", "read_only": True},
    ]
    findings = lint_schema(_schema(fields))
    assert "readonly-conditional-no-unlock" not in _rules(findings)


def test_readonly_conditional_with_NON_flip_unlock_still_warns():
    # bd rsy3: only unlock_method="flip_readonly_bit" actually lifts read_only in
    # FieldRenderer's shouldUnlock. A different value (e.g. set_property) leaves the
    # field permanently non-fillable when shown, so it MUST still warn.
    fields = [
        _select("trig"),
        {"id": "dep", "type": "checkbox", "read_only": True,
         "conditional_behavior": {"unlock_method": "set_property"},
         "show_if": {"field": "trig", "operator": "equals", "value": "alpha"}},
    ]
    findings = lint_schema(_schema(fields))
    rel = [f for f in findings if f.rule == "readonly-conditional-no-unlock"]
    assert rel and rel[0].severity == SEVERITY_WARNING


def test_readonly_conditional_unlock_via_LEGACY_conditional_logic_is_clean():
    # The legacy conditional_logic alias (still emitted by generated kits, e.g.
    # i-90) also lifts read_only in FieldRenderer, so a flip_readonly_bit there
    # must ALSO suppress the warning.
    fields = [
        _select("trig"),
        {"id": "dep", "type": "checkbox", "read_only": True,
         "conditional_logic": {"unlock_method": "flip_readonly_bit"},
         "show_if": {"field": "trig", "operator": "equals", "value": "alpha"}},
    ]
    findings = lint_schema(_schema(fields))
    assert "readonly-conditional-no-unlock" not in _rules(findings)


def test_readonly_unlock_check_never_throws_on_malformed_conditional_keys():
    # lint_schema must never raise on schema shape (POST /lint contract). A truthy
    # NON-dict conditional_behavior/conditional_logic must not crash has_unlock's
    # .get() -- it is treated as "no unlock" (so the field still warns).
    fields = [
        _select("trig"),
        {"id": "dep", "type": "checkbox", "read_only": True,
         "conditional_behavior": "garbage", "conditional_logic": ["also", "bad"],
         "show_if": {"field": "trig", "operator": "equals", "value": "alpha"}},
    ]
    findings = lint_schema(_schema(fields))  # must not raise
    rel = [f for f in findings if f.rule == "readonly-conditional-no-unlock"]
    assert rel and rel[0].severity == SEVERITY_WARNING


def test_readonly_conditional_via_require_if_only_warns():
    # The rule keys on show_if OR require_if -- a field made REQUIRED (not shown)
    # by a condition, read_only, no unlock, is equally stuck. Cover the require_if
    # branch (bd rsy3: the show_if branch was the only one tested).
    fields = [
        _select("trig"),
        {"id": "dep", "type": "checkbox", "read_only": True,
         "require_if": {"field": "trig", "operator": "equals", "value": "alpha"}},
    ]
    findings = lint_schema(_schema(fields))
    rel = [f for f in findings if f.rule == "readonly-conditional-no-unlock"]
    assert rel and rel[0].severity == SEVERITY_WARNING


def test_stale_controls_fields_on_a_v2_kit_is_a_lint_error():
    # controls_fields was DELETED at the P6.2 flip (bd h76m.16); the model IGNORES
    # the extra key, so a stale/mis-migrated V2 kit still carrying it would publish
    # with its trigger-side behavior silently dropped. Lint ERRORs on a V2 schema
    # so the mark-complete gate rejects it (Codex PR #346).
    fields = [
        {"id": "trigger", "type": "select",
         "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
         "controls_fields": [
             {"operator": "equals", "value": "a", "shows": ["ghost"]},
         ]},
    ]
    findings = lint_schema(_schema(fields, version="2"))
    assert "legacy-trigger-side-logic" in _rules(findings)
    assert has_errors(findings)


def test_stale_conditional_fields_on_a_v2_kit_is_a_lint_error():
    fields = [
        {"id": "trigger", "type": "text", "pdf_field_name": "trigger[0]", "conditional_fields": ["dep"]},
    ]
    findings = lint_schema(_schema(fields, version="2"))
    assert "legacy-trigger-side-logic" in _rules(findings)


def test_top_level_required_on_a_v2_kit_is_a_lint_error():
    # required must live at validation.required (the shape every kit + the frontend
    # isFieldRequired reader consume); a top-level required is read by no consumer
    # and the field is silently optional (bd polyglot-pdf-a1ql).
    fields = [
        {"id": "acct", "type": "text", "pdf_field_name": "acct[0]", "required": True},
    ]
    findings = lint_schema(_schema(fields, version="2"))
    assert "required-top-level" in _rules(findings)
    assert has_errors(findings)


def test_validation_required_on_a_v2_kit_is_clean():
    # The canonical location does NOT trip the rule.
    fields = [
        {"id": "acct", "type": "text", "pdf_field_name": "acct[0]", "validation": {"required": True}},
    ]
    findings = lint_schema(_schema(fields, version="2"))
    assert "required-top-level" not in _rules(findings)


def test_top_level_required_on_a_v1_draft_is_NOT_flagged():
    # A raw pre-migration/prior-extractor draft carrying top-level required is not
    # v2-stamped, so it is not yet held to the canonical shape (mirrors the
    # controls_fields v1 tolerance below).
    fields = [
        {"id": "acct", "type": "text", "pdf_field_name": "acct[0]", "required": True},
    ]
    findings = lint_schema(_schema(fields))  # no version -> v1 draft
    assert "required-top-level" not in _rules(findings)


def test_controls_fields_on_a_v1_draft_is_NOT_flagged():
    # A raw pre-migration extraction draft (no v2 stamp) legitimately still
    # carries controls_fields until the repair/migrate pipeline converts it; lint
    # runs on that draft mid-pipeline and must NOT ERROR on it (else the
    # broken-draft-repairs-to-lint-clean contract breaks -- CI regression).
    fields = [
        {"id": "trigger", "type": "select",
         "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
         "controls_fields": [
             {"operator": "equals", "value": "a", "shows": ["ghost"]},
         ]},
    ]
    findings = lint_schema(_schema(fields))  # no version -> v1 draft
    assert "legacy-trigger-side-logic" not in _rules(findings)


def test_composite_v2_group_with_valid_atoms_is_clean():
    fields = [
        _select(),
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
         "show_if": {
             "all_of": [{"field": "picker", "operator": "equals", "value": "alpha"}],
             "none_of": [{"field": "picker", "operator": "equals", "value": "beta"}],
         }},
    ]
    assert _lint_structural(_schema(fields)) == []


def test_lint_never_raises_on_garbage():
    assert has_errors(lint_schema("not even a dict"))
    assert _lint_structural({"fields": "oops"}) == []  # non-list fields -> empty
    assert _lint_structural({"fields": 123}) == []     # non-iterable too (PR #302)
    assert _lint_structural({"fields": [None, 42, "x"]}) == []  # non-dict members
    assert _lint_structural({}) == []


def test_non_list_options_never_crash_any_pass():
    # Codex PR #302 round 2: malformed `options` (a number) reached raw
    # iteration in BOTH the option-reference check and the dump-claim pass.
    fields = [
        {"id": "weird", "type": "select", "options": 5,
         "pdf_field_name": "w[0]"},
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
         "show_if": {"field": "weird", "operator": "equals", "value": "x"}},
    ]
    dump = {"fields": [{"name": "top[0].w[0]"}]}
    findings = lint_schema(_schema(fields), dump)  # must not raise
    assert all(isinstance(f.rule, str) for f in findings)


def test_long_acyclic_show_if_chain_does_not_overflow():
    # Codex PR #302 round 2: recursive DFS hit Python's recursion limit on
    # long chains; the iterative walk must handle depth > 1000 and stay quiet.
    n = 2000
    # Every synthetic field carries a widget name: under the sprint-17 ledger
    # rules a name-less text field is itself a defect (field-unbacked), and
    # this test pins ONLY the deep-chain walk staying quiet.
    fields = [{"id": "f0", "type": "text", "pdf_field_name": "f0[0]"}]
    fields += [
        {"id": f"f{i}", "type": "text", "pdf_field_name": f"f{i}[0]",
         "show_if": {"field": f"f{i-1}", "operator": "is_not_empty"}}
        for i in range(1, n)
    ]
    assert _lint_structural(_schema(fields)) == []


# ---------------------------------------------------------------------------
# Real artifacts: shipped kits lint clean; the archived broken draft is RED.
# ---------------------------------------------------------------------------

def _load_kit_schema(kit):
    path = _REPO / "form-kits" / kit / "schema.json"
    if not path.exists():
        pytest.skip(f"{kit} kit not present")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("kit", ["i-90", "w7"])
def test_shipped_kits_lint_error_free(kit):
    # The promotion gate is zero ERRORs (WARNINGs never block). Post the
    # guardrail-first inventory (bd h76m.16 follow-up), the shipped kits DO carry
    # known WARNINGs (i-90's readonly-conditional-no-unlock + dump-widget-unclaimed,
    # bd 3fz7/0nxh) -- those are inventoried by test_kit_unfillable_field_inventory
    # below, not asserted away here. This test pins only that no ERROR ships.
    findings = lint_schema(_load_kit_schema(kit))
    assert not has_errors(findings), f"{kit}: " + "; ".join(
        f"{f.rule} {f.path}" for f in findings if f.severity == SEVERITY_ERROR
    )


def _dump_kit(kit):
    """A live AcroForm dump of a shipped kit's PDF (no paid API). Skips if the
    kit / PDF / bakeoff tooling is absent."""
    import sys
    pdf = _REPO / "form-kits" / kit / "form.pdf"
    if not pdf.exists():
        pytest.skip(f"{kit} form.pdf not present")
    bakeoff = _REPO / "scripts" / "bakeoff"
    sys.path.insert(0, str(bakeoff))
    try:
        import acroform_dump
    except ImportError:
        pytest.skip("acroform_dump (scripts/bakeoff) not importable")
    return acroform_dump.dump_pdf(str(pdf))


# The "unfillable field" inventory (bd h76m.16 follow-up, guardrail-first): the
# CURRENT, KNOWN count per kit of the two warning classes that mean "a field/widget
# exists but can't be filled through the app":
#   - dump-widget-unclaimed: a real fillable PDF widget with NO schema field
#     (extraction dropped it) -- i-90's 4 were FIXED by bd 0nxh (now 0); f1040
#     still has 12; w7 has 2 (the box-h "Other" reason text line
#     f1_04 and the 6d "Other" ID-document text line f1_23 -- both surfaced as
#     genuinely unmodeled once bd polyglot-pdf-ivh9 corrected the field-to-widget
#     off-by-one that had been mis-parking treaty_country / id_number on them;
#     modeling those two "Other" free-text lines is a follow-up bead).
#   - readonly-conditional-no-unlock: a read_only field shown/required by a
#     condition but with no unlock_method -- bd 3fz7 fixed i-90's 3 (p4_checkbox1a/
#     b/c now carry flip_readonly_bit), so i-90 is now 0.
# These are WARNINGs (they do not block promotion). This baseline pins the current
# state so a NEW regression (a fresh dropped widget / stuck field) fails CI, while
# fixing a form's data (which LOWERS a count) also fails -- prompting a deliberate
# baseline update as the inventory shrinks toward zero.
_UNFILLABLE_BASELINE = {
    "i-90": {"dump-widget-unclaimed": 0, "readonly-conditional-no-unlock": 0},
    "w7": {"dump-widget-unclaimed": 2, "readonly-conditional-no-unlock": 0},
    "f1040": {"dump-widget-unclaimed": 12, "readonly-conditional-no-unlock": 0},
}


@pytest.mark.parametrize("kit", ["i-90", "w7", "f1040"])
def test_kit_unfillable_field_inventory(kit):
    # Lint each committed kit WITH its AcroForm dump and pin the count of each
    # "unfillable field" warning class against the known baseline. A mismatch is
    # intentional-failure-to-force-review: either a regression (count went UP) or a
    # form fix (count went DOWN, update the baseline). Fixing the underlying data
    # is tracked per-kit (bd 0nxh, 3fz7); this test is the systemic guardrail.
    findings = lint_schema(_load_kit_schema(kit), _dump_kit(kit))
    counts = {rule: sum(1 for f in findings if f.rule == rule)
              for rule in ("dump-widget-unclaimed", "readonly-conditional-no-unlock")}
    assert counts == _UNFILLABLE_BASELINE[kit], (
        f"{kit}: unfillable-field inventory changed. Got {counts}, baseline "
        f"{_UNFILLABLE_BASELINE[kit]}. If a form was fixed, lower the baseline; "
        f"if this is a new regression, a real widget/field is now unfillable."
    )


def test_i90_dump_unclaimed_excludes_machine_barcodes():
    # Regression guard for the bug caught pre-PR (bd polyglot-pdf-w0eq): the
    # dump-widget-unclaimed rule MUST run WITH a dump (the parametrized test above
    # passes no dump, so the rule never fired on a real kit). i-90's 7 hidden
    # PDF417 barcode widgets are machine-generated, NOT user fields -- they must
    # NOT be flagged as coverage gaps, even though they are read-only text (i-90
    # deliberately fills 20 real read-only-text fields via flip_readonly_bit, so
    # read-only is not a valid "unfillable" signal). Any unclaimed finding that
    # DOES survive must be a genuine fillable widget, never a barcode.
    dump = _dump_kit("i-90")
    findings = lint_schema(_load_kit_schema("i-90"), dump)
    unclaimed = [f for f in findings if f.rule == "dump-widget-unclaimed"]
    for f in unclaimed:
        low = f.path.lower()
        assert "barcode" not in low and "pdf417" not in low, (
            f"a machine barcode was wrongly flagged as a coverage gap: {f.path}"
        )


def test_f1040_duplicate_option_values_are_resolved_post_migration():
    # The shipped f1040 filing-status bug (plan "Additional live bugs"): dup
    # option values meant selecting one checked two widgets. Migrating f1040 to
    # v2 (bd h76m.16, P6.2) mints unique semantic slugs per field, RESOLVING it.
    # The kit now lints clean (no option-value-duplicate).
    findings = lint_schema(_load_kit_schema("f1040"))
    assert not any(f.rule == "option-value-duplicate" for f in findings)


def test_archived_broken_w7_draft_lints_red():
    """The W-7 draft that triggered the epic: invented operators + an 8-option
    group whose values are all "1". Lint must be RED naming those defects --
    and must NOT crash even though this draft fails FormSchema.model_validate.
    (Post the P6.2 flip, controls_fields is unlinted -- the invented operators
    that lived inside it no longer surface -- but the show_if-side defects and
    the duplicate-option-value defect still make the draft RED.)"""
    draft = json.loads(
        (_FIXTURES / "w7_broken_draft.json").read_text(encoding="utf-8")
    )
    findings = lint_schema(draft)
    assert has_errors(findings)
    rules = set(_rules(findings))
    assert "unknown-operator" in rules
    assert "option-value-duplicate" in rules


# ---------------------------------------------------------------------------
# field_id_of + as_dict: the editor's ValidationPanel focuses a finding by the
# field id carried in its path (bd h76m.11, P4.3). One Python implementation.
# ---------------------------------------------------------------------------

def test_field_id_of_extracts_the_anchored_field():
    assert field_id_of("fields[3] (id=picker).show_if") == "picker"
    assert field_id_of("fields[0] (id=dep).require_if") == "dep"
    # show-if-cycle warnings use the "fields (id=X)" (no index) path shape.
    assert field_id_of("fields (id=loop_a)") == "loop_a"


def test_field_id_of_returns_none_for_unanchored_paths():
    # Non-field paths (schema root, dump widget claims) have no id to focus.
    assert field_id_of("$") is None
    assert field_id_of("widget 'topmostSubform[0].Page1[0].f1[0]'") is None
    # A field with no id key renders as "(id=None)" -- nothing to focus.
    assert field_id_of("fields[0] (id=None).show_if") is None
    assert field_id_of("") is None


def test_as_dict_carries_the_derived_field_id():
    fields = [
        _select(),
        {"id": "dep", "type": "text", "pdf_field_name": "dep[0]",
         "show_if": {"field": "picker", "operator": "is_selected", "value": "alpha"}},
    ]
    findings = lint_schema(_schema(fields))
    assert findings, "expected the unknown-operator finding"
    d = findings[0].as_dict()
    assert set(d) == {"severity", "rule", "path", "message", "field_id"}
    assert d["field_id"] == "dep"
    assert d["rule"] == "unknown-operator"


def test_archived_broken_w7_draft_findings_all_carry_field_focus():
    """Every finding the W-7 draft produces anchors to a real field (P4.3's
    'lists N findings with field focus'): each field_id resolves to a field in
    the draft, so the panel can jump to every one."""
    draft = json.loads(
        (_FIXTURES / "w7_broken_draft.json").read_text(encoding="utf-8")
    )
    ids = {f["id"] for f in draft["fields"] if isinstance(f, dict) and "id" in f}
    # The aggregated guidance-coverage worklist (help-*, bd wsao.3) anchors at
    # $.fields by design (one finding per SCHEMA, not per field) -- it is the
    # documented exception to the every-finding-focusable contract, so the
    # focus assertion runs over the structural findings only.
    findings = [f for f in lint_schema(draft)
                if not f.rule.startswith("help-")]
    dicts = [f.as_dict() for f in findings]
    assert dicts, "the broken draft must produce findings"
    for d in dicts:
        assert d["field_id"] is not None, f"unfocusable finding: {d['path']}"
        assert d["field_id"] in ids, f"finding points at a missing field: {d}"


# ---------------------------------------------------------------------------
# 'To review' review gate (bd polyglot-pdf-6cfu.3): to-review-pending
# ---------------------------------------------------------------------------


def test_to_review_field_trips_once_per_field():
    # A field still filed in a sec_to_review* section is an ERROR (the publish
    # gate blocks on it); the section entry listing the same field does NOT
    # double-report.
    s = _schema([
        {"id": "f1", "type": "text", "pdf_field_name": "f1[0]", "section_id": "sec_to_review_p1"},
        {"id": "f2", "type": "text", "pdf_field_name": "f2[0]", "section_id": "sec_real"},
    ])
    s["sections"] = [
        {"id": "sec_to_review_p1", "label": "To review", "order": 1,
         "fields": ["f1"]},
        {"id": "sec_real", "label": "Real", "order": 2, "fields": ["f2"]},
    ]
    findings = [f for f in lint_schema(s) if f.rule == "to-review-pending"]
    assert len(findings) == 1
    assert findings[0].severity == SEVERITY_ERROR
    assert "f1" in findings[0].path


def test_to_review_unplaced_section_id_also_trips():
    s = _schema([
        {"id": "f1", "type": "text", "pdf_field_name": "f1[0]", "section_id": "sec_to_review_unplaced"},
    ])
    findings = [f for f in lint_schema(s) if f.rule == "to-review-pending"]
    assert len(findings) == 1


def test_to_review_stale_section_list_trips_section_level():
    # The field was re-pointed to a real section but the to-review section's
    # fields[] list still names it: one section-level finding.
    s = _schema([
        {"id": "f1", "type": "text", "pdf_field_name": "f1[0]", "section_id": "sec_real"},
    ])
    s["sections"] = [
        {"id": "sec_to_review_p1", "label": "To review", "order": 1,
         "fields": ["f1"]},
        {"id": "sec_real", "label": "Real", "order": 2, "fields": ["f1"]},
    ]
    findings = [f for f in lint_schema(s) if f.rule == "to-review-pending"]
    assert len(findings) == 1
    assert "sec_to_review_p1" in findings[0].path


def test_emptied_to_review_section_is_clean():
    # An emptied to-review section (fields re-filed, list emptied) no longer
    # blocks -- the reviewer may delete it or leave the empty husk.
    s = _schema([
        {"id": "f1", "type": "text", "pdf_field_name": "f1[0]", "section_id": "sec_real"},
    ])
    s["sections"] = [
        {"id": "sec_to_review_p1", "label": "To review", "order": 1,
         "fields": []},
        {"id": "sec_real", "label": "Real", "order": 2, "fields": ["f1"]},
    ]
    assert [f for f in lint_schema(s) if f.rule == "to-review-pending"] == []


def test_ordinary_sections_never_trip_to_review():
    s = _schema([
        {"id": "f1", "type": "text", "pdf_field_name": "f1[0]", "section_id": "sec_normal"},
    ])
    s["sections"] = [
        {"id": "sec_normal", "label": "Normal", "order": 1, "fields": ["f1"]},
    ]
    assert [f for f in lint_schema(s) if f.rule == "to-review-pending"] == []


# ---------------------------------------------------------------------------
# Translation verify/rectify flags (bd polyglot-pdf-9djc): the bake persists
# LintFinding-shaped flags at _bakeoff.authoring.option_translation.flags and
# lint RE-EMITS them, so the editor ValidationPanel shows the translation
# worklist on every lint pass.
# ---------------------------------------------------------------------------


def _with_translation_flags(flags):
    s = _schema([_select("sex", ("m", "f"))])
    s["_bakeoff"] = {"authoring": {"option_translation": {
        "changed": True, "failed_languages": [], "flags": flags,
    }}}
    return s


def test_translation_flags_reemitted_as_warning_findings():
    flag = {
        "severity": "WARNING",
        "rule": "translation-drift-unresolved",
        "path": "fields[0] (id=sex).options[m].label_translations.spanish",
        "message": "judge: meaning drift; kept the original",
        "field_id": "sex",
    }
    findings = lint_schema(_with_translation_flags([flag]))
    assert _rules(findings) == ["translation-drift-unresolved"]
    reemitted = [f for f in findings
                 if f.rule == "translation-drift-unresolved"][0]
    assert reemitted.severity == SEVERITY_WARNING
    assert reemitted.message == flag["message"]
    # The stored path round-trips through the SAME field-focus derivation as
    # native findings, so the panel can jump to the flagged field.
    assert reemitted.as_dict()["field_id"] == "sex"


def test_translation_flags_all_four_rules_pass_through():
    flags = [
        {"rule": rule, "path": "sections[s1].label_translations.urdu",
         "message": "m"}
        for rule in (
            "translation-drift-rectified", "translation-drift-unresolved",
            "translation-ambiguous-source", "translation-mechanical",
        )
    ]
    findings = lint_schema(_with_translation_flags(flags))
    assert sorted(_rules(findings)) == sorted(f["rule"] for f in flags)
    assert all(f.severity == SEVERITY_WARNING for f in findings)  # incl. help-*


def test_translation_flags_severity_is_pinned_warning():
    # A stored severity of ERROR must NOT block publish: flags inform, never
    # gate (the fail-open contract). Lint pins WARNING regardless.
    flag = {"severity": "ERROR", "rule": "translation-mechanical",
            "path": "p", "message": "m"}
    findings = lint_schema(_with_translation_flags([flag]))
    translation = [f for f in findings if f.rule.startswith("translation-")]
    assert [f.severity for f in translation] == [SEVERITY_WARNING]
    assert not has_errors(findings)


def test_translation_flags_malformed_slots_are_ignored():
    # Lint never throws on malformed input; a stale or hand-edited provenance
    # slot must not break linting -- junk entries are skipped, valid ones kept.
    flags = [
        "not-a-dict",
        {"rule": "translation-drift-unresolved"},              # no path/message
        {"rule": "some-other-rule", "path": "p", "message": "m"},  # unknown rule
        {"rule": "translation-mechanical", "path": "p", "message": "m"},
    ]
    findings = lint_schema(_with_translation_flags(flags))
    assert _rules(findings) == ["translation-mechanical"]
    # Malformed containers at every level: no crash, no findings.
    for bakeoff in (None, "junk", {"authoring": "junk"},
                    {"authoring": {"option_translation": "junk"}},
                    {"authoring": {"option_translation": {"flags": "junk"}}}):
        s = _schema([_select()])
        if bakeoff is not None:
            s["_bakeoff"] = bakeoff
        assert _lint_structural(s) == []


# --------------------------------------------------------------------------- #
# Ledger backstop rules (bd polyglot-pdf-xazf, sprint 17): the publish gate's
# catch for defects a human can hand-edit into a stored draft after the
# extraction-time repair checks (bd l1a9) already passed.
# --------------------------------------------------------------------------- #

def test_field_unbacked_fires_dump_less():
    # No dump at all: the rule is schema-only, unlike the dump-* family.
    fields = [{"id": "ghost", "type": "text"}]
    findings = _lint_structural(_schema(fields))
    assert [f.rule for f in findings] == ["field-unbacked"]
    assert "ghost" in findings[0].message
    assert findings[0].severity == SEVERITY_ERROR


def test_field_unbacked_exempts_below_field_identity_types():
    # Choice options / table columns / address slots carry the identity; a
    # missing FIELD-level name is legitimate for these.
    fields = [
        {"id": "grp", "type": "radio", "options": [
            {"value": "a", "label": "A", "pdf_field_name": "a[0]"},
            {"value": "b", "label": "B", "pdf_field_name": "b[0]"},
        ]},
        {"id": "tbl", "type": "table"},
        {"id": "addr", "type": "address_group"},
    ]
    assert _lint_structural(_schema(fields)) == []


def test_field_unbacked_skipped_for_non_pdf_source():
    findings = _lint_structural({"source": "web",
                                 "fields": [{"id": "x", "type": "text"}]})
    assert findings == []


def test_field_claim_unresolvable_fires_with_dump():
    # One field claims a widget the PDF does not have while a sibling claims
    # the real one (so dump-widget-unclaimed stays quiet and this test pins
    # exactly the new rule).
    fields = [
        {"id": "real", "type": "text", "pdf_field_name": "f1[0]"},
        {"id": "phantom", "type": "text", "pdf_field_name": "nothing[0]"},
    ]
    dump = {"fields": [{"name": "top[0].f1[0]"}]}
    findings = _lint_structural(_schema(fields), dump)
    assert [f.rule for f in findings] == ["field-claim-unresolvable"]
    assert "nothing[0]" in findings[0].message
    assert findings[0].severity == SEVERITY_ERROR
    # The path embeds "(id=...)" so the ValidationPanel can click-to-focus.
    assert field_id_of(findings[0].path) == "phantom"


def test_field_claim_unresolvable_is_genuinely_dump_gated():
    # The same phantom claim WITHOUT a dump: structurally silent (the /lint
    # route has no kit dump -- the mark-complete gate is the enforcing site).
    fields = [{"id": "phantom", "type": "text", "pdf_field_name": "nothing[0]"}]
    assert _lint_structural(_schema(fields)) == []


def test_option_claim_unresolvable_names_the_option():
    fields = [
        {"id": "grp", "type": "radio", "options": [
            {"value": "a", "label": "A", "pdf_field_name": "a[0]"},
            {"value": "b", "label": "B", "pdf_field_name": "ghost[0]"},
        ]},
    ]
    dump = {"fields": [{"name": "top[0].a[0]"}]}
    findings = _lint_structural(_schema(fields), dump)
    assert [f.rule for f in findings] == ["field-claim-unresolvable"]
    assert "option[1]" in findings[0].path


# --- guidance-identity-stale (bd polyglot-pdf-anim) ------------------------ #

def _identity_schema(field, baked=None):
    prov = {"source": "llm-verified"}
    if baked is not None:
        prov["identity_sha1"] = baked
    return {
        "form_metadata": {"title": "T", "version": "1"},
        "fields": [field], "sections": [], "parts": [],
        "_bakeoff": {"authoring": {"instructions_enrich": {
            "provenance": {field["id"]: prov}, "flags": []}}},
    }


def _stale(findings):
    return [f for f in findings if f.rule == "guidance-identity-stale"]


def test_identity_unchanged_emits_nothing():
    from backend.services import guidance_contract as gc
    f = {"id": "a", "name": "Phone", "spoken_name": "phone", "type": "text",
         "help": {"instructions": "x"}}
    assert _stale(lint_schema(_identity_schema(f, gc.identity_sha1(f)))) == []


def test_spoken_name_change_flags_the_field_as_a_warning():
    from backend.services import guidance_contract as gc
    f = {"id": "a", "name": "Phone", "spoken_name": "phone", "type": "text",
         "help": {"instructions": "x"}}
    baked = gc.identity_sha1(f)
    renamed = dict(f, spoken_name="telephone")
    hits = _stale(lint_schema(_identity_schema(renamed, baked)))
    assert len(hits) == 1
    assert hits[0].severity == "WARNING"      # informs, never blocks
    assert "id=a" in hits[0].path


def test_option_label_change_flags_but_plumbing_does_not():
    from backend.services import guidance_contract as gc
    f = {"id": "a", "name": "N", "spoken_name": "n", "type": "radio",
         "options": [{"label": "Yes", "value": "y"}],
         "help": {"instructions": "x"}}
    baked = gc.identity_sha1(f)
    relabelled = dict(f, options=[{"label": "Yes please", "value": "y"}])
    assert len(_stale(lint_schema(_identity_schema(relabelled, baked)))) == 1
    # a plumbing edit is NOT voice-facing -> no finding
    replumbed = dict(f, pdf_field_name="W[0]")
    assert _stale(lint_schema(_identity_schema(replumbed, baked))) == []


def test_option_label_swap_flags_even_with_identical_label_multiset():
    """THE HANDOFF CASE (bd anim): two labels trading places while their
    values stay put left the sorted-bare-label hash unchanged, yet the
    assistant's unchanged words now select the OPPOSITE stored answer -- the
    one identity drift that yields a wrong answer on the form rather than
    stale wording. The label->value pair binding exists to catch this."""
    from backend.services import guidance_contract as gc
    base = {"id": "a", "name": "Marital status", "spoken_name": "marital status",
            "type": "radio",
            "options": [{"label": "Married", "value": "m"},
                        {"label": "Single", "value": "s"}],
            "help": {"instructions": "x"}}
    baked = gc.identity_sha1(base)
    swapped = dict(base, options=[{"label": "Single", "value": "m"},
                                  {"label": "Married", "value": "s"}])
    assert len(_stale(lint_schema(_identity_schema(swapped, baked)))) == 1


def test_option_spoken_label_swap_flags_too():
    """spoken_label OUTRANKS label as the voice join key (secretary_context
    resolves spoken_label or label; manifest_service ships it to the live
    model), so two spoken labels trading places while values stay put is the
    same wrong-answer hazard as a label swap (closeout Opus round 3, bd
    polyglot-pdf-w028)."""
    from backend.services import guidance_contract as gc
    base = {"id": "a", "name": "N", "spoken_name": "n", "type": "radio",
            "options": [
                {"label": "M", "spoken_label": "Married", "value": "m"},
                {"label": "S", "spoken_label": "Single", "value": "s"}],
            "help": {"instructions": "x"}}
    baked = gc.identity_sha1(base)
    swapped = dict(base, options=[
        {"label": "M", "spoken_label": "Single", "value": "m"},
        {"label": "S", "spoken_label": "Married", "value": "s"}])
    assert len(_stale(lint_schema(_identity_schema(swapped, baked)))) == 1
    # editing one spoken_label flags; reordering whole options stays silent
    edited = dict(base, options=[
        {"label": "M", "spoken_label": "Currently married", "value": "m"},
        base["options"][1]])
    assert len(_stale(lint_schema(_identity_schema(edited, baked)))) == 1
    reordered = dict(base, options=[base["options"][1], base["options"][0]])
    assert _stale(lint_schema(_identity_schema(reordered, baked))) == []


def test_value_only_rename_flags_as_the_accepted_swap_safety_cost():
    """A value-only rename is indistinguishable, to any order-insensitive
    hash, from half of a label swap (a swap IS a reorder plus a value
    rename) -- so catching swaps means this flags too, the ACCEPTED TRADEOFF
    pinned in identity_payload's docstring. The editor cannot produce this
    edit (option values mint from labels on blur, never free-typed --
    FieldEditor, bd h76m.10); it costs one acknowledgment click on
    out-of-band script/JSON edits only. If this test starts failing because
    someone re-excluded values, the swap test above must be failing too --
    fix the swap case first."""
    from backend.services import guidance_contract as gc
    f = {"id": "a", "name": "N", "spoken_name": "n", "type": "radio",
         "options": [{"label": "Yes", "value": "y"}],
         "help": {"instructions": "x"}}
    baked = gc.identity_sha1(f)
    revalued = dict(f, options=[{"label": "Yes", "value": "changed"}])
    assert len(_stale(lint_schema(_identity_schema(revalued, baked)))) == 1


def test_pre_anim_bake_is_silent_not_noisy():
    # a provenance record with no identity_sha1 has nothing to be stale against
    f = {"id": "a", "name": "Renamed", "spoken_name": "x", "type": "text",
         "help": {"instructions": "x"}}
    assert _stale(lint_schema(_identity_schema(f, None))) == []


def test_identity_rule_never_throws_on_malformed_provenance():
    f = {"id": "a", "name": "N", "spoken_name": "n", "type": "text"}
    for junk in ("str", 123, [], {"a": "not-a-dict"}, {"a": {"identity_sha1": 5}}):
        s = _identity_schema(f, "x")
        s["_bakeoff"]["authoring"]["instructions_enrich"]["provenance"] = junk
        lint_schema(s)   # must not raise


def test_stale_finding_carries_current_identity_in_the_PATH_not_the_message():
    r"""CONTRACT PIN (bd anim): the editor parses the current identity out of
    the finding PATH with /\[identity:([0-9a-f]+)\]/ and pins a human's
    acknowledgment to it. If this format ever changes, that parse silently
    returns undefined and 'any ack satisfies the gate' -- reopening the
    permanent-waiver hole with no other test to catch it. The hash must stay
    OUT of the message, which is rendered to humans in three UI surfaces."""
    import re
    from backend.services import guidance_contract as gc
    f = {"id": "a", "name": "N", "spoken_name": "v1", "type": "text",
         "help": {"instructions": "x"}}
    baked = gc.identity_sha1(f)
    drifted = dict(f, spoken_name="v2")
    hit = _stale(lint_schema(_identity_schema(drifted, baked)))[0]

    # the editor's EXACT regex must find the CURRENT identity in the path
    m = re.search(r"\[identity:([0-9a-f]+)\]", hit.path)
    assert m, f"editor's identity regex no longer matches path: {hit.path!r}"
    assert m.group(1) == gc.identity_sha1(drifted)
    # ...and the human-facing message must NOT carry it
    assert "identity:" not in hit.message
    # field_id must still resolve for click-to-focus despite the suffix
    from backend.services.schema_lint import field_id_of
    assert field_id_of(hit.path) == "a"


def test_each_edit_reports_a_DIFFERENT_current_identity():
    """The gate re-raises per edit only because this value moves (bd anim)."""
    from backend.services import guidance_contract as gc
    f = {"id": "a", "name": "N", "spoken_name": "v1", "type": "text",
         "help": {"instructions": "x"}}
    baked = gc.identity_sha1(f)
    p1 = _stale(lint_schema(_identity_schema(dict(f, spoken_name="v2"), baked)))[0].path
    p2 = _stale(lint_schema(_identity_schema(dict(f, spoken_name="v3"), baked)))[0].path
    assert p1 != p2


def test_pure_option_reorder_does_NOT_flag_but_real_changes_do():
    """Maintainer decision 2026-07-29: reordering options with identical
    labels must NOT re-raise the gate -- the assistant says the same words, and
    a needless prompt trains editors to click through. Adding, removing or
    editing a label still flags."""
    from backend.services import guidance_contract as gc
    base = {"id": "a", "name": "N", "spoken_name": "n", "type": "radio",
            "options": [{"label": "Yes", "value": "y"},
                        {"label": "No", "value": "n"}],
            "help": {"instructions": "x"}}
    baked = gc.identity_sha1(base)

    reordered = dict(base, options=[{"label": "No", "value": "n"},
                                    {"label": "Yes", "value": "y"}])
    assert _stale(lint_schema(_identity_schema(reordered, baked))) == []

    for changed in (
        dict(base, options=[{"label": "Yes please", "value": "y"},
                            {"label": "No", "value": "n"}]),          # edited
        dict(base, options=base["options"] + [{"label": "Maybe",
                                               "value": "m"}]),       # added
        dict(base, options=[{"label": "Yes", "value": "y"}]),         # removed
    ):
        assert len(_stale(lint_schema(_identity_schema(changed, baked)))) == 1


def test_a_kit_baked_before_identity_tracking_never_reads_stale():
    """REAL-KIT SAFETY (bd anim outer review round 2): the shipped w7 kit's 44
    provenance records predate identity tracking and carry NO identity_sha1.
    The rule must stay silent for them -- otherwise changing the hash formula
    (as the reorder fix did) would light up every previously-baked field at
    once, the mass false alarm that destroys the gate's credibility."""
    import json, pathlib
    kit = pathlib.Path(__file__).resolve().parents[2] / "form-kits" / "w7" / "schema.json"
    if not kit.exists():          # kit not present in this checkout
        return
    schema = json.loads(kit.read_text(encoding="utf-8"))
    hits = [f for f in lint_schema(schema)
            if f.rule == "guidance-identity-stale"]
    assert hits == [], (
        "a kit baked before identity tracking must never read stale; "
        f"got {len(hits)} findings")
