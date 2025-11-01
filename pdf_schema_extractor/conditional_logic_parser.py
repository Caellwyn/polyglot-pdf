#!/usr/bin/env python3
"""
Conditional Logic Parser - Convert string-format conditionals to structured format.

Parses human-readable conditional descriptions and converts them to
machine-readable structured format for runtime evaluation.
"""

import json
import re
from typing import Dict, List, Optional, Tuple


def categorize_conditional(conditional_text: str) -> str:
    """
    Categorize the type of conditional logic.

    Returns:
        - 'pre_populated': Field is copy of another field
        - 'simple_readonly': Just permanently read-only, no logic
        - 'show_if': Conditional visibility/unlocking
        - 'needs_manual': Requires manual parsing
    """
    text = conditional_text.lower()

    if 'pre-populated from' in text or 'pre-populated if' in text:
        return 'pre_populated'

    if text.strip() in ['read only', 'read-only', 'readonly']:
        return 'simple_readonly'

    if 'show only if' in text or 'show if' in text:
        return 'show_if'

    if 'needs_gemini' in text or 'if this is yes' in text:
        return 'needs_manual'

    # Default to needs manual review
    return 'needs_manual'


def parse_pre_populated(conditional_text: str, field_id: str) -> Optional[Dict]:
    """
    Parse pre-populated conditionals.

    Example: "Pre-populated from p1_line1_aliennumber in Part 1, read-only."
    """
    # Extract source field
    match = re.search(r'pre-populated from ([a-z0-9_\[\]]+)', conditional_text.lower())
    if match:
        source_field = match.group(1)
        return {
            'type': 'pre_populated',
            'source_field': source_field,
            'unlock_method': 'voice_ai_only',
            'description': f'Pre-populated from {source_field}, read-only.'
        }

    # Check for "pre-populated if"
    if 'pre-populated if' in conditional_text.lower():
        return {
            'type': 'pre_populated_conditional',
            'unlock_method': 'voice_ai_only',
            'description': conditional_text,
            'note': 'Manual review needed - complex pre-population logic'
        }

    return None


def parse_show_if(conditional_text: str, field_id: str) -> Optional[Dict]:
    """
    Parse "show only if" conditionals.

    Examples:
    - "Show only if you are a conditional permanent resident."
    - "Show only if 'Yes' is selected for requesting accommodations."
    - "Show only if 'Sign language interpreter needed' is checked."
    """
    text = conditional_text

    # Pattern: "Show only if 'X' is selected/checked"
    quote_match = re.search(r"'([^']+)'\s+is\s+(selected|checked)", text, re.IGNORECASE)
    if quote_match:
        trigger_value = quote_match.group(1)

        # Try to infer trigger field from context
        # This is heuristic - may need manual review
        return {
            'type': 'conditional_visibility',
            'trigger_value': trigger_value,
            'unlock_method': 'flip_readonly_bit',
            'description': text,
            'note': 'Trigger field needs manual identification',
            'pdf_field_flag_change': {
                'bit': 0,
                'current_value': 1,
                'required_value': 0
            }
        }

    # Pattern: Generic "show only if" - needs manual parsing
    return {
        'type': 'conditional_visibility',
        'unlock_method': 'voice_ai_only',
        'description': text,
        'note': 'Complex condition - manual review needed'
    }


def parse_needs_manual(conditional_text: str, field_id: str) -> Optional[Dict]:
    """
    Parse NEEDS_GEMINI or other complex conditionals.

    Example: "NEEDS_GEMINI: If this is YES, show P1 Q5a, Q5b, Q5c"
    """
    # Extract dependent fields from text
    dependent_fields = []

    # Look for field patterns like "P1 Q5a"
    field_matches = re.findall(r'P\d+\s+Q\d+[a-c]?', conditional_text, re.IGNORECASE)
    if field_matches:
        # Convert to field IDs (lowercase, underscored)
        dependent_fields = [
            'p' + f.replace('P', '').replace(' Q', '_line').replace(' ', '').lower()
            for f in field_matches
        ]

    # Determine trigger field (usually the field itself for "If this is YES")
    trigger_field = None
    if 'if this is yes' in conditional_text.lower():
        trigger_field = field_id

    return {
        'type': 'needs_manual_parsing',
        'trigger_field': trigger_field,
        'dependent_fields': dependent_fields if dependent_fields else None,
        'unlock_method': 'voice_ai_only',
        'description': conditional_text,
        'note': 'Requires manual parsing - Gemini flagged for review'
    }


