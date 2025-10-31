#!/usr/bin/env python3
"""
I-90 Schema Validation Fixer - Addresses issues found in manual PDF review.

Fixes:
1. Field type corrections (checkbox → radio for mutually exclusive fields)
2. Consolidate separate checkboxes into radio groups (Apt/Ste/Flr)
3. Add validation rules (phone, date, zip code formats)
4. Convert text to date fields
5. Add format hints for voice AI
"""

import json
import sys
from typing import Dict, List, Any


# Field type corrections: checkbox → radio
CHECKBOX_TO_RADIO_PATTERNS = [
    # Part 1
    ('p1_checkbox6c_unit', 'Apartment/Suite/Floor selector'),
    ('p1_checkbox7b_unit', 'Physical address Apt/Ste/Flr selector'),

    # Part 3 - Yes/No questions (mutually exclusive)
    ('p3.*q3', 'Part 3 Q3 Yes/No'),
    ('p3.*q5', 'Part 3 Q5 Yes/No'),
    ('p3.*q6', 'Part 3 Q6 Yes/No'),
    ('p3.*q7', 'Part 3 Q7 Yes/No'),
    ('p3.*q10', 'Part 3 Q10 Yes/No'),
    ('p3.*q11', 'Part 3 Q11 Yes/No'),

    # Part 4
    ('p4.*q1', 'Part 4 Q1 accommodation type'),

    # Part 6
    ('p6_checkbox3b_unit', 'Part 6 Apt/Ste/Flr'),

    # Part 7
    ('p7_checkbox3b_unit', 'Part 7 Apt/Ste/Flr'),
]

# Text → Date conversions
TEXT_TO_DATE_FIELDS = [
    'p1_line9_dateofbirth',
    'p1_line15_dateofadmission',
    'p7_line8b_datesigned',  # Part 7 Q8b
]

# Validation rules
VALIDATION_RULES = {
    # Phone numbers (10 digits)
    'phone_number': {
        'pattern': r'^\d{10}$',
        'format_hint': '10 digits (XXX-XXX-XXXX)',
        'field_patterns': [
            'p5_line3_daytimephonenumber',
            'p5_line4_mobilephonenumber',
            'p5_line5_eveningphonenumber',  # if exists
            'p6_line4_interpretersdaytimephonenumber',
            'p6_line5',  # interpreter mobile
            'p6_line6',  # interpreter fax/evening
            'p7_line4_preparersdaytimephonenumber',
            'p7_line5_preparersfaxnumber',  # actually mobile based on earlier finding
            'p7_line6',  # preparer fax/evening
        ]
    },

    # ZIP codes (5 digits)
    'zip_code': {
        'pattern': r'^\d{5}$',
        'format_hint': '5 digits',
        'field_patterns': [
            'p1_line6f_zipcode',
            'p1_line7e_zipcode',
            'p7_line3e',  # Part 7 Q3e
        ]
    },

    # Postal codes (varies by country)
    'postal_code': {
        'pattern': r'^[A-Z0-9]{3,10}$',
        'format_hint': 'Alphanumeric postal code',
        'field_patterns': [
            'p1_line6h_postalcode',
            'p1_line7g_postalcode',
            'p6_line3g',  # Part 6 Q3g
            'p7_line3g',  # Part 7 Q3g
        ]
    },

    # Receipt/Case number (12 digits)
    'receipt_number': {
        'pattern': r'^\d{12}$',
        'format_hint': '12 digits',
        'field_patterns': [
            'p2_line2',  # Part 2 Q2
        ]
    },

    # Date fields (MM/DD/YYYY)
    'date': {
        'pattern': r'^\d{2}/\d{2}/\d{4}$',
        'format_hint': 'MM/DD/YYYY',
        'field_patterns': TEXT_TO_DATE_FIELDS
    },

    # Social Security Number (9 digits)
    'ssn': {
        'pattern': r'^\d{9}$',
        'format_hint': '9 digits (XXX-XX-XXXX)',
        'field_patterns': [
            'p1_line16_ssn',
        ]
    },

    # A-Number (7-9 digits)
    'a_number': {
        'pattern': r'^\d{7,9}$',
        'format_hint': '7-9 digits',
        'field_patterns': [
            'p1_line1_aliennumber',
        ]
    },
}


def match_pattern(field_id: str, patterns: List[str]) -> bool:
    """Check if field_id matches any of the patterns."""
    import re
    for pattern in patterns:
        if re.search(pattern, field_id, re.IGNORECASE):
            return True
    return False


