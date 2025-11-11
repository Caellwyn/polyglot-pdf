"""
Test Gemini-Enhanced Extraction Pipeline

Tests the complete flow:
1. Create annotated PDF (heuristic)
2. Build simplified field list
3. Call Gemini for enhancements
4. Merge heuristic + Gemini
5. Validate final schema

@version 1.0.0
@date 2025-11-10
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any

from form_models import FormSchema
from gemini_models import SimplifiedField
from gemini_enhancer import GeminiEnhancer
from schema_merger import merge_schemas
from pdf_annotator import annotate_pdf_with_field_names
from widget_inventory import extract_widget_inventory


def load_heuristic_schema(schema_path: str) -> FormSchema:
    """Load existing heuristic schema."""
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_data = json.load(f)

    return FormSchema(**schema_data)


def build_simplified_fields(schema: FormSchema) -> list[SimplifiedField]:
    """
    Build simplified field list for Gemini from full schema.

    Extracts only the essential information to minimize token count.
    """
    simplified = []

    for field in schema.fields:
        # Extract position if available
        position = {}
        if field.pdf_position:
            position = {
                "x": field.pdf_position.x,
                "y": field.pdf_position.y,
                "width": field.pdf_position.width,
                "height": field.pdf_position.height
            }

        simplified.append(SimplifiedField(
            id=field.id,
            pdf_field_name=field.pdf_field_name or field.name,
            type=field.type,
            label=field.label or field.name,
            page=field.pdf_position.page if field.pdf_position else 1,
            position=position
        ))

    return simplified


def extract_form_metadata(schema: FormSchema) -> Dict[str, Any]:
    """Extract relevant metadata for Gemini."""
    metadata = schema.form_metadata.model_dump() if schema.form_metadata else {}

    return {
        "form_number": metadata.get("form_number", "Unknown"),
        "title": metadata.get("title", "Unknown Form"),
        "edition_date": metadata.get("edition_date"),
        "total_fields": len(schema.fields)
    }


def test_extraction_pipeline(
    pdf_path: str,
    heuristic_schema_path: str,
    output_path: str,
    skip_annotation: bool = False
):
    """
    Test complete Gemini-enhanced extraction pipeline.

    Args:
        pdf_path: Path to original PDF
        heuristic_schema_path: Path to heuristic schema JSON
        output_path: Path to save enhanced schema
        skip_annotation: If True, skip PDF annotation step (use existing)
    """
    print("=" * 70)
    print("GEMINI-ENHANCED SCHEMA EXTRACTION TEST")
    print("=" * 70)

    pdf_path = Path(pdf_path)
    heuristic_schema_path = Path(heuristic_schema_path)
    output_path = Path(output_path)

    # Determine annotated PDF path
    annotated_pdf_path = pdf_path.parent / f"{pdf_path.stem}_annotated.pdf"

    # Step 1: Load heuristic schema
    print(f"\n[Step 1] Loading heuristic schema...")
    print(f"   Path: {heuristic_schema_path}")

    heuristic_schema = load_heuristic_schema(str(heuristic_schema_path))
    print(f"   OK: Loaded {len(heuristic_schema.fields)} fields")

    # Step 2: Create annotated PDF (if needed)
    if not skip_annotation or not annotated_pdf_path.exists():
        print(f"\n[Step 2] Creating annotated PDF...")
        print(f"   Input: {pdf_path}")
        print(f"   Output: {annotated_pdf_path}")

        # Extract widgets for annotation
        widgets = extract_widget_inventory(str(pdf_path))

        # Create annotated PDF
        annotate_pdf_with_field_names(
            str(pdf_path),
            widgets,
            str(annotated_pdf_path)
        )
        print(f"   OK: Annotated PDF created")
    else:
        print(f"\n[Step 2] Using existing annotated PDF")
        print(f"   Path: {annotated_pdf_path}")

    # Step 3: Build simplified field list
    print(f"\n[Step 3] Building simplified field list...")
    simplified_fields = build_simplified_fields(heuristic_schema)
    form_metadata = extract_form_metadata(heuristic_schema)

    print(f"   OK: {len(simplified_fields)} fields prepared")
    print(f"   Form: {form_metadata['form_number']} - {form_metadata['title']}")

    # Step 4: Call Gemini for enhancements
    print(f"\n[Step 4] Calling Gemini API for enhancements...")

    enhancer = GeminiEnhancer()
    gemini_enhancement = enhancer.enhance_schema(
        str(annotated_pdf_path),
        simplified_fields,
        form_metadata
    )

    # Step 5: Merge schemas
    print(f"\n[Step 5] Merging heuristic + Gemini...")

    try:
        final_schema = merge_schemas(heuristic_schema, gemini_enhancement)
        print(f"   OK: Merge successful!")
    except ValueError as e:
        print(f"   ERROR: Merge failed: {e}")
        sys.exit(1)

    # Step 6: Save enhanced schema
    print(f"\n[Step 6] Saving enhanced schema...")
    print(f"   Output: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(
            final_schema.model_dump(exclude_none=True),
            f,
            indent=2,
            ensure_ascii=False
        )

    print(f"   OK: Schema saved")

    # Step 7: Final summary
    print(f"\n" + "=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)
    print(f"Total API cost: ${enhancer.total_cost:.4f}")
    print(f"Final schema: {len(final_schema.fields)} fields")

    # Count enhancements
    fields_with_spoken_names = sum(1 for f in final_schema.fields if f.spoken_name)
    fields_with_help = sum(1 for f in final_schema.fields if f.help)
    fields_with_validation = sum(1 for f in final_schema.fields if f.validation)

    print(f"\nEnhancements:")
    print(f"  Spoken names: {fields_with_spoken_names}/{len(final_schema.fields)}")
    print(f"  Help text: {fields_with_help}/{len(final_schema.fields)}")
    print(f"  Validation: {fields_with_validation}/{len(final_schema.fields)}")
    print(f"\nEnhanced schema ready for human review in schema-editor!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Gemini-enhanced extraction pipeline")
    parser.add_argument("pdf", help="Path to PDF file")
    parser.add_argument("schema", help="Path to heuristic schema JSON")
    parser.add_argument("-o", "--output", required=True, help="Output path for enhanced schema")
    parser.add_argument("--skip-annotation", action="store_true", help="Skip PDF annotation (use existing)")

    args = parser.parse_args()

    test_extraction_pipeline(
        args.pdf,
        args.schema,
        args.output,
        args.skip_annotation
    )
