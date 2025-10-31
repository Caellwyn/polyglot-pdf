# PDF Schema Extractor - Project Status & Handoff

**Date:** October 30, 2025
**Status:** Minimal approach validated, verifier corrected, critical gaps identified

---

## Mission-Critical Context

**Purpose:** Extract schemas from government immigration PDFs to power a voice AI that helps non-English speaking immigrants complete forms. These forms determine work permits, asylum status, and other life-changing outcomes.

**Quality Bar:** 100% correctness required, not 99%. A wrong field = rejected application.

**Scale:** Need to support 50+ different government forms.

---

## Current State Summary

### What Works ✅

1. **Widget Extraction (100%)** - All editable PDF fields captured
2. **Type Detection (100%)** - Field types correctly identified
3. **Grouping Detection** - Radio/checkbox groups and tables identified
4. **Section Metadata (83%)** - Basic Part/Section hierarchy from tooltips
5. **Verification System** - Now uses correct baselines and metrics

### Critical Gaps ❌

1. **Conditional Logic (0%)** - "If married, show section X" not captured
2. **Validation Rules (0%)** - No required flags, formats, constraints
3. **Help Text (0%)** - No instructions for voice AI to guide users
4. **Round-trip Testing (0%)** - Haven't verified schema→PDF works
5. **Section Accuracy (83%)** - 17% of fields missing proper section labels

---

## Approaches Tested

### Minimal Approach (WINNER)
- **Method:** Gemini for grouping/tables only, Python for everything else
- **Cost:** 1-2 API calls per form (~$0.02-0.05)
- **Quality:** 99.9% verification score
- **Coverage:** 100% widget coverage (405/405 fields)
- **Files:**
  - `gemini_grouping_extractor.py` - Extract semantic groups
  - `heuristic_hierarchy_parser.py` - Parse tooltips with regex
  - `schema_builder_from_groupings.py` - Combine into schema
- **Output:** `final_schema_minimal.json`

### Hybrid v2 Approach (DEPRECATED)
- **Method:** Batched Gemini extraction of full field objects
- **Cost:** 9 API calls per form (~$0.10-0.20)
- **Quality:** 70.9% verification score (missing section metadata)
- **Coverage:** 99.8% widget coverage (404/405 fields)
- **Issue:** Gemini didn't provide section information
- **Output:** `gemini_hybrid_schema.json`

**Decision:** Use Minimal approach for production.

---

## Key Lessons Learned

### 1. Separation of Concerns Works

**What Gemini is Good At:**
- Semantic understanding (this checkbox group represents "marital status")
- Grouping related fields
- Identifying tables and their dimensions
- Inferring relationships from visual layout

**What Python/Regex is Good At:**
- 100% completeness guarantees
- Consistent pattern matching
- Fast, deterministic parsing
- No API costs or token limits

**Mistake to Avoid:** Don't ask Gemini to extract everything. Use it strategically.

### 2. Metrics Must Measure What Matters

**Original Verifier Problems:**
- Used unfiltered widget count (449 vs 405 filtered)
- Had fake 80% hardcoded metric
- Required `section_id` that schemas didn't have
- Reported 90% coverage when actual was 100%

**Fixed Verifier:**
- Uses filtered widget inventory (same as extractors)
- Removed fake metrics
- Accepts `section` OR `section_id`
- Reports accurate 100% coverage

**Lesson:** Metrics are useless if they don't measure the right thing.

### 3. Government PDFs Have Quirks

- **Signature widgets = text fields** - Type 7 used for secure text inputs, not just signatures
- **No required flags** - PDF metadata doesn't have field constraints
- **No conditional logic** - Business rules live in instructions, not form structure
- **Tooltips are goldmines** - Rich semantic info about hierarchy and field purpose

### 4. Label Overlay Doesn't Solve Core Problem

We tested annotating PDFs with field names overlay for Gemini to see. Result: Doesn't solve output token limit. The bottleneck is output size, not input clarity.

### 5. Widget Filtering Matters

**Filtered out (55 widgets):**
- Barcodes
- Read-only fields
- Hidden fields
- Button widgets

**Why this matters:** Extractors use filtered count (405), verifier was using unfiltered (460), causing false "90% coverage" reports.

---

## Critical Findings - PyMuPDF Limitations

**What PyMuPDF Gives Us:**
- ✅ Field names, types, positions
- ✅ Tooltips/labels (rich semantic data!)
- ✅ Widget properties (read-only, hidden, etc.)

**What PyMuPDF Does NOT Give Us:**
- ❌ Required vs optional flags (0/460 fields have flag set)
- ❌ Validation rules (format, length, etc.)
- ❌ Conditional logic (JavaScript-based show/hide)
- ❌ Help text separate from tooltips

**Implication:** Need to extract constraints and logic from tooltips and form instructions.

---

## Production Pipeline Architecture

### Current Working Pipeline (Minimal Approach)

