#!/usr/bin/env python3
"""
Extract Field Order from PDF Labels/Tooltips

Parses hierarchical question numbers from PDF widget tooltips to determine
the correct reading order. Government forms use numbering like:
- 1.1, 1.2, 1.3 (Part 1, questions)
- 1.3.A, 1.3.B (sub-questions)
- etc.

Usage:
    python extract_field_order_from_labels.py <pdf> <schema> <output_schema>
"""

import fitz
import json
import re
import sys
from typing import List, Dict, Tuple, Any
from pathlib import Path


def extract_question_number(tooltip: str, label: str = None) -> Tuple[List, str]:
    """
    Extract hierarchical question number from tooltip or label.

    Examples:
        "Part 1. ... 3. A. Enter..." -> ([1, 3, 'A'], "1.3.A")
        "Part 2. ... 4. Select..." -> ([2, 4], "2.4")
        "Part 3. ... 5. C. ..." -> ([3, 5, 'C'], "3.5.C")

    Returns:
        (parsed_parts, original_string)
    """
    if not tooltip and not label:
        return ([], "")

    text = tooltip or label or ""

    # Extract Part number first
    part_match = re.search(r'Part\s+(\d+)\.', text)
    if not part_match:
        return ([], "")

    part_num = int(part_match.group(1))

    # Find question numbers - patterns like "3. A." or "6. B." or just "2."
    # Look for number followed by period, optionally followed by letter and period
    # This finds patterns in the format: "X. [Y.]" where X is a number, Y is optional letter

    # Strategy: Find all "number." patterns, then check if followed by "letter."
    number_pattern = r'(\d+)\.\s+([A-Z])\.'
    letter_matches = re.findall(number_pattern, text)

    if letter_matches:
        # Found pattern like "3. A." - extract last one (most specific)
        last_match = letter_matches[-1]
        question_num = int(last_match[0])
        sub_question = last_match[1].upper()
        parts = [part_num, question_num, sub_question]
        question_str = f"{part_num}.{question_num}.{sub_question}"
    else:
        # No letter sub-question, look for just "number."
        # Find standalone numbers followed by period (not part of Part number)
        # Use negative lookbehind to avoid matching "Part 1."
        standalone_pattern = r'(?<!Part\s)(?<!Part\s\s)(\d+)\.\s+(?![A-Z]\.)'
        standalone_matches = re.findall(standalone_pattern, text)

        if standalone_matches:
            # Use the last match (most specific question number)
            question_num = int(standalone_matches[-1])
            parts = [part_num, question_num]
            question_str = f"{part_num}.{question_num}"
        else:
            # No question number found, just use part number
            parts = [part_num]
            question_str = f"{part_num}"

    return (parts, question_str)


def extract_widgets_with_labels(pdf_path: str) -> List[Dict]:
    """
    Extract all widgets from PDF with their tooltips, labels, and positions.

    Returns list of:
    {
        'name': 'P1_Line1_AlienNumber[0]',
        'tooltip': '1.1',
        'label': 'Alien Number',
        'page': 0,
        'x': 100.5,
        'y': 200.3,
        'question_parts': [1, 1],
        'question_number': '1.1'
    }
    """
    print(f"\n{'='*70}")
    print("EXTRACTING WIDGETS WITH LABELS")
    print(f"{'='*70}")

    doc = fitz.open(pdf_path)
    widgets = []

    for page_num, page in enumerate(doc):
        for widget in page.widgets():
            if not widget.field_name:
                continue

            # Get tooltip and label
            tooltip = widget.field_label or ""  # This is usually the tooltip
            label = widget.field_display or ""   # This might be the visible label

            # Get position and size from rect
            rect = widget.rect
            if rect:
                x = rect.x0
                y = rect.y0
                width = rect.x1 - rect.x0
                height = rect.y1 - rect.y0
            else:
                x = y = width = height = 0

            # Parse question number
            question_parts, question_number = extract_question_number(tooltip, label)

            widgets.append({
                'name': widget.field_name,
                'tooltip': tooltip,
                'label': label,
                'page': page_num,
                'x': x,
                'y': y,
                'width': width,
                'height': height,
                'question_parts': question_parts,
                'question_number': question_number
            })

    doc.close()

    print(f"  Extracted {len(widgets)} widgets")

    # Show sample
    print(f"\n  Sample widgets with question numbers:")
    for widget in widgets[:10]:
        if widget['question_number']:
            print(f"    {widget['question_number']:8} - {widget['name']}")

    # Count widgets with question numbers
    with_numbers = sum(1 for w in widgets if w['question_number'])
    print(f"\n  Widgets with question numbers: {with_numbers}/{len(widgets)}")

    return widgets


