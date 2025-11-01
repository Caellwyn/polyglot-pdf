# Pipeline Improvements for Universal Form Extraction

**Date:** October 31, 2025
**Purpose:** Fix the extraction pipeline to catch issues automatically for ALL forms
**Approach:** Enhance Gemini prompts + build reusable validation tools

---

## Problems We're Solving

### ❌ Current Issues (I-90 exposed these)
1. **Gemini doesn't identify "select only one" patterns** → Leaves checkboxes instead of radio
2. **Gemini identifies conditionals but doesn't flag read-only bits** → Fields stay locked
3. **Round-trip tester doesn't handle all field types** → Can't validate dropdowns/dates
4. **Validation rules in schema but not enforced** → Can't verify they work
5. **No automated way to create "unlocked" PDFs** → Can't test conditional fields

### ✅ What We Need (Reusable for ALL forms)
1. Enhanced Gemini prompt that identifies mutually exclusive patterns
2. Gemini flags which fields need read-only bits flipped
3. Generic PDF field flag mutator (works from schema)
4. Universal round-trip tester (handles all field types)
5. Validation enforcement in testing

---

## Pipeline Enhancement Strategy

### Phase 1: Enhanced Gemini Prompts
**File:** `gemini_schema_validator.py` (enhance existing prompt)

#### Add to Gemini's Task:

**1. Detect Mutually Exclusive Patterns**
```
**Field Type Detection - CRITICAL:**

Look for these patterns in tooltips/labels:
- "select only one box"
- "select one box"
- "mark only one"
- "check only one"
- Multiple checkboxes for Yes/No questions

If found → field_type_correction: "radio" (not checkbox)

**Why:** Checkboxes allow multiple selections. Radio buttons are mutually exclusive.
Voice AI needs to know user can only select ONE option.
```

**2. Identify Read-Only Bit Manipulation Needs**
```
**Conditional Field Unlocking:**

For fields with conditional_logic, identify:
1. **trigger_field**: Which field controls visibility (e.g., "P1 Q4")
2. **trigger_value**: What value unlocks it (e.g., "yes", "option A")
3. **dependent_fields**: Which fields unlock (e.g., ["P1 Q5a", "P1 Q5b", "P1 Q5c"])
4. **unlock_method**: How to unlock
   - "flip_readonly_bit" - Clear bit 0 in field_flags
   - "javascript" - Requires PDF JavaScript (not supported)
   - "voice_ai_only" - Only enforce in voice UI, not PDF

Output format:
{
  "field_id": "p1_q5a",
  "conditional_logic": {
    "trigger_field": "p1_q4",
    "trigger_value": "yes",
    "unlock_method": "flip_readonly_bit",
    "pdf_field_flag_change": {
      "bit": 0,
      "current_value": 1,
      "required_value": 0
    }
  }
}
```

**3. Validate Field Options for Dropdowns**
```
**Dropdown/Select Fields:**

When you identify field_type_correction: "select", provide the options:

Example - State dropdown:
{
  "field_id": "p1_line6e_state",
  "field_type_correction": "select",
  "options": [
    {"value": "AL", "label": "Alabama"},
    {"value": "AK", "label": "Alaska"},
    ... (all 50 states)
  ]
}

Example - Height feet:
{
  "field_id": "p3_line8_heightfeet",
  "field_type_correction": "select",
  "options": [
    {"value": "0", "label": "0 feet"},
    {"value": "1", "label": "1 foot"},
    ...
    {"value": "7", "label": "7 feet"}
  ]
}
```

---

### Phase 2: Generic PDF Field Flag Mutator
**New File:** `pdf_field_flag_mutator.py`

**Purpose:** Create "unlocked" PDFs based on schema conditional logic (works for ANY form)

