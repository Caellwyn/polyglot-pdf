#!/usr/bin/env python3
"""
Build Bidirectional Conditional Index

Creates a bidirectional index of conditional relationships:
1. triggers -> dependents: Maps trigger fields to what they control
2. dependents -> triggers: Maps dependent fields to what controls them

Also adds controls_fields metadata to trigger fields.
"""

import json
import sys
from typing import Dict, List, Set, Tuple
from collections import defaultdict


def extract_conditional_relationships(schema: Dict) -> Tuple[Dict, Dict]:
    """
    Extract all conditional relationships from schema.

    Returns:
        (trigger_to_deps, dep_to_triggers)

    trigger_to_deps: {
        "p1_checkbox4": [
            {
                "when_value": true,
                "shows": ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
                "unlocks": ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
                "makes_required": ["p1_line5a_familyname"]
            }
        ]
    }

    dep_to_triggers: {
        "p1_line5a_familyname": [
            {
                "triggered_by": "p1_checkbox4",
                "requires_value": true,
                "action": "unlock"
            }
        ]
    }
    """
    trigger_to_deps = defaultdict(list)
    dep_to_triggers = defaultdict(list)

    for field in schema['fields']:
        field_id = field['id']

        # Get conditional logic (check both locations)
        cond = field.get('conditional_logic')
        if not cond:
            cond = field.get('help', {}).get('conditional_logic')

        if not cond or not isinstance(cond, dict):
            continue

        # Extract trigger field and value
        trigger_field = cond.get('trigger_field')
        trigger_value = cond.get('trigger_value')
        unlock_method = cond.get('unlock_method')
        dependent_fields = cond.get('dependent_fields', [])
        actions = cond.get('actions', {})

        if not trigger_field:
            continue

        # Map dependent -> trigger
        dep_to_triggers[field_id].append({
            'triggered_by': trigger_field,
            'requires_value': trigger_value,
            'unlock_method': unlock_method,
            'action': 'unlock' if unlock_method == 'flip_readonly_bit' else 'show'
        })

        # Map trigger -> dependents
        # Check if this trigger relationship already exists
        existing = None
        for rel in trigger_to_deps[trigger_field]:
            if rel.get('when_value') == trigger_value:
                existing = rel
                break

        if not existing:
            existing = {
                'when_value': trigger_value,
                'shows': [],
                'unlocks': [],
                'makes_required': []
            }
            trigger_to_deps[trigger_field].append(existing)

        # Add to appropriate lists
        if unlock_method == 'flip_readonly_bit':
            if field_id not in existing['unlocks']:
                existing['unlocks'].append(field_id)
        else:
            if field_id not in existing['shows']:
                existing['shows'].append(field_id)

        # Check if field becomes required
        if field.get('required') or actions.get('set_required'):
            if field_id not in existing['makes_required']:
                existing['makes_required'].append(field_id)

        # If there are additional dependent_fields, add them too
        for dep in dependent_fields:
            if dep != field_id:  # Avoid duplicates
                if unlock_method == 'flip_readonly_bit':
                    if dep not in existing['unlocks']:
                        existing['unlocks'].append(dep)
                else:
                    if dep not in existing['shows']:
                        existing['shows'].append(dep)

    return dict(trigger_to_deps), dict(dep_to_triggers)


def add_controls_fields_to_triggers(schema: Dict, trigger_to_deps: Dict) -> int:
    """
    Add controls_fields metadata to trigger fields.

    Returns number of fields updated.
    """
    updated_count = 0

    for field in schema['fields']:
        field_id = field['id']

        if field_id in trigger_to_deps:
            # This field is a trigger - add controls_fields
            field['controls_fields'] = trigger_to_deps[field_id]
            updated_count += 1

    return updated_count


def build_conditional_index(schema: Dict) -> Dict:
    """
    Build complete bidirectional conditional index.

    Adds top-level 'conditional_index' to schema with:
    - triggers: Map of trigger fields to dependents
    - dependents: Map of dependent fields to triggers
    - stats: Statistics about conditionals
    """
    # Extract relationships
    trigger_to_deps, dep_to_triggers = extract_conditional_relationships(schema)

    # Add controls_fields to trigger fields
    triggers_updated = add_controls_fields_to_triggers(schema, trigger_to_deps)

    # Calculate stats
    total_triggers = len(trigger_to_deps)
    total_dependents = len(dep_to_triggers)
    total_relationships = sum(len(deps) for deps in dep_to_triggers.values())

    # Build index
    conditional_index = {
        'triggers': trigger_to_deps,
        'dependents': dep_to_triggers,
        'stats': {
            'total_trigger_fields': total_triggers,
            'total_dependent_fields': total_dependents,
            'total_conditional_relationships': total_relationships,
            'trigger_fields_updated': triggers_updated
        }
    }

    # Add to schema
    schema['conditional_index'] = conditional_index

    return schema


def main():
    if len(sys.argv) < 2:
        print("Usage: python build_conditional_index.py <schema.json> [output.json]")
        sys.exit(1)

    schema_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else schema_path.replace('.json', '_with_index.json')

    # Load schema
    print("Loading schema...")
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    # Build index
    print("\nBuilding conditional index...")
    schema = build_conditional_index(schema)

    # Save
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    # Print results
    index = schema['conditional_index']
    stats = index['stats']

    print(f"\n{'='*70}")
    print("CONDITIONAL INDEX BUILD COMPLETE")
    print(f"{'='*70}")
    print(f"Saved to: {output_path}")
    print(f"\nStatistics:")
    print(f"  Trigger fields: {stats['total_trigger_fields']}")
    print(f"  Dependent fields: {stats['total_dependent_fields']}")
    print(f"  Total relationships: {stats['total_conditional_relationships']}")
    print(f"  Trigger fields updated: {stats['trigger_fields_updated']}")

    # Show sample triggers
    print(f"\nSample trigger relationships:")
    for trigger_id, relationships in list(index['triggers'].items())[:3]:
        print(f"\n  {trigger_id}:")
        for rel in relationships:
            print(f"    When value = {rel['when_value']}:")
            if rel['unlocks']:
                print(f"      Unlocks: {rel['unlocks'][:3]}")
            if rel['shows']:
                print(f"      Shows: {rel['shows'][:3]}")
            if rel['makes_required']:
                print(f"      Makes required: {rel['makes_required'][:3]}")

    print(f"\n{'='*70}")
    print("NEXT STEPS")
    print(f"{'='*70}")
    print("1. Run schema validator to check for issues")
    print("2. Fix any trigger field ID mismatches")
    print("3. Add JavaScript unlock instructions")
    print("4. Test with voice AI and PDF viewer")


if __name__ == "__main__":
    main()
