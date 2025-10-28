"""
Polyglot PDF Form Schema - Pydantic Models

Unified schema supporting both web forms and PDF forms.
Designed to handle USCIS immigration forms with complex structures.

@version 1.0.0
@date 2025-10-25
"""

from typing import Optional, List, Dict, Any, Literal, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# ============================================================================
# Enums and Type Definitions
# ============================================================================

class FormSource(str, Enum):
    """Form source type - determines which additional metadata is required"""
    WEB = "web"
    PDF = "pdf"


class DatePrecision(str, Enum):
    """Date precision levels for different field requirements"""
    FULL = "full"
    MONTH_YEAR = "month_year"
    YEAR_ONLY = "year_only"


class DateFormat(str, Enum):
    """Date format specifications"""
    MM_DD_YYYY = "mm/dd/yyyy"
    MO_YR = "Mo/Yr"
    YYYY = "yyyy"
    ISO = "YYYY-MM-DD"


class FieldType(str, Enum):
    """Field types supported by the system"""
    TEXT = "text"
    TEXTAREA = "textarea"
    DATE = "date"
    NUMBER = "number"
    TEL = "tel"
    EMAIL = "email"
    SELECT = "select"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    SIGNATURE = "signature"
    ADDRESS_GROUP = "address_group"
    TABLE = "table"


class SignatureMethod(str, Enum):
    """Signature capture methods"""
    DRAW = "draw"
    UPLOAD = "upload"
    TYPE = "type"


class TextareaSize(str, Enum):
    """Textarea size presets"""
    SMALL = "small"    # 2 rows - for short responses
    MEDIUM = "medium"  # 5 rows - for moderate responses
    LARGE = "large"    # 10 rows - for long responses
    XLARGE = "xlarge"  # 20+ rows - for very long narratives (Part B questions)


class ConditionalOperator(str, Enum):
    """Conditional operator types for show_if logic"""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    IS_CHECKED = "is_checked"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"  # Added for completeness
    IN = "in"  # Value in list
    NOT_IN = "not_in"  # Value not in list


class SupplementType(str, Enum):
    """Types of supplement pages for overflow content"""
    SUPPLEMENT_A = "supplement_a"  # Additional children (I-589)
    SUPPLEMENT_B = "supplement_b"  # Additional information/narratives (I-589)


class GroupKind(str, Enum):
    """Type of field grouping"""
    CHECKBOX = "checkbox"
    RADIO = "radio"


class SessionStatus(str, Enum):
    """Form session status"""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPORTED = "exported"
    EXPIRED = "expired"


# ============================================================================
# Supporting Models
# ============================================================================

class FormMetadata(BaseModel):
    """Form-level metadata"""
    # Common to all forms
    title: str
    description: Optional[str] = None
    version: Optional[str] = None
    language: str = Field(default="en", description="ISO 639-1 code (e.g., 'en', 'es', 'zh')")

    # Web-specific
    url: Optional[str] = None

    # PDF-specific
    form_number: Optional[str] = Field(None, description='e.g., "I-589"')
    edition_date: Optional[str] = Field(None, description='e.g., "01/20/25"')
    omb_number: Optional[str] = Field(None, description='e.g., "1615-0067"')
    expiration_date: Optional[str] = Field(None, description='e.g., "2027-09-30"')
    page_count: Optional[int] = Field(None, description="Total pages in PDF")
    instructions_url: Optional[str] = Field(None, description="Link to separate instructions PDF")
    agency: Optional[str] = Field(None, description='e.g., "U.S. Citizenship and Immigration Services"')


class PDFPosition(BaseModel):
    """PDF-specific positioning information"""
    page: int = Field(description="Page number (1-indexed)")
    x: float = Field(description="X coordinate in points")
    y: float = Field(description="Y coordinate in points")
    width: float = Field(description="Width in points")
    height: float = Field(description="Height in points")


class ValidationRules(BaseModel):
    """Validation rules for a field"""
    required: Optional[bool] = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min: Optional[float] = None  # For numeric fields
    max: Optional[float] = None  # For numeric fields
    pattern: Optional[str] = Field(None, description="Regex pattern")
    custom_error: Optional[str] = Field(None, description="Custom error message")

    # Date-specific constraints
    date_constraint: Optional[Literal["past_only", "future_only", "within_5_years"]] = Field(
        None,
        description="Date-specific validation (e.g., birth date must be in past)"
    )

    # Format presets (common validation patterns)
    format_preset: Optional[Literal["ssn", "a_number", "phone", "email", "zip"]] = Field(
        None,
        description="Predefined format validation"
    )


