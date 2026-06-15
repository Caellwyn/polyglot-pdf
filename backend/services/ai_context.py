from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
from backend.config import get_settings
from backend.services.manifest_service import (
    format_manifest_for_context,
    get_next_field_schema
)


def get_confirmation_policy(section_number: int, total_sections: int) -> str:
    """Generate confirmation policy text based on section number.
    
    Args:
        section_number: Current section (1-indexed)
        total_sections: Total number of sections in form
        
    Returns:
        Confirmation policy text for system instruction
    """
    # NOTE: there is no complete_section tool -- section completion is auto-
    # detected by the frontend once all fields in a section are confirmed. The
    # model's job is to confirm each field (confirm_field); it must NOT be told
    # to call complete_section.
    if section_number <= 2:
        # First two sections: Full graduated end-of-section confirmation.
        # NOTE: per-field read-back ("read back value, ask Is that correct?")
        # is already in WORKFLOW step 3 of the system instruction -- do NOT
        # repeat it here or Gemini double-reads every field (bd polyglot-pdf-yn6q).
        # This block fires only when ALL fields in the section are confirmed.
        return (
            "When ALL fields in this section are confirmed: "
            "Read ALL fields back to user. "
            "Ask 'Would you like me to repeat any field?' "
            "Then ask 'Is everything correct?'"
        )
    elif section_number >= total_sections:
        # Last section: Extra careful final confirmation.
        # Same caveat as section <= 2: per-field confirm is WORKFLOW step 3;
        # this block is end-of-section only (bd polyglot-pdf-yn6q).
        return (
            "When ALL fields in this section are confirmed: "
            "Read ALL fields back to user. "
            "Ask 'Would you like me to repeat any field?' "
            "Then ask 'This is the last section - is everything correct?'"
        )
    else:
        # Middle sections: Simple end-of-section confirmation.
        # Same caveat as the other branches: per-field confirm is WORKFLOW
        # step 3; this block is end-of-section only (bd polyglot-pdf-yn6q).
        return (
            "When ALL fields in this section are confirmed: "
            "Say 'Section done. Ready for the next section?'"
        )


