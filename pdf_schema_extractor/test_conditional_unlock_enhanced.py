#!/usr/bin/env python3
"""
Enhanced Conditional Unlock Flow Test

Tests complete conditional logic flow with test data for UNLOCKED fields:
1. Unlock conditional fields using mutator
2. Generate test data for ALL fields (including unlocked ones)
3. Fill ALL fields using round-trip tester
4. Verify complete success

This fully validates the conditional unlock system.
"""

import sys
import json
from pathlib import Path
from pdf_field_flag_mutator import create_unlocked_pdf
from round_trip_tester import RoundTripTester


class EnhancedRoundTripTester(RoundTripTester):
    """Enhanced tester that includes unlocked fields."""

    def __init__(self, pdf_path: str, schema_path: str, unlocked_field_ids: list = None):
        super().__init__(pdf_path, schema_path)
        self.unlocked_field_ids = set(unlocked_field_ids or [])

    def generate_test_data(self):
        """Generate test data including for unlocked fields."""
        print(f"\n{'='*70}")
        print("GENERATING TEST DATA (INCLUDING UNLOCKED FIELDS)")
        print(f"{'='*70}")

        test_data = {}

        for field in self.schema.get('fields', []):
            field_id = field.get('id')

            # Skip read-only fields UNLESS they were unlocked
            is_read_only = field.get('read_only', False)
            is_unlocked = field_id in self.unlocked_field_ids

            if is_read_only and not is_unlocked:
                continue

            field_type = field.get('type')
            pdf_name = field.get('pdf_field_name')

            if not pdf_name:
                # For groups, use first consolidated widget
                consolidated = field.get('consolidated_widgets', [])
                if consolidated:
                    pdf_name = consolidated[0]
                else:
                    continue

            # Check for validation rules
            validation = field.get('validation') or {}
            # Support both old 'type' and new 'format_preset' keys
            val_type = validation.get('format_preset') or validation.get('type')
            exact_length = validation.get('exact_length') or (
                validation.get('min_length') if validation.get('min_length') == validation.get('max_length') else None
            )

            # Generate value based on validation rules first
            if val_type == 'phone' or val_type == 'phone_number':
                test_data[pdf_name] = "(555) 123-4567"
            elif val_type == 'zip' or val_type == 'zip_code':
                test_data[pdf_name] = "90210"
            elif val_type == 'postal_code':
                test_data[pdf_name] = "ABC123"
            elif val_type == 'ssn':
                test_data[pdf_name] = "123456789"
            elif val_type == 'a_number':
                max_len = field.get('max_length', 9)
                test_data[pdf_name] = '1' * min(max_len, 9)
            elif val_type == 'receipt_number' or val_type == 'uscis_account':
                # EXACTLY 12 characters/digits
                length = exact_length or 12
                test_data[pdf_name] = '1' * length
            elif val_type == 'date':
                test_data[pdf_name] = "01/01/2000"

            # Fall back to field type
            elif field_type == 'date':
                test_data[pdf_name] = "01/01/2000"

            elif field_type == 'select':
                # Use first option from field options
                options = field.get('options', [])
                if options:
                    test_data[pdf_name] = options[0].get('value', 'OPTION1')
                else:
                    test_data[pdf_name] = "CA"  # Default for state fields

            elif field_type == 'text':
                # Check if it's a COMB field (formatted input)
                if field.get('is_comb') or exact_length:
                    max_len = exact_length or field.get('max_length', 10)
                    # Generate to exact length for COMB fields
                    test_data[pdf_name] = '1' * max_len
                else:
                    # Regular text
                    field_name = field.get('name', 'Test')
                    # Add marker for unlocked fields
                    if is_unlocked:
                        test_data[pdf_name] = f"UNLOCKED-{field_name[:15]}"
                    else:
                        test_data[pdf_name] = f"Test {field_name[:20]}"

            elif field_type == 'textarea':
                test_data[pdf_name] = "This is a test multiline value.\nLine 2.\nLine 3."

            elif field_type == 'checkbox':
                # Check first option
                options = field.get('options', [])
                if options:
                    test_data[options[0]['value']] = True

            elif field_type == 'radio':
                # Select first option in radio group
                options = field.get('options', [])
                if options:
                    test_data[options[0]['value']] = True

            elif field_type == 'signature':
                test_data[pdf_name] = "Test Signature"

        print(f"  Generated {len(test_data)} test values")
        unlocked_count = sum(1 for field in self.schema.get('fields', [])
                            if field.get('id') in self.unlocked_field_ids)
        print(f"  Includes {unlocked_count} unlocked conditional fields")

        # Show sample test data keys
        sample_keys = list(test_data.keys())[:5]
        if sample_keys:
            print(f"\n  Sample test data keys:")
            for key in sample_keys:
                print(f"    - {key}")

        return test_data


