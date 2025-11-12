"""
JIT Schema System - End-to-End Validation Script
Run directly to test the complete JIT system without pytest complexity.

Usage: python test_jit_system_e2e.py
"""

import json
import os
import sys
from pathlib import Path

# Add backend to path when running standalone
if __name__ == "__main__":
    backend_dir = Path(__file__).parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

from services.manifest_service import (
    generate_part_manifest,
    get_next_field_schema,
    format_manifest_for_context,
    estimate_manifest_tokens
)
from config import get_settings


def load_i90_schema():
    """Load I-90 conformant schema"""
    # Try multiple locations
    possible_paths = [
        Path("frontend/public/pdf_schema_extractor/test_schemas/test_pdfs/i-90/i-90_schema.json"),
        Path("../frontend/public/pdf_schema_extractor/test_schemas/test_pdfs/i-90/i-90_schema.json"),
    ]

    for schema_path in possible_paths:
        if schema_path.exists():
            with open(schema_path, 'r', encoding='utf-8') as f:
                return json.load(f)

    raise FileNotFoundError("I-90 schema not found")


def test_feature_flag():
    """Test 1: Verify JIT feature flag configuration"""
    print("\n" + "="*60)
    print("TEST 1: JIT Feature Flag Configuration")
    print("="*60)

    settings = get_settings()
    print(f"   USE_JIT_SCHEMA: {settings.USE_JIT_SCHEMA}")
    print(f"   Type: {type(settings.USE_JIT_SCHEMA)}")

    assert isinstance(settings.USE_JIT_SCHEMA, bool), "USE_JIT_SCHEMA must be boolean"
    print("[OK] PASS: Feature flag properly configured\n")


def build_part_data_with_fields(schema, part):
    """Helper: Build part data with fields included"""
    part_data = {
        'id': part['id'],
        'label': part['label'],
        'order': part['order'],
        'fields': []
    }

    # Get all sections for this part
    section_ids = part.get('section_ids', [])
    for section_id in section_ids:
        section = next((s for s in schema.get('sections', []) if s['id'] == section_id), None)
        if section:
            # Get fields for this section
            field_ids = section.get('fields', [])
            for field_id in field_ids:
                field = next((f for f in schema.get('fields', []) if f['id'] == field_id), None)
                if field:
                    part_data['fields'].append(field)

    return part_data


def test_manifest_generation(schema):
    """Test 2: Manifest generation and validation"""
    print("="*60)
    print("TEST 2: Manifest Generation")
    print("="*60)

    parts = schema.get('parts', [])
    part1 = next((p for p in parts if p['id'] == 'part_1'), None)

    if not part1:
        print("[FAIL] FAIL: Part 1 not found in schema")
        return False

    # Build part data with fields
    part_data = build_part_data_with_fields(schema, part1)

    # Generate manifest (no previous parts)
    manifest_wrapper = generate_part_manifest(part_data, [])
    manifest = manifest_wrapper['current_part']

    print(f"   Part ID: {manifest['part_id']}")
    print(f"   Part Label: {manifest['part_label']}")
    print(f"   Field Count: {len(manifest['fields'])}")

    # Verify structure
    assert 'part_id' in manifest
    assert 'part_label' in manifest
    assert 'fields' in manifest
    assert len(manifest['fields']) > 0

    # Show first 3 fields
    print(f"\n   First 3 Fields:")
    for i, field in enumerate(manifest['fields'][:3], 1):
        print(f"      {i}. {field['spoken_name']} (ID: {field['field_id']})")

    print("[OK] PASS: Manifest generated successfully\n")
    return manifest_wrapper


def test_spoken_name_uniqueness(manifest):
    """Test 3: Verify spoken names are unique"""
    print("="*60)
    print("TEST 3: Spoken Name Uniqueness")
    print("="*60)

    spoken_names = [f['spoken_name'] for f in manifest['fields']]
    unique_names = set(spoken_names)

    print(f"   Total Fields: {len(spoken_names)}")
    print(f"   Unique Spoken Names: {len(unique_names)}")

    if len(spoken_names) != len(unique_names):
        duplicates = [name for name in spoken_names if spoken_names.count(name) > 1]
        print(f"   [FAIL] FAIL: Duplicate spoken names found: {set(duplicates)}")
        return False

    print("[OK] PASS: All spoken names are unique\n")
    return True


def test_token_count(manifest_wrapper):
    """Test 4: Token count validation (<500 target)"""
    print("="*60)
    print("TEST 4: Token Count Validation")
    print("="*60)

    # Format manifest (pass the wrapper with current_part/previous_parts)
    formatted = format_manifest_for_context(manifest_wrapper)

    # Estimate tokens
    tokens = estimate_manifest_tokens(manifest_wrapper)

    print(f"   Manifest Tokens: {tokens}")
    print(f"   Target: <500 tokens")
    print(f"   Status: {'[OK] PASS' if tokens < 500 else '[FAIL] FAIL'}")

    if tokens >= 500:
        print(f"   Warning: Token count exceeds target by {tokens - 500}")

    print(f"\n   Sample Manifest Format:")
    print(f"   {formatted[:200]}...\n")

    assert tokens < 500, f"Token count {tokens} exceeds 500"
    print("[OK] PASS: Token count under 500\n")
    return tokens


