#!/usr/bin/env python3
"""
Fix I-90 schema issues:
1. Correct type detection (signature -> text/textarea)
2. Extract option labels from tooltips
3. Fix incomplete groups
4. Sort fields by part/question order
"""

import json
import re
from collections import defaultdict
from heuristic_hierarchy_parser import parse_tooltip_hierarchy


def extract_question_order(field: dict, widget_data: dict) -> tuple:
    """
    Extract (part_num, question_num, subquestion, page_index) for sorting.

    Uses tooltips as primary source since they contain the actual form structure.

    Examples:
    - "Part 1. ... 1. Enter ..." → (1, 1, '', 0)
    - "Part 8. ... 1. Enter ... [second page]" → (8, 1, '', 1)
    - "Part 1. ... 6. C. Select Unit" → (1, 6, 'c', 0)
    """
    field_id = field.get('id', '')

    # Get tooltip - primary source of ordering info
    tooltip = widget_data.get('field_label', field.get('label', ''))

    # Parse tooltip hierarchy
    parsed = parse_tooltip_hierarchy(tooltip)

    # Extract part number (handle both numbers like "1" and letters like "A")
    part_num = 999  # Default for fields without part info
    if parsed.get('part'):
        part_str = str(parsed['part'])
        if part_str.isdigit():
            part_num = int(part_str)
        elif part_str.isalpha() and len(part_str) == 1:
            # Convert letter to number (A=1, B=2, etc.)
            part_num = ord(part_str.upper()) - ord('A') + 1

    # Extract question number
    question_num = 999  # Default for fields without question
    if parsed.get('question'):
        try:
            question_num = int(parsed['question'])
        except (ValueError, TypeError):
            pass

    # Extract subquestion letter
    subquestion = parsed.get('sub_question', '').lower() if parsed.get('sub_question') else ''

    # Get page index from field ID [n] suffix for handling duplicates
    page_match = re.search(r'\[(\d+)\]$', field_id)
    page_index = int(page_match.group(1)) if page_match else 0

    return (part_num, question_num, subquestion, page_index)


def fix_field_type(field: dict, widget: dict) -> str:
    """
    Fix field type detection.
    Type 7 (signature) should be text or textarea based on context.
    """
    current_type = field.get('type', 'text')

    if current_type == 'signature':
        # Check if it's actually a text field
        field_name = widget.get('field_name', '').lower()

        # Real signature fields
        if 'signature' in field_name or 'sign' in field_name:
            return 'signature'

        # Multiline text fields
        if widget.get('multiline', False):
            return 'textarea'

        # Regular text fields
        return 'text'

    return current_type


def extract_option_label(tooltip: str) -> str:
    """
    Extract the actual option label from tooltip.

    Examples:
    - "Part 1. ... 6. C. Select Apartment." → "Apartment"
    - "Part 2. ... 2. A. Select My previous card has been lost..." → "My previous card has been lost, stolen, or destroyed"
    """
    # Pattern 1: Question number + letter + Select + label
    # e.g., "2. A. Select My previous card..."
    pattern1 = re.search(r'\d+\.\s*[A-Z]\.\s*Select\s+(.+?)(?:\.\s*(?:NOTE|Select|$)|$)', tooltip, re.IGNORECASE)
    if pattern1:
        label = pattern1.group(1).strip()
        # Remove common trailing patterns
        label = re.sub(r'\s*\(.*?\)\s*$', '', label)  # Remove trailing parentheticals
        label = re.sub(r'[.,;]+$', '', label)  # Remove trailing punctuation
        return label

    # Pattern 2: Just letter + Select + label
    # e.g., "C. Select Apartment"
    pattern2 = re.search(r'[A-Z]\.\s*Select\s+(.+?)(?:\.|$)', tooltip, re.IGNORECASE)
    if pattern2:
        label = pattern2.group(1).strip()
        label = re.sub(r'[.,;]+$', '', label)
        return label

    # Pattern 3: Any Select followed by content
    # Use the LAST occurrence of "Select"
    select_matches = list(re.finditer(r'Select\s+(.+?)(?:\.|$)', tooltip, re.IGNORECASE))
    if select_matches:
        label = select_matches[-1].group(1).strip()
        label = re.sub(r'[.,;]+$', '', label)
        # Skip if label is just filler text
        if not re.match(r'^(only one box|if|the|yes|no)$', label, re.IGNORECASE):
            return label

    # Fallback: try to get last meaningful part
    parts = [p.strip() for p in tooltip.split('.') if p.strip()]
    if parts:
        last_part = parts[-1]
        # Remove common prefixes
        last_part = re.sub(r'^(Enter|Provide|Check if|Indicate)\s+', '', last_part, flags=re.IGNORECASE)
        # Skip if too short or just punctuation
        if len(last_part) > 3 and not re.match(r'^[.,;)\]]+$', last_part):
            return last_part

    return tooltip[:50]


