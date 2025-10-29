#!/usr/bin/env python3
"""
Test the form-agnostic Gemini extractor on i-589.pdf
Compare results with ground truth.
"""

import json
from pathlib import Path
from dotenv import load_dotenv
from pdf_schema_extractor.gemini_extractor import extract_form_schema

# Load from the correct .env file and override OS environment
load_dotenv(Path(__file__).parent / '.env', override=True)

if __name__ == "__main__":
    # Paths
    base_dir = Path(__file__).parent
    pdf_path = base_dir / "test_schemas" / "test_pdfs" / "i-589.pdf"
    ground_truth_path = base_dir / "test_schemas" / "test_pdfs" / "i589_schema.json"
    output_dir = base_dir / "gemini_extraction_output"

    # Load ground truth
    with open(ground_truth_path) as f:
        ground_truth = json.load(f)

    print(f"Ground Truth:")
    print(f"  Total fields: {len(ground_truth['fields'])}")
    print(f"  Sections: {len(ground_truth['sections'])}")

    # Extract with Gemini
    print(f"\nExtracting with form-agnostic Gemini pipeline...")
    gemini_schema = extract_form_schema(str(pdf_path), output_dir=str(output_dir))

    # Compare results
    print(f"\n{'='*60}")
    print(f"COMPARISON: Gemini vs Ground Truth")
    print(f"{'='*60}")

    print(f"\nField Count:")
    print(f"  Gemini:        {gemini_schema['total_fields']}")
    print(f"  Ground Truth:  {len(ground_truth['fields'])}")
    print(f"  Difference:    {gemini_schema['total_fields'] - len(ground_truth['fields']):+d}")

    # Compare field types
    print(f"\nField Type Distribution:")
    gt_types = {}
    for f in ground_truth['fields']:
        gt_types[f['type']] = gt_types.get(f['type'], 0) + 1

    gemini_types = gemini_schema.get('field_type_summary', {})

    all_types = sorted(set(list(gemini_types.keys()) + list(gt_types.keys())))

    print(f"  {'Type':<12} {'Gemini':>8} {'Target':>8} {'Diff':>6}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*6}")
    for ftype in all_types:
        gemini_count = gemini_types.get(ftype, 0)
        gt_count = gt_types.get(ftype, 0)
        diff = gemini_count - gt_count
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        print(f"  {ftype:<12} {gemini_count:>8} {gt_count:>8} {diff_str:>6}")

    # Calculate accuracy metrics
    print(f"\n{'='*60}")
    print(f"ACCURACY METRICS")
    print(f"{'='*60}")

    field_count_accuracy = 1 - abs(gemini_schema['total_fields'] - len(ground_truth['fields'])) / len(ground_truth['fields'])
    print(f"Field count accuracy: {field_count_accuracy * 100:.1f}%")

    type_accuracies = []
    for ftype in all_types:
        gemini_count = gemini_types.get(ftype, 0)
        gt_count = gt_types.get(ftype, 0)
        if gt_count > 0:
            accuracy = 1 - abs(gemini_count - gt_count) / gt_count
            type_accuracies.append(max(0, accuracy))

    if type_accuracies:
        avg_type_accuracy = sum(type_accuracies) / len(type_accuracies)
        print(f"Type distribution accuracy: {avg_type_accuracy * 100:.1f}%")

    # Overall score
    overall_score = (field_count_accuracy + avg_type_accuracy) / 2
    print(f"\nOverall score: {overall_score * 100:.1f}%")

    print(f"\n{'='*60}")
    print(f"Full extraction saved to: {output_dir}/gemini_extracted_schema.json")
    print(f"{'='*60}\n")
