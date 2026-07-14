"""Unit tests for manifest_service.get_field_guidance (the DTI per-field
guidance builder) and its shared option-sanitizer.

The legacy JIT manifest helpers (generate_part_manifest, get_next_field_schema,
format_manifest_for_context, should_include_schema_in_response,
estimate_manifest_tokens) and their tests were removed with the JIT SI mode in bd
polyglot-pdf-en2j; DTI is the shipped reduced-SI mode.
"""

from __future__ import annotations

import json

from backend.services.manifest_service import get_field_guidance


def test_get_field_guidance_strips_pdf_plumbing_from_options():
    """The DTI get_field_guidance dict feeds both the system instruction and the
    confirm_field tool response -- a model-facing payload. Its options must be
    sanitized to value/label/spoken_label via the shared helper, so
    pdf_field_name/pdf_on_value/pdf_position/label_translations never leak (bd
    polyglot-pdf-lj5v; boundary first established in bd polyglot-pdf-5f41)."""
    field = {
        "id": "eth", "name": "Ethnicity", "spoken_name": "ethnicity",
        "type": "radio",
        "options": [
            {"value": "hispanic", "label": "Hispanic or Latino",
             "spoken_label": "Hispanic or Latino",
             "label_translations": {"es": "Hispano o Latino"},
             "pdf_field_name": "P3_checkbox5_Hispanic[0]",
             "pdf_on_value": "1",
             "pdf_position": {"page": 3, "x": 344.0, "y": 115.58,
                              "width": 10.0, "height": 10.0}},
            {"value": "not_hispanic", "label": "Not Hispanic"},
        ],
    }
    options = get_field_guidance(field)["options"]
    assert options == [
        {"value": "hispanic", "label": "Hispanic or Latino",
         "spoken_label": "Hispanic or Latino"},
        {"value": "not_hispanic", "label": "Not Hispanic"},
    ]
    # Belt-and-suspenders: no pdf plumbing key survives anywhere in the payload.
    flat = json.dumps(get_field_guidance(field))
    for leaked in ("pdf_field_name", "pdf_on_value", "pdf_position",
                   "label_translations"):
        assert leaked not in flat


def test_get_field_guidance_passes_bare_string_options_through():
    """get_field_guidance must tolerate bare-string options (allowed_values
    shape) unchanged."""
    field = {
        "id": "f", "name": "F", "spoken_name": "f", "type": "select",
        "allowed_values": ["alpha", "beta"],
    }
    assert get_field_guidance(field)["options"] == ["alpha", "beta"]


def test_get_field_guidance_reads_required_from_validation_not_top_level():
    """required lives at validation.required (the canonical shape). A top-level
    `required` is read by no consumer and must NOT surface in the guidance; the
    nested one must (bd polyglot-pdf-a1ql)."""
    nested = {
        "id": "acct", "name": "Account", "spoken_name": "account", "type": "text",
        "validation": {"required": True},
    }
    assert get_field_guidance(nested).get("required") is True

    top_level_only = {
        "id": "acct", "name": "Account", "spoken_name": "account", "type": "text",
        "required": True,  # dead location -- must be ignored
    }
    assert "required" not in get_field_guidance(top_level_only)
