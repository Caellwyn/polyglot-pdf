"""
Test script for Gemini V2 schema extraction with batching.

Usage:
    python test_gemini_extraction_v2.py <pdf_path> <schema_path> -o <output_path> [options]

Options:
    --skip-annotation       Skip PDF annotation step (use existing annotated PDF)
    --skip-groupings        Skip groupings enhancement
    --skip-conditionals     Skip conditionals enhancement
    --batch-size N          Fields per batch (default: 50)
    --min-confidence N      Minimum confidence threshold (default: 0.7)
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List

from form_models import FormSchema
from pdf_annotator import annotate_pdf_with_field_names
from gemini_enhancer_v2 import GeminiEnhancerV2
from schema_merger_v2 import SchemaMergerV2


def load_heuristic_schema(schema_path: str) -> FormSchema:
    """Load heuristic extraction schema."""
    with open(schema_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return FormSchema(**data)


def build_simplified_fields(schema: FormSchema) -> List[Dict[str, Any]]:
    """Build simplified field list for Gemini API."""
    fields = []
    for field in schema.fields:
        # Extract position if it exists
        position = None
        if field.pdf_position:
            position = {
                "page": field.pdf_position.page,
                "x": round(field.pdf_position.x, 2),
                "y": round(field.pdf_position.y, 2)
            }

        fields.append({
            "field_id": field.id,
            "name": field.name,
            "field_type": str(field.type),
            "position": position
        })
    return fields


def extract_form_metadata(schema: FormSchema) -> Dict[str, Any]:
    """Extract form metadata."""
    if schema.form_metadata:
        return {
            "form_title": schema.form_metadata.title or "Unknown Form",
            "form_number": schema.form_metadata.form_number or "",
            "total_pages": schema.form_metadata.page_count or 0
        }
    else:
        return {
            "form_title": "Unknown Form",
            "form_number": "",
            "total_pages": 0
        }


def annotate_pdf(pdf_path: str, schema: FormSchema) -> str:
    """Annotate PDF with field IDs and return path to annotated PDF."""
    print("\n[ANNOTATE] Creating annotated PDF with field IDs...")

    output_path = pdf_path.replace('.pdf', '_annotated.pdf')

    # Use the function from pdf_annotator
    annotated_path = annotate_pdf_with_field_names(pdf_path, output_path)

    print(f"[OK] Annotated PDF: {annotated_path}")

    return annotated_path


def calculate_cost(
    spoken_name_batches: int,
    groupings_call: bool,
    conditional_batches: int
) -> float:
    """
    Estimate API cost.

    Rough estimates based on I-90 testing:
    - Spoken names batch: ~$0.0005
    - Groupings call: ~$0.0002
    - Conditionals batch: ~$0.0003
    """
    cost = 0.0
    cost += spoken_name_batches * 0.0005
    if groupings_call:
        cost += 0.0002
    cost += conditional_batches * 0.0003
    return cost


def main():
    parser = argparse.ArgumentParser(
        description="Test Gemini V2 schema extraction with batching"
    )
    parser.add_argument("pdf_path", help="Path to PDF file")
    parser.add_argument("schema_path", help="Path to heuristic schema JSON")
    parser.add_argument("-o", "--output", required=True, help="Output path for enhanced schema")
    parser.add_argument("--skip-annotation", action="store_true", help="Skip PDF annotation")
    parser.add_argument("--skip-groupings", action="store_true", help="Skip groupings enhancement")
    parser.add_argument("--skip-conditionals", action="store_true", help="Skip conditionals enhancement")
    parser.add_argument("--batch-size", type=int, default=50, help="Fields per batch (default: 50)")
    parser.add_argument("--min-confidence", type=float, default=0.7, help="Minimum confidence (default: 0.7)")

    args = parser.parse_args()

    # Validate paths
    pdf_path = Path(args.pdf_path)
    schema_path = Path(args.schema_path)

    if not pdf_path.exists():
        print(f"[ERROR] PDF not found: {pdf_path}")
        sys.exit(1)

    if not schema_path.exists():
        print(f"[ERROR] Schema not found: {schema_path}")
        sys.exit(1)

    print("=" * 70)
    print("GEMINI V2 SCHEMA EXTRACTION TEST")
    print("=" * 70)

    # Load heuristic schema
    print(f"\n[LOAD] Loading heuristic schema: {schema_path}")
    schema = load_heuristic_schema(str(schema_path))
    print(f"[OK] Loaded {len(schema.fields)} fields")

    # Build simplified fields and metadata
    simplified_fields = build_simplified_fields(schema)
    form_metadata = extract_form_metadata(schema)

    # Annotate PDF (if needed)
    if args.skip_annotation:
        annotated_pdf_path = str(pdf_path).replace('.pdf', '_annotated.pdf')
        if not Path(annotated_pdf_path).exists():
            print(f"[ERROR] Annotated PDF not found: {annotated_pdf_path}")
            print("[ERROR] Run without --skip-annotation first to create it")
            sys.exit(1)
        print(f"[SKIP] Using existing annotated PDF: {annotated_pdf_path}")
    else:
        annotated_pdf_path = annotate_pdf(str(pdf_path), schema)

    # Initialize enhancer
    print("\n[INIT] Initializing Gemini V2 enhancer...")
    enhancer = GeminiEnhancerV2()

    # Track API calls for cost calculation
    spoken_name_batches = 0
    groupings_call = False
    conditional_batches = 0

    # Enhance spoken names (always)
    print("\n" + "=" * 70)
    print("STEP 1: SPOKEN NAMES + HELP TEXT")
    print("=" * 70)

    spoken_names_responses = enhancer.enhance_spoken_names(
        annotated_pdf_path,
        simplified_fields,
        form_metadata
    )
    spoken_name_batches = len(spoken_names_responses)

    # Enhance groupings (optional)
    if args.skip_groupings:
        print("\n[SKIP] Skipping groupings enhancement")
        groupings_response = None
    else:
        print("\n" + "=" * 70)
        print("STEP 2: WIDGET GROUPINGS")
        print("=" * 70)

        groupings_response = enhancer.enhance_groupings(
            annotated_pdf_path,
            simplified_fields,
            form_metadata
        )
        groupings_call = True

    # Enhance conditionals (optional)
    if args.skip_conditionals:
        print("\n[SKIP] Skipping conditionals enhancement")
        conditionals_responses = None
    else:
        print("\n" + "=" * 70)
        print("STEP 3: CONDITIONAL RULES")
        print("=" * 70)

        conditionals_responses = enhancer.enhance_conditionals(
            annotated_pdf_path,
            simplified_fields,
            form_metadata
        )
        conditional_batches = len(conditionals_responses)

    # Merge enhancements
    print("\n" + "=" * 70)
    print("MERGING ENHANCEMENTS")
    print("=" * 70)

    merger = SchemaMergerV2(schema)

    # Apply spoken names
    spoken_count = merger.apply_spoken_names(spoken_names_responses, args.min_confidence)
    print(f"[OK] Applied {spoken_count} spoken names")

    # Apply groupings
    if groupings_response:
        groups_count = merger.apply_groupings(groupings_response, args.min_confidence)
        print(f"[OK] Applied {groups_count} widget groups")

    # Apply conditionals
    if conditionals_responses:
        conditionals_count = merger.apply_conditionals(conditionals_responses, args.min_confidence)
        print(f"[OK] Applied {conditionals_count} conditional rules")

    # Get enhanced schema
    enhanced_schema = merger.get_enhanced_schema()

    # Save output
    print(f"\n[SAVE] Writing enhanced schema: {args.output}")
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(enhanced_schema.model_dump(), f, indent=2)

    # Print statistics
    print("\n" + "=" * 70)
    print("ENHANCEMENT STATISTICS")
    print("=" * 70)

    stats = merger.get_enhancement_stats()
    print(f"Total fields:              {stats['total_fields']}")
    print(f"Fields with spoken names:  {stats['fields_with_spoken_names']}")
    print(f"Unique spoken names:       {stats['unique_spoken_names']}")
    print(f"Fields with help text:     {stats['fields_with_help_text']}")
    print(f"Fields with groups:        {stats['fields_with_groups']}")
    print(f"Fields with conditionals:  {stats['fields_with_conditionals']}")

    # Cost estimate
    print("\n" + "=" * 70)
    print("API USAGE")
    print("=" * 70)

    print(f"Spoken name batches:       {spoken_name_batches}")
    print(f"Groupings call:            {'Yes' if groupings_call else 'No'}")
    print(f"Conditional batches:       {conditional_batches}")

    estimated_cost = calculate_cost(spoken_name_batches, groupings_call, conditional_batches)
    print(f"\nEstimated cost:            ${estimated_cost:.4f}")

    print("\n" + "=" * 70)
    print("SUCCESS!")
    print("=" * 70)


if __name__ == "__main__":
    main()