class ConditionalDisplay(BaseModel):
    """Conditional display logic"""
    field: str = Field(description="Field ID to check")
    operator: ConditionalOperator
    value: Union[str, int, float, bool]


class FieldHelp(BaseModel):
    """Field-level help and instruction text"""
    inline: Optional[str] = Field(None, description='Inline hint text like "(if any)"')
    tooltip: Optional[str] = Field(None, description="Hover tooltip")
    instructions: Optional[str] = Field(None, description="Longer instructions below field")
    warning: Optional[str] = Field(None, description="Legal warning or important note")
    example: Optional[str] = Field(None, description="Example value")
    legal_reference: Optional[str] = Field(None, description='Legal reference (e.g., "INA 241(b)(3)", "18 USC 1546(a)")')


class FieldOption(BaseModel):
    """Options for select, radio, and checkbox fields"""
    value: str
    label: str
    spoken_label: Optional[str] = Field(None, description="Alternative label for voice input")
    label_translations: Optional[Dict[str, str]] = Field(
        None,
        description='Multi-language labels (e.g., {"es": "Soltero", "zh": "单身"})'
    )
    pdf_field_name: Optional[str] = Field(None, description="Original PDF field backing this option")


class TableColumn(BaseModel):
    """Table column definition for repeating rows"""
    id: str
    label: str
    type: FieldType
    width: Optional[int] = Field(None, description="Percentage or pixels")
    validation: Optional[ValidationRules] = None
    help: Optional[FieldHelp] = None
    pdf_field_name: Optional[str] = Field(None, description="Representative PDF field backing this column")
    options: Optional[List[FieldOption]] = Field(
        None,
        description="Available option choices when the column captures radios/checkbox groups"
    )


class MultiEntryConfig(BaseModel):
    """Multi-entry configuration for tables and repeating fields"""
    min_entries: int = Field(description="Minimum required entries")
    max_entries: Optional[int] = Field(None, description="Maximum allowed (None = unlimited)")
    initial_rows: int = Field(description="How many rows to show initially")
    add_button_label: Optional[str] = Field(None, description='Label for "Add" button')
    remove_button_label: Optional[str] = Field(None, description='Label for "Remove" button')
    overflow_instruction: Optional[str] = Field(
        None,
        description='Instructions when max reached (e.g., "Use Supplement A")'
    )
    overflow_to_supplement: Optional[SupplementType] = Field(
        None,
        description="Which supplement to use for overflow entries"
    )
    row_pdf_field_map: Optional[List[Dict[str, str]]] = Field(
        None,
        description="Mapping of column IDs to underlying PDF field names per template row"
    )


class AddressFields(BaseModel):
    """Address group sub-fields"""
    street: str = Field(description="Field ID for street address")
    apt: Optional[str] = Field(None, description="Field ID for apartment number")
    city: str = Field(description="Field ID for city")
    state: str = Field(description="Field ID for state")
    zip: str = Field(description="Field ID for ZIP code")
    country: Optional[str] = Field(None, description="Field ID for country (international addresses)")


# ============================================================================
# Core Field Model
# ============================================================================

