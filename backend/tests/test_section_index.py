"""
Unit tests for section index validation.
Tests that the section index correctly maps all 174 fields with no gaps or overlaps.
"""

import json
import pytest
from pathlib import Path


@pytest.fixture
def section_index():
    """Load the section index."""
    index_path = Path(__file__).parent.parent.parent / "demos" / "adult_intake_sections_index.json"
    with open(index_path, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def full_schema():
    """Load the full form schema."""
    schema_path = Path(__file__).parent.parent.parent / "demos" / "adult_intake_demo_schema.json"
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def test_index_structure(section_index):
    """Test that index has correct structure."""
    assert "form_id" in section_index
    assert section_index["form_id"] == "adult-intake-demo"
    assert "total_sections" in section_index
    assert section_index["total_sections"] == 8
    assert "sections" in section_index
    assert len(section_index["sections"]) == 8


def test_section_count(section_index):
    """Test that we have exactly 8 sections."""
    assert len(section_index["sections"]) == 8


def test_field_count_sum(section_index):
    """Test that sum of all field_count equals 174."""
    total = sum(section["field_count"] for section in section_index["sections"])
    assert total == 174, f"Expected 174 fields, got {total}"


def test_field_indices_sum(section_index):
    """Test that sum of field indices lengths equals 174."""
    total = sum(len(section["field_indices"]) for section in section_index["sections"])
    assert total == 174, f"Expected 174 field indices, got {total}"


def test_field_count_matches_indices(section_index):
    """Test that field_count matches length of field_indices for each section."""
    for section in section_index["sections"]:
        assert section["field_count"] == len(section["field_indices"]), \
            f"Section {section['section_number']}: field_count {section['field_count']} != indices length {len(section['field_indices'])}"


def test_no_gaps_or_overlaps(section_index):
    """Test that all indices 0-173 appear exactly once."""
    all_indices = []
    for section in section_index["sections"]:
        all_indices.extend(section["field_indices"])
    
    # Check for duplicates
    assert len(all_indices) == len(set(all_indices)), "Duplicate indices found"
    
    # Check all indices present
    expected = set(range(174))
    actual = set(all_indices)
    assert expected == actual, f"Missing: {expected - actual}, Extra: {actual - expected}"


def test_indices_are_sequential(section_index):
    """Test that indices within each section are sequential (no gaps)."""
    for section in section_index["sections"]:
        indices = section["field_indices"]
        for i in range(len(indices) - 1):
            assert indices[i + 1] == indices[i] + 1, \
                f"Section {section['section_number']} has gap: {indices[i]} -> {indices[i + 1]}"


def test_section_numbers_sequential(section_index):
    """Test that section numbers are 1-8 in order."""
    for i, section in enumerate(section_index["sections"], start=1):
        assert section["section_number"] == i, \
            f"Expected section_number {i}, got {section['section_number']}"


def test_section_ids_unique(section_index):
    """Test that all section IDs are unique."""
    ids = [section["section_id"] for section in section_index["sections"]]
    assert len(ids) == len(set(ids)), "Duplicate section IDs found"


def test_section_labels_unique(section_index):
    """Test that all section labels are unique."""
    labels = [section["section_label"] for section in section_index["sections"]]
    assert len(labels) == len(set(labels)), "Duplicate section labels found"


def test_indices_match_schema_length(section_index, full_schema):
    """Test that max index matches schema length."""
    max_index = max(
        max(section["field_indices"]) 
        for section in section_index["sections"]
    )
    schema_length = len(full_schema["fields"])
    
    assert max_index == schema_length - 1, \
        f"Max index {max_index} should equal schema length - 1 ({schema_length - 1})"


def test_section_breakdown_as_specified(section_index):
    """Test that sections match the specified breakdown (after merging sections 6 & 7):
    1. Client Information (12 fields)
    2. Reasons for Services & Goals (10 fields)
    3. Relationships & Development (13 fields)
    4. Living Situation & Support (21 fields)
    5. Substance Use & Legal History (30 fields)
    6. Mental Health, Safety & Trauma (25 fields - merged)
    7. Medical Information & Providers (38 fields)
    8. Medications & Demographics (25 fields)
    """
    expected_counts = [12, 10, 13, 21, 30, 25, 38, 25]
    actual_counts = [section["field_count"] for section in section_index["sections"]]
    
    assert actual_counts == expected_counts, \
        f"Expected {expected_counts}, got {actual_counts}"


def test_indices_are_integers(section_index):
    """Test that all indices are integers (not strings or ranges)."""
    for section in section_index["sections"]:
        for idx in section["field_indices"]:
            assert isinstance(idx, int), \
                f"Section {section['section_number']} has non-integer index: {idx} (type: {type(idx)})"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