```python
#!/usr/bin/env python3
"""
PDF Field Flag Mutator - Unlocks conditional fields based on schema.

Takes schema with conditional_logic and modifies PDF field flags to create
testable version where conditional fields are unlocked.

Reusable across ALL forms.
"""

import fitz
import json
from typing import Dict, List


def parse_schema_conditionals(schema: Dict) -> List[Dict]:
    """
    Extract all conditional field unlocking instructions from schema.

    Returns list of:
    {
        "field_pdf_name": "P1_Line5a_FirstName[0]",
        "unlock_method": "flip_readonly_bit",
        "field_flag_changes": {
            "bit": 0,
            "from": 1,
            "to": 0
        }
    }
    """
    unlocks = []

    for field in schema.get('fields', []):
        conditional = field.get('conditional_logic', {})

        if isinstance(conditional, dict):
            unlock_method = conditional.get('unlock_method')
            pdf_field = field.get('pdf_field_name')
            flag_change = conditional.get('pdf_field_flag_change')

            if unlock_method == 'flip_readonly_bit' and pdf_field and flag_change:
                unlocks.append({
                    'field_pdf_name': pdf_field,
                    'unlock_method': unlock_method,
                    'field_flag_changes': flag_change
                })

    return unlocks


def unlock_field(widget, bit: int, value: int):
    """
    Modify widget field_flags bit.

    Args:
        widget: PyMuPDF widget
        bit: Bit position (0-31)
        value: Target value (0 or 1)
    """
    if value == 0:
        # Clear bit
        widget.field_flags &= ~(1 << bit)
    else:
        # Set bit
        widget.field_flags |= (1 << bit)

    widget.update()


def create_unlocked_pdf(
    source_pdf: str,
    schema_file: str,
    output_pdf: str
) -> Dict:
    """
    Create unlocked version of PDF for testing conditional fields.

    Args:
        source_pdf: Original PDF path
        schema_file: Schema JSON with conditional_logic
        output_pdf: Path for unlocked PDF

    Returns:
        Statistics dict
    """
    # Load schema
    with open(schema_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    # Parse conditional unlocks
    unlocks = parse_schema_conditionals(schema)

    # Open PDF
    doc = fitz.open(source_pdf)

    stats = {
        'fields_unlocked': 0,
        'fields_not_found': 0,
        'total_unlock_requests': len(unlocks)
    }

    # Apply unlocks
    for unlock in unlocks:
        field_name = unlock['field_pdf_name']
        flag_change = unlock['field_flag_changes']

        found = False
        for page in doc:
            for widget in page.widgets():
                if widget.field_name == field_name:
                    # Unlock field
                    unlock_field(
                        widget,
                        bit=flag_change['bit'],
                        value=flag_change['to']
                    )
                    stats['fields_unlocked'] += 1
                    found = True
                    break
            if found:
                break

        if not found:
            stats['fields_not_found'] += 1

    # Save
    doc.save(output_pdf, garbage=4, deflate=True)
    doc.close()

    return stats


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python pdf_field_flag_mutator.py <source.pdf> <schema.json> <output_unlocked.pdf>")
        sys.exit(1)

    source = sys.argv[1]
    schema = sys.argv[2]
    output = sys.argv[3]

    stats = create_unlocked_pdf(source, schema, output)

    print(f"Unlocked PDF created: {output}")
    print(f"  Fields unlocked: {stats['fields_unlocked']}")
    print(f"  Fields not found: {stats['fields_not_found']}")
    print(f"  Total requests: {stats['total_unlock_requests']}")
```

---

### Phase 3: Universal Round-Trip Tester
**File:** `round_trip_tester.py` (enhance existing)

**Make it handle ALL field types generically:**