class FormField(BaseModel):
    """Core field definition"""
    # Identity
    id: str = Field(description="Unique field identifier")
    name: str = Field(description="Display label")
    spoken_name: str = Field(description="Name for voice interaction")
    spoken_aliases: Optional[List[str]] = Field(None, description="Alternative names for voice input")

    # Type and behavior
    type: FieldType
    validation: Optional[ValidationRules] = None

    # Organization
    section_id: str = Field(description="Which section this belongs to")
    section_label: Optional[str] = Field(None, description="Section display name")
    group_id: Optional[str] = Field(None, description='Grouping within section (e.g., "full-name")')
    group_label: Optional[str] = Field(None, description="Group display name")
    group_kind: Optional[GroupKind] = Field(None, description="Type of group if applicable")

    # Conditional display
    show_if: Optional[ConditionalDisplay] = None

    # Help and guidance
    help: Optional[FieldHelp] = None
    placeholder: Optional[str] = None
    description: Optional[str] = Field(None, description="Field description")

    # PDF-specific
    pdf_position: Optional[PDFPosition] = Field(None, description="Position in original PDF")
    pdf_field_name: Optional[str] = Field(None, description="Original PDF field name")

    # Type-specific properties - Date fields
    date_precision: Optional[DatePrecision] = None
    format: Optional[DateFormat] = None
    min_date: Optional[str] = Field(None, description="ISO date string")
    max_date: Optional[str] = Field(None, description="ISO date string")

    # Type-specific properties - Text/Textarea fields
    max_length: Optional[int] = None
    textarea_size: Optional[TextareaSize] = None
    rows: Optional[int] = Field(None, description="Specific row count for textarea")

    # Type-specific properties - Numeric fields
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = Field(None, description="Increment for number spinners")

    # Type-specific properties - Select/Radio/Checkbox fields
    options: Optional[List[FieldOption]] = None

    # Type-specific properties - Signature fields
    signature_method: Optional[SignatureMethod] = None
    signature_box_style: Optional[str] = Field(None, description='e.g., "bracketed" for I-589 Part D')

    # Type-specific properties - Address group fields
    address_fields: Optional[AddressFields] = None

    # Type-specific properties - Table fields
    columns: Optional[List[TableColumn]] = None
    multi_entry: Optional[MultiEntryConfig] = None

    # Multi-language support
    name_translations: Optional[Dict[str, str]] = Field(
        None,
        description='Translations of field name for multi-language support (e.g., {"es": "Nombre Completo"})'
    )

    # Auto-fill logic
    auto_fill_na: Optional[bool] = Field(
        False,
        description="If true, auto-fill with NA when first similar field in group is set to NA"
    )

    # Supplement overflow
    overflow_to_supplement: Optional[SupplementType] = Field(
        None,
        description="Which supplement to overflow to (for long narratives or repeating fields)"
    )

    @field_validator('options')
    @classmethod
    def validate_options(cls, v, info):
        """Ensure options are provided for select/radio/checkbox types"""
        if info.data.get('type') in [FieldType.SELECT, FieldType.RADIO]:
            if not v:
                raise ValueError(f"Options required for {info.data.get('type')} field type")
        return v


# ============================================================================
# Section and Supplement Models
# ============================================================================

class FormSection(BaseModel):
    """Form section definition"""
    id: str
    label: str
    description: Optional[str] = None
    order: int = Field(description="Display order")
    fields: List[str] = Field(description="Field IDs in this section")
    page_number: Optional[int] = Field(None, description="PDF page number (PDF only)")
    page_numbers: Optional[List[int]] = Field(None, description="PDF page numbers if section spans multiple pages")
    required: Optional[bool] = Field(True, description="Can this section be skipped?")
    show_if: Optional[ConditionalDisplay] = None


class FormPart(BaseModel):
    """Form part definition (hierarchical grouping above sections)

    Example: I-589 has Part A, Part B, Part C, etc.
    Each part contains one or more sections.
    """
    id: str = Field(description='e.g., "part_a", "part_b"')
    label: str = Field(description='e.g., "Part A: Information About Applicant"')
    description: Optional[str] = None
    order: int = Field(description="Display order")
    section_ids: List[str] = Field(description="Section IDs in this part")
    required: Optional[bool] = Field(True, description="Can this part be skipped?")


class FormSupplement(BaseModel):
    """Supplement definition for overflow content"""
    id: str = Field(description='e.g., "supplement_a"')
    name: str = Field(description='e.g., "Supplement A - Additional Children"')
    purpose: str = Field(description="What this supplement is for")
    trigger_condition: Optional[str] = Field(None, description="When to use this supplement")
    fields: List[str] = Field(description="Field IDs available in supplement")
    page_number: Optional[int] = Field(None, description="PDF page number")


class ExtractionInfo(BaseModel):
    """Metadata about PDF extraction process"""
    extracted_at: str = Field(description="ISO timestamp")
    extraction_confidence: float = Field(ge=0, le=1, description="0-1 score")
    extractor_version: str = Field(description="Version of extraction tool")
    manual_review_required: bool
    manual_review_completed: Optional[bool] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


# ============================================================================
# Complete Form Schema
# ============================================================================

