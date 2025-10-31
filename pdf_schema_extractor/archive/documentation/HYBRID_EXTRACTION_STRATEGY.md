# Hybrid PDF Schema Extraction Strategy

## Problem Identified

**Verification Results:**
- **Canonical Schema** (heuristic): 75.5% confidence
  - Widget coverage: 22.5% ✓ (has actual PDF field names)
  - Type compatibility: 100% ✓
  - Structural consistency: 99.6% ✓

- **Gemini Schema** (LLM): 45.0% confidence
  - Widget coverage: 0.0% ✗ (using human-readable labels instead of PDF field names)
  - Type compatibility: 0.0% ✗ (can't validate without PDF field names)
  - Structural consistency: 100.0% ✓

## Root Cause

**Gemini cannot see actual PDF widget field names** when analyzing the PDF visually.

Examples:
- **PDF Widget Name**: `form1[0].#subform[0].PtAILine1_ANumber[0]` → `PtAILine1_ANumber[0]`
- **Gemini Generated**: `Alien Registration Number (A-Number)[0]` ❌

This makes it impossible to:
1. Map schema back to PDF for filling
2. Verify widget coverage
3. Validate type compatibility
4. Cross-reference with heuristic extraction

## Complementary Strengths

### Heuristic Extractor Strengths
✅ **Accurate PDF field names** - Directly reads widget metadata
✅ **Type compatibility** - Knows actual widget types
✅ **Complete widget coverage** - Finds all form fields
✅ **Position data** - X/Y coordinates, pages

### Heuristic Extractor Weaknesses
❌ Poor semantic understanding (can't infer "date" from "DateOfBirth")
❌ No grouping intelligence (treats radio groups as individual checkboxes)
❌ No table detection (misses multi-row patterns)
❌ No conditional logic detection

### Gemini (LLM) Strengths
✅ **Excellent semantic understanding** - Infers field types from labels
✅ **Smart grouping** - Consolidates radio/checkbox groups
✅ **Table detection** - Identifies repeating patterns
✅ **Human-readable labels** - Generates clean field names
✅ **Structural understanding** - Detects sections and relationships

### Gemini (LLM) Weaknesses
❌ No access to actual PDF field names
❌ Hallucinates field names from visual labels
❌ Can't verify against actual PDF structure

## Hybrid Solution

### Approach: Heuristic-First with Gemini Enhancement

```
┌─────────────────────────────────────────────┐
│  Step 1: Heuristic Widget Extraction       │
│  - Extract all PDF widgets (PyMuPDF)       │
│  - Get: field_name, type, position, page   │
│  - Output: Widget inventory                │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Step 2: Pass Widget List to Gemini        │
│  - Upload PDF to Gemini                    │
│  - Provide complete widget inventory       │
│  - Ask: "Map visual fields to widgets"    │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Step 3: Gemini Semantic Analysis          │
│  - Groups widgets into radio/checkbox      │
│  - Detects tables from patterns            │
│  - Infers semantic types                   │
│  - Maps to actual PDF field names          │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Step 4: Merge & Validate                  │
│  - Combine heuristic + Gemini results      │
│  - Cross-validate coverage                 │
│  - Verify all widgets accounted for        │
└─────────────────────────────────────────────┘
```

## Implementation Plan

### 1. Create Widget Inventory Function

```python
def extract_widget_inventory(pdf_path: str) -> List[Dict]:
    """
    Extract all PDF widgets with metadata.

    Returns:
        [
            {
                "field_name": "PtAILine1_ANumber[0]",
                "full_name": "form1[0].#subform[0].PtAILine1_ANumber[0]",
                "widget_type": "text",
                "page": 0,
                "x": 100,
                "y": 200,
                "width": 150,
                "height": 20
            },
            ...
        ]
    """
```

### 2. Modify Gemini Prompt

**Current Prompt:**
```
5. Include pdf_field_name from the actual PDF form
```

**New Prompt:**
```
**CRITICAL - PDF Widget Inventory:**

Below is the COMPLETE list of actual PDF widget field names extracted from this form.
You MUST use these exact field names in the "pdf_field_name" field:

{widget_inventory_json}

**Your Task:**
1. Visually identify each form field in the PDF
2. Match each visual field to the correct widget from the inventory above
3. Use the EXACT "field_name" from the inventory as "pdf_field_name"
4. Group related widgets (radio buttons, checkboxes, tables)
5. Infer semantic types based on labels and context

**Example:**
Visual field: "Alien Registration Number (A-Number)"
Widget inventory match: "PtAILine1_ANumber[0]"
Your output:
{
  "id": "alien_registration_number",
  "name": "Alien Registration Number (A-Number)",
  "spoken_name": "alien registration number",
  "pdf_field_name": "PtAILine1_ANumber[0]",  ← Use exact name from inventory
  "type": "text"
}
```

### 3. Add Widget-to-Visual Matching

Provide Gemini with spatial context to help matching:

```python
widget_context = []
for widget in widgets:
    widget_context.append({
        "field_name": widget["field_name"],
        "type": widget["widget_type"],
        "page": widget["page"],
        "approx_position": f"page {widget['page']}, y={widget['y']}"
    })
```

### 4. Cross-Validation Layer

After Gemini extraction:
```python
def validate_hybrid_schema(
    widgets: List[Dict],
    gemini_schema: Dict
) -> ValidationReport:
    """
    Ensure every widget is mapped and no hallucinations.
    """
    widget_names = {w["field_name"] for w in widgets}
    schema_names = extract_pdf_field_names(gemini_schema)

    coverage = len(schema_names & widget_names) / len(widget_names)
    hallucinated = schema_names - widget_names
    missing = widget_names - schema_names

    return {
        "coverage": coverage,
        "hallucinated": list(hallucinated),
        "missing": list(missing)
    }
```

## Expected Improvements

### Before (Gemini Only):
- Widget coverage: 0.0%
- Type compatibility: 0.0%
- Overall confidence: 45.0%

### After (Hybrid):
- Widget coverage: **95%+** ✓ (using actual field names)
- Type compatibility: **100%** ✓ (validated against widgets)
- Semantic quality: **90%+** ✓ (Gemini's strength)
- Overall confidence: **85-90%** ✓

## Alternative: Code Execution (Future)

**Using Gemini SDK with Code Execution:**

```python
from google import genai
from google.genai import types

client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=f"Extract schema from this PDF. Use PyMuPDF to get actual field names: {pdf_uri}",
    config=types.GenerateContentConfig(
        tools=[types.Tool(code_execution=types.ToolCodeExecution)]
    )
)
```

**Pros:**
- Gemini can directly run PyMuPDF code
- No need to pass widget inventory
- More autonomous

**Cons:**
- Requires SDK (we're using REST API)
- Less control over extraction process
- Harder to debug/validate
- Not available in all regions

**Recommendation:** Stick with hybrid approach for now, consider code execution later.

## Implementation Steps

1. ✅ Identify the problem (widget name mismatch)
2. ✅ Document hybrid strategy
3. ⏳ Implement widget inventory extraction
4. ⏳ Modify Gemini prompts to include widget list
5. ⏳ Add widget-to-visual matching logic
6. ⏳ Test on i-589.pdf
7. ⏳ Validate widget coverage reaches 95%+
8. ⏳ Compare hybrid vs pure Gemini vs pure heuristic

## Success Criteria

- [ ] Widget coverage: 95%+ (from 0%)
- [ ] Type compatibility: 100% (from 0%)
- [ ] Semantic quality: Maintains Gemini's grouping/typing strength
- [ ] Field count accuracy: 90%+ (153-187 fields)
- [ ] Overall confidence: 85%+
- [ ] No hallucinated field names
- [ ] All widgets accounted for

## Next Session

**Priority 1:** Implement widget inventory extraction
**Priority 2:** Update Gemini prompt with widget list
**Priority 3:** Test hybrid extraction on i-589.pdf
**Priority 4:** Compare results with verification system

---

**Status:** Strategy documented, ready for implementation
**Estimated effort:** 2-3 hours
**Expected outcome:** Production-ready hybrid extraction pipeline
