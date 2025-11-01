#!/usr/bin/env python3
"""
Apply Dependencies - Apply Gemini-extracted dependencies to schema bidirectionally.

Updates schema with both show_if (triggered by) and conditional_fields (triggers).
"""

import json
import sys
from typing import Dict, List


def apply_dependencies_to_schema(schema: Dict, dependencies: Dict, min_confidence: str = "medium") -> Dict:
    """
    Apply bidirectional dependencies to schema.

    Args:
        schema: Original schema dict
        dependencies: Dependencies from Gemini (with show_if and conditional_fields)
        min_confidence: Minimum confidence level to apply ("high", "medium", "low")

    Returns:
        Updated schema with dependencies applied
    """
    # Confidence ranking
    confidence_rank = {"high": 3, "medium": 2, "low": 1}
    min_rank = confidence_rank.get(min_confidence, 2)

    # Index fields by ID
    fields_by_id = {f['id']: f for f in schema.get('fields', [])}

    stats = {
        'total_dependencies': len(dependencies.get('fields', [])),
        'show_if_applied': 0,
        'conditional_fields_applied': 0,
        'needs_unlock_flagged': 0,
        'skipped_low_confidence': 0,
        'errors': []
    }

    print(f"\nApplying dependencies (min confidence: {min_confidence})...")

    for dep in dependencies.get('fields', []):
        field_id = dep.get('field_id')
        confidence = dep.get('confidence', 'low')

        # Skip low confidence if threshold not met
        if confidence_rank.get(confidence, 0) < min_rank:
            stats['skipped_low_confidence'] += 1
            continue

        # Find field in schema
        field = fields_by_id.get(field_id)
        if not field:
            stats['errors'].append(f"Field {field_id} not found in schema")
            continue

        # Apply show_if (this field is triggered by another)
        show_if = dep.get('show_if')
        if show_if:
            # Validate trigger field exists
            trigger_field = show_if.get('field')
            if trigger_field not in fields_by_id:
                stats['errors'].append(f"Trigger field {trigger_field} not found for {field_id}")
                continue

            # Convert value to proper type
            value = show_if.get('value')
            if value == 'true':
                value = True
            elif value == 'false':
                value = False

            # Create ConditionalDisplay structure
            field['show_if'] = {
                'field': trigger_field,
                'operator': show_if.get('operator'),
                'value': value
            }

            stats['show_if_applied'] += 1

        # Apply conditional_fields (this field triggers others)
        conditional_fields = dep.get('conditional_fields')
        if conditional_fields:
            # Validate all dependent fields exist
            valid_deps = []
            for dep_id in conditional_fields:
                if dep_id in fields_by_id:
                    valid_deps.append(dep_id)
                else:
                    stats['errors'].append(f"Dependent field {dep_id} not found")

            if valid_deps:
                # Merge with existing conditional_fields if present
                existing = field.get('conditional_fields', [])
                # Combine and deduplicate
                merged = list(set(existing + valid_deps))
                field['conditional_fields'] = merged
                stats['conditional_fields_applied'] += 1

        # Flag fields needing unlock
        if dep.get('needs_unlock'):
            # If field doesn't already have unlock_method, add it
            if 'conditional_logic' not in field:
                field['conditional_logic'] = {}

            if isinstance(field['conditional_logic'], dict):
                field['conditional_logic']['unlock_method'] = 'flip_readonly_bit'
                field['conditional_logic']['pdf_field_flag_change'] = {
                    'bit': 0,
                    'current_value': 1,
                    'required_value': 0
                }
                stats['needs_unlock_flagged'] += 1

    return schema, stats


def main():
    if len(sys.argv) < 3:
        print("Usage: python apply_dependencies.py <schema.json> <dependencies.json> [output.json] [--min-confidence=medium]")
        print("\nOptions:")
        print("  --min-confidence  Minimum confidence level: high, medium, low (default: medium)")
        print("\nExample:")
        print("  python apply_dependencies.py \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v7_final.json \\")
        print("    test_schemas/test_pdfs/i-90/i-90_dependencies.json \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v8_with_deps.json")
        sys.exit(1)

    schema_path = sys.argv[1]
    deps_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else schema_path.replace('.json', '_with_deps.json')

    # Parse min-confidence
    min_confidence = "medium"
    for arg in sys.argv:
        if arg.startswith('--min-confidence='):
            min_confidence = arg.split('=')[1]

    # Load schema and dependencies
    print("Loading schema...")
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    print("Loading dependencies...")
    with open(deps_path, 'r', encoding='utf-8') as f:
        dependencies = json.load(f)

    # Apply dependencies
    updated_schema, stats = apply_dependencies_to_schema(schema, dependencies, min_confidence)

    # Save updated schema
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(updated_schema, f, indent=2, ensure_ascii=False)

    # Print results
    print(f"\n{'='*70}")
    print("DEPENDENCIES APPLIED")
    print(f"{'='*70}")
    print(f"Output: {output_path}")
    print(f"\nStatistics:")
    print(f"  Total dependencies processed: {stats['total_dependencies']}")
    print(f"  show_if applied: {stats['show_if_applied']}")
    print(f"  conditional_fields applied: {stats['conditional_fields_applied']}")
    print(f"  needs_unlock flagged: {stats['needs_unlock_flagged']}")
    print(f"  Skipped (low confidence): {stats['skipped_low_confidence']}")

    if stats['errors']:
        print(f"\nErrors ({len(stats['errors'])}):")
        for error in stats['errors'][:10]:
            print(f"  - {error}")
        if len(stats['errors']) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more")

    print(f"\n{'='*70}")
    print("NEXT STEPS")
    print(f"{'='*70}")
    print("1. Run: python build_conditional_index.py (rebuild index)")
    print("2. Run: python schema_validator.py (validate)")
    print("3. Check bidirectional relationships work correctly")


if __name__ == "__main__":
    main()
