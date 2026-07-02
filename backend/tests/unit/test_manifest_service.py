"""Unit tests for manifest_service helpers using inline schemas."""

from __future__ import annotations

import pytest

from backend.services.manifest_service import (
    estimate_manifest_tokens,
    format_manifest_for_context,
    generate_part_manifest,
    get_next_field_schema,
    should_include_schema_in_response,
)


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


def test_should_include_schema_in_response_tracks_loaded_state():
    loaded = set()
    assert should_include_schema_in_response("field_1", loaded) is True
    loaded.add("field_1")
    assert should_include_schema_in_response("field_1", loaded) is False
    assert should_include_schema_in_response("field_2", loaded) is True

