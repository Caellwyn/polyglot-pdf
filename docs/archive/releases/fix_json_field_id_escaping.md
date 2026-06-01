# Fix: Field ID JSON Escaping Issue

## Problem
When using `json.dumps()` to format the form schema in the system instruction, field IDs with special characters (like `reason[]` or `items[0][name]`) were getting quoted. This confused Gemini, causing it to occasionally return field IDs with escaped quotes like `"\"reason[]\""` instead of the correct `reason[]`.

## Root Cause
The system instruction was using `json.dumps(fields_info, indent=2)` to format field information. JSON serialization adds quotes around all string values:

```json
{
  "id": "reason[]",
  "name": "Reason",
  ...
}
```

When Gemini saw field IDs in this format, it sometimes returned them with the quotes escaped.

## Solution
Changed from JSON format to pipe-separated text format for field information:

**Before (JSON):**
```json
[
  {
    "order": 1,
    "id": "reason[]",
    "name": "Reason",
    "type": "select",
    "required": false,
    "filled": false,
    "allowed_values": ["Option A", "Option B"]
  }
]
```

**After (Pipe-separated):**
```
Field 1: | id=reason[] | name=Reason | type=select | required=False | filled=False | allowed_values=[Option A, Option B]
```

## Benefits
1. **No quote escaping**: Field IDs appear as bare values without JSON quotes
2. **Clearer to AI**: More natural text format, easier for Gemini to parse
3. **More compact**: Slightly reduces token usage
4. **Better for long option lists**: Automatically truncates to show first 3 options + count for lists longer than 5

## Files Changed

### `backend/services/ai_context.py`
- Modified `build_form_context()` to use pipe-separated format instead of JSON
- Added smart truncation for option lists (show all if ≤5, else show first 3 + count)

### `backend/config.py`
- Updated `SYSTEM_INSTRUCTION` template comment to clarify the format
- Improved instruction clarity: "use the 'id' field exactly as shown"

### `backend/tests/unit/test_ai_context.py`
- Replaced outdated tests for removed `build_initial_message()` function
- Added comprehensive tests for `build_form_context()`:
  - Basic schema formatting
  - Field IDs with special characters (brackets)
  - Current values handling
  - Option list truncation (many vs few options)
  - No JSON escaped quotes validation

## Validation
All new tests pass:
```
backend/tests/unit/test_ai_context.py::test_build_form_context_basic PASSED
backend/tests/unit/test_ai_context.py::test_build_form_context_with_special_field_ids PASSED
backend/tests/unit/test_ai_context.py::test_build_form_context_with_current_values PASSED
backend/tests/unit/test_ai_context.py::test_build_form_context_with_many_options PASSED
backend/tests/unit/test_ai_context.py::test_build_form_context_with_few_options PASSED
```

## Example Output
For a schema with field IDs like `reason[]` and `items[0][name]`:
```
FORM FIELDS:
Field 1: | id=first_name | name=First Name | type=text | required=True | filled=True | current_value=John
Field 2: | id=reason[] | name=Reason | type=select | required=False | filled=False | allowed_values=[Option A, Option B, Option C]
Field 3: | id=items[0][name] | name=Item Name | type=text | required=False | filled=False
```

Gemini now sees `id=reason[]` without quotes and correctly returns `reason[]` in tool calls.
