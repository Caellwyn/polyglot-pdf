#!/usr/bin/env python3
"""
Fix duplicate spoken names in form schemas.

This script:
1. Loads a form schema JSON file
2. Identifies duplicate spoken names
3. Generates unique spoken names based on context (field name, help text, section)
4. Updates the schema with unique spoken names
5. Validates 100% uniqueness
"""

import json
import sys
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Tuple


def load_schema(schema_path: str) -> dict:
    """Load schema from JSON file."""
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_duplicate_spoken_names(schema: dict) -> Dict[str, List[dict]]:
    """
    Find all duplicate spoken names and return grouped by spoken name.

    Returns:
        Dict mapping spoken_name to list of fields with that name
    """
    spoken_name_to_fields = defaultdict(list)

    for field in schema.get('fields', []):
        spoken_name = field.get('spoken_name', '')
        if spoken_name:
            spoken_name_to_fields[spoken_name].append(field)

    # Filter to only duplicates
    duplicates = {
        name: fields
        for name, fields in spoken_name_to_fields.items()
        if len(fields) > 1
    }

    return duplicates


def extract_field_info(field: dict) -> dict:
    """Extract relevant info from a field for display and disambiguation."""
    return {
        'field_id': field.get('id', 'NO_ID'),
        'name': field.get('name', 'NO_NAME'),
        'spoken_name': field.get('spoken_name', 'NO_SPOKEN_NAME'),
        'section_id': field.get('section_id', 'NO_SECTION'),
        'help': field.get('help', {}),
        'type': field.get('type', 'unknown'),
    }


def generate_unique_spoken_name(field_info: dict, index: int, total: int) -> str:
    """
    Generate a unique spoken name based on field context.

    Strategy:
    - Extract context from help text (most reliable)
    - Fall back to field name/ID patterns
    - Use section context if available
    - Add numeric suffix as last resort
    """
    field_id = field_info['field_id'].lower()
    field_name = field_info['name'].lower()
    section_id = field_info['section_id'].lower()
    help_text = field_info.get('help', {})
    original_spoken = field_info['spoken_name']

    # Extract help instructions (most reliable context)
    instructions = help_text.get('instructions', '').lower() if help_text else ''

    # Context extraction patterns
    context = None

    # Check help text first (most reliable)
    if 'interpreter' in instructions:
        context = "interpreter's"
    elif 'preparer' in instructions:
        context = "preparer's"
    elif 'mailing address' in instructions:
        context = 'mailing'
    elif 'physical address' in instructions:
        context = 'physical'
    elif 'daytime' in instructions or 'daytime' in field_name:
        context = 'daytime'
    elif 'mobile' in instructions or 'mobile' in field_name:
        context = 'mobile'
    elif 'evening' in instructions or 'evening' in field_name:
        context = 'evening'

    # Additional Information page context (Part 8)
    elif 'part 8' in section_id or 'additional information' in section_id:
        # For Part 8 repeating fields, distinguish by line number and array notation
        # Pattern: p8_line{N}{suffix}[{array_index}]
        # Lines map to entries: line3=entry1, line4=entry2, line5=entry3, line5[1]=entry4, line5[2]=entry5
        if '_line3' in field_id:
            context = 'entry 1'
        elif '_line4' in field_id:
            context = 'entry 2'
        elif '_line5' in field_id:
            # Distinguish based on array notation
            if '[2]' in field_id:
                context = 'entry 5'
            elif '[1]' in field_id:
                context = 'entry 4'
            else:
                # Base field without array notation
                context = 'entry 3'

    # Pre-populated fields from Part 1
    elif 'pre-populate' in field_name.lower() or 'pre-populates' in instructions:
        context = 'page 8'

    # Address-related contexts from field name/ID
    elif 'mailing' in field_name or 'mailing' in field_id:
        context = 'mailing'
    elif 'physical' in field_name or 'physical' in field_id:
        context = 'physical'
    elif 'residence' in field_name or 'residence' in field_id:
        context = 'current'
    elif 'safe mailing' in field_name or 'safemailing' in field_id:
        context = 'safe mailing'

    # Section-based context (Part 6 = Interpreter, Part 7 = Preparer)
    elif 'part_6' in section_id or 'part 6' in section_id:
        context = "interpreter's"
    elif 'part_7' in section_id or 'part 7' in section_id:
        context = "preparer's"
    elif 'part_5' in section_id or 'part 5' in section_id:
        context = "applicant's"

    # Port of Entry disambiguation
    elif 'port-of-entry' in instructions:
        if 'part 2' in section_id or 'application type' in section_id:
            context = 'commuter status'
        elif 'part 3' in section_id or 'processing information' in section_id:
            context = 'original entry'

    # Build unique name
    if context:
        return f"{context} {original_spoken}"
    else:
        # Fall back to numeric suffix
        if total == 2:
            return f"{original_spoken} {index + 1}"
        else:
            return f"{original_spoken} (entry {index + 1})"


