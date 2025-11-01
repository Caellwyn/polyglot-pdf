#!/usr/bin/env python3
"""
Apply CSV Dependencies - Convert CSV dependency mapping to structured format and apply to schema.

Reads a CSV file with columns: Field, Unlocks, is unlocked by, copies values to, Is equal to, condition
Converts to proper bidirectional dependencies and applies to schema.
"""

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


def normalize_field_name(pdf_field_name: str) -> str:
    """
    Normalize PDF field name to schema ID format.

    Example: P1_Line1_AlienNumber[0] -> p1_line1_aliennumber
    """
    # Remove array index [0], [1], etc.
    base_name = pdf_field_name.split('[')[0]
    # Convert to lowercase
    return base_name.lower()


def get_option_value(pdf_field_name: str) -> str:
    """
    Get the option value for consolidated fields.

    Example: P1_checkbox4[0] -> P1_checkbox4[0] (keep as-is for option value)
    """
    return pdf_field_name.strip()


def build_widget_to_field_map(schema: Dict) -> Dict[str, str]:
    """
    Build a reverse map from consolidated widget names to parent field IDs.

    Example: 'P1_checkbox6c_Unit[0]' -> 'p1_unit_type6c_unit'
    """
    widget_map = {}
    for field in schema.get('fields', []):
        field_id = field['id']
        consolidated = field.get('consolidated_widgets', [])
        for widget in consolidated:
            widget_map[widget] = field_id
    return widget_map


def parse_csv_dependencies(csv_path: str, schema: Dict) -> Tuple[Dict[str, Dict], Dict[str, List[str]]]:
    """
    Parse CSV dependencies into structured format.

    Args:
        csv_path: Path to CSV file
        schema: Schema dict to look up field structures

    Returns:
        (dependencies_dict, copy_relationships)
        - dependencies_dict: {field_id: {show_if, conditional_fields, needs_unlock}}
        - copy_relationships: {source_field: [target_fields]}
    """
    dependencies = {}  # field_id -> {show_if, conditional_fields, needs_unlock}
    copy_relationships = {}  # source_field -> [target_fields]

    # Index schema fields for lookup
    fields_by_id = {f['id']: f for f in schema.get('fields', [])}

    # Build reverse map from widget names to parent field IDs
    widget_to_field = build_widget_to_field_map(schema)

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            field = row['Field'].strip()
            unlocks = row['Unlocks'].strip()
            unlocked_by = row['is unlocked by'].strip()
            copies_to = row['copies values to'].strip()
            is_equal_to = row['Is equal to'].strip()
            condition = row['condition'].strip()

            # Resolve field names (widget name -> parent field ID)
            field_option_value = get_option_value(field)  # Keep original for option values
            field_id = widget_to_field.get(field_option_value, normalize_field_name(field))

            # Handle "Unlocks" relationships (trigger -> dependent)
            if unlocks:
                unlocks_option_value = get_option_value(unlocks)
                unlocked_id = widget_to_field.get(unlocks_option_value, normalize_field_name(unlocks))

                # Initialize field entry if needed
                if field_id not in dependencies:
                    dependencies[field_id] = {
                        'field_id': field_id,
                        'conditional_fields': [],
                        'confidence': 'high'
                    }

                # Ensure conditional_fields exists (in case field was already initialized without it)
                if 'conditional_fields' not in dependencies[field_id]:
                    dependencies[field_id]['conditional_fields'] = []

                # Add to conditional_fields list
                if unlocked_id not in dependencies[field_id]['conditional_fields']:
                    dependencies[field_id]['conditional_fields'].append(unlocked_id)

                # Initialize unlocked field entry
                if unlocked_id not in dependencies:
                    dependencies[unlocked_id] = {
                        'field_id': unlocked_id,
                        'confidence': 'high'
                    }

                # Determine operator and value from condition and field structure
                trigger_field = fields_by_id.get(field_id)

                if condition == 'When True':
                    # Check if this is a consolidated field with options
                    if trigger_field and trigger_field.get('options'):
                        # For consolidated fields, use equals with the specific option value
                        operator = 'equals'
                        value = field_option_value  # Use the widget name as the value
                    else:
                        # For simple boolean fields
                        operator = 'is_checked'
                        value = True
                elif condition == 'When Not Empty':
                    operator = 'is_not_empty'
                    value = None  # Not used for is_not_empty
                else:
                    # Default
                    operator = 'is_checked'
                    value = True

                # Add show_if to the unlocked field
                dependencies[unlocked_id]['show_if'] = {
                    'field': field_id,
                    'operator': operator,
                    'value': value
                }
                dependencies[unlocked_id]['needs_unlock'] = True

            # Handle "is unlocked by" relationships (dependent -> trigger)
            # This is redundant with "Unlocks" but we process it for validation
            if unlocked_by:
                unlocked_by_option_value = get_option_value(unlocked_by)
                unlocked_by_id = widget_to_field.get(unlocked_by_option_value, normalize_field_name(unlocked_by))

                # Initialize field entry if needed
                if field_id not in dependencies:
                    dependencies[field_id] = {
                        'field_id': field_id,
                        'confidence': 'high'
                    }

                # Determine operator and value from condition and field structure
                unlocked_by_field = fields_by_id.get(unlocked_by_id)

                if condition == 'When True':
                    # Check if this is a consolidated field with options
                    if unlocked_by_field and unlocked_by_field.get('options'):
                        # For consolidated fields, use equals with the specific option value
                        operator = 'equals'
                        value = unlocked_by_option_value
                    else:
                        # For simple boolean fields
                        operator = 'is_checked'
                        value = True
                elif condition == 'When Not Empty':
                    operator = 'is_not_empty'
                    value = None
                else:
                    operator = 'is_checked'
                    value = True

                # Add show_if if not already present
                if 'show_if' not in dependencies[field_id]:
                    dependencies[field_id]['show_if'] = {
                        'field': unlocked_by_id,
                        'operator': operator,
                        'value': value
                    }
                    dependencies[field_id]['needs_unlock'] = True

            # Handle "copies values to" relationships
            if copies_to:
                copies_to_option_value = get_option_value(copies_to)
                source_id = widget_to_field.get(field_option_value, normalize_field_name(field))
                target_id = widget_to_field.get(copies_to_option_value, normalize_field_name(copies_to))

                if source_id not in copy_relationships:
                    copy_relationships[source_id] = []

                if target_id not in copy_relationships[source_id]:
                    copy_relationships[source_id].append(target_id)

            # Handle "Is equal to" relationships (reverse of copies_to)
            if is_equal_to:
                is_equal_to_option_value = get_option_value(is_equal_to)
                source_id = widget_to_field.get(is_equal_to_option_value, normalize_field_name(is_equal_to))
                target_id = widget_to_field.get(field_option_value, normalize_field_name(field))

                if source_id not in copy_relationships:
                    copy_relationships[source_id] = []

                if target_id not in copy_relationships[source_id]:
                    copy_relationships[source_id].append(target_id)

    return dependencies, copy_relationships