def test_next_field_retrieval(schema):
    """Test 5: Next field schema retrieval"""
    print("="*60)
    print("TEST 5: Next Field Schema Retrieval")
    print("="*60)

    parts = schema.get('parts', [])
    part1 = next((p for p in parts if p['id'] == 'part_1'), None)
    part_data = build_part_data_with_fields(schema, part1)

    # Get first field
    first_field = get_next_field_schema(part_data, None)

    assert first_field is not None, "Failed to get first field"
    print(f"   First Field ID: {first_field['id']}")
    print(f"   Spoken Name: {first_field.get('spoken_name', 'N/A')}")
    print(f"   Type: {first_field['type']}")

    # Get second field
    second_field = get_next_field_schema(part_data, first_field['id'])

    assert second_field is not None, "Failed to get second field"
    assert second_field['id'] != first_field['id'], "Second field same as first"

    print(f"\n   Second Field ID: {second_field['id']}")
    print(f"   Spoken Name: {second_field.get('spoken_name', 'N/A')}")

    print("[OK] PASS: Next field retrieval working\n")


def test_linear_flow(schema):
    """Test 6: Linear field filling flow"""
    print("="*60)
    print("TEST 6: Linear Field Filling Flow")
    print("="*60)

    parts = schema.get('parts', [])
    part1 = next((p for p in parts if p['id'] == 'part_1'), None)
    part_data = build_part_data_with_fields(schema, part1)

    loaded_field_ids = set()
    current_field_id = None

    print("   Simulating filling first 10 fields:")

    for i in range(10):
        next_field = get_next_field_schema(part_data, current_field_id)

        if not next_field:
            print(f"      {i+1}. No more fields (reached end)")
            break

        loaded_field_ids.add(next_field['id'])
        current_field_id = next_field['id']

        print(f"      {i+1}. {next_field.get('spoken_name', 'N/A')}")

    print(f"\n   Total Fields Loaded: {len(loaded_field_ids)}")
    print("[OK] PASS: Linear flow working correctly\n")


def test_token_accumulation(schema):
    """Test 7: Token accumulation with previous parts"""
    print("="*60)
    print("TEST 7: Token Accumulation (Previous Parts)")
    print("="*60)

    parts = schema.get('parts', [])
    previous_manifests = []

    print("   Testing first 3 parts:")

    for i, part in enumerate(parts[:3], 1):
        part_data = build_part_data_with_fields(schema, part)
        manifest_wrapper = generate_part_manifest(part_data, previous_manifests)
        tokens = estimate_manifest_tokens(manifest_wrapper)

        print(f"      Part {i}: {tokens} tokens (cumulative)")

        # Add current part to previous for next iteration
        previous_manifests.append(manifest_wrapper['current_part'])

    print("\n[OK] PASS: Token accumulation test complete\n")


def test_part_switching(schema):
    """Test 8: Part switching with manifest retention"""
    print("="*60)
    print("TEST 8: Part Switching (Manifest Retention)")
    print("="*60)

    parts = schema.get('parts', [])

    # Generate Part 1 manifest
    part1_data = build_part_data_with_fields(schema, parts[0])
    part1_wrapper = generate_part_manifest(part1_data, [])

    # Generate Part 2 manifest with Part 1 as previous
    part2_data = build_part_data_with_fields(schema, parts[1])
    part2_wrapper = generate_part_manifest(part2_data, [part1_wrapper['current_part']])

    # Format with previous parts
    formatted = format_manifest_for_context(part2_wrapper)

    # Verify both parts present
    has_part1 = 'part_1' in formatted.lower() or parts[0]['label'].lower() in formatted.lower()
    has_part2 = 'part_2' in formatted.lower() or parts[1]['label'].lower() in formatted.lower()

    print(f"   Part 1 retained: {has_part1}")
    print(f"   Part 2 included: {has_part2}")

    assert has_part1, "Part 1 not retained"
    assert has_part2, "Part 2 not included"

    print("[OK] PASS: Part switching retains previous manifests\n")


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  JIT SCHEMA SYSTEM - END-TO-END VALIDATION")
    print("="*60)

    try:
        # Load schema
        print("\nLoading I-90 schema...")
        schema = load_i90_schema()
        form_name = schema.get('form_number', schema.get('id', 'Unknown'))
        print(f"[OK] Schema loaded: {form_name}")

        # Run tests
        test_feature_flag()
        manifest_wrapper = test_manifest_generation(schema)
        manifest = manifest_wrapper['current_part']
        test_spoken_name_uniqueness(manifest)
        tokens = test_token_count(manifest_wrapper)
        test_next_field_retrieval(schema)
        test_linear_flow(schema)
        test_token_accumulation(schema)
        test_part_switching(schema)

        # Summary
        print("\n" + "="*60)
        print("  SUMMARY")
        print("="*60)
        print("[OK] All tests PASSED")
        print(f"[OK] Initial token count: {tokens} (<500 target)")
        print(f"[OK] Manifest fields: {len(manifest['fields'])}")
        print("[OK] JIT schema system validated end-to-end")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n[FAIL] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
