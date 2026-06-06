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


def normalize_value(field: Dict[str, Any], value: Any) -> Any:
    """Normalize a raw input value to the field's canonical stored form.

    Keyed on the field's format_preset so user/AI input can be accepted in the
    natural way it is spoken or written and still satisfy the strict pattern.
    Currently handles a_number: an Alien Registration Number is spoken/written as
    "A" + 7-9 digits (often with dashes or spaces), but the PDF comb field stores
    bare digits (pattern ^\\d{7,9}$, 9 cells). So we strip a leading A/a and all
    non-digits, leaving the canonical digits. Non-a_number fields and non-string
    values pass through unchanged (bd polyglot-pdf-0zr).
    """
    preset = field.get("format_preset")
    if preset == "a_number" and isinstance(value, str):
        stripped = value.strip()
        # Drop a single leading A/a (the A-Number prefix), then keep only digits.
        if stripped[:1] in ("A", "a"):
            stripped = stripped[1:]
        digits = re.sub(r"\D", "", stripped)
        return digits
    return value


def validate_field_value(field: Dict[str, Any], value: Any) -> List[ValidationError]:
    """
    Validate a field value against its schema constraints.

    Args:
        field: Field schema dict with id, name, type, and constraint properties
        value: The value to validate

    Returns:
        List of ValidationError objects (empty list if valid)
        Multiple errors can be returned to inform user of all violations
    """
    field_id = field.get("id", "")
    field_name = field.get("name", field_id)
    field_type = field.get("type", "text")

    # Skip validation for null/empty values (let required validation handle that)
    if value is None or value == "":
        return []

    # Type-specific validations - now returns list of errors
    if field_type in ["number", "tel"]:
        return _validate_number(field, value, field_id, field_name)
    elif field_type == "date":
        return _validate_date(field, value, field_id, field_name)
    elif field_type in ["text", "email", "textarea"]:
        return _validate_text(field, value, field_id, field_name)
    elif field_type in ["select", "radio"]:
        return _validate_select(field, value, field_id, field_name)
    elif field_type == "checkbox":
        return _validate_checkbox(field, value, field_id, field_name)

    return []


