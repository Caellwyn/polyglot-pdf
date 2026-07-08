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


def test_operator_trigger_trips_once():
    fields = [
        {"id": "freetext", "type": "text"},
        {"id": "dep", "type": "text",
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
        {"id": "dep", "type": "text",
         "show_if": {"field": "grp", "operator": "is_checked"}},
    ]
    assert lint_schema(_schema(fields)) == []
    findings = lint_schema(_schema(fields, version="2"))
    assert _rules(findings) == ["operator-trigger"]


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
    assert findings[0].severity == "WARNING"
    assert "f2[0]" in findings[0].path
    assert not has_errors(findings)


def test_unclaimed_button_widget_is_not_a_finding():
    # A decorative reset/print button is legitimately unmodeled -- not a gap.
    fields = [{"id": "a", "type": "text", "pdf_field_name": "f1[0]"}]
    dump = {"fields": [
        {"name": "top[0].f1[0]", "logical_type": "text"},
        {"name": "top[0].reset[0]", "logical_type": "button"},
    ]}
    assert lint_schema(_schema(fields), dump) == []


def test_all_widgets_claimed_emits_no_unclaimed_finding():
    fields = [
        {"id": "a", "type": "text", "pdf_field_name": "f1[0]"},
        {"id": "b", "type": "text", "pdf_field_name": "f2[0]"},
    ]
    dump = {"fields": [
        {"name": "top[0].f1[0]", "logical_type": "text"},
        {"name": "top[0].f2[0]", "logical_type": "text"},
    ]}
    assert lint_schema(_schema(fields), dump) == []


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


def test_vestigial_value_on_no_value_operator_is_tolerated_on_v1_only():
    fields = [
        _select(),
        {"id": "dep", "type": "text",
         "show_if": {"field": "picker", "operator": "is_not_empty", "value": "x"}},
    ]
    # v1: the operator ignores the stray value -- tolerated.
    assert lint_schema(_schema(fields)) == []
    # v2: the model rejects this exact shape as an arity error, and lint must
    # agree on the Pydantic-rejected raw-draft path (Codex PR #302).
    findings = lint_schema(_schema(fields, version="2"))
    assert _rules(findings) == ["value-arity"]


def test_empty_composite_buckets_are_malformed():
    # ConditionGroup requires at least one non-empty bucket; the raw-draft
    # path must report the same shape instead of passing it clean.
    fields = [
        {"id": "dep", "type": "text", "show_if": {"all_of": []}},
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
        {"id": "dep", "type": "text",
         "show_if": {"field": "p", "operator": "equals", "value": "alpha"}},
    ]
    assert lint_schema(_schema(fields)) == []


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
        {"id": "trigger", "type": "text", "conditional_fields": ["dep"]},
    ]
    findings = lint_schema(_schema(fields, version="2"))
    assert "legacy-trigger-side-logic" in _rules(findings)


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
        {"id": "dep", "type": "text",
         "show_if": {
             "all_of": [{"field": "picker", "operator": "equals", "value": "alpha"}],
             "none_of": [{"field": "picker", "operator": "equals", "value": "beta"}],
         }},
    ]
    assert lint_schema(_schema(fields)) == []


def test_lint_never_raises_on_garbage():
    assert has_errors(lint_schema("not even a dict"))
    assert lint_schema({"fields": "oops"}) == []  # non-list fields -> empty
    assert lint_schema({"fields": 123}) == []     # non-iterable too (PR #302)
    assert lint_schema({"fields": [None, 42, "x"]}) == []  # non-dict members
    assert lint_schema({}) == []


def test_non_list_options_never_crash_any_pass():
    # Codex PR #302 round 2: malformed `options` (a number) reached raw
    # iteration in BOTH the option-reference check and the dump-claim pass.
    fields = [
        {"id": "weird", "type": "select", "options": 5,
         "pdf_field_name": "w[0]"},
        {"id": "dep", "type": "text",
         "show_if": {"field": "weird", "operator": "equals", "value": "x"}},
    ]
    dump = {"fields": [{"name": "top[0].w[0]"}]}
    findings = lint_schema(_schema(fields), dump)  # must not raise
    assert all(isinstance(f.rule, str) for f in findings)


def test_long_acyclic_show_if_chain_does_not_overflow():
    # Codex PR #302 round 2: recursive DFS hit Python's recursion limit on
    # long chains; the iterative walk must handle depth > 1000 and stay quiet.
    n = 2000
    fields = [{"id": "f0", "type": "text"}]
    fields += [
        {"id": f"f{i}", "type": "text",
         "show_if": {"field": f"f{i-1}", "operator": "is_not_empty"}}
        for i in range(1, n)
    ]
    assert lint_schema(_schema(fields)) == []


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
        {"id": "dep", "type": "text",
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
    findings = lint_schema(draft)
    dicts = [f.as_dict() for f in findings]
    assert dicts, "the broken draft must produce findings"
    for d in dicts:
        assert d["field_id"] is not None, f"unfocusable finding: {d['path']}"
        assert d["field_id"] in ids, f"finding points at a missing field: {d}"