```python
def generate_test_value_from_schema(field: dict) -> Any:
    """
    Generate appropriate test value based on field metadata.
    Works for ANY form automatically.
    """
    field_type = field.get('type')
    validation = field.get('validation', {})

    # Use validation rules to generate correct test data
    if validation:
        val_type = validation.get('type')

        if val_type == 'phone_number':
            return "(555) 123-4567"
        elif val_type == 'zip_code':
            return "90210"
        elif val_type == 'postal_code':
            return "ABC123"
        elif val_type == 'ssn':
            return "123456789"
        elif val_type == 'a_number':
            return "123456789"
        elif val_type == 'receipt_number':
            return "123456789012"  # Exactly 12
        elif val_type == 'date':
            return "01/01/2000"

    # Handle by field type
    if field_type == 'date':
        return "01/01/2000"

    elif field_type == 'select':
        # Use first option from schema
        options = field.get('options', [])
        if options:
            return options[0].get('value')
        return "OPTION1"

    elif field_type == 'text':
        # Respect max_length
        max_len = field.get('max_length')
        if max_len:
            return '1' * max_len  # Fill to max for COMB fields
        return f"Test {field.get('name', 'Value')[:20]}"

    elif field_type == 'textarea':
        return "Test multiline\\nLine 2\\nLine 3"

    elif field_type in ['checkbox', 'radio']:
        return True  # Check/select first option

    return None


def fill_field_by_type(widget, value, field_type: str):
    """
    Fill widget based on field type.
    Handles all PyMuPDF widget types.
    """
    if widget.field_type == 1:  # Text
        widget.field_value = str(value)

    elif widget.field_type == 2:  # Checkbox
        widget.field_value = bool(value)

    elif widget.field_type == 3:  # Radio
        widget.field_value = bool(value)

    elif widget.field_type == 4:  # Select/Dropdown
        # Set dropdown value
        widget.field_value = str(value)

    elif widget.field_type == 6:  # Listbox
        widget.field_value = str(value)

    elif widget.field_type == 7:  # Signature (usually text)
        widget.field_value = str(value)

    widget.update()
```

---

### Phase 4: Validation Enforcement
**New File:** `schema_validator_enforcement.py`

**Purpose:** Verify test data matches validation rules (reusable)

```python
import re
from typing import Dict, Any, List, Tuple


def validate_field_value(value: Any, validation: Dict) -> Tuple[bool, str]:
    """
    Check if value matches validation rules.

    Returns:
        (is_valid, error_message)
    """
    if not validation:
        return (True, "")

    pattern = validation.get('pattern')
    val_type = validation.get('type')

    # Convert to string for pattern matching
    str_value = str(value)

    # Check regex pattern
    if pattern:
        if not re.match(pattern, str_value):
            return (False, f"Value '{str_value}' doesn't match pattern '{pattern}'")

    # Type-specific checks
    if val_type == 'phone_number':
        if len(str_value.replace('(', '').replace(')', '').replace('-', '').replace(' ', '')) != 10:
            return (False, f"Phone number must be 10 digits, got '{str_value}'")

    elif val_type == 'zip_code':
        if len(str_value) != 5 or not str_value.isdigit():
            return (False, f"ZIP code must be 5 digits, got '{str_value}'")

    elif val_type == 'ssn':
        cleaned = str_value.replace('-', '')
        if len(cleaned) != 9 or not cleaned.isdigit():
            return (False, f"SSN must be 9 digits, got '{str_value}'")

    return (True, "")


def validate_schema_data(schema: Dict, test_data: Dict) -> Dict:
    """
    Validate all test data against schema rules.

    Returns summary of validation results.
    """
    results = {
        'total_validated': 0,
        'passed': 0,
        'failed': 0,
        'failures': []
    }

    for field in schema.get('fields', []):
        field_id = field.get('id')
        pdf_field = field.get('pdf_field_name')
        validation = field.get('validation')

        if not validation:
            continue

        # Get test value
        value = test_data.get(pdf_field) or test_data.get(field_id)
        if value is None:
            continue

        results['total_validated'] += 1

        # Validate
        is_valid, error = validate_field_value(value, validation)

        if is_valid:
            results['passed'] += 1
        else:
            results['failed'] += 1
            results['failures'].append({
                'field_id': field_id,
                'pdf_field': pdf_field,
                'value': value,
                'error': error
            })

    return results
```