def test_enhanced_unlock_flow(
    source_pdf: str,
    schema_json: str,
    unlocked_pdf: str = None,
    filled_pdf: str = None
):
    """
    Run enhanced conditional unlock flow test.
    """
    print("=" * 70)
    print("ENHANCED CONDITIONAL UNLOCK FLOW TEST")
    print("=" * 70)
    print(f"\nSource PDF: {source_pdf}")
    print(f"Schema: {schema_json}")

    # Generate output paths if not provided
    if not unlocked_pdf:
        unlocked_pdf = source_pdf.replace('.pdf', '_unlocked_enhanced.pdf')
    if not filled_pdf:
        filled_pdf = source_pdf.replace('.pdf', '_filled_enhanced.pdf')

    # Load schema to get unlocked field IDs
    with open(schema_json, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    # STEP 1: Unlock conditional fields
    print("\n" + "=" * 70)
    print("STEP 1: UNLOCKING CONDITIONAL FIELDS")
    print("=" * 70)

    unlock_stats = create_unlocked_pdf(source_pdf, schema_json, unlocked_pdf)

    # Get list of unlocked field IDs
    unlocked_field_ids = []
    for field in schema.get('fields', []):
        # Check if field has show_if and read_only (indicates conditional field)
        if field.get('show_if') and field.get('read_only', False):
            unlocked_field_ids.append(field.get('id'))

    print(f"\nIdentified {len(unlocked_field_ids)} unlocked field IDs in schema")

    # STEP 2: Run enhanced round-trip test
    print("\n" + "=" * 70)
    print("STEP 2: ENHANCED ROUND-TRIP TEST (WITH UNLOCKED FIELDS)")
    print("=" * 70)

    tester = EnhancedRoundTripTester(unlocked_pdf, schema_json, unlocked_field_ids)
    results = tester.run_full_test(filled_pdf)

    # STEP 3: Analysis
    print("\n" + "=" * 70)
    print("ENHANCED TEST SUMMARY")
    print("=" * 70)

    print("\n[STEP 1 - UNLOCKING]")
    print(f"  Fields unlocked in PDF: {unlock_stats['fields_unlocked']}/{unlock_stats['total_unlock_requests']}")
    print(f"  Unlocked field IDs identified: {len(unlocked_field_ids)}")

    print("\n[STEP 2 - ENHANCED ROUND-TRIP]")
    print(f"  Fields filled: {results['successful_fills']}/{results['successful_fills'] + results['failed_fills']}")
    print(f"  Verification matches: {results['verification']['matches']}/{results['verification']['total']}")
    print(f"  Success rate: {results['verification']['success_rate']:.1f}%")

    # Compare to baseline
    baseline_fillable = 99  # From original test
    enhanced_fillable = results['successful_fills']
    additional_filled = enhanced_fillable - baseline_fillable

    print("\n[COMPARISON TO BASELINE]")
    print(f"  Baseline (locked PDF): {baseline_fillable} fields filled")
    print(f"  Enhanced (unlocked PDF): {enhanced_fillable} fields filled")
    print(f"  Additional fields unlocked: {additional_filled}")

    print("\n[OVERALL ASSESSMENT]")
    if results['verification']['success_rate'] == 100.0 and additional_filled > 0:
        print("  [SUCCESS] Conditional unlock system fully validated!")
        print(f"  - All {enhanced_fillable} fields round-tripped correctly")
        print(f"  - {additional_filled} additional fields unlocked and filled")
    elif results['verification']['success_rate'] == 100.0:
        print("  [PASSED] All fields round-tripped, but no additional fields unlocked")
    else:
        print("  [PARTIAL] Some fields have issues")

    print("\n" + "=" * 70)
    print("FILES GENERATED")
    print("=" * 70)
    print(f"  Unlocked PDF: {unlocked_pdf}")
    print(f"  Filled PDF: {filled_pdf}")

    return {
        'unlock_stats': unlock_stats,
        'round_trip_results': results,
        'additional_fields_unlocked': additional_filled
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_conditional_unlock_enhanced.py <pdf> <schema> [unlocked_pdf] [filled_pdf]")
        print("\nExample:")
        print("  python test_conditional_unlock_enhanced.py \\")
        print("    test_schemas/test_pdfs/i-90/i-90.pdf \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v9_conformant.json")
        sys.exit(1)

    source_pdf = sys.argv[1]
    schema_json = sys.argv[2]
    unlocked_pdf = sys.argv[3] if len(sys.argv) > 3 else None
    filled_pdf = sys.argv[4] if len(sys.argv) > 4 else None

    results = test_enhanced_unlock_flow(source_pdf, schema_json, unlocked_pdf, filled_pdf)
