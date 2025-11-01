#!/usr/bin/env python3
"""
Fix Schema Issues

Automatically fixes common schema issues found by validator:
1. Add JavaScript unlock instructions
2. Fix trigger field ID mismatches
3. Clean up incomplete conditionals
"""

import json
import sys
from typing import Dict, List


def add_javascript_unlock_instructions(schema: Dict) -> int:
    """
    Add JavaScript unlock instructions to all fields with flip_readonly_bit.

    Converts Python bit manipulation to JavaScript property setting.
    """
    fixed_count = 0

    for field in schema['fields']:
        cond = field.get('conditional_logic') or field.get('help', {}).get('conditional_logic')

        if cond and isinstance(cond, dict):
            unlock_method = cond.get('unlock_method')

            if unlock_method == 'flip_readonly_bit':
                # Check if it already has unlock_instructions
                unlock_instructions = cond.get('unlock_instructions', {})

                if 'javascript' not in unlock_instructions:
                    # Add JavaScript instructions
                    pdf_flag_change = cond.get('pdf_field_flag_change', {})

                    unlock_instructions['python'] = {
                        'field_flags_bit': pdf_flag_change.get('bit', 0),
                        'target_value': pdf_flag_change.get('required_value', 0)
                    }

                    unlock_instructions['javascript'] = {
                        'property': 'readOnly',
                        'value': False  # Unlock means readOnly = false
                    }

                    cond['unlock_instructions'] = unlock_instructions
                    fixed_count += 1

    return fixed_count


def fix_trigger_field_mismatches(schema: Dict) -> Dict:
    """
    Fix known trigger field ID mismatches.

    Returns dict of fixes applied: {old_id: new_id}
    """
    fields_by_id = {f['id']: f for f in schema['fields']}
    fixes = {}

    for field in schema['fields']:
        cond = field.get('conditional_logic') or field.get('help', {}).get('conditional_logic')

        if cond and isinstance(cond, dict):
            trigger_field = cond.get('trigger_field')

            if trigger_field and trigger_field not in fields_by_id:
                # Known mismatch: p2_checkbox2[11] should be p2_checkbox2[5]
                if trigger_field == 'p2_checkbox2[11]':
                    # Search for actual p2_checkbox2 fields
                    candidates = [f for f in schema['fields'] if 'checkbox2' in f['id'] and 'p2' in f['id']]

                    if candidates:
                        # Use the first match (likely p2_checkbox2[5])
                        new_trigger = candidates[0]['id']
                        cond['trigger_field'] = new_trigger
                        fixes[trigger_field] = new_trigger

                # Add more mismatch patterns as discovered
                # ...

    return fixes


def remove_simple_readonly_conditionals(schema: Dict) -> int:
    """
    Remove conditional_logic from fields that are just "Read only" with no logic.

    These aren't actually conditional - they're permanently read-only.
    """
    removed_count = 0

    for field in schema['fields']:
        # Check both locations
        for location in ['conditional_logic', ('help', 'conditional_logic')]:
            if isinstance(location, tuple):
                if 'help' not in field:
                    continue
                cond = field['help'].get(location[1])
                parent = field['help']
                key = location[1]
            else:
                cond = field.get(location)
                parent = field
                key = location

            if cond and isinstance(cond, dict):
                if cond.get('type') == 'simple_readonly':
                    # Remove this conditional - it's not actually conditional
                    del parent[key]
                    removed_count += 1

    return removed_count


def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_schema_issues.py <schema.json> [output.json]")
        sys.exit(1)

    schema_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else schema_path.replace('.json', '_fixed.json')

    # Load schema
    print("Loading schema...")
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    print("\nApplying automatic fixes...\n")

    # Fix 1: Add JavaScript unlock instructions
    print("[1/3] Adding JavaScript unlock instructions...")
    js_fixed = add_javascript_unlock_instructions(schema)
    print(f"  Fixed {js_fixed} fields")

    # Fix 2: Fix trigger field mismatches
    print("\n[2/3] Fixing trigger field ID mismatches...")
    trigger_fixes = fix_trigger_field_mismatches(schema)
    if trigger_fixes:
        print(f"  Fixed {len(trigger_fixes)} trigger field references:")
        for old_id, new_id in trigger_fixes.items():
            print(f"    {old_id} -> {new_id}")
    else:
        print("  No mismatches found")

    # Fix 3: Remove simple readonly conditionals
    print("\n[3/3] Removing simple read-only markers...")
    readonly_removed = remove_simple_readonly_conditionals(schema)
    print(f"  Removed {readonly_removed} non-conditional markers")

    # Save fixed schema
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print("FIXES APPLIED")
    print(f"{'='*70}")
    print(f"Saved to: {output_path}")
    print(f"\nSummary:")
    print(f"  JavaScript unlock instructions added: {js_fixed}")
    print(f"  Trigger field references fixed: {len(trigger_fixes)}")
    print(f"  Simple readonly conditionals removed: {readonly_removed}")

    print(f"\n{'='*70}")
    print("NEXT STEPS")
    print(f"{'='*70}")
    print("1. Run schema_validator.py again to verify fixes")
    print("2. Manually review 20 incomplete conditionals")
    print("3. Add trigger fields for fields missing them")
    print("4. Rebuild conditional index if triggers changed")


if __name__ == "__main__":
    main()
