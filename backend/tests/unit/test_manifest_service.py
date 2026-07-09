"""Unit tests for manifest_service helpers using inline schemas,
plus the JIT token-budget guard against the real I-90 schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services.manifest_service import (
    estimate_manifest_tokens,
    format_manifest_for_context,
    generate_part_manifest,
    get_next_field_schema,
    should_include_schema_in_response,
)

# The documented JIT manifest token budget: a single part's manifest must fit
# well inside the system instruction (see docs/components/jit-schema.md).
JIT_MANIFEST_TOKEN_BUDGET = 500

_I90_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "form-kits" / "i-90" / "schema.json"
)


def _load_i90_schema() -> dict:
    with open(_I90_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _build_part_data_with_fields(schema: dict, part: dict) -> dict:
    """Resolve a part's section_ids -> field ids -> field dicts (the shape
    generate_part_manifest consumes), mirroring the JIT manifest path."""
    part_data = {"id": part["id"], "label": part["label"], "fields": []}
    for section_id in part.get("section_ids", []):
        section = next(
            (s for s in schema.get("sections", []) if s["id"] == section_id), None
        )
        if not section:
            continue
        for field_id in section.get("fields", []):
            field = next(
                (f for f in schema.get("fields", []) if f["id"] == field_id), None
            )
            if field:
                part_data["fields"].append(field)
    return part_data


@pytest.fixture()
def sample_part() -> dict:
    return {
        "id": "part_1",
        "label": "Part 1 - Basics",
        "fields": [
            {"id": "field_1", "spoken_name": "full name", "name": "Full Name"},
            {"id": "field_2", "name": "Email"},  # spoken_name fallback to name
        ],
    }


def test_generate_part_manifest_only_keeps_spoken_names(sample_part):
    manifest = generate_part_manifest(sample_part, previous_parts_manifests=[])

    assert manifest["current_part"]["part_id"] == "part_1"
    assert manifest["current_part"]["part_label"] == "Part 1 - Basics"
    assert manifest["current_part"]["fields"] == [
        {"field_id": "field_1", "spoken_name": "full name"},
        {"field_id": "field_2", "spoken_name": "Email"},
    ]


def test_format_manifest_lists_previous_parts(sample_part):
    previous = [{
        "part_id": "part_0",
        "part_label": "Intro",
        "fields": [{"field_id": "f0", "spoken_name": "intro"}],
    }]
    manifest = generate_part_manifest(sample_part, previous)

    formatted = format_manifest_for_context(manifest)
    assert "CURRENT PART: Part 1 - Basics" in formatted
    assert "Fields: field_1|full name | field_2|Email" in formatted
    assert "PREVIOUS PARTS" in formatted
    assert "Intro: f0|intro" in formatted


def test_estimate_manifest_tokens_uses_text_length(sample_part):
    manifest = generate_part_manifest(sample_part, [])
    tokens = estimate_manifest_tokens(manifest)
    assert tokens > 0


def test_get_next_field_schema_walks_fields(sample_part):
    assert get_next_field_schema(sample_part, None)["id"] == "field_1"
    assert get_next_field_schema(sample_part, "field_1")["id"] == "field_2"
    assert get_next_field_schema(sample_part, "field_2") is None


def test_get_next_field_schema_strips_pdf_plumbing_from_options():
    """The JIT next_field_schema rides inside confirm_field tool responses --
    a model-facing payload. Schema option dicts carry PDF plumbing
    (pdf_field_name, pdf_on_value, and per-option pdf_position since bd
    polyglot-pdf-5f41) plus label_translations, none of which the voice model
    can use: assert options are sanitized to value/label/spoken_label only
    (epic polyglot-pdf-oaiz rubric R5)."""
    part = {"id": "p", "label": "P", "fields": [{
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
    }]}
    options = get_next_field_schema(part, None)["options"]
    assert options == [
        {"value": "hispanic", "label": "Hispanic or Latino",
         "spoken_label": "Hispanic or Latino"},
        {"value": "not_hispanic", "label": "Not Hispanic"},
    ]


def test_should_include_schema_in_response_tracks_loaded_state():
    loaded = set()
    assert should_include_schema_in_response("field_1", loaded) is True
    loaded.add("field_1")
    assert should_include_schema_in_response("field_1", loaded) is False
    assert should_include_schema_in_response("field_2", loaded) is True


def test_i90_part_manifests_stay_under_jit_token_budget():
    """Every real I-90 part's manifest must fit the documented JIT budget.

    Guards the budget the deleted manual validation script
    (backend/test_jit_system_e2e.py, bd polyglot-pdf-o0pc) used to check by
    hand: if the schema or the manifest text format grows, this catches the
    regression automatically.
    """
    schema = _load_i90_schema()
    parts = schema.get("parts", [])
    assert parts, "I-90 schema has no parts -- schema shape changed?"

    checked = 0
    for part in parts:
        part_data = _build_part_data_with_fields(schema, part)
        if not part_data["fields"]:
            # e.g. I-90 part_7 is an instructions-only part with no sections
            continue
        checked += 1
        manifest = generate_part_manifest(part_data, [])
        tokens = estimate_manifest_tokens(manifest)
        assert tokens < JIT_MANIFEST_TOKEN_BUDGET, (
            f"part {part['id']} manifest is {tokens} tokens "
            f"(budget {JIT_MANIFEST_TOKEN_BUDGET})"
        )
    assert checked > 0, "no I-90 part resolved any fields -- schema shape changed?"

