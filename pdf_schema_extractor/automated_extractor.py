#!/usr/bin/env python3
"""
Automated PDF Schema Extractor - Best-attempt extraction with heuristics

Extracts as much as possible automatically:
- Field types, properties, positions
- Field ordering from labels (using regex pattern)
- Radio/checkbox groups (pattern matching)
- Select options
- Section parsing
- Placeholder spoken names

Human correction needed for:
- Help text
- Validation rules
- Conditional dependencies
"""

import fitz
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from datetime import datetime

# Import from existing modules
from widget_inventory import extract_widget_inventory


def normalize_field_id(field_name: str) -> str:
    """
    Normalize PDF field name to schema field ID.

    Examples:
        P1_Line1_AlienNumber[0] -> p1_line1_aliennumber
        P2_checkbox1[0] -> p2_checkbox1[0]
    """
    # Remove XFA path prefixes
    field_name = field_name.split('.')[-1]

    # Lowercase
    field_id = field_name.lower()

    # Remove trailing [0] for most fields, but keep for arrays
    # Keep [0], [1], etc. for fields that are clearly part of a series
    if field_id.endswith('[0]') and not re.search(r'checkbox|radio', field_id):
        # Check if there's a [1] version - if not, remove [0]
        # For now, just remove [0] from non-checkbox/radio fields
        pass  # Will handle in grouping logic

    return field_id


def extract_ordering_key(label: str) -> str:
    """
    Extract ordering key from label using regex [0-9A-Z]\.

    Examples:
        "Part 1. Information About You. 3. A. Enter Family Name" -> "1.3.A"
        "Part 2. Application Type. 1. Select one" -> "2.1"
    """
    if not label:
        return ""

    # Find all matches of number/letter followed by period
    matches = re.findall(r'([0-9A-Z])\.', label)

    if not matches:
        return ""

    # Join with dots to create hierarchical key
    return '.'.join(matches)


def parse_section_from_label(label: str) -> Optional[str]:
    """
    Extract section name from label.

    Examples:
        "Part 1. Information About You. 3. A. ..." -> "Part 1 - Information About You"
        "Part 2. Application Type. 1. ..." -> "Part 2 - Application Type"
    """
    if not label:
        return None

    # Pattern: "Part X. [Section Name]. [rest]"
    match = re.match(r'Part\s+(\d+)\.\s+([^.]+?)\.', label, re.IGNORECASE)
    if match:
        part_num = match.group(1)
        section_name = match.group(2).strip()
        return f"Part {part_num} - {section_name}"

    return None


def generate_spoken_name(label: str) -> str:
    """
    Generate placeholder spoken name from label.

    Examples:
        "Part 1. ... Enter Family Name (Last Name)" -> "family name"
        "3. A. Enter Given Name (First Name)" -> "given name"
    """
    if not label:
        return ""

    # Remove "Part X." prefix
    cleaned = re.sub(r'Part\s+\d+\.', '', label, flags=re.IGNORECASE)

    # Remove "Enter" prefix
    cleaned = re.sub(r'\bEnter\b', '', cleaned, flags=re.IGNORECASE)

    # Remove "Provide" prefix
    cleaned = re.sub(r'\bProvide\b', '', cleaned, flags=re.IGNORECASE)

    # Remove question numbers (1., 3. A., etc.)
    cleaned = re.sub(r'\b\d+\.\s*([A-Z]\.\s*)?', '', cleaned)

    # Extract text before parentheses (often the key part)
    paren_match = re.search(r'^[^(]+', cleaned)
    if paren_match:
        cleaned = paren_match.group(0)

    # Clean up
    cleaned = cleaned.strip(' .,')

    # Lowercase
    spoken = cleaned.lower()

    # Truncate if too long
    if len(spoken) > 50:
        spoken = spoken[:50]

    return spoken


def detect_field_type(widget: Dict[str, Any]) -> str:
    """
    Detect the actual field type (fixes widget_inventory detection).

    Returns: text, textarea, checkbox, radio, select, date, signature
    """
    # widget_inventory.py already converts to string types
    field_type_str = widget.get('field_type', '')
    label = widget.get('field_label', '').lower()

    # Checkbox or Radio
    if field_type_str == 'checkbox':
        # Check if it's actually a radio button (mutually exclusive group)
        if widget.get('is_radio') or widget.get('no_toggle_to_off'):
            return 'radio'
        return 'checkbox'

    # Select/dropdown
    if field_type_str == 'select':
        return 'select'

    # Signature type from PyMuPDF - often text fields in XFA forms
    if field_type_str == 'signature':
        # Check if it's actually a signature field
        if 'signature' in label or 'sign here' in label or 'applicant signature' in label:
            return 'signature'

        # Check if it's a date field
        if any(word in label for word in ['date of birth', 'date of', 'date you']):
            return 'date'

        # Check if multiline
        if widget.get('multiline'):
            return 'textarea'

        # Most "signature" type fields in XFA are actually text inputs
        return 'text'

    # Default to text
    return 'text'


