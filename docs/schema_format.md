# FormSchema Format Specification

**Version**: 1.0
**Date**: October 26, 2025
**Status**: Living reference

---

## Overview

The FormSchema format is a comprehensive JSON/Python structure for representing fillable PDF forms (especially USCIS immigration forms). It supports:

- Multiple field types (text, textarea, date, radio, checkbox, select, signature, etc.)
- Conditional logic (show/hide fields based on other values)
- Multi-entry/repeating fields (children, employment history, etc.)
- Validation rules (required, format, patterns, date constraints)
- Supplement mapping (overflow to Supplement A -- the only modeled supplement type)
- Multi-language support
- Hierarchical structure (Form > Parts > Sections > Fields)

---

## High-Level Structure

```
FormSchema
├── form_metadata (FormMetadata)
│   ├── title, form_number, version, edition_date
│   └── agency, page_count, expiration_date, etc.
├── parts (List[FormPart]) - Optional hierarchical grouping
│   └── Part A, Part B, Part C, etc.
├── sections (List[FormSection])
│   └── Part A.I, Part A.II, Part B, etc.
├── fields (List[FormField])
│   └── All form fields (flat list)
├── supplements (List[FormSupplement]) - Optional
│   └── Supplement A (the only modeled supplement type today)
└── extraction_info (ExtractionInfo) - For PDF forms
```

---

## Core Components

### 1. FormSchema (Root)

The top-level container for the entire form definition.

**Required Fields**:
- `source`: `"web"` or `"pdf"`
- `form_metadata`: Metadata object (see below)
- `sections`: Array of section definitions
- `fields`: Array of all field definitions

**Optional Fields**:
- `parts`: Array of part definitions (for hierarchical forms like I-589)
- `supplements`: Array of supplement page definitions
- `extraction_info`: Extraction metadata (required for PDF forms)
- `legal_warnings`: Array of form-level legal warnings

**Example**:
```json
{
  "source": "pdf",
  "form_metadata": {
    "title": "Application for Asylum and for Withholding of Removal",
    "form_number": "I-589",
    "version": "1.0",
    "edition_date": "2025-01-20",
    "expiration_date": "2027-09-30",
    "omb_number": "1615-0067",
    "page_count": 12,
    "agency": "U.S. Citizenship and Immigration Services",
    "language": "en"
  },
  "parts": [...],
  "sections": [...],
  "fields": [...],
  "supplements": [...],
  "legal_warnings": [
    "WARNING: Applicants who make frivolous applications..."
  ]
}
```

---

### 2. FormPart (Hierarchical Grouping)

**Purpose**: Groups sections into major parts (e.g., Part A, Part B).

**Required Fields**:
- `id`: Unique identifier (e.g., `"part_a"`)
- `label`: Display label (e.g., `"Part A: Information About Applicant"`)
- `order`: Display order (integer)
- `section_ids`: Array of section IDs in this part

**Optional Fields**:
- `description`: Instructions for this part
- `required`: Boolean (default `true`)

**Example**:
```json
{
  "id": "part_a",
  "label": "Part A: Information About Applicant",
  "description": "Provide information about yourself and your family",
  "order": 1,
  "section_ids": ["part_a_i", "part_a_ii", "part_a_iii"],
  "required": true
}
```

---

### 3. FormSection

**Purpose**: Logical grouping of fields (e.g., Part A.I, Part A.II).

**Required Fields**:
- `id`: Unique identifier (e.g., `"part_a_i"`)
- `label`: Display label (e.g., `"Part A.I: Information About You"`)
- `order`: Display order (integer)
- `fields`: Array of field IDs in this section

**Optional Fields**:
- `description`: Instructions for this section
- `page_number`: PDF page number (single page)
- `page_numbers`: Array of page numbers (if section spans multiple pages)
- `required`: Boolean (default `true`)
- `show_if`: Conditional display rule

**Example**:
```json
{
  "id": "part_a_ii",
  "label": "Part A.II: Information About Your Spouse and Children",
  "description": "List all children regardless of age, location, or marital status",
  "order": 2,
  "fields": ["a2_spouse_not_married", "a2_spouse_lastname", ...],
  "page_numbers": [2, 3],
  "required": true,
  "show_if": {
    "field": "a1_marital_status",
    "operator": "equals",
    "value": "married"
  }
}
```

