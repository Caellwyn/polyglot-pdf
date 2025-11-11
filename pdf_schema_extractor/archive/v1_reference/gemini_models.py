"""
Gemini API Input/Output Models for PDF Schema Enhancement

These models define what we send to Gemini and what we expect back.
Designed to minimize token usage while maximizing semantic understanding.

@version 1.0.0
@date 2025-11-10
"""

from typing import Optional, List, Dict, Any, Literal, Union
from pydantic import BaseModel, Field


# ============================================================================
# Input Models (What We Send to Gemini)
# ============================================================================

class SimplifiedField(BaseModel):
    """
    Minimal field info sent to Gemini - just enough for context.
    Keeps token count low while providing necessary information.
    """
    id: str = Field(description="Unique field identifier")
    pdf_field_name: str = Field(description="Original PDF widget name")
    type: str = Field(description="Field type: text, checkbox, radio, etc.")
    label: Optional[str] = Field(None, description="Extracted label from heuristic parsing")
    page: int = Field(description="Page number (1-indexed)")
    position: Dict[str, float] = Field(description="x, y, width, height in PDF points")


class GeminiInput(BaseModel):
    """
    Complete input package sent to Gemini.
    Includes form metadata and simplified field list.
    """
    form_metadata: Dict[str, Any] = Field(description="Form number, title, edition date, etc.")
    fields: List[SimplifiedField] = Field(description="All fields in the form")
    # Note: annotated_pdf_uri is sent separately as a file part


# ============================================================================
# Output Models (What We Expect from Gemini)
# ============================================================================

class WidgetGroup(BaseModel):
    """
    Related fields that should be grouped together.
    Examples: address blocks, name fields, radio groups.
    """
    group_type: Literal["radio", "checkbox", "address", "name", "date_range", "related"] = Field(
        description="Type of grouping"
    )
    field_ids: List[str] = Field(description="Field IDs that belong to this group")
    purpose: str = Field(description="What this group represents (e.g., 'Current mailing address')")
    spoken_name: Optional[str] = Field(None, description="Voice-friendly name for the group")
    help_text: Optional[str] = Field(None, description="Instructions for the entire group")


class ConditionalRule(BaseModel):
    """
    Show/hide/require logic between fields.
    Example: If 'Has spouse' is checked, show spouse name fields.
    """
    trigger_field_id: str = Field(description="Field that triggers the condition")
    operator: Literal["equals", "not_equals", "is_checked", "is_not_checked", "is_empty", "is_not_empty"] = Field(
        description="Comparison operator"
    )
    value: Union[str, bool, int, None] = Field(description="Value to check for (None for is_empty/is_not_empty)")
    affected_field_ids: List[str] = Field(description="Fields affected by this condition")
    action: Literal["show", "hide", "require", "unrequire"] = Field(description="Action to take")
    confidence: float = Field(description="Confidence level 0.0-1.0", ge=0.0, le=1.0)


class FieldEnhancement(BaseModel):
    """
    Semantic enhancements for a single field.
    Focus on spoken names, help text, and validation hints.
    """
    field_id: str = Field(description="Field ID being enhanced")

    # Voice-friendly names (CRITICAL: Must be unique across entire form)
    spoken_name: Optional[str] = Field(
        None,
        description="Short, natural voice name (2-4 words). MUST BE UNIQUE. Use context prefixes for disambiguation."
    )
    spoken_aliases: Optional[List[str]] = Field(None, description="Alternative voice commands")

    # Help text
    help_text: Optional[str] = Field(None, description="Clear, user-friendly instructions")
    format_hint: Optional[str] = Field(None, description="Format guidance (e.g., 'MM/DD/YYYY', 'XXX-XX-XXXX')")
    example: Optional[str] = Field(None, description="Example valid value")
    warning: Optional[str] = Field(None, description="Important legal warning or note")

    # Validation suggestions
    format_preset: Optional[Literal["ssn", "a_number", "phone", "email", "zip", "date"]] = Field(
        None, description="Named format preset"
    )
    validation_pattern: Optional[str] = Field(None, description="Regex pattern for validation")

    # Type corrections (if heuristic extraction got it wrong)
    suggested_type: Optional[str] = Field(None, description="Suggested field type if different from current")
    type_confidence: Optional[float] = Field(None, description="Confidence in type suggestion", ge=0.0, le=1.0)

    # Relationships
    related_to: Optional[List[str]] = Field(None, description="IDs of semantically related fields")


class GeminiEnhancement(BaseModel):
    """
    Complete output from Gemini.
    Contains all semantic enhancements for the form.
    """
    widget_groups: List[WidgetGroup] = Field(
        default_factory=list,
        description="Identified field groupings"
    )
    conditional_rules: List[ConditionalRule] = Field(
        default_factory=list,
        description="Detected conditional logic"
    )
    field_enhancements: List[FieldEnhancement] = Field(
        description="Enhancements for individual fields"
    )

    # Metadata
    confidence: float = Field(description="Overall confidence in enhancements", ge=0.0, le=1.0)
    processing_notes: Optional[List[str]] = Field(
        None,
        description="Observations, warnings, or interesting patterns found"
    )
    ambiguities: Optional[List[str]] = Field(
        None,
        description="Things that were unclear or uncertain"
    )


# ============================================================================
# Gemini API Response Schema (for structured outputs)
# ============================================================================

def get_gemini_response_schema() -> Dict[str, Any]:
    """
    Returns the JSON schema for Gemini's structured output.
    This is what we pass to the responseSchema parameter.
    """
    return {
        "type": "OBJECT",
        "properties": {
            "widget_groups": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "group_type": {
                            "type": "STRING",
                            "enum": ["radio", "checkbox", "address", "name", "date_range", "related"]
                        },
                        "field_ids": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"}
                        },
                        "purpose": {"type": "STRING"},
                        "spoken_name": {"type": "STRING", "nullable": True},
                        "help_text": {"type": "STRING", "nullable": True}
                    },
                    "required": ["group_type", "field_ids", "purpose"]
                }
            },
            "conditional_rules": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "trigger_field_id": {"type": "STRING"},
                        "operator": {
                            "type": "STRING",
                            "enum": ["equals", "not_equals", "is_checked", "is_not_checked", "is_empty", "is_not_empty"]
                        },
                        "value": {"type": "STRING", "nullable": True},
                        "affected_field_ids": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"}
                        },
                        "action": {
                            "type": "STRING",
                            "enum": ["show", "hide", "require", "unrequire"]
                        },
                        "confidence": {"type": "NUMBER"}
                    },
                    "required": ["trigger_field_id", "operator", "affected_field_ids", "action", "confidence"]
                }
            },
            "field_enhancements": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "field_id": {"type": "STRING"},
                        "spoken_name": {"type": "STRING", "nullable": True},
                        "spoken_aliases": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                            "nullable": True
                        },
                        "help_text": {"type": "STRING", "nullable": True},
                        "format_hint": {"type": "STRING", "nullable": True},
                        "example": {"type": "STRING", "nullable": True},
                        "warning": {"type": "STRING", "nullable": True},
                        "format_preset": {"type": "STRING", "nullable": True},
                        "validation_pattern": {"type": "STRING", "nullable": True},
                        "suggested_type": {"type": "STRING", "nullable": True},
                        "type_confidence": {"type": "NUMBER", "nullable": True},
                        "related_to": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                            "nullable": True
                        }
                    },
                    "required": ["field_id"]
                }
            },
            "confidence": {"type": "NUMBER"},
            "processing_notes": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "nullable": True
            },
            "ambiguities": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "nullable": True
            }
        },
        "required": ["field_enhancements", "confidence"]
    }
