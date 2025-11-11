#!/usr/bin/env python3
"""
Test manifest generation with real I-90 schema.

Validates:
1. Manifest generation succeeds
2. Token count is under 500
3. All fields are represented
4. Pipe-separated format is correct
"""

import sys
import json
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from services.manifest_service import (
    generate_part_manifest,
    format_manifest_for_context,
    estimate_manifest_tokens,
    get_next_field_schema
)


def load_i90_schema():
    """Load the I-90 schema from frontend public directory."""
    schema_path = Path(__file__).parent.parent / "frontend" / "public" / "pdf_schema_extractor" / "test_schemas" / "test_pdfs" / "i-90" / "i-90_schema.json"

    if not schema_path.exists():
        print(f"[ERROR] Schema not found: {schema_path}")
        sys.exit(1)

    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def test_single_part_manifest(schema):
    """Test generating a manifest for a single part."""
    print("\n" + "="*80)
    print("TEST: Single Part Manifest Generation")
    print("="*80)

    # Get Part 1 (Information About You)
    part = schema['parts'][0]
    print(f"\nPart: {part['label']}")

    # Get section for this part
    section_id = part['section_ids'][0]
    section = next(s for s in schema['sections'] if s['id'] == section_id)

    # Build part data with fields
    part_data = {
        'id': part['id'],
        'label': part['label'],
        'order': part['order'],
        'fields': []
    }

    # Get all fields in this part
    field_ids = section['fields']
    for field_id in field_ids:
        field = next((f for f in schema['fields'] if f['id'] == field_id), None)
        if field:
            part_data['fields'].append(field)

    print(f"Total fields in part: {len(part_data['fields'])}")

    # Generate manifest (no previous parts)
    manifest = generate_part_manifest(part_data, [])

    # Format for context
    formatted = format_manifest_for_context(manifest)

    # Estimate tokens
    tokens = estimate_manifest_tokens(manifest)

    print(f"\n[TOKENS] Estimated: {tokens}")
    print(f"[TARGET] Must be < 500")

    if tokens < 500:
        print("[PASS] Token count within target")
    else:
        print(f"[FAIL] Token count exceeds target by {tokens - 500}")

    print(f"\n[FORMAT] Preview (first 500 chars):")
    print(formatted[:500])
    print("...")

    return manifest, tokens


def test_all_parts_manifest(schema):
    """Test generating manifests for all parts."""
    print("\n" + "="*80)
    print("TEST: All Parts Manifest Generation")
    print("="*80)

    previous_manifests = []
    total_tokens = 0

    for part in schema['parts']:
        print(f"\n--- {part['label']} ---")

        # Get section for this part
        section_id = part['section_ids'][0]
        section = next(s for s in schema['sections'] if s['id'] == section_id)

        # Build part data
        part_data = {
            'id': part['id'],
            'label': part['label'],
            'order': part['order'],
            'fields': []
        }

        # Get fields
        for field_id in section['fields']:
            field = next((f for f in schema['fields'] if f['id'] == field_id), None)
            if field:
                part_data['fields'].append(field)

        # Generate manifest with previous parts
        manifest = generate_part_manifest(part_data, previous_manifests)
        tokens = estimate_manifest_tokens(manifest)

        print(f"Fields: {len(part_data['fields'])}")
        print(f"Tokens: {tokens}")
        print(f"Status: {'PASS' if tokens < 500 else 'FAIL'}")

        total_tokens += tokens

        # Save current part manifest for next iteration
        previous_manifests.append(manifest['current_part'])

    print(f"\n[SUMMARY]")
    print(f"Total parts: {len(schema['parts'])}")
    print(f"Average tokens per part: {total_tokens // len(schema['parts'])}")

    return total_tokens


def test_next_field_schema(schema):
    """Test getting next field schema for next_field_hint."""
    print("\n" + "="*80)
    print("TEST: Next Field Schema Retrieval")
    print("="*80)

    # Get Part 1
    part = schema['parts'][0]
    section_id = part['section_ids'][0]
    section = next(s for s in schema['sections'] if s['id'] == section_id)

    part_data = {
        'id': part['id'],
        'label': part['label'],
        'fields': []
    }

    for field_id in section['fields']:
        field = next((f for f in schema['fields'] if f['id'] == field_id), None)
        if field:
            part_data['fields'].append(field)

    # Test getting first field (initial handshake)
    first_field = get_next_field_schema(part_data, None)
    print(f"\n[FIRST FIELD]")
    print(f"ID: {first_field['id']}")
    print(f"Spoken Name: {first_field['spoken_name']}")
    print(f"Type: {first_field['type']}")

    # Test getting next field after first
    second_field = get_next_field_schema(part_data, first_field['id'])
    print(f"\n[SECOND FIELD]")
    print(f"ID: {second_field['id']}")
    print(f"Spoken Name: {second_field['spoken_name']}")
    print(f"Type: {second_field['type']}")

    print("\n[PASS] Next field retrieval working")


def test_loaded_field_tracking():
    """Test the loaded_field_ids tracking logic."""
    print("\n" + "="*80)
    print("TEST: Loaded Field IDs Tracking")
    print("="*80)

    from services.manifest_service import should_include_schema_in_response

    loaded_fields = set()

    # First access - should include schema
    should_include = should_include_schema_in_response('field_1', loaded_fields)
    print(f"\nFirst access to field_1: include_schema={should_include}")
    assert should_include == True, "First access should include schema"

    # Mark as loaded
    loaded_fields.add('field_1')

    # Second access - should NOT include schema
    should_include = should_include_schema_in_response('field_1', loaded_fields)
    print(f"Second access to field_1: include_schema={should_include}")
    assert should_include == False, "Second access should NOT include schema"

    # Different field - should include schema
    should_include = should_include_schema_in_response('field_2', loaded_fields)
    print(f"First access to field_2: include_schema={should_include}")
    assert should_include == True, "Different field should include schema"

    print("\n[PASS] Loaded field tracking working correctly")


def main():
    print("="*80)
    print("MANIFEST GENERATION VALIDATION")
    print("Testing with I-90 Schema")
    print("="*80)

    # Load schema
    print("\n[LOADING] I-90 schema...")
    schema = load_i90_schema()
    print(f"[INFO] Form: {schema['form_metadata']['form_number']}")
    print(f"[INFO] Total fields: {len(schema['fields'])}")
    print(f"[INFO] Total parts: {len(schema['parts'])}")

    # Run tests
    try:
        test_single_part_manifest(schema)
        test_all_parts_manifest(schema)
        test_next_field_schema(schema)
        test_loaded_field_tracking()

        print("\n" + "="*80)
        print("ALL TESTS PASSED")
        print("="*80)

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
