#!/usr/bin/env python3
"""
Test Gemini field type enhancement with sample fields.
"""

from pdf_schema_extractor.models import FormField, FieldType, PDFPosition
from pdf_schema_extractor.gemini_enhancer import GeminiEnhancer

def test_field_type_inference():
    """Test Gemini's ability to infer field types from labels."""

    # Create sample fields that need type correction
    sample_fields = [
        FormField(
            id="dob",
            name="Date of Birth (mm/dd/yyyy)",
            spoken_name="date of birth",
            type=FieldType.TEXT,  # Wrong - should be DATE
            section_id="part_a_i",
            pdf_field_name="PtAILine1_DOB[0]",
            pdf_position=PDFPosition(page=1, x=100, y=200, width=120, height=15)
        ),
        FormField(
            id="email",
            name="Email Address",
            spoken_name="email address",
            type=FieldType.TEXT,  # Wrong - should be EMAIL
            section_id="part_a_i",
            pdf_field_name="PtAILine2_Email[0]",
            pdf_position=PDFPosition(page=1, x=100, y=220, width=200, height=15)
        ),
        FormField(
            id="phone",
            name="Telephone Number",
            spoken_name="telephone number",
            type=FieldType.TEXT,  # Wrong - should be TEL
            section_id="part_a_i",
            pdf_field_name="PtAILine3_Phone[0]",
            pdf_position=PDFPosition(page=1, x=100, y=240, width=150, height=15)
        ),
        FormField(
            id="explanation",
            name="Explain your reasons for seeking asylum",
            spoken_name="explain your reasons",
            type=FieldType.TEXT,  # Wrong - should be TEXTAREA
            section_id="part_b",
            pdf_field_name="PtB_Explanation[0]",
            pdf_position=PDFPosition(page=2, x=50, y=100, width=500, height=200)
        ),
        FormField(
            id="a_number",
            name="A-Number (if any)",
            spoken_name="a number",
            type=FieldType.TEXT,  # Could be NUMBER
            section_id="part_a_i",
            pdf_field_name="PtAILine4_ANumber[0]",
            pdf_position=PDFPosition(page=1, x=100, y=260, width=100, height=15)
        ),
    ]

    print("=" * 60)
    print("Testing Gemini Field Type Inference")
    print("=" * 60)
    print()

    print("Original field types:")
    for field in sample_fields:
        print(f"  {field.id}: {field.type.value}")
    print()

    try:
        enhancer = GeminiEnhancer()
        print("Calling Gemini API...")
        enhanced_fields = enhancer.infer_field_types(sample_fields)
        print()

        print("Enhanced field types:")
        correct = 0
        total = 0
        for original, enhanced in zip(sample_fields, enhanced_fields):
            changed = "✓" if enhanced.type != original.type else " "
            print(f"  {changed} {enhanced.id}: {enhanced.type.value}")

            # Check if corrections match expectations
            if enhanced.id == "dob" and enhanced.type == FieldType.DATE:
                correct += 1
            elif enhanced.id == "email" and enhanced.type == FieldType.EMAIL:
                correct += 1
            elif enhanced.id == "phone" and enhanced.type == FieldType.TEL:
                correct += 1
            elif enhanced.id == "explanation" and enhanced.type == FieldType.TEXTAREA:
                correct += 1

            total += 1

        print()
        print("=" * 60)
        print(f"✓ Test completed successfully!")
        print(f"  Correct type inferences: {correct}/{total}")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_field_type_inference()
