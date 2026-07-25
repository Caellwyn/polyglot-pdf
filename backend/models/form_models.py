"""
Polyglot PDF Form Schema - Pydantic Models

Unified schema supporting both web forms and PDF forms.
Designed to handle USCIS immigration forms with complex structures.

@version 1.1.0
@date 2025-11-01
"""

import warnings

from typing import Optional, List, Dict, Any, Literal, Union
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from enum import Enum

from . import conditional_vocabulary as vocab


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
    # v2 (bd h76m.3): a multi-select group of checkboxes as ONE logical field
    # whose options[] carry per-box PDF identity; value shape is List[str] of
    # option slugs. In v2 CHECKBOX means a STANDALONE boolean (options
    # forbidden); the old one-checkbox-field-per-box modeling migrates here.
    CHECKBOX_GROUP = "checkbox_group"
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
    XLARGE = "xlarge"  # 20+ rows - for very long narratives


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
    # v2 group-membership operators (bd h76m.3): "option <value> is (not) in
    # the checkbox_group trigger's selected set". These retire the undocumented
    # equals-means-membership evaluator hack (bd vq4m) -- in a v2 schema,
    # equals on a checkbox_group trigger is a validation error.
    INCLUDES = "includes"
    NOT_INCLUDES = "not_includes"


# Import-time registry sync guard: the vocabulary registry speaks in enum
# STRING values (it cannot import this module -- cycle), so a desync between
# the two would otherwise surface only when a validator hits the "unknown
# operator" branch at runtime. Fail at import instead. Plain raise, not
# assert: asserts vanish under python -O.
if vocab.ALLOWED_OPERATORS != {op.value for op in ConditionalOperator}:
    raise RuntimeError(
        "conditional_vocabulary.OPERATORS is out of sync with "
        "ConditionalOperator: registry-only="
        f"{sorted(vocab.ALLOWED_OPERATORS - {op.value for op in ConditionalOperator})}, "
        f"enum-only={sorted({op.value for op in ConditionalOperator} - vocab.ALLOWED_OPERATORS)}"
    )
if not (vocab.CHOICE_FIELD_TYPES | vocab.CONDITION_TRIGGER_TYPES) <= {
    ft.value for ft in FieldType
}:
    raise RuntimeError(
        "conditional_vocabulary field-type sets name types missing from "
        "FieldType: "
        f"{sorted((vocab.CHOICE_FIELD_TYPES | vocab.CONDITION_TRIGGER_TYPES) - {ft.value for ft in FieldType})}"
    )


class SupplementType(str, Enum):
    ## Not fully implemented yet
    """Types of supplement pages for overflow content"""
    TYPE = "supplement_a"  # ex. Additional children (I-589)

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
    version: str
    language: str = Field(default="en", description="ISO 639-1 code (e.g., 'en', 'es', 'zh')")

    # Web-specific
    url: Optional[str] = None

    # PDF-specific
    form_number: Optional[str] = Field(None, description='e.g., "I-589"')
    edition_date: Optional[str] = Field(None, description='e.g., "01/20/25"')
    omb_number: Optional[str] = Field(None, description='e.g., "1615-0067"')
    expiration_date: Optional[str] = Field(None, description='e.g., "2027-09-30"')
    version_confidence: Optional[float] = Field(
        None, ge=0, le=1,
        description="0-1 confidence in the auto-extracted version (bd s4dp.2): "
                    "high for a specific Edition/Rev pattern, low for a generic "
                    "year/loose-OMB fallback, 0 when nothing is recoverable. Note "
                    "version may be 'unknown' yet carry LOW (not 0) confidence when "
                    "a loose OMB number gives some provenance.",
    )
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

    # Character restrictions (more readable than regex)
    digits_only: Optional[bool] = Field(None, description="Only allow numeric digits (0-9)")

    # Date-specific constraints
    date_constraint: Optional[Literal["past_only", "future_only", "within_5_years"]] = Field(
        None,
        description="Date-specific validation (e.g., birth date must be in past)"
    )

    # Format presets (common validation patterns). Digit-only presets (a_number,
    # uscis_account) drive normalize_value() to strip punctuation before length/
    # pattern checks, so speech-to-text formatting (commas, "$") does not fail an
    # otherwise-valid digit string (bd polyglot-pdf-jnjj.40).
    format_preset: Optional[Literal["ssn", "a_number", "phone", "email", "zip", "uscis_account"]] = Field(
        None,
        description="Predefined format validation"
    )


