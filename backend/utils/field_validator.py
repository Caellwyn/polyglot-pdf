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


# Digit-only field presets: input is a sequence of digits, but speech-to-text and
# natural phrasing routinely add PUNCTUATION (commas, a "$", spaces, dashes, dots).
# The stored/validated form is bare digits, so normalize_value strips that
# punctuation BEFORE the length/pattern check (bd polyglot-pdf-jnjj.40). a_number
# ALSO drops a single leading "A" prefix. CRUCIALLY, only punctuation is stripped --
# embedded LETTERS are left in place so a genuinely wrong value (e.g. "ABC1234...")
# stays invalid instead of being silently coerced to digits (Codex PR #249).
_DIGIT_PRESETS = frozenset({"a_number", "uscis_account"})
# Punctuation/formatting characters STT and humans add to digit strings. Letters
# are deliberately NOT in this class.
_DIGIT_PUNCT_RE = re.compile(r"[\s,.$-]")


def _resolve_constraint(field: Dict[str, Any], top_key: str, nested_key: str) -> Any:
    """Resolve a validation constraint from the CANONICAL nested location
    (validation.<snake_case>) with a fallback to the flattened TOP-LEVEL key.

    validation_handler pre-flattens validation.* to top-level camelCase keys
    (minLength, maxLength, ...), but raw schema-shaped dicts (form-kits/*/
    schema.json, tests, any future non-WS caller) keep constraints nested under
    `validation` in snake_case (min_length, max_length, pattern, ...). Reading
    the top level alone silently skipped ALL pattern/length/min/max validation
    for nested callers (bd polyglot-pdf-0mv2; parallel to the format_preset miss
    fixed in bd polyglot-pdf-cn0e). `validation` may be a dict or a Pydantic
    model, so read it tolerantly. Returns None when the constraint is absent.

    The TOP-LEVEL fallback also tries BOTH forms (bd polyglot-pdf-1dz2): a real
    on-disk kit (form-kits/w7/schema.json's date_of_entry_us) carries the
    constraint as a top-level SNAKE_CASE key with no `validation` block at all
    -- trying only `top_key` (camelCase) there silently dropped the constraint.
    """
    validation = field.get("validation")
    if isinstance(validation, dict):
        for key in (nested_key, top_key):
            value = validation.get(key)
            if value is not None:
                return value
    elif validation is not None:
        value = getattr(validation, nested_key, None)
        if value is not None:
            return value
    for key in (top_key, nested_key):
        value = field.get(key)
        if value is not None:
            return value
    return None


def _resolve_format_preset(field: Dict[str, Any]) -> Optional[str]:
    """Resolve a field's format_preset from the CANONICAL nested location
    (validation.format_preset) with a legacy TOP-LEVEL fallback.

    The schema (form-kits/*/schema.json) and the FormField model nest it under
    `validation`; only some callers (validation_handler) pre-flatten it to the top
    level. Reading one location alone misses the other (bd polyglot-pdf-cn0e).
    `validation` may be a dict or a Pydantic model, so read it tolerantly.
    """
    validation = field.get("validation")
    if isinstance(validation, dict):
        nested = validation.get("format_preset")
        if nested is not None:
            return nested
    elif validation is not None:
        nested = getattr(validation, "format_preset", None)
        if nested is not None:
            return nested
    return field.get("format_preset")


