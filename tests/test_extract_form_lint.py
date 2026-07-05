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
    assert report["warnings"] == 0
    (finding,) = report["findings"]
    # JSON-ready plain dict (rides inside the draft written to disk).
    assert finding["severity"] == "ERROR"
    assert finding["rule"] == "unknown-operator"
    assert "dep" in finding["path"]


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
    assert with_dump["findings"][0]["rule"] == "dump-widget-multiclaim"