class ConditionalDisplay(BaseModel):
    """
    Reactive, dependent-side logic.
    Used on a field to define the condition under which it should be shown.
    Example: Placed on Field B, "Show me if Field A's value is 'Yes'."
    """
    field: str = Field(description="Field ID to check")
    operator: ConditionalOperator
    value: Optional[Union[str, int, float, bool, List[Union[str, int, float, bool]]]] = Field(
        None,
        description="Value to compare against (a list for IN/NOT_IN; omitted for "
                    "the no-value operators is_checked/is_empty/is_not_empty)"
    )

    @model_validator(mode="after")
    def _value_required_unless_no_value_operator(self):
        """value stays REQUIRED for value-taking operators in every dialect.

        value became Optional only so the no-value operators (is_checked /
        is_empty / is_not_empty) can be authored without a dummy value; an
        equals/in/... condition with no value was rejected before this field
        relaxed and must stay rejected, or a malformed legacy condition
        parses and evaluates wrongly downstream (Codex PR #299).
        """
        spec = vocab.OPERATORS.get(self.operator.value)
        if spec is not None and spec.value_arity != "none" and self.value is None:
            raise ValueError(
                f"operator '{self.operator.value}' requires a value "
                f"(only {', '.join(sorted(n for n, s in vocab.OPERATORS.items() if s.value_arity == 'none'))} "
                f"may omit it)"
            )
        return self


class ConditionGroup(BaseModel):
    """
    v2 composite condition (bd h76m.3): one level of boolean structure over
    atomic conditions. "(A AND B) AND NOT C" = all_of:[A,B] + none_of:[C].

    FLAT BY CONSTRUCTION: bucket members are atomic ConditionalDisplay
    conditions -- a nested group is a validation error (its dict has no
    'field'/'operator'), and extra="forbid" keeps a legacy single condition
    from mis-parsing as an empty group. Nesting can later be admitted inside
    all_of without a wire break; until then depth <= 1 is the contract
    (mirrored by the P3.0 normalizeToComposite helper on the TS side).

    Semantics: visible when ALL of all_of hold, AND at least one of any_of
    holds (when present), AND none of none_of hold. An omitted bucket is
    vacuously satisfied; at least one bucket must be present and non-empty.
    """
    model_config = ConfigDict(extra="forbid")

    all_of: Optional[List[ConditionalDisplay]] = None
    any_of: Optional[List[ConditionalDisplay]] = None
    none_of: Optional[List[ConditionalDisplay]] = None

    @model_validator(mode="after")
    def _at_least_one_bucket(self):
        if not (self.all_of or self.any_of or self.none_of):
            raise ValueError(
                "ConditionGroup must carry at least one non-empty bucket "
                "(all_of / any_of / none_of)"
            )
        return self


# A field-level condition on the wire: either the legacy single condition
# (v1, normalized to a one-atom group by readers via normalizeToComposite /
# iter_condition_atoms) or a v2 composite group. Union order matters only for
# error aggregation; discrimination is structural (a group has buckets and
# forbids extras, an atom requires field+operator).
FieldCondition = Union[ConditionGroup, ConditionalDisplay]

_ATOM_KEYS = frozenset({"field", "operator"})