def normalize_value(field: Dict[str, Any], value: Any) -> Any:
    """Normalize a raw input value to the field's canonical stored form.

    Keyed on the field's format_preset so user/AI input can be accepted in the
    natural way it is spoken or written and still satisfy the strict pattern.
    Digit-only presets (a_number, uscis_account -- see _DIGIT_PRESETS): an Alien
    Registration Number is spoken as "A" + 7-9 digits and a USCIS account number as
    12 digits, but speech-to-text formats them with commas / a "$" / spaces (e.g.
    Gemini transcribed the spoken digits as "$1,234,567,890", which failed the
    length check and stalled DTI -- bd polyglot-pdf-jnjj.40). So we drop a single
    leading A/a (a_number only) and strip PUNCTUATION (_DIGIT_PUNCT_RE), leaving the
    canonical digits the comb field stores. Embedded LETTERS are kept (not stripped)
    so a wrong value like "ABC123456789012" stays invalid rather than being coerced
    to digits (Codex PR #249). Non-digit-preset fields and non-string values pass
    through unchanged (bd polyglot-pdf-0zr).

    format_preset is resolved from validation.format_preset (the CANONICAL location
    in the schema and the FormField model) with a TOP-LEVEL fallback for callers
    that pre-flatten it (e.g. validation_handler). Reading only the top level missed
    the nested location and silently no-op'd normalization, so a real "A12345678"
    A-Number failed the digits-only (7-9 digit) pattern (bd polyglot-pdf-cn0e).
    """
    preset = _resolve_format_preset(field)
    if preset in _DIGIT_PRESETS and isinstance(value, str):
        stripped = value.strip()
        # Drop a single leading A/a -- the A-Number prefix. ONLY for a_number:
        # uscis_account is pure digits, so a leading letter there is an error to
        # preserve, not a prefix to drop.
        if preset == "a_number" and stripped[:1] in ("A", "a"):
            stripped = stripped[1:]
        # Strip punctuation only; KEEP any remaining letters so validation rejects
        # them rather than silently dropping them.
        return _DIGIT_PUNCT_RE.sub("", stripped)
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
    elif field_type in ["checkbox", "checkbox_group"]:
        # checkbox_group (schema v2, bd h76m.17) shares the checkbox path:
        # _validate_checkbox handles both the standalone-bool shape and the
        # options-bearing group shape (list OR voice-path comma string).
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

    # Check min constraint. min/max may carry a DATE-STRING bound when authored
    # against a date-typed field (bd polyglot-pdf-ondn widened ValidationRules
    # to accept that) -- on a NUMBER field that shape is an authoring mistake,
    # not a value to compare against, so skip it rather than crash the whole
    # validate_field_value call on a TypeError (`'<' not supported between
    # instances of 'float' and 'str'`). A NUMERIC-looking string (e.g. "18")
    # is coerced to float by ValidationRules' own field_validator before it
    # ever reaches here when the caller goes through the real Pydantic model
    # -- this isinstance guard is defense-in-depth for a raw-dict caller
    # (tests, any future non-Pydantic path), which bypasses that coercion
    # entirely and could still hand this function a bare numeric string.
    min_val = _resolve_constraint(field, "min", "min")
    if isinstance(min_val, (int, float)) and not isinstance(min_val, bool):
        if num_value < min_val:
            errors.append(ValidationError(
                field_id, field_name, value, "min",
                f"Below minimum ({min_val})",
                constraint_value=min_val
            ))

    # Check max constraint
    max_val = _resolve_constraint(field, "max", "max")
    if isinstance(max_val, (int, float)) and not isinstance(max_val, bool):
        if num_value > max_val:
            errors.append(ValidationError(
                field_id, field_name, value, "max",
                f"Exceeds maximum ({max_val})",
                constraint_value=max_val
            ))

    return errors


# Date layouts this validator understands, as (strptime directive, human label).
# Keyed by a NORMALIZED format spec (lowercased, whitespace-stripped) so a kit
# may declare "MM/DD/YYYY", "mm/dd/yyyy", or the DateFormat enum's value and all
# resolve to the same layout. Mirrors backend/models/form_models.py DateFormat.
_DATE_LAYOUTS: Dict[str, tuple] = {
    "mm/dd/yyyy": ("%m/%d/%Y", "MM/DD/YYYY"),
    "dd/mm/yyyy": ("%d/%m/%Y", "DD/MM/YYYY"),
    "yyyy-mm-dd": ("%Y-%m-%d", "YYYY-MM-DD"),
    "mm-dd-yyyy": ("%m-%d-%Y", "MM-DD-YYYY"),
    "mo/yr": ("%m/%Y", "MM/YYYY"),
    "mm/yyyy": ("%m/%Y", "MM/YYYY"),
    "yyyy": ("%Y", "YYYY"),
}

# The layout assumed when a field declares no format at all. ISO stays the
# default for format-less fields so existing callers/tests are unaffected.
_DEFAULT_DATE_SPEC = "yyyy-mm-dd"


