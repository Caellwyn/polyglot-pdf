#!/usr/bin/env python3
"""
Round-Trip Tester - Verify schema can fill PDF and extract back correctly.

Tests the complete workflow:
1. Load schema
2. Fill PDF with test data
3. Verify fields populated correctly
4. Compare input vs. output values
"""

import fitz
import json
import sys
from typing import Dict, Any, List, Tuple
from pathlib import Path


class RoundTripTester:
    """Test schema -> PDF -> verification workflow."""

    def __init__(self, pdf_path: str, schema_path: str):
        self.pdf_path = pdf_path
        self.schema_path = schema_path
        self.schema = None
        self.fields_by_pdf_name = {}

    def load_schema(self):
        """Load schema and index by pdf_field_name."""
        print(f"\n{'='*70}")
        print("LOADING SCHEMA")
        print(f"{'='*70}")

        with open(self.schema_path, 'r', encoding='utf-8') as f:
            self.schema = json.load(f)

        # Index fields by pdf_field_name for quick lookup
        for field in self.schema.get('fields', []):
            pdf_name = field.get('pdf_field_name')
            if pdf_name:
                self.fields_by_pdf_name[pdf_name] = field

            # Also index consolidated_widgets for groups
            for widget_name in field.get('consolidated_widgets', []):
                if widget_name not in self.fields_by_pdf_name:
                    self.fields_by_pdf_name[widget_name] = field

        print(f"  Loaded {len(self.schema.get('fields', []))} fields")
        print(f"  Indexed {len(self.fields_by_pdf_name)} PDF field mappings")

    def generate_test_data(self) -> Dict[str, Any]:
        """Generate test data for all fillable fields with validation support."""
        print(f"\n{'='*70}")
        print("GENERATING TEST DATA")
        print(f"{'='*70}")

        test_data = {}

        for field in self.schema.get('fields', []):
            # Skip read-only fields (they're pre-populated)
            if field.get('read_only'):
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
            if val_type == 'phone_number':
                test_data[pdf_name] = "(555) 123-4567"
            elif val_type == 'zip_code':
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

        # Show sample test data keys
        sample_keys = list(test_data.keys())[:5]
        if sample_keys:
            print(f"\n  Sample test data keys:")
            for key in sample_keys:
                print(f"    - {key}")

        return test_data

    def fill_pdf(self, test_data: Dict[str, Any], output_path: str) -> Tuple[int, int]:
        """
        Fill PDF with test data.

        Returns:
            (successful_fills, failed_fills)
        """
        print(f"\n{'='*70}")
        print("FILLING PDF")
        print(f"{'='*70}")

        doc = fitz.open(self.pdf_path)
        successful = 0
        failed = 0
        failed_fields = []
        not_in_test_data = []

        for page in doc:
            for widget in page.widgets():
                if not widget.field_name:
                    continue

                field_value = test_data.get(widget.field_name)

                if field_value is None:
                    # Try to find by short name
                    short_name = widget.field_name.split('.')[-1]
                    field_value = test_data.get(short_name)

                if field_value is not None:
                    try:
                        # Handle different field types
                        if widget.field_type == 2:  # Checkbox
                            widget.field_value = field_value
                        elif widget.field_type == 3:  # Radio
                            widget.field_value = field_value
                        elif widget.field_type == 4:  # Select/Dropdown
                            widget.field_value = str(field_value)
                        elif widget.field_type == 6:  # Listbox
                            widget.field_value = str(field_value)
                        elif widget.field_type in [1, 7]:  # Text or signature
                            widget.field_value = str(field_value)
                        else:
                            widget.field_value = field_value

                        widget.update()
                        successful += 1
                    except Exception as e:
                        failed += 1
                        failed_fields.append((widget.field_name, str(e)))
                else:
                    # Track fields not in test data (first 5 only)
                    if len(not_in_test_data) < 5:
                        not_in_test_data.append(widget.field_name)

        # Save filled PDF
        doc.save(output_path, garbage=4, deflate=True)
        doc.close()

        print(f"  Successfully filled: {successful} fields")
        print(f"  Failed to fill: {failed} fields")

        if not_in_test_data:
            print(f"\n  Sample PDF widget names not in test data:")
            for name in not_in_test_data:
                short_name = name.split('.')[-1]
                print(f"    Full: {name}")
                print(f"    Short: {short_name}")
                print(f"    In test_data? {name in test_data or short_name in test_data}")

        if failed_fields:
            print(f"\n  Failed fields:")
            for field_name, error in failed_fields[:10]:  # Show first 10
                print(f"    - {field_name}: {error}")
            if len(failed_fields) > 10:
                print(f"    ... and {len(failed_fields) - 10} more")

        print(f"\n  Saved to: {output_path}")

        return successful, failed

    def verify_filled_pdf(self, filled_pdf_path: str, original_test_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verify the filled PDF by reading it back and comparing values.

        Returns:
            Dictionary with verification results
        """
        print(f"\n{'='*70}")
        print("VERIFYING FILLED PDF")
        print(f"{'='*70}")

        doc = fitz.open(filled_pdf_path)

        matches = 0
        mismatches = 0
        missing = 0

        mismatch_details = []

        for page in doc:
            for widget in page.widgets():
                if not widget.field_name:
                    continue

                # Try full name first, then short name (same logic as filling)
                expected_value = original_test_data.get(widget.field_name)
                if expected_value is None:
                    short_name = widget.field_name.split('.')[-1]
                    expected_value = original_test_data.get(short_name)

                if expected_value is None:
                    continue  # Field wasn't in test data

                actual_value = widget.field_value

                # Normalize for comparison
                if widget.field_type in [1, 4, 6, 7]:  # Text, Select, Listbox, Signature
                    expected_str = str(expected_value)
                    actual_str = str(actual_value) if actual_value else ""

                    if expected_str == actual_str:
                        matches += 1
                    else:
                        mismatches += 1
                        mismatch_details.append({
                            'field_name': widget.field_name,
                            'expected': expected_str,
                            'actual': actual_str
                        })

                elif widget.field_type in [2, 3]:  # Checkbox/Radio
                    # Check if checked
                    is_checked = actual_value not in [None, False, 0, '', 'Off']
                    expected_checked = bool(expected_value)

                    if is_checked == expected_checked:
                        matches += 1
                    else:
                        mismatches += 1
                        mismatch_details.append({
                            'field_name': widget.field_name,
                            'expected': expected_checked,
                            'actual': is_checked
                        })

        doc.close()

        total = matches + mismatches
        success_rate = (matches / total * 100) if total > 0 else 0

        print(f"  Total verified: {total}")
        print(f"  Matches: {matches}")
        print(f"  Mismatches: {mismatches}")
        print(f"  Success rate: {success_rate:.1f}%")

        if mismatch_details:
            print(f"\n  Mismatches (showing first 10):")
            for detail in mismatch_details[:10]:
                print(f"    - {detail['field_name']}")
                print(f"      Expected: {detail['expected']}")
                print(f"      Actual:   {detail['actual']}")
            if len(mismatch_details) > 10:
                print(f"    ... and {len(mismatch_details) - 10} more")

        return {
            'total': total,
            'matches': matches,
            'mismatches': mismatches,
            'success_rate': success_rate,
            'mismatch_details': mismatch_details
        }

    def run_full_test(self, output_pdf_path: str = None) -> Dict[str, Any]:
        """
        Run complete round-trip test.

        Returns:
            Dictionary with all test results
        """
        if not output_pdf_path:
            pdf_stem = Path(self.pdf_path).stem
            output_pdf_path = f"{pdf_stem}_filled_test.pdf"

        # 1. Load schema
        self.load_schema()

        # 2. Generate test data
        test_data = self.generate_test_data()

        # 3. Fill PDF
        successful_fills, failed_fills = self.fill_pdf(test_data, output_pdf_path)

        # 4. Verify filled PDF
        verification = self.verify_filled_pdf(output_pdf_path, test_data)

        # Summary
        print(f"\n{'='*70}")
        print("ROUND-TRIP TEST COMPLETE")
        print(f"{'='*70}")
        print(f"Schema: {self.schema_path}")
        print(f"Source PDF: {self.pdf_path}")
        print(f"Filled PDF: {output_pdf_path}")
        print(f"\nResults:")
        print(f"  Fields filled: {successful_fills}/{successful_fills + failed_fills}")
        print(f"  Verification matches: {verification['matches']}/{verification['total']}")
        print(f"  Success rate: {verification['success_rate']:.1f}%")

        if verification['success_rate'] == 100.0:
            print(f"\n[PASSED] All fields round-tripped correctly!")
        elif verification['success_rate'] >= 95.0:
            print(f"\n[WARNING] MOSTLY PASSED - Minor issues detected")
        else:
            print(f"\n[FAILED] Significant issues detected")

        return {
            'filled_pdf': output_pdf_path,
            'successful_fills': successful_fills,
            'failed_fills': failed_fills,
            'verification': verification
        }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python round_trip_tester.py <pdf_path> <schema_json> [output_pdf]")
        print("\nExample:")
        print("  python round_trip_tester.py test_schemas/test_pdfs/i-90/i-90.pdf test_schemas/test_pdfs/i-90/i-90_schema_final_complete.json")
        sys.exit(1)

    pdf_path = sys.argv[1]
    schema_path = sys.argv[2]
    output_pdf = sys.argv[3] if len(sys.argv) > 3 else None

    tester = RoundTripTester(pdf_path, schema_path)
    results = tester.run_full_test(output_pdf)