---

### 4. FormField

**Purpose**: Individual form input.

**Required Fields**:
- `id`: Unique field identifier (e.g., `"a1_lastname"`)
- `name`: Display label (e.g., `"Complete Last Name"`)
- `spoken_name`: Name for voice interaction (e.g., `"last name"`)
- `type`: Field type (see Field Types below)
- `section_id`: Which section this belongs to

**Common Optional Fields**:
- `validation`: Validation rules object
- `help`: Help text object (inline, tooltip, instructions, warning, legal_reference)
- `show_if` / `hide_if`: Conditional display logic
- `placeholder`: Placeholder text
- `description`: Field description
- `pdf_field_name`: Original PDF fillable field name
- `pdf_position`: PDF coordinates object
- `name_translations`: Multi-language name translations
- `auto_fill_na`: Boolean for auto-fill NA logic
- `overflow_to_supplement`: Which supplement to use for overflow

**Type-Specific Fields**:

**Date Fields**:
- `date_precision`: `"full"`, `"month_year"`, or `"year_only"`
- `format`: `"mm/dd/yyyy"`, `"Mo/Yr"`, `"yyyy"`, or `"YYYY-MM-DD"`
- `min_date` / `max_date`: ISO date strings

**Textarea Fields**:
- `textarea_size`: `"small"`, `"medium"`, `"large"`, or `"xlarge"`
- `rows`: Explicit row count (overrides size)

**Select/Radio/Checkbox Fields**:
- `options`: Array of option objects
- `allow_multiple`: Boolean (for checkbox groups)

**Signature Fields**:
- `signature_method`: `"draw"`, `"upload"`, or `"type"`
- `signature_box_style`: free-form string (e.g. `"bracketed"` for I-589 Part D); not an enforced enum

**Table Fields**:
- `columns`: Array of column definitions
- `multi_entry`: Multi-entry configuration object

**Example (Simple Text Field)**:
```json
{
  "id": "a1_lastname",
  "name": "Complete Last Name",
  "spoken_name": "last name",
  "type": "text",
  "section_id": "part_a_i",
  "validation": {
    "required": true,
    "min_length": 1,
    "max_length": 100
  },
  "help": {
    "inline": null,
    "tooltip": "Enter your full legal last name as it appears on official documents"
  },
  "pdf_field_name": "a1_lastname",
  "pdf_position": {
    "page": 1,
    "x": 150.5,
    "y": 620.3,
    "width": 300.0,
    "height": 20.0
  }
}
```

**Example (Date Field with Constraint)**:
```json
{
  "id": "a1_dob",
  "name": "Date of Birth",
  "spoken_name": "date of birth",
  "type": "date",
  "section_id": "part_a_i",
  "date_precision": "full",
  "format": "mm/dd/yyyy",
  "validation": {
    "required": true,
    "date_constraint": "past_only"
  },
  "help": {
    "inline": null,
    "example": "01/15/1985"
  }
}
```

**Example (Radio Field)**:
```json
{
  "id": "a1_sex",
  "name": "Sex",
  "spoken_name": "sex",
  "type": "radio",
  "section_id": "part_a_i",
  "options": [
    {
      "value": "male",
      "label": "Male",
      "spoken_label": "male",
      "label_translations": {
        "spanish": "Masculino",
        "chinese": "男"
      }
    },
    {
      "value": "female",
      "label": "Female",
      "spoken_label": "female",
      "label_translations": {
        "spanish": "Femenino",
        "chinese": "女"
      }
    }
  ],
  "validation": {
    "required": true
  }
}
```

**Example (Textarea with Supplement Overflow)**:
```json
{
  "id": "b1a_narrative",
  "name": "Describe harm or mistreatment you experienced in the past",
  "spoken_name": "past harm narrative",
  "type": "textarea",
  "section_id": "part_b",
  "textarea_size": "xlarge",
  "rows": 20,
  "validation": {
    "required": true,
    "min_length": 50
  },
  "help": {
    "instructions": "Explain: 1) What happened, 2) When it occurred, 3) Who caused it, 4) Why you believe it occurred",
    "warning": "Provide detailed and truthful information. False statements may result in denial."
  },
  "overflow_to_supplement": "supplement_a"
}
```