class FormSchema(BaseModel):
    """Complete form schema"""
    # Metadata
    source: FormSource
    form_metadata: FormMetadata

    # Structure (hierarchical: parts contain sections, or just sections if no parts)
    sections: List[FormSection]
    fields: List[FormField]
    parts: Optional[List[FormPart]] = Field(
        None,
        description="Optional hierarchical grouping (e.g., Part A, Part B). If absent, use flat section structure."
    )

    # Optional components
    supplements: Optional[List[FormSupplement]] = None

    # Extraction metadata (for PDF forms)
    extraction_info: Optional[ExtractionInfo] = None

    # Legal warnings (form-level)
    legal_warnings: Optional[List[str]] = Field(
        None,
        description="Form-level legal warnings (e.g., perjury statements)"
    )

    @field_validator('extraction_info')
    @classmethod
    def validate_extraction_info(cls, v, info):
        """Ensure extraction_info is provided for PDF forms"""
        if info.data.get('source') == FormSource.PDF and not v:
            raise ValueError("extraction_info required for PDF forms")
        return v

    def get_field(self, field_id: str) -> Optional[FormField]:
        """Get a field by ID"""
        for field in self.fields:
            if field.id == field_id:
                return field
        return None

    def get_section(self, section_id: str) -> Optional[FormSection]:
        """Get a section by ID"""
        for section in self.sections:
            if section.id == section_id:
                return section
        return None

    def get_fields_in_section(self, section_id: str) -> List[FormField]:
        """Get all fields in a specific section"""
        section = self.get_section(section_id)
        if not section:
            return []
        return [self.get_field(fid) for fid in section.fields if self.get_field(fid)]

    def get_part(self, part_id: str) -> Optional[FormPart]:
        """Get a part by ID"""
        if not self.parts:
            return None
        for part in self.parts:
            if part.id == part_id:
                return part
        return None

    def get_sections_in_part(self, part_id: str) -> List[FormSection]:
        """Get all sections in a specific part"""
        part = self.get_part(part_id)
        if not part:
            return []
        return [self.get_section(sid) for sid in part.section_ids if self.get_section(sid)]

    def validate_field_value(self, field_id: str, value: Any) -> tuple[bool, Optional[str]]:
        """
        Validate a field value against its validation rules

        Returns:
            tuple: (is_valid, error_message)
        """
        field = self.get_field(field_id)
        if not field:
            return False, f"Field {field_id} not found"

        if not field.validation:
            return True, None

        rules = field.validation

        # Required check
        if rules.required and (value is None or value == ""):
            return False, f"{field.name} is required"

        # Skip other checks if value is empty and not required
        if value is None or value == "":
            return True, None

        # Type-specific validation
        if field.type == FieldType.TEXT or field.type == FieldType.TEXTAREA:
            value_str = str(value)
            if rules.min_length and len(value_str) < rules.min_length:
                return False, f"{field.name} must be at least {rules.min_length} characters"
            if rules.max_length and len(value_str) > rules.max_length:
                return False, f"{field.name} must be at most {rules.max_length} characters"
            if rules.pattern:
                import re
                if not re.match(rules.pattern, value_str):
                    return False, rules.custom_error or f"{field.name} format is invalid"

        elif field.type == FieldType.NUMBER:
            try:
                num_value = float(value)
                if rules.min is not None and num_value < rules.min:
                    return False, f"{field.name} must be at least {rules.min}"
                if rules.max is not None and num_value > rules.max:
                    return False, f"{field.name} must be at most {rules.max}"
            except (ValueError, TypeError):
                return False, f"{field.name} must be a valid number"

        return True, None

    def validate_all_references(self) -> Dict[str, List[str]]:
        """
        Validate all references (field IDs, section IDs, part IDs) are valid

        Returns:
            Dict with keys: 'errors', 'warnings' containing lists of validation messages
        """
        errors = []
        warnings = []

        # Validate section field references
        all_field_ids = {f.id for f in self.fields}
        for section in self.sections:
            for field_id in section.fields:
                if field_id not in all_field_ids:
                    errors.append(f"Section '{section.id}' references non-existent field '{field_id}'")

        # Validate part section references
        all_section_ids = {s.id for s in self.sections}
        if self.parts:
            for part in self.parts:
                for section_id in part.section_ids:
                    if section_id not in all_section_ids:
                        errors.append(f"Part '{part.id}' references non-existent section '{section_id}'")

        # Validate conditional display references
        for field in self.fields:
            if field.show_if and field.show_if.field not in all_field_ids:
                errors.append(f"Field '{field.id}' show_if references non-existent field '{field.show_if.field}'")

        # Validate supplement references
        if self.supplements:
            for supplement in self.supplements:
                for field_id in supplement.fields:
                    if field_id not in all_field_ids:
                        errors.append(f"Supplement '{supplement.id}' references non-existent field '{field_id}'")

        return {"errors": errors, "warnings": warnings}


# ============================================================================
# Session Models
# ============================================================================

class FormSession(BaseModel):
    """Form session state (for saving/loading)"""
    session_id: str
    form_schema_id: str
    form_version: str
    created_at: str
    updated_at: str
    expires_at: str

    # Form data
    field_values: Dict[str, Any] = Field(default_factory=dict)
    current_section: str
    completed_sections: List[str] = Field(default_factory=list)

    # Metadata
    language: str = "en"
    user_id: Optional[str] = None

    # Status
    status: SessionStatus = SessionStatus.IN_PROGRESS


# ============================================================================
# WebSocket Event Models
# ============================================================================

