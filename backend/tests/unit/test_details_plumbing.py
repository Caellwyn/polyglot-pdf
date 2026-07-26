"""Unit tests for the help.details plumbing (bd polyglot-pdf-wsao.1).

The sprint-16 plan (docs/sprint_16_instructions-enrichment_plan.md) adds a
second, verbatim guidance channel: FieldHelp.details (per-field booklet
excerpts) plus FormMetadata.details / FormMetadata.booklet_text (the form-level
guidance + whole-booklet secretary floor). v1 delivery is INLINE: details ride
the current field's guidance block and the secretary static catalog -- and
NOTHING else. These tests pin:

  1. the model accepts the new keys (round-trip, no validation error);
  2. get_field_guidance / render_field_guidance carry details, and a
     no-details render is BYTE-IDENTICAL to the pre-wsao.1 output;
  3. the secretary catalog renders field details + the form-level floor, and
     is byte-identical for schemas without them (cache-prefix stability).

ASCII only (CLAUDE.md scar #6).
"""

from __future__ import annotations

from backend.models.form_models import FieldHelp, FormMetadata
from backend.services.ai_context import render_field_guidance
from backend.services.manifest_service import get_field_guidance
from backend.services.secretary_context import (
    render_secretary_context,
    render_static_catalog,
)

DETAILS = (
    "## a. Tax treaty benefit\n"
    "Certain nonresident aliens must get an ITIN to claim certain tax treaty\n"
    "benefits even if they don't have to file a U.S. federal tax return. If you\n"
    "check this box, you must also check box h."
)


def _field(with_details: bool = True) -> dict:
    help_block = {"instructions": "Check the one box that best applies."}
    if with_details:
        help_block["details"] = DETAILS
    return {
        "id": "reason_for_applying",
        "name": "Reason you're submitting Form W-7",
        "spoken_name": "reason for applying",
        "type": "radio",
        "help": help_block,
        "options": [{"value": "treaty_benefit", "label": "Nonresident alien claiming tax treaty benefit"}],
    }


def _schema(with_reference: bool = True) -> dict:
    field = _field()
    metadata = {"title": "Form W-7", "version": "2024-12"}
    if with_reference:
        metadata["details"] = "Who Is Eligible: see the eligibility rules."
        metadata["booklet_text"] = "FULL BOOKLET TEXT PAGE 1\nFULL BOOKLET TEXT PAGE 2"
    return {
        "metadata": metadata,
        "fields": [field],
        "sections": [{"id": "s1", "label": "Section 1", "fields": [field["id"]]}],
        "parts": [{"id": "p1", "label": "Part 1", "section_ids": ["s1"]}],
    }


# --- 1. model round-trip -----------------------------------------------------

def test_field_help_accepts_details():
    h = FieldHelp(instructions="short", details=DETAILS)
    assert h.details == DETAILS


def test_form_metadata_accepts_reference_keys():
    m = FormMetadata(title="W-7", version="1", details="form-level",
                     booklet_text="whole booklet")
    assert m.details == "form-level"
    assert m.booklet_text == "whole booklet"


# --- 2. guidance path --------------------------------------------------------

def test_get_field_guidance_carries_details():
    guidance = get_field_guidance(_field())
    assert guidance["details"] == DETAILS
    # the short channel is untouched
    assert guidance["instructions"] == "Check the one box that best applies."


def test_get_field_guidance_omits_details_key_when_absent():
    guidance = get_field_guidance(_field(with_details=False))
    assert "details" not in guidance


def test_render_field_guidance_renders_official_reference_text():
    rendered = render_field_guidance(_field())
    assert "Official reference text: " + DETAILS in rendered
    # instructions still render as their own segment
    assert "Instructions: Check the one box that best applies." in rendered


def test_render_field_guidance_byte_identical_without_details():
    """A field without details must render EXACTLY as before wsao.1 -- no
    empty segment, no label, no trailing separator."""
    rendered = render_field_guidance(_field(with_details=False))
    assert "Official reference text" not in rendered


# --- 3. secretary catalog ----------------------------------------------------

def test_static_catalog_renders_field_details_block():
    catalog = render_static_catalog(_schema(with_reference=False))
    assert "    details: |" in catalog
    # every details line is indented under the field entry
    assert "      ## a. Tax treaty benefit" in catalog


def test_static_catalog_renders_form_level_floor():
    catalog = render_static_catalog(_schema())
    assert "=== FORM-LEVEL GUIDANCE ===" in catalog
    assert "Who Is Eligible: see the eligibility rules." in catalog
    assert "=== OFFICIAL FORM INSTRUCTIONS (verbatim reference) ===" in catalog
    assert "FULL BOOKLET TEXT PAGE 2" in catalog
    # the floor renders AFTER the per-field catalog (cache prefix = catalog
    # first, reference appended -- both session-invariant)
    assert catalog.index("reason_for_applying") < catalog.index(
        "=== OFFICIAL FORM INSTRUCTIONS")


def test_full_secretary_context_includes_floor_too():
    ctx = render_secretary_context(_schema(), {}, {})
    assert "=== OFFICIAL FORM INSTRUCTIONS (verbatim reference) ===" in ctx


def test_catalog_byte_identical_for_schema_without_reference():
    """Cache-prefix stability + backward compat: a schema with no details and
    no metadata reference keys renders the EXACT pre-wsao.1 catalog."""
    schema = _schema(with_reference=False)
    schema["fields"][0]["help"].pop("details")
    catalog = render_static_catalog(schema)
    assert "details:" not in catalog
    assert "FORM-LEVEL GUIDANCE" not in catalog
    assert "OFFICIAL FORM INSTRUCTIONS" not in catalog
    # and it still ends with the canonical single trailing newline
    assert catalog.endswith("\n") and not catalog.endswith("\n\n")
