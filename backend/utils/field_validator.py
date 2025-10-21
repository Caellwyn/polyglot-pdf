"""
Field Validator - Validates field values against schema constraints

This module validates field values against their schema-defined constraints
(min, max, pattern, format, etc.) and returns detailed error messages that
can be sent back to the AI to prompt correction.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import re


class ValidationError:
    """Represents a field validation error"""
    
    def __init__(self, field_id: str, field_name: str, value: Any, constraint: str, message: str, 
                 constraint_value: Any = None, valid_options: Optional[List[str]] = None):
        self.field_id = field_id
        self.field_name = field_name
        self.value = value
        self.constraint = constraint
        self.message = message
        self.constraint_value = constraint_value  # The actual constraint (e.g., max=120)
        self.valid_options = valid_options  # For select/checkbox, the valid options
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "field_id": self.field_id,
            "field_name": self.field_name,
            "value": self.value,
            "constraint": self.constraint,
            "message": self.message
        }
        if self.constraint_value is not None:
            result["constraint_value"] = self.constraint_value
        if self.valid_options is not None:
            result["valid_options"] = self.valid_options
        return result


def validate_field_value(field: Dict[str, Any], value: Any) -> Optional[ValidationError]:
    """
    Validate a field value against its schema constraints.
    
    Args:
        field: Field schema dict with id, name, type, and constraint properties
        value: The value to validate
    
    Returns:
        ValidationError if validation fails, None if valid
    """
    field_id = field.get("id", "")
    field_name = field.get("name", field_id)
    field_type = field.get("type", "text")
    
    # Skip validation for null/empty values (let required validation handle that)
    if value is None or value == "":
        return None
    
    # Type-specific validations
    if field_type in ["number", "tel"]:
        return _validate_number(field, value, field_id, field_name)
    elif field_type == "date":
        return _validate_date(field, value, field_id, field_name)
    elif field_type in ["text", "email", "textarea"]:
        return _validate_text(field, value, field_id, field_name)
    elif field_type == "select":
        return _validate_select(field, value, field_id, field_name)
    elif field_type == "checkbox":
        return _validate_checkbox(field, value, field_id, field_name)
    
    return None


def _validate_number(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> Optional[ValidationError]:
    """Validate number field against min/max constraints"""
    try:
        num_value = float(value)
    except (ValueError, TypeError):
        return ValidationError(
            field_id, field_name, value, "type",
            f"Not a valid number"
        )
    
    # Check min constraint
    if "min" in field:
        min_val = field["min"]
        if num_value < min_val:
            return ValidationError(
                field_id, field_name, value, "min",
                f"Below minimum",
                constraint_value=min_val
            )
    
    # Check max constraint
    if "max" in field:
        max_val = field["max"]
        if num_value > max_val:
            return ValidationError(
                field_id, field_name, value, "max",
                f"Exceeds maximum",
                constraint_value=max_val
            )
    
    return None


def _validate_date(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> Optional[ValidationError]:
    """Validate date field against format and min/max constraints"""
    value_str = str(value)
    
    # Check format (expect YYYY-MM-DD)
    format_pattern = field.get("format", "YYYY-MM-DD")
    if format_pattern == "YYYY-MM-DD":
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', value_str):
            return ValidationError(
                field_id, field_name, value, "format",
                f"Invalid format",
                constraint_value=format_pattern
            )
        
        # Try to parse the date
        try:
            date_obj = datetime.strptime(value_str, "%Y-%m-%d")
        except ValueError:
            return ValidationError(
                field_id, field_name, value, "format",
                f"Invalid date",
                constraint_value=format_pattern
            )
        
        # Check min constraint (minimum date)
        if "min" in field:
            try:
                min_date = datetime.strptime(str(field["min"]), "%Y-%m-%d")
                if date_obj < min_date:
                    return ValidationError(
                        field_id, field_name, value, "min",
                        f"Before minimum date",
                        constraint_value=field["min"]
                    )
            except ValueError:
                pass  # Invalid min constraint, skip
        
        # Check max constraint (maximum date)
        if "max" in field:
            try:
                max_date = datetime.strptime(str(field["max"]), "%Y-%m-%d")
                if date_obj > max_date:
                    return ValidationError(
                        field_id, field_name, value, "max",
                        f"After maximum date",
                        constraint_value=field["max"]
                    )
            except ValueError:
                pass  # Invalid max constraint, skip
    
    return None


def _validate_text(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> Optional[ValidationError]:
    """Validate text field against pattern, minLength, maxLength constraints"""
    value_str = str(value)
    
    # Check minLength
    if "minLength" in field:
        min_len = field["minLength"]
        if len(value_str) < min_len:
            return ValidationError(
                field_id, field_name, value, "minLength",
                f"Too short",
                constraint_value=min_len
            )
    
    # Check maxLength
    if "maxLength" in field:
        max_len = field["maxLength"]
        if len(value_str) > max_len:
            return ValidationError(
                field_id, field_name, value, "maxLength",
                f"Too long",
                constraint_value=max_len
            )
    
    # Check pattern (regex)
    if "pattern" in field:
        pattern = field["pattern"]
        if not re.match(pattern, value_str):
            return ValidationError(
                field_id, field_name, value, "pattern",
                f"Invalid pattern",
                constraint_value=pattern
            )
    
    return None


def _validate_select(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> Optional[ValidationError]:
    """Validate select/radio field against options list"""
    options = field.get("options", [])
    if not options:
        return None  # No options defined, can't validate
    
    value_str = str(value)
    
    # Check if value is in options
    if value_str not in options:
        return ValidationError(
            field_id, field_name, value, "options",
            f"Invalid option",
            valid_options=options
        )
    
    return None


def _validate_checkbox(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> Optional[ValidationError]:
    """Validate checkbox field against options list (for checkbox groups)"""
    options = field.get("options", [])
    if not options:
        # Simple boolean checkbox, validate as boolean
        if not isinstance(value, bool) and value not in ["true", "false", True, False]:
            return ValidationError(
                field_id, field_name, value, "type",
                f"Must be boolean"
            )
        return None
    
    # Checkbox group - value should be comma-separated list of options
    if isinstance(value, str):
        selected_values = [v.strip() for v in value.split(",")]
    elif isinstance(value, list):
        selected_values = [str(v) for v in value]
    else:
        selected_values = [str(value)]
    
    # Check each selected value is in options
    invalid_values = [v for v in selected_values if v not in options]
    if invalid_values:
        return ValidationError(
            field_id, field_name, value, "options",
            f"Invalid: {', '.join(invalid_values)}",
            valid_options=options
        )
    
    return None


def validate_updates(fields: List[Dict[str, Any]], updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate all field updates against schema constraints.
    
    Args:
        fields: List of field schemas
        updates: Dict mapping field_id to value
    
    Returns:
        Dict with:
        - valid_fields: List of field IDs that passed validation
        - validation_errors: List of ValidationError dicts for failed fields
        - form_state: Dict of field_id -> value for valid fields only
    """
    field_map = {f.get("id"): f for f in fields if f.get("id")}
    
    valid_fields = []
    validation_errors = []
    form_state = {}
    
    for field_id, value in updates.items():
        field = field_map.get(field_id)
        if not field:
            # Field not in schema, skip (will be caught as unknown_field elsewhere)
            continue
        
        error = validate_field_value(field, value)
        if error:
            validation_errors.append(error.to_dict())
        else:
            valid_fields.append(field_id)
            form_state[field_id] = value
    
    return {
        "valid_fields": valid_fields,
        "validation_errors": validation_errors,
        "form_state": form_state
    }
