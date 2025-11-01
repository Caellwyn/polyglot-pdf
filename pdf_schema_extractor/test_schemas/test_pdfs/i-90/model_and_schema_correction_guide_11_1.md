I-90 Schema Conformance GuideThis document provides a step-by-step guide to refactor i-90_schema_v8_final.json to fully conform to the FormSchema Pydantic model defined in form_models.py.The changes are organized from the most critical structural fixes to specific field-level corrections.1. Restructure Root to Match FormSchema (Critical)The most significant issue is that the current JSON is a root object containing form_metadata and fields, not a valid FormSchema object. The entire file structure must be updated.Action:Wrap the existing form_metadata and fields blocks inside a new root object that includes all required keys from the FormSchema model: source, sections, parts, and extraction_info.Step 1.1: Modify the Root JSON StructureChange the JSON from this:{
  "form_metadata": { ... },
  "fields": [ ... ],
  "conditional_index": { ... }
}
To this:{
  "source": "pdf",
  "form_metadata": {
    "title": "Form I-90, Application to Replace Permanent Residence Card",
    "form_number": "I-90",
    "edition_date": "01/20/25",
    "page_count": 7,
    "agency": "U.S. Citizenship and Immigration Services"
  },
  "parts": [
    {
      "id": "part_1",
      "label": "Part 1. Information About You",
      "order": 1,
      "section_ids": ["part_1_info_you", "part_1_mailing_addr", "part_1_phys_addr", "part_1_addl_info"]
    },
    {
      "id": "part_2",
      "label": "Part 2. Application Type",
      "order": 2,
      "section_ids": ["part_2_app_type"]
    },
    {
      "id": "part_3",
      "label": "Part 3. Processing Information",
      "order": 3,
      "section_ids": ["part_3_processing", "part_3_bio_info"]
    },
    {
      "id": "part_4",
      "label": "Part 4. Accommodations for Individuals with Disabilities and/or Impairments",
      "order": 4,
      "section_ids": ["part_4_accommodations"]
    },
    {
      "id": "part_5",
      "label": "Part 5. Applicant's Statement, Contact Information, Certification, and Signature",
      "order": 5,
      "section_ids": ["part_5_applicant_statement"]
    },
    {
      "id": "part_6",
      "label": "Part 6. Interpreter's Contact Information, Certification, and Signature",
      "order": 6,
      "section_ids": ["part_6_interpreter_info"]
    },
    {
      "id": "part_7",
      "label": "Part 7. Contact Information, Declaration, and Signature of the Person Preparing this Application, if Other Than the Applicant",
      "order": 7,
      "section_ids": ["part_7_preparer_info"]
    },
    {
      "id": "part_8",
      "label": "Part 8. Additional Information",
      "order": 8,
      "section_ids": ["part_8_additional_info"]
    }
  ],
  "sections": [
    { "id": "part_1_info_you", "label": "Information About You", "order": 1, "fields": [...] },
    { "id": "part_1_mailing_addr", "label": "Mailing Address", "order": 2, "fields": [...] },
    { "id": "part_1_phys_addr", "label": "Physical Address", "order": 3, "fields": [...] },
    { "id": "part_1_addl_info", "label": "Additional Information", "order": 4, "fields": [...] },
    { "id": "part_2_app_type", "label": "Application Type", "order": 1, "fields": [...] },
    { "id": "part_3_processing", "label": "Processing Information", "order": 1, "fields": [...] },
    { "id": "part_3_bio_info", "label": "Biographic Information", "order": 2, "fields": [...] },
    { "id": "part_4_accommodations", "label": "Accommodations", "order": 1, "fields": [...] },
    { "id": "part_5_applicant_statement", "label": "Applicant's Statement", "order": 1, "fields": [...] },
    { "id": "part_6_interpreter_info", "label": "Interpreter Information", "order": 1, "fields": [...] },
    { "id": "part_7_preparer_info", "label": "Preparer Information", "order": 1, "fields": [...] },
    { "id": "part_8_additional_info", "label": "Additional Information", "order": 1, "fields": [...] }
  ],
  "fields": [
    ...
  ],
  "extraction_info": {
    "extracted_at": "2025-11-01T14:30:00Z",
    "extraction_confidence": 0.95,
    "extractor_version": "v8_final",
    "manual_review_required": false,
    "manual_review_completed": true,
    "approved_by": "system"
  }
}
Step 1.2: Create sections and parts ListsYou must create the sections and parts lists (as shown above). This involves:Creating FormSection objects: Go through all fields and identify the unique section_id strings (e.g., "Part 1 - Information About You"). Create a FormSection object for each, giving it a stable id (e.g., part_1_info_you).Updating FormField.section_id: Change the section_id of every field to match the new stable id (e.g., "Part 1 - Information About You" becomes "part_1_info_you").Creating FormPart objects: Create FormPart objects for each "Part" of the form and list their corresponding section_ids.2. Consolidate Multi-Option GroupsThe schema inconsistently defines fields for single-choice (radio) and multiple-choice (checkbox) groups. This must be cleaned up to match the PDF and Pydantic model.Action: Consolidate scattered field definitions for Ethnicity, Race, Eye Color, and Hair Color into one FormField object for each group.Field Group (PDF)PDF RuleSchema IssueCorrectionEthnicity (P3, I6)Select onep3_checkbox6[1] is radio but has a confusing ID.1. Rename id: "p3_checkbox6[1]" to id: "p3_ethnicity".  2. Confirm type: "radio" and its two options are correct.Race (P3, I7)Select allp3_checkbox7_white is checkbox but has a confusing ID.1. Rename id: "p3_checkbox7_white" to id: "p3_race".  2. Confirm type: "checkbox" and all 5 options are correct.Eye Color (P3, I10)Select oneDefined as two separate fields: p3_checkbox10[3] (checkbox) and p3_checkbox10[6] (radio).1. Delete both p3_checkbox10[3] and p3_checkbox10[6].  2. Add a new field: id: "p3_eye_color", type: "radio".  3. Add all 9 options (Black, Blue, Brown, Gray, Green, Hazel, Maroon, Pink, Unknown/Other) to its options array.Hair Color (P3, I11)Select oneDefined as two separate fields: p3_checkbox11 (checkbox) and p3_checkbox11[2] (checkbox).1. Delete both p3_checkbox11 and p3_checkbox11[2].  2. Add a new field: id: "p3_hair_color", type: "radio".  3. Add all 9 options (Bald, Black, Blond, Brown, Gray, Red, Sandy, White, Unknown/Other) to its options array.3. Align validation Objects with ValidationRulesThe validation objects in the schema use custom keys that do not match the ValidationRules Pydantic model.Action: Update all validation objects to use the keys defined in ValidationRules: format_preset, min_length, max_length, pattern, etc.Field IDNon-Conformant validation (Schema)Conformant validation (Correction)p1_line1_aliennumber{"type": "a_number", "pattern": "^\\d{7,9}$"}{"format_preset": "a_number", "pattern": "^\\d{7,9}$"}p1_line2_acctidentifier{"type": "uscis_account", "exact_length": 12}{"min_length": 12, "max_length": 12}p1_line6f_zipcode{"type": "zip_code", "pattern": "^\\d{5}$"}{"format_preset": "zip", "pattern": "^\\d{5}$"}p1_line16_ssn{"type": "ssn", "pattern": "^\\d{9}$"}{"format_preset": "ssn", "pattern": "^\\d{9}$"}p1_line9_dateofbirth{"type": "date", ...}{} (Remove entire object. type: "date" on the field is sufficient)p5_line3_daytimephonenumber{"type": "phone_number", ...}{"format_preset": "phone"}p7_line3e_zipcode{"type": "zip_code", ...}{"format_preset": "zip", "pattern": "^\\d{5}$"}p7_line4_preparersdaytimephonenumber{"type": "phone_number", ...}{"format_preset": "phone"}General Rules for this step:Change validation.type to validation.format_preset for: a_number, ssn.Change validation.type to validation.format_preset AND correct the value for:"zip_code" -> "format_preset": "zip""phone_number" -> "format_preset": "phone"Replace non-standard keys like "exact_length": 12 with {"min_length": 12, "max_length": 12}.Remove any validation object from fields that are already type: "date". The validation is redundant.4. Remove Non-Conformant help.conditional_logic KeyThe schema places a custom conditional_logic object inside the help object of many fields. This is non-conformant, as FieldHelp has no such key, and it's redundant with the show_if key and conditional_index.Action:Search for every field in the schema and delete the entire conditional_logic: { ... } object from within its help property.Example (Field p1_line5a_familyname):Change this:"help": {
  "instructions": "Enter your family name exactly as it appears...",
  "conditional_logic": {
    "trigger_field": "p1_checkbox4",
    "trigger_value": "P1_checkbox4[0]",
    "dependent_fields": [],
    "unlock_method": "flip_readonly_bit",
    "description": "If name has legally changed...",
    "pdf_field_flag_change": { ... },
    "unlock_instructions": { ... }
  }
}
To this:"help": {
  "instructions": "Enter your family name exactly as it appears..."
}
Repeat this for all affected fields.5. Refine Address Grouping (Using address_group)The Pydantic model provides a FieldType.ADDRESS_GROUP which acts as a mapper to link individual address fields. This should be added for semantic clarity.Action:Add new "container" fields of type address_group for the Mailing and Physical addresses. Do not delete the individual fields (street, city, etc.), as the AddressFields model maps to their IDs.Add the following new field to the fields list:{
  "id": "p1_mailing_address_group",
  "name": "Mailing Address",
  "spoken_name": "mailing address",
  "type": "address_group",
  "section_id": "part_1_mailing_addr",
  "address_fields": {
    "street": "p1_line6b_streetnumbername",
    "apt": "p1_line6c_aptsteflrnumber",
    "city": "p1_line6d_cityortown",
    "state": "p1_line6e_state",
    "zip": "p1_line6f_zipcode",
    "country": "p1_line6i_country"
  },
  "help": {
    "instructions": "Enter your complete mailing address."
  }
}
Note on Limitation: The AddressFields model in form_models.py does not include properties for province or postal_code. The form_models.py should be updated to handle these.

