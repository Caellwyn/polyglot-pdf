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
        
        Extracts constraint fields (min, max, pattern, etc.) if present.
        
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
            
            # Add constraint fields if present
            constraint_attrs = [
                'min', 'max', 'format', 'pattern',
                'minLength', 'maxLength', 'options'
            ]
            
            for attr in constraint_attrs:
                if hasattr(field_obj, attr):
                    value = getattr(field_obj, attr)
                    # Only add non-None/non-empty values
                    if value is not None and (not isinstance(value, (list, str)) or value):
                        field_dict[attr] = value
            
            field_dicts.append(field_dict)
        
        return field_dicts
