# Gemini Dependency Pipeline - Structured Outputs Approach

**Date:** October 31, 2025
**Status:** NEW APPROACH - Replaces form-specific heuristics

---

## Why This Approach?

### ❌ Previous Problem

**What we were doing:**
1. Gemini returned string-format conditionals like: `"Show only if 'Yes' is selected for requesting accommodations"`
2. We built `conditional_logic_parser.py` with I-90-specific heuristics to parse these
3. We built `dependency_finder.py` with form-specific pattern matching
4. **Result**: Tools won't generalize to other forms (I-485, I-765, N-400)

**Root cause:** Gemini didn't follow our structured format instructions.

### ✅ New Solution

**Force Gemini to return EXACTLY the structure we need:**
- Use Gemini's `responseSchema` feature (structured outputs)
- Define JSON schema matching our `FormField` model
- Gemini CANNOT return anything else - it's forced by the API
- **Result**: 100% structured, form-agnostic, bidirectional dependencies

---

## How It Works

### Step 1: Define Response Schema

We tell Gemini API exactly what JSON structure to return:

```python
response_schema = {
    "type": "OBJECT",
    "properties": {
        "fields": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "field_id": {"type": "STRING"},
                    "show_if": {
                        "type": "OBJECT",
                        "properties": {
                            "field": {"type": "STRING"},
                            "operator": {"type": "STRING", "enum": ["equals", "is_checked", ...]},
                            "value": {"type": "STRING"}
                        }
                    },
                    "conditional_fields": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"}
                    },
                    "needs_unlock": {"type": "BOOLEAN"},
                    "confidence": {"type": "STRING", "enum": ["high", "medium", "low"]}
                }
            }
        }
    }
}
```

### Step 2: Gemini Analyzes PDFs

**Input:**
- Form PDF
- Instruction PDF
- Current schema (field list)
- Response schema (structure enforcement)

**Gemini's Task:**
1. Read BOTH PDFs
2. For each field, identify:
   - **show_if**: What field triggers this? (triggered_by)
   - **conditional_fields**: What fields does this trigger? (triggers)
   - **needs_unlock**: Does it need READ_ONLY bit cleared?
   - **confidence**: High/Medium/Low

**Output Format (GUARANTEED):**
```json
{
  "fields": [
    {
      "field_id": "p1_q4",
      "conditional_fields": ["p1_q5a", "p1_q5b", "p1_q5c"],
      "confidence": "high"
    },
    {
      "field_id": "p1_q5a",
      "show_if": {
        "field": "p1_q4",
        "operator": "equals",
        "value": "yes"
      },
      "needs_unlock": true,
      "confidence": "high"
    }
  ]
}
```

### Step 3: Apply to Schema Bidirectionally

**Tool:** `apply_dependencies.py`

For each dependency:
1. Update triggered field with `show_if` (ConditionalDisplay)
2. Update trigger field with `conditional_fields` (List[str])
3. Add `unlock_method` for fields needing unlock

**Result:** Schema has BOTH directions of every relationship.

---

## Bidirectional Dependencies Explained

### FormField Model Already Supports This!

From `form_schema_model.py`:

```python
class ConditionalDisplay(BaseModel):
    """Conditional display logic"""
    field: str  # Field ID to check
    operator: ConditionalOperator  # equals, is_checked, etc.
    value: Union[str, int, float, bool]

class FormField(BaseModel):
    # This field is triggered by another field:
    show_if: Optional[ConditionalDisplay] = None

    # This field triggers these fields:
    conditional_fields: Optional[List[str]] = None
```

### Example: Name Change

**Trigger field (p1_q4 - "Has your name legally changed?"):**
```json
{
  "id": "p1_q4",
  "name": "My name has legally changed since issuance of my card",
  "type": "radio",
  "conditional_fields": ["p1_q5a", "p1_q5b", "p1_q5c"]
}
```

**Dependent field (p1_q5a - "Family Name on Green Card"):**
```json
{
  "id": "p1_q5a",
  "name": "Family Name (as appears on green card)",
  "type": "text",
  "read_only": true,
  "show_if": {
    "field": "p1_q4",
    "operator": "equals",
    "value": "yes"
  }
}
```

### Voice AI Can Now Ask:
- "User answered No to Q4" → Lookup `p1_q4.conditional_fields` → Skip Q5a-c
- "Should I ask Q5a?" → Check `p1_q5a.show_if` → Only if Q4 = "yes"

### PDF Viewer Can Now:
- Attach `onChange` to `p1_q4` → When changed, check `conditional_fields` → Show/hide Q5a-c
- When rendering `p1_q5a` → Check `show_if` → Hide if Q4 ≠ "yes"

---

## Tools

### 1. `gemini_dependency_analyzer.py`
**Purpose:** Extract dependencies using Gemini with forced structured output

**Usage:**
```bash
python gemini_dependency_analyzer.py \
  i-90.pdf \
  i-90_instructions.pdf \
  i-90_schema.json \
  i-90_dependencies.json
```