def _resolve_date_format(field: Dict[str, Any]) -> tuple:
    """Resolve the (strptime_directive, human_label) a date field expects.

    Reads the format spec from every place a kit may declare it, in priority
    order: the flat `format` key (DateFormat enum value), then the CANONICAL
    nested `help.format_hint` -- the property the schema editor's "Format Hint"
    box writes and the ONLY one the shipped kits populate for dates -- then
    `validation.hint`.

    Why this matters (bd polyglot-pdf-52qm era): this used to read ONLY the flat
    `format` key and hardcode a YYYY-MM-DD fallback. No shipped kit sets `format`
    on a date field (i-90 / w7 both carry help.format_hint = "MM/DD/YYYY"), and
    validation_handler did not pass `format` through either, so EVERY date field
    fell back to ISO -- and a correctly-filled "10/25/1984" was rejected as
    "Invalid format (expected YYYY-MM-DD)". The voice model, which IS told
    MM/DD/YYYY via the same help.format_hint, then adapted to the error text and
    started asking users for year-first dates.

    A hint may be prose ('MM/DD/YYYY or "Never Entered US"'); match the first
    recognized layout token inside it rather than requiring an exact string.
    Returns the ISO default when nothing recognizable is declared.
    """
    help_block = field.get("help")
    hint_sources = [field.get("format")]
    if isinstance(help_block, dict):
        hint_sources.append(help_block.get("format_hint"))
    elif help_block is not None:
        hint_sources.append(getattr(help_block, "format_hint", None))
    hint_sources.append(_resolve_constraint(field, "hint", "hint"))

    for raw in hint_sources:
        if raw is None:
            continue
        # Unwrap a (str, Enum) member (DateFormat.MM_DD_YYYY -> "mm/dd/yyyy").
        spec = str(getattr(raw, "value", raw)).strip().lower()
        if not spec:
            continue
        if spec in _DATE_LAYOUTS:
            return _DATE_LAYOUTS[spec]
        # Prose hint (e.g. 'MM/DD/YYYY or "Never Entered US"'): pick the layout
        # token that appears EARLIEST in the sentence, breaking ties on the
        # LONGEST token. Position must dominate length, or a hint naming two
        # layouts ("Use DD/MM/YYYY not MM/DD/YYYY") would resolve to whichever
        # token the dict happened to yield first among equal-length candidates
        # -- silently picking the layout the author explicitly ruled OUT.
        # Length still breaks ties so a bare "yyyy" inside "mm/dd/yyyy" (same
        # start index is impossible, but "yyyy-mm-dd" vs "yyyy" is not) cannot
        # shadow the longer, more specific layout.
        best = None  # (start_index, -len(token), token)
        for token in _DATE_LAYOUTS:
            idx = spec.find(token)
            if idx == -1:
                continue
            candidate = (idx, -len(token), token)
            if best is None or candidate < best:
                best = candidate
        if best is not None:
            return _DATE_LAYOUTS[best[2]]

    return _DATE_LAYOUTS[_DEFAULT_DATE_SPEC]


