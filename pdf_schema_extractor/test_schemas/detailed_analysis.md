# Detailed PDF Schema Extraction Analysis

**Date:** October 27, 2025  
**Test Subject:** I-589 Asylum Application Form  
**Extractor Version:** 0.1.0

## Executive Summary

The PDF schema extractor successfully identified the basic structure of the form but has significant differences from the expected output. The main issues are:

1. **Field Count Discrepancy:** 281 fields extracted vs 156 expected (80% more fields than expected)
2. **ID Format Mismatch:** Using PDF internal names instead of semantic IDs
3. **Incomplete Metadata:** Missing critical form identification fields
4. **Field Name Issues:** Using verbose tooltips instead of concise labels

### Overall Match Rate
- ✓ Parts: 7/7 (100%)
- ✓ Sections: 9/9 (100% count, but IDs don't match)
- ✓ Supplements: 2/2 (100%)
- ✗ Fields: 0/156 (0% - no ID matches)
- ✗ Metadata: Partial match

---

## Issue 1: Field ID Generation

### Current Behavior
The extractor generates field IDs by sanitizing the PDF's internal field names:
- `form1__pageSet_Page1_PDF417BarCode1`
- `form1__subform_PtAILine1_ANumber`
- `form1__subform_TextField1`

### Expected Behavior
Field IDs should be semantic and human-readable:
- `part_a_i_a_number`
- `part_a_i_ssn`
- `part_a_i_last_name`

### Root Cause
The extractor uses this logic (line ~152 in extractor.py):
```python
clean_id = re.sub(r'\[\d+\]', '', field.field_name)
clean_id = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_id)
clean_id = clean_id.strip('_')
```

This sanitizes the PDF's internal field name rather than generating a semantic ID.

### Recommended Fix
Create a field ID mapping strategy:
1. Parse the field's label/tooltip text
2. Extract key information (part, section, field purpose)
3. Generate semantic ID based on:
   - Section context (e.g., `part_a_i`)
   - Field purpose extracted from label
   - Field type if needed for disambiguation

**Example Implementation:**
```python
def generate_semantic_field_id(field, section_id, field_label):
    """Generate semantic field ID from context."""
    # Remove "Part A.I. Information About You." prefix
    # Extract key terms like "Alien Registration Number"
    # Convert to snake_case: "a_number"
    # Combine: section_id + "_" + field_key
    # Result: "part_a_i_a_number"
    pass
```

---

## Issue 2: Section ID Generation

### Current Behavior
Sections get sequential numeric IDs:
- `section_1`, `section_2`, `section_3`, etc.

### Expected Behavior
Semantic IDs based on form structure:
- `part_a_i`, `part_a_ii`, `part_a_iii`
- `part_b_questions`
- `part_c_questions`
- `part_d_signature`

### Root Cause
The extractor generates IDs with a simple counter (line ~61):
```python
section_id = f"section_{section_order}"
```

### Recommended Fix
Parse the section label to extract:
- Part designation (A, B, C, etc.)
- Roman numeral subsection (I, II, III)
- Or semantic name from the label

**Example Implementation:**
```python
def generate_semantic_section_id(section_label):
    """Generate semantic section ID from label."""
    # "Part A.I. Information About You" -> "part_a_i"
    # "Part B: Information About Your Application" -> "part_b_questions"
    # "Part D: Your Signature" -> "part_d_signature"
    
    label_lower = section_label.lower()
    
    # Extract part letter and roman numeral if present
    match = re.match(r'part ([a-g])(\.([ivx]+))?', label_lower)
    if match:
        part = match.group(1)
        subsection = match.group(3) if match.group(3) else ""
        
        # Convert roman numerals: i->i, ii->ii, iii->iii
        if subsection:
            return f"part_{part}_{subsection}"
        
        # Use semantic suffix based on label content
        if "signature" in label_lower:
            return f"part_{part}_signature"
        elif "question" in label_lower or "application" in label_lower:
            return f"part_{part}_questions"
        # etc.
    
    return f"part_{part}"
```

---

## Issue 3: Field Name Extraction

### Current Behavior
Field names use the complete tooltip text from the PDF:
```
"Part. A. 1. Information About You. 1. Enter Alien Registration Number (A. Number), if any."
"Part. A. 1. Information About You. 2. Enter U. S. Social Security Number, if any."
```

### Expected Behavior
Concise, meaningful field names:
```
"Alien Registration Number(s) (A-Number)"
"U.S. Social Security Number"
```

### Impact
- Long field names are verbose and include section context unnecessarily
- The section context is already captured in `section_id` and `section_label`
- Makes the schema harder to read and use

### Recommended Fix
Extract the actual field purpose from the tooltip:
1. Remove section prefix (e.g., "Part. A. 1. Information About You.")
2. Remove instruction verbs (e.g., "Enter", "Provide")
3. Keep the core field descriptor

**Example Implementation:**
```python
def clean_field_name(tooltip_text):
    """Extract clean field name from PDF tooltip."""
    # Remove part/section prefix
    text = re.sub(r'^Part\. [A-G]\. \d+\.\s+.*?\.\s+\d+\.\s+', '', tooltip_text)
    
    # Remove instruction verbs
    text = re.sub(r'^(Enter|Provide|List|Specify)\s+', '', text, flags=re.IGNORECASE)
    
    # Clean up extra punctuation
    text = text.strip('. ')
    
    return text
```

---

## Issue 4: Field Count Discrepancy

### Analysis
- **Extracted:** 281 fields
- **Expected:** 156 fields
- **Difference:** +125 fields (81% more)

### Likely Causes

#### A. Including Non-Form Fields
The extractor may be capturing:
- Barcode fields (`PDF417BarCode1`)
- Hidden calculation fields
- Duplicate fields across pages
- Internal form management fields

**Evidence:**
```json
{
  "id": "form1__pageSet_Page1_PDF417BarCode1",
  "name": "PDF417BarCode1",
  "type": "text"
}
```

#### B. Not Grouping Related Fields
The expected schema groups related fields into:
- **Tables** (e.g., `part_a_i_us_entries` with columns)
- **Multi-entry fields** (e.g., children information)
- **Radio button groups** (multiple radio buttons as one field with options)

The extractor currently creates separate fields for each form widget.

#### C. Including Auto-Generated Fields
Each extracted field has `"auto_fill_na": false` which doesn't appear in the expected schema, suggesting these may be implementation-specific fields.

### Recommended Fixes

1. **Filter Non-User Fields:**
   ```python
   # Skip barcode fields
   if "barcode" in field.field_name.lower():
       continue
   
   # Skip hidden/calculation fields
   if field.field_flags & FIELD_FLAG_HIDDEN:
       continue
   ```

2. **Group Table Fields:**
   - Detect repeating field patterns (same names with row numbers)
   - Create single `table` type field with columns definition
   - Example: Multiple "Child Name" fields → single table with name column

3. **Group Radio Buttons:**
   - Already partially implemented in the code (lines ~181-223)
   - Verify it's working correctly
   - Check if radio button grouping is incomplete

---

## Issue 5: Metadata Extraction

### Current Output
```json
{
  "title": "Form I-589, Application for Asylum and for Withholding of Removal",
  "version": "1.0",
  "language": "en",
  "page_count": 12
}
```

### Expected Output
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

### Missing Fields
- `form_number`: Should extract "I-589" from title or form
- `edition_date`: Form revision date
- `expiration_date`: When form expires
- `omb_number`: Office of Management and Budget control number
- `agency`: Issuing agency

### Recommended Fix

These fields typically appear:
- In PDF metadata
- On the first page header/footer
- In small print at bottom of pages

**Implementation:**
```python
def extract_form_metadata(doc):
    """Extract comprehensive form metadata."""
    metadata = doc.metadata
    first_page = doc[0]
    text = first_page.get_text()
    
    # Extract form number from title or text
    form_number = None
    title = metadata.get("title", "")
    match = re.search(r'(I-\d+)', title or text)
    if match:
        form_number = match.group(1)
    
    # Extract OMB number
    omb_match = re.search(r'OMB No\.\s+(\d+-\d+)', text)
    omb_number = omb_match.group(1) if omb_match else None
    
    # Extract dates (often in footer)
    # Edition Date: MM/DD/YYYY format
    # Expiration Date: MM/DD/YYYY format
    
    return FormMetadata(
        title=clean_title(title),
        form_number=form_number,
        edition_date=edition_date,
        expiration_date=expiration_date,
        omb_number=omb_number,
        agency=extract_agency(text),
        page_count=doc.page_count,
        language="en"
    )
```

---

## Issue 6: Missing Field Attributes

### Current Field Structure
```json
{
  "id": "form1__subform_PtAILine1_ANumber",
  "name": "Part. A. 1. ...",
  "spoken_name": "Part. A. 1. ...",
  "type": "text",
  "section_id": "section_1",
  "section_label": "Part A.I. Information About You",
  "pdf_position": {...},
  "pdf_field_name": "...",
  "auto_fill_na": false
}
```

### Expected Field Structure
```json
{
  "id": "part_a_i_a_number",
  "name": "Alien Registration Number(s) (A-Number)",
  "spoken_name": "A-Number",
  "type": "text",
  "section_id": "part_a_i",
  "help": {
    "inline": "(if any)"
  },
  "validation": {
    "required": false,
    "format_preset": "a_number"
  },
  "pdf_field_name": "PtAILine1_ANumber[0]"
}
```

### Missing Attributes

1. **`help.inline`**: Parenthetical help text like "(if any)"
2. **`validation.required`**: Whether field is required
3. **`validation.format_preset`**: Expected format (ssn, a_number, zip, etc.)
4. **`validation.date_constraint`**: For date fields (past_only, future_only)
5. **`format`**: For date fields (mm/dd/yyyy)
6. **`options`**: Detailed structure for radio/select fields
7. **`spoken_name`**: Concise name for voice interaction

### Extraction Challenges

These attributes require:
- **Help text**: Parse from field tooltips (parenthetical content)
- **Required status**: PDF form field flags or visual indicators (asterisks)
- **Format presets**: Infer from field name or validate against pattern
- **Options**: For radio/select, extract all choices with labels

### Recommended Implementation

```python
def extract_field_attributes(field, field_label):
    """Extract additional field attributes."""
    attributes = {}
    
    # Extract help text from parentheses
    help_match = re.search(r'\(([^)]+)\)', field_label)
    if help_match:
        attributes['help'] = {'inline': help_match.group(1)}
    
    # Infer validation based on field name
    validation = {'required': False}  # Default, could check PDF flags
    
    name_lower = field_label.lower()
    if 'social security' in name_lower or 'ssn' in name_lower:
        validation['format_preset'] = 'ssn'
    elif 'a-number' in name_lower or 'alien registration' in name_lower:
        validation['format_preset'] = 'a_number'
    elif 'zip' in name_lower:
        validation['format_preset'] = 'zip'
    
    if validation:
        attributes['validation'] = validation
    
    # Generate spoken name (concise version)
    spoken_name = generate_spoken_name(field_label)
    attributes['spoken_name'] = spoken_name
    
    return attributes
```

---

## Issue 7: Section Page Numbers

### Current Behavior
Sections store a single `page_number`:
```json
{
  "id": "section_1",
  "label": "Part A.I. Information About You",
  "order": 1,
  "page_number": 1
}
```

### Expected Behavior
Sections can span multiple pages and should track all of them:
```json
{
  "id": "part_a_ii",
  "label": "Part A.II: Information About Your Spouse and Children",
  "order": 2,
  "page_numbers": [2, 3]
}
```

### Impact
- Can't properly navigate multi-page sections
- Can't determine section boundaries accurately

### Recommended Fix
```python
# Track all pages where section fields appear
section_pages = defaultdict(set)

for field in fields:
    section_pages[field.section_id].add(field.pdf_position.page)

# When creating sections
for section_data in all_sections_temp:
    pages = sorted(section_pages[section_data["id"]])
    section_data["page_numbers"] = pages
```

---

## Issue 8: Radio Button Grouping

### Current Implementation
Lines 181-223 in `extractor.py` include radio button grouping logic, but there's an issue:

```python
from .models import (
    # ...
    GroupKind,  # ← This import is missing!
)
```

The code references `GroupKind.RADIO` but `GroupKind` is not imported from models.

### Error Impact
The radio button grouping code will fail at runtime with:
```
NameError: name 'GroupKind' is not defined
```

### Recommended Fix
1. Add `GroupKind` to the imports from models
2. Verify `GroupKind` enum exists in `models.py`
3. Test radio button grouping functionality

---

## Priority Recommendations

### Critical (Must Fix)
1. **Field ID Generation** - Implement semantic ID generation
2. **Section ID Generation** - Parse labels to create semantic IDs
3. **Field Name Cleaning** - Remove section prefixes and instructions
4. **Fix GroupKind Import** - Add missing import to prevent runtime errors

### High Priority (Should Fix)
5. **Filter Non-User Fields** - Remove barcodes and internal fields
6. **Metadata Extraction** - Extract form_number, OMB, dates, agency
7. **Help Text Extraction** - Parse parenthetical help from tooltips
8. **Spoken Name Generation** - Create concise voice-friendly names

### Medium Priority (Good to Have)
9. **Validation Rules** - Infer format presets and requirements
10. **Section Page Numbers** - Track all pages for each section
11. **Table Field Grouping** - Detect and group repeating field patterns
12. **Field Type Refinement** - Distinguish text/textarea, add tel type

### Low Priority (Nice to Have)
13. **Supplement Metadata** - Add trigger_condition and page_number
14. **Date Format Specification** - Add format strings for date fields
15. **Option Details** - Enhance radio/select options with spoken_label

---

## Testing Recommendations

### Unit Tests Needed
1. **Test Semantic ID Generation**
   - Input: Various field labels and section contexts
   - Output: Correct semantic IDs

2. **Test Field Name Cleaning**
   - Input: Raw tooltip text
   - Output: Clean field names

3. **Test Section ID Parsing**
   - Input: Section labels
   - Output: Semantic section IDs

4. **Test Field Filtering**
   - Input: All PDF fields
   - Output: Only user-facing fields

### Integration Tests
1. **Full I-589 Extraction**
   - Extract complete form
   - Compare field count (should be ~156)
   - Validate all IDs match expected format

2. **Field Attribute Completeness**
   - Check all fields have required attributes
   - Verify validation rules are present where expected
   - Confirm help text extraction

### Regression Tests
1. **Multi-page Sections**
   - Verify sections spanning multiple pages
   - Check page_numbers array is correct

2. **Radio Button Groups**
   - Confirm multiple radio buttons become single field
   - Verify options array is populated

3. **Table Detection**
   - Test repeating field pattern recognition
   - Validate table column generation

---

## Code Quality Observations

### Positive Aspects
- Good use of Pydantic models for type safety
- Proper section detection heuristics
- Consolidated section handling to avoid duplicates
- Attempt to group radio buttons

### Areas for Improvement
- Missing imports (GroupKind)
- Hardcoded paths in `__main__` block
- Long function (extract_schema) should be broken into smaller functions
- Limited error handling for malformed PDFs
- No logging for debugging extraction issues

### Suggested Refactoring
```python
# Break extract_schema into focused functions:
def extract_schema(pdf_path: str) -> FormSchema:
    doc = fitz.open(pdf_path)
    
    metadata = extract_form_metadata(doc)
    sections = identify_sections(doc)
    raw_fields = extract_pdf_fields(doc, sections)
    fields = process_fields(raw_fields)  # Filter, group, clean
    parts = organize_parts(sections)
    supplements = identify_supplements(sections, fields)
    extraction_info = create_extraction_info()
    
    return FormSchema(...)
```

---

## Conclusion

The PDF schema extractor has a solid foundation but needs significant refinements to match the expected output format. The main issues are:

1. **ID Generation**: Complete overhaul needed for both fields and sections
2. **Field Processing**: Need filtering, grouping, and better name extraction
3. **Metadata**: Missing critical form identification fields
4. **Attributes**: Need to extract help text, validation, and other metadata

**Estimated Effort:**
- Critical fixes: 8-12 hours
- High priority: 6-8 hours
- Medium priority: 4-6 hours
- Total: 18-26 hours of development work

**Risk Assessment:**
- Low risk: Section/field ID generation (straightforward logic)
- Medium risk: Field grouping and table detection (complex patterns)
- High risk: Metadata extraction (varies by PDF format)

The extractor should be tested with multiple PDF forms to ensure generalization beyond the I-589 form.