def apply_copy_relationships(schema: Dict, copy_relationships: Dict[str, List[str]]) -> int:
    """
    Apply copy relationships to schema fields.

    Adds copy_to metadata to fields that copy values to other fields.

    Returns:
        Number of copy relationships applied
    """
    fields_by_id = {f['id']: f for f in schema.get('fields', [])}
    applied = 0

    for source_id, targets in copy_relationships.items():
        source_field = fields_by_id.get(source_id)
        if not source_field:
            continue

        # Validate all targets exist
        valid_targets = [t for t in targets if t in fields_by_id]

        if valid_targets:
            # Add copy_to metadata
            if 'copy_to' not in source_field:
                source_field['copy_to'] = []

            # Merge and deduplicate
            source_field['copy_to'] = list(set(source_field['copy_to'] + valid_targets))
            applied += 1

            # Mark target fields as read-only copies
            for target_id in valid_targets:
                target_field = fields_by_id[target_id]
                if 'copy_from' not in target_field:
                    target_field['copy_from'] = source_id

    return applied


def main():
    if len(sys.argv) < 3:
        print("Usage: python apply_csv_dependencies.py <schema.json> <dependencies.csv> [output.json]")
        print("\nExample:")
        print("  python apply_csv_dependencies.py \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v7_final.json \\")
        print("    test_schemas/test_pdfs/i-90/i-90_dependencies.csv \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v8_final.json")
        sys.exit(1)

    schema_path = sys.argv[1]
    csv_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else schema_path.replace('.json', '_with_deps.json')

    print(f"\n{'='*70}")
    print("CSV DEPENDENCY APPLICATOR")
    print(f"{'='*70}\n")

    # Load schema
    print(f"Loading schema: {schema_path}")
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    # Parse CSV dependencies
    print(f"Parsing CSV: {csv_path}")
    dependencies, copy_relationships = parse_csv_dependencies(csv_path, schema)

    print(f"\nParsed:")
    print(f"  - {len(dependencies)} fields with dependencies")
    print(f"  - {len(copy_relationships)} copy relationships")

    # Convert to the format expected by apply_dependencies.py
    deps_json = {
        'fields': list(dependencies.values())
    }

    # Apply dependencies using the existing apply_dependencies logic
    from apply_dependencies import apply_dependencies_to_schema

    updated_schema, stats = apply_dependencies_to_schema(schema, deps_json, min_confidence='high')

    # Apply copy relationships
    print("\nApplying copy relationships...")
    copy_count = apply_copy_relationships(updated_schema, copy_relationships)

    # Save updated schema
    print(f"\nSaving updated schema: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(updated_schema, f, indent=2, ensure_ascii=False)

    # Print results
    print(f"\n{'='*70}")
    print("RESULTS")
    print(f"{'='*70}")
    print(f"Output: {output_path}")
    print(f"\nDependencies Applied:")
    print(f"  show_if applied: {stats['show_if_applied']}")
    print(f"  conditional_fields applied: {stats['conditional_fields_applied']}")
    print(f"  needs_unlock flagged: {stats['needs_unlock_flagged']}")
    print(f"\nCopy Relationships:")
    print(f"  copy_to applied: {copy_count}")

    if stats['errors']:
        print(f"\nWarnings/Errors ({len(stats['errors'])}):")
        for error in stats['errors'][:10]:
            print(f"  - {error}")
        if len(stats['errors']) > 10:
            print(f"  ... and {len(stats['errors']) - 10} more")

    print(f"\n{'='*70}")
    print("NEXT STEPS")
    print(f"{'='*70}")
    print("1. Review the updated schema for correctness")
    print("2. Run: python validate_schema.py (validate with Pydantic)")
    print("3. Test conditional logic in voice AI")

    return 0


if __name__ == "__main__":
    sys.exit(main())