def extract_select_options(doc: fitz.Document, widget: Dict[str, Any]) -> Optional[List[str]]:
    """
    Extract options from select/dropdown fields.
    """
    if widget.get('field_type') != 'select':  # Not a choice field
        return None

    # Get the actual widget from PyMuPDF
    page_num = widget['page']
    page = doc[page_num]
    widget_name = widget['field_name']

    for pdf_widget in page.widgets():
        # Match on field name (short name without XFA path)
        if pdf_widget.field_name == widget_name:
            # Get choice values
            if hasattr(pdf_widget, 'choice_values'):
                choices = pdf_widget.choice_values
                if choices:
                    return choices

    return None


def detect_radio_checkbox_groups(widgets: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Detect radio/checkbox groups by name patterns.

    Returns:
        {group_base_name: [widget_name1, widget_name2, ...]}
    """
    groups = defaultdict(list)

    for widget in widgets:
        field_name = widget['field_name']
        field_type = widget.get('detected_type', '')

        if field_type not in ['radio', 'checkbox']:
            continue

        # Pattern: FieldName[0], FieldName[1], etc.
        match = re.match(r'(.+?)\[(\d+)\]$', field_name)
        if match:
            base_name = match.group(1)
            groups[base_name].append(field_name)

    # Only return groups with 2+ members
    return {k: v for k, v in groups.items() if len(v) >= 2}


def create_draft_schema(pdf_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a draft schema from PDF with best-attempt extraction.

    Args:
        pdf_path: Path to PDF file
        output_path: Optional path to save JSON output

    Returns:
        Draft schema dictionary
    """
    print("="*70)
    print("AUTOMATED PDF SCHEMA EXTRACTOR")
    print("="*70)

    # Step 1: Extract widgets
    print("\n[1/6] Extracting widgets from PDF...")
    widgets = extract_widget_inventory(pdf_path)
    print(f"  Extracted {len(widgets)} widgets")

    # Open PDF for additional analysis
    doc = fitz.open(pdf_path)

    # Step 2: Detect field types
    print("\n[2/6] Detecting field types...")
    for widget in widgets:
        widget['detected_type'] = detect_field_type(widget)

    type_counts = defaultdict(int)
    for widget in widgets:
        type_counts[widget['detected_type']] += 1

    for ftype, count in sorted(type_counts.items()):
        print(f"  {ftype}: {count}")

    # Step 3: Extract ordering and sections
    print("\n[3/6] Parsing labels for ordering and sections...")
    sections = {}
    for widget in widgets:
        label = widget.get('field_label', '')

        # Extract ordering key
        ordering_key = extract_ordering_key(label)
        widget['ordering_key'] = ordering_key

        # Extract section
        section = parse_section_from_label(label)
        if section:
            widget['section_id'] = section
            sections[section] = sections.get(section, 0) + 1

    print(f"  Found {len(sections)} sections")
    for section, count in sorted(sections.items()):
        print(f"    {section}: {count} fields")

    # Step 4: Detect groups
    print("\n[4/6] Detecting radio/checkbox groups...")
    groups = detect_radio_checkbox_groups(widgets)
    print(f"  Found {len(groups)} groups")
    for group_name, members in groups.items():
        print(f"    {group_name}: {len(members)} members")

    # Step 5: Extract select options
    print("\n[5/6] Extracting select field options...")
    select_count = 0
    for widget in widgets:
        if widget['detected_type'] == 'select':
            options = extract_select_options(doc, widget)
            if options:
                widget['select_options'] = options
                select_count += 1
    print(f"  Extracted options for {select_count} select fields")

    # Step 6: Build schema structure
    print("\n[6/6] Building schema structure...")

    # Extract form metadata
    metadata = doc.metadata or {}
    form_title = metadata.get('title', 'Unknown Form')

    # Try to extract form number from filename or title
    pdf_filename = Path(pdf_path).stem
    form_number_match = re.search(r'(i-\d+)', pdf_filename, re.IGNORECASE)
    form_number = form_number_match.group(1).upper() if form_number_match else "UNKNOWN"

    # Build fields
    fields = []
    for widget in widgets:
        field_name = widget['field_name']
        field_id = normalize_field_id(field_name)
        label = widget.get('field_label', '')

        field = {
            'id': field_id,
            'name': label[:100] if label else field_name,  # Truncate long labels
            'type': widget['detected_type'],
            'pdf_field_name': field_name,
            'label': label,
            'read_only': widget.get('read_only', False),
            'required': widget.get('required', False),
            'multiline': widget.get('multiline', False),
            'is_comb': widget.get('is_comb', False),
            'hidden': widget.get('hidden', False),
        }

        # Add section if detected
        if 'section_id' in widget:
            field['section_id'] = widget['section_id']

        # Add ordering key
        if widget.get('ordering_key'):
            field['question_number'] = widget['ordering_key']

        # Add max length for text fields
        if widget.get('text_maxlen') and widget.get('text_maxlen') > 0:
            field['max_length'] = widget['text_maxlen']

        # Add select options
        if 'select_options' in widget:
            field['options'] = [{'label': opt, 'value': opt} for opt in widget['select_options']]

        # Add position
        field['pdf_position'] = {
            'page': widget['page'] + 1,  # 1-indexed for humans
            'y': widget.get('position_y', 0)
        }

        # Generate placeholder spoken name
        spoken = generate_spoken_name(label)
        if spoken:
            field['spoken_name'] = spoken

        # Add placeholder help (marks that human review is needed)
        field['help'] = {
            'instructions': f"[TODO: Add help text for {spoken or field_id}]"
        }

        fields.append(field)

    # Sort fields by ordering key, then by page and position
    def sort_key(field):
        # Parse ordering key for sorting
        ordering = field.get('question_number', '')
        if ordering:
            # Convert "1.3.A" to sortable tuple (1, 3, 'A')
            parts = ordering.split('.')
            sort_parts = []
            for part in parts:
                if part.isdigit():
                    sort_parts.append((0, int(part)))  # Numbers sort before letters
                else:
                    sort_parts.append((1, part))  # Letters
            return (0, tuple(sort_parts))
        else:
            # No ordering key, sort by page and y position
            pos = field.get('pdf_position', {})
            return (1, pos.get('page', 999), -pos.get('y', 0))  # Negative y for top-to-bottom

    fields.sort(key=sort_key)

    # Build parts and sections
    parts_dict = {}
    sections_dict = {}

    for field in fields:
        section_id = field.get('section_id')
        if section_id:
            if section_id not in sections_dict:
                sections_dict[section_id] = {
                    'id': section_id,
                    'label': section_id,
                    'order': len(sections_dict) + 1,
                    'fields': []
                }
            sections_dict[section_id]['fields'].append(field['id'])

            # Extract part from section
            part_match = re.match(r'(Part \d+)', section_id)
            if part_match:
                part_id = part_match.group(1).lower().replace(' ', '_')
                part_label = part_match.group(1)
                if part_id not in parts_dict:
                    parts_dict[part_id] = {
                        'id': part_id,
                        'label': section_id.split(' - ')[0],  # "Part 1"
                        'order': len(parts_dict) + 1,
                        'section_ids': []
                    }
                if section_id not in parts_dict[part_id]['section_ids']:
                    parts_dict[part_id]['section_ids'].append(section_id)

    # Build final schema
    schema = {
        'source': 'pdf',
        'form_metadata': {
            'title': form_title,
            'form_number': form_number,
            'edition_date': '[TODO: Extract from PDF]',
            'total_widgets': len(widgets),
            'total_fields': len(fields),
            'version': 'draft_v1',
            'language': 'en',
            'extraction_date': datetime.now().isoformat(),
            'extraction_method': 'automated_extractor.py'
        },
        'parts': list(parts_dict.values()),
        'sections': list(sections_dict.values()),
        'fields': fields,
        'extraction_notes': {
            'radio_checkbox_groups_detected': len(groups),
            'sections_detected': len(sections_dict),
            'select_options_extracted': select_count,
            'needs_human_review': [
                'Help text (all fields)',
                'Validation rules',
                'Conditional dependencies',
                'Spoken names (placeholders generated)',
                'Field grouping verification'
            ]
        }
    }

    doc.close()

    # Save if output path provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Draft schema saved to: {output_path}")

    print(f"\n✅ Extraction complete!")
    print(f"   Total fields: {len(fields)}")
    print(f"   Sections: {len(sections_dict)}")
    print(f"   Parts: {len(parts_dict)}")

    return schema


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python automated_extractor.py <pdf_path> [output_json]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    # Auto-generate output path if not provided
    if not output_path:
        pdf_stem = Path(pdf_path).stem
        output_path = f"{pdf_stem}_draft_schema.json"

    create_draft_schema(pdf_path, output_path)