def fix_group_options(group_field: dict, widget_map: dict) -> dict:
    """
    Fix group options by finding all related widgets and extracting labels.

    Uses existing consolidated_widgets list rather than trying to find them.
    """
    # Use the consolidated_widgets list that was already built by schema_builder
    if not group_field.get('consolidated_widgets'):
        return group_field

    consolidated_widgets = group_field['consolidated_widgets']

    # Find matching widgets from widget_map
    matching_widgets = []
    for widget_name in consolidated_widgets:
        # Try exact match first
        widget_data = widget_map.get(widget_name)

        # Try without full path
        if not widget_data:
            simple_name = widget_name.split('.')[-1]
            widget_data = widget_map.get(simple_name)

        if widget_data:
            matching_widgets.append((widget_name, widget_data))

    # Sort by index number
    def get_index(name):
        match = re.search(r'\[(\d+)\]', name)
        return int(match.group(1)) if match else 0

    matching_widgets.sort(key=lambda x: get_index(x[0]))

    # Build options with proper labels
    options = []
    valid_widgets = []
    seen_labels = set()  # Track duplicates

    for widget_name, widget_data in matching_widgets:
        tooltip = widget_data.get('field_label', '')
        label = extract_option_label(tooltip)

        # Skip if label is empty, just punctuation, or already seen
        if label and not re.match(r'^[.,;)\]]+$', label) and label not in seen_labels:
            options.append({
                "value": widget_name,
                "label": label,
                "pdf_field_name": widget_data.get('full_field_name', widget_name)
            })
            valid_widgets.append(widget_name)
            seen_labels.add(label)

    if options:
        group_field['options'] = options
        group_field['consolidated_widgets'] = valid_widgets

    return group_field


def fix_schema(schema_file: str, widgets_file: str, output_file: str):
    """
    Fix all issues in the schema.
    """
    print("="*70)
    print("I-90 SCHEMA FIXER")
    print("="*70)

    # Load data
    print("\n[1/5] Loading data...")
    with open(schema_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    with open(widgets_file, 'r', encoding='utf-8') as f:
        widget_data = json.load(f)
        widgets = widget_data['widgets']

    print(f"  Schema has {len(schema['fields'])} fields")
    print(f"  Widget inventory has {len(widgets)} widgets")

    # Create widget lookup
    widget_map = {}
    for w in widgets:
        widget_map[w['field_name']] = w
        widget_map[w['full_field_name']] = w

    # Fix fields and add metadata
    print("\n[2/5] Fixing field types and adding metadata...")
    type_changes = 0
    metadata_added = 0

    for field in schema['fields']:
        pdf_field = field.get('pdf_field_name', '')

        # For group fields, use first consolidated widget
        if not pdf_field and field.get('consolidated_widgets'):
            first_widget_name = field['consolidated_widgets'][0]
            widget = widget_map.get(first_widget_name)
            if not widget:
                simple_name = first_widget_name.split('.')[-1]
                widget = widget_map.get(simple_name, {})
        else:
            widget = widget_map.get(pdf_field, {})

        # Fix type
        old_type = field.get('type')
        new_type = fix_field_type(field, widget)

        if old_type != new_type:
            field['type'] = new_type
            type_changes += 1

        # Add metadata from widget if available
        if widget:
            # Add field behavior flags
            if 'read_only' in widget:
                field['read_only'] = widget['read_only']
                metadata_added += 1
            if 'required' in widget:
                field['required'] = widget['required']
                metadata_added += 1
            if 'multiline' in widget:
                field['multiline'] = widget['multiline']
            if 'is_comb' in widget:
                field['is_comb'] = widget['is_comb']
            if 'no_toggle_off' in widget:
                field['no_toggle_off'] = widget['no_toggle_off']
            if 'hidden' in widget:
                field['hidden'] = widget['hidden']
            if widget.get('text_maxlen'):
                field['max_length'] = widget['text_maxlen']

    print(f"  Changed {type_changes} field types")
    print(f"  Added metadata to {metadata_added} fields")

    # Fix option labels
    print("\n[3/5] Fixing option labels...")
    options_fixed = 0
    for field in schema['fields']:
        if field.get('options'):
            # Check if this is a group field
            if field.get('consolidated_widgets'):
                field = fix_group_options(field, widget_map)
                options_fixed += 1
            else:
                # Fix standalone field options
                pdf_field = field.get('pdf_field_name', '')
                widget = widget_map.get(pdf_field, {})
                if widget:
                    tooltip = widget.get('field_label', '')
                    label = extract_option_label(tooltip)
                    if label and field['options']:
                        field['options'][0]['label'] = label
                        options_fixed += 1

    print(f"  Fixed options for {options_fixed} fields")

    # Sort fields
    print("\n[4/5] Sorting fields by question order...")
    fields_with_order = []
    for field in schema['fields']:
        pdf_field = field.get('pdf_field_name', '')

        # For group fields without pdf_field_name, use first consolidated widget
        if not pdf_field and field.get('consolidated_widgets'):
            first_widget_name = field['consolidated_widgets'][0]
            # Try direct lookup, then try with just the field name part (remove form1[0].#subform[0]. prefix)
            widget = widget_map.get(first_widget_name)
            if not widget:
                # Extract just field name from full path like "form1[0].#subform[0].P1_checkbox4[1]"
                simple_name = first_widget_name.split('.')[-1]
                widget = widget_map.get(simple_name, {})
        else:
            widget = widget_map.get(pdf_field, widget_map.get(field.get('id'), {}))

        order = extract_question_order(field, widget)
        fields_with_order.append((order, field))

    fields_with_order.sort(key=lambda x: x[0])
    schema['fields'] = [f[1] for f in fields_with_order]

    print(f"  Sorted {len(schema['fields'])} fields")

    # Save
    print("\n[5/5] Saving fixed schema...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print("\n" + "="*70)
    print("SCHEMA FIXED")
    print("="*70)
    print(f"Saved to: {output_file}")
    print(f"\nChanges:")
    print(f"  - Fixed {type_changes} field types (signature -> text/textarea)")
    print(f"  - Added metadata to {metadata_added} fields (read_only, required, multiline, etc.)")
    print(f"  - Fixed options for {options_fixed} groups")
    print(f"  - Sorted fields by part/question order (using tooltip-based ordering)")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python fix_i90_schema.py <schema_json> <widgets_json> <output_json>")
        sys.exit(1)

    schema_file = sys.argv[1]
    widgets_file = sys.argv[2]
    output_file = sys.argv[3]

    fix_schema(schema_file, widgets_file, output_file)
