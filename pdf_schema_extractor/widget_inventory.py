#!/usr/bin/env python3
"""
Extract complete widget inventory from PDF with field labels and metadata.
This provides structured data for Gemini enhancement without needing OCR.
"""

import fitz
import json
from typing import List, Dict, Any
from pathlib import Path


def should_exclude_widget(widget) -> tuple[bool, str]:
    """
    Determine if a widget should be excluded from the schema.

    Returns:
        (should_exclude: bool, reason: str)
    """
    field_name = widget.field_name or ""
    field_label = (widget.field_label or "").lower()

    # Filter out barcodes
    if any(barcode in field_name.upper() for barcode in ['BARCODE', 'BAR_CODE']):
        return (True, "barcode")

    # Note: We don't filter signature section fields because they contain important
    # text inputs (name, date, etc.). Gemini will handle identifying actual signature widgets.

    # Filter out read-only fields (field_flags bit 0 = read-only)
    if widget.field_flags and (widget.field_flags & 1):
        return (True, "read_only")

    # Filter out hidden fields (field_display = 2 means hidden)
    if widget.field_display == 2:
        return (True, "hidden")

    # Filter out buttons (except if they're signature buttons)
    if widget.field_type == 5 and widget.field_type_string != "signature":
        return (True, "button")

    return (False, "")


def extract_widget_inventory(pdf_path: str, include_filtered: bool = False) -> List[Dict[str, Any]]:
    """
    Extract all PDF widgets with their labels and metadata.

    Args:
        pdf_path: Path to PDF file
        include_filtered: If True, include filtered widgets with exclusion reason

    Returns:
        List of widget dictionaries with:
        - field_name: Short name (last component after dot)
        - full_field_name: Complete hierarchical name
        - field_label: Tooltip/label text (rich semantic info!)
        - field_type: Widget type (text, checkbox, etc.)
        - page: Page number (0-indexed)
        - position: Approximate Y position for ordering
    """
    doc = fitz.open(pdf_path)

    widgets = []
    filtered_widgets = []
    seen_short_names = {}  # Track duplicates

    for page_num, page in enumerate(doc):
        for widget in page.widgets():
            if not widget.field_name:
                continue

            # Check if widget should be excluded
            should_exclude, exclusion_reason = should_exclude_widget(widget)
            if should_exclude:
                if include_filtered:
                    filtered_widgets.append({
                        "field_name": widget.field_name,
                        "exclusion_reason": exclusion_reason
                    })
                continue

            # Extract short name (normalized)
            short_name = widget.field_name.split('.')[-1] if '.' in widget.field_name else widget.field_name

            # Track duplicates (for debugging)
            if short_name in seen_short_names:
                # Mark as duplicate but still include
                is_duplicate = True
                seen_short_names[short_name] += 1
            else:
                is_duplicate = False
                seen_short_names[short_name] = 1

            # Get widget type string
            type_map = {
                1: "text",
                2: "checkbox",
                3: "radio",
                4: "select",
                5: "button",
                6: "listbox",
                7: "signature"
            }
            widget_type = type_map.get(widget.field_type, f"unknown_{widget.field_type}")

            widget_data = {
                "field_name": short_name,
                "full_field_name": widget.field_name,
                "field_label": widget.field_label or "",
                "field_type": widget_type,
                "page": page_num,
                "position_y": int(widget.rect.y0) if widget.rect else 0,
            }

            # Flag duplicates
            if is_duplicate:
                widget_data["duplicate_warning"] = f"Duplicate short name (occurrence #{seen_short_names[short_name]})"

            widgets.append(widget_data)

    # Sort by page, then Y position (top to bottom)
    widgets.sort(key=lambda w: (w['page'], w['position_y']))

    # Print filtering stats if we filtered anything
    if filtered_widgets:
        print(f"\nFiltered out {len(filtered_widgets)} non-user-input widgets:")
        from collections import Counter
        reasons = Counter(w['exclusion_reason'] for w in filtered_widgets)
        for reason, count in reasons.items():
            print(f"  - {reason}: {count}")

    return widgets


def save_widget_inventory(pdf_path: str, output_path: str = None, include_filtered: bool = False) -> str:
    """
    Extract and save widget inventory to JSON file.

    Args:
        pdf_path: Path to PDF file
        output_path: Optional output JSON path (defaults to pdf_name_widgets.json)
        include_filtered: If True, include filtered widgets in output

    Returns:
        Path to saved inventory file
    """
    if not output_path:
        pdf_name = Path(pdf_path).stem
        output_path = f"{pdf_name}_widgets.json"

    widgets = extract_widget_inventory(pdf_path, include_filtered=include_filtered)

    # Calculate stats
    total_widgets = len(widgets)
    unique_names = len(set(w['field_name'] for w in widgets))
    duplicates = total_widgets - unique_names

    inventory = {
        "pdf_path": pdf_path,
        "total_widgets": total_widgets,
        "unique_short_names": unique_names,
        "duplicate_count": duplicates,
        "widgets": widgets
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(inventory, f, indent=2, ensure_ascii=False)

    print(f"\nWidget Inventory Extracted:")
    print(f"  Total widgets: {total_widgets}")
    print(f"  Unique names: {unique_names}")
    print(f"  Duplicates: {duplicates}")
    print(f"  Saved to: {output_path}")

    return output_path


def format_for_gemini(widgets: List[Dict[str, Any]], max_widgets: int = None) -> str:
    """
    Format widget inventory for Gemini prompt.

    Includes only essential fields to reduce token usage.
    """
    if max_widgets:
        widgets = widgets[:max_widgets]

    # Simplify for Gemini (remove duplicate warnings, full names)
    simplified = []
    for w in widgets:
        simplified.append({
            "field_name": w["field_name"],
            "label": w["field_label"],
            "type": w["field_type"],
            "page": w["page"]
        })

    return json.dumps(simplified, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python widget_inventory.py <pdf_path> [output_json]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    save_widget_inventory(pdf_path, output_path)