def _reject_mixed_condition_keys(value):
    """Refuse a condition dict that mixes atom keys with bucket keys.

    Without this, {"field": ..., "operator": ..., "all_of": [...]} would parse
    as a ConditionalDisplay (which tolerates extra keys, unlike ConditionGroup)
    and SILENTLY DROP the bucket -- a half-migrated show_if would ship with
    part of its logic gone and no error (fresh-eyes finding, bd h76m.3). Extra
    keys that are not bucket keys stay tolerated (stored editor drafts carry
    benign strays); only the ambiguous atom+bucket mix is refused. Applies
    recursively to bucket members so the same mix cannot hide one level down.
    """
    if isinstance(value, dict):
        buckets = vocab.CONDITION_GROUP_BUCKETS & value.keys()
        if buckets and _ATOM_KEYS & value.keys():
            raise ValueError(
                "condition mixes atomic keys (field/operator) with composite "
                f"buckets ({', '.join(sorted(buckets))}) -- use ONE shape: a "
                "single {field, operator, value} condition OR a "
                "{all_of/any_of/none_of} group of them"
            )
        for bucket in buckets:
            members = value[bucket]
            if isinstance(members, list):
                for member in members:
                    if isinstance(member, dict) and (
                        vocab.CONDITION_GROUP_BUCKETS & member.keys()
                    ):
                        raise ValueError(
                            f"condition group bucket '{bucket}' members must be "
                            "atomic {field, operator, value} conditions -- "
                            "nesting (or stray bucket keys) is not allowed"
                        )
    return value


def iter_condition_atoms(condition: Optional["FieldCondition"]) -> List[ConditionalDisplay]:
    """Flatten a legacy-or-composite condition to its atomic conditions.

    The Python-side reader normalization (plan P1.1): None -> []; a legacy
    single condition -> [it]; a ConditionGroup -> its buckets concatenated.
    Consumers that only need "which fields/operators does this reference"
    (reference validation, cycle detection, lint) use this instead of
    special-casing the two shapes.
    """
    if condition is None:
        return []
    if isinstance(condition, ConditionalDisplay):
        return [condition]
    atoms: List[ConditionalDisplay] = []
    for bucket in (condition.all_of, condition.any_of, condition.none_of):
        if bucket:
            atoms.extend(bucket)
    return atoms


class ConditionalBehavior(BaseModel):
    """
    Defines *how* a field reacts to conditional actions.
    This is often implementation-specific (e.g., PDF vs. Web).
    """
    unlock_method: Optional[Literal["flip_readonly_bit", "set_property"]] = Field(
        None, description="Method to use when unlocking this field."
    )
    show_method: Optional[Literal["remove_hidden_flag", "set_property"]] = Field(
        None, description="Method to use when showing this field."
    )
    pdf_field_flag_change: Optional[Dict[str, Any]] = Field(
        None, description="PDF-specific bit manipulation for field flags (e.g., {'bit': 0, 'current_value': 1, 'required_value': 0})"
    )


class FieldHelp(BaseModel):
    """Field-level help and instruction text"""
    inline: Optional[str] = Field(None, description='Inline hint text like "(if any)"')
    tooltip: Optional[str] = Field(None, description="Hover tooltip")
    instructions: Optional[str] = Field(None, description="Longer instructions below field")
    format_hint: Optional[str] = Field(None, description='Short input-format hint, e.g. "7-9 digits" or "YYYY-MM-DD" (rendered into the SI; bd polyglot-pdf-jnjj.23)')
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
        # Canonical key = LOWERCASE SPOKEN-LANGUAGE NAME (bd polyglot-pdf-2h9j;
        # baked at authoring time by option_translation.bake_label_translations).
        # The runtime reader also tolerates BCP-47 codes/stems for hand-authored
        # kits, but bare ISO-639-1 that differs from the stem ("zh", "tl") does
        # NOT resolve. The chinese value uses unicode escapes (the CJK word for
        # "single") so this source stays ASCII-only (scar #6 / bd bw8).
        description='Multi-language labels keyed by lowercase spoken-language '
                    'name (e.g., {"spanish": "Soltero", "chinese": "\u5355\u8eab"})'
    )
    pdf_field_name: Optional[str] = Field(None, description="Original PDF field backing this option")
    pdf_on_value: Optional[str] = Field(
        None,
        description="The PDF 'on' state name selecting this option (v2, bd h76m.3). "
                    "For true-AcroForm radio groups the kids share ONE field name "
                    "(on the FIELD's pdf_field_name) and differ only by this state; "
                    "for per-widget checkbox groups it is the widget's on_value "
                    "(usually with option-level pdf_field_name)."
    )
    pdf_position: Optional[PDFPosition] = Field(
        None,
        description="Per-option widget rect, same shape as FormField.pdf_position "
                    "(bd polyglot-pdf-5f41). Populated deterministically from the "
                    "AcroForm dump, keyed by this option's widget."
    )


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

    @field_validator('options', mode='before')
    @classmethod
    def normalize_options(cls, v):
        """
        Normalize options to FieldOption objects.
        Accepts both List[str] and List[FieldOption] formats.
        """
        if v is None or not isinstance(v, list) or not v:
            return v
        
        # Check if first item is a string (simple format)
        if isinstance(v[0], str):
            return [FieldOption(value=opt, label=opt) for opt in v]
        
        return v


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