def parse_apt_suite_floor(conditional_text: str, field_id: str) -> Optional[Dict]:
    """
    Parse apartment/suite/floor checkbox conditionals.

    Example: "This field is read-only and only becomes available when the
              apartment, suite, or floor checkbox is selected."
    """
    if 'apartment' in conditional_text.lower() and 'checkbox' in conditional_text.lower():
        # Find corresponding checkbox field
        # Pattern: p7_line3b_aptsteflrnumber -> trigger is p7_line3a_* checkbox
        trigger_field = None
        if '_aptsteflrnumber' in field_id:
            # Replace aptsteflrnumber with checkbox reference
            base_id = field_id.replace('_aptsteflrnumber', '')
            trigger_field = f"{base_id}_aptsteflt"  # Typical naming

        return {
            'type': 'conditional_visibility',
            'trigger_field': trigger_field,
            'trigger_value': True,
            'unlock_method': 'flip_readonly_bit',
            'description': conditional_text,
            'pdf_field_flag_change': {
                'bit': 0,
                'current_value': 1,
                'required_value': 0
            }
        }

    return None


def parse_conditional_logic(conditional_text: str, field_id: str, field_data: Dict) -> Dict:
    """
    Main parser - route to appropriate parser based on conditional type.

    Returns structured conditional logic or marks for manual review.
    """
    category = categorize_conditional(conditional_text)
    result = None

    if category == 'pre_populated':
        result = parse_pre_populated(conditional_text, field_id)
    elif category == 'simple_readonly':
        # No conditional logic, just permanently read-only
        return {
            'type': 'simple_readonly',
            'unlock_method': 'none',
            'description': 'Field is permanently read-only'
        }
    elif category == 'show_if':
        # Check for apartment/suite/floor special case
        if 'apartment' in conditional_text.lower():
            result = parse_apt_suite_floor(conditional_text, field_id)
        if not result:
            result = parse_show_if(conditional_text, field_id)
    elif category == 'needs_manual':
        result = parse_needs_manual(conditional_text, field_id)
    else:
        result = None

    if not result:
        return {
            'type': 'unparsed',
            'unlock_method': 'voice_ai_only',
            'description': conditional_text,
            'note': 'Could not parse - manual review required'
        }

    return result


def convert_string_conditionals_to_structured(schema: Dict) -> Tuple[Dict, List[Dict]]:
    """
    Convert all string-format conditionals to structured format.

    Returns:
        (updated_schema, conversion_report)
    """
    conversion_report = []
    fields_updated = 0

    for field in schema['fields']:
        # Check both top-level and help section
        cond_location = None
        cond = field.get('conditional_logic')
        if cond and isinstance(cond, str):
            cond_location = 'top_level'
        elif not cond:
            cond = field.get('help', {}).get('conditional_logic')
            if cond and isinstance(cond, str):
                cond_location = 'help_section'

        if cond and isinstance(cond, str):
            # Parse the string conditional
            structured = parse_conditional_logic(cond, field['id'], field)

            # Store original string for reference
            structured['original_text'] = cond

            # Update field with structured conditional
            if cond_location == 'top_level':
                field['conditional_logic'] = structured
            else:
                field['help']['conditional_logic'] = structured

            fields_updated += 1

            # Track conversion
            conversion_report.append({
                'field_id': field['id'],
                'location': cond_location,
                'category': structured.get('type'),
                'needs_review': 'note' in structured,
                'original': cond[:100],
                'structured': structured
            })

    return schema, conversion_report


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python conditional_logic_parser.py <schema.json> [output.json]")
        sys.exit(1)

    schema_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else schema_path.replace('.json', '_structured_conditionals.json')

    # Load schema
    print("Loading schema...")
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    # Convert string conditionals
    print("\nConverting string-format conditionals to structured format...")
    updated_schema, report = convert_string_conditionals_to_structured(schema)

    # Save updated schema
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(updated_schema, f, indent=2, ensure_ascii=False)

    # Print report
    print(f"\n{'='*70}")
    print("CONDITIONAL LOGIC CONVERSION REPORT")
    print(f"{'='*70}")
    print(f"Total fields converted: {len(report)}")
    print(f"Saved to: {output_path}")

    # Categorize results
    categories = {}
    needs_review_count = 0

    for item in report:
        cat = item['category']
        categories[cat] = categories.get(cat, 0) + 1
        if item['needs_review']:
            needs_review_count += 1

    print(f"\nConversion breakdown:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")

    print(f"\nFields needing manual review: {needs_review_count}")

    if needs_review_count > 0:
        print(f"\nFields requiring manual review:")
        for item in report:
            if item['needs_review']:
                print(f"\n  Field: {item['field_id']}")
                print(f"  Original: {item['original']}")
                print(f"  Note: {item['structured'].get('note')}")

    print(f"\n{'='*70}")
    print("NEXT STEPS")
    print(f"{'='*70}")
    print("1. Review fields marked for manual parsing")
    print("2. Update trigger_field references where needed")
    print("3. Run schema validator to check for issues")
    print("4. Build bidirectional conditional index")


if __name__ == "__main__":
    main()
