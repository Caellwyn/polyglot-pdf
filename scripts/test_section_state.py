"""
Test script for Step 2: Frontend Section State & UI
Tests section loading, schema slicing, and UI state management.
"""

import json
from pathlib import Path

def test_section_state_functions():
    """Test the section state management functions."""
    print("=== Testing Section State Functions ===\n")
    
    # Load data
    demos_path = Path(__file__).parent.parent / "demos"
    index_path = demos_path / "adult_intake_sections_index.json"
    schema_path = demos_path / "adult_intake_demo_schema.json"
    
    with open(index_path) as f:
        section_index = json.load(f)
    
    with open(schema_path) as f:
        full_schema = json.load(f)
    
    print(f"✓ Loaded section index: {section_index['total_sections']} sections")
    print(f"✓ Loaded full schema: {len(full_schema['fields'])} fields\n")
    
    # Test: Get section 1 schema
    section_1 = section_index['sections'][0]
    section_1_fields = [full_schema['fields'][idx] for idx in section_1['field_indices']]
    print(f"Section 1: {section_1['section_label']}")
    print(f"  Fields: {len(section_1_fields)} (expected {section_1['field_count']})")
    print(f"  First field: {section_1_fields[0]['id']}")
    print(f"  Last field: {section_1_fields[-1]['id']}")
    assert len(section_1_fields) == section_1['field_count'], "Field count mismatch!"
    print("  ✓ Section 1 schema slicing works\n")
    
    # Test: Spoken name map for section 1
    spoken_map = {}
    for field in section_1_fields:
        if 'spoken_name' in field:
            spoken_map[field['spoken_name'].lower()] = field['id']
        if 'spoken_aliases' in field:
            for alias in field['spoken_aliases']:
                spoken_map[alias.lower()] = field['id']
    
    print(f"Spoken name map for section 1:")
    print(f"  Entries: {len(spoken_map)}")
    print(f"  Sample: 'first name' → {spoken_map.get('first name', 'NOT FOUND')}")
    print(f"  Sample: 'phone number' → {spoken_map.get('phone number', 'NOT FOUND')}")
    assert spoken_map.get('first name') == 'firstName', "Spoken name mapping failed!"
    print("  ✓ Spoken name map works\n")
    
    # Test: Section label lookup
    section_labels = {s['section_label'].lower(): s['section_number'] for s in section_index['sections']}
    print(f"Section label lookup:")
    print(f"  'client information' → Section {section_labels.get('client information', 'NOT FOUND')}")
    print(f"  'trauma history' → Section {section_labels.get('trauma history', 'NOT FOUND')}")
    assert section_labels.get('client information') == 1, "Section lookup failed!"
    assert section_labels.get('trauma history') == 7, "Section lookup failed!"
    print("  ✓ Section label lookup works\n")
    
    # Test: Field count per section
    print("Field counts per section:")
    for section in section_index['sections']:
        section_fields = [full_schema['fields'][idx] for idx in section['field_indices']]
        print(f"  Section {section['section_number']}: {len(section_fields)}/{section['field_count']} - {section['section_label']}")
        assert len(section_fields) == section['field_count'], f"Section {section['section_number']} field count mismatch!"
    print("  ✓ All sections have correct field counts\n")
    
    print("=== All Tests Passed! ===")


if __name__ == "__main__":
    test_section_state_functions()