class AddressFields(BaseModel):
    """Address group sub-fields"""
    street: str = Field(description="Field ID for street address")
    apt: Optional[str] = Field(None, description="Field ID for apartment number")
    city: str = Field(description="Field ID for city")
    state: str = Field(description="Field ID for state")
    zip: str = Field(description="Field ID for ZIP code")
    province: Optional[str] = Field(
        None, description="Field ID for province (international addresses)"
    )
    postal_code: Optional[str] = Field(
        None, description="Field ID for postal code (international addresses)"
    )
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
    spoken_name_translations: Optional[Dict[str, str]] = Field(
        None,
        description="Session-language translations of spoken_name, keyed by "
                    "lowercase English language name ('spanish') -- same "
                    "convention as option label_translations "
                    "(bd polyglot-pdf-tupu.1)")
    spoken_aliases: Optional[List[str]] = Field(None, description="Alternative names for voice input")

    # Type and behavior
    type: FieldType
    validation: Optional[ValidationRules] = None
    read_only: Optional[bool] = Field(
        False, description="Is this field read-only by default? Can be changed by conditional logic."
    )
    hidden: Optional[bool] = Field(
        False, description="Is this field hidden by default? Can be changed by conditional logic."
    )

    # Organization
    section_id: str = Field(description="Which section this belongs to")
    section_label: Optional[str] = Field(None, description="Section display name")
    group_id: Optional[str] = Field(None, description='Grouping within section (e.g., "full-name")')
    group_label: Optional[str] = Field(None, description="Group display name")

    # Conditional display. v1: a single {field, operator, value} condition.
    # v2 (bd h76m.3): additionally accepts a composite ConditionGroup
    # {all_of/any_of/none_of}; readers normalize the legacy shape to a
    # one-atom group (iter_condition_atoms here, normalizeToComposite in TS).
    show_if: Optional[FieldCondition] = Field(
        None, description="Reactive logic: defines if this field should be shown."
    )

    # v2 (bd h76m.3): condition under which this field becomes REQUIRED --
    # sits beside show_if with the same legacy/composite shape and the same
    # evaluator machinery; the target-side require_if is the ONLY require path.
    require_if: Optional[FieldCondition] = Field(
        None, description="Reactive logic: defines when this field is required."
    )

    # Conditional behavior (how to react)
    conditional_behavior: Optional[ConditionalBehavior] = Field(
        None, description="Defines *how* this field reacts to conditional logic (e.g., PDF bit flipping)."
    )

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
    # name_translations: Optional[Dict[str, str]] = Field(
    #     None,
    #     description='Translations of field name for multi-language support (e.g., {"es": "Nombre Completo"})'
    # )

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

    @field_validator('show_if', 'require_if', mode='before')
    @classmethod
    def _no_mixed_condition_shapes(cls, v):
        """Loudly refuse the ambiguous atom+bucket key mix (see
        _reject_mixed_condition_keys) instead of letting the tolerant legacy
        member of the Union win and silently drop the buckets."""
        return _reject_mixed_condition_keys(v)

    @field_validator('options', mode='before')
    @classmethod
    def normalize_options(cls, v):
        """
        Normalize options to FieldOption objects.
        Accepts both List[str] and List[FieldOption] formats.
        Converts simple string lists to FieldOption objects for consistency.
        """
        if v is None or not isinstance(v, list):
            return v
        
        # If empty list, return as-is
        if not v:
            return v
        
        # Check if first item is a string (simple format)
        if isinstance(v[0], str):
            # Convert all strings to FieldOption objects
            return [FieldOption(value=opt, label=opt) for opt in v]
        
        # Already in correct format (dict or FieldOption)
        return v

    @field_validator('options')
    @classmethod
    def validate_options(cls, v, info):
        """Ensure options are provided for select/radio types.

        Deliberately NOT extended to checkbox_group: a v2 group with missing/
        empty options must fall through to _collect_v2_problems, whose
        aggregated report carries the 'fields[i] (id=...)' path and the
        schema's OTHER v2 violations in one error (Codex PR #299). Raising
        here would abort that aggregation with a generic per-field error.
        select/radio keep the historical field-level check (v1 parity).
        """
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
    # Session-language translations of label, keyed by lowercase English
    # language name -- same convention as option label_translations / field
    # spoken_name_translations (bd polyglot-pdf-tupu.2; kit coverage keeps
    # session start free of a live translate call).
    label_translations: Optional[Dict[str, str]] = None
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
    supplement_type: Optional[SupplementType] = None


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

