# Label Overlay Approach - Findings

**Date:** October 30, 2025

---

## Concept

Annotate the PDF with field names overlaid directly on each widget, then send the **annotated PDF** to Gemini. This eliminates the ambiguity of matching JSON widget inventory to visual elements.

## Implementation

### 1. PDF Annotation (`pdf_annotator.py`)
- Reads PDF widgets and their bounding boxes
- Overlays field names in red text directly on each field
- Adds border around each field for clarity
- Successfully annotated I-589 with 405 field labels

### 2. Label Overlay Extractor (`gemini_label_overlay_extractor.py`)
- Uploads annotated PDF to Gemini
- Uses single prompt asking Gemini to:
  - Look at visual form layout
  - Read the red field name labels
  - Group related widgets into logical fields
- Requests aggressive consolidation (405 widgets → 150 target fields)

---

## Results

### What Worked ✓

1. **PDF annotation successful** - 405 field names overlaid on 12-page form
2. **Gemini can read the labels** - Started extraction correctly:
   ```json
   {
     "id": "alien_registration_number",
     "name": "Alien Registration Number(s) (A-Number)",
     "pdf_field_name": "PtAlLine1_ANumber[0]",
     "consolidated_widgets": ["PtAlLine1_ANumber[0]"]
   }
   ```
3. **Visual context preserved** - Gemini can see spatial relationships, sections, tables

### What Didn't Work ✗

1. **JSON Truncation at ~870 lines** (same 8K token output limit)
   - Parsed ~150-200 fields before truncation
   - Error: `Unterminated string starting at: line 874`
   - Same issue as hybrid v1 before batching

### Analysis

The label overlay approach **fundamentally works** - Gemini successfully:
- Reads field names from the visual overlay
- Understands form structure
- Begins correct extraction with proper consolidation

**However**, it hits the same output token limit as other approaches.

---

## Comparison: Label Overlay vs Hybrid

| Aspect | Hybrid (PDF + JSON) | Label Overlay (Annotated PDF) |
|--------|-------------------|----------------------------|
| **Input Complexity** | 2 inputs (PDF + JSON inventory) | 1 input (annotated PDF) |
| **Matching Ambiguity** | High (must correlate JSON → visual) | Low (labels directly on fields) |
| **Visual Context** | ✓ | ✓ |
| **Exact Field Names** | ✓ | ✓ |
| **Token Efficiency** | Moderate (JSON is verbose) | Better (visual only) |
| **Output Limit Issue** | Yes (needs batching) | Yes (needs batching) |
| **Implementation** | More complex (2-step correlation) | Simpler (single visual reference) |

---

## Key Insights

### 1. Visual Labels > JSON Matching

The label overlay approach proves that **showing field names directly on the form** is more intuitive for Gemini than providing a separate JSON inventory. This reduces cognitive load and ambiguity.

### 2. Output Limit Is The Real Bottleneck

Whether we use:
- Hybrid (PDF + JSON inventory)
- Label Overlay (annotated PDF)
- Structured only (JSON)

All approaches hit the **8K output token limit** when trying to extract 400+ widgets in one pass.

### 3. Batching Is Essential

For large forms (200+ fields), batching is unavoidable with current Gemini output limits.

---

## Recommendations

### Option A: Batched Label Overlay (Best of Both Worlds)

Combine label overlay + batching:

1. **Annotate entire PDF** with all field names
2. **Process in batches** by page range or widget count
3. **Each batch sees:**
   - Full annotated PDF (visual context for whole form)
   - Subset of widgets to extract (50-100 at a time)
4. **Advantages:**
   - Visual labels eliminate matching ambiguity
   - Batching prevents truncation
   - Each batch has full form context (can see sections, tables spanning pages)

### Option B: Stick with Hybrid + Batching (Current Best)

The hybrid approach works well with batching:
- ✓ 100% widget coverage achieved
- ✓ No hallucination
- ✓ Proven with I-589 (278 fields extracted)
- ⚠️ Over-extracting (278 vs 170 target)

**Next step:** Improve consolidation logic, not extraction method.

### Option C: Hybrid Output for Gemini 1.5 Pro

Try with `gemini-1.5-pro` which may have higher output token limits (but slower and more expensive).

---

## Verdict

The label overlay approach is **conceptually superior** for single-pass extraction because it:
- Makes field name matching trivial
- Reduces ambiguity
- Provides better spatial context

**But** for production use with large forms, **batching is required anyway**, which makes the implementation complexity similar to the hybrid approach.

**Recommendation:** Use **hybrid approach with batching** for now, but keep label overlay as a potential optimization if Gemini's output limits increase in the future.

---

## Files Created

- `pdf_annotator.py` - Annotates PDF with field name overlays
- `gemini_label_overlay_extractor.py` - Extracts from annotated PDF
- `i589_annotated.pdf` - Test annotation with 405 field labels
- `gemini_label_overlay_partial.json` - Partial extraction (truncated)

---

## Cost Analysis

**Annotation Cost:** Negligible (local PyMuPDF operation)

**Extraction Cost:**
- Single-pass (failed): 1 API call × large context
- Batched (estimated): ~9 API calls × large context
- Similar cost to hybrid approach

---

## Conclusion

Your idea to overlay field names directly on the PDF was excellent - it **does** simplify Gemini's task significantly. The partial extraction shows correct field identification and grouping.

The real bottleneck is Gemini's output token limit, not the input approach. For production, we need batching regardless of input method.

**Status:** Proof of concept successful, but production use requires batching implementation.