def sort_by_question_number(widgets: List[Dict]) -> List[Dict]:
    """
    Sort widgets by hierarchical question number.

    Sort order:
    1. Page number (0, 1, 2, ...)
    2. Question parts ([1, 1] < [1, 2] < [1, 3, 'A'] < [1, 3, 'B'])
    3. X position (left to right within same question)
    4. Y position (top to bottom)
    """
    def sort_key(widget):
        parts = widget['question_parts']
        page = widget['page']
        x = widget['x']
        y = widget['y']

        # If no question number, sort by position only (put at end)
        if not parts:
            return (999, page, x, y)

        # Pad parts to consistent length for sorting
        # Convert letters to numbers for sorting (A=100, B=101, etc.)
        padded_parts = []
        for part in parts:
            if isinstance(part, int):
                padded_parts.append(part)
            else:
                # Letter: convert to number (A=100, B=101, etc.)
                padded_parts.append(100 + ord(part) - ord('A'))

        # Pad to length 5 with zeros
        while len(padded_parts) < 5:
            padded_parts.append(0)

        return (page, *padded_parts, x, y)

    return sorted(widgets, key=sort_key)


def create_widget_to_field_map(schema: Dict) -> Dict[str, str]:
    """
    Create mapping from PDF widget name to schema field ID.

    Maps both full hierarchical names and short names.

    Returns:
        {
            'form1[0].#subform[0].P1_Line1_AlienNumber[0]': 'p1_line1_aliennumber',
            'P1_Line1_AlienNumber[0]': 'p1_line1_aliennumber',
            ...
        }
    """
    mapping = {}

    for field in schema['fields']:
        pdf_name = field.get('pdf_field_name')
        field_id = field.get('id')

        if pdf_name:
            # Map both full name and short name (last part after .)
            mapping[pdf_name] = field_id
            short_name = pdf_name.split('.')[-1]
            mapping[short_name] = field_id

        # Also map consolidated widgets
        for widget_name in field.get('consolidated_widgets', []):
            if widget_name not in mapping:
                mapping[widget_name] = field_id
            short_name = widget_name.split('.')[-1]
            mapping[short_name] = field_id

    return mapping


