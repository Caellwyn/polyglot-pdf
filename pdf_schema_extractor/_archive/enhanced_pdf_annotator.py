#!/usr/bin/env python3
"""
Enhanced PDF Annotator - Creates verification PDFs with group indicators.

Overlays:
- Field names in blue
- Group names in green boxes
- Radio/checkbox group indicators
- Color-coded by field type
"""

import fitz
import json
from typing import Dict, List, Any
from pathlib import Path


def create_verification_pdf(
    pdf_path: str,
    widgets_file: str,
    groupings_file: str,
    output_path: str
) -> str:
    """
    Create enhanced verification PDF with group indicators.

    Args:
        pdf_path: Original PDF
        widgets_file: Widget inventory JSON
        groupings_file: Gemini groupings JSON
        output_path: Output PDF path
    """
    print("="*70)
    print("ENHANCED PDF ANNOTATOR - Verification Mode")
    print("="*70)

    # Load data
    print("\n[1/4] Loading widget inventory...")
    with open(widgets_file, 'r', encoding='utf-8') as f:
        widget_data = json.load(f)
        widgets = widget_data['widgets']
    print(f"  Loaded {len(widgets)} widgets")

    print("\n[2/4] Loading groupings...")
    with open(groupings_file, 'r', encoding='utf-8') as f:
        groupings_data = json.load(f)
        groups = groupings_data.get('groups', [])
    print(f"  Loaded {len(groups)} groups")

    # Create field name to widget map
    field_map = {w['full_field_name']: w for w in widgets}

    # Create group membership map
    group_map = {}  # field_name -> (group_index, group_type, group_purpose)
    for i, group in enumerate(groups):
        group_type = group.get('type', 'unknown')
        purpose = group.get('purpose', f'Group {i}')
        for field_name in group.get('widgets', []):
            group_map[field_name] = (i, group_type, purpose)

    # Open PDF
    print("\n[3/4] Annotating PDF...")
    doc = fitz.open(pdf_path)

    annotation_count = 0
    group_annotations = 0

    for page_num, page in enumerate(doc):
        # Get all widgets on this page
        page_widgets = [w for w in page.widgets() if w.field_name]

        for widget in page_widgets:
            field_name = widget.field_name
            rect = widget.rect

            # Get widget data
            widget_data = field_map.get(field_name, {})
            field_type = widget_data.get('field_type', 'unknown')
            is_readonly = widget_data.get('read_only', False)
            is_required = widget_data.get('required', False)

            # Check if in group
            group_info = group_map.get(field_name)

            # Color coding by field type
            if group_info:
                color = (0, 0.7, 0)  # Green for grouped fields
            elif field_type == 'checkbox':
                color = (0, 0.5, 1)  # Blue for standalone checkboxes
            elif field_type == 'radio':
                color = (0.8, 0, 0.8)  # Purple for standalone radios
            elif is_readonly:
                color = (0.5, 0.5, 0.5)  # Gray for read-only
            else:
                color = (0, 0, 0.8)  # Dark blue for normal fields

            # Draw field name
            label_rect = fitz.Rect(rect.x0, rect.y1, rect.x1, rect.y1 + 12)

            # Add background for better visibility
            bg_rect = fitz.Rect(label_rect.x0 - 2, label_rect.y0 - 1,
                               label_rect.x1 + 2, label_rect.y1 + 1)
            page.draw_rect(bg_rect, color=(1, 1, 0.9), fill=(1, 1, 0.9))

            # Draw field name
            short_name = field_name.split('.')[-1] if '.' in field_name else field_name
            display_text = short_name[:30]  # Truncate if too long

            # Add indicators
            indicators = []
            if group_info:
                indicators.append(f"G{group_info[0]}")
            if is_required:
                indicators.append("REQ")
            if is_readonly:
                indicators.append("RO")

            if indicators:
                display_text = f"{display_text} [{','.join(indicators)}]"

            page.insert_text(
                (label_rect.x0, label_rect.y1 - 2),
                display_text,
                fontsize=8,
                color=color
            )

            annotation_count += 1

            # Draw group box if part of a group
            if group_info:
                group_idx, group_type, purpose = group_info

                # Draw box around grouped fields
                page.draw_rect(rect, color=(0, 0.7, 0), width=1.5)

                # Add group label (only once per group per page)
                group_key = f"page{page_num}_group{group_idx}"
                if not hasattr(page, '_group_labels'):
                    page._group_labels = set()

                if group_key not in page._group_labels:
                    # Find a good spot for the group label (above first field)
                    label_y = rect.y0 - 15
                    label_rect = fitz.Rect(rect.x0, label_y, rect.x1 + 100, label_y + 12)

                    # Background
                    page.draw_rect(label_rect, color=(0, 0.7, 0), fill=(0.9, 1, 0.9))

                    # Group label
                    group_label = f"GROUP {group_idx}: {purpose[:40]}"
                    page.insert_text(
                        (label_rect.x0 + 2, label_rect.y1 - 2),
                        group_label,
                        fontsize=9,
                        color=(0, 0.5, 0),
                        fontname="helv-bold"
                    )

                    page._group_labels.add(group_key)
                    group_annotations += 1

    # Save annotated PDF
    print("\n[4/4] Saving verification PDF...")
    doc.save(output_path)
    doc.close()

    print("\n" + "="*70)
    print("ANNOTATION COMPLETE")
    print("="*70)
    print(f"Input: {pdf_path}")
    print(f"Output: {output_path}")
    print(f"Field annotations: {annotation_count}")
    print(f"Group annotations: {group_annotations}")
    print("\nColor Legend:")
    print("  Green: Grouped fields (radio/checkbox groups)")
    print("  Blue: Standalone checkboxes")
    print("  Purple: Standalone radios")
    print("  Dark Blue: Normal text fields")
    print("  Gray: Read-only fields")
    print("\nIndicators:")
    print("  [G#]: Group number")
    print("  [REQ]: Required field")
    print("  [RO]: Read-only field")

    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 5:
        print("Usage: python enhanced_pdf_annotator.py <pdf> <widgets_json> <groupings_json> <output_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    widgets_file = sys.argv[2]
    groupings_file = sys.argv[3]
    output_path = sys.argv[4]

    create_verification_pdf(pdf_path, widgets_file, groupings_file, output_path)
