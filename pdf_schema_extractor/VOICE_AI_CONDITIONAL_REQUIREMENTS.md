# Voice AI Conditional Logic Requirements

**Date:** October 31, 2025
**Purpose:** Ensure schema has all pieces needed for runtime conditional logic in voice AI + PDF viewer

---

## Use Cases

### 1. Voice AI Flow Control
- **Need**: Know which fields to ask based on previous answers
- **Example**: User says "No" to Q4 (name changed) → Skip Q5a-c

### 2. Live PDF Unlocking (JavaScript/PDF.js)
- **Need**: Dynamically unlock read-only fields when conditions met
- **Example**: User checks "Yes" for Q4 → Unlock and enable Q5a-c fields in PDF viewer

### 3. Bidirectional Navigation
- **Need**: Both directions of conditional relationships
- **Trigger → Dependent**: "If THIS is selected, show THESE"
- **Dependent → Trigger**: "This field shows when THAT is selected"

### 4. Conditional Validation
- **Need**: Fields required only when visible
- **Example**: Q5a required ONLY IF Q4 = "Yes"

---

## Current Schema Structure (I-90 v5)

### What We Have ✅

**5 Structured Conditionals:**
```json
{
  "id": "p1_line5a_familyname",
  "conditional_logic": {
    "trigger_field": "p1_checkbox4",
    "trigger_value": "yes",
    "dependent_fields": ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
    "unlock_method": "flip_readonly_bit",
    "description": "If name has legally changed, unlock fields...",
    "pdf_field_flag_change": {
      "bit": 0,
      "current_value": 1,
      "required_value": 0
    }
  }
}
```

**26 String-Format Conditionals:**
```json
{
  "id": "p2_line2a_street",
  "conditional_logic": "NEEDS_GEMINI: Visible only if user lost card..."
}
```

### What's Missing ❌

#### 1. Bidirectional Indexing
**Problem**: Trigger fields don't know what they control

**Current**: Dependent fields (Q5a-c) know their trigger (Q4)
**Missing**: Trigger field (Q4) doesn't list dependents

**Need**:
```json
{
  "id": "p1_checkbox4",
  "name": "My name has legally changed since issuance of my card",
  "type": "radio",
  "controls_fields": {
    "when_value": "yes",
    "shows_fields": ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
    "hides_fields": []
  }
}
```

#### 2. Machine-Readable Condition Expressions
**Problem**: Can't evaluate conditions programmatically

**Current**: String descriptions or simple trigger_value
**Missing**: Structured condition trees for complex logic

**Need**:
```json
{
  "condition": {
    "type": "equals",
    "field": "p1_checkbox4",
    "value": true
  },
  "actions": {
    "unlock": ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
    "set_required": ["p1_line5a_familyname"]
  }
}
```

**For complex conditions (AND/OR)**:
```json
{
  "condition": {
    "type": "or",
    "conditions": [
      {
        "type": "and",
        "conditions": [
          {"type": "equals", "field": "p2_q1", "value": "lost"},
          {"type": "not_empty", "field": "p2_q2"}
        ]
      },
      {
        "type": "equals",
        "field": "p2_q1",
        "value": "stolen"
      }
    ]
  }
}
```

#### 3. Client-Side Unlock Instructions
**Problem**: pdf_field_flag_change is Python-specific

**Current**: Bit manipulation for PyMuPDF (Python)
**Missing**: JavaScript-compatible instructions for PDF.js

**Need**:
```json
{
  "unlock_instructions": {
    "backend": {
      "method": "flip_readonly_bit",
      "bit": 0,
      "value": 0
    },
    "frontend": {
      "method": "set_field_flag",
      "flag_name": "readOnly",
      "value": false
    }
  }
}
```

#### 4. Conditional Validation Rules
**Problem**: Don't know if field is required conditionally

**Current**: required: true/false (static)
**Missing**: Conditional required

**Need**:
```json
{
  "required": false,
  "required_if": {
    "field": "p1_checkbox4",
    "value": true
  }
}
```

#### 5. All Conditionals Structured
**Problem**: 26/31 conditionals still in string format

**Current**: "NEEDS_GEMINI: If user lost card..."
**Need**: All 31 converted to structured format

---

## Proposed Schema Enhancements

### Enhancement 1: Add Bidirectional Index
**New top-level schema property:**
```json
{
  "conditional_index": {
    "triggers": {
      "p1_checkbox4": {
        "when": {"value": "yes"},
        "affects": ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
        "action": "unlock"
      }
    },
    "dependents": {
      "p1_line5a_familyname": {
        "triggered_by": "p1_checkbox4",
        "requires": {"value": "yes"}
      }
    }
  }
}
```