---

### Phase 5: Pattern Detection in Pipeline
**File:** `widget_inventory.py` (enhance)

**Add automatic pattern detection during extraction:**

```python
def detect_field_patterns(widget) -> Dict[str, Any]:
    """
    Detect common patterns in widget to suggest field type/behavior.

    Returns metadata about patterns found.
    """
    tooltip = (widget.field_label or "").lower()
    field_name = (widget.field_name or "").lower()

    patterns = {
        'mutually_exclusive': False,
        'suggested_type': None,
        'conditional_hint': None,
    }

    # Detect "select only one" patterns
    exclusive_patterns = [
        'select only one',
        'select one box',
        'mark only one',
        'check only one',
    ]

    if any(p in tooltip for p in exclusive_patterns):
        patterns['mutually_exclusive'] = True
        patterns['suggested_type'] = 'radio'

    # Detect conditional language
    conditional_patterns = [
        'if you answered',
        'if you selected',
        'skip if',
        'complete only if',
    ]

    if any(p in tooltip for p in conditional_patterns):
        patterns['conditional_hint'] = 'has_conditional_logic'

    return patterns


# Add to widget_data in extract_widget_inventory():
widget_data['pattern_detection'] = detect_field_patterns(widget)
```

---

## Updated Pipeline Flow

### Current Pipeline:
1. Widget Inventory → Schema Builder → Schema Fixer → Gemini Enhancement

### Enhanced Pipeline:
1. **Widget Inventory** (+ pattern detection)
2. **Schema Builder** (uses pattern hints)
3. **Gemini Validator** (enhanced prompt with specific instructions)
4. **Schema Fixer** (applies Gemini corrections)
5. **PDF Field Flag Mutator** (creates unlocked PDF)
6. **Round-Trip Tester** (uses unlocked PDF, validates all types)
7. **Validation Enforcement** (reports validation failures)

---

## Gemini Prompt Enhancement Summary

Add these sections to `gemini_schema_validator.py` prompt:

### 1. Mutually Exclusive Detection
```
CRITICAL - Checkbox vs Radio:
- Search tooltips for: "select only one", "select one box", "mark only one"
- Yes/No questions → ALWAYS radio
- Multiple checkboxes for same question → Check if mutually exclusive
```

### 2. Conditional Field Unlocking
```
For fields with conditional_logic, provide:
{
  "conditional_logic": {
    "trigger_field": "p1_q4",
    "trigger_value": "yes",
    "dependent_fields": ["p1_q5a", "p1_q5b", "p1_q5c"],
    "unlock_method": "flip_readonly_bit",
    "pdf_field_flag_change": {
      "bit": 0,
      "current_value": 1,
      "required_value": 0
    }
  }
}
```

### 3. Dropdown Options
```
For select/dropdown fields, provide complete options list:
- States: All 50 US states
- Heights: Appropriate ranges
- Yes/No: ["Yes", "No"]
```

---

## Success Metrics (For ALL Forms)

After pipeline improvements, ANY new form should achieve:

1. ✅ **95%+ automatic field type detection** (checkbox vs radio, text vs date vs select)
2. ✅ **100% conditional logic identification** (from instruction PDF)
3. ✅ **100% validation rule detection** (phone, zip, date formats)
4. ✅ **Automatic unlocked PDF creation** (for testing conditionals)
5. ✅ **100% round-trip success** (all field types handled)
6. ✅ **Validation enforcement** (test data matches rules)

---

## Next Steps

1. **Enhance Gemini prompt** (highest impact)
2. **Build PDF field flag mutator** (enables conditional testing)
3. **Update round-trip tester** (handle all field types)
4. **Add validation enforcement** (verify rules work)
5. **Test on I-90** (validate improvements)
6. **Extract new form** (prove pipeline works universally)

**Goal:** Next form (I-485, I-765, N-400) should extract with minimal manual fixes.
