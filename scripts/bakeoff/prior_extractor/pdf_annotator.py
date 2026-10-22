#!/usr/bin/env python3
"""
Annotate PDF with widget field names overlaid on each field.
This creates a visual reference that Gemini can use to map field names to form structure.
"""

import pymupdf as fitz
from pathlib import Path
from typing import List, Dict, Any
from widget_inventory import extract_widget_inventory


def annotate_pdf_with_field_names(
    pdf_path: str,
    output_path: str = None,
    font_size: int = 8,
    color: tuple = (1, 0, 0)  # Red (RGB in 0-1 range)
) -> str:
    """
    Create an annotated version of the PDF with field names overlaid on each widget.

    Args:
        pdf_path: Path to input PDF
        output_path: Path for annotated PDF (defaults to {pdf_name}_annotated.pdf)
        font_size: Size of annotation text
        color: RGB color tuple (0-1 range) for annotations

    Returns:
        Path to annotated PDF
    """
    if not output_path:
        pdf_name = Path(pdf_path).stem
        output_path = f"{pdf_name}_annotated.pdf"

    # Open PDF
    doc = fitz.open(pdf_path)

    # Get widget inventory (with filtering applied)
    widgets = extract_widget_inventory(pdf_path)

    # Group widgets by page for efficient processing
    widgets_by_page = {}
    for widget in widgets:
        page_num = widget['page']
        if page_num not in widgets_by_page:
            widgets_by_page[page_num] = []
        widgets_by_page[page_num].append(widget)

    annotation_count = 0

    # Annotate each page
    for page_num in range(len(doc)):
        page = doc[page_num]
        page_widgets = widgets_by_page.get(page_num, [])

        for widget_info in page_widgets:
            # Find the actual widget to get rect
            for widget in page.widgets():
                if not widget.field_name:
                    continue

                # Match by short name
                short_name = widget.field_name.split('.')[-1] if '.' in widget.field_name else widget.field_name
                if short_name == widget_info['field_name'] and widget.rect:
                    # Draw semi-transparent rectangle behind text
                    rect = widget.rect

                    # Calculate text position (above the field, or inside if field is tall)
                    field_height = rect.y1 - rect.y0
                    if field_height > font_size + 4:
                        # Tall field - put text inside at top
                        text_point = fitz.Point(rect.x0 + 2, rect.y0 + font_size + 2)
                    else:
                        # Short field - put text above
                        text_point = fitz.Point(rect.x0, rect.y0 - 2)

                    # Add text annotation
                    text = widget_info['field_name']

                    # Insert text with background
                    # First, create a background rectangle
                    text_rect = fitz.Rect(
                        text_point.x - 2,
                        text_point.y - font_size - 2,
                        text_point.x + len(text) * font_size * 0.6 + 2,
                        text_point.y + 2
                    )

                    # Draw white background
                    page.draw_rect(
                        text_rect,
                        color=None,
                        fill=(1, 1, 1)  # White
                    )

                    # Draw text
                    page.insert_text(
                        text_point,
                        text,
                        fontsize=font_size,
                        color=color,
                        fontname="helv",  # Helvetica
                        overlay=True
                    )

                    # Draw border around field (optional - helps see boundaries)
                    page.draw_rect(
                        rect,
                        color=color,
                        width=0.5,
                        overlay=True
                    )

                    annotation_count += 1
                    break  # Found the widget, move to next

    # Save annotated PDF
    doc.save(output_path)
    doc.close()

    print(f"\nAnnotated PDF created:")
    print(f"  Input: {pdf_path}")
    print(f"  Output: {output_path}")
    print(f"  Annotations: {annotation_count} field names overlaid")

    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_annotator.py <pdf_path> [output_path]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    annotate_pdf_with_field_names(pdf_path, output_path)