Here is a suggestion for that update.

# ... existing code ...
class AddressFields(BaseModel):
    """Address group sub-fields"""
    street: str = Field(description="Field ID for street address")
    apt: Optional[str] = Field(None, description="Field ID for apartment number")
    city: str = Field(description="Field ID for city")
    state: str = Field(description="Field ID for state")
    zip: str = Field(description="Field ID for ZIP code")
    province: Optional[str] = Field(None, description="Field ID for province (international addresses)")
    postal_code: Optional[str] = Field(None, description="Field ID for postal code (international addresses)")
    country: Optional[str] = Field(None, description="Field ID for country (international addresses)")


# ============================================================================
# ... existing code ...

Further model updates suggested:

"""
Polyglot PDF Form Schema - Pydantic Models
...
@version 1.1.0
@date 2025-11-01
"""

from typing import Optional, List, Dict, Any, Literal, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# ============================================================================
# Enums and Type Definitions
# ============================================================================

# ... (No changes to FormSource, DatePrecision, DateFormat, FieldType) ...
# ... (No changes to SignatureMethod, TextareaSize) ...

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

# ... (No changes to SupplementType, GroupKind, SessionStatus) ...


# ============================================================================
# Supporting Models
# ============================================================================

# ... (No changes to FormMetadata, PDFPosition, ValidationRules) ...