```
1. Widget Inventory (Python)
   ├─ Extract 405 editable widgets from PDF
   ├─ Filter out barcodes, read-only, hidden fields
   └─ Output: widget_inventory.json

2. PDF Annotation (Python)
   ├─ Overlay field names on PDF in red
   └─ Output: i589_annotated.pdf

3. Gemini Grouping (Gemini API)
   ├─ Identify radio/checkbox groups (51 groups)
   ├─ Identify tables with dimensions (6 tables)
   └─ Output: gemini_groupings.json (57 items, 14% of schema)

4. Tooltip Hierarchy Parsing (Python Regex)
   ├─ Extract Part/Section/Question from tooltips
   ├─ Extract spoken field names
   └─ Output: heuristic_hierarchy.json (83% success rate)

5. Schema Builder (Python)
   ├─ Apply Gemini groups (135 widgets)
   ├─ Add standalone widgets (270 widgets)
   ├─ Enrich with hierarchy metadata
   ├─ Validate 100% widget coverage
   └─ Output: final_schema_minimal.json (303 fields)

6. Verification (Python)
   ├─ Widget coverage: 100% ✓
   ├─ Type compatibility: 100% ✓
   ├─ Structural consistency: 99.7% ✓
   └─ Overall confidence: 99.9% ✓
```

**Cost per form:** ~$0.02-0.05
**Time per form:** ~2-3 minutes
**Quality:** 99.9% by current metrics

---

## What's Missing for Production

### Priority 1: Round-Trip Validation ⚠️ CRITICAL
**Status:** Not tested
**Why Critical:** Can't deploy until we verify schema→PDF→submission works

**Test Plan:**
1. Fill schema with test data
2. Export to PDF using PyMuPDF
3. Verify fields appear correctly in PDF
4. Verify PDF is submittable to government systems

**Acceptance:** 100% of fields round-trip correctly

---

### Priority 2: Conditional Logic Extraction ⚠️ CRITICAL
**Status:** 0% implemented
**Why Critical:** Voice AI needs to know "If married, ask about spouse"

**Current Coverage:** 0 fields with `show_if` rules (should be ~20-50)

**Extraction Strategy:**
1. Parse form instructions for conditional language
   - "If yes, complete Part C"
   - "Answer questions 5-10 only if..."
2. Gemini pass to identify dependencies
3. Add `show_if` rules to schema

**Validation:** Manual review of i-589 to identify all conditionals

---

### Priority 3: Field Constraints & Validation ⚠️ CRITICAL
**Status:** Partial (types only)
**Why Critical:** Voice AI must validate user input

**What We Need:**
- Required vs optional
- Data type (SSN, date, phone, etc.)
- Format (MM/DD/YYYY, XXX-XX-XXXX)
- Min/max length
- Allowed values/ranges

**Extraction Sources:**
1. Tooltips - "Enter 8-9 digit A-Number"
2. Field names - "DateFrom" implies date type
3. Gemini inference - "This looks like a social security number"

**Validation:** Test with invalid inputs, verify rejection

---

### Priority 4: Section Accuracy (83% → 100%)
**Status:** Regex parser failing on 17% of fields
**Why Critical:** Poor navigation experience

**Failures:**
- Part E fields - Different tooltip format
- Instruction/note fields - No standard pattern

**Fix Options:**
1. Improve regex patterns for Part E
2. Add Gemini tooltip parser for validation
3. Hybrid: Regex first, Gemini for failures

**Acceptance:** 100% of fields have correct section

---

### Priority 5: Help Text / Instructions
**Status:** Not extracted
**Why Important:** Better UX for voice AI

**Sources:**
- Tooltips (we have these)
- Form instructions (not parsed yet)
- Examples in form (not identified)

**Extraction:** Likely needs Gemini to identify helpful instructions

---

## File Organization

### Active Production Files

**Extractors:**
- `widget_inventory.py` - Extract widgets from PDF
- `pdf_annotator.py` - Create labeled PDF
- `gemini_grouping_extractor.py` - Gemini semantic grouping
- `heuristic_hierarchy_parser.py` - Regex tooltip parsing
- `schema_builder_from_groupings.py` - Combine into schema

**Verification:**
- `schema_verifier.py` - Multi-layer validation (CORRECTED)

**Outputs:**
- `final_schema_minimal.json` - Best schema so far
- `heuristic_hierarchy.json` - Tooltip parsing results
- `gemini_groupings.json` - Grouping extraction

### Deprecated Files (Can Archive)

**Old Approaches:**
- `gemini_hybrid_extractor.py` - Batched approach (replaced by minimal)
- `gemini_hybrid_schema.json` - Output from hybrid v2
- `gemini_extraction_output/` - Old extraction attempts

**Old Documentation:**
- `HYBRID_EXTRACTION_STRATEGY.md` - Pre-minimal approach
- `APPROACH_COMPARISON.md` - Outdated comparison
- `FINAL_SESSION_SUMMARY.md` - Old session summary

