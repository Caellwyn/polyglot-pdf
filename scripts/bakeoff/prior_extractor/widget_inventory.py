#!/usr/bin/env python3
"""
Extract complete widget inventory from PDF with field labels and metadata.
This provides structured data for Gemini enhancement without needing OCR.
"""

import fitz
import json
from typing import List, Dict, Any
from pathlib import Path

# PDF Field Flag Constants (bit positions per PDF 1.7 specification)
# Common to all field types:
READ_ONLY = 1 << 0       # bit 0  - field is read-only
REQUIRED = 1 << 1        # bit 1  - field is required
NO_EXPORT = 1 << 2       # bit 2  - exclude from submit

# Text field flags:
MULTILINE = 1 << 12      # bit 12 - multiline text field
PASSWORD = 1 << 13       # bit 13 - password field (mask input)
FILE_SELECT = 1 << 20    # bit 20 - file selection field
COMB = 1 << 24           # PDF 32000-1 Table 228 bit 25 (1-indexed) - fixed-width cells (e.g., SSN)
RICH_TEXT = 1 << 25      # PDF 32000-1 Table 228 bit 26 (1-indexed) - rich text formatting

# Button field flags (checkbox, radio):
NO_TOGGLE_TO_OFF = 1 << 14  # bit 14 - radio button can't be toggled off once selected
RADIO = 1 << 15          # bit 15 - part of radio button group (mutually exclusive)
PUSHBUTTON = 1 << 16     # bit 16 - push button (not checkbox/radio)

# Choice field flags (dropdown, list):
COMBO = 1 << 17          # bit 17 - combo box (dropdown)
EDIT = 1 << 18           # bit 18 - editable combo box
MULTI_SELECT = 1 << 21   # bit 21 - allow multiple selections


def parse_field_flags(flags: int) -> dict:
    """
    Parse PDF field flags into readable boolean flags.

    Args:
        flags: Raw field_flags integer from PDF widget

    Returns:
        Dictionary with boolean flags for common field properties
    """
    return {
        # Common flags
        "read_only": bool(flags & READ_ONLY),
        "required": bool(flags & REQUIRED),
        "no_export": bool(flags & NO_EXPORT),

        # Text field flags
        "multiline": bool(flags & MULTILINE),
        "password": bool(flags & PASSWORD),
        "is_comb": bool(flags & COMB),
        "rich_text": bool(flags & RICH_TEXT),

        # Button field flags
        "no_toggle_to_off": bool(flags & NO_TOGGLE_TO_OFF),
        "is_radio": bool(flags & RADIO),
        "is_pushbutton": bool(flags & PUSHBUTTON),

        # Choice field flags
        "is_combo": bool(flags & COMBO),
        "is_editable": bool(flags & EDIT),
        "multi_select": bool(flags & MULTI_SELECT),
    }


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

    # Check if hidden (field_display: 1 = hidden, 2 = visible)
    # Per PyMuPDF docs: 0=visible, 1=hidden, 2=no_print, 3=no_view
    if widget.field_display == 1:
        return (True, "hidden")

    # Filter out buttons (except if they're signature buttons)
    if widget.field_type == 5 and widget.field_type_string != "signature":
        return (True, "button")

    # Note: We DO NOT filter read-only fields here anymore, as they may be
    # conditionally unlockable. We flag them instead and let downstream logic decide.

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
        - position_y: Y position for ordering
        - field_flags: Raw field flags integer
        - field_display: Display mode (0=visible, 1=hidden, 2=no_print, 3=no_view)
        - text_maxlen: Maximum text length (for text fields)

        Parsed boolean flags (Common):
        - read_only: Field is read-only
        - required: Field is required
        - no_export: Exclude from form submission
        - hidden: Field is hidden (computed from field_display)

        Text field flags:
        - multiline: Multiline text field
        - password: Password field (mask input)
        - is_comb: Fixed-width character cells (e.g., SSN, dates)
        - rich_text: Rich text formatting enabled

        Button field flags:
        - no_toggle_to_off: Radio button can't be toggled off once selected
        - is_radio: Part of radio button group (mutually exclusive)
        - is_pushbutton: Push button (not checkbox/radio)

        Choice field flags:
        - is_combo: Combo box (dropdown)
        - is_editable: Editable combo box
        - multi_select: Allow multiple selections
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

            # Parse field flags
            flags = widget.field_flags if widget.field_flags else 0
            parsed_flags = parse_field_flags(flags)

            # Override type based on field flags (more accurate than PyMuPDF's field_type)
            if parsed_flags['is_combo']:
                # COMBO flag (bit 17) indicates dropdown/select field
                # PyMuPDF often reports these as 'radio' but they're actually dropdowns
                widget_type = "select"

            # Extract dropdown options for select fields
            choice_options = None
            if widget_type == "select" and hasattr(widget, 'choice_values'):
                # choice_values is list of (value, label) tuples
                choice_options = [
                    {"value": val, "label": label}
                    for val, label in widget.choice_values
                    if val and val.strip()  # Skip empty entries
                ]

            widget_data = {
                "field_name": short_name,
                "full_field_name": widget.field_name,
                "field_label": widget.field_label or "",
                "field_type": widget_type,
                "page": page_num,
                "position_y": int(widget.rect.y0) if widget.rect else 0,

                # Raw field properties
                "field_flags": flags,
                "field_display": widget.field_display,
                "text_maxlen": widget.text_maxlen if hasattr(widget, 'text_maxlen') else None,

                # Parsed boolean flags - Common
                "read_only": parsed_flags["read_only"],
                "required": parsed_flags["required"],
                "no_export": parsed_flags["no_export"],

                # Text field flags
                "multiline": parsed_flags["multiline"],
                "password": parsed_flags["password"],
                "is_comb": parsed_flags["is_comb"],
                "rich_text": parsed_flags["rich_text"],

                # Button field flags
                "no_toggle_to_off": parsed_flags["no_toggle_to_off"],
                "is_radio": parsed_flags["is_radio"],
                "is_pushbutton": parsed_flags["is_pushbutton"],

                # Choice field flags
                "is_combo": parsed_flags["is_combo"],
                "is_editable": parsed_flags["is_editable"],
                "multi_select": parsed_flags["multi_select"],

                # Computed flags
                "hidden": widget.field_display == 1,
            }

            # Add choice options for select fields
            if choice_options:
                widget_data["choice_options"] = choice_options

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
