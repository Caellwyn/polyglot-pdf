# Gemini Extraction Findings - Initial Full Run

## Date: October 28, 2025

## Executive Summary

Successfully completed first full extraction of i-589.pdf using form-agnostic Gemini pipeline. Extracted **135 fields** from **13 auto-detected sections** with **79.4% field count accuracy** compared to ground truth (170 fields).

## Extraction Results

### Performance Metrics

| Metric | Result | Target | Status |
|--------|--------|--------|--------|
| Total Fields | 135 | 170 | 79.4% ✓ |
| Sections Detected | 13 | 9 | Auto-detected ✓ |
| Field Count Accuracy | 79.4% | 90%+ | Needs improvement |
| Type Distribution Accuracy | 52.9% | 90%+ | Needs improvement |
| Overall Score | 66.2% | 90%+ | **Needs refinement** |
| Widget Coverage | 0.0% | 95%+ | **BUG - Investigate** |

### Field Type Distribution

| Type | Gemini | Ground Truth | Difference | Analysis |
|------|--------|--------------|------------|----------|
| text | 58 | 71 | -13 | Under-extracted text fields |
| radio | 28 | 26 | +2 | Good accuracy ✓ |
| date | 13 | 15 | -2 | Good accuracy ✓ |
| textarea | 11 | 13 | -2 | Good accuracy ✓ |
| checkbox | 7 | 16 | -9 | Under-extracted checkboxes |
| signature | 6 | 7 | -1 | Good accuracy ✓ |
| table | 6 | 10 | -4 | Missing 4 tables |
| tel | 3 | 3 | 0 | Perfect ✓ |
| number | 3 | 1 | +2 | Over-extracted |
| select | 0 | 3 | -3 | Missed all select fields |
| email | 0 | 1 | -1 | Missed email field |
| static_text | 0 | 4 | -4 | Missed static text fields |

## Critical Issues

### 1. Widget Coverage: 0.0% ⚠️
**Status**: CRITICAL BUG

**Problem**: Validation reports 0% widget coverage despite successful extraction.

**Possible Causes**:
- PDF field name mismatch between extraction and validation
- Schema structure differs from expected format
- Bug in `_collect_pdf_field_names()` method
- Widget enumeration issue in verifier

**Action Required**: Debug verifier's widget coverage calculation

### 2. Missing 35 Fields (-20.6%)
**Status**: HIGH PRIORITY

**Breakdown**:
- 13 text fields
- 9 checkboxes
- 4 tables
- 4 static_text fields
- 3 select fields
- 2 misc fields

**Likely Causes**:
- Section detection too granular (13 vs 9 sections)
- Some fields split across section boundaries
- Gemini not recognizing certain field patterns
- Table detection missing complex tables

### 3. Type Distribution Accuracy: 52.9%
**Status**: MEDIUM PRIORITY

**Issues**:
- Missing all select fields (0/3)
- Missing all email fields (0/1)
- Missing all static_text fields (0/4)
- Under-detecting checkboxes (7/16)

**Likely Causes**:
- Prompts need refinement for select/email/static_text
- Checkbox vs radio group logic needs tuning
- Data model may not clearly define static_text

## Strengths

### What Worked Well ✓

1. **Auto Section Detection**
   - Successfully detected 13 sections without hardcoding
   - Form-agnostic approach validated
   - Section titles accurately extracted

2. **Radio Button Grouping**
   - 28/26 (108%) - slightly over but close
   - Correctly identified mutually exclusive patterns

3. **Date Field Detection**
   - 13/15 (87%) - good accuracy
   - High confidence scores (90%+)

4. **Tel Field Detection**
   - 3/3 (100%) - perfect accuracy

5. **Signature Fields**
   - 6/7 (86%) - good accuracy

6. **Infrastructure**
   - Upload → Process → Extract pipeline working smoothly
   - Chunked extraction avoiding token limits
   - All 13 sections extracted successfully
   - No API errors or timeouts

## Next Steps Recommendations

### Immediate (Next Session)

#### 1. Fix Widget Coverage Bug (CRITICAL)
**Priority**: P0

**Steps**:
```python
# Debug widget coverage calculation
verifier = SchemaVerifier()
result = verifier.verify_widget_coverage("i-589.pdf", gemini_schema)
print(f"PDF widgets found: {result.details['total_widgets']}")
print(f"Schema PDF names: {result.details['covered_widgets']}")
# Compare what's in PDF vs what's in schema
```

**Expected Outcome**: Identify mismatch between PDF field names and schema field names

#### 2. Investigate Missing 35 Fields
**Priority**: P0