**Output:** JSON with all conditional relationships

### 2. `apply_dependencies.py`
**Purpose:** Apply dependencies to schema bidirectionally

**Usage:**
```bash
python apply_dependencies.py \
  i-90_schema.json \
  i-90_dependencies.json \
  i-90_schema_with_deps.json \
  --min-confidence=medium
```

**Output:** Updated schema with both `show_if` and `conditional_fields`

---

## Comparison: Old vs New

### Old Approach (Heuristic-Based)

```python
# conditional_logic_parser.py
if "show only if 'yes' is selected for requesting accommodations" in text:
    # Try to guess which field...
    # Search for "are you requesting" in same section...
    # Hope we find it...
```

**Problems:**
- I-90-specific patterns
- Fragile string matching
- Doesn't generalize
- Hard to maintain

### New Approach (Gemini Structured)

```json
{
  "field_id": "p4_q1a",
  "show_if": {
    "field": "p4_q1",
    "operator": "equals",
    "value": "yes"
  },
  "confidence": "high"
}
```

**Benefits:**
- ✅ Form-agnostic (works for ALL forms)
- ✅ No string parsing
- ✅ Guaranteed structure
- ✅ Gemini does the hard work
- ✅ Bidirectional by design

---

## Integration with Existing Pipeline

### Updated Pipeline Flow

**Before:**
1. Widget Inventory → Schema Builder
2. Gemini Validator → String conditionals (mixed quality)
3. conditional_logic_parser.py → Try to parse strings (I-90-specific)
4. dependency_finder.py → Heuristic matching (I-90-specific)
5. Build index → Hope it works

**After:**
1. Widget Inventory → Schema Builder
2. **gemini_dependency_analyzer.py** → Structured dependencies (form-agnostic)
3. **apply_dependencies.py** → Bidirectional schema
4. Build index → Guaranteed correct
5. Validate → Check for issues

---

## Success Criteria

After running the new pipeline, the schema should have:

1. ✅ **All trigger fields** have `conditional_fields: List[str]`
2. ✅ **All dependent fields** have `show_if: ConditionalDisplay`
3. ✅ **No string-format conditionals** (all structured)
4. ✅ **Confidence scores** for manual review prioritization
5. ✅ **Unlock metadata** for read-only conditional fields

---

## Example: Complete Flow for I-90

```bash
# Step 1: Extract dependencies (Gemini does the work)
python gemini_dependency_analyzer.py \
  test_schemas/test_pdfs/i-90/i-90.pdf \
  test_schemas/test_pdfs/i-90/i-90_instructions.pdf \
  test_schemas/test_pdfs/i-90/i-90_schema_v7_final.json \
  test_schemas/test_pdfs/i-90/i-90_dependencies.json

# Step 2: Apply to schema
python apply_dependencies.py \
  test_schemas/test_pdfs/i-90/i-90_schema_v7_final.json \
  test_schemas/test_pdfs/i-90/i-90_dependencies.json \
  test_schemas/test_pdfs/i-90/i-90_schema_v8_final.json \
  --min-confidence=medium

# Step 3: Rebuild index
python build_conditional_index.py \
  test_schemas/test_pdfs/i-90/i-90_schema_v8_final.json \
  test_schemas/test_pdfs/i-90/i-90_schema_v8_final.json

# Step 4: Validate
python schema_validator.py \
  test_schemas/test_pdfs/i-90/i-90_schema_v8_final.json
```

**Expected result:** Schema with bidirectional dependencies, 0 errors, ready for voice AI.

---

## Why This is Better

### For Developers
- No form-specific code to maintain
- Clean, predictable structure
- Easy to debug (JSON is readable)
- Works for ALL forms automatically

### For Voice AI
- Fast lookups: "What fields depend on this?"
- Both directions: "What controls this field?"
- Confidence scores: Prioritize manual review

### For PDF Viewer
- Simple onChange logic
- Clear show/hide rules
- Unlock instructions included

---

## Migration Path

### Deprecate
- ❌ `conditional_logic_parser.py` (form-specific heuristics)
- ❌ `dependency_finder.py` (I-90-specific patterns)

### Keep
- ✅ `build_conditional_index.py` (still needed for indexing)
- ✅ `schema_validator.py` (still needed for validation)
- ✅ `pdf_field_flag_mutator.py` (still needed for testing)

### New Standard Pipeline
1. **gemini_dependency_analyzer.py** - Extract dependencies
2. **apply_dependencies.py** - Apply bidirectionally
3. **build_conditional_index.py** - Build index
4. **schema_validator.py** - Validate

---

## Next Steps

1. **Test on I-90** - Verify Gemini extracts all 31 conditionals correctly
2. **Review confidence scores** - Check medium/low confidence dependencies
3. **Validate bidirectionality** - Ensure both directions work
4. **Test on another form** (I-485) - Prove it generalizes
5. **Update documentation** - Remove old heuristic-based approach

**This is the RIGHT way to handle dependencies.**