def _v2_condition_problems(
    owner: str,
    kind: str,
    condition: Optional[FieldCondition],
    fields_by_id: Dict[str, "FormField"],
) -> List[str]:
    """v2 checks for one show_if/require_if: operator/trigger compatibility,
    value arity, and option-slug references, per the vocabulary registry."""
    problems: List[str] = []
    for atom in iter_condition_atoms(condition):
        where = f"{owner}.{kind} ({atom.operator.value} on '{atom.field}')"
        spec = vocab.OPERATORS.get(atom.operator.value)
        if spec is None:
            # Unreachable through the enum; guards registry/enum drift.
            problems.append(f"{where}: operator not in the v2 registry")
            continue

        trigger = fields_by_id.get(atom.field)
        if trigger is None:
            problems.append(f"{where}: references non-existent field '{atom.field}'")
            continue
        if trigger.type.value not in vocab.CONDITION_TRIGGER_TYPES:
            problems.append(
                f"{where}: field type '{trigger.type.value}' cannot trigger conditions"
            )
            continue
        if trigger.type.value not in spec.trigger_types:
            allowed = ", ".join(sorted(spec.trigger_types))
            problems.append(
                f"{where}: operator '{atom.operator.value}' is not valid on a "
                f"'{trigger.type.value}' trigger (valid on: {allowed})"
            )
            continue

        if spec.value_arity == "none":
            if atom.value is not None:
                problems.append(
                    f"{where}: operator takes no value (found {atom.value!r})"
                )
            continue
        if spec.value_arity == "list":
            if not isinstance(atom.value, list) or not atom.value:
                problems.append(f"{where}: operator requires a non-empty list value")
                continue
            atom_values = atom.value
        else:  # scalar
            if atom.value is None or isinstance(atom.value, list):
                problems.append(f"{where}: operator requires a single scalar value")
                continue
            atom_values = [atom.value]

        if (
            spec.value_must_be_trigger_option
            and trigger.type.value in vocab.CHOICE_FIELD_TYPES
            and trigger.options
        ):
            slugs = {opt.value for opt in trigger.options}
            for val in atom_values:
                if str(val) not in slugs:
                    problems.append(
                        f"{where}: value {val!r} is not an option slug of "
                        f"'{trigger.id}' (options: {', '.join(sorted(slugs))})"
                    )
    return problems


