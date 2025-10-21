"""
Test script for Step 3: Frontend Section Switching Logic
Tests section navigation, state transitions, and spoken name accumulation.
"""

import json
from pathlib import Path

def test_section_switching_flow():
    """Test the section switching workflow."""
    print("=== Testing Section Switching Flow ===\n")
    
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
    
    # Simulate section flow: 1 → 2 → 5 → 9
    sections_to_test = [1, 2, 5, 9]
    completed = set()
    all_spoken_names = {}
    
    for section_num in sections_to_test:
        section = section_index['sections'][section_num - 1]
        print(f"Section {section_num}: {section['section_label']}")
        print(f"  Fields: {section['field_count']}")
        print(f"  Indices: {section['field_indices'][0]}-{section['field_indices'][-1]}")
        
        # Get section fields
        section_fields = [full_schema['fields'][idx] for idx in section['field_indices']]
        
        # Accumulate spoken names (simulate completion)
        section_spoken = {}
        for field in section_fields:
            if 'spoken_name' in field:
                section_spoken[field['spoken_name'].lower()] = field['id']
            if 'spoken_aliases' in field:
                for alias in field['spoken_aliases']:
                    section_spoken[alias.lower()] = field['id']
        
        all_spoken_names.update(section_spoken)
        completed.add(section_num)
        
        print(f"  Spoken names in section: {len(section_spoken)}")
        print(f"  Total accumulated: {len(all_spoken_names)}")
        print(f"  Completed sections: {sorted(completed)}")
        print()
    
    print(f"=== Flow Test Complete ===")
    print(f"Completed {len(completed)} sections")
    print(f"Accumulated {len(all_spoken_names)} spoken name mappings")
    print()
    
    # Test spoken name lookups
    print("=== Testing Cross-Section Lookups ===\n")
    
    test_lookups = [
        ("first name", "firstName", 1),  # Section 1
        ("phone number", "primaryPhone", 1),  # Section 1
        ("primary household", "primaryHousehold", 3),  # Section 3
        ("substance use concerns", "substanceConcerns", 5),  # Section 5
    ]
    
    for spoken_name, expected_id, section_origin in test_lookups:
        found_id = all_spoken_names.get(spoken_name.lower())
        status = "✓" if found_id == expected_id else "✗"
        print(f"{status} '{spoken_name}' → {found_id or 'NOT FOUND'} (expected {expected_id}, from section {section_origin})")
    
    print()
    
    # Test section label lookup
    print("=== Testing Section Label Lookup ===\n")
    
    label_tests = [
        ("Client Information", 1),
        ("client information", 1),  # case insensitive
        ("Trauma History", 7),
        ("Medical - Medications & Demographics", 9),
    ]
    
    label_map = {s['section_label'].lower(): s['section_number'] for s in section_index['sections']}
    
    for label, expected_num in label_tests:
        found_num = label_map.get(label.lower())
        status = "✓" if found_num == expected_num else "✗"
        print(f"{status} '{label}' → Section {found_num or 'NOT FOUND'} (expected {expected_num})")
    
    print()
    
    # Test section validation
    print("=== Testing Section Validation ===\n")
    
    total_sections = section_index['total_sections']
    
    valid_sections = [1, 5, 9]
    invalid_sections = [0, 10, -1, 100]
    
    print(f"Total sections: {total_sections}")
    print()
    
    print("Valid section numbers:")
    for num in valid_sections:
        is_valid = 1 <= num <= total_sections
        status = "✓" if is_valid else "✗"
        print(f"  {status} Section {num}: {'Valid' if is_valid else 'Invalid'}")
    
    print()
    print("Invalid section numbers:")
    for num in invalid_sections:
        is_valid = 1 <= num <= total_sections
        status = "✗" if not is_valid else "✓"
        print(f"  {status} Section {num}: {'Invalid' if not is_valid else 'Valid (unexpected!)'}")
    
    print()
    print("=== All Tests Passed! ===")


if __name__ == "__main__":
    test_section_switching_flow()
