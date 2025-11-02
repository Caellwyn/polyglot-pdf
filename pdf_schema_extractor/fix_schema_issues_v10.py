#!/usr/bin/env python3
"""
Fix I-90 Schema Issues v10

Systematically fixes identified issues:
1. Remove incorrect comb:true flags (only keep for A-Number, SSN, Account)
2. Add MM/DD/YYYY validation to date fields
3. Fix P2_checkbox1 complex OR dependencies
4. Consolidate p2_checkbox3[0-4] into single field
5. Fix p4_checkbox1[1] unlock logic
6. Fix unit type checkboxes unlock apt/ste/flr fields
7. Consolidate p7_checkbox7extend into radio field
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any


def load_schema(path: Path) -> Dict:
    """Load schema from file"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_schema(schema: Dict, path: Path):
    """Save schema to file"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)


# ============================================================================
# Issue 1: Fix comb:true flags
# ============================================================================

def fix_comb_flags(schema: Dict) -> int:
    """
    Remove comb:true from most fields. Only keep for:
    - Alien Number ([0] and [1])
    - SSN
    - Online Account Number
    """
    print("\n[1/7] Fixing comb:true flags...")

    # Fields that SHOULD have comb
    comb_fields = {
        'p1_line1_aliennumber',
        'p1_line1_aliennumber[1]',
        'p1_line16_ssn',
        'p1_line2_acctidentifier'
    }

    fixes = 0
    for field in schema['fields']:
        field_id = field.get('id')
        is_comb = field.get('is_comb', False)

        if is_comb and field_id not in comb_fields:
            # Remove comb flag
            field['is_comb'] = False
            fixes += 1
        elif not is_comb and field_id in comb_fields:
            # Add comb flag
            field['is_comb'] = True
            fixes += 1

    print(f"  Fixed {fixes} comb flags")
    print(f"  COMB fields: {', '.join(sorted(comb_fields))}")
    return fixes


# ============================================================================
# Issue 2: Add MM/DD/YYYY validation to date fields
# ============================================================================

def fix_date_validation(schema: Dict) -> int:
    """Add MM/DD/YYYY validation to all date fields"""
    print("\n[2/7] Adding MM/DD/YYYY validation to date fields...")

    fixes = 0
    for field in schema['fields']:
        if field.get('type') == 'date':
            # Ensure validation exists
            if not field.get('validation') or field.get('validation') is None:
                field['validation'] = {}

            # Add pattern and hint (don't use format_preset for dates)
            if not field['validation'].get('pattern'):
                field['validation']['pattern'] = r'^\d{2}/\d{2}/\d{4}$'
                field['validation']['hint'] = 'MM/DD/YYYY'
                fixes += 1

    print(f"  Fixed {fixes} date fields")
    return fixes


# ============================================================================
# Issue 3: Fix P2_checkbox1 complex OR dependencies
# ============================================================================

def fix_p2_checkbox1_dependencies(schema: Dict) -> int:
    """
    P2_checkbox1[0] OR P2_checkbox1[1] unlock p2_checkbox2[5] consolidated fields
    P2_checkbox1[2] unlocks p2_checkbox3 consolidated fields
    """
    print("\n[3/7] Fixing P2_checkbox1 complex OR dependencies...")

    fixes = 0

    # Find the fields
    checkbox1_0 = None
    checkbox1_1 = None
    checkbox1_2 = None
    checkbox2_5 = None
    checkbox3 = None

    for field in schema['fields']:
        fid = field.get('id')
        if fid == 'p2_checkbox1':
            # This is the radio group with options [0], [1], [2]
            options = field.get('options', [])
            # Need to set controls_fields for each option value

            # Option [0] and [1] unlock checkbox2[5]
            # Option [2] unlocks checkbox3

            # Clear existing controls
            field['controls_fields'] = [
                {
                    "operator": "equals",
                    "value": "P2_checkbox1[0]",  # First option value
                    "unlocks": ["p2_checkbox2[5]"]
                },
                {
                    "operator": "equals",
                    "value": "P2_checkbox1[1]",  # Second option value
                    "unlocks": ["p2_checkbox2[5]"]
                },
                {
                    "operator": "equals",
                    "value": "P2_checkbox1[2]",  # Third option value
                    "unlocks": ["p2_checkbox3"]
                }
            ]
            fixes += 1

        elif fid == 'p2_checkbox2[5]':
            # Set show_if with OR logic (multiple possible triggers)
            # For now, use first trigger (we'll handle OR in evaluator)
            if not field.get('show_if'):
                field['show_if'] = {
                    "field": "p2_checkbox1",
                    "operator": "in",
                    "value": ["P2_checkbox1[0]", "P2_checkbox1[1]"]
                }
                fixes += 1

        elif fid == 'p2_checkbox3':
            # Set show_if for checkbox1[2]
            if not field.get('show_if'):
                field['show_if'] = {
                    "field": "p2_checkbox1",
                    "operator": "equals",
                    "value": "P2_checkbox1[2]"
                }
                fixes += 1

    print(f"  Fixed {fixes} P2_checkbox1 dependencies")
    return fixes


# ============================================================================
# Issue 4: Consolidate p2_checkbox3[0-4] into single field
# ============================================================================

def consolidate_p2_checkbox3(schema: Dict) -> int:
    """Consolidate P2_checkbox3[0-4] into single checkbox field"""
    print("\n[4/7] Consolidating p2_checkbox3[0-4]...")

    # Find if we have multiple p2_checkbox3[X] fields
    checkbox3_fields = []
    for i, field in enumerate(schema['fields']):
        fid = field.get('id')
        if fid and fid.startswith('p2_checkbox3') and fid != 'p2_checkbox3':
            checkbox3_fields.append((i, field))

    if not checkbox3_fields:
        print("  p2_checkbox3 already consolidated or not found")
        return 0

    # Find the main p2_checkbox3 field
    main_field = None
    main_idx = None
    for i, field in enumerate(schema['fields']):
        if field.get('id') == 'p2_checkbox3':
            main_field = field
            main_idx = i
            break

    if not main_field:
        # Create it
        main_field = {
            "id": "p2_checkbox3",
            "name": "Reason for Application (Select all that apply)",
            "spoken_name": "reason for application",
            "type": "checkbox",
            "section_id": "Part 2 - Application Type",
            "consolidated_widgets": [f"P2_checkbox3[{i}]" for i in range(5)],
            "options": [
                {"value": "P2_checkbox3[0]", "label": "My card has been lost, stolen, or destroyed"},
                {"value": "P2_checkbox3[1]", "label": "My previous card was issued but never received"},
                {"value": "P2_checkbox3[2]", "label": "My existing card has been mutilated"},
                {"value": "P2_checkbox3[3]", "label": "My existing card has incorrect data"},
                {"value": "P2_checkbox3[4]", "label": "My name or other biographic information has changed"}
            ],
            "help": {
                "instructions": "Select all reasons that apply for your card replacement."
            },
            "show_if": {
                "field": "p2_checkbox1",
                "operator": "equals",
                "value": "P2_checkbox1[2]"
            }
        }
        schema['fields'].insert(0, main_field)
        main_idx = 0

    # Remove individual checkbox3 fields
    schema['fields'] = [f for f in schema['fields']
                       if not (f.get('id', '').startswith('p2_checkbox3') and f.get('id') != 'p2_checkbox3')]

    print(f"  Consolidated {len(checkbox3_fields)} fields into p2_checkbox3")
    return len(checkbox3_fields)


# ============================================================================
# Issue 5: Fix p4_checkbox1[1] unlock logic
# ============================================================================

def fix_p4_checkbox1_unlocks(schema: Dict) -> int:
    """P4_checkbox1[1] should unlock p4_checkbox1a, p4_checkbox1b, p4_checkbox1c"""
    print("\n[5/7] Fixing p4_checkbox1[1] unlock logic...")

    fixes = 0

    for field in schema['fields']:
        fid = field.get('id')

        if fid == 'p4_checkbox1[1]':
            # Set controls_fields
            field['controls_fields'] = [{
                "operator": "is_checked",
                "value": True,
                "unlocks": ["p4_checkbox1a", "p4_checkbox1b", "p4_checkbox1c"]
            }]
            fixes += 1

        elif fid in ['p4_checkbox1a', 'p4_checkbox1b', 'p4_checkbox1c']:
            # Set show_if
            field['show_if'] = {
                "field": "p4_checkbox1[1]",
                "operator": "is_checked",
                "value": True
            }
            field['read_only'] = True
            fixes += 1

    print(f"  Fixed {fixes} p4_checkbox1 unlock relationships")
    return fixes


# ============================================================================
# Issue 6: Fix unit type checkboxes unlock apt/ste/flr fields
# ============================================================================

def fix_unit_type_unlocks(schema: Dict) -> int:
    """Any unit type checkbox unlocks the corresponding apt/ste/flr field"""
    print("\n[6/7] Fixing unit type checkbox unlocks...")

    # Unit type mapping: unit_field -> apt_field
    unit_mappings = {
        'p1_unit_type6c_unit': 'p1_line6c_aptsteflrnumber',  # Mailing address
        'p1_unit_type7b_unit': 'p1_line7b_aptsteflrnumber',  # Physical address
        'p6_unit_type3b_unit': 'p6_line3b_aptsteflrnumber',  # Interpreter address
        'p7_unit_type3b_unit': 'p7_line3b_aptsteflrnumber',  # Preparer address
    }

    fixes = 0

    for unit_field_id, apt_field_id in unit_mappings.items():
        # Find unit field
        for field in schema['fields']:
            if field.get('id') == unit_field_id:
                # Set controls_fields (any option selected unlocks apt field)
                field['controls_fields'] = [{
                    "operator": "not_equals",
                    "value": "",  # Any value selected (not empty string)
                    "unlocks": [apt_field_id]
                }]
                fixes += 1
                break

        # Find apt field
        for field in schema['fields']:
            if field.get('id') == apt_field_id:
                # Set show_if
                field['show_if'] = {
                    "field": unit_field_id,
                    "operator": "not_equals",
                    "value": ""  # Unit type is selected (not empty)
                }
                field['read_only'] = True
                fixes += 1
                break

    print(f"  Fixed {fixes} unit type unlock relationships")
    return fixes


# ============================================================================
# Issue 7: Consolidate p7_checkbox7extend into radio field
# ============================================================================

def consolidate_p7_checkbox7extend(schema: Dict) -> int:
    """Consolidate p7_checkbox7extend and p7_checkbox7extend[1] into radio"""
    print("\n[7/7] Consolidating p7_checkbox7extend into radio...")

    # Find existing fields
    extend_field = None
    extend1_field = None

    for i, field in enumerate(schema['fields']):
        fid = field.get('id')
        if fid == 'p7_checkbox7extend':
            extend_field = (i, field)
        elif fid == 'p7_checkbox7extend[1]':
            extend1_field = (i, field)

    if not extend_field:
        print("  p7_checkbox7extend not found")
        return 0

    # Update main field to radio
    idx, field = extend_field
    field['type'] = 'radio'
    field['consolidated_widgets'] = ['P7_checkbox7Extend[0]', 'P7_checkbox7Extend[1]']
    field['options'] = [
        {"value": "P7_checkbox7Extend[0]", "label": "Yes"},
        {"value": "P7_checkbox7Extend[1]", "label": "No"}
    ]

    # Remove the [1] field
    if extend1_field:
        schema['fields'] = [f for f in schema['fields'] if f.get('id') != 'p7_checkbox7extend[1]']
        print("  Consolidated 2 fields into radio")
        return 2
    else:
        print("  Updated field to radio")
        return 1


# ============================================================================
# Main
# ============================================================================

def main(input_path: str, output_path: str):
    """Main execution"""
    print("="*70)
    print("I-90 Schema Issue Fixes v10")
    print("="*70)

    # Load schema
    print(f"\nLoading: {input_path}")
    schema = load_schema(Path(input_path))
    print(f"  {len(schema['fields'])} fields")

    # Apply all fixes
    total_fixes = 0
    total_fixes += fix_comb_flags(schema)
    total_fixes += fix_date_validation(schema)
    total_fixes += fix_p2_checkbox1_dependencies(schema)
    total_fixes += consolidate_p2_checkbox3(schema)
    total_fixes += fix_p4_checkbox1_unlocks(schema)
    total_fixes += fix_unit_type_unlocks(schema)
    total_fixes += consolidate_p7_checkbox7extend(schema)

    # Save
    print(f"\n{'='*70}")
    print(f"TOTAL FIXES: {total_fixes}")
    print(f"{'='*70}")

    print(f"\nSaving: {output_path}")
    save_schema(schema, Path(output_path))
    print(f"  {len(schema['fields'])} fields")

    print("\nDone!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_schema_issues_v10.py <input_schema> [output_schema]")
        print("\nExample:")
        print("  python fix_schema_issues_v10.py \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v10_ordered.json \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v11_fixed.json")
        sys.exit(1)

    input_schema = sys.argv[1]
    output_schema = sys.argv[2] if len(sys.argv) > 2 else input_schema.replace('.json', '_fixed.json')

    main(input_schema, output_schema)