def build_form_context(
    schema: dict,
    current_values: dict,
    fill_language: str = "English",
    section_number: Optional[int] = None,
    total_sections: Optional[int] = None,
    section_label: Optional[str] = None,
    previous_spoken_names: Optional[List[str]] = None,
    next_field_hint: Optional[str] = None,
    is_reconnect: bool = False,
) -> str:
    """Build form context system instruction for AI.

    This system instruction provides the AI with complete form schema and current state.
    Uses Settings.SYSTEM_INSTRUCTION template for centralized configuration.

    Args:
        schema: Form schema with field definitions
        current_values: Current field values from client (may be pre-filled by user)
        fill_language: Language to use for filling form field values (default: English)
        section_number: Current section number (1-indexed), None for non-sectioned forms
        total_sections: Total number of sections, None for non-sectioned forms
        section_label: Human-readable section label (e.g., "Client Information")
        previous_spoken_names: List of spoken names from completed sections
    
    Returns:
        System instruction text
    """
    settings = get_settings()
    
    # Build field metadata with current values
    fields_info = []
    filled_count = 0
    
    for idx, field in enumerate(schema.get("fields", []), start=1):
        field_id = field.get("id")
        field_name = field.get("name")
        field_type = field.get("type", "text")
        required = field.get("required", False)
        
        # Check if this field has a current value
        current = current_values.get(field_id, "")
        field_info = {
            "order": idx,
            "id": field_id,
            "name": field_name,
            "type": field_type,
            "required": required,
            "filled": bool(current)
        }
        
        if current:
            field_info["current_value"] = current
            filled_count += 1
        
        # Add allowed values if present
        allowed_values = field.get("allowed_values") or field.get("options")
        if allowed_values:
            field_info["allowed_values"] = allowed_values
        
        # Add validation constraints
        if "format" in field:
            field_info["format"] = field.get("format")
        if "pattern" in field:
            field_info["pattern"] = field.get("pattern")
        if "min" in field:
            field_info["min"] = field.get("min")
        if "max" in field:
            field_info["max"] = field.get("max")
        if "minLength" in field:
            field_info["min"] = field.get("minLength")  # Use "min" in display for consistency
        if "maxLength" in field:
            field_info["max"] = field.get("maxLength")  # Use "max" in display
        if "placeholder" in field:
            field_info["placeholder"] = field.get("placeholder")
        if "description" in field:
            field_info["description"] = field.get("description")
        
        fields_info.append(field_info)
    
    form_title = schema.get("form_metadata", {}).get("title", "Form")
    total_fields = len(schema.get("fields", []))
    unfilled_count = total_fields - filled_count
    
    # Format fields in a more natural way to avoid JSON quote confusion
    # Build a clear text representation instead of JSON to prevent Gemini from
    # seeing field IDs like "reason[]" and returning them as "\"reason[]\""
    fields_lines = []
    for field_info in fields_info:
        field_id = field_info.get("id", "")
        field_name = field_info.get("name", "")
        field_type = field_info.get("type", "text")
        required = field_info.get("required", False)
        filled = field_info.get("filled", False)
        
        # Build field description line by line
        # Format: Field N | ID: field_id | Name: field_name | ...
        # This makes it crystal clear which is the ID to use in tool calls
        line_parts = [
            f"Field {field_info.get('order', '?')}",
            f"ID: {field_id}",
            f"Name: {field_name}",
            f"Type: {field_type}",
            f"Required: {required}",
            f"Filled: {filled}"
        ]
        
        if filled and "current_value" in field_info:
            line_parts.append(f"Current: {field_info['current_value']}")
        
        if "allowed_values" in field_info and field_info["allowed_values"]:
            allowed = field_info["allowed_values"]
            # Options are now guaranteed to be FieldOption objects (normalized at model level)
            # For radio/select fields, we need to show BOTH the label (what user hears/sees)
            # AND the value (what to send in the tool call)
            allowed_strs = []
            for opt in allowed:
                if isinstance(opt, dict):
                    # Extract both value and label
                    opt_value = opt.get("value", "")
                    opt_label = opt.get("label", "")
                    # Show label first (user-facing), then value (for tool call)
                    if opt_label and opt_value and opt_label != opt_value:
                        allowed_strs.append(f'"{opt_label}" (use value: {opt_value})')
                    elif opt_label:
                        allowed_strs.append(opt_label)
                    elif opt_value:
                        allowed_strs.append(opt_value)
                    else:
                        allowed_strs.append(str(opt))
                else:
                    # Fallback for non-dict options
                    allowed_strs.append(str(opt))

            if len(allowed_strs) <= 5:
                # Show all options if 5 or fewer
                line_parts.append(f"Options: [{', '.join(allowed_strs)}]")
            else:
                # Show first 3 and count for longer lists
                line_parts.append(f"Options: [{', '.join(allowed_strs[:3])}, ... ({len(allowed_strs)} total)]")
        
        # Add validation constraints if present
        if "format" in field_info and field_info["format"]:
            line_parts.append(f"Format: {field_info['format']}")
        
        if "min" in field_info:
            line_parts.append(f"Min: {field_info['min']}")
        
        if "max" in field_info:
            line_parts.append(f"Max: {field_info['max']}")
        
        if "pattern" in field_info and field_info["pattern"]:
            line_parts.append(f"Pattern: {field_info['pattern']}")
        
        if "placeholder" in field_info and field_info["placeholder"]:
            line_parts.append(f"Example: {field_info['placeholder']}")
        
        if "description" in field_info and field_info["description"]:
            line_parts.append(f"Note: {field_info['description']}")
        
        fields_lines.append(" | ".join(line_parts))
    
    fields_text = "\n".join(fields_lines)

    # Build section list for navigation
    # Format: "1. Personal Information, 2. Employment History, 3. References"
    # This helps Gemini understand section names, order, and handle requests like "go to last section"
    section_list_text = ""
    if schema.get("sections"):
        # Multi-section form - list all sections (NOT parts)
        # This is critical: Gemini must see section order (1-16 for I-90), not part order (1-8)
        section_items = []
        for section in schema.get("sections", []):
            order = section.get("order", "?")
            label = section.get("label", f"Section {order}")
            section_items.append(f"{order}. {label}")
        section_list_text = ", ".join(section_items)
    elif schema.get("parts"):
        # Fallback: If no sections array, use parts
        section_items = []
        for part in schema.get("parts", []):
            order = part.get("order", "?")
            label = part.get("label", f"Part {order}")
            section_items.append(f"{order}. {label}")
        section_list_text = ", ".join(section_items)
    else:
        # Single section form
        section_list_text = f"1. {form_title}"

    # Prepare section-specific context
    # Default values for non-sectioned forms (backward compatibility)
    section_num_text = section_number if section_number is not None else "1"
    total_sections_text = total_sections if total_sections is not None else "1"
    section_label_text = section_label if section_label else form_title
    
    # Format previous spoken names for field lookups
    # These are ALL the spoken names from completed sections that can be queried via get_field_value
    # The frontend maintains a spokenNameToFieldId map, so we need to give Gemini all available names
    if previous_spoken_names and len(previous_spoken_names) > 0:
        # Include ALL spoken names - user might want to look up any field from any previous section
        previous_names_text = (
            "Available fields from completed sections (use get_field_value with these exact names): " +
            ", ".join(previous_spoken_names)
        )
    else:
        previous_names_text = "None (this is the first section)"
    
    # Get confirmation policy based on section number
    if section_number is not None and total_sections is not None:
        confirmation_policy = get_confirmation_policy(section_number, total_sections)
    else:
        # Default policy for non-sectioned forms.
        # Per-field confirm is WORKFLOW step 3; this is end-of-form only
        # (bd polyglot-pdf-yn6q).
        confirmation_policy = (
            "When ALL fields are confirmed: "
            "Read ALL fields back to user. "
            "Ask 'Would you like me to repeat any field?' "
            "Then ask 'Is everything correct?'"
        )

    # Phase 2.6: JIT Schema Loading - Use manifest-first approach when enabled
    if settings.USE_JIT_SCHEMA:
        # Consume the section manifest the CLIENT sent on the handshake
        # (schema["manifest"]), NOT a manifest regenerated from schema["fields"]
        # -- in JIT mode schema["fields"] is only the synthesized first-field
        # schema, so regenerating would describe one field, not the section
        # (bd polyglot-pdf-jnjj.9; see docs/components/jit-schema.md gaps A/B/C/N).
        client_manifest = schema.get("manifest") or {}
        current_section = client_manifest.get("current_section") or {}
        # Section field list as {field_id, spoken_name} pairs (the real section).
        section_fields = current_section.get("fields", [])

        # Build the SI manifest text from the real section + previous sections,
        # so {manifest_text} lists every field in the section and the cheap
        # cross-section lookup block is populated (gaps A/B/C).
        manifest_for_context = {
            "current_part": {
                "part_id": current_section.get("section_id", section_label_text),
                "part_label": current_section.get("section_label", section_label_text),
                "fields": section_fields,
            },
            "previous_parts": [
                {
                    "part_id": prev.get("section_id", "unknown"),
                    "part_label": prev.get("section_label", "Unknown"),
                    "fields": prev.get("fields", []),
                }
                for prev in client_manifest.get("previous_sections", [])
            ],
        }
        manifest_text = format_manifest_for_context(manifest_for_context)

        # Recompute progress from the REAL section field set, not the one-field
        # schema["fields"] (gap N: "Progress: x/1" on every section otherwise).
        # Key on the manifest being PRESENT (current_section truthy), not on the
        # field list being non-empty -- an empty section must read 0/0, not fall
        # back to the one-field "x/1" symptom (fresh-eyes). With no manifest at all
        # (e.g. a legacy reconnect hitting this branch) keep the pre-branch values.
        if current_section:
            total_fields = len(section_fields)
            filled_count = sum(
                1 for f in section_fields if current_values.get(f.get("field_id"))
            )
            unfilled_count = total_fields - filled_count

        # Render the field schema the CLIENT sent as schema["fields"][0]. The
        # frontend now selects the first UNFILLED field (not the section's
        # positional first field), so on a reconnect/revisit the SI points at the
        # actual next field, not an already-confirmed one (gap D; the selection
        # lives in schemaFormState.getJITHandshakePayload). The backend renders
        # whatever single field-schema the handshake carried -- it does not hold
        # the other fields' full schemas in JIT mode (that is the point of JIT).
        first_field_schema = get_next_field_schema(schema, current_field_id=None)

        # Format first field schema as readable text (similar to fields_text format above)
        if first_field_schema:
            field_id = first_field_schema.get("id", "")
            field_name = first_field_schema.get("name", "")
            spoken_name = first_field_schema.get("spoken_name", field_name)
            field_type = first_field_schema.get("type", "text")
            required = first_field_schema.get("required", False)

            next_field_schema_text = f"ID: {field_id} | Spoken: {spoken_name} | Name: {field_name} | Type: {field_type} | Required: {required}"

            # Add options if present
            allowed_values = first_field_schema.get("allowed_values") or first_field_schema.get("options")
            if allowed_values:
                allowed_strs = []
                for opt in allowed_values:
                    if isinstance(opt, dict):
                        opt_value = opt.get("value", "")
                        opt_label = opt.get("label", "")
                        if opt_label and opt_value and opt_label != opt_value:
                            allowed_strs.append(f'"{opt_label}" (use value: {opt_value})')
                        elif opt_label:
                            allowed_strs.append(opt_label)
                        else:
                            allowed_strs.append(opt_value)
                    else:
                        allowed_strs.append(str(opt))

                next_field_schema_text += f" | Options: [{', '.join(allowed_strs)}]"
        else:
            next_field_schema_text = "No fields available"

        # Use JIT_SYSTEM_INSTRUCTION template
        system_instruction = settings.JIT_SYSTEM_INSTRUCTION.format(
            form_title=form_title,
            section_number=section_num_text,
            total_sections=total_sections_text,
            section_label=section_label_text,
            section_list=section_list_text,
            filled_count=filled_count,
            total_fields=total_fields,
            manifest_text=manifest_text,
            fill_language=fill_language,
            previous_spoken_names=previous_names_text,
            next_field_hint=next_field_hint or "the first unfilled field",
            next_field_schema=next_field_schema_text,
            confirmation_policy=confirmation_policy
        )
    else:
        # Legacy mode: Use full schema with SYSTEM_INSTRUCTION template
        system_instruction = settings.SYSTEM_INSTRUCTION.format(
            form_title=form_title,
            section_number=section_num_text,
            total_sections=total_sections_text,
            section_label=section_label_text,
            section_list=section_list_text,
            filled_count=filled_count,
            total_fields=total_fields,
            unfilled_count=unfilled_count,
            fields_json=fields_text,  # Still using fields_json placeholder name for compatibility
            fill_language=fill_language,
            previous_spoken_names=previous_names_text,
            confirmation_policy=confirmation_policy,
            next_field_hint=next_field_hint or "the first unfilled field"
        )

    # On mid-section reconnects, override any greet directive so Gemini resumes
    # silently rather than re-introducing the form/section (bd polyglot-pdf-vmxx).
    if is_reconnect:
        system_instruction = (
            system_instruction
            + "\n\nRESUME: The user has reconnected mid-session. "
            "Do NOT greet them. Do NOT re-introduce the form or section. "
            "Simply ask for the next field as if continuing naturally."
        )

    return system_instruction