def fix_duplicates(schema: dict, dry_run: bool = True) -> Tuple[dict, List[dict]]:
    """
    Fix duplicate spoken names in the schema.

    Args:
        schema: The form schema dict
        dry_run: If True, don't modify schema, just report what would change

    Returns:
        (modified_schema, changes_list)
    """
    duplicates = find_duplicate_spoken_names(schema)
    changes = []

    if not duplicates:
        print("[OK] No duplicate spoken names found!")
        return schema, changes

    print(f"\n[FOUND] {len(duplicates)} duplicate spoken names affecting {sum(len(fields) for fields in duplicates.values())} fields\n")

    # Process each duplicate group
    for spoken_name, fields in sorted(duplicates.items()):
        print(f"\n{'='*80}")
        print(f"Duplicate: '{spoken_name}' ({len(fields)} fields)")
        print(f"{'='*80}")

        # Sort fields by ID for consistent ordering
        fields_sorted = sorted(fields, key=lambda f: f.get('id', ''))

        for idx, field in enumerate(fields_sorted):
            info = extract_field_info(field)
            new_spoken_name = generate_unique_spoken_name(info, idx, len(fields))

            print(f"\n  [{idx + 1}/{len(fields)}] {info['field_id']}")
            print(f"    Name: {info['name']}")
            print(f"    Section: {info['section_id']}")
            print(f"    Type: {info['type']}")
            print(f"    Help: {info['help']}")
            print(f"    Current: '{info['spoken_name']}'")
            print(f"    New:     '{new_spoken_name}'")

            change = {
                'field_id': info['field_id'],
                'old_spoken_name': info['spoken_name'],
                'new_spoken_name': new_spoken_name,
                'field_name': info['name'],
            }
            changes.append(change)

            if not dry_run:
                # Actually update the field in the schema
                field['spoken_name'] = new_spoken_name

    return schema, changes


def validate_uniqueness(schema: dict) -> bool:
    """Validate that all spoken names are unique."""
    spoken_names = [f.get('spoken_name', '') for f in schema.get('fields', [])]
    spoken_names = [name for name in spoken_names if name]  # Filter empty

    counter = Counter(spoken_names)
    duplicates = [name for name, count in counter.items() if count > 1]

    if duplicates:
        print(f"\n[FAIL] VALIDATION FAILED: {len(duplicates)} duplicate spoken names remain:")
        for name in duplicates:
            print(f"   - '{name}' (appears {counter[name]} times)")
        return False
    else:
        print(f"\n[PASS] VALIDATION PASSED: All {len(spoken_names)} spoken names are unique!")
        return True


def save_schema(schema: dict, output_path: str):
    """Save updated schema to JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    print(f"\n[SAVED] Updated schema saved to: {output_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_duplicate_spoken_names.py <schema_path> [--apply]")
        print("\nOptions:")
        print("  --apply    Actually modify the schema (default is dry-run)")
        sys.exit(1)

    schema_path = sys.argv[1]
    apply_changes = '--apply' in sys.argv

    if not Path(schema_path).exists():
        print(f"[ERROR] Schema file not found: {schema_path}")
        sys.exit(1)

    print(f"[LOADING] Schema: {schema_path}")
    schema = load_schema(schema_path)

    print(f"[INFO] Schema info:")
    print(f"   Form: {schema.get('form_metadata', {}).get('form_number', 'UNKNOWN')}")
    print(f"   Version: {schema.get('form_metadata', {}).get('version', 'UNKNOWN')}")
    print(f"   Total fields: {len(schema.get('fields', []))}")

    if apply_changes:
        print(f"\n[APPLY] APPLY MODE: Schema will be modified")
    else:
        print(f"\n[DRY-RUN] No changes will be made (use --apply to modify)")

    # Fix duplicates
    modified_schema, changes = fix_duplicates(schema, dry_run=not apply_changes)

    if changes:
        print(f"\n[SUMMARY] {len(changes)} fields would be updated")

        if apply_changes:
            # Validate uniqueness
            if validate_uniqueness(modified_schema):
                # Save to new file with _unique suffix
                output_path = schema_path.replace('.json', '_unique.json')
                save_schema(modified_schema, output_path)
                print(f"\n[SUCCESS] Original file preserved, updated schema saved to:")
                print(f"   {output_path}")
            else:
                print(f"\n[ERROR] Failed validation - schema not saved")
                sys.exit(1)
        else:
            print(f"\n[INFO] To apply these changes, run with --apply flag")
    else:
        validate_uniqueness(schema)


if __name__ == '__main__':
    main()
