#!/usr/bin/env python3
"""
Generate field manifests from form schemas.

A manifest is a lightweight representation containing only:
- field_id
- spoken_name

This is used for JIT (Just-In-Time) field loading to reduce initial token count
from ~7,400 to <500 tokens.

Conditionals, validation rules, help text, and options are NOT included in the manifest.
They are loaded on-demand when needed.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List


def generate_manifest(schema: dict) -> dict:
    """
    Generate a minimal manifest from a full schema.

    Args:
        schema: Full form schema with all field details

    Returns:
        Manifest containing only field_id and spoken_name for each field
    """
    manifest = {
        "form_metadata": {
            "form_number": schema.get("form_metadata", {}).get("form_number", "UNKNOWN"),
            "version": schema.get("form_metadata", {}).get("version", "UNKNOWN"),
            "total_fields": len(schema.get("fields", [])),
        },
        "parts": []
    }

    # Process each part
    for part in schema.get("parts", []):
        part_manifest = {
            "part_id": part["id"],
            "part_label": part["label"],
            "part_order": part["order"],
            "fields": []
        }

        # Get all fields in this part by looking up sections
        part_field_ids = set()
        for section_id in part.get("section_ids", []):
            section = next((s for s in schema.get("sections", []) if s["id"] == section_id), None)
            if section:
                part_field_ids.update(section.get("fields", []))

        # Extract minimal field info for fields in this part
        for field in schema.get("fields", []):
            if field["id"] in part_field_ids:
                field_entry = {
                    "field_id": field["id"],
                    "spoken_name": field.get("spoken_name", field.get("name", "UNKNOWN"))
                }
                part_manifest["fields"].append(field_entry)

        manifest["parts"].append(part_manifest)

    return manifest


def count_tokens_estimate(manifest: dict) -> int:
    """
    Estimate token count for a manifest.

    Rough estimate: ~4 characters per token for JSON.
    """
    manifest_str = json.dumps(manifest, indent=2)
    char_count = len(manifest_str)
    token_estimate = char_count // 4
    return token_estimate


def validate_manifest(manifest: dict, schema: dict) -> Dict[str, List[str]]:
    """
    Validate that a manifest is correct and complete.

    Checks:
    1. All fields from schema are in manifest
    2. All spoken names are present
    3. No duplicate field_ids
    4. No duplicate spoken_names
    5. Manifest does NOT contain conditional info, validation, options, etc.

    Returns:
        Dict with 'errors' and 'warnings' lists
    """
    errors = []
    warnings = []

    # Get all field IDs from schema
    schema_field_ids = {f["id"] for f in schema.get("fields", [])}

    # Get all field IDs from manifest
    manifest_field_ids = set()
    for part in manifest.get("parts", []):
        for field in part.get("fields", []):
            manifest_field_ids.add(field["field_id"])

    # Check coverage
    missing_fields = schema_field_ids - manifest_field_ids
    if missing_fields:
        errors.append(f"Manifest missing {len(missing_fields)} fields: {list(missing_fields)[:5]}...")

    extra_fields = manifest_field_ids - schema_field_ids
    if extra_fields:
        errors.append(f"Manifest has {len(extra_fields)} unknown fields: {list(extra_fields)[:5]}...")

    # Check for duplicates
    all_field_ids = []
    all_spoken_names = []
    for part in manifest.get("parts", []):
        for field in part.get("fields", []):
            all_field_ids.append(field["field_id"])
            all_spoken_names.append(field.get("spoken_name", ""))

    duplicate_ids = [fid for fid in set(all_field_ids) if all_field_ids.count(fid) > 1]
    if duplicate_ids:
        errors.append(f"Duplicate field_ids in manifest: {duplicate_ids}")

    duplicate_names = [name for name in set(all_spoken_names) if all_spoken_names.count(name) > 1]
    if duplicate_names:
        errors.append(f"Duplicate spoken_names in manifest: {duplicate_names}")

    # Check that manifest doesn't include restricted fields
    for part in manifest.get("parts", []):
        for field in part.get("fields", []):
            restricted_keys = {"validation", "options", "help", "show_if", "conditional_fields",
                             "type", "description", "placeholder"}
            found_restricted = restricted_keys & set(field.keys())
            if found_restricted:
                warnings.append(f"Field {field['field_id']} contains restricted keys: {found_restricted}")

    return {"errors": errors, "warnings": warnings}


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_manifest.py <schema_path> [--output <manifest_path>]")
        print("\nGenerates a minimal field manifest for JIT schema loading.")
        sys.exit(1)

    schema_path = sys.argv[1]
    output_path = None

    if "--output" in sys.argv:
        output_idx = sys.argv.index("--output")
        if output_idx + 1 < len(sys.argv):
            output_path = sys.argv[output_idx + 1]

    if not Path(schema_path).exists():
        print(f"[ERROR] Schema file not found: {schema_path}")
        sys.exit(1)

    print(f"[LOADING] Schema: {schema_path}")
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    print(f"[INFO] Form: {schema.get('form_metadata', {}).get('form_number', 'UNKNOWN')}")
    print(f"[INFO] Total fields: {len(schema.get('fields', []))}")
    print(f"[INFO] Total parts: {len(schema.get('parts', []))}")

    # Generate manifest
    print(f"\n[GENERATING] Manifest...")
    manifest = generate_manifest(schema)

    # Estimate tokens
    token_estimate = count_tokens_estimate(manifest)
    print(f"[TOKENS] Estimated token count: {token_estimate}")

    if token_estimate > 500:
        print(f"[WARNING] Token count exceeds target of 500 tokens!")
    else:
        print(f"[PASS] Token count within target (<500)")

    # Validate manifest
    print(f"\n[VALIDATING] Manifest...")
    validation = validate_manifest(manifest, schema)

    if validation["errors"]:
        print(f"[FAIL] Validation errors:")
        for error in validation["errors"]:
            print(f"  - {error}")
        sys.exit(1)

    if validation["warnings"]:
        print(f"[WARNING] Validation warnings:")
        for warning in validation["warnings"]:
            print(f"  - {warning}")

    print(f"[PASS] Manifest validation successful!")

    # Save manifest
    if not output_path:
        output_path = schema_path.replace('.json', '_manifest.json')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n[SAVED] Manifest saved to: {output_path}")
    print(f"\n[SUMMARY]")
    print(f"  Form: {manifest['form_metadata']['form_number']}")
    print(f"  Fields: {manifest['form_metadata']['total_fields']}")
    print(f"  Parts: {len(manifest['parts'])}")
    print(f"  Estimated tokens: {token_estimate}")
    print(f"  Target: <500 tokens")
    print(f"  Status: {'PASS' if token_estimate <= 500 else 'FAIL'}")


if __name__ == '__main__':
    main()
