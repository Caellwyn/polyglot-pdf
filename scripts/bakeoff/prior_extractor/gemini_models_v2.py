"""
Pydantic models for Gemini API v2 with separate enhancement types.

V2 Design:
- Three separate API calls for different enhancement types
- Batching support (50 fields per call to prevent truncation)
- Focused prompts for each enhancement type
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# ============================================================================
# SPOKEN NAMES + HELP TEXT ENHANCEMENTS
# ============================================================================

class SpokenNameEnhancement(BaseModel):
    """Enhancement for a single field's spoken name and help text."""
    field_id: str = Field(description="The field ID from the input")
    spoken_name: str = Field(
        description="Clear, unique spoken name that disambiguates this field from others"
    )
    help_text: Optional[str] = Field(
        default=None,
        description="Brief helpful directions or clarification for filling out this field"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence level for these enhancements (0.0 to 1.0)"
    )


class SpokenNamesResponse(BaseModel):
    """Response containing spoken names and help text for a batch of fields."""
    field_enhancements: List[SpokenNameEnhancement] = Field(
        description="List of field enhancements with spoken names and help text"
    )


# ============================================================================
# GROUPINGS (RADIO/CHECKBOX ONLY)
# ============================================================================

class WidgetGroup(BaseModel):
    """A logical group of related radio buttons or checkboxes."""
    group_name: str = Field(
        description="Name of this logical group (e.g., 'Marital Status', 'Contact Preferences')"
    )
    group_label: str = Field(
        description="Human-readable label for the group"
    )
    field_ids: List[str] = Field(
        description="List of field IDs that belong to this group"
    )
    is_exclusive: bool = Field(
        description="True if only one option can be selected (radio buttons), False for checkboxes"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence level for this grouping (0.0 to 1.0)"
    )


class GroupingsResponse(BaseModel):
    """Response containing logical groupings of radio/checkbox fields."""
    widget_groups: List[WidgetGroup] = Field(
        description="List of identified widget groups"
    )


# ============================================================================
# CONDITIONALS (OPTIONAL, BEST EFFORT)
# ============================================================================

class ConditionalRule(BaseModel):
    """A conditional rule that shows/hides/requires fields based on other field values."""
    field_id: str = Field(
        description="The field ID that is affected by this rule"
    )
    condition_type: Literal["show", "hide", "require"] = Field(
        description="Type of conditional action"
    )
    trigger_field_id: str = Field(
        description="The field ID whose value triggers this rule"
    )
    trigger_value: Optional[str] = Field(
        default=None,
        description="The value that triggers this rule (if applicable)"
    )
    description: str = Field(
        description="Human-readable description of this conditional rule"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence level for this rule (0.0 to 1.0)"
    )


class ConditionalsResponse(BaseModel):
    """Response containing conditional rules for field visibility/requirements."""
    conditional_rules: List[ConditionalRule] = Field(
        description="List of identified conditional rules"
    )


# ============================================================================
# JSON SCHEMA GENERATORS
# ============================================================================

def get_spoken_names_schema() -> dict:
    """Get JSON schema for spoken names and help text enhancement."""
    return SpokenNamesResponse.model_json_schema()


def get_groupings_schema() -> dict:
    """Get JSON schema for widget groupings."""
    return GroupingsResponse.model_json_schema()


def get_conditionals_schema() -> dict:
    """Get JSON schema for conditional rules."""
    return ConditionalsResponse.model_json_schema()