**Example (Table/Multi-Entry Field)**:
```json
{
  "id": "a2_children",
  "name": "Your Children",
  "spoken_name": "children",
  "type": "table",
  "section_id": "part_a_ii",
  "columns": [
    {
      "id": "lastname",
      "label": "Last Name",
      "type": "text",
      "width": 25,
      "validation": {"required": true}
    },
    {
      "id": "firstname",
      "label": "First Name",
      "type": "text",
      "width": 25,
      "validation": {"required": true}
    },
    {
      "id": "dob",
      "label": "Date of Birth",
      "type": "date",
      "width": 20,
      "validation": {"required": true}
    },
    {
      "id": "in_us",
      "label": "In U.S.?",
      "type": "radio",
      "width": 15
    }
  ],
  "multi_entry": {
    "min_entries": 0,
    "max_entries": null,
    "initial_rows": 4,
    "add_button_label": "Add Child",
    "remove_button_label": "Remove",
    "overflow_instruction": "Use Supplement A for more than 4 children",
    "overflow_to_supplement": "supplement_a"
  },
  "auto_fill_na": true
}
```

---

### 5. Field Types

| Type | Description | Example Use Cases |
|------|-------------|-------------------|
| `text` | Single-line text input | Name, address, A-number |
| `textarea` | Multi-line text input | Narratives, explanations |
| `date` | Date picker | Birth date, entry date, marriage date |
| `number` | Numeric input | Age, number of children |
| `tel` | Phone number | Contact phone |
| `email` | Email address | Contact email |
| `select` | Dropdown menu | State selection, country list |
| `radio` | Radio buttons | Yes/No, sex, marital status |
| `checkbox` | Checkbox(es) | Agreement, multi-select options |
| `signature` | Signature capture | Applicant signature, preparer signature |
| `address_group` | Compound address | Residence, mailing address |
| `table` | Repeating rows | Children, employment history, addresses |
| `checkbox_group` | v2 multi-select modeled as ONE field | "Basis for asylum" (select all that apply) -- see Section 15 |

---

### 6. Validation Rules

**ValidationRules Object**:

```json
{
  "required": true,
  "min_length": 1,
  "max_length": 100,
  "min": 0,
  "max": 150,
  "pattern": "^[A-Z0-9]+$",
  "custom_error": "A-Number must be 8-9 digits starting with A",
  "date_constraint": "past_only",
  "format_preset": "ssn"
}
```

**Validation Types**:
- `required`: Boolean
- `min_length` / `max_length`: Integer (for text fields)
- `min` / `max`: Number (for numeric fields)
- `pattern`: Regex string
- `custom_error`: Custom error message
- `date_constraint`: `"past_only"`, `"future_only"`, `"within_5_years"`
- `format_preset`: `"ssn"`, `"a_number"`, `"phone"`, `"email"`, `"zip"`, `"uscis_account"`

**Date Constraints**:
- `past_only`: Date must be in the past (e.g., birth date)
- `future_only`: Date must be in the future (e.g., passport expiration)
- `within_5_years`: Date must be within last 5 years (e.g., employment history)

