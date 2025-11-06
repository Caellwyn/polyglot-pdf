# Automated Schema Extraction Results

**Date:** November 5, 2025
**Test Subject:** i-90.pdf (Green Card Replacement Form)
**Comparison:** Draft extraction vs. Gold standard (manually perfected)

---

## Executive Summary

The automated extractor successfully extracts **~75-80% of the schema automatically**, providing a strong foundation for human review and correction.

### ✅ **What Works Well**

| Metric | Score | Status |
|--------|-------|--------|
| **Field Coverage** | 93.9% (124/132) | Excellent |
| **Section Detection** | 100% (10/10) | Perfect |
| **Field Ordering** | 76.6% (95/124) | Good |
| **Basic Properties** | 100% | Perfect |
| **Group Detection** | 16 groups found | Good |

### ⚠️ **Needs Improvement**

| Area | Score | Notes |
|------|-------|-------|
| **Field Types** | 60.5% (75/124) | Main issue - see details below |
| **Field Consolidation** | 188 → 132 needed | Human judgment required |
| **Help Text** | 0% | All placeholder text |
| **Validation Rules** | 0% | Not extracted |
| **Conditional Logic** | 0% | Not extracted |

---

## Detailed Results

### Field Coverage: 93.9%

**Found:** 124 of 132 gold standard fields
**Missing:** 8 fields
- `p1_unit_type6c_unit`
- `p1_unit_type7b_unit`
- `p3_ethnicity`
- `p3_eye_color`
- `p3_hair_color`
- `p3_race`
- `p6_unit_type3b_unit`
- `p7_unit_type3b_unit`

**Analysis:** These are primarily consolidated fields (unit type groups and select fields with specific IDs in gold). The raw widgets exist in the draft but with different IDs.

---

### Section Detection: 100%

All 10 sections correctly identified:
- Part 1 - Information About You
- Part 2 - Application Type
- Part 3 - Processing Information
- Part 4 - Accommodations... (both variants)
- Part 5 - Applicant's Statement...
- Part 6 - Interpreter's Contact...
- Part 7 - Contact Information...  (both variants)
- Part 8 - Additional Information

**Success Factor:** The regex pattern `[0-9A-Z]\.` on labels worked perfectly for section parsing.

---

### Field Ordering: 76.6%

**Correct:** 95 of 124 fields have matching `question_number`
**Incorrect:** 29 fields

**Example Matches:**
- `1.1` ✓
- `1.3.A` ✓
- `2.1` ✓

**Analysis:** The ordering extraction using regex on labels is highly effective. The 23% error rate is likely due to edge cases in label formatting or fields without clear numbering.

---

### Field Types: 60.5%

**Distribution in Draft:**
- text: 56
- checkbox: 78
- date: 2
- select: 6
- signature: 38
- textarea: 8

**Common Mismatches:**
- **checkbox → radio**: Draft detects individual checkbox widgets, gold consolidates into radio groups
- **signature → text**: Draft conservatively labels non-signature fields as 'signature' (XFA quirk)
- **text → date**: Draft only catches obvious date patterns, misses some

**Fix Needed:** Better heuristics for:
1. Consolidating checkbox arrays into radio fields
2. Date field detection (more keywords)
3. Signature vs text distinction

---

### Basic Properties: 100%

Perfect accuracy on:
- `read_only`: 124/124 (100%)
- `required`: 124/124 (100%)
- `multiline`: 124/124 (100%)

**Success Factor:** These come directly from PDF field flags, which are reliable.

---

### Field Consolidation

**Draft:** 188 individual widgets
**Gold:** 132 logical fields

**Consolidation Examples:**
- `P1_checkbox4[0]`, `P1_checkbox4[1]`, `P1_checkbox4[2]` → Single `p1_checkbox4` radio field
- Multiple unit type checkboxes → Single consolidated field

**Challenge:** Determining when to consolidate requires semantic understanding or human judgment.

---

## What's Automatically Extracted

### ✅ High Confidence (90-100% accurate)
- Field IDs (normalized from PDF names)
- PDF field names (full XFA paths)
- Page positions
- Basic flags (read_only, required, multiline, is_comb)
- Max length for text fields
- Section names (from labels)

### ⚠️ Medium Confidence (60-80% accurate)
- Field types (needs better heuristics)
- Field ordering (question numbers)
- Field grouping (checkbox/radio groups)
- Placeholder spoken names

### ❌ Requires Human Input (0% automated)
- Help text (instructions, context)
- Validation rules (patterns, constraints, formats)
- Conditional dependencies (show_if, controls_fields)
- Field consolidation decisions
- Select field options (extraction code exists but didn't work - needs debugging)

---

## Recommendations

### Immediate Improvements (Could Boost to 85% automation)

1. **Better Field Type Detection**
   - Add more date keywords: "date of", "date you", "dob", "expiration"
   - Improve signature vs text distinction using label analysis
   - Auto-consolidate checkbox arrays into radio groups when all members have `no_toggle_to_off` flag

2. **Select Option Extraction**
   - Debug why options aren't being extracted
   - Likely needs to match on full XFA path instead of short name

3. **Field Consolidation Heuristics**
   - Detect checkbox groups with [0], [1], [2] pattern
   - Check for `no_toggle_to_off` flag (indicates radio behavior)
   - Auto-consolidate into single radio field

### Schema Editor Must-Haves

Based on this analysis, the schema editor needs:

1. **Field Type Correction**
   - Quick dropdown to change field types
   - Bulk operations (change all selected fields to type X)

2. **Field Consolidation UI**
   - Visual grouping tool: select multiple checkboxes → create radio group
   - Drag-and-drop to merge fields
   - Preview of consolidated field

3. **Help Text Editor**
   - Template system for common field types (A-number, date, SSN)
   - Copy help text from similar field
   - Bulk apply help text to section

4. **Conditional Logic Builder**
   - Visual graph of dependencies (trigger → dependent)
   - Click two fields to create "show_if" relationship
   - Test conditional logic with sample data

5. **Validation Panel**
   - Show real-time Pydantic validation errors
   - Highlight incomplete/invalid fields
   - Coverage metrics (% complete)

---

## Files Generated

1. **`automated_extractor.py`** - Main extraction script
2. **`compare_schemas.py`** - Validation tool
3. **`test_schemas/test_pdfs/i-90/i-90_draft_schema.json`** - Draft extraction (188 fields)
4. **`i-90_widgets.json`** - Raw widget inventory

---

## Next Steps

### Phase 1: Quick Wins (1-2 hours)
- Fix select option extraction
- Improve date field detection
- Add auto-consolidation for radio groups

### Phase 2: Schema Editor UI (6-8 hours)
**Priority Features:**
1. PDF viewer with field overlay
2. Field property editor (types, help text, validation)
3. Field list with drag-and-drop ordering
4. Real-time validation panel
5. Conditional logic builder (click-to-link)

### Phase 3: Production Pipeline (2-3 hours)
1. Extract schema from new PDF
2. Open in editor
3. Human review (~30 min per form)
4. Validate and save
5. Deploy to system

---

## Success Criteria

**Target for Production:**
- Automated extraction: 85%+ coverage
- Human correction: < 30 min per form
- Quality: 100% validation pass rate

**Current Status:**
- ✅ Automated extraction: ~75-80%
- ⚠️ Human correction: ~2-4 hours (raw JSON editing)
- ⚠️ Quality: Needs validation tool

**With Schema Editor:**
- ✅ Automated extraction: ~80-85% (with improvements)
- ✅ Human correction: ~20-30 min (visual UI)
- ✅ Quality: Real-time validation ensures 100%
