#!/usr/bin/env python3
"""
Build proper I-90 schema with voice-friendly names and correct section structure.

This script:
1. Loads widget inventory and Gemini groupings
2. Parses Part/subsection structure from labels
3. Creates voice-friendly field names
4. Generates proper sections (up to 20 fields each)
5. Maps to FormSchema model
"""

import json
import re
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime


def parse_i90_label(label: str) -> Dict[str, Optional[str]]:
    """
    Parse I-90 field label into structured components.

    Examples:
    - "Part 1. Information About You. 1. Enter Alien Registration Number."
    - "Part 1. Information About You. Mailing Address. 6. A. Enter In Care Of Name."
    - "Part 3. Processing Information. Biographic Information. 8. Height. Feet."

    Returns:
        Dict with: part_num, part_title, subsection, question_num, subquestion, field_description
    """
    result = {
        "part_num": None,
        "part_title": None,
        "subsection": None,
        "question_num": None,
        "subquestion": None,
        "field_description": None
    }

    # Extract Part number and title
    part_match = re.match(r'^Part (\d+)\.\s*([^.]+)\.', label)
    if part_match:
        result["part_num"] = int(part_match.group(1))
        result["part_title"] = part_match.group(1).strip()

    # Remove the Part prefix to analyze remaining structure
    remaining = re.sub(r'^Part \d+\.\s*[^.]+\.\s*', '', label)

    # Try to identify subsection (e.g., "Mailing Address", "Your Full Name")
    # These appear before numbered questions
    subsection_match = re.match(r'^([^.]+?)\.\s*(\d+)', remaining)
    if subsection_match:
        result["subsection"] = subsection_match.group(1).strip()
        result["question_num"] = subsection_match.group(2).strip()
        remaining = remaining[subsection_match.end():]
    else:
        # No subsection, just question number
        q_match = re.match(r'^(\d+)', remaining)
        if q_match:
            result["question_num"] = q_match.group(1)
            remaining = remaining[q_match.end():]

    # Extract subquestion letter (A, B, C, etc.)
    subq_match = re.match(r'^\.\s*([A-Z])\.\s*', remaining)
    if subq_match:
        result["subquestion"] = subq_match.group(1)
        remaining = remaining[subq_match.end():]

    # Remaining is the field description
    result["field_description"] = remaining.strip().rstrip('.')

    return result


def create_voice_friendly_name(parsed_label: Dict, field_name: str) -> tuple[str, str]:
    """
    Create display name and spoken name for voice interaction.

    Returns:
        (display_name, spoken_name)
    """
    desc = parsed_label.get("field_description", "")

    # Clean up common patterns
    desc = re.sub(r'^(Enter|Select|Provide|Check if)\s+', '', desc, flags=re.IGNORECASE)
    desc = re.sub(r'\s*\(.*?\)\s*', ' ', desc)  # Remove parentheticals
    desc = desc.strip()

    # Create display name
    if parsed_label.get("subsection"):
        prefix = f"{parsed_label['subsection']} - "
    else:
        prefix = ""

    display_name = prefix + desc if desc else field_name

    # Create spoken name (more conversational)
    spoken = desc.lower()
    spoken = re.sub(r'\s+', ' ', spoken).strip()

    # Simplify for voice
    spoken_aliases = {
        "family name": "last name",
        "given name": "first name",
        "alien registration number": "a number",
        "u s c i s": "uscis",
        "zip code": "zip",
    }

    for pattern, replacement in spoken_aliases.items():
        spoken = spoken.replace(pattern, replacement)

    return display_name, spoken