**Keep for Reference:**
- `METRICS_AUDIT.md` - Documents verifier issues found
- `VERIFIER_FINAL_RESULTS.md` - Corrected verification results
- `MINIMAL_APPROACH_SUMMARY.md` - Minimal approach details
- `LABEL_OVERLAY_FINDINGS.md` - Why label overlay doesn't help

---

## Technical Debt

### 1. Duplicate Widgets in Minimal Schema
**Issue:** 14 widgets listed in multiple groups (103.5% coverage)
**Fix:** Deduplicate in `schema_builder_from_groupings.py`
**Impact:** Low (just data hygiene)

### 2. Hybrid v2 Missing 1 Widget
**Issue:** `DateTimeField48[0]` not in hybrid schema
**Status:** Minimal approach captures it, so not blocking
**Action:** Can ignore if using minimal approach

### 3. Background Bash Processes
**Issue:** Several long-running background processes from testing
**Action:** Kill or let them complete

---

## Next Steps (Prioritized)

### Immediate (This Week)

1. **Kill background processes**
   ```bash
   # Check running processes
   /bashes
   # Kill old test runs
   ```

2. **Archive deprecated files**
   - Move hybrid approach files to `archive/hybrid_v2/`
   - Move old docs to `archive/documentation/`
   - Keep only active minimal approach files

3. **Create round-trip test**
   - Write test that fills schema and exports to PDF
   - Verify all 405 fields appear correctly
   - Document any failures

### Short Term (Next 2 Weeks)

4. **Fix section parsing (17% failures)**
   - Option A: Improve regex for Part E format
   - Option B: Create Gemini tooltip parser for validation
   - Decision depends on round-trip test results

5. **Extract conditional logic**
   - Manual audit of i-589 for all conditionals
   - Design `show_if` schema structure
   - Create Gemini extractor for dependencies

6. **Extract validation constraints**
   - Parse tooltips for constraints
   - Gemini pass for type inference
   - Add to schema with test cases

### Medium Term (Next Month)

7. **Test with second form**
   - Pick different government form
   - Run minimal pipeline
   - Measure quality metrics
   - Identify form-specific patterns

8. **Build constraint validator**
   - Code that checks user input against schema constraints
   - Used by voice AI for real-time validation

9. **Create human review UI**
   - Tool to flag schema issues
   - Easy editing of section labels, constraints, conditionals

### Long Term

10. **Scale to 50+ forms**
11. **Build schema versioning system**
12. **Create automated regression tests**

---

## Quality Metrics That Actually Matter

### Current Metrics (Good for Pipeline Quality)
- ✅ Widget coverage: 100%
- ✅ Type compatibility: 100%
- ✅ Structural consistency: 99.7%

### Missing Metrics (Good for Production Readiness)
- ❌ Round-trip success: Not tested
- ❌ Conditional logic coverage: 0%
- ❌ Validation rule coverage: Unknown
- ❌ Section accuracy: 83%
- ❌ Help text coverage: 0%

### Target for Production
- Round-trip: 100%
- Conditional logic: 100%
- Validation rules: 95%+
- Section accuracy: 100%
- Help text: 80%+

---

## Key Decisions Needed

1. **Section parsing approach?**
   - Improve regex OR add Gemini validation?
   - Cost: Regex = free, Gemini = +1 API call

2. **Conditional logic extraction?**
   - Automated (Gemini) OR manual (human review)?
   - Hybrid approach?

3. **Quality bar for constraints?**
   - 100% required for some forms?
   - Or acceptable to mark "unknown" and let humans fill in?

4. **Testing strategy?**
   - Automated tests for each form?
   - Or manual spot-checks?

---

## Commands for Cleanup

```bash
# Archive old approaches
mkdir -p archive/hybrid_v2
mv gemini_hybrid_extractor.py archive/hybrid_v2/
mv gemini_hybrid_schema.json archive/hybrid_v2/

# Archive old docs
mkdir -p archive/documentation
mv APPROACH_COMPARISON.md archive/documentation/
mv FINAL_SESSION_SUMMARY.md archive/documentation/
mv HYBRID_EXTRACTION_STRATEGY.md archive/documentation/

# Kill background processes if still running
/bashes  # List processes
# Then kill individual ones as needed
```

---

## Questions for Next Session

1. What's the highest priority - round-trip, conditionals, or constraints?
2. Should we create Gemini tooltip parser or fix regex?
3. How many forms do we need to support in V1?
4. What's the timeline for production?
5. Manual review acceptable or must be 100% automated?

---

## Contact/Handoff Notes

**Current schemas:**
- `final_schema_minimal.json` - Use this one (99.9% quality)
- `gemini_hybrid_schema.json` - Don't use (missing sections)

**Key insight:** The minimal approach (Gemini for semantics, Python for precision) achieves same quality as hybrid at 75% lower cost.

**Biggest risk:** Haven't tested round-trip. This is critical path blocker.

**Biggest gap:** Zero conditional logic captured. Forms are unusable for voice AI without this.

**Ready for:** Round-trip testing, conditional logic extraction planning

**Not ready for:** Production deployment to real users
