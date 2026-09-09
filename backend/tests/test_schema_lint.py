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
    (backend/tests/unit/test_guidance_contract.py).

    Also drops audit-identity-* (bd polyglot-pdf-47r3) for the same reason:
    it is a KIT-LEVEL publish gate (does form_metadata name the form and its
    government edition?), not a structural defect in the fields these fixtures
    build -- and `_schema()` deliberately omits form_metadata entirely, so it
    would fire on nearly every fixture and drown the exact-defect-list
    assertions. Its own suite is test_audit_identity_lint below."""
    return [f for f in lint_schema(schema, dump)
            if not f.rule.startswith("help-")
            and not f.rule.startswith("audit-identity-")]

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
    assert "change it to one of:" in findings[0].message


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


_COMBO_CLAIM = "P1_Line6e_State[0]"
_COMBO_DUMP = {"fields": [{
    "name": "form1[0].#subform[0].P1_Line6e_State[0]",
    "widgets": [{"choices": [
        {"value": " "}, {"value": "WY"}, {"value": "AL"}, {"value": "DC"},
    ]}],
}]}


def _combo(options, fid="mail_state", ftype="select", claim=_COMBO_CLAIM):
    return [{"id": fid, "type": ftype, "pdf_field_name": claim,
             "options": list(options)}]



def test_a_pdf_sanctioned_code_in_a_dropdowns_VALUE_is_no_longer_exempt():
    """The 4we6j carve-out let a select keep the PDF export code in value
    because the filler wrote value verbatim. Since g2fpr the filler writes
    pdf_on_value, the kits are migrated, and the carve-out is RETIRED
    (g2fpr.4): every /Opt code sitting in value is a slug-rule finding whose
    remedy names the migration. Pins the whole set, not one code.
    """
    codes = [c["value"] for c in _COMBO_DUMP["fields"][0]["widgets"][0]["choices"]
             if c["value"].strip()]
    assert len(codes) >= 3, "fixture must exercise more than one code"
    opts = [{"value": c, "label": "State %s" % c} for c in codes]
    findings = [f for f in _lint_structural(_schema(_combo(opts), version="2"), _COMBO_DUMP)
                if f.rule == "option-value-slug"]
    assert len(findings) == len(codes)
    for f in findings:
        assert "migrate_select_on_values" in f.message
        assert "do NOT regenerate" not in f.message



@pytest.mark.parametrize("bad", ["Wyoming!!", "NOT_A_CODE", "WYO", "Wy oming"])
def test_dropdown_values_absent_from_pdf_choices_trip_the_slug_rule_and_rule_b(bad):
    """A junk value with no pdf_on_value gets BOTH findings now: it is not a
    slug (option-value-slug) and, with a dump resolving the widget, the
    choice has no export code for the filler (select-on-value-missing). Two
    findings, one fix each, no contradiction between them.
    """
    findings = _lint_structural(
        _schema(_combo([{"value": bad, "label": "X"}]), version="2"), _COMBO_DUMP)
    assert sorted(_rules(findings)) == ["option-value-slug", "select-on-value-missing"]



def test_dumpless_dropdown_finding_names_the_two_slot_shape_never_verbatim_codes():
    """A dropdown linted with NO dump still trips the slug rule on a code-shaped
    value (no exemption survives), and the remedy must describe the two-slot
    shape -- the code belongs in pdf_on_value -- never "keep the code as the
    value" or "do NOT regenerate", which was the pre-migration advice.
    Allowlist, not banned words: the sanctioned phrases must be present.
    """
    opts = [{"value": "WY", "label": "Wyoming (WY)"},
            {"value": "AL", "label": "Alabama (AL)"}]
    findings = [f for f in _lint_structural(_schema(_combo(opts), version="2"), None)
                if f.rule == "option-value-slug"]
    assert len(findings) == 2, "a dumpless dropdown lint must still report the values"
    for f in findings:
        assert "pdf_on_value" in f.message
        assert "regenerate it from the label" in f.message
        assert "do NOT regenerate" not in f.message
    # A non-select choice field keeps the plain remedy, which is correct there.
    radio = _combo([{"value": "Bad Value", "label": "x", "pdf_on_value": "1"},
                    {"value": "ok", "label": "y", "pdf_on_value": "2"}],
                   ftype="radio")
    rf = [f for f in _lint_structural(_schema(radio, version="2"), None)
          if f.rule == "option-value-slug"]
    assert rf and all("regenerate it from the label" in f.message
                      and "pdf_on_value" not in f.message for f in rf)



def test_no_dump_no_exemption_and_no_channel_finding():
    """Without a dump the slug rule still fires on a code-shaped value (there
    is no exemption to withhold any more), and the evidence-based channel
    rule stays silent -- no evidence never reads as "nothing is legal".
    """
    opts = [{"value": "WY", "label": "Wyoming (WY)"}]
    assert _rules(_lint_structural(
        _schema(_combo(opts), version="2"), None)) == ["option-value-slug"]



def test_the_channel_rule_is_keyed_on_THIS_fields_widget():
    """Claiming some other widget must not borrow its choice list: with the
    dump resolving no widget for this field, only the slug rule fires.
    """
    opts = [{"value": "WY", "label": "Wyoming (WY)"}]
    findings = _lint_structural(
        _schema(_combo(opts, claim="P9_Other[0]"), version="2"), _COMBO_DUMP)
    rules = _rules(findings)
    assert "option-value-slug" in rules
    assert "select-on-value-missing" not in rules      # no evidence for THIS widget



def test_radio_options_follow_the_same_slug_rule():
    """Radios and selects now share one rule: value is a slug, identity in
    pdf_on_value. A code in a radio's value is a slug-rule finding.
    """
    opts = [{"value": "WY", "label": "Wyoming", "pdf_on_value": "WY"}]
    findings = _lint_structural(
        _schema(_combo(opts, ftype="radio"), version="2"), _COMBO_DUMP)
    assert "option-value-slug" in _rules(findings)



def test_duplicate_dropdown_codes_trip_uniqueness_AND_the_retired_carve_outs_rules():
    """Uniqueness still bites; and since the carve-out is gone each duplicate
    code-in-value option is also a slug-rule and a missing-code finding.
    """
    opts = [{"value": "WY", "label": "a"}, {"value": "WY", "label": "b"}]
    findings = _lint_structural(_schema(_combo(opts), version="2"), _COMBO_DUMP)
    assert "option-value-duplicate" in _rules(findings)
    assert _rules(findings).count("option-value-slug") == 2
    assert _rules(findings).count("select-on-value-missing") == 2


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


def test_readonly_conditional_remedy_describes_flip_readonly_bit_as_WORKING():
    """The remedy must not tell authors flip_readonly_bit leaves a field unfillable.

    THE BUG THIS PINS (bd polyglot-pdf-38p0y). This message used to say an
    unlock "lets the PDF filler clear the bit, but the voice assistant is still
    refused, so a REQUIRED field stays unfillable" -- true while isFieldReadOnly
    ignored unlock_method, and FALSE once the AI-write gate learned to honor it.
    Left alone it steers authors away from the mechanism and toward permanently
    clearing read_only, which drops the form's own lock.

    WHY EXACT EQUALITY AND NOT A PHRASE CHECK. Three substring-based versions of
    this pin were each defeated by a reviewer in turn: (1) asserting the phrases
    were PRESENT allowed a message saying skipping pdf_field_flag_change "is
    usually harmless"; (2) adding a consequence-clause check allowed the clause
    to be present but undercut by the prose around it. Every fix widened the
    vocabulary and left the next paraphrase open, which is the blacklist trap one
    level up (bd memory stop-fixing-instances-after-two-failures): a substring
    test cannot judge meaning, because meaning lives in the sentence AROUND the
    substring.

    So this asserts the message EQUALS its sanctioned text. That is deliberately
    brittle: any rewording fails here and must be re-read and re-approved, which
    is exactly the review this text did not get when it silently went stale
    mid-branch. The cost is one obvious test edit per intentional reword; the
    thing it buys is that no edit can quietly invert the advice.

    The rule NAME and severity are pinned by the sibling tests.
    """
    fields = [
        _select("trig"),
        {"id": "dep", "type": "checkbox", "read_only": True,
         "show_if": {"field": "trig", "operator": "equals", "value": "alpha"}},
    ]
    findings = lint_schema(_schema(fields))
    rel = [f for f in findings if f.rule == "readonly-conditional-no-unlock"]
    assert rel, "the rule must still fire for a locked conditional field"

    expected = (
        "this field is locked, and a condition makes it appear or become "
        "required, but nothing unlocks it -- when that happens, no one can "
        "ever fill it in. Two ways to fix it. If the form itself locks the "
        "box, set the unlock method to flip_readonly_bit: the PDF filler "
        "clears the bit, and the voice assistant may fill the field once the "
        "condition shows it (bd polyglot-pdf-38p0y). Pair it with a "
        "pdf_field_flag_change, or the unlock never reaches the printed form. "
        "If the form does NOT lock the box, just clear read-only -- simpler, "
        "and nothing has to stay in sync. Either way the exception is a field "
        "another field copies into, which is written for the applicant."
    )
    assert rel[0].message == expected, (
        "the readonly-conditional-no-unlock remedy changed. This text tells a "
        "human author which fix to apply, and it went silently WRONG once "
        "before -- it advised clearing read_only on the grounds that an unlock "
        "leaves the field unfillable by voice, false since bd "
        "polyglot-pdf-38p0y. Re-read the new wording against the code before "
        "updating this expectation. isFieldReadOnly (frontend/src/schema-forms/"
        "utils/validation.ts) decides whether the AI may write a read_only "
        "field; apply_field_flag_changes (backend/routes/pdf_fill_routes.py) "
        "early-returns unless pdf_field_flag_change is present, so an unlock "
        "without it never reaches the printed form. Got: " + rel[0].message
    )


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
    #
    # The dump is REQUIRED, not an optimization (bd polyglot-pdf-4we6j): a
    # dropdown's option value must be the PDF's own export code ('AK', 'WY'),
    # and option-value-slug exempts a value only when it can see that value in
    # the form's choice list. Linting dump-less therefore reports every correct
    # export code as an ERROR -- which is exactly what the i-90 v2 kit's 124
    # state options hit. Passing the dump also widens this gate to the
    # dump-dependent rules (widget multi-claim), so it is strictly stronger.
    findings = lint_schema(_load_kit_schema(kit), _dump_kit(kit))
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
#     went 12 -> 8 (bd polyglot-pdf-3ave + lha9; see the per-kit note below);
#     w7 has 2 (the box-h "Other" reason text line
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
    # i-90 went 0 -> 45 on the v2 kit, and the rise is BY DESIGN, not a
    # regression: this app is filled by the APPLICANT, so the v2 schema models
    # only applicant-completed fields. The 45 unclaimed widgets are the blocks
    # a preparer or interpreter fills, which the applicant must never complete
    # (maintainer, 2026-08-31): 23 in Part 7 (preparer name/business/address/
    # phone/fax/email/attestation), 20 in Part 6 (interpreter name/business/
    # address/phone/email/language), and 2 Part 5 applicant-SIGNATURE widgets
    # (a wet signature is not app-fillable). The PDF's 7 barcode widgets are
    # excluded by the rule itself and are not in this count.
    # Lowering this number means the applicant schema GREW to cover a widget it
    # previously dropped; raising it again means more non-applicant scope was
    # removed. Either way, confirm which of the four groups above moved.
    "i-90": {"dump-widget-unclaimed": 45, "readonly-conditional-no-unlock": 0},
    # w7 went 2 -> 1, but read the SETS, not the count: they are disjoint.
    # The gold pass (bd polyglot-pdf-fjxe) modeled BOTH previously-unclaimed
    # "Other" lines (f1_04, f1_23), which is -2, and simultaneously quarantined
    # f1_02 into _ignored_fields, which is +1. So the lowered number is not
    # unambiguous progress: a widget was also lost. Whether f1_02 -- the
    # caption-line continuation of the "d or e" name+SSN prompt -- should be
    # modeled rather than ignored is tracked in bd polyglot-pdf-va4d.
    "w7": {"dump-widget-unclaimed": 1, "readonly-conditional-no-unlock": 0},
    # f1040 went 12 -> 8 (bd polyglot-pdf-3ave + lha9, shipped together). 3ave
    # rebound the page-1 amount column to the widgets on its own printed lines,
    # which CLAIMED the displaced tail f1_72/73/74/75 (the real Lines 8/9/10/11a
    # boxes) while freeing f1_47/48/49/50 (the real Lines 1a-1d boxes) -- a swap,
    # not progress, so the count sat at 12 mid-fix. lha9 then bound fld_1a..fld_1d
    # to those four freed widgets (they had claimed the NON-EXISTENT f1_31..f1_34),
    # which is the real -4 and also cleared f1040's 4 field-claim-unresolvable
    # ERRORs. The remaining 8 are genuinely unmodeled: f1_07..f1_10
    # (combat-zone/deceased), f1_25..f1_27 (address continuation), and f1_71
    # (the Line 7b "Check if: Schedule D not required" write-in, verified
    # against the PDF's printed row text).
    "f1040": {"dump-widget-unclaimed": 8, "readonly-conditional-no-unlock": 0},
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


def test_to_review_non_string_id_does_not_falsely_double_report():
    """bd polyglot-pdf-5ry1: a field with a NON-STRING id (e.g. an int 123)
    sitting in a to-review section must NOT ALSO trip a section-level
    to-review-pending finding claiming the id "names no field at all" / "is
    already filed in a proper section" -- both are false, since field 123 is
    real and is still sitting in that very holding section.

    Root cause: flagged_review_fields only tracked str-typed ids
    (isinstance(f["id"], str)), while the section's own fields[] list is
    filtered to string entries only -- so an int id never matched its own
    stringified entry there, and the section-level check wrongly called it
    stale. Mirrors test_to_review_field_trips_once_per_field's "no double
    report" shape, but with a non-string id.
    """
    s = _schema([
        {"id": 123, "type": "text", "pdf_field_name": "f123[0]",
         "section_id": "sec_to_review_p1"},
    ])
    s["sections"] = [
        {"id": "sec_to_review_p1", "label": "To review", "order": 1,
         "fields": ["123"]},
    ]
    findings = [f for f in lint_schema(s) if f.rule == "to-review-pending"]
    # Exactly the ONE field-level finding (field 123 is still un-reviewed --
    # that part is true and correctly still an ERROR); the section-level
    # "stale id" finding must NOT also fire for the same field.
    assert len(findings) == 1
    assert "123" in findings[0].path
    assert "sections[" not in findings[0].path


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


def test_emptied_guidance_never_gates():
    """A human who DELETED the guidance after the bake has nothing left to
    confirm -- gating would render the ack box under an empty textarea with
    copy about text that no longer exists (Opus round 5), the unactionable
    noise the rule's own docstring forbids. help-instructions-missing already
    surfaces the emptiness itself."""
    from backend.services import guidance_contract as gc
    f = {"id": "a", "name": "N", "spoken_name": "v1", "type": "text",
         "help": {"instructions": "x"}}
    baked = gc.identity_sha1(f)
    for emptied_help in ({}, None, {"instructions": "   "}):
        emptied = dict(f, spoken_name="v2", help=emptied_help)
        assert _stale(lint_schema(_identity_schema(emptied, baked))) == []
    # ...but ANY surviving guidance channel still gates
    hint_only = dict(f, spoken_name="v2", help={"format_hint": "letters only"})
    assert len(_stale(lint_schema(_identity_schema(hint_only, baked)))) == 1


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


def test_a_field_baked_before_identity_tracking_never_reads_stale():
    """REAL-KIT SAFETY (bd anim outer review round 2): a provenance record that
    predates identity tracking carries NO identity_sha1, and the rule must stay
    silent for it -- otherwise changing the hash formula (as the reorder fix
    did) would light up every previously-baked field at once, the mass false
    alarm that destroys the gate's credibility.

    Asserted against the real w7 kit but keyed on the RECORD, not the kit: the
    hand-verified gold pass (bd polyglot-pdf-fjxe) re-baked w7 WITH identity
    hashes, so a blanket 'this kit never reads stale' no longer describes
    anything (its post-edit fields legitimately do read stale, which is the
    gate working). The invariant that must never break is the hash-less one.
    """
    import json, pathlib
    kit = pathlib.Path(__file__).resolve().parents[2] / "form-kits" / "w7" / "schema.json"
    if not kit.exists():          # kit not present in this checkout
        return
    schema = json.loads(kit.read_text(encoding="utf-8"))
    prov = (((schema.get("_bakeoff") or {}).get("authoring") or {})
            .get("instructions_enrich") or {}).get("provenance") or {}

    # Strip every identity_sha1: the whole kit now looks pre-anim, which is
    # exactly the shape the mass-false-alarm guard has to survive.
    for rec in prov.values():
        if isinstance(rec, dict):
            rec.pop("identity_sha1", None)
    assert prov, "w7 provenance missing -- test no longer exercises the rule"

    hits = [f for f in lint_schema(schema)
            if f.rule == "guidance-identity-stale"]
    assert hits == [], (
        "a field baked before identity tracking must never read stale; "
        f"got {len(hits)} findings")


# --- guidance-identity-mass-drift (bd polyglot-pdf-cf6v) -------------------- #
#
# The measured W-7 wave this rule exists for (root-cause evidence in the
# 2026-08-07 cf6v journal entry): bd polyglot-pdf-stkz (PR #518) appended the
# type token to identity_payload 25 minutes AFTER PR #519 wrote the kit's 52
# stamps, so every stamp mismatched at once with zero author edits (the stale
# set jumped 14 -> 51; under the pre-#518 3-element payload, 35 of the 51
# match again). Underneath, the pre-existing 14 are bake-time fossils: stamps
# describing the field one position over (the ivh9 off-by-one) or a
# pre-hand-verify identity. Per-field acknowledgment of such a wave is 51
# meaningless clicks, so the linter collapses it to ONE kit-level finding.


def _mass(findings):
    return [f for f in findings if f.rule == "guidance-identity-mass-drift"]


def _drift_kit(n_fields, n_drifted):
    """A kit with n_fields guidance-carrying stamped fields, the first
    n_drifted of which have drifted (spoken_name edited after the bake)."""
    from backend.services import guidance_contract as gc
    fields, prov = [], {}
    for i in range(n_fields):
        f = {"id": f"f{i}", "name": f"Field {i}", "spoken_name": f"field {i}",
             "type": "text", "help": {"instructions": "x"}}
        prov[f["id"]] = {"source": "llm-verified",
                        "identity_sha1": gc.identity_sha1(f)}
        if i < n_drifted:
            f = dict(f, spoken_name=f"renamed {i}")
        fields.append(f)
    return {
        "form_metadata": {"title": "T", "version": "1"},
        "fields": fields, "sections": [], "parts": [],
        "_bakeoff": {"authoring": {"instructions_enrich": {
            "provenance": prov, "flags": []}}},
    }


def test_whole_kit_drift_collapses_to_one_kit_level_finding():
    """REGRESSION (bd cf6v): every compared field mismatching at once is the
    signature of a formula change / bulk sweep, not hand edits -- one legible
    kit-level WARNING replaces the N per-field ack gates."""
    findings = lint_schema(_drift_kit(3, 3))
    assert _stale(findings) == []
    hits = _mass(findings)
    assert len(hits) == 1
    assert hits[0].severity == "WARNING"
    assert field_id_of(hits[0].path) is None   # kit-level: no field anchor
    assert "3 fields" in hits[0].message


def test_partial_drift_keeps_per_field_flags_and_no_mass_finding():
    """One surviving match is what real hand edits look like -- the per-field
    ack gate must keep firing, and the collapse must stay silent."""
    findings = lint_schema(_drift_kit(3, 2))
    assert len(_stale(findings)) == 2
    assert _mass(findings) == []


def test_small_kit_full_drift_stays_per_field():
    """Below 3 compared fields "all mismatch" is too weak a signature to
    suppress the ack gate -- 1- and 2-field kits keep per-field flags."""
    for n in (1, 2):
        findings = lint_schema(_drift_kit(n, n))
        assert len(_stale(findings)) == n
        assert _mass(findings) == []


def test_w7_wave_is_pinned_as_one_mass_drift_finding():
    """The shipped kit's wave must surface as exactly ONE kit-level finding
    and ZERO per-field flags (the 51-flag wall was the bd cf6v bug). If the
    per-field set comes back, either the guidance was re-baked (good: delete
    this pin's zero-assert and re-pin the residual set) or the collapse
    regressed. If BOTH sets are empty, the rule went dark -- also look."""
    import json, pathlib
    kit = pathlib.Path(__file__).resolve().parents[2] / "form-kits" / "w7" / "schema.json"
    if not kit.exists():          # kit not present in this checkout
        return
    findings = lint_schema(json.loads(kit.read_text(encoding="utf-8")))
    assert _stale(findings) == [], (
        "w7 emitted per-field stale flags again -- re-baked (re-pin) or "
        "collapse regressed?")
    hits = _mass(findings)
    assert len(hits) == 1, "w7 mass-drift finding missing: rule went dark?"
    assert "51 fields" in hits[0].message


# --- audit identity (bd polyglot-pdf-47r3) ------------------------------------
#
# The confirmation trail records form_number + kit_id + edition_date so a
# disputed filing can name WHICH form and WHICH revision the client confirmed
# against. edition_date is ADVISORY here, never a publish gate: a custom form (a
# firm's own intake sheet) legitimately has no government edition, and blocking
# it would make the product unusable for exactly the firm-tier customers it is
# meant to serve (maintainer, 2026-08-04). The audit record falls back to a
# content fingerprint instead.


def _audit_rules(schema):
    return [f.rule for f in lint_schema(schema)
            if f.rule.startswith("audit-identity-")]


def test_missing_edition_date_warns_but_never_blocks():
    schema = _schema([{"id": "a", "type": "text"}])
    schema["form_metadata"] = {"title": "T"}

    findings = [f for f in lint_schema(schema)
                if f.rule == "audit-identity-no-edition"]

    assert len(findings) == 1
    # WARNING, not ERROR: an ERROR would block Mark-complete promotion.
    assert findings[0].severity == SEVERITY_WARNING


def test_edition_date_present_is_silent():
    schema = _schema([{"id": "a", "type": "text"}])
    schema["form_metadata"] = {"title": "T", "edition_date": "12/2024"}

    assert _audit_rules(schema) == []


def test_author_version_resolves_the_no_edition_warning():
    """The warning is about falling back to an UNREADABLE fingerprint, not
    about the government field specifically (bd polyglot-pdf-xzw5). An author
    version names the revision in plain language, so it clears the finding --
    otherwise every custom form would carry a permanent warning it has no way
    to resolve."""
    schema = _schema([{"id": "a", "type": "text"}])
    schema["form_metadata"] = {"title": "T", "author_version": "2026-08-07"}

    assert _audit_rules(schema) == []


def test_a_blank_author_version_does_not_resolve_the_warning():
    """Mirrors the blank-edition rule: whitespace names no revision, so the
    fingerprint fallback still applies and the author still needs telling."""
    schema = _schema([{"id": "a", "type": "text"}])
    schema["form_metadata"] = {"title": "T", "author_version": "   "}

    assert _audit_rules(schema) == ["audit-identity-no-edition"]


def test_the_no_edition_warning_names_BOTH_remedies():
    """The message must offer the author version, not just the edition date --
    a custom form's author following the old text had no actionable fix."""
    schema = _schema([{"id": "a", "type": "text"}])
    schema["form_metadata"] = {"title": "T"}

    finding = [f for f in lint_schema(schema)
               if f.rule == "audit-identity-no-edition"][0]
    assert "edition_date" in finding.message
    assert "author version" in finding.message


def test_blank_edition_date_is_treated_as_missing():
    """A whitespace-only edition is not an edition -- it must not read as one."""
    schema = _schema([{"id": "a", "type": "text"}])
    schema["form_metadata"] = {"title": "T", "edition_date": "   "}

    assert _audit_rules(schema) == ["audit-identity-no-edition"]


def test_schema_without_form_metadata_is_not_flagged():
    """A metadata-less schema is a fixture/draft shape, not an authoring slip.

    Flagging it would fire on nearly every structural fixture in this suite and
    drown the exact-defect-list assertions those tests make.
    """
    assert _audit_rules(_schema([{"id": "a", "type": "text"}])) == []


# ---------------------------------------------------------------------------
# hidden + show_if is a CONTRADICTION, not a preference (bd polyglot-pdf-pfx1).
# ---------------------------------------------------------------------------

_SHOW_IF = {"field": "trigger", "operator": "equals", "value": "yes"}


def _visibility_field(**kw):
    f = {"id": "target", "type": "text"}
    f.update(kw)
    return f


def test_hidden_with_show_if_trips_once():
    """The gated state: always-hidden AND conditionally shown.

    MAINTAINER DECISION 2026-08-04: "A field cannot be hidden and have a
    condition to be shown. period." A warning was explicitly considered and
    rejected, so this is an ERROR -- the promotion gate must refuse it.
    """
    findings = _lint_structural(_schema([
        _visibility_field(hidden=True, show_if=dict(_SHOW_IF)),
        {"id": "trigger", "type": "text"},
    ]))
    hits = [f for f in findings if f.rule == "hidden-with-show-if"]
    assert len(hits) == 1, _rules(findings)
    assert hits[0].severity == SEVERITY_ERROR, hits[0].severity
    # The path anchors the finding at the property the editor must disable.
    assert hits[0].path.endswith(".hidden"), hits[0].path


def test_hidden_with_show_if_message_names_both_remedies():
    """bd xfdb copy standard: say what happened, the real consequence, and
    what to do. Both escape routes must be offered -- an author who reads only
    'remove the condition' loses the conditional behavior they wanted.

    Allowlist-style (memory: pin the sanctioned remedies, never ban a word):
    banning 'contradict' would be one synonym from defeat.
    """
    findings = _lint_structural(_schema([
        _visibility_field(hidden=True, show_if=dict(_SHOW_IF)),
        {"id": "trigger", "type": "text"},
    ]))
    msg = next(f.message for f in findings if f.rule == "hidden-with-show-if")
    assert "untick Hidden" in msg, msg          # remedy 1: keep the condition
    assert "delete the condition" in msg, msg   # remedy 2: keep hidden
    assert "IS shown to the applicant" in msg, msg  # the real consequence


@pytest.mark.parametrize("kw", [
    {},                                    # neither
    {"hidden": True},                      # hidden only
    {"show_if": dict(_SHOW_IF)},           # condition only
    {"hidden": False, "show_if": dict(_SHOW_IF)},   # explicit hidden=False
    {"hidden": True, "show_if": {}},       # empty condition reads as absent
    {"hidden": True, "show_if": None},     # null condition reads as absent
])
def test_hidden_with_show_if_stays_quiet_on_every_legitimate_shape(kw):
    """The false-positive half. Each of these is a LEGITIMATE authoring choice
    and must not be flagged -- a gate that fires on a valid schema trains
    authors to ignore it. The two falsy-condition cases matter because a
    hand-edited kit can carry `show_if: {}` and the editor's own gate treats
    that as absent; the two must agree or the editor would lock a checkbox
    over a condition lint says does not exist.
    """
    findings = _lint_structural(_schema([
        _visibility_field(**kw),
        {"id": "trigger", "type": "text"},
    ]))
    assert "hidden-with-show-if" not in _rules(findings), _rules(findings)


# ---------------------------------------------------------------------------
# The select's SECOND channel: pdf_on_value (bd polyglot-pdf-g2fpr)
# ---------------------------------------------------------------------------

_SELECT_RULES = { "select-on-value-not-in-pdf",
                 "select-on-value-missing"}


def _select_findings(fields, dump=_COMBO_DUMP):
    return [f for f in _lint_structural(_schema(fields, version="2"), dump)
            if f.rule in _SELECT_RULES]


def test_the_v2_select_shape_lints_clean():
    """value is a slug, pdf_on_value is a code the PDF declares: no finding
    from EITHER the slug rule or the new channel rules."""
    opts = [{"value": "wyoming", "label": "Wyoming (WY)", "pdf_on_value": "WY"},
            {"value": "alabama", "label": "Alabama (AL)", "pdf_on_value": "AL"}]
    findings = _lint_structural(_schema(_combo(opts), version="2"), _COMBO_DUMP)
    assert [f.rule for f in findings
            if f.rule in _SELECT_RULES | {"option-value-slug"}] == []



def test_a_code_valued_option_with_pdf_on_value_is_a_slug_rule_finding_once():
    """The former select-value-not-slug rule restated the slug rule for the
    code-in-both shape and was retired with the carve-out (g2fpr.4): one
    finding, from option-value-slug, whose remedy knows the code lives in
    pdf_on_value. The channel rule stays silent (the code IS in /Opt)."""
    opts = [{"value": "WY", "label": "Wyoming", "pdf_on_value": "WY"}]
    assert _select_findings(_combo(opts)) == []
    findings = [f for f in _lint_structural(_schema(_combo(opts), version="2"), _COMBO_DUMP)
                if f.rule in _SELECT_RULES | {"option-value-slug"}]
    assert [f.rule for f in findings] == ["option-value-slug"]
    assert "pdf_on_value" in findings[0].message


def test_rule_a_numeric_values_are_already_slugs():
    """height_feet on the i-90: '5' with pdf_on_value '5' is the correct shape
    and must NOT be told to regenerate anything."""
    dump = {"fields": [{"name": _COMBO_DUMP["fields"][0]["name"],
                        "widgets": [{"choices": [{"value": "5"}, {"value": "6"}]}]}]}
    opts = [{"value": "5", "label": "5", "pdf_on_value": "5"}]
    assert _select_findings(_combo(opts), dump) == []


def test_rule_a_pdf_on_value_must_be_a_code_the_widget_accepts():
    """The filler now WRITES pdf_on_value, so a code /Opt does not declare
    prints wrong exactly as a slug used to."""
    opts = [{"value": "wyoming", "label": "Wyoming", "pdf_on_value": "XX"}]
    assert [f.rule for f in _select_findings(_combo(opts))] == ["select-on-value-not-in-pdf"]


def test_rule_b_a_slug_with_no_pdf_on_value_is_THE_HOLE_and_now_errors():
    """The c5r8 defect, open until this rule. Pin the PREMISE first: the slug
    rule does not fire (it is a slug) and the code check does not fire (no
    code) -- so before rule (b) this shape lint clean, published clean, and
    printed 'wyomin'."""
    opts = [{"value": "wyoming", "label": "Wyoming"}]
    all_findings = _lint_structural(_schema(_combo(opts), version="2"), _COMBO_DUMP)
    assert "option-value-slug" not in [f.rule for f in all_findings]   # premise
    assert [f.rule for f in _select_findings(_combo(opts))] == ["select-on-value-missing"]



def test_rule_b_reports_a_junk_value_with_no_code_alongside_the_slug_rule():
    """Junk ('Bad Slug') trips option-value-slug; since g2fpr.4 the channel
    rule ALSO fires, because whatever the value looks like, the choice has
    no export code for the filler. Two findings, two distinct fixes."""
    opts = [{"value": "Bad Slug", "label": "x"}]
    assert [f.rule for f in _select_findings(_combo(opts))] == ["select-on-value-missing"]



def test_the_legacy_code_shape_is_an_ERROR_with_a_dump_present():
    """EXIT CRITERION 2 (g2fpr.4): a select option lacking pdf_on_value is an
    ERROR with a dump present -- no legacy path survives. The pre-migration
    shape (code in value, no pdf_on_value) gets the channel finding whose
    remedy names the migration tool, plus the slug-rule finding."""
    opts = [{"value": "WY", "label": "Wyoming"}]
    channel = _select_findings(_combo(opts))
    assert [f.rule for f in channel] == ["select-on-value-missing"]
    assert channel[0].severity == SEVERITY_ERROR
    assert "migrate_select_on_values" in channel[0].message
    assert "pre-migration" in channel[0].message


def test_the_channel_rules_are_evidence_based_no_dump_no_finding():
    """Same convention as the carve-out: pdf_choice_values returns 'no
    evidence' without a dump, and that must never read as 'nothing is legal'."""
    opts = [{"value": "wyoming", "label": "Wyoming"},
            {"value": "alabama", "label": "Alabama", "pdf_on_value": "ZZ"}]
    assert _select_findings(_combo(opts), dump=None) == []


def test_the_channel_rules_are_select_only():
    """A radio carrying the identical option shape is governed by its own
    rules; nothing here may fire on it."""
    opts = [{"value": "WY", "label": "Wyoming", "pdf_on_value": "WY"},
            {"value": "wyoming", "label": "Wyoming"}]
    assert _select_findings(_combo(opts, ftype="radio")) == []


def test_a_junk_value_with_pdf_on_value_gets_ONE_finding_and_the_right_remedy():
    """Fresh-eyes (g2fpr.1): 'Alabama (AL)' with pdf_on_value 'AL' fired BOTH
    option-value-slug ('do NOT regenerate from the label') and
    select-value-not-slug ('regenerate from the label') -- two ERRORs on one
    option with opposite instructions, at exactly the moment PR 2 and the
    migration will be producing this transitional shape.

    Now: one finding, and its remedy knows the code lives in pdf_on_value."""
    opts = [{"value": "Alabama (AL)", "label": "Alabama (AL)", "pdf_on_value": "AL"}]
    findings = [f for f in _lint_structural(_schema(_combo(opts), version="2"), _COMBO_DUMP)
                if f.rule in _SELECT_RULES | {"option-value-slug"}]
    assert [f.rule for f in findings] == ["option-value-slug"]
    assert "regenerate it from the label" in findings[0].message
    assert "do NOT regenerate" not in findings[0].message
    assert "pdf_on_value" in findings[0].message



def test_no_remedy_anywhere_says_do_not_regenerate_any_more():
    """The pre-migration advice ("do NOT regenerate from the label, the value
    must stay the PDF's code") was correct only while the filler wrote value
    verbatim. It must not survive anywhere in lint's select output."""
    shapes = [
        [{"value": "Alabama (AL)", "label": "Alabama (AL)"}],
        [{"value": "AL", "label": "Alabama (AL)"}],
        [{"value": "alabama", "label": "Alabama (AL)"}],
    ]
    for opts in shapes:
        for dump in (_COMBO_DUMP, None):
            for f in _lint_structural(_schema(_combo(opts), version="2"), dump):
                assert "do NOT regenerate" not in f.message, (opts, dump, f.rule)