### Enhancement 2: Structured Condition Expressions
**Add to conditional_logic:**
```json
{
  "conditional_logic": {
    "trigger_field": "p1_checkbox4",
    "condition": {
      "type": "equals",
      "field": "p1_checkbox4",
      "value": true
    },
    "actions": {
      "unlock": ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
      "set_required": ["p1_line5a_familyname"],
      "set_visible": ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"]
    },
    "unlock_method": "flip_readonly_bit",
    "unlock_instructions": {
      "python": {"bit": 0, "value": 0},
      "javascript": {"property": "readOnly", "value": false}
    }
  }
}
```

### Enhancement 3: Voice AI Metadata
**Add to each field:**
```json
{
  "voice_ai": {
    "skip_if": {
      "field": "p1_checkbox4",
      "value": false
    },
    "ask_order": 25,
    "prompt_template": "What is your family name as it appears on your green card?"
  }
}
```

---

## Implementation Plan

### Phase 1: Convert String Conditionals to Structured (CRITICAL)
**Tool**: `conditional_logic_parser.py` (NEW)

Parse the 26 string-format conditionals into structured format:
- Extract trigger_field from description
- Identify trigger_value
- List dependent_fields
- Determine unlock_method
- Generate condition expressions

### Phase 2: Build Bidirectional Index (CRITICAL)
**Tool**: `build_conditional_index.py` (NEW)

Scan all structured conditionals and create:
- `conditional_index.triggers` - Map trigger fields to dependents
- `conditional_index.dependents` - Map dependent fields to triggers
- Add to top-level schema

### Phase 3: Add Client-Side Unlock Instructions
**Tool**: Enhance `gemini_schema_validator.py`

Add JavaScript-compatible unlock instructions:
- Convert bit manipulation to property sets
- Add PDF.js compatible field update methods

### Phase 4: Runtime Condition Evaluator (JavaScript)
**Tool**: `conditional_evaluator.js` (NEW - Frontend)

JavaScript module that:
- Takes schema + current form state
- Evaluates condition expressions
- Returns list of fields to show/hide/unlock
- Validates conditionally required fields

### Phase 5: Voice AI Schema Transformer
**Tool**: `voice_ai_schema_transformer.py` (NEW)

Prepare schema for voice AI chunking:
- Flatten conditional relationships
- Add skip_if metadata
- Optimize for streaming

---

## Success Criteria

After enhancements, the schema should support:

1. ✅ **Voice AI can determine which fields to ask** - Based on previous answers
2. ✅ **JavaScript can unlock PDF fields at runtime** - When conditions met
3. ✅ **Bidirectional conditional navigation** - Both trigger → dependent and dependent → trigger
4. ✅ **Complex conditional expressions** - AND/OR/NOT logic
5. ✅ **Conditional validation** - Fields required only when visible
6. ✅ **Zero string-format conditionals** - All structured and machine-readable

---

## Example: Complete Conditional Field

```json
{
  "id": "p1_line5a_familyname",
  "name": "Family Name (Last Name)",
  "type": "text",
  "read_only": true,
  "required": false,
  "required_if": {
    "field": "p1_checkbox4",
    "value": true
  },
  "conditional_logic": {
    "trigger_field": "p1_checkbox4",
    "condition": {
      "type": "equals",
      "field": "p1_checkbox4",
      "value": true
    },
    "actions": {
      "unlock": ["p1_line5a_familyname"],
      "set_required": true,
      "set_visible": true
    },
    "unlock_method": "flip_readonly_bit",
    "unlock_instructions": {
      "python": {
        "field_flags_bit": 0,
        "target_value": 0
      },
      "javascript": {
        "property": "readOnly",
        "value": false
      }
    },
    "description": "If name has legally changed, unlock fields to provide name as it appears on current permanent resident card."
  },
  "voice_ai": {
    "skip_if": {
      "field": "p1_checkbox4",
      "value": false
    },
    "prompt_template": "Since your name has legally changed, what is your family name as it appears on your current green card?"
  }
}
```

And trigger field:
```json
{
  "id": "p1_checkbox4",
  "name": "My name has legally changed since issuance of my card",
  "type": "radio",
  "controls_fields": {
    "when_value": true,
    "shows": ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
    "unlocks": ["p1_line5a_familyname", "p1_line5b_givenname", "p1_line5c_middlename"],
    "makes_required": ["p1_line5a_familyname"]
  }
}
```

---

## Next Steps

1. **Build conditional_logic_parser.py** - Convert 26 string conditionals to structured
2. **Build build_conditional_index.py** - Create bidirectional index
3. **Enhance schema with full conditional metadata** - All fields
4. **Create conditional_evaluator.js** - Frontend runtime evaluation
5. **Create voice_ai_schema_transformer.py** - Optimize for voice AI
6. **Test with I-90** - Validate all conditionals work
7. **Document API** - For frontend developers using schema
