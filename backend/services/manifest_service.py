"""
Manifest Service for JIT Schema Loading

Generates lightweight field manifests containing only field_id and spoken_name pairs.
Used to reduce initial token count from ~7,400 to <500 tokens.
"""

from typing import Dict, List, Any
import structlog

_log = structlog.get_logger(__name__)

# The only option keys a voice/text model needs. The schema option dicts also
# carry PDF plumbing (pdf_field_name, pdf_on_value, per-option pdf_position -- bd
# polyglot-pdf-5f41) and label_translations, which are meaningless to the model,
# cost tokens in every tool response, and are PDF-internal detail that must not
# leak into a model-facing payload.
_MODEL_FACING_OPTION_KEYS = ("value", "label", "spoken_label")


def _sanitize_options(options: list | None) -> list | None:
    """Strip option dicts to the model-facing keys (value/label/spoken_label).

    Shared by get_next_field_schema (JIT path) and get_field_guidance (DTI path)
    so both apply the SAME sanitization boundary (bd polyglot-pdf-lj5v; the
    boundary was first established for the JIT path in bd polyglot-pdf-5f41).

    Bare-string options (allowed_values-style lists) pass through unchanged --
    every other option consumer guards the same way (ai_context isinstance
    checks), and the pre-sanitizer code never crashed on them.
    """
    if not options:
        return options
    return [
        opt if not isinstance(opt, dict)
        else {k: opt[k] for k in _MODEL_FACING_OPTION_KEYS if opt.get(k) is not None}
        for opt in options
    ]


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
    Get minimal schema for the next unfilled field - only what Gemini needs for voice interaction.

    Filters field schema to include only essential properties:
    - Identity: id, name, spoken_name, spoken_aliases
    - Type and validation: type, required, options/allowed_values
    - Guidance: placeholder, help_text

    Excludes internal properties like section_id, group_id, show_if logic, etc.

    Args:
        part_data: Full part schema
        current_field_id: ID of current field (None = get first field)

    Returns:
        Next field's minimal schema for voice interaction, or None if no more fields
    """
    fields = part_data.get("fields", [])
    if not fields:
        return None

    # Find the next field
    next_field = None
    if current_field_id is None:
        # Return first field
        next_field = fields[0]
    else:
        # Find next field after current
        try:
            current_index = next(i for i, f in enumerate(fields) if f.get("id") == current_field_id)
            if current_index + 1 < len(fields):
                next_field = fields[current_index + 1]
        except StopIteration:
            pass

    if not next_field:
        return None

    # Filter to only properties Gemini needs for voice interaction
    minimal_schema = {
        "id": next_field.get("id"),
        "name": next_field.get("name"),
        "spoken_name": next_field.get("spoken_name"),
        "type": next_field.get("type"),
    }

    # Add optional properties if present
    if next_field.get("spoken_aliases"):
        minimal_schema["spoken_aliases"] = next_field["spoken_aliases"]

    if next_field.get("required"):
        minimal_schema["required"] = next_field["required"]

    # Include options/allowed_values for select/radio/checkbox fields.
    # SANITIZE each option to what the voice model needs (value/label/
    # spoken_label) via the shared helper (bd polyglot-pdf-lj5v) -- the schema
    # option dicts also carry PDF plumbing (pdf_field_name, pdf_on_value,
    # pdf_position -- bd polyglot-pdf-5f41) and label_translations, which are
    # meaningless to the model and cost tokens in every JIT tool response.
    if next_field.get("options"):
        minimal_schema["options"] = _sanitize_options(next_field["options"])
    elif next_field.get("allowed_values"):
        minimal_schema["allowed_values"] = next_field["allowed_values"]

    # Include validation hints if present
    if next_field.get("placeholder"):
        minimal_schema["placeholder"] = next_field["placeholder"]

    if next_field.get("help_text"):
        minimal_schema["help_text"] = next_field["help_text"]

    # Include validation rules for format guidance
    validation = next_field.get("validation")
    if validation:
        minimal_validation = {}
        # Only include constraints that help Gemini guide the user
        for key in ["format", "pattern", "min", "max", "minLength", "maxLength"]:
            if key in validation:
                minimal_validation[key] = validation[key]
        if minimal_validation:
            minimal_schema["validation"] = minimal_validation

    return minimal_schema


def get_field_guidance(field: dict) -> dict | None:
    """Build the per-field guidance block for Dynamic Turn Injection (bd
    polyglot-pdf-jnjj.22).

    Unlike get_next_field_schema (which reads FLAT keys -- placeholder, help_text,
    description -- the demo schema's shape), this reads the canonical NESTED `help`
    block (`help.instructions`, `help.format_hint`) that real form-kit schemas use
    (e.g. form-kits/i-90/schema.json: help.instructions on every field), with the
    flat keys as a fallback so the demo schema still renders. This is the single
    source of truth for a field's guidance: it feeds both the DTI system
    instruction (field 1) and the confirm_field tool response (fields 2..N), so the
    model sees identical guidance whichever path delivers it.

    PII-free schema only -- never user values.

    Args:
        field: A full field dict from the schema.

    Returns:
        A guidance dict, or None if no field. Keys: field_id, spoken_name, name,
        type, required, instructions, format_hint, options, validation. Absent keys
        are omitted (not null) to keep the rendered block lean.
    """
    if not field or not field.get("id"):
        return None

    help_block = field.get("help") if isinstance(field.get("help"), dict) else {}

    # instructions: nested help.instructions (canonical) -> flat help_text/description.
    instructions = (
        help_block.get("instructions")
        or field.get("help_text")
        or field.get("description")
    )
    # format_hint: nested help.format_hint (canonical) -> flat format.
    format_hint = help_block.get("format_hint") or field.get("format")

    guidance: dict = {
        "field_id": field.get("id"),
        "spoken_name": field.get("spoken_name") or field.get("name") or field.get("id"),
        "type": field.get("type", "text"),
    }
    if field.get("name"):
        guidance["name"] = field["name"]
    if field.get("required"):
        guidance["required"] = field["required"]
    if instructions:
        guidance["instructions"] = instructions
    if format_hint:
        guidance["format_hint"] = format_hint

    # Options for select/radio/checkbox (label/value pairs or bare values).
    # SANITIZE via the shared helper (bd polyglot-pdf-lj5v) so this DTI path
    # applies the SAME value/label/spoken_label boundary as the JIT
    # get_next_field_schema path -- never leak pdf_field_name/pdf_on_value/
    # pdf_position/label_translations into a model-facing payload.
    options = field.get("options") or field.get("allowed_values")
    if options:
        guidance["options"] = _sanitize_options(options)

    # Validation hints that help the model guide the user (no internal-only keys).
    validation = field.get("validation")
    if isinstance(validation, dict):
        minimal_validation = {
            k: validation[k]
            for k in ("format", "format_preset", "pattern", "min", "max",
                      "min_length", "max_length", "minLength", "maxLength")
            if k in validation
        }
        if minimal_validation:
            guidance["validation"] = minimal_validation
    # Flat placeholder as a last-resort example.
    if field.get("placeholder"):
        guidance.setdefault("example", field["placeholder"])

    return guidance


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

    # Use .get() with fallbacks: since A2 (bd polyglot-pdf-jnjj.9) this is fed the
    # CLIENT's handshake manifest fields (WebSocket data), so a malformed entry must
    # degrade gracefully, not KeyError and drop the connection mid-SI build.
    field_entries = []
    for field in current.get("fields", []):
        field_entries.append(f"{field.get('field_id', '')}|{field.get('spoken_name', '')}")

    lines.append("Fields: " + " | ".join(field_entries))

    # Previous parts (for cross-section queries)
    previous_parts = manifest.get("previous_parts", [])
    if previous_parts:
        lines.append("\nPREVIOUS PARTS (lookup only):")
        for part in previous_parts:
            part_fields = []
            for field in part.get("fields", []):
                part_fields.append(f"{field.get('field_id', '')}|{field.get('spoken_name', '')}")
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