**Format Presets**:
- `ssn`: Social Security Number (###-##-####)
- `a_number`: A-Number (A########)
- `phone`: Phone number ((###) ###-####)
- `email`: Email address
- `zip`: ZIP code (#####)
- `uscis_account`: USCIS Online Account Number (strips punctuation before length/pattern checks)

---

### 7. Conditional Logic

**ConditionalDisplay Object**:

```json
{
  "field": "a2_spouse_in_us",
  "operator": "equals",
  "value": "yes"
}
```

**Operators**:
- `equals`: Field value equals specified value
- `not_equals`: Field value does not equal specified value
- `in`: Field value in list of values
- `not_in`: Field value not in list
- `contains`: Field value contains substring
- `greater_than` / `less_than`: Numeric comparison
- `is_empty` / `is_not_empty`: Field has no value / has value
- `is_checked`: Checkbox is checked

**Usage**:
- `show_if`: Show field if condition is true
- `hide_if`: Hide field if condition is true

**Example (Show spouse details if married)**:
```json
{
  "id": "a2_spouse_lastname",
  "name": "Spouse Last Name",
  "type": "text",
  "section_id": "part_a_ii",
  "show_if": {
    "field": "a1_marital_status",
    "operator": "equals",
    "value": "married"
  }
}
```

**Example (Show U.S. entry fields if spouse in U.S.)**:
```json
{
  "id": "a2_spouse_entry_date",
  "name": "Date of Last Entry into the U.S.",
  "type": "date",
  "section_id": "part_a_ii",
  "show_if": {
    "field": "a2_spouse_in_us",
    "operator": "equals",
    "value": "yes"
  }
}
```

---

### 8. Multi-Entry/Repeating Fields

**MultiEntryConfig Object**:

```json
{
  "min_entries": 0,
  "max_entries": null,
  "initial_rows": 4,
  "add_button_label": "Add Child",
  "remove_button_label": "Remove",
  "overflow_instruction": "Use Supplement A for more than 4 children",
  "overflow_to_supplement": "supplement_a"
}
```

**Fields**:
- `min_entries`: Minimum required entries (e.g., 1 for "at least one child")
- `max_entries`: Maximum allowed (null = unlimited)
- `initial_rows`: How many rows to show initially
- `add_button_label`: Label for "Add" button
- `remove_button_label`: Label for "Remove" button
- `overflow_instruction`: Message when max reached
- `overflow_to_supplement`: Which supplement to use -- `"supplement_a"` is the
  only value the `SupplementType` enum accepts today
  (`backend/models/form_models.py`); the feature is not fully implemented
  beyond this one generic supplement type

**Example Use Cases**:
- **Children**: Min 0, Max unlimited, Initial 4, Overflow to Supplement A
- **U.S. Entries**: Min 1, Max unlimited, Initial 3, Overflow to Supplement A
- **Employment History**: Min 0, Max unlimited, Initial 4, Overflow to Supplement A
- **Addresses (Last 5 Years)**: Min 1, Max unlimited, Initial 5, Overflow to Supplement A

---

### 9. Supplement Pages

**FormSupplement Object**:

```json
{
  "id": "supplement_a",
  "name": "Supplement A - Additional Children",
  "purpose": "Use this supplement to list additional children beyond the first 4",
  "trigger_condition": "More than 4 children",
  "fields": ["sa_anumber", "sa_date", "sa_applicant_name", "sa_applicant_signature", "sa_child1_*", ...],
  "page_number": 11
}
```

**Common Supplements**:

**Supplement A (I-589)**: Additional children
- Header: A-Number, Date, Applicant Name, Signature
- Content: Repeating child entries (2 per page)

Only `supplement_a` is modeled by `SupplementType`
(`backend/models/form_models.py`) today; a second supplement type is not
implemented.

---

### 10. Help Text and Instructions

**FieldHelp Object**:

```json
{
  "inline": "(if any)",
  "tooltip": "Hover for more information",
  "instructions": "Provide the following information: ...",
  "warning": "False statements may result in denial",
  "example": "01/15/1985",
  "legal_reference": "INA 241(b)(3)"
}
```

**Fields**:
- `inline`: Short hint next to field (e.g., `"(if any)"`, `"(if applicable)"`)
- `tooltip`: Hover tooltip
- `instructions`: Longer instructions above or below field
- `warning`: Legal warning or important note
- `example`: Example value to guide user
- `legal_reference`: Statute or regulation reference

**Example**:
```json
{
  "id": "b1_basis_asylum",
  "name": "I am seeking asylum based on",
  "type": "checkbox",
  "options": [...],
  "help": {
    "instructions": "Select all that apply. You must select at least one basis for your asylum claim.",
    "warning": "WARNING: Applicants who make frivolous applications for asylum will be permanently ineligible for any benefits under the Immigration and Nationality Act.",
    "legal_reference": "INA 208(d)(6)"
  }
}
```

---

### 11. Multi-Language Support

**label_translations** (on FieldOption). The **canonical key is the lowercase
spoken-language NAME** ("spanish", "chinese") -- settled by bd polyglot-pdf-2h9j:

```json
{
  "value": "single",
  "label": "Single",
  "label_translations": {
    "spanish": "Soltero",
    "chinese": "单身"
  }
}
```

- **Authoring**: the extraction pipeline bakes these for every supported spoken
  language (a post-pass in `scripts/authoring/extract_form.py`, skippable with
  `--no-translate-options`); `scripts/authoring/translate_option_labels.py`
  bakes/patches an existing kit standalone (idempotent; `--check` reports,
  `--force` retranslates after label renames). The hosted editor exposes both
  (extract checkbox + `POST /api/editor/kits/{id}/translate-options`).
- **Runtime**: kit translations take precedence -- the secretary
  (`backend/services/option_translation.py`) only translates labels the kit
  lacks. The runtime reader is tolerant for hand-authored kits: the plain name
  ("Spanish"/"spanish"), the short BCP-47 stem ("es") and the full code
  ("es-US") all resolve, case-insensitively. **Bare ISO-639-1 codes that differ
  from the BCP-47 stem do NOT resolve** -- Chinese is "cmn" (from cmn-CN), not
  "zh"; Tagalog is "fil" (from fil-PH), not "tl". Write lowercase names.
- **Supported languages**: the canonical list is
  `backend/utils/language_codes.py::SPOKEN_LANGUAGE_BCP47` (18 code-backed
  spoken languages, mirrored by `frontend/src/shared/languages.ts`
  SPOKEN_LANGUAGES). Never hardcode the list; when it grows, re-running the
  patch tool fills only the missing languages.

**spoken_name_translations** (on FormField, bd polyglot-pdf-tupu.1): the
field-level counterpart -- session-language translations of the field's
`spoken_name`, same canonical lowercase-name keys, baked by the SAME
authoring pass/CLI/editor route as the option labels (labels + spoken names
ride one batched translate call per language). All 3 kits (f1040, i-90, w7)
are fully baked for every code-backed language. Runtime delivery to the voice
model shipped in bd polyglot-pdf-tupu.2
(`backend/services/form_filling_service.py`: `_spoken_name_translations`,
`get_spoken_name_overrides`, threaded into `render_field_guidance` and the
greeting-hint substitution).

```json
{
  "id": "p1_line3a_familyname",
  "spoken_name": "current family name",
  "spoken_name_translations": {
    "spanish": "Apellido actual",
    "chinese": "当前姓氏"
  }
}
```

**name_translations** (on FormField) is documented-but-dormant: the model field
is commented out in `backend/models/form_models.py` and nothing populates or
reads it today.

---

### 12. Auto-Fill NA Logic

For expandable fields in repeating groups (e.g., spouse "other names"), when the user fills the first field with "NA", automatically fill all remaining similar fields with "NA".

**FormField setting**:
```json
{
  "id": "a2_spouse_othername",
  "name": "Other Names Used",
  "type": "text",
  "auto_fill_na": true
}
```

**Behavior**:
1. User fills first `other_names` field with "NA"
2. System auto-fills all remaining `other_names` fields in the same group with "NA"
3. User can override auto-filled values if needed

---

### 13. PDF Mapping

**pdf_field_name**: Original fillable PDF field name
```json
{
  "id": "a1_lastname",
  "pdf_field_name": "form1[0].#subform[0].Pt1Line1a_FamilyName[0]"
}
```

**pdf_position**: Coordinates in PDF
```json
{
  "pdf_position": {
    "page": 1,
    "x": 150.5,
    "y": 620.3,
    "width": 300.0,
    "height": 20.0
  }
}
```

**Purpose**: Maps schema fields back to original PDF for export, and drives the
schema editor's field overlay on the PDF preview.

**`page` is ONE-BASED.** The editor's PDF viewer matches pages `1..numPages` by
exact equality, so a field claiming page `0` draws nothing at all -- silently. The
AcroForm dump is 0-based, and the extraction pipeline converts it with an explicit
`+1`.

**Who owns this value.** On a fillable (AcroForm) PDF it is read DIRECTLY from the
PDF's own widget geometry and OVERWRITES anything an extraction model emitted --
the extraction contract tells the model not to emit `pdf_position` at all, the same
treatment `parts`/`sections`/`section_id` already get. A model transcribing
coordinates rounds them (469.2 -> 469) and its page base is non-deterministic:
that combination shipped a real bug where 48 of 54 W-7 fields landed on page 0 and
every text-field overlay vanished from the preview while only the choice fields
(whose rects came from the deterministic path) drew (bd polyglot-pdf-icyi).

Model-supplied coordinates survive ONLY for a field whose widget name resolves to
nothing -- the route a future non-AcroForm/scanned PDF would need. On that path a
0-based page is treated as an ordinal counting-scheme difference and shifted up by
one rather than discarded. A field with neither a resolvable widget nor a usable
model rect carries NO `pdf_position` key at all, rather than a zero-size
placeholder that would read as a real position downstream.

---

### 14. Complete Example (Part A.I of I-589, First 3 Fields)

```json
{
  "source": "pdf",
  "form_metadata": {
    "title": "Application for Asylum and for Withholding of Removal",
    "form_number": "I-589",
    "version": "1.0",
    "edition_date": "2025-01-20",
    "expiration_date": "2027-09-30",
    "omb_number": "1615-0067",
    "page_count": 12,
    "agency": "U.S. Citizenship and Immigration Services",
    "language": "en"
  },
  "parts": [
    {
      "id": "part_a",
      "label": "Part A: Information About Applicant",
      "order": 1,
      "section_ids": ["part_a_i", "part_a_ii", "part_a_iii"]
    }
  ],
  "sections": [
    {
      "id": "part_a_i",
      "label": "Part A.I: Information About You",
      "order": 1,
      "fields": ["a1_anumber", "a1_ssn", "a1_uscis_account"],
      "page_number": 1
    }
  ],
  "fields": [
    {
      "id": "a1_anumber",
      "name": "Alien Registration Number(s) (A-Number)",
      "spoken_name": "A number",
      "spoken_aliases": ["alien registration number", "registration number"],
      "type": "text",
      "section_id": "part_a_i",
      "validation": {
        "required": false,
        "pattern": "^A\\d{8,9}$",
        "custom_error": "A-Number must be 8-9 digits starting with A",
        "format_preset": "a_number"
      },
      "help": {
        "inline": "(if any)",
        "example": "A123456789"
      },
      "placeholder": "A123456789",
      "pdf_field_name": "form1[0].#subform[0].Pt1Line1_AlienNumber[0]",
      "pdf_position": {
        "page": 1,
        "x": 50.0,
        "y": 720.0,
        "width": 200.0,
        "height": 20.0
      }
    },
    {
      "id": "a1_ssn",
      "name": "U.S. Social Security Number",
      "spoken_name": "social security number",
      "spoken_aliases": ["SSN"],
      "type": "text",
      "section_id": "part_a_i",
      "validation": {
        "required": false,
        "format_preset": "ssn"
      },
      "help": {
        "inline": "(if any)",
        "example": "123-45-6789"
      },
      "placeholder": "123-45-6789",
      "pdf_field_name": "form1[0].#subform[0].Pt1Line2_SSN[0]"
    },
    {
      "id": "a1_uscis_account",
      "name": "USCIS Online Account Number",
      "spoken_name": "USCIS account number",
      "type": "text",
      "section_id": "part_a_i",
      "validation": {
        "required": false
      },
      "help": {
        "inline": "(if any)"
      },
      "pdf_field_name": "form1[0].#subform[0].Pt1Line3_OnlineAccountNumber[0]"
    }
  ]
}
```

---

### 15. Schema v2 (`schema_version`, `checkbox_group`, `require_if`, `ConditionGroup`)

**`schema_version`** (root, `FormSchema`): `None`/`"1"` = legacy, `"2"` = strict
v2. As of bd polyglot-pdf-h76m.16, the strict v2 rules are enforced on EVERY
schema regardless of the stamped version -- v2 is the only shape the model
accepts; all stored kits (f1040, i-90, w7) are migrated to v2. Only the exact
string `"2"` is treated as opted-in for tooling gates (e.g. the mark-complete
check, bd polyglot-pdf-t96a); other stamps take the legacy read path but are
still subject to the v2 structural rules.

**`checkbox_group`** (FieldType): a v2 standalone field type for modeling a
"select all that apply" group as ONE field (rather than the legacy
`allow_multiple` checkbox convention). A `checkbox_group` field carries no
field-level `pdf_field_name`; each `FieldOption` supplies its own
`pdf_field_name` + `pdf_on_value` (see below), since each checkbox is an
independent PDF widget.

**`FieldOption.pdf_on_value`**: the PDF "on" state name that selects this
option. For true-AcroForm radio groups, the kids share ONE field name (the
FIELD's `pdf_field_name`) and differ only by this state; for per-widget
`checkbox_group` options, it is the widget's own on-value (paired with the
option's own `pdf_field_name`).

**`require_if`** (FormField): a sibling of `show_if`/`hide_if` -- marks a
field conditionally REQUIRED (rather than conditionally visible) based on
another field's value. Same condition shape as `show_if`.

**`ConditionGroup`** (composite condition, bd polyglot-pdf-h76m.3): one level
of boolean structure over atomic conditions, for `show_if`/`require_if`
fields that need more than a single equality check:

```json
{
  "all_of": [
    {"field": "a1_marital_status", "operator": "equals", "value": "married"}
  ],
  "any_of": [
    {"field": "a2_spouse_in_us", "operator": "equals", "value": "yes"}
  ],
  "none_of": [
    {"field": "a2_spouse_deceased", "operator": "is_checked"}
  ]
}
```

Visible/required when ALL of `all_of` hold, AND at least one of `any_of`
holds (if present), AND none of `none_of` hold. Buckets are flat -- a nested
group is a validation error; at least one non-empty bucket is required. This
sits alongside the legacy single-condition shape (a plain
`{"field", "operator", "value"}` object) as an alternative for `show_if` /
`hide_if` / `require_if`, not a replacement for it.

---

## Schema Validation

The FormSchema model includes validation methods:

### `validate_field_value(field_id, value)`
Validates a single field value against its validation rules.

**Returns**: `(is_valid: bool, error_message: Optional[str])`

### `validate_all_references()`
Validates all field/section/part ID references are correct.

**Returns**: `{"errors": List[str], "warnings": List[str]}`

**Checks**:
- Section field references point to existing fields
- Part section references point to existing sections
- Conditional `show_if` references point to existing fields
- Supplement field references point to existing fields

---

## Best Practices

1. **Field IDs**: Use consistent naming (e.g., `part_section_fieldname`)
2. **Spoken Names**: Keep simple and natural for voice interaction
3. **Validation**: Always validate required fields and format constraints
4. **Help Text**: Provide inline hints for optional fields (`"(if any)"`)
5. **Conditionals**: Test conditional logic thoroughly
6. **Multi-Entry**: Set realistic `initial_rows` based on common use cases
7. **Supplements**: Map overflow explicitly to `supplement_a` (the only modeled supplement type)
8. **PDF Mapping**: Preserve original PDF field names for export accuracy
9. **Multi-Language**: Add translations for the app's supported spoken languages (see `backend/utils/language_codes.py::SPOKEN_LANGUAGE_BCP47` for the current, growing list)
10. **Legal Warnings**: Include warnings for legally significant fields

---

## Future Enhancements

- **Complex Conditionals**: AND/OR combinations
- **Cross-Field Validation**: Validate relationships between fields
- **Field Dependencies**: Auto-populate based on other fields
- **Dynamic Options**: Options loaded from external source
- **File Upload Fields**: Support for document attachments
- **Calculated Fields**: Auto-calculate based on formula

---

**Document Owner**: Development Team
**Status**: Living reference

*Last updated: 2026-08-05 (docs audit bd polyglot-pdf-2zk3: fixed supplement_b/omn_number typos, added schema v2 (checkbox_group/schema_version/require_if/ConditionGroup) + uscis_account format_preset, corrected kit count and tupu.2 status, dropped unsupported-language list).*
