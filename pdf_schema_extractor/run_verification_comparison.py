#!/usr/bin/env python3
"""
Run verification tests on both canonical and Gemini-extracted schemas.
Compare results to identify synergies between heuristic and LLM approaches.
"""

import argparse
import json
from pathlib import Path
from schema_verifier import verify_schema, VerificationReport

def print_section_header(title: str):
    """Print formatted section header."""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}")

def print_layer_details(layer_result):
    """Print detailed layer results."""
    print(f"\n  Layer: {layer_result['layer']}")
    print(f"  Status: {'PASS' if layer_result['passed'] else 'FAIL'}")
    print(f"  Score: {layer_result['score']*100:.1f}%")

    if layer_result['errors']:
        print(f"\n  Errors ({len(layer_result['errors'])}):")
        for i, error in enumerate(layer_result['errors'][:5], 1):  # Show first 5
            print(f"    {i}. {error}")
        if len(layer_result['errors']) > 5:
            print(f"    ... and {len(layer_result['errors']) - 5} more")

    if layer_result['warnings']:
        print(f"\n  Warnings ({len(layer_result['warnings'])}):")
        for i, warning in enumerate(layer_result['warnings'][:3], 1):  # Show first 3
            print(f"    {i}. {warning}")
        if len(layer_result['warnings']) > 3:
            print(f"    ... and {len(layer_result['warnings']) - 3} more")

    if layer_result['details']:
        print(f"\n  Details:")
        for key, value in layer_result['details'].items():
            if isinstance(value, (int, float)):
                print(f"    {key}: {value}")
            elif isinstance(value, list) and len(value) <= 5:
                print(f"    {key}: {value}")

