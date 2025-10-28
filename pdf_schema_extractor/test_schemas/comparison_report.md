# PDF Schema Extraction Comparison Report

Generated: compare_schemas.py

## Summary

### Counts

**parts_count:**
- Extracted: 7
- Expected: 7
- Match: ✓

**sections_count:**
- Extracted: 9
- Expected: 9
- Match: ✓

**supplements_count:**
- Extracted: 2
- Expected: 2
- Match: ✓

**fields_count:**
- Extracted: 281
- Expected: 156
- Match: ✗

## Metadata Differences

### Metadata mismatch

**Extracted:**
```json
{
  "title": "Form I-589, Application for Asylum and for Withholding of Removal",
  "version": "1.0",
  "language": "en",
  "page_count": 12
}
```

**Expected:**
```json
{
  "title": "Application for Asylum and for Withholding of Removal",
  "form_number": "I-589",
  "edition_date": "2025-01-20",
  "expiration_date": "2027-09-30",
  "omb_number": "1615-0067",
  "page_count": 12,
  "agency": "U.S. Citizenship and Immigration Services",
  "language": "en"
}
```

## Sections Differences

### Missing sections

- `part_b_questions`
- `part_c_questions`
- `part_a_ii`
- `part_g_hearing`
- `part_e_declaration`
- `part_d_signature`
- `part_a_iii`
- `part_f_interview`
- `part_a_i`

### Extra sections

- `section_11`
- `section_1`
- `section_10`
- `section_12`
- `section_7`
- `section_4`
- `section_9`
- `section_2`
- `section_5`

## Fields Differences

### Missing fields

**Count:** 156

**Sample IDs:**
- `supplement_b_a_number`
- `part_g_oath_language_other`
- `part_a_i_ssn`
- `part_a_i_first_name`
- `part_a_ii_spouse_first_name`
- `part_b_q1a_past_harm`
- `part_g_immigration_judge_signature`
- `part_a_i_religion`
- `part_a_i_a_number`
- `part_a_i_mailing_apt_number`

### Extra fields

**Count:** 281

**Sample IDs:**
- `form1__subform_DateTimeField43`
- `form1__subform_ckboxyn2`
- `form1__subform_DateTimeField44`
- `form1__subform_CheckBox31`
- `form1__subform_PtE_State`
- `form1__subform_NotMarried_PtAIILine23_PreviousArrivalDate`
- `form1__subform_DateTimeField25`
- `form1__subform_PtAIILine17_StatusofLastAdmission`
- `form1__subform_SuppALine20_CheckBox2`
- `form1__subform_PtAIILine21_No`

## Required Changes to Extractor

Based on the differences above, the following changes are needed:

### 1. Field ID Generation
- **Issue:** Field IDs don't match expected format
- **Current:** Using sanitized PDF field names (e.g., `form1__subform_PtAILine1_ANumber`)
- **Expected:** Using semantic IDs (e.g., `part_a_i_a_number`)
- **Fix:** Implement semantic field ID generation based on field labels and context

### 2. Section IDs
- **Issue:** Section IDs use generic numbering
- **Current:** `section_1`, `section_2`, etc.
- **Expected:** Semantic IDs like `part_a_i`, `part_a_ii`, etc.
- **Fix:** Parse section labels to generate semantic section IDs

### 3. Field Attributes
- **Issue:** Missing or incorrect field attributes
- **Missing:** `spoken_name`, `help`, `validation`, `options` details
- **Fix:** Need to extract field tooltips, help text, and validation rules from PDF

### 4. Form Metadata
- **Issue:** Incomplete metadata extraction
- **Missing:** `form_number`, `edition_date`, `expiration_date`, `omb_number`, `agency`
- **Fix:** Extract these from PDF metadata or first page text

### 5. Section Structure
- **Issue:** Section hierarchy and page numbers
- **Missing:** Proper `page_numbers` arrays, section nesting
- **Fix:** Track all pages a section appears on, not just the first

### 6. Field Types
- **Issue:** Type inference may be incomplete
- **Fix:** Verify all field types are correctly identified (text, checkbox, radio, select, date, tel, signature, textarea, table)

### 7. Supplement Structure
- **Issue:** Supplements may not have all required fields
- **Missing:** `trigger_condition`, `page_number`, detailed `purpose`
- **Fix:** Add these metadata fields to supplement extraction

## Priority Actions

1. **High Priority:**
   - Fix field ID generation (semantic vs. PDF field names)
   - Fix section ID generation
   - Extract complete form metadata

2. **Medium Priority:**
   - Add field `spoken_name` extraction from tooltips
   - Add `help` text extraction
   - Improve validation rules extraction

3. **Low Priority:**
   - Add supplement trigger conditions
   - Refine section page tracking
   - Add field options for radio/select fields