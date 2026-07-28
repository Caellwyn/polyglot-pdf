"""Extraction-time ledger + provenance (bd polyglot-pdf-l1a9, sprint 17 C1).

Pins the three pure pieces added to scripts/authoring/extract_form.py:

1. _check_dump_coverage: a fillable dump widget claimed by NO field/option is
   returned (the post-backfill pipeline-failure signal); buttons/barcodes and
   claimed widgets are not; dot-suffix claims resolve like the lint rules.
2. _stamp_extraction_info: every extraction carries an extraction_info stanza
   that the backend Pydantic model accepts -- absence of this stanza is what
   422'd every modern kit at the publish gate.
3. _classify_exit: a repair-failed or coverage-gapped draft classifies ISSUES
   (exit 3), never VALID -- both were previously invisible to the tri-state.

ASCII only.
"""

import importlib.util
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))
sys.path.insert(0, str(_REPO / "scripts" / "authoring"))

_SCRIPT = _REPO / "scripts" / "authoring" / "extract_form.py"
spec = importlib.util.spec_from_file_location("extract_form_under_test", _SCRIPT)
xf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xf)

from backend.models.form_models import FormSchema  # noqa: E402


def _dump(*entries):
    return {"fields": [dict(e) for e in entries]}


def _text_widget(name, tooltip="A field"):
    return {"name": name, "logical_type": "text", "tooltip": tooltip,
            "widgets": [{"page": 0, "rect": [0, 0, 10, 10]}]}


# --------------------------------------------------------------------------- #
# 1. _check_dump_coverage
# --------------------------------------------------------------------------- #

def test_unclaimed_fillable_widget_is_reported():
    dump = _dump(_text_widget("top[0].a[0]"), _text_widget("top[0].b[0]"))
    schema = {"source": "pdf", "fields": [
        {"id": "a", "type": "text", "pdf_field_name": "top[0].a[0]"},
    ]}
    assert xf._check_dump_coverage(schema, dump) == ["top[0].b[0]"]


def test_option_claims_and_dot_suffix_resolution_count_as_claimed():
    dump = _dump(_text_widget("top[0].a[0]"), _text_widget("top[0].b[0]"))
    schema = {"source": "pdf", "fields": [
        # Dot-suffix claim (leaf name) resolves like the lint dump rules.
        {"id": "a", "type": "text", "pdf_field_name": "a[0]"},
        # Option-level claim counts too.
        {"id": "grp", "type": "radio", "options": [
            {"value": "b", "label": "B", "pdf_field_name": "top[0].b[0]"},
        ]},
    ]}
    assert xf._check_dump_coverage(schema, dump) == []


def test_buttons_and_barcodes_are_not_coverage_gaps():
    dump = _dump(
        {"name": "top[0].print[0]", "logical_type": "button",
         "widgets": [{"page": 0}]},
        {"name": "top[0].BarCode1[0]", "logical_type": "text",
         "widgets": [{"page": 0}]},
    )
    schema = {"source": "pdf", "fields": [
        {"id": "x", "type": "text", "pdf_field_name": "unrelated[0]"},
    ]}
    assert xf._check_dump_coverage(schema, dump) == []


def test_no_dump_means_no_coverage_signal():
    assert xf._check_dump_coverage({"fields": []}, None) == []


# --------------------------------------------------------------------------- #
# 2. _stamp_extraction_info
# --------------------------------------------------------------------------- #

def test_stamp_produces_model_valid_extraction_info():
    schema = {
        "source": "pdf",
        "schema_version": "2",
        "form_metadata": {
            "title": "T", "form_number": "T-1", "total_widgets": 1,
            "total_fields": 1, "version": "unknown", "language": "en",
        },
        "parts": [], "sections": [
            {"id": "s1", "label": "S1", "order": 0, "fields": ["f1"]},
        ],
        "fields": [{
            "id": "f1", "name": "F1", "spoken_name": "field one",
            "type": "text", "section_id": "s1",
            "pdf_field_name": "top[0].f1[0]",
        }],
    }
    xf._stamp_extraction_info(schema)
    info = schema["extraction_info"]
    assert info["extractor_version"] == xf.EXTRACTOR_VERSION
    assert info["manual_review_required"] is True
    assert info["extraction_confidence"] == 0.0
    assert "T" in info["extracted_at"]  # ISO timestamp separator
    # The stanza satisfies the backend contract the publish gate enforces.
    parsed = FormSchema.model_validate(schema)
    assert parsed.extraction_info is not None


# --------------------------------------------------------------------------- #
# 3. _classify_exit
# --------------------------------------------------------------------------- #

def _draft(authoring):
    return {"fields": [{"id": "f1"}], "_bakeoff": {"authoring": authoring}}


def test_clean_draft_classifies_valid():
    a = {"schema_valid": True, "lint": {"errors": 0},
         "repair": {"applied": 0}, "coverage": {"unclaimed_fillable": []}}
    assert xf._classify_exit(_draft(a)) == xf.EXIT_VALID


def test_repair_failed_classifies_issues_not_valid():
    # Previously invisible: a REPAIR-FAILED draft with passing Pydantic and
    # 0 lint ERRORs exited 0 VALID (bd l1a9).
    a = {"schema_valid": True, "lint": {"errors": 0},
         "repair": {"failed": "no PDF widget name: ghost"},
         "coverage": {"unclaimed_fillable": []}}
    assert xf._classify_exit(_draft(a)) == xf.EXIT_ISSUES


def test_coverage_gap_classifies_issues():
    a = {"schema_valid": True, "lint": {"errors": 0},
         "repair": {"applied": 0},
         "coverage": {"unclaimed_fillable": ["top[0].b[0]"]}}
    assert xf._classify_exit(_draft(a)) == xf.EXIT_ISSUES


def test_empty_draft_still_hard_fails():
    assert xf._classify_exit({"fields": []}) == xf.EXIT_HARD_FAIL