def compare_reports(canonical_report_path: str, gemini_report_path: str):
    """Compare two verification reports and identify synergies."""

    with open(canonical_report_path) as f:
        canonical = json.load(f)

    with open(gemini_report_path) as f:
        gemini = json.load(f)

    print_section_header("COMPARISON: CANONICAL vs GEMINI SCHEMAS")

    # Overall comparison
    print("\nOVERALL RESULTS:")
    print(f"  Canonical: {'PASS' if canonical['overall_passed'] else 'FAIL'} "
          f"(Confidence: {canonical['confidence_score']*100:.1f}%)")
    print(f"  Gemini:    {'PASS' if gemini['overall_passed'] else 'FAIL'} "
          f"(Confidence: {gemini['confidence_score']*100:.1f}%)")

    # Layer-by-layer comparison
    print("\nLAYER-BY-LAYER COMPARISON:")
    print(f"{'Layer':<30} {'Canonical':<15} {'Gemini':<15} {'Delta':<10}")
    print(f"{'-'*70}")

    for can_layer, gem_layer in zip(canonical['layers'], gemini['layers']):
        layer_name = can_layer['layer']
        can_score = can_layer['score'] * 100
        gem_score = gem_layer['score'] * 100
        delta = gem_score - can_score

        print(f"{layer_name:<30} {can_score:>6.1f}% {'PASS' if can_layer['passed'] else 'FAIL':<8} "
              f"{gem_score:>6.1f}% {'PASS' if gem_layer['passed'] else 'FAIL':<8} "
              f"{delta:>+6.1f}%")

    # Identify synergies
    print_section_header("SYNERGY ANALYSIS")

    print("\n1. COMPLEMENTARY STRENGTHS:")
    for can_layer, gem_layer in zip(canonical['layers'], gemini['layers']):
        layer_name = can_layer['layer']
        can_score = can_layer['score']
        gem_score = gem_layer['score']

        # If one is significantly better than the other
        if abs(can_score - gem_score) > 0.15:  # 15% difference
            if can_score > gem_score:
                print(f"  - {layer_name}: Canonical stronger ({can_score*100:.1f}% vs {gem_score*100:.1f}%)")
                print(f"    Suggestion: Use canonical/heuristic approach for this aspect")
            else:
                print(f"  - {layer_name}: Gemini stronger ({gem_score*100:.1f}% vs {can_score*100:.1f}%)")
                print(f"    Suggestion: Use Gemini/LLM approach for this aspect")

    # Detailed comparison by layer
    print("\n2. DETAILED LAYER ANALYSIS:")

    for can_layer, gem_layer in zip(canonical['layers'], gemini['layers']):
        layer_name = can_layer['layer']
        print(f"\n  {layer_name}:")

        # Widget Coverage details
        if 'coverage_percent' in can_layer['details'] and 'coverage_percent' in gem_layer['details']:
            can_cov = can_layer['details']['coverage_percent']
            gem_cov = gem_layer['details']['coverage_percent']
            print(f"    Coverage: Canonical={can_cov:.1f}%, Gemini={gem_cov:.1f}%")

            # Check missing widgets
            if 'missing_widgets' in gem_layer['details']:
                missing = gem_layer['details']['missing_widgets']
                if isinstance(missing, list) and missing:
                    print(f"    Gemini missing: {len(missing)} widgets")
                elif isinstance(missing, int):
                    print(f"    Gemini missing: {missing} widgets")

            # Check hallucinated names
            if 'hallucinated_names' in gem_layer['details']:
                halluc = gem_layer['details']['hallucinated_names']
                if isinstance(halluc, list) and halluc:
                    print(f"    Gemini hallucinated: {len(halluc)} names")
                elif isinstance(halluc, int):
                    print(f"    Gemini hallucinated: {halluc} names")

        # Type compatibility
        if 'compatible_percent' in can_layer['details'] and 'compatible_percent' in gem_layer['details']:
            can_compat = can_layer['details']['compatible_percent']
            gem_compat = gem_layer['details']['compatible_percent']
            print(f"    Type compat: Canonical={can_compat:.1f}%, Gemini={gem_compat:.1f}%")

    print("\n3. HYBRID APPROACH RECOMMENDATIONS:")

    # Check widget coverage
    can_widget_layer = next((l for l in canonical['layers'] if l['layer'] == 'Widget Coverage'), None)
    gem_widget_layer = next((l for l in gemini['layers'] if l['layer'] == 'Widget Coverage'), None)

    if can_widget_layer and gem_widget_layer:
        if can_widget_layer['score'] > 0.90 and gem_widget_layer['score'] < 0.80:
            print("  - Use heuristic extraction for widget discovery")
            print("  - Use LLM for field type inference and semantic understanding")
        elif gem_widget_layer['score'] > can_widget_layer['score']:
            print("  - Gemini has better widget coverage than heuristics")
            print("  - Consider using Gemini as primary extraction method")

    # Check structural consistency
    can_struct_layer = next((l for l in canonical['layers'] if l['layer'] == 'Structural Consistency'), None)
    gem_struct_layer = next((l for l in gemini['layers'] if l['layer'] == 'Structural Consistency'), None)

    if gem_struct_layer and gem_struct_layer['score'] > 0.85:
        print("  - Gemini produces well-structured schemas")
        print("  - Consider using Gemini for grouping and table detection")

    # Overall recommendation
    can_conf = canonical['confidence_score']
    gem_conf = gemini['confidence_score']

    print(f"\n4. OVERALL RECOMMENDATION:")
    if can_conf > 0.90 and gem_conf < 0.80:
        print("  -> HEURISTIC-FIRST: Use heuristic extraction as primary, LLM for enhancement")
    elif gem_conf > 0.85 and gem_conf > can_conf:
        print("  -> LLM-FIRST: Use Gemini as primary extraction method")
    elif abs(can_conf - gem_conf) < 0.10:
        print("  -> HYBRID: Combine both approaches:")
        print("     1. Extract with both methods")
        print("     2. Use heuristic for widget discovery")
        print("     3. Use LLM for semantic typing and grouping")
        print("     4. Cross-validate and merge results")
    else:
        print("  -> INVESTIGATE: Significant gaps in both approaches")
        print("     Focus on fixing individual issues before combining")

def main():
    """Run verification comparison."""

    # Paths
    parser = argparse.ArgumentParser(description="Process PDF schema extraction")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument(
        "-c", "--canonical",
        required=True,
        help="Path to canonical schema JSON"
    )
    parser.add_argument(
        "-g", "--gemini",
        default="gemini_extraction_output/gemini_extracted_schema.json",
        help="Path for Gemini extracted schema output (default: gemini_extraction_output/gemini_extracted_schema.json)"
    )
    canonical_report_path = "verification_canonical.json"
    gemini_report_path = "verification_gemini.json"

    print_section_header("VERIFICATION TEST SUITE")
    print(f"\nPDF: {args.pdf_path}")
    print(f"Canonical Schema: {args.canonical_schema_path}")
    print(f"Gemini Schema: {args.gemini_schema_path}")



    # Verify canonical schema
    print_section_header("VERIFYING CANONICAL SCHEMA")
    canonical_report = verify_schema(args.pdf_path, args.canonical, canonical_report_path)

    # Verify Gemini schema
    print_section_header("VERIFYING GEMINI SCHEMA")
    gemini_report = verify_schema(args.pdf_path, args.gemini, gemini_report_path)

    # Compare results
    compare_reports(canonical_report_path, gemini_report_path)

    print_section_header("VERIFICATION COMPLETE")
    print(f"\nDetailed reports saved:")
    print(f"  - {canonical_report_path}")
    print(f"  - {gemini_report_path}")

if __name__ == "__main__":
    main()
