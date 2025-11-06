from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
from backend.config import get_settings


def get_confirmation_policy(section_number: int, total_sections: int) -> str:
    """Generate confirmation policy text based on section number.
    
    Args:
        section_number: Current section (1-indexed)
        total_sections: Total number of sections in form
        
    Returns:
        Confirmation policy text for system instruction
    """
    if section_number <= 2:
        # First two sections: Full graduated confirmation
        return (
            "Read ALL fields back to user. "
            "Ask 'Would you like me to repeat any field?' "
            "Then ask 'Is everything correct?' "
            "Only call complete_section after user confirms."
        )
    elif section_number >= total_sections:
        # Last section: Extra careful final confirmation
        return (
            "Read ALL fields back to user. "
            "Ask 'Would you like me to repeat any field?' "
            "Then ask 'This is the last section - is everything correct?' "
            "Only call complete_section after user confirms."
        )
    else:
        # Middle sections: Simple confirmation
        return (
            "Say 'Section done. Ready for the next section?' "
            "Only call complete_section after user confirms."
        )


def build_form_context(
    schema: dict,
    current_values: dict,
    fill_language: str = "English",
    section_number: Optional[int] = None,
    total_sections: Optional[int] = None,
    section_label: Optional[str] = None,
    previous_spoken_names: Optional[List[str]] = None,
    next_field_hint: Optional[str] = None
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
            # Extract labels for display
            allowed_strs = [
                opt.get("label") or opt.get("value", str(opt)) if isinstance(opt, dict) else opt.label
                for opt in allowed
            ]
            
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
        # Default policy for non-sectioned forms
        confirmation_policy = (
            "Read ALL fields back to user. "
            "Ask 'Would you like me to repeat any field?' "
            "Then ask 'Is everything correct?' "
            "Only proceed after user confirms."
        )

    # Use SYSTEM_INSTRUCTION template from settings
    system_instruction = settings.SYSTEM_INSTRUCTION.format(
        form_title=form_title,
        section_number=section_num_text,
        total_sections=total_sections_text,
        section_label=section_label_text,
        filled_count=filled_count,
        total_fields=total_fields,
        unfilled_count=unfilled_count,
        fields_json=fields_text,  # Still using fields_json placeholder name for compatibility
        fill_language=fill_language,
        previous_spoken_names=previous_names_text,
        confirmation_policy=confirmation_policy,
        next_field_hint=next_field_hint or "the first unfilled field"
    )
    
    return system_instruction
