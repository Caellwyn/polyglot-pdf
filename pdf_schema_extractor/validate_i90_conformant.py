"""
I-90 Schema Validation Script

Validates i-90_schema_v9_conformant.json against the FormSchema Pydantic model.

@version 1.0.0
@date 2025-11-01
"""

import json
from pathlib import Path
from form_models import FormSchema
from pydantic import ValidationError


def validate_schema(schema_path: Path) -> bool:
    """Validate schema against Pydantic model"""
    print("=" * 70)
    print("I-90 Schema Validation")
    print("=" * 70)
    print(f"\nValidating: {schema_path}")

    # Load schema
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_data = json.load(f)

    print(f"  - Loaded schema with {len(schema_data.get('fields', []))} fields")

    # Validate against Pydantic model
    try:
        form_schema = FormSchema(**schema_data)
        print("\n[SUCCESS] Schema is valid!")
        print(f"  - Source: {form_schema.source}")
        print(f"  - Title: {form_schema.form_metadata.title}")
        print(f"  - Parts: {len(form_schema.parts) if form_schema.parts else 0}")
        print(f"  - Sections: {len(form_schema.sections)}")
        print(f"  - Fields: {len(form_schema.fields)}")

        # Run additional reference validation
        print("\nValidating references...")
        validation_result = form_schema.validate_all_references()

        if validation_result['errors']:
            print("\n[ERRORS FOUND]")
            for error in validation_result['errors']:
                print(f"  - {error}")
            return False
        else:
            print("  [OK] All references are valid")

        if validation_result['warnings']:
            print("\n[WARNINGS]")
            for warning in validation_result['warnings']:
                print(f"  - {warning}")

        # Summary statistics
        print("\n" + "=" * 70)
        print("Validation Summary")
        print("=" * 70)

        # Count field types
        field_types = {}
        for field in form_schema.fields:
            field_type = field.type
            field_types[field_type] = field_types.get(field_type, 0) + 1

        print("\nField Type Distribution:")
        for field_type, count in sorted(field_types.items()):
            print(f"  - {field_type}: {count}")

        # Count conditional fields
        fields_with_show_if = sum(1 for f in form_schema.fields if f.show_if)
        fields_with_controls = sum(1 for f in form_schema.fields if f.controls_fields)
        fields_with_behavior = sum(1 for f in form_schema.fields if f.conditional_behavior)

        print("\nConditional Logic:")
        print(f"  - Fields with show_if: {fields_with_show_if}")
        print(f"  - Fields with controls_fields: {fields_with_controls}")
        print(f"  - Fields with conditional_behavior: {fields_with_behavior}")

        # Count validation rules
        fields_with_validation = sum(1 for f in form_schema.fields if f.validation)
        fields_required = sum(1 for f in form_schema.fields
                            if f.validation and f.validation.required)
        fields_read_only = sum(1 for f in form_schema.fields if f.read_only)

        print("\nValidation & Constraints:")
        print(f"  - Fields with validation: {fields_with_validation}")
        print(f"  - Required fields: {fields_required}")
        print(f"  - Read-only fields: {fields_read_only}")

        print("\n" + "=" * 70)
        print("[SUCCESS] Schema validation complete!")
        print("=" * 70)
        return True

    except ValidationError as e:
        print("\n[VALIDATION FAILED]")
        print("\nPydantic Validation Errors:")
        print("-" * 70)

        # Parse and display errors
        errors = e.errors()
        for error in errors:
            loc = " -> ".join(str(x) for x in error['loc'])
            msg = error['msg']
            error_type = error['type']
            print(f"\nLocation: {loc}")
            print(f"  Type: {error_type}")
            print(f"  Message: {msg}")

        print("\n" + "=" * 70)
        print(f"Total Errors: {len(errors)}")
        print("=" * 70)
        return False

    except Exception as e:
        print(f"\n[ERROR] Unexpected error during validation: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    schema_path = Path("test_schemas/test_pdfs/i-90/i-90_schema_v9_conformant.json")
    success = validate_schema(schema_path)
    exit(0 if success else 1)
