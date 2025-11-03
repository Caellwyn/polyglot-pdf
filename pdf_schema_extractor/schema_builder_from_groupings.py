#!/usr/bin/env python3
"""
Schema Builder - Combines Gemini groupings with widget inventory.

Separation of concerns:
- Gemini provides: Groups, tables (semantic understanding)
- Python provides: 100% widget coverage, field details, schema structure
"""

import json
import re
import fitz
from typing import Dict, List, Any, Optional, Tuple
from widget_inventory import extract_widget_inventory
from heuristic_hierarchy_parser import parse_tooltip_hierarchy


def extract_form_metadata_from_pdf(pdf_path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract form metadata from PDF.

    Returns:
        (form_number, form_title, edition_date)
    """
    doc = fitz.open(pdf_path)

    form_number = None
    form_title = None
    edition_date = None

    # Try to get from PDF metadata
    metadata = doc.metadata
    if metadata.get('title'):
        title = metadata['title']
        form_title = title

        # Extract form number from title (e.g., "Form I-90, Application...")
        match = re.search(r'Form\s+(I-\d+)', title, re.IGNORECASE)
        if match:
            form_number = match.group(1).upper()

    # Try to get from barcode widget (contains: form_number|edition_date|page)
    if not form_number or not edition_date:
        first_page = doc[0]
        for widget in first_page.widgets():
            if widget.field_value and 'barcode' in widget.field_name.lower():
                parts = widget.field_value.split('|')
                if len(parts) >= 2:
                    form_number = parts[0].strip().upper()
                    edition_date = parts[1].strip()
                break

    # Fallback to filename
    if not form_number:
        filename = pdf_path.split('/')[-1].replace('\\', '/')
        match = re.search(r'(i-\d+)', filename, re.IGNORECASE)
        if match:
            form_number = match.group(1).upper()

    doc.close()

    return form_number, form_title, edition_date


def parse_tooltip_for_label(tooltip: str) -> str:
    """
    Extract user-friendly label from tooltip.

    Examples:
    - "Part. A. 1. Information About You. 1. Enter Alien Registration Number" → "Alien Registration Number"
    - "Part. A. 1. Information About You. 4. Enter Complete Last Name" → "Complete Last Name"
    """
    if not tooltip:
        return ""

    # Remove "Part X" prefix
    if ". Enter " in tooltip:
        return tooltip.split(". Enter ")[-1].rstrip(".")

    # Try to extract last meaningful part
    parts = [p.strip() for p in tooltip.split(".") if p.strip()]
    if parts:
        # Skip "Part X" type prefixes
        filtered = [p for p in parts if not p.startswith("Part ") and len(p) > 3]
        if filtered:
            return filtered[-1]

    return tooltip[:50]  # Fallback


def parse_section_from_tooltip(tooltip: str) -> str:
    """
    Extract section name from tooltip using generalized parser.

    Examples:
    - i-589: "Part. A. 1. Information About You. ..." → "Part A.1 - Information About You"
    - i-90: "Part 1. Information About You. Mailing Address. ..." → "Part 1 - Information About You"
    """
    if not tooltip:
        return "General"

    parsed = parse_tooltip_hierarchy(tooltip)

    # Build section name from parsed hierarchy
    parts = []
    if parsed.get('part'):
        part_str = f"Part {parsed['part']}"
        if parsed.get('section'):
            part_str += f".{parsed['section']}"
        parts.append(part_str)

    if parsed.get('section_name'):
        parts.append(parsed['section_name'])

    if parts:
        return " - ".join(parts)

    return "General"


def build_schema(
    widget_inventory: List[Dict[str, Any]],
    groupings: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build complete schema from widget inventory + Gemini groupings.

    Args:
        widget_inventory: List of all widgets from PDF
        groupings: Gemini output with 'groups' and 'tables'

    Returns:
        Complete schema with 100% widget coverage
    """
    print(f"\n{'='*70}")
    print("SCHEMA BUILDER - Combining Gemini + Heuristic")
    print(f"{'='*70}")

    # Index widgets by field name for fast lookup
    widgets_by_name = {w['field_name']: w for w in widget_inventory}
    accounted_widgets = set()

    fields = []

    # Process groups
    print(f"\nProcessing {len(groupings.get('groups', []))} groups...")
    for group in groupings.get('groups', []):
        widget_names = group['widgets']
        group_type = group['type']
        purpose = group['purpose']

        # Get widget details - try exact match first, then fuzzy match
        group_widgets = []
        found_widget_names = []
        fuzzy_matches = []

        for name in widget_names:
            widget = widgets_by_name.get(name)

            # If exact match fails, try fuzzy matching
            if not widget:
                # Try case-insensitive match
                name_lower = name.lower()
                for w_name, w_data in widgets_by_name.items():
                    if w_name.lower() == name_lower:
                        widget = w_data
                        found_widget_names.append(w_name)
                        fuzzy_matches.append((name, w_name, "case-insensitive"))
                        break

                # Try partial match (e.g., "P1_Line8_m" -> "P1_Line8_male[0]")
                if not widget:
                    for w_name, w_data in widgets_by_name.items():
                        # Check if name is a prefix of w_name
                        if w_name.lower().startswith(name_lower):
                            widget = w_data
                            found_widget_names.append(w_name)
                            fuzzy_matches.append((name, w_name, "prefix"))
                            break
            else:
                found_widget_names.append(name)

            if widget:
                group_widgets.append(widget)

        # Log fuzzy matches
        if fuzzy_matches:
            print(f"  Fuzzy matched in '{purpose}':")
            for gemini_name, actual_name, match_type in fuzzy_matches:
                print(f"    '{gemini_name}' -> '{actual_name}' ({match_type})")

        if not group_widgets:
            print(f"  WARNING: Group '{purpose}' has no matching widgets")
            continue

        # Mark as accounted (only widgets that actually exist)
        accounted_widgets.update(found_widget_names)

        # Build field
        first_widget = group_widgets[0]
        field = {
            "id": first_widget['field_name'].replace('[0]', '').lower(),
            "name": parse_tooltip_for_label(first_widget['field_label']) or purpose,
            "type": "radio" if group_type == "radio" else "checkbox",
            "section": parse_section_from_tooltip(first_widget['field_label']),
            "consolidated_widgets": found_widget_names,  # Use actual found names, not Gemini names
            "options": [
                {
                    "value": w['field_name'],
                    "label": w['field_label'].split('.')[-1].strip() if w['field_label'] else w['field_name'],
                    "pdf_field_name": w['field_name']
                }
                for w in group_widgets
            ]
        }
        fields.append(field)

    print(f"  Created {len([f for f in fields if f['type'] in ['radio', 'checkbox']])} group fields")

    # Process tables
    print(f"\nProcessing {len(groupings.get('tables', []))} tables...")
    for table in groupings.get('tables', []):
        widget_names = table['widgets']
        rows = table['rows']
        columns = table['columns']
        purpose = table['purpose']

        # Mark as accounted
        accounted_widgets.update(widget_names)

        # Get first widget for context
        first_widget = widgets_by_name.get(widget_names[0])

        field = {
            "id": purpose.lower().replace(' ', '_'),
            "name": purpose,
            "type": "table",
            "section": parse_section_from_tooltip(first_widget['field_label']) if first_widget else "General",
            "consolidated_widgets": widget_names,
            "columns": [
                {
                    "id": col['field_pattern'].lower(),
                    "name": col['label'],
                    "type": "text"  # Could be enhanced with actual widget types
                }
                for col in columns
            ],
            "rows": []  # Empty - filled by user
        }
        fields.append(field)

    print(f"  Created {len([f for f in fields if f['type'] == 'table'])} table fields")

    # Process standalone widgets (not in any group/table)
    standalone_widgets = [w for w in widget_inventory if w['field_name'] not in accounted_widgets]
    print(f"\nProcessing {len(standalone_widgets)} standalone widgets...")

    for widget in standalone_widgets:
        field = {
            "id": widget['field_name'].replace('[0]', '').lower(),
            "name": parse_tooltip_for_label(widget['field_label']) or widget['field_name'],
            "type": widget['field_type'],
            "section": parse_section_from_tooltip(widget['field_label']),
            "pdf_field_name": widget['field_name'],
            "consolidated_widgets": [widget['field_name']],
            "label": widget['field_label']
        }

        # Single checkboxes don't need options - they store boolean true/false
        # Only checkbox GROUPS (created by Gemini groupings) have options

        # Add choice options for select fields
        if widget['field_type'] == 'select' and 'choice_options' in widget:
            field['options'] = widget['choice_options']

        fields.append(field)

    print(f"  Created {len(standalone_widgets)} standalone fields")

    # Validate 100% coverage
    all_consolidated = set()
    for field in fields:
        all_consolidated.update(field.get('consolidated_widgets', []))

    total_widgets = len(widget_inventory)
    coverage = len(all_consolidated) / total_widgets if total_widgets else 0

    print(f"\n{'='*70}")
    print("SCHEMA BUILD COMPLETE")
    print(f"{'='*70}")
    print(f"Total fields: {len(fields)}")
    print(f"  - Groups/Tables (Gemini): {len(groupings.get('groups', [])) + len(groupings.get('tables', []))}")
    print(f"  - Standalone (Heuristic): {len(standalone_widgets)}")
    print(f"Widget coverage: {len(all_consolidated)} / {total_widgets} ({coverage*100:.1f}%)")

    if coverage < 1.0:
        missing = total_widgets - len(all_consolidated)
        print(f"  WARNING: {missing} widgets not accounted for!")
    elif coverage > 1.0:
        print(f"  WARNING: Some widgets counted multiple times (check for duplicates)")
    else:
        print(f"  SUCCESS: 100% widget coverage achieved")

    # Extract form metadata from PDF
    form_number, form_title, edition_date = extract_form_metadata_from_pdf(pdf_path)

    schema = {
        "form_metadata": {
            "title": form_title or f"Form {form_number}" if form_number else "Unknown Form",
            "form_number": form_number,
            "edition_date": edition_date,
            "total_widgets": total_widgets,
            "total_fields": len(fields)
        },
        "fields": fields
    }

    return schema


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python schema_builder_from_groupings.py <pdf_path> <groupings_json> [output_json]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    groupings_path = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else "final_schema.json"

    # Load widget inventory
    print(f"Loading widget inventory from {pdf_path}...")
    widgets = extract_widget_inventory(pdf_path)

    # Load groupings
    print(f"Loading groupings from {groupings_path}...")
    with open(groupings_path, 'r', encoding='utf-8') as f:
        groupings = json.load(f)

    # Build schema
    schema = build_schema(widgets, groupings)

    # Save
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print(f"\nSchema saved to: {output_path}")