class FieldUpdateEvent(BaseModel):
    """WebSocket event for field updates"""
    event_type: Literal["field_update"] = "field_update"
    session_id: str
    field_id: str
    value: Any
    timestamp: str


class SectionNavigateEvent(BaseModel):
    """WebSocket event for section navigation"""
    event_type: Literal["section_navigate"] = "section_navigate"
    session_id: str
    from_section: str
    to_section: str
    timestamp: str


class ValidationErrorEvent(BaseModel):
    """WebSocket event for validation error"""
    event_type: Literal["validation_error"] = "validation_error"
    session_id: str
    field_id: str
    error_message: str
    timestamp: str


class ToolResponse(BaseModel):
    """Tool response from Gemini function calls"""
    status: Literal["ok", "error"]
    field: Optional[str] = None
    message: str
    data: Optional[Any] = None


# ============================================================================
# Helper Functions for Creating Fields
# ============================================================================

def create_text_field(
    field_id: str,
    name: str,
    spoken_name: str,
    section_id: str,
    required: bool = False,
    help_inline: Optional[str] = None,
    placeholder: Optional[str] = None,
    **kwargs
) -> FormField:
    """Helper to create a simple text field"""
    return FormField(
        id=field_id,
        name=name,
        spoken_name=spoken_name,
        type=FieldType.TEXT,
        section_id=section_id,
        validation=ValidationRules(required=required) if required else None,
        help=FieldHelp(inline=help_inline) if help_inline else None,
        placeholder=placeholder,
        **kwargs
    )


def create_date_field(
    field_id: str,
    name: str,
    spoken_name: str,
    section_id: str,
    required: bool = False,
    date_precision: DatePrecision = DatePrecision.FULL,
    date_constraint: Optional[str] = None,
    **kwargs
) -> FormField:
    """Helper to create a date field"""
    validation = ValidationRules(required=required)
    if date_constraint:
        validation.date_constraint = date_constraint

    return FormField(
        id=field_id,
        name=name,
        spoken_name=spoken_name,
        type=FieldType.DATE,
        section_id=section_id,
        date_precision=date_precision,
        format=DateFormat.MM_DD_YYYY if date_precision == DatePrecision.FULL else DateFormat.MO_YR,
        validation=validation,
        **kwargs
    )


def create_radio_field(
    field_id: str,
    name: str,
    spoken_name: str,
    section_id: str,
    options: List[tuple],  # [(value, label, spoken_label), ...]
    required: bool = False,
    **kwargs
) -> FormField:
    """Helper to create a radio button field"""
    field_options = [
        FieldOption(value=v, label=l, spoken_label=sl if len(opt) > 2 else None)
        for opt in options
        for v, l, *rest in [opt + (None,)]  # Pad tuple if spoken_label missing
        for sl in [rest[0] if rest else None]
    ]

    return FormField(
        id=field_id,
        name=name,
        spoken_name=spoken_name,
        type=FieldType.RADIO,
        section_id=section_id,
        options=field_options,
        validation=ValidationRules(required=required) if required else None,
        **kwargs
    )


def create_textarea_field(
    field_id: str,
    name: str,
    spoken_name: str,
    section_id: str,
    size: TextareaSize = TextareaSize.MEDIUM,
    required: bool = False,
    overflow_to_supplement: Optional[SupplementType] = None,
    **kwargs
) -> FormField:
    """Helper to create a textarea field"""
    return FormField(
        id=field_id,
        name=name,
        spoken_name=spoken_name,
        type=FieldType.TEXTAREA,
        section_id=section_id,
        textarea_size=size,
        validation=ValidationRules(required=required) if required else None,
        overflow_to_supplement=overflow_to_supplement,
        **kwargs
    )


def create_select_field(
    field_id: str,
    name: str,
    spoken_name: str,
    section_id: str,
    options: List[tuple],  # [(value, label), ...]
    required: bool = False,
    **kwargs
) -> FormField:
    """Helper to create a select dropdown field"""
    field_options = [FieldOption(value=v, label=l) for v, l in options]

    return FormField(
        id=field_id,
        name=name,
        spoken_name=spoken_name,
        type=FieldType.SELECT,
        section_id=section_id,
        options=field_options,
        validation=ValidationRules(required=required) if required else None,
        **kwargs
    )


def create_checkbox_field(
    field_id: str,
    name: str,
    spoken_name: str,
    section_id: str,
    required: bool = False,
    **kwargs
) -> FormField:
    """Helper to create a single checkbox field"""
    return FormField(
        id=field_id,
        name=name,
        spoken_name=spoken_name,
        type=FieldType.CHECKBOX,
        section_id=section_id,
        validation=ValidationRules(required=required) if required else None,
        **kwargs
    )
