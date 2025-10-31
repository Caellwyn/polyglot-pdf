#!/usr/bin/env python3
"""
Validate extracted schema against form_schema_model.py
"""

import sys
import json
from pathlib import Path

# Add parent directory to path to import form_schema_model
sys.path.insert(0, str(Path(__file__).parent))

from form_schema_model import FormSchema, FormField, FormSection, FormPart, FieldType


def convert_to_form_schema(raw_schema: dict) -> dict:
    """
    Convert raw schema from builder to FormSchema-compatible format.
    """
    form_metadata = raw_schema.get("form_metadata", {})
    raw_fields = raw_schema.get("fields", [])

    # Group fields by section
    section_map = {}
    for field in raw_fields:
        section_name = field.get("section", "General")
        if section_name not in section_map:
            section_map[section_name] = []
        section_map[section_name].append(field)

    # Convert fields to FormField format
    converted_fields = []
    for field in raw_fields:
        try:
            # Map field type
            field_type_str = field.get("type", "text")
            type_mapping = {
                "text": FieldType.TEXT,
                "textarea": FieldType.TEXTAREA,
                "checkbox": FieldType.CHECKBOX,
                "radio": FieldType.RADIO,
                "signature": FieldType.SIGNATURE,
                "select": FieldType.SELECT,
                "date": FieldType.DATE,
            }
            field_type = type_mapping.get(field_type_str, FieldType.TEXT)

            # Build FormField-compatible dict
            converted_field = {
                "id": field.get("id", "unknown"),
                "name": field.get("name", "Unknown Field"),
                "spoken_name": field.get("name", "Unknown Field").lower(),
                "type": field_type,
                "section_id": field.get("section", "general").lower().replace(" ", "_").replace("-", "_"),
            }

            # Add optional fields
            if field.get("pdf_field_name"):
                converted_field["pdf_field_name"] = field["pdf_field_name"]

            if field.get("options"):
                converted_field["options"] = field["options"]

            converted_fields.append(converted_field)

        except Exception as e:
            print(f"  WARNING: Failed to convert field {field.get('id')}: {e}")

    # Create sections
    sections = []
    for i, (section_name, fields) in enumerate(section_map.items()):
        section_id = section_name.lower().replace(" ", "_").replace("-", "_")
        sections.append({
            "id": section_id,
            "label": section_name,
            "order": i + 1,
            "fields": [f["id"] for f in fields if f.get("section") == section_name]
        })

    # Build FormSchema-compatible structure
    schema = {
        "source": "pdf",
        "form_metadata": {
            "title": form_metadata.get("title", "Unknown Form"),
            "form_number": form_metadata.get("form_number"),
            "edition_date": form_metadata.get("edition_date"),
            "version": "1.0.0",
            "language": "en"
        },
        "sections": sections,
        "fields": converted_fields
    }

    return schema


def validate_schema(schema_path: str, verbose: bool = True):
    """
    Validate schema against FormSchema model.
    """
    print("="*70)
    print("SCHEMA VALIDATION")
    print("="*70)
    print(f"\nSchema file: {schema_path}")

    # Load raw schema
    print("\n[1/4] Loading schema...")
    with open(schema_path, 'r', encoding='utf-8') as f:
        raw_schema = json.load(f)

    print(f"  Loaded {len(raw_schema.get('fields', []))} fields")

    # Convert to FormSchema format
    print("\n[2/4] Converting to FormSchema format...")
    try:
        converted = convert_to_form_schema(raw_schema)
        print(f"  Created {len(converted['sections'])} sections")
        print(f"  Converted {len(converted['fields'])} fields")
    except Exception as e:
        print(f"  ERROR during conversion: {e}")
        return False

    # Validate with Pydantic
    print("\n[3/4] Validating with Pydantic FormSchema model...")
    errors = []
    warnings = []

    try:
        # This will raise ValidationError if invalid
        form_schema = FormSchema(**converted)
        print("  [OK] Schema structure is valid!")

    except Exception as e:
        print(f"  [FAIL] Validation failed: {e}")
        errors.append(str(e))

        # Try to provide more detail
        if verbose:
            print("\nDetailed errors:")
            error_str = str(e)
            for line in error_str.split('\n'):
                if line.strip():
                    print(f"    {line}")

        return False

    # Additional checks
    print("\n[4/4] Running additional checks...")

    # Check for duplicate field IDs
    field_ids = [f.id for f in form_schema.fields]
    duplicates = [fid for fid in field_ids if field_ids.count(fid) > 1]
    if duplicates:
        warnings.append(f"Duplicate field IDs: {set(duplicates)}")

    # Check for fields without sections
    orphan_fields = [f.id for f in form_schema.fields if f.section_id not in [s.id for s in form_schema.sections]]
    if orphan_fields:
        warnings.append(f"{len(orphan_fields)} fields reference non-existent sections")

    # Check for empty sections
    empty_sections = [s.id for s in form_schema.sections if not s.fields]
    if empty_sections:
        warnings.append(f"{len(empty_sections)} empty sections: {empty_sections}")

    # Check for required fields without validation
    fields_missing_validation = [
        f.id for f in form_schema.fields
        if f.required and not f.validation
    ]
    if fields_missing_validation:
        warnings.append(f"{len(fields_missing_validation)} required fields without validation rules")

    # Print results
    print("\n" + "="*70)
    print("VALIDATION RESULTS")
    print("="*70)

    if errors:
        print(f"\n[FAIL] FAILED with {len(errors)} error(s):")
        for error in errors:
            print(f"  - {error}")
        return False
    else:
        print("\n[PASS] Schema is valid!")

    if warnings:
        print(f"\n[WARN] {len(warnings)} warning(s):")
        for warning in warnings:
            print(f"  - {warning}")

    # Print summary stats
    print(f"\nSchema Statistics:")
    print(f"  Form: {form_schema.form_metadata.title}")
    print(f"  Form Number: {form_schema.form_metadata.form_number}")
    print(f"  Edition: {form_schema.form_metadata.edition_date}")
    print(f"  Sections: {len(form_schema.sections)}")
    print(f"  Fields: {len(form_schema.fields)}")

    # Field type distribution
    from collections import Counter
    type_counts = Counter(f.type for f in form_schema.fields)
    print(f"\n  Field Types:")
    for ftype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"    {ftype}: {count}")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_schema.py <schema_json> [--verbose]")
        sys.exit(1)

    schema_path = sys.argv[1]
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    success = validate_schema(schema_path, verbose=verbose)
    sys.exit(0 if success else 1)
