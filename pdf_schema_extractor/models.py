"""
Pydantic Models for PDF Schema Extraction
Based on the unified schema in `backend/models/form_schema.py`.
"""

from typing import Optional, List, Dict, Any, Literal, Union
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
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XLARGE = "xlarge"


class ConditionalOperator(str, Enum):
    """Conditional operator types for show_if logic"""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    IS_CHECKED = "is_checked"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    IN = "in"
    NOT_IN = "not_in"


class SupplementType(str, Enum):
    """Types of supplement pages for overflow content"""
    SUPPLEMENT_A = "supplement_a"
    SUPPLEMENT_B = "supplement_b"


class GroupKind(str, Enum):
    """Type of field grouping"""
    CHECKBOX = "checkbox"
    RADIO = "radio"


# ============================================================================
# Supporting Models
# ============================================================================

class FormMetadata(BaseModel):
    """Form-level metadata"""
    title: str
    description: Optional[str] = None
    version: str
    language: str = Field(default="en", description="ISO 639-1 code")
    url: Optional[str] = None
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
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: Optional[str] = Field(None, description="Regex pattern")
    custom_error: Optional[str] = Field(None, description="Custom error message")
    date_constraint: Optional[Literal["past_only", "future_only", "within_5_years"]] = None
    format_preset: Optional[Literal["ssn", "a_number", "phone", "email", "zip"]] = None


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
    legal_reference: Optional[str] = Field(None, description='Legal reference (e.g., "INA 241(b)(3)")')


class FieldOption(BaseModel):
    """Options for select, radio, and checkbox fields"""
    value: str
    label: str
    spoken_label: Optional[str] = None
    label_translations: Optional[Dict[str, str]] = None


class TableColumn(BaseModel):
    """Table column definition for repeating rows"""
    id: str
    label: str
    type: FieldType
    width: Optional[int] = None
    validation: Optional[ValidationRules] = None
    help: Optional[FieldHelp] = None


class MultiEntryConfig(BaseModel):
    """Multi-entry configuration for tables and repeating fields"""
    min_entries: int
    max_entries: Optional[int] = None
    initial_rows: int
    add_button_label: Optional[str] = None
    remove_button_label: Optional[str] = None
    overflow_instruction: Optional[str] = None
    overflow_to_supplement: Optional[SupplementType] = None


class AddressFields(BaseModel):
    """Address group sub-fields"""
    street: str
    apt: Optional[str] = None
    city: str
    state: str
    zip: str
    country: Optional[str] = None


# ============================================================================
# Core Field Model
# ============================================================================

class FormField(BaseModel):
    """Core field definition"""
    id: str
    name: str
    spoken_name: str
    spoken_aliases: Optional[List[str]] = None
    type: FieldType
    validation: Optional[ValidationRules] = None
    section_id: str
    section_label: Optional[str] = None
    group_id: Optional[str] = None
    group_label: Optional[str] = None
    group_kind: Optional[GroupKind] = None
    show_if: Optional[ConditionalDisplay] = None
    help: Optional[FieldHelp] = None
    placeholder: Optional[str] = None
    description: Optional[str] = None
    pdf_position: Optional[PDFPosition] = None
    pdf_field_name: Optional[str] = None
    date_precision: Optional[DatePrecision] = None
    format: Optional[DateFormat] = None
    min_date: Optional[str] = None
    max_date: Optional[str] = None
    max_length: Optional[int] = None
    textarea_size: Optional[TextareaSize] = None
    rows: Optional[int] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    options: Optional[List[FieldOption]] = None
    signature_method: Optional[SignatureMethod] = None
    signature_box_style: Optional[str] = None
    address_fields: Optional[AddressFields] = None
    columns: Optional[List[TableColumn]] = None
    multi_entry: Optional[MultiEntryConfig] = None
    name_translations: Optional[Dict[str, str]] = None
    auto_fill_na: Optional[bool] = False
    overflow_to_supplement: Optional[SupplementType] = None

    @field_validator('options')
    @classmethod
    def validate_options(cls, v, info):
        if info.data.get('type') in [FieldType.SELECT, FieldType.RADIO] and not v:
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
    order: int
    fields: List[str]
    page_number: Optional[int] = None
    page_numbers: Optional[List[int]] = None
    required: Optional[bool] = True
    show_if: Optional[ConditionalDisplay] = None


class FormPart(BaseModel):
    """Form part definition (hierarchical grouping above sections)"""
    id: str
    label: str
    description: Optional[str] = None
    order: int
    section_ids: List[str]
    required: Optional[bool] = True


class FormSupplement(BaseModel):
    """Supplement definition for overflow content"""
    id: str
    name: str
    purpose: str
    trigger_condition: Optional[str] = None
    fields: List[str]
    page_number: Optional[int] = None


class ExtractionInfo(BaseModel):
    """Metadata about PDF extraction process"""
    extracted_at: str
    extraction_confidence: float = Field(ge=0, le=1)
    extractor_version: str
    manual_review_required: bool
    manual_review_completed: Optional[bool] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


# ============================================================================
# Complete Form Schema
# ============================================================================

class FormSchema(BaseModel):
    """Complete form schema"""
    source: FormSource
    form_metadata: FormMetadata
    sections: List[FormSection]
    fields: List[FormField]
    parts: Optional[List[FormPart]] = None
    supplements: Optional[List[FormSupplement]] = None
    extraction_info: Optional[ExtractionInfo] = None
    legal_warnings: Optional[List[str]] = None

    @field_validator('extraction_info')
    @classmethod
    def validate_extraction_info(cls, v, info):
        if info.data.get('source') == FormSource.PDF and not v:
            raise ValueError("extraction_info required for PDF forms")
        return v