def _validate_date(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> List[ValidationError]:
    """Validate date field against its DECLARED format, min/max, and date_constraint

    Returns list of all validation errors (can be multiple)
    """
    value_str = str(value).strip()
    errors = []

    directive, label = _resolve_date_format(field)

    # Parse against the field's OWN declared layout. strptime is the single
    # gate -- it rejects both a wrong layout and an impossible date (13/45/2020),
    # so a separate regex pre-check would only duplicate it (and previously
    # hardcoded ISO). Constraint checks below are deliberately OUTSIDE any
    # format branch: they used to be nested under `if format == "YYYY-MM-DD"`,
    # so a non-ISO field silently skipped date_constraint/min/max entirely.
    try:
        date_obj = datetime.strptime(value_str, directive)
    except ValueError:
        errors.append(ValidationError(
            field_id, field_name, value, "format",
            f"Invalid date (expected {label})",
            constraint_value=label
        ))
        return errors  # If the date will not parse, no other constraint is checkable

    # Check date_constraint (past_only, future_only, within_5_years)
    today = datetime.now()
    date_constraint = _resolve_constraint(field, "date_constraint", "date_constraint")

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

    # Check min/max constraints. A bound may be authored in the field's own
    # layout OR in ISO; try both before giving up (an unparseable bound is
    # skipped, not reported as a user error -- it is an authoring mistake).
    def _parse_bound(raw: Any):
        for fmt in (directive, "%Y-%m-%d"):
            try:
                return datetime.strptime(str(raw).strip(), fmt)
            except ValueError:
                continue
        return None

    min_constraint = _resolve_constraint(field, "min", "min")
    if min_constraint is not None:
        min_date = _parse_bound(min_constraint)
        if min_date is not None and date_obj < min_date:
            errors.append(ValidationError(
                field_id, field_name, value, "min",
                f"Date cannot be before {min_constraint}",
                constraint_value=min_constraint
            ))

    max_constraint = _resolve_constraint(field, "max", "max")
    if max_constraint is not None:
        max_date = _parse_bound(max_constraint)
        if max_date is not None and date_obj > max_date:
            errors.append(ValidationError(
                field_id, field_name, value, "max",
                f"Date cannot be after {max_constraint}",
                constraint_value=max_constraint
            ))

    return errors


def _validate_text(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> List[ValidationError]:
    """Validate text field against pattern, minLength, maxLength, digits_only constraints

    Returns list of all validation errors (can be multiple)
    """
    value_str = str(value)
    errors = []

    # Check digits_only constraint
    if _resolve_constraint(field, "digits_only", "digits_only") is True:
        if not value_str.isdigit():
            errors.append(ValidationError(
                field_id, field_name, value, "digits_only",
                f"Must contain only digits (0-9)",
                constraint_value=True
            ))

    # Check minLength
    min_len = _resolve_constraint(field, "minLength", "min_length")
    if min_len is not None:
        if len(value_str) < min_len:
            errors.append(ValidationError(
                field_id, field_name, value, "minLength",
                f"Too short (minimum {min_len} characters)",
                constraint_value=min_len
            ))

    # Check maxLength
    max_len = _resolve_constraint(field, "maxLength", "max_length")
    if max_len is not None:
        if len(value_str) > max_len:
            errors.append(ValidationError(
                field_id, field_name, value, "maxLength",
                f"Too long (maximum {max_len} characters)",
                constraint_value=max_len
            ))

    # Check pattern (regex)
    pattern = _resolve_constraint(field, "pattern", "pattern")
    if pattern is not None:
        if not re.match(pattern, value_str):
            errors.append(ValidationError(
                field_id, field_name, value, "pattern",
                f"Invalid format",
                constraint_value=pattern
            ))

    return errors


def _option_values(options: List[Any]) -> List[str]:
    """Extract the comparable string values from a field's options list.

    Options come in two schema shapes: plain strings, or {value, label} dicts
    (the generated form-kits use the dict shape). Both select/radio and checkbox
    validation -- and the error message that lists "valid=..." options -- need the
    bare string values, never the dict objects. Returning dicts here was the d24n
    bug: a dict-shaped option reached `", ".join(valid_options)` in
    callback_handler._build_update_fields_response and raised
    `TypeError: sequence item 0: expected str instance, dict found`, which the
    Live adapter swallowed -- silently failing the update_form_fields call
    (bd polyglot-pdf-jnjj.1 / d24n).
    """
    values: List[str] = []
    for opt in options:
        if isinstance(opt, dict):
            opt_value = opt.get("value")
            if opt_value is not None:
                values.append(str(opt_value))
        else:
            values.append(str(opt))
    return values


def _validate_select(field: Dict[str, Any], value: Any, field_id: str, field_name: str) -> List[ValidationError]:
    """Validate select/radio field against options list

    Returns list of validation errors (usually 0 or 1 for select fields)
    """
    options = field.get("options", [])
    if not options:
        return []  # No options defined, can't validate

    value_str = str(value)

    # Extract valid values from options (handle both string and dict formats)
    valid_values = _option_values(options)

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

    # Compare against the bare string option values (options may be {value, label}
    # dicts; comparing a selected string against a dict never matches, and passing
    # the raw dicts on to the error message crashed the formatter -- d24n).
    valid_values = _option_values(options)

    # Check each selected value is in options
    invalid_values = [v for v in selected_values if v not in valid_values]
    if invalid_values:
        return [ValidationError(
            field_id, field_name, value, "options",
            f"Invalid: {', '.join(invalid_values)}",
            valid_options=valid_values
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

        # Guard against normalization eating a non-empty input down to empty
        # (e.g. an a_number like "A" or "A---" with no digits). validate_field_value
        # SKIPS empty values (treating them as an unfilled optional field), so
        # without this an all-non-digit input would be silently stored as "" and
        # written blank to the PDF (fresh-eyes finding, PR #98). A raw value that
        # had content but normalized to empty is invalid, not unfilled.
        had_content = value is not None and str(value).strip() != ""
        if had_content and (normalized is None or str(normalized) == ""):
            validation_errors.append(ValidationError(
                field.get("id", ""), field.get("name", field.get("id", "")),
                value, "pattern", "Invalid format",
                constraint_value=field.get("pattern"),
            ).to_dict())
            continue

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
