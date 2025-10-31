#!/usr/bin/env python3
"""
Heuristic Hierarchy Parser - Uses regex to parse tooltip structure.

Parses tooltips like:
  "Part. A. 1. Information About You. 1. Enter Alien Registration Number..."
Into:
  {"part": "A", "section": "1", "question": "1", "spoken_name": "Alien Registration Number"}
"""

import re
import json
from typing import Dict, Any, Optional, List


def parse_tooltip_hierarchy(tooltip: str) -> Dict[str, Any]:
    """
    Parse tooltip into hierarchical structure.

    Returns:
        {
            "part": "A" | "B" | "C" | "D" | null,
            "section": "1" | "2" | ... | null,
            "question": "1" | "2" | ... | null,
            "sub_question": "A" | "B" | ... | null,
            "section_name": "Information About You" | null,
            "spoken_name": "Alien Registration Number" | tooltip,
            "raw_tooltip": original tooltip
        }
    """
    result = {
        "part": None,
        "section": None,
        "question": None,
        "sub_question": None,
        "section_name": None,
        "spoken_name": None,
        "raw_tooltip": tooltip,
        "parse_method": "regex"
    }

    if not tooltip:
        return result

    # Pattern 1: Full hierarchy - Part A. 1. Section Name. 1. A. Enter ...
    # Example: "Part. A. 1. Information About You. 1. Enter Alien Registration Number..."
    # Sub-question must be followed by period to avoid matching first letter of words
    match = re.match(
        r'Part\.?\s*([A-D])\.?\s*(\d+)?\.\s*([^.]+?)\.\s*(\d+)\.?\s*(?:([A-Z])\.)?\s*(.+)',
        tooltip,
        re.IGNORECASE
    )

    if match:
        result["part"] = match.group(1)
        result["section"] = match.group(2)
        result["section_name"] = match.group(3).strip()
        result["question"] = match.group(4)
        result["sub_question"] = match.group(5)
        description = match.group(6)

        # Extract spoken name from description
        result["spoken_name"] = extract_spoken_name(description)
        return result

    # Pattern 2: Part + Section Name + Question - Part B. Section Name. 2. A. ...
    # Example: "Part B. Information About Your Application. 2. Have you..."
    match = re.match(
        r'Part\.?\s*([A-D])\.?\s*([^.]+?)\.\s*(\d+)\.?\s*(?:([A-Z])\.)?\s*(.+)',
        tooltip,
        re.IGNORECASE
    )

    if match:
        result["part"] = match.group(1)
        result["section_name"] = match.group(2).strip()
        result["question"] = match.group(3)
        result["sub_question"] = match.group(4)
        description = match.group(5)

        result["spoken_name"] = extract_spoken_name(description)
        return result

    # Pattern 3: Part + Section Name only - Part D. Your Signature. ...
    # Example: "Part D. Your Signature. Print your Complete Name."
    match = re.match(
        r'Part\.?\s*([A-D])\.?\s*([^.]+?)\.\s*(.+)',
        tooltip,
        re.IGNORECASE
    )

    if match:
        result["part"] = match.group(1)
        result["section_name"] = match.group(2).strip()
        description = match.group(3)

        result["spoken_name"] = extract_spoken_name(description)
        return result

    # Fallback: No clear structure
    result["spoken_name"] = tooltip[:50] if len(tooltip) > 50 else tooltip
    return result


def extract_spoken_name(description: str) -> str:
    """
    Extract user-friendly spoken name from field description.

    Examples:
        "Enter Alien Registration Number (A. Number), if any." → "Alien Registration Number"
        "Print your Complete Name." → "Complete Name"
        "Have you ever..." → "Have you ever..."
    """
    # Remove common prefixes (must be followed by space or uppercase to avoid matching "E" in "Expires")
    prefixes = [
        (r'^Enter\s+', ''),
        (r'^Print\s+(?:your\s+)?', ''),
        (r'^Provide\s+', ''),
        (r'^Select\s+', ''),
        (r'^Check\s+', ''),
        (r'^List\s+', ''),
        (r'^Complete\s+', '')
    ]

    cleaned = description.strip()
    for pattern, replacement in prefixes:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    # Take text before first parenthesis or comma
    cleaned = re.split(r'[,(]', cleaned)[0].strip()

    # Remove trailing "if any", periods
    cleaned = re.sub(r'\s+if\s+any\.?$', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.rstrip('.')

    # Limit length
    if len(cleaned) > 60:
        cleaned = cleaned[:60].rsplit(' ', 1)[0] + '...'

    return cleaned if cleaned else description[:50]


def parse_all_tooltips(widgets: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Parse all widget tooltips.

    Args:
        widgets: List of widget dicts with 'field_name' and 'field_label'

    Returns:
        Dict mapping field_name → parsed hierarchy
    """
    results = {}

    for widget in widgets:
        field_name = widget.get('field_name')
        tooltip = widget.get('field_label', '')

        if field_name:
            results[field_name] = parse_tooltip_hierarchy(tooltip)

    return results


if __name__ == "__main__":
    import sys
    from widget_inventory import extract_widget_inventory

    if len(sys.argv) < 2:
        print("Usage: python heuristic_hierarchy_parser.py <pdf_path> [output_json]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "heuristic_hierarchy.json"

    # Load widgets
    print(f"Loading widgets from {pdf_path}...")
    widgets = extract_widget_inventory(pdf_path)

    # Parse hierarchies
    print(f"Parsing {len(widgets)} tooltips with regex...")
    hierarchies = parse_all_tooltips(widgets)

    # Stats
    with_part = sum(1 for h in hierarchies.values() if h['part'])
    with_section = sum(1 for h in hierarchies.values() if h['section'])
    with_question = sum(1 for h in hierarchies.values() if h['question'])
    with_subq = sum(1 for h in hierarchies.values() if h['sub_question'])

    print(f"\nParsing statistics:")
    print(f"  Fields with Part: {with_part}/{len(hierarchies)}")
    print(f"  Fields with Section: {with_section}/{len(hierarchies)}")
    print(f"  Fields with Question: {with_question}/{len(hierarchies)}")
    print(f"  Fields with Sub-question: {with_subq}/{len(hierarchies)}")

    # Sample results
    print(f"\nSample parsed hierarchies:")
    for field_name, hier in list(hierarchies.items())[:5]:
        print(f"\n{field_name}:")
        print(f"  Path: Part {hier['part']} > Section {hier['section']} > Q{hier['question']} > {hier['sub_question']}")
        print(f"  Name: {hier['spoken_name']}")

    # Save
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(hierarchies, f, indent=2, ensure_ascii=False)

    print(f"\nHierarchies saved to: {output_path}")
