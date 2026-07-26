"""Tests for extract_form.py's _lint_schema wiring (bd polyglot-pdf-h76m.5).

The extraction pipeline records schema-lint findings in the draft's
_bakeoff.authoring.lint block. These tests pin the report shape and the
dump-aware path with synthetic data (no PDF / LLM needed) -- the lint RULES
themselves are covered in backend/tests/test_schema_lint.py; this file covers
only the extract_form-side adapter (report keys, counts, findings encoding).

Imports extract_form by file path (repo precedent: test_extract_form_backfill.py).
ASCII only.
"""

import importlib.util
import pathlib
import sys


_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))
_SCRIPT = _REPO / "scripts" / "authoring" / "extract_form.py"
spec = importlib.util.spec_from_file_location("extract_form_lint", _SCRIPT)
ef = importlib.util.module_from_spec(spec)
sys.modules["extract_form_lint"] = ef
spec.loader.exec_module(ef)


def test_clean_schema_reports_zero_counts():
    report = ef._lint_schema({"source": "pdf", "fields": []}, None)
    assert report == {"errors": 0, "warnings": 0, "findings": []}


def test_broken_schema_reports_findings_as_plain_dicts():
    schema = {
        "source": "pdf",
        "fields": [
            {"id": "dep", "type": "text",
             "show_if": {"field": "ghost", "operator": "is_selected"}},
        ],
    }
    report = ef._lint_schema(schema, None)
    assert report["errors"] == 1
    # help-* guidance findings (bd wsao.3) are a standing WARNING worklist on
    # guidance-less fixtures -- filter them; this test pins the ERROR shape.
    findings = [f for f in report["findings"]
                if not f["rule"].startswith("help-")]
    assert report["warnings"] == len(report["findings"]) - len(findings)
    (finding,) = findings
    # JSON-ready plain dict (rides inside the draft written to disk).
    assert finding["severity"] == "ERROR"
    assert finding["rule"] == "unknown-operator"
    assert "dep" in finding["path"]


def test_repair_schema_report_counts_exclude_the_summary_entry():
    """bd h76m.13: _repair_schema's applied/dropped counts must exclude the
    synthetic alias-hit-rate summary entry (fresh-eyes round 1 -- it inflated
    'applied' by one whenever any alias fired)."""
    schema = {
        "source": "pdf",
        "fields": [
            {"id": "grp", "type": "checkbox_group", "options": [
                {"value": "alpha", "label": "Alpha", "pdf_field_name": "a[0]"},
                {"value": "beta", "label": "Beta", "pdf_field_name": "b[0]"},
            ]},
            {"id": "dep", "type": "text",
             "show_if": {"field": "grp", "operator": "is_selected",
                         "value": "alpha"}},
        ],
    }
    repaired, report = ef._repair_schema(schema, None)
    assert report["alias_hits"] == 1
    # ONE substantive repair (the alias rewrite); the summary entry is not
    # counted as applied.
    assert report["applied"] == 1
    assert report["dropped"] == 0
    dep = next(f for f in repaired["fields"] if f["id"] == "dep")
    assert dep["show_if"]["operator"] == "includes"


def test_repair_schema_fails_loudly_but_returns_the_draft_on_hallucination():
    schema = {"source": "pdf", "fields": [
        {"id": "grp", "type": "checkbox_group", "options": [
            {"value": "alpha", "label": "Alpha", "pdf_field_name": "a[0]"},
            {"value": "beta", "label": "Beta", "pdf_field_name": "ghost[0]"},
        ]},
    ]}
    dump = {"fields": [{"name": "top[0].a[0]"}]}
    out, report = ef._repair_schema(schema, dump)
    assert out is schema  # unrepaired draft continues through the pipeline
    assert "ghost[0]" in report["failed"]


def test_dump_reaches_the_widget_claim_rule():
    schema = {
        "source": "pdf",
        "fields": [
            {"id": "a", "type": "text", "pdf_field_name": "f1[0]"},
            {"id": "b", "type": "text", "pdf_field_name": "f1[0]"},
        ],
    }
    dump = {"fields": [{"name": "top[0].f1[0]"}]}
    without_dump = ef._lint_schema(schema, None)
    with_dump = ef._lint_schema(schema, dump)
    assert without_dump["errors"] == 0  # the rule is dump-only
    assert with_dump["errors"] == 1
    # index by rule, not position: the wsao.3 guidance WARNINGs precede the
    # dump-claim findings in lint order.
    assert any(f["rule"] == "dump-widget-multiclaim"
               for f in with_dump["findings"])


# --- Translation flag surfacing at extraction (bd polyglot-pdf-9djc) --------
# The bake report -- flags included -- rides the draft verbatim at
# _bakeoff.authoring.option_translation (the extract() provenance write);
# these pin the extract_form-side adapter: the report passes through
# _bake_option_translations intact, and the console gets a count-only
# summary line (messages can carry foreign script -- cp1252 rule).


def test_bake_option_translations_report_passes_through_flags(monkeypatch):
    planted = {
        "changed": True,
        "failed_languages": [],
        "languages": {"spanish": {"labels": 1, "missing": 1, "translated": 1,
                                  "options_updated": 1, "failed": False}},
        "flags": [{"severity": "WARNING",
                   "rule": "translation-drift-unresolved",
                   "path": "fields[0] (id=sex).options[m]"
                           ".label_translations.spanish",
                   "message": "judge: drift", "field_id": "sex"}],
    }

    async def _fake_bake(schema, text_ai, languages, **kwargs):
        return dict(planted)

    import backend.adapters.text_ai_gemini as tag
    import backend.services.option_translation as ot
    monkeypatch.setattr(ot, "bake_label_translations", _fake_bake)
    monkeypatch.setattr(tag, "TextAIGemini", lambda **kw: object())
    monkeypatch.setenv("VERTEXAI", "true")

    report = ef._bake_option_translations({"fields": []}, "gemini-2.5-pro")
    assert report["flags"] == planted["flags"]
    assert report["model"] == "gemini-2.5-pro"


def test_translation_flag_summary_counts_by_rule():
    report = {"flags": [
        {"rule": "translation-drift-unresolved", "path": "p1", "message": "m"},
        {"rule": "translation-drift-unresolved", "path": "p2", "message": "m"},
        {"rule": "translation-ambiguous-source", "path": "p3", "message": "m"},
    ]}
    line = ef._translation_flag_summary(report)
    assert line.startswith("translation flags: 3 (")
    assert "translation-drift-unresolved=2" in line
    assert "translation-ambiguous-source=1" in line
    assert "_bakeoff.authoring.option_translation.flags" in line
    # Count-only: no flag message text reaches the console line.
    assert "m" != line  # (sanity) and specifically:
    assert "judge" not in line


def test_translation_flag_summary_is_none_when_flag_free():
    assert ef._translation_flag_summary({}) is None
    assert ef._translation_flag_summary({"flags": []}) is None
    assert ef._translation_flag_summary({"skipped": "disabled"}) is None