def determine_field_type(widget: Dict, groups: Dict) -> tuple[str, Optional[str]]:
    """
    Determine proper field type for schema.

    Returns:
        (field_type, group_id if part of a group)
    """
    field_name = widget["field_name"]
    widget_type = widget["field_type"]

    # Check if part of a group
    group_id = None
    for group_name, group_data in groups.items():
        if field_name in group_data.get("fields", []):
            group_id = group_name
            break

    # Map widget type to schema type
    if group_id:
        # Part of a group
        group_type = groups[group_id].get("type", "checkbox")
        return group_type, group_id
    elif widget_type == "signature":
        # Signature fields are actually text inputs in I-90
        if widget.get("multiline"):
            return "textarea", None
        else:
            return "text", None
    elif widget_type == "checkbox":
        return "checkbox", None
    elif widget_type == "radio":
        return "radio", None
    else:
        return widget_type, None


def create_section_id(part_num: int, subsection: Optional[str]) -> str:
    """Create section ID from part and subsection."""
    if subsection:
        # Clean subsection name for ID
        clean = re.sub(r'[^a-zA-Z0-9]+', '_', subsection.lower())
        return f"part_{part_num}_{clean}"
    else:
        return f"part_{part_num}"


def build_i90_schema(widgets_file: str, groupings_file: str, output_file: str):
    """Build complete I-90 schema."""

    print("="*70)
    print("I-90 SCHEMA BUILDER")
    print("="*70)

    # Load data
    print("\n[1/6] Loading widget inventory...")
    with open(widgets_file, 'r', encoding='utf-8') as f:
        widget_data = json.load(f)
        widgets = widget_data["widgets"]
    print(f"  Loaded {len(widgets)} widgets")

    print("\n[2/6] Loading Gemini groupings...")
    with open(groupings_file, 'r', encoding='utf-8') as f:
        groupings_data = json.load(f)
        # Create IDs from purpose and index
        groups = {}
        for i, g in enumerate(groupings_data.get("groups", [])):
            group_id = f"group_{i}"
            g["id"] = group_id
            # Normalize field names: "widgets" -> "fields"
            g["fields"] = g.get("widgets", [])
            groups[group_id] = g
    print(f"  Loaded {len(groups)} groups")

    # Parse all widget labels
    print("\n[3/6] Parsing widget labels...")
    parsed_widgets = []
    for widget in widgets:
        parsed = parse_i90_label(widget["field_label"])
        widget["parsed"] = parsed
        parsed_widgets.append(widget)

    # Count by part
    parts_count = defaultdict(int)
    for w in parsed_widgets:
        part = w["parsed"].get("part_num")
        if part:
            parts_count[part] += 1
    print(f"  Identified {len(parts_count)} parts:")
    for part, count in sorted(parts_count.items()):
        print(f"    Part {part}: {count} fields")

    # Group by Part and Subsection
    print("\n[4/6] Organizing into sections...")
    sections_map = defaultdict(list)
    for widget in parsed_widgets:
        parsed = widget["parsed"]
        part_num = parsed.get("part_num", 0)
        subsection = parsed.get("subsection")

        section_key = (part_num, subsection)
        sections_map[section_key].append(widget)

    print(f"  Created {len(sections_map)} sections")

    # Build schema structure
    print("\n[5/6] Building schema structure...")

    fields = []
    sections = []
    parts = []
    processed_groups = set()

    section_order = 0
    # Sort with None handling (None comes before strings)
    sorted_sections = sorted(sections_map.items(), key=lambda x: (x[0][0], x[0][1] or ""))
    for (part_num, subsection), section_widgets in sorted_sections:
        section_order += 1

        # Get part title from first widget
        if section_widgets:
            part_title = section_widgets[0]["parsed"].get("part_title", f"Part {part_num}")
        else:
            part_title = f"Part {part_num}"

        # Create section
        section_id = create_section_id(part_num, subsection)
        section_label = f"Part {part_num}: {part_title}"
        if subsection:
            section_label += f" - {subsection}"

        section_field_ids = []

        # Process widgets in this section
        for widget in section_widgets:
            field_name = widget["field_name"]
            full_name = widget["full_field_name"]
            parsed = widget["parsed"]

            # Determine field type
            field_type, group_id = determine_field_type(widget, groups)

            # Skip if already processed as part of a group
            if group_id and group_id in processed_groups:
                continue

            # Create field ID
            field_id = re.sub(r'[^a-z0-9_]', '_', field_name.lower())

            # Create names
            display_name, spoken_name = create_voice_friendly_name(parsed, field_name)

            # Build field
            field = {
                "id": field_id,
                "name": display_name,
                "spoken_name": spoken_name,
                "type": field_type,
                "section_id": section_id,
                "section_label": section_label,
                "pdf_field_name": full_name,
                "read_only": widget.get("read_only", False),
                "required": widget.get("required", False),
                "multiline": widget.get("multiline", False),
                "hidden": widget.get("hidden", False),
            }

            # Add max_length for text fields
            if widget.get("text_maxlen") and widget["text_maxlen"] > 0:
                field["max_length"] = widget["text_maxlen"]

            # Add help text from label
            if widget["field_label"]:
                field["help"] = {
                    "tooltip": widget["field_label"]
                }

            # Handle grouped fields (radio/checkbox groups)
            if group_id:
                group_data = groups[group_id]
                field["group_id"] = group_id
                field["options"] = []

                for group_field in group_data.get("fields", []):
                    # Find widget for this option
                    option_widget = next((w for w in widgets if w["field_name"] == group_field), None)
                    if option_widget:
                        option_label = option_widget.get("field_label", "").split(".")[-1].strip()
                        field["options"].append({
                            "value": group_field,
                            "label": option_label or group_field,
                            "pdf_field_name": option_widget["full_field_name"]
                        })

                processed_groups.add(group_id)

            fields.append(field)
            section_field_ids.append(field_id)

        # Create section entry
        sections.append({
            "id": section_id,
            "label": section_label,
            "order": section_order,
            "fields": section_field_ids,
            "page_number": section_widgets[0]["page"] + 1 if section_widgets else 1
        })

    # Create parts structure
    parts_map = defaultdict(list)
    for section in sections:
        part_num = int(section["id"].split("_")[1])
        parts_map[part_num].append(section["id"])

    for part_num in sorted(parts_map.keys()):
        # Get part title from first section
        first_section = next(s for s in sections if s["id"] in parts_map[part_num])
        part_title = first_section["label"].split(":")[1].split("-")[0].strip()

        parts.append({
            "id": f"part_{part_num}",
            "label": f"Part {part_num}: {part_title}",
            "order": part_num,
            "section_ids": parts_map[part_num]
        })

    # Build final schema
    schema = {
        "source": "pdf",
        "form_metadata": {
            "title": "Application to Replace Permanent Resident Card",
            "form_number": "I-90",
            "edition_date": "01/20/25",
            "agency": "U.S. Citizenship and Immigration Services",
            "page_count": 7,
            "version": "1.0.0",
            "language": "en"
        },
        "parts": parts,
        "sections": sections,
        "fields": fields,
        "extraction_info": {
            "extracted_at": datetime.now().isoformat(),
            "extraction_confidence": 0.95,
            "extractor_version": "1.0.0",
            "manual_review_required": True,
            "manual_review_completed": False
        }
    }

    # Save schema
    print(f"\n[6/6] Saving schema...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print("\n" + "="*70)
    print("SCHEMA BUILD COMPLETE")
    print("="*70)
    print(f"Parts: {len(parts)}")
    print(f"Sections: {len(sections)}")
    print(f"Fields: {len(fields)}")
    print(f"Groups processed: {len(processed_groups)}")
    print(f"\nSchema saved to: {output_file}")
    print("\nNext steps:")
    print("1. Review schema for accuracy")
    print("2. Add validation rules where needed")
    print("3. Refine spoken names for voice UX")
    print("4. Test with form_schema_model.py validation")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python build_i90_schema.py <widgets_json> <groupings_json> <output_json>")
        sys.exit(1)

    widgets_file = sys.argv[1]
    groupings_file = sys.argv[2]
    output_file = sys.argv[3]

    build_i90_schema(widgets_file, groupings_file, output_file)
