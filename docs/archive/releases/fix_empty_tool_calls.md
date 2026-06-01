# Fix: Gemini Sending Empty Tool Call Updates

## Problem
After fixing the JSON escaping issue, Gemini started sending tool calls with empty `updates` arguments, indicating it was confused about which field IDs to use.

## Root Cause
The initial fix changed from JSON format to pipe-separated format using `id=fieldName`, but this was still potentially ambiguous. Gemini couldn't clearly distinguish between:
- What to say to the user (the field name)
- What to use in tool calls (the field ID)

The format `id=reason[]` might have been parsed by Gemini as an assignment rather than a label-value pair.

## Solution
Changed to an even clearer labeled format with explicit prefixes:

**Before (ambiguous):**
```
Field 1: | id=firstName | name=First Name | type=text | required=True | filled=True
```

**After (crystal clear):**
```
Field 1 | ID: firstName | Name: First Name | Type: text | Required: True | Filled: True
```

## Key Improvements

### 1. Field Format Changes
- Changed `id=` to `ID:` (label-value pair instead of assignment)
- Changed `name=` to `Name:`
- Capitalized labels for better visual distinction
- Changed `allowed_values` to `Options` (more natural)
- Changed `current_value` to `Current` (shorter, clearer)

### 2. Enhanced System Instruction
Added explicit sections:

**FIELD ID USAGE:**
- Clear distinction: speak "Name", use "ID" in tools
- Multiple examples showing bracket handling
- Explicit instruction to include brackets

**TOOL CALL FORMAT:**
- Exact syntax template
- Concrete example with bracket field IDs

**CRITICAL RULES:**
- Added: "ALWAYS call update_form_fields when user provides a value"
- Changed `filled=true` to `Filled: True` to match new format

### 3. Improved Tool Declaration
Updated `update_form_fields` description:
- More explicit about using field "ID" from schema
- Better examples in parameter description
- Clearer about when to batch fields

## Files Changed

### `backend/services/ai_context.py`
- Changed field format from `id=value` to `ID: value`
- Updated all field labels to use capitalized prefix format
- Comments improved to explain clarity goal

### `backend/config.py`
- Completely restructured `SYSTEM_INSTRUCTION` with clear sections
- Added FIELD ID USAGE section with examples
- Added TOOL CALL FORMAT section with syntax template
- Updated tool declaration for `update_form_fields`
- Made all instructions more explicit and example-driven

### `backend/tests/unit/test_ai_context.py`
- Updated all assertions to match new format (`ID:` instead of `id=`)
- Updated option format (`Options:` instead of `allowed_values=`)
- Updated filled status (`Filled:` instead of `filled=`)

## Example Output

### Complete Field Examples
```
Field 1 | ID: firstName | Name: First Name | Type: text | Required: True | Filled: True | Current: Jane
Field 2 | ID: lastName | Name: Last Name | Type: text | Required: True | Filled: False
Field 3 | ID: reason[] | Name: Reason for Visit | Type: select | Required: True | Filled: False | Options: [Annual Checkup, Illness, Injury, Follow-up]
Field 4 | ID: medications[0][name] | Name: Medication Name | Type: text | Required: False | Filled: False
```

### What Gemini Learns
1. **Speaking to user**: Use "Reason for Visit" (the Name field)
2. **Tool calls**: Use `reason[]` (the ID field, brackets included)
3. **Format**: `update_form_fields({'updates': {'reason[]': 'Annual Checkup'}})`

## Validation

All tests pass:
```
✓ test_build_form_context_basic
✓ test_build_form_context_with_special_field_ids  
✓ test_build_form_context_with_current_values
✓ test_build_form_context_with_many_options
✓ test_build_form_context_with_few_options
```

## Benefits

1. **Crystal clear distinction** between field ID and field name
2. **Visual hierarchy** - capitalized labels stand out
3. **Explicit examples** show Gemini exactly how to handle brackets
4. **Natural language** - "Options" instead of "allowed_values"
5. **Concrete templates** - exact tool call syntax shown
6. **Reduced ambiguity** - label-value pairs instead of assignments

## Expected Result

Gemini should now:
- ✅ Correctly use field IDs in tool calls (including brackets)
- ✅ Never send empty `updates` arguments
- ✅ Speak natural field names to users
- ✅ Follow the explicit tool call format shown in examples
