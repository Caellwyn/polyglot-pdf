#!/usr/bin/env python3
"""
PDF Field Flag Mutator - Unlocks conditional fields based on schema.

Creates "unlocked" PDFs where read-only conditional fields have their
READ_ONLY bit (bit 0) cleared, enabling them to be filled for testing.

Reusable across ALL forms.
"""

import fitz
import json
import sys
from typing import Dict, List, Tuple


def parse_conditional_logic(conditional_logic) -> Dict:
    """
    Parse conditional logic from schema into structured format.

    Handles both string format and structured dict format.

    Returns:
        {
            'unlock_method': 'flip_readonly_bit' | 'voice_ai_only' | 'javascript',
            'bit_change': {
                'bit': 0,
                'from': 1,
                'to': 0
            }
        }
    """
    if isinstance(conditional_logic, dict):
        # Structured format from enhanced Gemini
        unlock_method = conditional_logic.get('unlock_method', 'voice_ai_only')
        bit_change = conditional_logic.get('pdf_field_flag_change')

        if unlock_method == 'flip_readonly_bit' and bit_change:
            return {
                'unlock_method': unlock_method,
                'bit_change': bit_change
            }

    elif isinstance(conditional_logic, str):
        # String format - check if it mentions read-only or bit flipping
        text = conditional_logic.lower()
        if 'read-only' in text or 'read only' in text or 'pre-populated' in text:
            # Assume it needs readonly bit cleared
            return {
                'unlock_method': 'flip_readonly_bit',
                'bit_change': {
                    'bit': 0,
                    'current_value': 1,
                    'required_value': 0
                }
            }

    return {'unlock_method': 'voice_ai_only'}


def extract_unlock_instructions(schema: Dict) -> List[Dict]:
    """
    Extract all field unlocking instructions from schema.

    Supports both v8 (conditional_logic) and v9 (conditional_behavior) schemas.

    Returns list of:
    {
        "field_pdf_name": "P1_Line5a_FirstName[0]",
        "field_id": "p1_line5a_firstname",
        "unlock_method": "flip_readonly_bit",
        "bit_change": {
            "bit": 0,
            "from": 1,
            "to": 0
        }
    }
    """
    unlock_instructions = []

    for field in schema.get('fields', []):
        # V9 schema format: check conditional_behavior (new format)
        conditional_behavior = field.get('conditional_behavior')

        # Also check if field has show_if and is read_only (indicates conditional field)
        show_if = field.get('show_if')
        read_only = field.get('read_only', False)

        # V8 schema format: check conditional_logic (legacy)
        conditional_logic = field.get('conditional_logic')
        if not conditional_logic:
            # Also check in help section (very old format)
            help_section = field.get('help', {})
            conditional_logic = help_section.get('conditional_logic')

        # Determine unlock method
        unlock_method = None
        bit_change = None

        # Priority 1: conditional_behavior (v9)
        if conditional_behavior:
            unlock_method = conditional_behavior.get('unlock_method')
            bit_change = conditional_behavior.get('pdf_field_flag_change')

        # Priority 2: conditional_logic (v8)
        elif conditional_logic:
            parsed = parse_conditional_logic(conditional_logic)
            unlock_method = parsed.get('unlock_method')
            bit_change = parsed.get('bit_change')

        # Priority 3: Infer from show_if + read_only (v9 inference)
        elif show_if and read_only:
            # Field has conditional display and is read-only
            # Assume it needs unlocking via bit flip
            unlock_method = 'flip_readonly_bit'
            bit_change = {
                'bit': 0,
                'current_value': 1,
                'required_value': 0
            }

        # Skip if no unlock method found
        if unlock_method != 'flip_readonly_bit':
            continue

        # Get PDF field name(s)
        pdf_field_name = field.get('pdf_field_name')

        # For group fields, get all consolidated widgets
        pdf_fields = []
        if pdf_field_name:
            pdf_fields.append(pdf_field_name)
        elif field.get('consolidated_widgets'):
            pdf_fields.extend(field['consolidated_widgets'])

        # Add unlock instructions
        for pdf_name in pdf_fields:
            unlock_instructions.append({
                'field_pdf_name': pdf_name,
                'field_id': field.get('id'),
                'unlock_method': unlock_method,
                'bit_change': bit_change or {
                    'bit': 0,
                    'current_value': 1,
                    'required_value': 0
                }
            })

    return unlock_instructions


