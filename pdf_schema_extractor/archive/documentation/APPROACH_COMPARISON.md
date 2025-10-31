# PDF Schema Extraction: Approach Comparison

## Date: 2025-10-31

## Three Approaches Tested

### 1. Canonical (Heuristic-Only)
**Method:** PyMuPDF widget extraction + heuristic field detection
**Source:** `test_schemas/test_pdfs/i589_schema.json`

### 2. Gemini Visual (PDF Upload + OCR)
**Method:** Upload PDF to Gemini, extract schema visually
**Source:** `gemini_extraction_output/gemini_extracted_schema.json`

### 3. Gemini Structured (Widget Inventory Only)
**Method:** Extract widgets heuristically, send labels to Gemini for enhancement
**Source:** `gemini_structured_schema.json`

---

## Verification Results Comparison

| Metric | Canonical | Gemini Visual | Gemini Structured | Target |
|--------|-----------|---------------|-------------------|--------|
| **Overall Confidence** | **75.5%** | 45.0% | 64.7% | 90%+ |
| | | | | |
| **Layer 1: Widget Coverage** | | | | |
| Score | **22.5%** | 0.0% | **76.8%** | 95%+ |
| Status | FAIL | FAIL | FAIL | |
| | | | | |
| **Layer 2: Type Compatibility** | | | | |
| Score | **100%** | 0.0% | **100%** | 100% |
| Status | PASS | FAIL | PASS | |
| | | | | |
| **Layer 3: Structural Consistency** | | | | |
| Score | **99.6%** | 100% | 1.8% | 95%+ |
| Status | PASS | PASS | FAIL | |
| | | | | |
| **Layer 4: Heuristic Cross-Val** | | | | |
| Score | 80.0% | 80.0% | 80.0% | 80%+ |
| Status | PASS | PASS | PASS | |
| | | | | |
| **Field Count** | 170 | 135 | 324 | ~170 |
| **Ground Truth** | 170 | 170 | 170 | |
| **Accuracy** | 100% | 79.4% | 190.6% | 90-110% |

---

## Detailed Analysis

### Canonical (Heuristic) - 75.5% Confidence

**Strengths:**
- ✅ 100% type compatibility (knows actual widget types)
- ✅ 99.6% structural consistency
- ✅ Exact field count match (170)
- ✅ Has actual PDF field names

**Weaknesses:**
- ❌ Only 22.5% widget coverage (missing many widgets)
- ❌ No semantic understanding
- ❌ No intelligent grouping
- ❌ Poor table detection

**Root Cause of Low Coverage:**
The canonical schema likely uses a different field naming convention or only includes a subset of widgets. Need to investigate why 77.5% of widgets are marked as "missing."

---

### Gemini Visual (PDF Upload) - 45.0% Confidence

**Strengths:**
- ✅ 100% structural consistency
- ✅ Excellent semantic understanding
- ✅ Good table detection (found 6 tables)
- ✅ Smart grouping (radio/checkbox groups)

