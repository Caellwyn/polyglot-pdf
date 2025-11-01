#!/usr/bin/env python3
"""
Integrated Conditional Unlock Flow Test

Tests the complete flow:
1. Unlock conditional fields using mutator
2. Fill ALL fields (including unlocked ones) using round-trip tester
3. Verify all fields round-trip correctly

This validates that the conditional behavior system works end-to-end.
"""

import sys
from pathlib import Path
from pdf_field_flag_mutator import create_unlocked_pdf, verify_unlock
from round_trip_tester import RoundTripTester


def test_conditional_unlock_flow(
    source_pdf: str,
    schema_json: str,
    unlocked_pdf: str = None,
    filled_pdf: str = None
):
    """
    Run complete conditional unlock flow test.

    Args:
        source_pdf: Original PDF with locked conditional fields
        schema_json: Schema with conditional_behavior metadata
        unlocked_pdf: Output path for unlocked PDF (optional)
        filled_pdf: Output path for filled PDF (optional)
    """
    print("=" * 70)
    print("INTEGRATED CONDITIONAL UNLOCK FLOW TEST")
    print("=" * 70)
    print(f"\nSource PDF: {source_pdf}")
    print(f"Schema: {schema_json}")

    # Generate output paths if not provided
    if not unlocked_pdf:
        unlocked_pdf = source_pdf.replace('.pdf', '_unlocked_for_test.pdf')
    if not filled_pdf:
        filled_pdf = source_pdf.replace('.pdf', '_filled_unlocked_test.pdf')

    # STEP 1: Unlock conditional fields
    print("\n" + "=" * 70)
    print("STEP 1: UNLOCKING CONDITIONAL FIELDS")
    print("=" * 70)

    unlock_stats = create_unlocked_pdf(source_pdf, schema_json, unlocked_pdf)

    if unlock_stats['fields_unlocked'] == 0:
        print("\n[WARNING] No fields were unlocked!")
        print("This may indicate:")
        print("  - Schema doesn't have conditional_behavior metadata")
        print("  - No read-only conditional fields in schema")
        print("  - Field name mismatch")
        print("\nContinuing with round-trip test anyway...")

    # STEP 2: Run round-trip test on UNLOCKED PDF
    print("\n" + "=" * 70)
    print("STEP 2: ROUND-TRIP TEST ON UNLOCKED PDF")
    print("=" * 70)

    tester = RoundTripTester(unlocked_pdf, schema_json)
    results = tester.run_full_test(filled_pdf)

    # STEP 3: Summary
    print("\n" + "=" * 70)
    print("INTEGRATED TEST SUMMARY")
    print("=" * 70)

    print("\n[STEP 1 - UNLOCKING]")
    print(f"  Fields unlocked: {unlock_stats['fields_unlocked']}/{unlock_stats['total_unlock_requests']}")
    if unlock_stats['fields_not_found'] > 0:
        print(f"  Fields not found: {unlock_stats['fields_not_found']}")

    print("\n[STEP 2 - ROUND-TRIP]")
    print(f"  Fields filled: {results['successful_fills']}/{results['successful_fills'] + results['failed_fills']}")
    print(f"  Verification matches: {results['verification']['matches']}/{results['verification']['total']}")
    print(f"  Success rate: {results['verification']['success_rate']:.1f}%")

    print("\n[OVERALL ASSESSMENT]")

    # Calculate expected fillable fields
    # Unlocked fields should now be fillable
    expected_fillable = results['successful_fills']
    actual_matches = results['verification']['matches']

    if results['verification']['success_rate'] == 100.0:
        print("  [PASSED] All fields (including unlocked) round-tripped correctly!")
    elif results['verification']['success_rate'] >= 95.0:
        print("  [WARNING] MOSTLY PASSED - Minor issues detected")
    else:
        print("  [FAILED] Significant issues detected")

    # Specific assessment for unlocked fields
    if unlock_stats['fields_unlocked'] > 0:
        print(f"\n[CONDITIONAL UNLOCK VALIDATION]")
        print(f"  Fields unlocked by mutator: {unlock_stats['fields_unlocked']}")
        print(f"  Total fields filled: {results['successful_fills']}")

        # Check if we filled more fields than in the original test
        # (This would indicate unlocked fields are now fillable)
        print(f"\n  NOTE: Compare this to the original round-trip test")
        print(f"        to see if unlocked fields were successfully filled.")

    print("\n" + "=" * 70)
    print("FILES GENERATED")
    print("=" * 70)
    print(f"  Unlocked PDF: {unlocked_pdf}")
    print(f"  Filled PDF: {filled_pdf}")

    return {
        'unlock_stats': unlock_stats,
        'round_trip_results': results
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_conditional_unlock_flow.py <pdf> <schema> [unlocked_pdf] [filled_pdf]")
        print("\nExample:")
        print("  python test_conditional_unlock_flow.py \\")
        print("    test_schemas/test_pdfs/i-90/i-90.pdf \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v9_conformant.json")
        sys.exit(1)

    source_pdf = sys.argv[1]
    schema_json = sys.argv[2]
    unlocked_pdf = sys.argv[3] if len(sys.argv) > 3 else None
    filled_pdf = sys.argv[4] if len(sys.argv) > 4 else None

    results = test_conditional_unlock_flow(source_pdf, schema_json, unlocked_pdf, filled_pdf)