**Action**: Compare Gemini schema with ground truth field-by-field
```bash
# Create comparison script
python compare_schemas.py \
  gemini_extraction_output/gemini_extracted_schema.json \
  test_schemas/test_pdfs/i589_schema.json \
  > field_diff.txt
```

**Analyze**:
- Which specific fields are missing?
- Are they clustered in certain sections?
- What patterns do missing fields share?

#### 3. Run Verification Tests
**Priority**: P1

**Steps**:
```python
from schema_verifier import verify_schema

# Test Gemini extraction
gemini_report = verify_schema(
    "test_schemas/test_pdfs/i-589.pdf",
    "gemini_extraction_output/gemini_extracted_schema.json",
    "verification_gemini.json"
)

# Test canonical schema (validation)
canonical_report = verify_schema(
    "test_schemas/test_pdfs/i-589.pdf",
    "test_schemas/test_pdfs/i589_schema.json",
    "verification_canonical.json"
)

# Compare reports
compare_verification_reports(gemini_report, canonical_report)
```

**Expected Outcome**:
- Canonical should pass all layers
- Gemini will show specific gaps
- Comparison reveals refinement targets

### Short-term (Next 1-2 Sessions)

#### 4. Refine Gemini Prompts
**Priority**: P1

**Focus Areas**:
1. **Select fields** - Add explicit examples in prompt
2. **Email fields** - Include in type inference list
3. **Static text** - Define clearly in data model
4. **Checkboxes** - Tune checkbox vs radio logic

**Approach**:
- Add examples of each field type to prompts
- Clarify data model definitions
- Test on small sections first

#### 5. Improve Table Detection
**Priority**: P1

**Current**: 6/10 tables detected (60%)

**Actions**:
- Analyze the 4 missing tables
- Check if they're complex multi-row tables
- Refine table detection heuristics
- Add table detection examples to prompt

#### 6. Section Detection Tuning
**Priority**: P2

**Observation**: 13 sections detected vs 9 in ground truth

**Investigation**:
- Are extra sections causing field splits?
- Should we merge similar section titles?
- Does over-segmentation hurt accuracy?

**Test**: Try merging sections and re-extracting

### Medium-term (Next 3-5 Sessions)

#### 7. Implement Heuristic Cross-Validation
**Priority**: P2

**Goal**: Use heuristic extraction as validation baseline

**Steps**:
1. Run heuristic extraction
2. Compare with Gemini extraction
3. High agreement = high confidence
4. Disagreements = manual review needed

#### 8. Test on Additional PDFs
**Priority**: P2

**Goal**: Validate form-agnostic approach

**Actions**:
- Test on 2-3 other USCIS forms
- Measure accuracy without ground truth
- Use verification system for validation

#### 9. Build Field Comparison Tool
**Priority**: P2

**Features**:
- Visual diff of schemas
- Highlight missing/extra fields
- Show type mismatches
- Generate refinement suggestions

#### 10. Create Extraction CLI
**Priority**: P3

**Goal**: Production-ready extraction tool

**Features**:
```bash
pdf-extract schema input.pdf --output schema.json --verify
```

## Success Criteria for Next Milestone

### Definition of Success:
- Field count accuracy: **90%+** (153-187 fields)
- Type distribution accuracy: **85%+**
- Widget coverage: **95%+**
- All critical verification layers passing
- Zero critical bugs

### Estimated Effort:
- Bug fixes: 1-2 hours
- Prompt refinement: 2-3 hours
- Testing & validation: 1-2 hours
- **Total**: 4-7 hours over 2-3 sessions

## Lessons Learned

### What We Learned

1. **Auto section detection works** but may be too granular
2. **Gemini is strong** at radio/date/tel/signature detection
3. **Gemini struggles** with select/email/static_text/checkbox
4. **Widget coverage validation** needs debugging (critical path)
5. **Form-agnostic approach is viable** - no hardcoded section names

### Adjustments Needed

1. **Prompt engineering** - Add explicit examples for weak types
2. **Data model clarity** - Define static_text, select, email more clearly
3. **Section merging** - May need to consolidate similar sections
4. **Table detection** - Heuristics or better prompting needed
5. **Verification** - Fix widget coverage bug immediately

## Data Files Generated

- `gemini_extraction_output/gemini_extracted_schema.json` - Full extraction
- `gemini_full_run.log` - Complete extraction log
- Section raw outputs: `gemini_chunk_part_*.json`

## Repository State

- All code committed ✓
- Documentation up to date ✓
- Next session ready to start with verification ✓
- Known issues documented ✓

---

**Status**: First iteration complete. Ready for refinement cycle.
**Confidence**: Infrastructure solid (90%), Accuracy needs work (66%)
**Recommendation**: Focus on bug fixes and prompt refinement next session.