def reorder_schema_fields(schema: Dict, sorted_widgets: List[Dict]) -> Dict:
    """
    Reorder schema fields based on sorted widgets.

    Also adds page number to pdf_position for each field.
    """
    print(f"\n{'='*70}")
    print("REORDERING SCHEMA FIELDS")
    print(f"{'='*70}")

    # Create widget->field mapping
    widget_to_field = create_widget_to_field_map(schema)

    # Create field->widget(s) reverse mapping
    field_to_widgets = {}
    for widget in sorted_widgets:
        widget_name = widget['name']
        # Try full name first, then short name
        field_id = widget_to_field.get(widget_name)
        if not field_id:
            short_name = widget_name.split('.')[-1]
            field_id = widget_to_field.get(short_name)

        if field_id:
            if field_id not in field_to_widgets:
                field_to_widgets[field_id] = []
            field_to_widgets[field_id].append(widget)

    print(f"  Mapped {len(field_to_widgets)} fields to widgets")

    # Create field lookup
    field_lookup = {f['id']: f for f in schema['fields']}

    # Reorder fields based on first occurrence in sorted widgets
    seen_fields = set()
    ordered_fields = []

    for widget in sorted_widgets:
        widget_name = widget['name']
        # Try full name first, then short name
        field_id = widget_to_field.get(widget_name)
        if not field_id:
            short_name = widget_name.split('.')[-1]
            field_id = widget_to_field.get(short_name)

        if field_id and field_id not in seen_fields:
            seen_fields.add(field_id)
            field = field_lookup[field_id]

            # Add page number and question number to field
            if field_id in field_to_widgets:
                first_widget = field_to_widgets[field_id][0]

                # Ensure pdf_position exists as a dict (not None)
                if field.get('pdf_position') is None or not isinstance(field.get('pdf_position'), dict):
                    field['pdf_position'] = {}

                # Add position info
                field['pdf_position']['page'] = first_widget['page'] + 1  # 1-indexed
                field['pdf_position']['x'] = first_widget['x']
                field['pdf_position']['y'] = first_widget['y']
                field['pdf_position']['width'] = first_widget['width']
                field['pdf_position']['height'] = first_widget['height']

                # Add question number if available
                if first_widget.get('question_number'):
                    field['question_number'] = first_widget['question_number']

            ordered_fields.append(field)

    # Add any fields that weren't in widgets (shouldn't happen, but just in case)
    for field_id, field in field_lookup.items():
        if field_id not in seen_fields:
            ordered_fields.append(field)
            print(f"  WARNING: Field {field_id} not found in widgets")

    schema['fields'] = ordered_fields

    print(f"  Reordered {len(ordered_fields)} fields")
    print(f"\n  First 20 fields in new order:")
    for i, field in enumerate(ordered_fields[:20]):
        question_num = field.get('question_number', 'N/A')
        page_info = field.get('pdf_position')
        if page_info and isinstance(page_info, dict):
            page = page_info.get('page', 'N/A')
        else:
            page = 'N/A'
        print(f"    {i+1:3}. {question_num:10} Page {page:3} - {field['id']}")

    return schema


def main(pdf_path: str, schema_path: str, output_path: str):
    """Main execution"""
    print("="*70)
    print("FIELD ORDER EXTRACTOR - Parse Question Numbers from Labels")
    print("="*70)
    print(f"\nPDF: {pdf_path}")
    print(f"Schema: {schema_path}")
    print(f"Output: {output_path}")

    # Load schema
    print(f"\n{'='*70}")
    print("LOADING SCHEMA")
    print(f"{'='*70}")
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    print(f"  Loaded {len(schema['fields'])} fields")

    # Extract widgets with labels
    widgets = extract_widgets_with_labels(pdf_path)

    # Sort by question number
    print(f"\n{'='*70}")
    print("SORTING BY QUESTION NUMBER")
    print(f"{'='*70}")
    sorted_widgets = sort_by_question_number(widgets)

    print(f"  Sorted {len(sorted_widgets)} widgets")
    print(f"\n  First 15 in sorted order:")
    for i, widget in enumerate(sorted_widgets[:15]):
        q_num = widget['question_number'] or 'N/A'
        page = widget['page'] + 1
        print(f"    {i+1:3}. Page {page} | {q_num:8} | {widget['name']}")

    # Reorder schema
    schema = reorder_schema_fields(schema, sorted_widgets)

    # Save
    print(f"\n{'='*70}")
    print("SAVING ORDERED SCHEMA")
    print(f"{'='*70}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    print(f"  Saved to: {output_path}")

    print(f"\n{'='*70}")
    print("COMPLETE")
    print(f"{'='*70}")
    print(f"  Fields reordered by question number")
    print(f"  Page numbers added to pdf_position")
    print(f"  Question numbers added to fields")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python extract_field_order_from_labels.py <pdf> <schema> [output_schema]")
        print("\nExample:")
        print("  python extract_field_order_from_labels.py \\")
        print("    test_schemas/test_pdfs/i-90/i-90.pdf \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v9_conformant.json \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v10_ordered.json")
        sys.exit(1)

    pdf = sys.argv[1]
    schema = sys.argv[2]
    output = sys.argv[3] if len(sys.argv) > 3 else schema.replace('.json', '_ordered.json')

    main(pdf, schema, output)
