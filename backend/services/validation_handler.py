"""
Validation handler for form field updates.

Orchestrates field matching (exact + fuzzy) and validation against schema
constraints. Extracted from FormFillingService to improve testability and
separation of concerns.
"""
from typing import Any, Dict, List, Optional, Tuple
import structlog

from backend.models.form_models import FormField
from backend.utils.fuzzy_field_matcher import fuzzy_match_hint
from backend.utils.field_validator import validate_updates

_log = structlog.get_logger().bind(module="validation_handler")


class ValidationHandler:
    """Handles field matching and validation for form updates."""
    
    def __init__(self, session_id: Optional[str] = None):
        """
        Initialize validation handler.
        
        Args:
            session_id: Optional session ID for logging context
        """
        self._session_id = session_id
    
    def validate_field_updates(
        self,
        fields: List[FormField],
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Match and validate field updates against schema.
        
        Performs two-step validation:
        1. Match update keys to field IDs (exact match, then fuzzy)
        2. Validate matched updates against schema constraints
        
        Args:
            fields: List of FormField objects from schema
            updates: Dict mapping field keys (ID or name) to new values
            
        Returns:
            Validation result dict with:
                - applied_fields: List of successfully validated field IDs
                - unknown_fields: List of unmatched field keys
                - validation_errors: List of constraint violation errors
                - form_state: Dict of field_id -> validated value
            
            Returns None if an exception occurs during validation.
            
        Example:
            >>> handler = ValidationHandler("session_123")
            >>> result = handler.validate_field_updates(
            ...     fields=[FormField(id="email", name="Email", type="email")],
            ...     updates={"email": "test@example.com"}
            ... )
            >>> result["applied_fields"]
            ["email"]
        """
        try:
            # Step 1: Match field IDs (exact or fuzzy)
            matched_updates, unknown_fields, field_map = self._match_fields(
                fields, updates or {}
            )
            
            # Step 2: Validate matched fields against schema constraints
            field_dicts = self._convert_fields_to_dicts(fields)
            validation_result = validate_updates(field_dicts, matched_updates)
            
            applied_fields = validation_result["valid_fields"]
            validation_errors = validation_result["validation_errors"]
            form_state = validation_result["form_state"]
            
            result = {
                "applied_fields": applied_fields,
                "unknown_fields": unknown_fields,
                "validation_errors": validation_errors,
                "form_state": form_state,
            }
            
            # Log validation failures concisely
            if validation_errors or unknown_fields:
                _log.warning(
                    "validation_failures",
                    error_count=len(validation_errors),
                    unknown_count=len(unknown_fields),
                    session_id=self._session_id
                )
            
            return result
            
        except Exception as exc:
            _log.exception(
                "update_validation_error",
                session_id=self._session_id,
                error=str(exc)
            )
            return None
    
    def _match_fields(
        self,
        fields: List[FormField],
        updates: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[str], Dict[str, FormField]]:
        """
        Match update keys to field IDs using exact then fuzzy matching.
        
        Args:
            fields: List of FormField objects
            updates: Dict mapping field keys to values
            
        Returns:
            Tuple of:
                - matched_updates: Dict of field_id -> value
                - unknown_fields: List of unmatched keys
                - field_map: Dict of field_id -> FormField object
        """
        matched_updates = {}  # field_id -> value (with actual field IDs)
        unknown_fields = []
        field_map = {}  # field_id -> field object
        
        for field_key, value in updates.items():
            # Try exact match by field ID first
            matched_field = next((f for f in fields if f.id == field_key), None)
            
            # If no exact match, try fuzzy matching by name
            if not matched_field:
                match_result = fuzzy_match_hint(field_key, fields)
                if match_result.status == "resolved" and match_result.top_candidate:
                    matched_field = match_result.top_candidate.field
                    _log.debug(
                        "fuzzy_matched_field",
                        model_key=field_key,
                        matched_id=matched_field.id,
                        matched_name=matched_field.name,
                        score=match_result.top_candidate.score,
                        session_id=self._session_id
                    )
            
            if matched_field:
                matched_updates[matched_field.id] = value
                field_map[matched_field.id] = matched_field
            else:
                unknown_fields.append(field_key)
        
        return matched_updates, unknown_fields, field_map
    
    def _convert_fields_to_dicts(self, fields: List[FormField]) -> List[Dict[str, Any]]:
        """
        Convert FormField objects to dicts for field_validator.

        Extracts constraint fields (min, max, pattern, etc.) from validation object.

        Args:
            fields: List of FormField objects

        Returns:
            List of field dicts with id, name, type, and constraints
        """
        field_dicts = []

        for field_obj in fields:
            field_dict = {
                "id": field_obj.id,
                "name": field_obj.name,
                "type": field_obj.type,
            }

            # Extract validation constraints from nested validation object
            if field_obj.validation:
                validation = field_obj.validation

                # Map validation fields (snake_case) to expected format (camelCase)
                # Note: field_validator.py expects camelCase (minLength, maxLength)
                if validation.min_length is not None:
                    field_dict['minLength'] = validation.min_length
                if validation.max_length is not None:
                    field_dict['maxLength'] = validation.max_length
                if validation.min is not None:
                    field_dict['min'] = validation.min
                if validation.max is not None:
                    field_dict['max'] = validation.max
                if validation.pattern is not None:
                    field_dict['pattern'] = validation.pattern
                if validation.digits_only is not None:
                    field_dict['digits_only'] = validation.digits_only
                if validation.date_constraint is not None:
                    field_dict['date_constraint'] = validation.date_constraint
                # format_preset drives normalize_value() in field_validator (e.g.
                # a_number strips the "A" prefix before pattern validation) -- it
                # MUST be passed through or normalization never runs (bd 0zr).
                if getattr(validation, 'format_preset', None) is not None:
                    field_dict['format_preset'] = validation.format_preset

            # Add options if field has them (for select/radio/checkbox)
            if hasattr(field_obj, 'options') and field_obj.options:
                # Convert Pydantic models to dicts
                field_dict['options'] = [
                    opt.dict() if hasattr(opt, 'dict') else opt
                    for opt in field_obj.options
                ]

            field_dicts.append(field_dict)

        return field_dicts