class ConditionalDisplay(BaseModel):
    """
    Reactive, dependent-side logic.
    Used on a field to define the condition under which it should be shown.
    Example: Placed on Field B, "Show me if Field A's value is 'Yes'."
    """
    field: str = Field(description="Field ID to check")
    operator: ConditionalOperator
    value: Union[str, int, float, bool, List[Union[str, int, float, bool]]]


# --- NEW MODEL ---
class ConditionalControl(BaseModel):
    """
    Proactive, trigger-side logic.
    Used on a field to define what it controls when its value changes.
    Example: Placed on Field A, "When my value is 'Yes', unlock Field B and show Field C."
    """
    operator: ConditionalOperator = Field(
        default=ConditionalOperator.EQUALS,
        description="The operator to check this field's value against."
    )
    value: Union[str, int, float, bool, List[Union[str, int, float, bool]]] = Field(
        description="The value (or list of values) to check for."
    )
    
    # Define all possible actions
    shows: Optional[List[str]] = Field(
        None, description="List of field IDs to show (make not hidden)."
    )
    hides: Optional[List[str]] = Field(
        None, description="List of field IDs to hide."
    )
    unlocks: Optional[List[str]] = Field(
        None, description="List of field IDs to unlock (make not read-only)."
    )
    locks: Optional[List[str]] = Field(
        None, description="List of field IDs to lock (make read-only)."
    )
    makes_required: Optional[List[str]] = Field(
        None, description="List of field IDs to make required."
    )
    makes_optional: Optional[List[str]] = Field(
        None, description="List of field IDs to make optional (not required)."
    )


# --- NEW MODEL ---
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
    # ... other behaviors can be added as needed
    

class FieldHelp(BaseModel):
    """Field-level help and instruction text"""
    inline: Optional[str] = Field(None, description='Inline hint text like "(if any)"')
    tooltip: Optional[str] = Field(None, description="Hover tooltip")
    instructions: Optional[str] = Field(None, description="Longer instructions below field")
    warning: Optional[str] = Field(None, description="Legal warning or important note")
    example: Optional[str] = Field(None, description="Example value")
    legal_reference: Optional[str] = Field(None, description='Legal reference (e.g., "INA 241(b)(3)", "18 USC 1546(a)")')
    # --- REMOVED ---
    # The non-conformant `conditional_logic` block that was previously
    # in the I-90 JSON's `help` object is now formally replaced by 
    # `conditional_behavior` on the `FormField` itself.