**Weaknesses:**
- ❌ 0% widget coverage (hallucinated field names)
- ❌ 0% type compatibility (can't validate)
- ❌ Missing 35 fields (79.4% field count accuracy)

**Root Cause:**
Gemini generates human-readable field names from visual labels instead of using actual PDF widget names:
- **Actual**: `PtAILine1_ANumber[0]`
- **Gemini**: `Alien Registration Number (A-Number)[0]`

This makes the schema impossible to map back to the PDF for filling.

---

### Gemini Structured (Inventory Only) - 64.7% Confidence

**Strengths:**
- ✅ 76.8% widget coverage (big improvement over visual!)
- ✅ 100% type compatibility
- ✅ Uses exact PDF field names (no hallucination)
- ✅ Detected 1 table with 22 columns

**Weaknesses:**
- ❌ 1.8% structural consistency (major issues)
- ❌ Over-extracted (324 fields vs 170 target = 190.6%)
- ❌ Classified 221 widgets as "signature" (should be ~7)
- ❌ JSON parsing failures (3/5 batches had errors)
- ❌ Still missing 60 widgets (23.2%)

**Root Causes:**
1. **JSON truncation**: Large batches caused malformed JSON responses
2. **Mis-classification**: Without visual context, Gemini mis-labeled many widget types
3. **Over-generation**: Created 324 fields from 405 widgets (some duplication/splitting?)
4. **Structural errors**: Low consistency score suggests broken references, invalid groups

---

## Key Insights

### Finding #1: Visual Context Matters for Accuracy
- **Gemini Visual**: Better semantic understanding, correct types
- **Gemini Structured**: Mis-classified 54% of widgets as "signature"

**Conclusion:** Gemini needs visual context to correctly infer field types.

### Finding #2: Widget Inventory Critical for Coverage
- **Gemini Visual**: 0% coverage (made up field names)
- **Gemini Structured**: 76.8% coverage (used provided names)

**Conclusion:** Providing exact widget names solves hallucination problem.

### Finding #3: Batch Size Issues
- 3 out of 5 batches (100 widgets each) failed with JSON parsing errors
- Smaller batch (5 widgets) succeeded
- Suggests token limit or response size issues

**Conclusion:** Need smaller batches (~25-50 widgets) or streaming responses.

### Finding #4: Table Detection from Labels Alone is Limited
- **Gemini Visual** (with PDF): Found 6 tables
- **Gemini Structured** (labels only): Found 1 table

**Conclusion:** Visual layout helps identify table patterns. Labels alone are insufficient.

---

## Hybrid Approach Recommendations

### Option A: Heuristic + Gemini Visual Enhancement (Recommended)

**Pipeline:**
```
1. Heuristic extraction → Extract all widgets with actual field names
2. Create widget inventory → field_name + label + position
3. Upload PDF to Gemini → Visual analysis for context
4. Provide widget inventory → Force Gemini to use exact names
5. Gemini enhances schema → Grouping, typing, tables (with visual context)
6. Cross-validate → Ensure 100% widget coverage
```

**Advantages:**
- ✅ 100% widget coverage (from inventory)
- ✅ Accurate typing (from visual context)
- ✅ Smart grouping (from Gemini)
- ✅ Good table detection (from visual layout)
- ✅ No hallucination (forced to use inventory names)

**Expected Results:**
- Widget coverage: 95%+
- Type compatibility: 100%
- Structural consistency: 95%+
- Overall confidence: **85-90%**

### Option B: Gemini with Code Execution

**Method:**
Use Gemini SDK with code_execution tool:
```python
from google import genai
from google.genai import types

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=f"Extract schema from {pdf_uri}. Use PyMuPDF to get widget names.",
    config=types.GenerateContentConfig(
        tools=[types.Tool(code_execution=types.ToolCodeExecution)]
    )
)
```

**Advantages:**
- ✅ Gemini can run PyMuPDF directly
- ✅ Gets actual field names autonomously
- ✅ Visual + programmatic access

**Disadvantages:**
- ❌ Requires SDK (we're using REST API)
- ❌ Less control/debuggability
- ❌ May still have token limit issues

### Option C: Structured Only with Better Prompts

**Improvements Needed:**
1. Reduce batch size to 25-50 widgets
2. Add visual field type hints to labels
3. Provide better table detection heuristics
4. Add fallback for failed batches

**Expected Improvement:**
- Widget coverage: 85-90% (from 76.8%)
- Structural consistency: 50-70% (from 1.8%)
- Overall: ~70-75%

**Assessment:** Not sufficient to reach 90%+ target.

---

## Recommended Next Steps

### Immediate (This Session):
1. ✅ Document comparison (this file)
2. ⏳ Implement Option A (Hybrid: PDF + Inventory)
3. ⏳ Test on i-589.pdf
4. ⏳ Verify results reach 85%+ confidence

### Short-term (Next Session):
1. Refine prompts based on results
2. Add better error handling for JSON parsing
3. Implement retry logic for failed batches
4. Test on additional PDF forms

### Long-term:
1. Consider Code Execution approach (Option B)
2. Build production pipeline
3. Create extraction CLI tool
4. Add visual verification overlay

---

## Conclusion

**Best Approach:** **Hybrid (Heuristic + Gemini with PDF Upload + Widget Inventory)**

This combines:
- Heuristic strengths: Exact field names, complete widget coverage
- Gemini strengths: Semantic understanding, grouping, table detection
- Inventory constraint: Prevents hallucination, ensures coverage

**Expected Performance:**
- Widget Coverage: **95-100%** (forced by inventory)
- Type Compatibility: **100%** (validated against widgets)
- Structural Consistency: **90-95%** (Gemini's strong suit)
- Field Count Accuracy: **90-100%** (constrained by inventory)
- **Overall Confidence: 85-90%+** ✓

This should meet or exceed all target metrics while avoiding the pitfalls of each individual approach.