def _collect_v2_problems(schema: "FormSchema") -> List[str]:
    """All schema-v2 strictness rules (bd h76m.3). Called on EVERY schema since
    the P6.2 flip (bd h76m.16) -- v2 is the only shape; each problem names the
    offending field path."""
    problems: List[str] = []
    fields_by_id = {f.id: f for f in schema.fields}
    is_pdf = schema.source == FormSource.PDF

    for i, f in enumerate(schema.fields):
        path = f"fields[{i}] (id={f.id})"

        if f.type == FieldType.CHECKBOX:
            if f.options:
                problems.append(
                    f"{path}: a v2 checkbox is a standalone boolean; options are "
                    f"forbidden (model the group as type=checkbox_group)"
                )
            if is_pdf and not f.pdf_field_name:
                problems.append(
                    f"{path}: a standalone checkbox on a PDF form requires a "
                    f"field-level pdf_field_name"
                )

        elif f.type.value in vocab.CHOICE_FIELD_TYPES:
            opts = f.options or []
            if len(opts) < 2:
                problems.append(
                    f"{path}: {f.type.value} requires at least 2 options (found {len(opts)})"
                )
            values = [o.value for o in opts]
            for o in opts:
                if not vocab.is_valid_option_slug(o.value):
                    problems.append(
                        f"{path}: option value {o.value!r} is not a v2 slug "
                        f"(lowercase ascii [a-z0-9_-], no commas/spaces; "
                        f"mint from the label)"
                    )
            dupes = sorted({v for v in values if values.count(v) > 1})
            if dupes:
                problems.append(
                    f"{path}: duplicate option values {dupes} (option values must "
                    f"be unique per field)"
                )
            if is_pdf:
                if f.type == FieldType.CHECKBOX_GROUP and f.pdf_field_name:
                    problems.append(
                        f"{path}: a checkbox_group carries NO field-level "
                        f"pdf_field_name; per-box identity lives on "
                        f"options[].pdf_field_name"
                    )
                if f.type == FieldType.CHECKBOX_GROUP:
                    # A checkbox_group's boxes are independent widgets, so each
                    # option MUST carry its own pdf_field_name. The shared-NAME
                    # path (a field-level pdf_field_name + option pdf_on_value) is
                    # RADIO-ONLY and is already forbidden here by the :827 check
                    # above (a checkbox_group may not carry f.pdf_field_name at
                    # all) -- so do NOT offer it as a fillability option here, or
                    # the rule reads as if v2 supports a shared-name checkbox
                    # matrix, which it does not (bd polyglot-pdf-f6lj; the picker,
                    # migrator, and editor-merge all strip a lifted name).
                    for o in opts:
                        if not o.pdf_field_name:
                            problems.append(
                                f"{path}: option {o.value!r} is not PDF-fillable -- "
                                f"a checkbox_group option needs its own "
                                f"pdf_field_name"
                            )
                elif f.type == FieldType.RADIO:
                    # Radio IS a shared AcroForm field: an option is fillable via
                    # its own pdf_field_name OR the shared-name shape (field-level
                    # pdf_field_name + option pdf_on_value).
                    for o in opts:
                        fillable = bool(o.pdf_field_name) or bool(
                            f.pdf_field_name and o.pdf_on_value
                        )
                        if not fillable:
                            problems.append(
                                f"{path}: option {o.value!r} is not PDF-fillable -- "
                                f"needs option pdf_field_name, or a field-level "
                                f"pdf_field_name plus option pdf_on_value"
                            )
                elif f.type == FieldType.SELECT and not f.pdf_field_name:
                    problems.append(
                        f"{path}: a select on a PDF form requires a field-level "
                        f"pdf_field_name"
                    )

        problems.extend(_v2_condition_problems(path, "show_if", f.show_if, fields_by_id))
        problems.extend(_v2_condition_problems(path, "require_if", f.require_if, fields_by_id))

    for i, s in enumerate(schema.sections):
        section_path = f"sections[{i}] (id={s.id})"
        problems.extend(_v2_condition_problems(section_path, "show_if", s.show_if, fields_by_id))

    return problems


