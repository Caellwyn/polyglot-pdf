"""Editor-merge output is v2-lint-clean and fills correctly (bd h76m.10).

The schema editor's mergeFields (schema-editor/src/utils/fieldGrouping.ts)
consolidates N separate W-7-style checkbox widgets into ONE v2 checkbox_group:
type=checkbox_group, NO field-level pdf_field_name, option.value = a semantic
slug minted from the label (unique), per-option pdf_field_name = the source
widget. This test pins the CROSS-LANGUAGE half of exit criterion 1 -- that the
exact shape mergeFields emits (a) passes schema_lint with zero ERRORs when
stamped v2, (b) validates under the strict Pydantic model, and (c) round-trips
a real PDF fill via /fill-pdf (the group's selected slugs land on the right
widgets). The TS side pins the transform itself
(schema-editor/src/utils/fieldGrouping.test.ts).

ASCII only.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from backend.services.schema_lint import lint_schema, has_errors
from backend.models.form_models import FormSchema
from backend.routes.pdf_fill_routes import PDFFillRequest, fill_pdf

_KIT_ROOT = Path(__file__).resolve().parents[2] / "form-kits" / "i-90"

# The checkbox_group EXACTLY as mergeFields emits it for the i-90 race widgets
# (slug values minted from labels; per-option pdf_field_name; no field-level
# pdf_field_name). Kept in sync with fieldGrouping.test.ts's merge assertions.
_MERGED_RACE_GROUP = {
    "id": "race_group",
    "name": "White",
    "spoken_name": "race",
    "label": "Race",
    "type": "checkbox_group",
    "section_id": "s1",
    "read_only": False,
    "required": False,
    "options": [
        {"value": "white", "label": "White", "pdf_field_name": "P3_checkbox7_White[0]"},
        {"value": "asian", "label": "Asian", "pdf_field_name": "P3_checkbox7_Asian[0]"},
        {"value": "black", "label": "Black", "pdf_field_name": "P3_checkbox7_Black[0]"},
        {"value": "american_indian", "label": "American Indian", "pdf_field_name": "P3_checkbox7_Indian[0]"},
        {"value": "native_hawaiian", "label": "Native Hawaiian", "pdf_field_name": "P3_checkbox7_Hawaiian[0]"},
    ],
}

_ALL_LEAVES = [o["pdf_field_name"] for o in _MERGED_RACE_GROUP["options"]]


def _v2_schema_with_group() -> dict:
    return {
        "source": "pdf",
        "schema_version": "2",
        "form_metadata": {"title": "i-90 race merge", "version": "1"},
        "extraction_info": {
            "extracted_at": "2026-07-05T00:00:00Z", "extraction_confidence": 1.0,
            "extractor_version": "test", "manual_review_required": False,
        },
        "sections": [{"id": "s1", "label": "S1", "order": 1, "fields": ["race_group"]}],
        "fields": [json.loads(json.dumps(_MERGED_RACE_GROUP))],
    }


def test_merged_group_lints_clean_as_v2():
    findings = lint_schema(_v2_schema_with_group())
    errors = [f for f in findings if f.severity == "error"]
    assert not has_errors(findings), (
        "merged checkbox_group is not v2-lint-clean: "
        + "; ".join(f"{f.path}: {f.message}" for f in errors)
    )


def test_merged_group_validates_under_strict_model():
    # The strict v2 model enforces the structural rules lint does not
    # (no field-level pdf on a group, per-option fillable, options >= 2).
    schema = FormSchema.model_validate(_v2_schema_with_group())
    grp = schema.get_field("race_group")
    assert grp.type.value == "checkbox_group"
    assert grp.pdf_field_name is None


def _as_states_by_leaf(pdf_bytes: bytes, leaves: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for pno in range(doc.page_count):
            for w in doc[pno].widgets() or []:
                leaf = (w.field_name or "").split(".")[-1]
                if leaf in leaves:
                    as_key = doc.xref_get_key(w.xref, "AS")
                    out[leaf] = (
                        as_key[1]
                        if isinstance(as_key, (list, tuple)) and len(as_key) > 1
                        else None
                    )
    finally:
        doc.close()
    return out


@pytest.mark.skipif(
    not (_KIT_ROOT / "form.pdf").exists(), reason="i-90 kit not present"
)
def test_merged_group_round_trips_a_real_fill():
    """The group's selected option SLUGS fill exactly their widgets -- the
    editor merge output is genuinely fillable (exit criterion 1)."""
    selected = ["white", "black"]  # slugs
    req = PDFFillRequest(
        kit_id="i-90",
        pdf_filename="form.pdf",
        field_values={"race_group": selected},
        form_schema=_v2_schema_with_group(),
    )
    resp = asyncio.run(fill_pdf(req))
    assert resp.status_code == 200

    states = _as_states_by_leaf(resp.body, _ALL_LEAVES)
    picked = {"P3_checkbox7_White[0]", "P3_checkbox7_Black[0]"}
    for leaf, state in states.items():
        if leaf in picked:
            assert state not in ("/Off", "Off", None), f"{leaf} did not fill"
        else:
            assert state in ("/Off", "Off"), f"{leaf} should not be selected"
