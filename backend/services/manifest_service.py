"""
Manifest Service for JIT Schema Loading

Generates lightweight field manifests containing only field_id and spoken_name pairs.
Used to reduce initial token count from ~7,400 to <500 tokens.
"""

from typing import Dict, List, Any
import logging

_log = logging.getLogger(__name__)


def generate_part_manifest(
    part_data: dict,
    previous_parts_manifests: List[dict]
) -> dict:
    """
    Generate manifest for a single part.

    Args:
        part_data: Full part schema with all fields
        previous_parts_manifests: Manifests from completed parts (for cross-section lookups)

    Returns:
        Manifest dict with:
        - current_part: {part_id, part_label, fields: [{field_id, spoken_name}]}
        - previous_parts: [{part_id, part_label, fields: [{field_id, spoken_name}]}]
    """
    # Extract current part manifest (lightweight)
    current_part_manifest = {
        "part_id": part_data.get("id", "unknown"),
        "part_label": part_data.get("label", "Unknown Part"),
        "fields": []
    }

    # Extract only field_id and spoken_name for each field
    for field in part_data.get("fields", []):
        current_part_manifest["fields"].append({
            "field_id": field.get("id", "unknown"),
            "spoken_name": field.get("spoken_name", field.get("name", "unknown"))
        })

    # Build complete manifest
    manifest = {
        "current_part": current_part_manifest,
        "previous_parts": previous_parts_manifests
    }

    _log.info(
        "manifest_generated",
        part_id=current_part_manifest["part_id"],
        current_fields=len(current_part_manifest["fields"]),
        previous_parts=len(previous_parts_manifests)
    )

    return manifest


def get_next_field_schema(part_data: dict, current_field_id: str | None = None) -> dict | None:
    """
    Get the full schema for the next unfilled field in the part.

    Used for next_field_hint to attach schema when guiding Gemini forward.

    Args:
        part_data: Full part schema
        current_field_id: ID of current field (None = get first field)

    Returns:
        Next field's complete schema, or None if no more fields
    """
    fields = part_data.get("fields", [])
    if not fields:
        return None

    # If no current field, return first field
    if current_field_id is None:
        return fields[0]

    # Find next field after current
    try:
        current_index = next(i for i, f in enumerate(fields) if f.get("id") == current_field_id)
        if current_index + 1 < len(fields):
            return fields[current_index + 1]
    except StopIteration:
        pass

    return None


def should_include_schema_in_response(field_id: str, loaded_field_ids: set) -> bool:
    """
    Determine if a field's schema should be included in a tool response.

    Schema is included if:
    1. Field schema has not been sent to Gemini yet (not in loaded_field_ids)

    Args:
        field_id: Field ID being accessed
        loaded_field_ids: Set of field IDs whose schemas have been sent

    Returns:
        True if schema should be included, False otherwise
    """
    return field_id not in loaded_field_ids


def format_manifest_for_context(manifest: dict) -> str:
    """
    Format manifest as pipe-separated text for Gemini context.

    Avoids JSON quote confusion with field IDs containing brackets.

    Args:
        manifest: Manifest dict

    Returns:
        Formatted string like:
        "CURRENT PART: Part 1 - Information About You
        Fields: field_id|spoken_name | field_id|spoken_name | ...

        PREVIOUS PARTS:
        Part 2: field_id|spoken_name | field_id|spoken_name | ...
        "
    """
    lines = []

    # Current part
    current = manifest.get("current_part", {})
    lines.append(f"CURRENT PART: {current.get('part_label', 'Unknown')}")

    field_entries = []
    for field in current.get("fields", []):
        field_entries.append(f"{field['field_id']}|{field['spoken_name']}")

    lines.append("Fields: " + " | ".join(field_entries))

    # Previous parts (for cross-section queries)
    previous_parts = manifest.get("previous_parts", [])
    if previous_parts:
        lines.append("\nPREVIOUS PARTS (lookup only):")
        for part in previous_parts:
            part_fields = []
            for field in part.get("fields", []):
                part_fields.append(f"{field['field_id']}|{field['spoken_name']}")
            lines.append(f"{part.get('part_label', 'Unknown')}: " + " | ".join(part_fields))

    return "\n".join(lines)


def estimate_manifest_tokens(manifest: dict) -> int:
    """
    Estimate token count for a manifest.

    Uses formatted text version since that's what goes to Gemini.
    Rough estimate: ~4 characters per token.

    Args:
        manifest: Manifest dict

    Returns:
        Estimated token count
    """
    formatted_text = format_manifest_for_context(manifest)
    char_count = len(formatted_text)
    token_estimate = char_count // 4

    _log.debug(
        "manifest_token_estimate",
        characters=char_count,
        estimated_tokens=token_estimate
    )

    return token_estimate