class FormSchema(BaseModel):
    """Complete form schema"""
    # Metadata
    source: FormSource
    form_metadata: FormMetadata

    # Wire-format version (bd h76m.3). None/'1' = legacy v1 (tolerant: the
    # pre-v2 group modeling and conditional shapes parse unchanged); '2'
    # opts in to the strict v2 rules (checkbox_group modeling, option slugs,
    # option-value uniqueness, operator/trigger compatibility). The v1 read
    # window closes at the P6.2 strictness flip.
    schema_version: Optional[str] = Field(
        None,
        description="Schema wire-format version: None/'1' legacy, '2' strict v2."
    )

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

    @field_validator('schema_version', mode='before')
    @classmethod
    def _coerce_schema_version(cls, v):
        """Coerce to str; any stamp other than '2' takes the legacy path.

        Stored drafts in the wild carry stamps like '1.0' that predate this
        field being modeled at all (it was ignored as an extra key) --
        rejecting them would break the very v1 tolerance this bead promises
        (Codex PR #299). Only the exact '2' activates the strict rules; the
        P6.2 strictness flip is where non-v2 stamps become errors.
        """
        if v is None:
            return v
        return str(v)

    @model_validator(mode='after')
    def _enforce_v2_rules(self):
        """Apply the strict v2 rules to EVERY schema (bd h76m.16, P6.2 flip).

        The v1-acceptance bypass is gone: schema v2 is the only shape. All
        stored kits are migrated to v2 (i-90/w7/f1040), and the trigger-
        side controls_fields / group_kind / conditional_fields fields have been
        deleted from the model. The model uses the default extra="ignore", so a
        legacy schema carrying those keys does NOT fail here -- the key is
        SILENTLY DROPPED. That silent-drop is why schema_lint ERRORs on a v2 kit
        still carrying controls_fields, and why the mark-complete gate requires
        schema_version=="2" (bd polyglot-pdf-t96a) -- the model is not a backstop
        for the removed keys. The dict-based migration script
        (migrate_schema_v2.py) reads raw v1 dicts and does NOT go through this
        model, so it is unaffected.
        """
        problems = _collect_v2_problems(self)
        if problems:
            raise ValueError(
                "schema v2 validation failed:\n"
                + "\n".join(f"- {p}" for p in problems)
            )
        return self

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

        # Validate conditional display references (legacy single conditions
        # and v2 composite groups both flatten through iter_condition_atoms).
        condition_edges: Dict[str, set] = {}
        for field in self.fields:
            triggers = set()
            for kind, condition in (("show_if", field.show_if), ("require_if", field.require_if)):
                for atom in iter_condition_atoms(condition):
                    triggers.add(atom.field)
                    if atom.field not in all_field_ids:
                        errors.append(
                            f"Field '{field.id}' {kind} references non-existent field '{atom.field}'"
                        )
            if triggers:
                condition_edges[field.id] = triggers

        # Section-level show_if references (same atom-reference check as
        # fields, but sections only carry the legacy single-atom shape).
        for section in self.sections:
            for atom in iter_condition_atoms(section.show_if):
                if atom.field not in all_field_ids:
                    errors.append(
                        f"Section '{section.id}' show_if references non-existent field '{atom.field}'"
                    )

        # show_if/require_if cycle detection (warning, not error): a field
        # whose visibility depends -- directly or transitively -- on itself
        # can never settle deterministically (bd h76m.3).
        def _find_cycle(start: str) -> Optional[List[str]]:
            stack: List[tuple] = [(start, [start])]
            while stack:
                node, path = stack.pop()
                for nxt in condition_edges.get(node, ()):
                    if nxt == start:
                        return path + [start]
                    if nxt not in path:
                        stack.append((nxt, path + [nxt]))
            return None

        reported: set = set()
        for field_id in condition_edges:
            if field_id in reported:
                continue
            cycle = _find_cycle(field_id)
            if cycle:
                reported.update(cycle)
                warnings.append(
                    "Conditional cycle: " + " -> ".join(cycle)
                    + " (visibility depends on itself)"
                )

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