def _validate_number(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> List[ValidationError]:
    """Validate number field against min/max constraints

    Returns list of all validation errors (can be multiple)
    """
    errors = []

    try:
        num_value = float(value)
    except (ValueError, TypeError):
        errors.append(ValidationError(
            field_id, field_name, value, "type",
            f"Not a valid number"
        ))
        return errors  # If not a number, can't check min/max

    # Check min constraint
    if "min" in field:
        min_val = field["min"]
        if num_value < min_val:
            errors.append(ValidationError(
                field_id, field_name, value, "min",
                f"Below minimum ({min_val})",
                constraint_value=min_val
            ))

    # Check max constraint
    if "max" in field:
        max_val = field["max"]
        if num_value > max_val:
            errors.append(ValidationError(
                field_id, field_name, value, "max",
                f"Exceeds maximum ({max_val})",
                constraint_value=max_val
            ))

    return errors


def _validate_date(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> List[ValidationError]:
    """Validate date field against format, min/max, and date_constraint

    Returns list of all validation errors (can be multiple)
    """
    value_str = str(value)
    errors = []

    # Check format (expect YYYY-MM-DD)
    format_pattern = field.get("format", "YYYY-MM-DD")
    if format_pattern == "YYYY-MM-DD":
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', value_str):
            errors.append(ValidationError(
                field_id, field_name, value, "format",
                f"Invalid format (expected YYYY-MM-DD)",
                constraint_value=format_pattern
            ))
            return errors  # If format is invalid, can't check other constraints

        # Try to parse the date
        try:
            date_obj = datetime.strptime(value_str, "%Y-%m-%d")
        except ValueError:
            errors.append(ValidationError(
                field_id, field_name, value, "format",
                f"Invalid date",
                constraint_value=format_pattern
            ))
            return errors  # If date is invalid, can't check other constraints

        # Check date_constraint (past_only, future_only, within_5_years)
        today = datetime.now()
        date_constraint = field.get("date_constraint")

        if date_constraint == "past_only":
            if date_obj > today:
                errors.append(ValidationError(
                    field_id, field_name, value, "date_constraint",
                    f"Date must be in the past",
                    constraint_value="past_only"
                ))
        elif date_constraint == "future_only":
            if date_obj < today:
                errors.append(ValidationError(
                    field_id, field_name, value, "date_constraint",
                    f"Date must be in the future",
                    constraint_value="future_only"
                ))
        elif date_constraint == "within_5_years":
            # Check if date is within 5 years of today (past or future)
            from datetime import timedelta
            five_years_ago = today - timedelta(days=365*5)
            five_years_from_now = today + timedelta(days=365*5)
            if date_obj < five_years_ago or date_obj > five_years_from_now:
                errors.append(ValidationError(
                    field_id, field_name, value, "date_constraint",
                    f"Date must be within 5 years of today",
                    constraint_value="within_5_years"
                ))

        # Check min constraint (minimum date)
        if "min" in field:
            try:
                min_date = datetime.strptime(str(field["min"]), "%Y-%m-%d")
                if date_obj < min_date:
                    errors.append(ValidationError(
                        field_id, field_name, value, "min",
                        f"Date cannot be before {field['min']}",
                        constraint_value=field["min"]
                    ))
            except ValueError:
                pass  # Invalid min constraint, skip

        # Check max constraint (maximum date)
        if "max" in field:
            try:
                max_date = datetime.strptime(str(field["max"]), "%Y-%m-%d")
                if date_obj > max_date:
                    errors.append(ValidationError(
                        field_id, field_name, value, "max",
                        f"Date cannot be after {field['max']}",
                        constraint_value=field["max"]
                    ))
            except ValueError:
                pass  # Invalid max constraint, skip

    return errors


def _validate_text(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> List[ValidationError]:
    """Validate text field against pattern, minLength, maxLength, digits_only constraints

    Returns list of all validation errors (can be multiple)
    """
    value_str = str(value)
    errors = []

    # Check digits_only constraint
    if field.get("digits_only") is True:
        if not value_str.isdigit():
            errors.append(ValidationError(
                field_id, field_name, value, "digits_only",
                f"Must contain only digits (0-9)",
                constraint_value=True
            ))

    # Check minLength
    if "minLength" in field:
        min_len = field["minLength"]
        if len(value_str) < min_len:
            errors.append(ValidationError(
                field_id, field_name, value, "minLength",
                f"Too short (minimum {min_len} characters)",
                constraint_value=min_len
            ))

    # Check maxLength
    if "maxLength" in field:
        max_len = field["maxLength"]
        if len(value_str) > max_len:
            errors.append(ValidationError(
                field_id, field_name, value, "maxLength",
                f"Too long (maximum {max_len} characters)",
                constraint_value=max_len
            ))

    # Check pattern (regex)
    if "pattern" in field:
        pattern = field["pattern"]
        if not re.match(pattern, value_str):
            errors.append(ValidationError(
                field_id, field_name, value, "pattern",
                f"Invalid format",
                constraint_value=pattern
            ))

    return errors


def _validate_select(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> List[ValidationError]:
    """Validate select/radio field against options list

    Returns list of validation errors (usually 0 or 1 for select fields)
    """
    options = field.get("options", [])
    if not options:
        return []  # No options defined, can't validate

    value_str = str(value)

    # Extract valid values from options (handle both string and dict formats)
    valid_values = []
    for opt in options:
        if isinstance(opt, dict):
            # Option is {value: "...", label: "..."}
            opt_value = opt.get("value")
            if opt_value is not None:
                valid_values.append(str(opt_value))
        else:
            # Option is a plain string
            valid_values.append(str(opt))

    # Check if value is in valid values
    if value_str not in valid_values:
        return [ValidationError(
            field_id, field_name, value, "options",
            f"Invalid option",
            valid_options=valid_values
        )]

    return []


def _validate_checkbox(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> List[ValidationError]:
    """Validate checkbox field against options list (for checkbox groups)

    Returns list of validation errors (can be multiple for checkbox groups)
    """
    options = field.get("options", [])
    if not options:
        # Simple boolean checkbox, validate as boolean
        if not isinstance(value, bool) and value not in ["true", "false", True, False]:
            return [ValidationError(
                field_id, field_name, value, "type",
                f"Must be boolean"
            )]
        return []

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
        return [ValidationError(
            field_id, field_name, value, "options",
            f"Invalid: {', '.join(invalid_values)}",
            valid_options=options
        )]

    return []


def validate_updates(fields: List[Dict[str, Any]], updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate all field updates against schema constraints.

    Args:
        fields: List of field schemas
        updates: Dict mapping field_id to value

    Returns:
        Dict with:
        - valid_fields: List of field IDs that passed validation
        - validation_errors: List of ValidationError dicts for failed fields (can be multiple per field)
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

        # Normalize to the canonical stored form BEFORE validating, so input that
        # is correct-but-differently-formatted (e.g. an A-Number with its "A"
        # prefix) is accepted and the canonical value is what gets validated,
        # stored, and written to the PDF (bd polyglot-pdf-0zr).
        normalized = normalize_value(field, value)

        # validate_field_value now returns a list of errors
        errors = validate_field_value(field, normalized)
        if errors:
            # Add all errors for this field to the list (report against the
            # normalized value -- that is what failed the constraint).
            for error in errors:
                validation_errors.append(error.to_dict())
        else:
            # No errors - field is valid; store the NORMALIZED value so the
            # client/PDF receive the canonical form, not the raw input.
            valid_fields.append(field_id)
            form_state[field_id] = normalized

    return {
        "valid_fields": valid_fields,
        "validation_errors": validation_errors,
        "form_state": form_state
    }