class FieldOption(BaseModel):
# ... (No changes to FieldOption, TableColumn, MultiEntryConfig) ...


# --- MODIFIED MODEL ---
class AddressFields(BaseModel):
    """Address group sub-fields"""
    street: str = Field(description="Field ID for street address")
    apt: Optional[str] = Field(None, description="Field ID for apartment number")
    city: str = Field(description="Field ID for city")
    state: str = Field(description="Field ID for state")
    zip: str = Field(description="Field ID for ZIP code")
    # --- ADDED ---
    province: Optional[str] = Field(
        None, description="Field ID for province (international addresses)"
    )
    postal_code: Optional[str] = Field(
        None, description="Field ID for postal code (international addresses)"
    )
    # --- (End of Add) ---
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
    # --- ADDED ---
    read_only: Optional[bool] = Field(
        False, description="Is this field read-only by default? Can be changed by conditional logic."
    )
    hidden: Optional[bool] = Field(
        False, description="Is this field hidden by default? Can be changed by conditional logic."
    )
    # --- (End of Add) ---

    # Organization
    section_id: str = Field(description="Which section this belongs to")
    # ... (No changes to section_label, group_id, group_label, group_kind) ...

    # Conditional display
    show_if: Optional[ConditionalDisplay] = Field(
        None, description="Reactive logic: defines if this field should be shown."
    )
    
    # --- REPLACED ---
    # conditional_fields: Optional[List[str]] = Field(...)
    # --- with ---
    controls_fields: Optional[List[ConditionalControl]] = Field(
        None,
        alias="controls",  # Allows JSON to use "controls" or "controls_fields"
        description="Proactive logic: defines how this field's value affects other fields."
    )
    # --- (End of Replace) ---

    # --- ADDED ---
    conditional_behavior: Optional[ConditionalBehavior] = Field(
        None, description="Defines *how* this field reacts to conditional logic (e.g., PDF bit flipping)."
    )
    # --- (End of Add) ---

    # Help and guidance
    help: Optional[FieldHelp] = None
    # ... (No changes to placeholder, description) ...

    # PDF-specific
    # ... (No changes to pdf_position, pdf_field_name) ...

    # Type-specific properties
    # ... (No changes to date, text, numeric, select, signature, address, or table properties) ...

    # ... (No changes to auto_fill_na, overflow_to_supplement, or @field_validator) ...

# ... (Rest of file unchanged) ...
```

### How to Use These New Models

This new structure fully supports your requirements by separating the *trigger's intent* from the *dependent's behavior*.

**1. The Trigger Field (Proactive Logic)**

Your **Trigger Field** (e.g., `p1_checkbox4`) now uses the `controls_fields` property. This tells the system *what* to do.

**Example `p1_checkbox4` JSON:**
```json
{
  "id": "p1_checkbox4",
  "name": "Has Your Name Legally Changed?",
  "type": "radio",
  "section_id": "part_1_info_you",
  "options": [
    { "value": "P1_checkbox4[0]", "label": "Yes" },
    { "value": "P1_checkbox4[1]", "label": "No" },
    { "value": "P1_checkbox4[2]", "label": "Not Applicable" }
  ],
  "controls_fields": [
    {
      "operator": "equals",
      "value": "P1_checkbox4[0]",
      "shows": [],
      "unlocks": [
        "p1_line5a_familyname",
        "p1_line5b_givenname",
        "p1_line5c_middlename"
      ],
      "makes_required": []
    }
  ]
}
```

**2. The Dependent Field (Reactive Behavior)**

Your **Dependent Field** (e.g., `p1_line5a_familyname`) is set to `read_only: true` by default. It now uses the `conditional_behavior` property to tell the system *how* to perform the "unlock" action requested by the trigger.

**Example `p1_line5a_familyname` JSON:**
```json
{
  "id": "p1_line5a_familyname",
  "name": "Family Name (Last Name). ",
  "type": "text",
  "section_id": "part_1_info_you",
  "read_only": true,
  "show_if": {
    "field": "p1_checkbox4",
    "operator": "equals",
    "value": "P1_checkbox4[0]"
  },
  "conditional_behavior": {
    "unlock_method": "flip_readonly_bit"
  },
  "help": {
    "instructions": "Enter your family name exactly as it is printed on your current Permanent Resident Card."
  }
}