def consolidate_unit_checkboxes(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Consolidate separate Apt/Ste/Flr checkboxes into single radio groups.

    Example:
      p1_checkbox6c_unit[0] (Apartment)
      p1_checkbox6c_unit[1] (Suite)
      p1_checkbox6c_unit[2] (Floor)

    Should become:
      p1_unit_type (radio group with 3 options)
    """
    print("\n[CONSOLIDATION] Merging Apt/Ste/Flr checkbox groups...")

    # Group fields by base name
    unit_groups = {}
    fields_to_remove = []

    for i, field in enumerate(schema['fields']):
        field_id = field.get('id', '')

        # Look for checkbox unit patterns
        if 'checkbox' in field_id and 'unit' in field_id:
            # Extract base (e.g., "p1_checkbox6c_unit")
            base = field_id.split('[')[0] if '[' in field_id else field_id

            if base not in unit_groups:
                unit_groups[base] = []

            unit_groups[base].append((i, field))

    # Create consolidated radio groups
    new_fields = []
    for base, fields in unit_groups.items():
        if len(fields) >= 2:  # Only consolidate if there are multiple options
            print(f"  Consolidating {len(fields)} fields: {base}")

            # Create new radio group field
            first_field = fields[0][1]
            section = first_field.get('section', '')

            # Extract part/question from base (e.g., "p1_checkbox6c_unit" → "Part 1 Q6c")
            part_match = base.split('_')[0]  # e.g., "p1"

            new_field = {
                'id': base.replace('checkbox', 'unit_type'),
                'name': 'Select Unit Type',
                'type': 'radio',
                'section': section,
                'consolidated_widgets': [],
                'options': []
            }

            # Add all options
            for idx, field in fields:
                option_label = field.get('name', 'Option')
                option_label = option_label.replace('Select ', '')

                consolidated_widgets = field.get('consolidated_widgets', [])
                if consolidated_widgets:
                    new_field['consolidated_widgets'].extend(consolidated_widgets)

                pdf_field = field.get('pdf_field_name', '')
                if pdf_field:
                    new_field['options'].append({
                        'value': pdf_field,
                        'label': option_label,
                        'pdf_field_name': pdf_field
                    })

                # Mark for removal
                fields_to_remove.append(idx)

            new_fields.append(new_field)

    # Remove old fields and add new consolidated fields
    fields_to_remove.sort(reverse=True)
    for idx in fields_to_remove:
        del schema['fields'][idx]

    # Add new consolidated fields
    schema['fields'].extend(new_fields)

    print(f"  Created {len(new_fields)} consolidated radio groups")
    print(f"  Removed {len(fields_to_remove)} individual checkbox fields")

    return schema


def fix_field_types(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Fix field type mismatches."""
    print("\n[FIELD TYPES] Fixing type mismatches...")

    changes = {
        'checkbox_to_radio': 0,
        'text_to_date': 0,
    }

    for field in schema['fields']:
        field_id = field.get('id', '')
        current_type = field.get('type', '')

        # Convert checkboxes to radio
        for pattern, desc in CHECKBOX_TO_RADIO_PATTERNS:
            if match_pattern(field_id, [pattern]):
                if current_type == 'checkbox':
                    field['type'] = 'radio'
                    changes['checkbox_to_radio'] += 1
                    print(f"  {field_id}: checkbox -> radio ({desc})")
                break

        # Convert text to date
        if field_id in TEXT_TO_DATE_FIELDS:
            if current_type == 'text':
                field['type'] = 'date'
                changes['text_to_date'] += 1
                print(f"  {field_id}: text -> date")

    print(f"\n  Summary:")
    print(f"    Checkbox -> Radio: {changes['checkbox_to_radio']}")
    print(f"    Text -> Date: {changes['text_to_date']}")

    return schema


def add_validation_rules(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Add validation rules and format hints."""
    print("\n[VALIDATION] Adding validation rules...")

    rules_added = 0

    for field in schema['fields']:
        field_id = field.get('id', '')

        # Check each validation rule type
        for rule_type, rule_config in VALIDATION_RULES.items():
            if match_pattern(field_id, rule_config['field_patterns']):
                # Add validation
                if 'validation' not in field:
                    field['validation'] = {}

                field['validation']['pattern'] = rule_config['pattern']
                field['validation']['type'] = rule_type

                # Add format hint to help section
                if 'help' not in field:
                    field['help'] = {}

                field['help']['format_hint'] = rule_config['format_hint']

                rules_added += 1
                print(f"  {field_id}: {rule_type} validation added")
                break

    print(f"\n  Added validation to {rules_added} fields")

    return schema


def add_conditional_logic_placeholders(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Add placeholders for known conditional logic (to be filled by Gemini)."""
    print("\n[CONDITIONAL LOGIC] Adding placeholders...")

    # Known conditionals from manual review
    conditionals = [
        {
            'field_pattern': 'p1.*checkbox4',  # P1 Q4 (name change)
            'condition': 'NEEDS_GEMINI: If this is YES, show P1 Q5a, Q5b, Q5c',
            'description': 'Name change conditional'
        },
        {
            'field_pattern': 'p2.*line2',  # P2 Q2 (receipt number)
            'condition': 'NEEDS_GEMINI: Unlocked by P2 Q1a selection. Complex conditional tree - see i-90instr.pdf',
            'description': 'Receipt number conditional'
        },
    ]

    added = 0
    for field in schema['fields']:
        field_id = field.get('id', '')

        for cond in conditionals:
            if match_pattern(field_id, [cond['field_pattern']]):
                if 'help' not in field:
                    field['help'] = {}

                field['help']['conditional_logic'] = cond['condition']
                added += 1
                print(f"  {field_id}: {cond['description']}")
                break

    print(f"\n  Added {added} conditional logic placeholders")

    return schema


def fix_schema(schema_file: str, output_file: str):
    """Apply all fixes to schema."""
    print("="*70)
    print("I-90 SCHEMA VALIDATION FIXER")
    print("="*70)

    # Load schema
    print("\n[1/5] Loading schema...")
    with open(schema_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    print(f"  Loaded {len(schema['fields'])} fields")

    # Apply fixes
    schema = consolidate_unit_checkboxes(schema)
    schema = fix_field_types(schema)
    schema = add_validation_rules(schema)
    schema = add_conditional_logic_placeholders(schema)

    # Save
    print("\n[5/5] Saving fixed schema...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print("\n" + "="*70)
    print("SCHEMA FIXING COMPLETE")
    print("="*70)
    print(f"Saved to: {output_file}")
    print("\nNext steps:")
    print("  1. Run round-trip test on fixed schema")
    print("  2. Use Gemini with i-90instr.pdf for conditional logic")
    print("  3. Manual review of filled PDF")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python fix_i90_schema_validation.py <schema_json> <output_json>")
        sys.exit(1)

    schema_file = sys.argv[1]
    output_file = sys.argv[2]

    fix_schema(schema_file, output_file)