def flip_field_bit(widget, bit: int, target_value: int) -> bool:
    """
    Modify widget field_flags bit.

    Args:
        widget: PyMuPDF widget
        bit: Bit position (0-31)
        target_value: Target value (0 or 1)

    Returns:
        True if bit was changed, False if already at target value
    """
    original_flags = widget.field_flags or 0
    current_bit_value = (original_flags >> bit) & 1

    # Check if already at target
    if current_bit_value == target_value:
        return False

    # Modify the bit
    if target_value == 0:
        # Clear bit
        widget.field_flags = original_flags & ~(1 << bit)
    else:
        # Set bit
        widget.field_flags = original_flags | (1 << bit)

    widget.update()
    return True


def create_unlocked_pdf(
    source_pdf: str,
    schema_file: str,
    output_pdf: str
) -> Dict:
    """
    Create unlocked version of PDF for testing conditional fields.

    Args:
        source_pdf: Original PDF path
        schema_file: Schema JSON with conditional_logic
        output_pdf: Path for unlocked PDF

    Returns:
        Statistics dict with results
    """
    print("="*70)
    print("PDF FIELD FLAG MUTATOR - Unlocking Conditional Fields")
    print("="*70)

    # Load schema
    print("\n[1/4] Loading schema...")
    with open(schema_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    # Extract unlock instructions
    print("\n[2/4] Parsing conditional logic...")
    unlock_instructions = extract_unlock_instructions(schema)

    print(f"  Found {len(unlock_instructions)} fields to unlock")

    if not unlock_instructions:
        print("\n  No conditional fields found that require unlocking.")
        print("  Schema may not have structured conditional_logic with unlock_method.")
        return {
            'fields_unlocked': 0,
            'fields_not_found': 0,
            'total_unlock_requests': 0
        }

    # Show sample instructions
    print("\n  Sample unlock instructions:")
    for instr in unlock_instructions[:3]:
        print(f"    - {instr['field_pdf_name']}: flip bit {instr['bit_change']['bit']} ({instr['bit_change']['current_value']} -> {instr['bit_change']['required_value']})")
    if len(unlock_instructions) > 3:
        print(f"    ... and {len(unlock_instructions) - 3} more")

    # Open PDF
    print("\n[3/4] Processing PDF...")
    doc = fitz.open(source_pdf)

    stats = {
        'fields_unlocked': 0,
        'fields_not_found': 0,
        'total_unlock_requests': len(unlock_instructions),
        'unlocked_fields': []
    }

    # Create lookup for fast matching
    # Match both full hierarchical name and short name
    unlock_by_name = {}
    for instr in unlock_instructions:
        pdf_name = instr['field_pdf_name']
        short_name = pdf_name.split('.')[-1]

        unlock_by_name[pdf_name] = instr
        unlock_by_name[short_name] = instr

    # Apply unlocks
    for page_num, page in enumerate(doc):
        for widget in page.widgets():
            field_name = widget.field_name
            if not field_name:
                continue

            # Try exact match first
            unlock_instr = unlock_by_name.get(field_name)

            # Try short name
            if not unlock_instr:
                short_name = field_name.split('.')[-1]
                unlock_instr = unlock_by_name.get(short_name)

            if unlock_instr:
                bit_change = unlock_instr['bit_change']

                # Flip the bit
                changed = flip_field_bit(
                    widget,
                    bit=bit_change['bit'],
                    target_value=bit_change['required_value']
                )

                if changed:
                    stats['fields_unlocked'] += 1
                    stats['unlocked_fields'].append({
                        'field_name': field_name,
                        'page': page_num,
                        'bit': bit_change['bit'],
                        'old_flags': widget.field_flags | (1 << bit_change['bit']) if bit_change['required_value'] == 0 else widget.field_flags & ~(1 << bit_change['bit']),
                        'new_flags': widget.field_flags
                    })

    # Calculate not found
    stats['fields_not_found'] = stats['total_unlock_requests'] - stats['fields_unlocked']

    # Save
    print("\n[4/4] Saving unlocked PDF...")
    doc.save(output_pdf, garbage=4, deflate=True)
    doc.close()

    print("\n" + "="*70)
    print("UNLOCKING COMPLETE")
    print("="*70)
    print(f"Unlocked PDF: {output_pdf}")
    print(f"\nResults:")
    print(f"  Fields unlocked: {stats['fields_unlocked']}")
    print(f"  Fields not found: {stats['fields_not_found']}")
    print(f"  Total requests: {stats['total_unlock_requests']}")

    if stats['fields_not_found'] > 0:
        print(f"\n  WARNING: {stats['fields_not_found']} fields were not found in PDF")
        print(f"  This may be due to:")
        print(f"    - Field name mismatch between schema and PDF")
        print(f"    - Fields that don't actually exist")
        print(f"    - Conditional logic applied to wrong fields")

    if stats['fields_unlocked'] > 0:
        print(f"\n  SUCCESS: {stats['fields_unlocked']} fields unlocked")
        print(f"  Sample unlocked fields:")
        for field_info in stats['unlocked_fields'][:5]:
            print(f"    - {field_info['field_name']} (page {field_info['page']})")
            print(f"      Flags: 0x{field_info['old_flags']:08x} -> 0x{field_info['new_flags']:08x}")
        if len(stats['unlocked_fields']) > 5:
            print(f"    ... and {len(stats['unlocked_fields']) - 5} more")

    return stats


def verify_unlock(pdf_path: str, field_names: List[str]) -> Dict:
    """
    Verify that fields were unlocked successfully.

    Args:
        pdf_path: Path to unlocked PDF
        field_names: List of field names to check

    Returns:
        Dict with verification results
    """
    doc = fitz.open(pdf_path)

    results = {
        'checked': 0,
        'unlocked': 0,
        'still_locked': 0,
        'not_found': 0
    }

    for page in doc:
        for widget in page.widgets():
            field_name = widget.field_name

            if field_name in field_names or field_name.split('.')[-1] in field_names:
                results['checked'] += 1

                # Check READ_ONLY bit (bit 0)
                is_readonly = bool(widget.field_flags & (1 << 0))

                if is_readonly:
                    results['still_locked'] += 1
                else:
                    results['unlocked'] += 1

    results['not_found'] = len(field_names) - results['checked']

    doc.close()
    return results


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python pdf_field_flag_mutator.py <source.pdf> <schema.json> [output_unlocked.pdf]")
        print("\nExample:")
        print("  python pdf_field_flag_mutator.py \\")
        print("    test_schemas/test_pdfs/i-90/i-90.pdf \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v4_gemini_validated.json \\")
        print("    test_schemas/test_pdfs/i-90/i-90_unlocked.pdf")
        sys.exit(1)

    source = sys.argv[1]
    schema = sys.argv[2]
    output = sys.argv[3] if len(sys.argv) > 3 else source.replace('.pdf', '_unlocked.pdf')

    stats = create_unlocked_pdf(source, schema, output)

    # Verify if any fields were unlocked
    if stats['fields_unlocked'] > 0:
        print("\n" + "="*70)
        print("VERIFICATION")
        print("="*70)

        # Get list of unlocked field names
        unlocked_names = [f['field_name'] for f in stats['unlocked_fields']]

        verify_results = verify_unlock(output, unlocked_names)

        print(f"Verified {verify_results['checked']} fields:")
        print(f"  Unlocked (READ_ONLY bit cleared): {verify_results['unlocked']}")
        print(f"  Still locked (READ_ONLY bit set): {verify_results['still_locked']}")
        print(f"  Not found: {verify_results['not_found']}")

        if verify_results['unlocked'] == verify_results['checked']:
            print("\n  SUCCESS: All fields verified as unlocked!")
        elif verify_results['still_locked'] > 0:
            print(f"\n  WARNING: {verify_results['still_locked']} fields are still locked")
