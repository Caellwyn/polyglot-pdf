"""
Field utility functions for form schema processing.

Pure functions for building field objects, fuzzy matching field names,
and extracting field metadata from schemas. These functions are stateless
and can be used independently of the FormFillingService.
"""
from typing import Any, Dict, List, Optional
from backend.models.form_models import FormField, FieldType


def build_fields_from_schema(schema: Dict[str, Any]) -> List[FormField]:
    """Build field list from schema (stateless).
    
    Constructs FormField objects from a form schema dictionary.
    Used by web sessions to build field objects for validation.
    
    Args:
        schema: Form schema dictionary with 'fields' array
        
    Returns:
        List of FormField objects with populated metadata
        
    Note:
        The backend doesn't persist these fields - they're rebuilt each time.
    """
    fields = []
    
    for field_data in schema.get("fields", []):
        # Build FormField object from schema
        # Extract only the properties that exist in the current FormField model
        field_type_str = field_data.get("type", "text")
        
        # Convert string type to FieldType enum
        try:
            field_type = FieldType(field_type_str)
        except ValueError:
            field_type = FieldType.TEXT
        
        field = FormField(
            id=field_data.get("id"),
            name=field_data.get("name"),
            spoken_name=field_data.get("spoken_name") or field_data.get("name"),
            spoken_aliases=field_data.get("spoken_aliases") or [],
            type=field_type,
            section_id=field_data.get("section_id", ""),  # Required field
            validation=field_data.get("validation"),
            options=field_data.get("options"),
        )
        fields.append(field)
    
    return fields


def get_available_spoken_names(schema: Optional[Dict[str, Any]]) -> List[str]:
    """Get list of all available spoken field names from schema.
    
    Extracts field names that can be used for voice queries via get_field_value tool.
    
    Args:
        schema: Form schema dictionary with 'fields' array
        
    Returns:
        List of spoken names that can be queried, empty list if schema is None
    """
    available_names = []
    
    if schema:
        for field in schema.get("fields", []):
            # Use field name as spoken name (this is what frontend maps)
            field_name = field.get("name")
            if field_name:
                available_names.append(field_name)
    
    return available_names


def find_similar_field_names(
    query: str, 
    available_names: List[str], 
    max_suggestions: int = 3
) -> List[str]:
    """Find similar field names using fuzzy matching.
    
    Uses rapidfuzz for high-quality fuzzy matching (same library used for 
    PDF field normalization). Falls back to simple substring matching if
    rapidfuzz is not available.
    
    Args:
        query: User's query string (e.g., "phone")
        available_names: List of valid field names to match against
        max_suggestions: Maximum number of suggestions to return (default: 3)
        
    Returns:
        List of suggested field names, sorted by similarity score.
        Matches must score >= 52% to be included.
        
    Example:
        >>> find_similar_field_names("phone", ["Phone Number", "Cell Phone", "Email"])
        ["Phone Number", "Cell Phone"]
    """
    if not available_names:
        return []
    
    try:
        from rapidfuzz import fuzz, process
        
        # Use rapidfuzz to find best matches
        # extractOne returns (match, score, index) or None
        results = process.extract(
            query, 
            available_names, 
            scorer=fuzz.token_sort_ratio,  # Robust to word order
            limit=max_suggestions
        )
        
        # Filter by minimum score threshold (52% - same as fuzzy_field_matcher.py)
        # Return matches with score >= 52
        suggestions = [match for match, score, _ in results if score >= 52]
        
        return suggestions
        
    except ImportError:
        # Fallback if rapidfuzz not available: simple substring matching
        query_lower = query.lower().strip()
        matches = []
        
        for name in available_names:
            name_lower = name.lower().strip()
            
            # Exact match
            if name_lower == query_lower:
                matches.append((name, 0))
            # Substring match
            elif query_lower in name_lower or name_lower in query_lower:
                matches.append((name, 1))
        
        # Sort by priority and return
        matches.sort(key=lambda x: x[1])
        return [name for name, _ in matches[:max_suggestions]]
