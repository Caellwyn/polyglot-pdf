# Development Journal — 2025-10-28 (Heuristic Branch)

## Branch: claude/session-011CUaHiv5h66fu5oTHR7S2a

## Table of Contents

1. [Session Summary](#session-summary)
2. [Changes Made](#changes-made)
3. [Current State](#current-state)
4. [Issues Identified](#issues-identified)
5. [If Returning to This Branch](#if-returning-to-this-branch)
6. [Key Files Modified](#key-files-modified)

## Session Summary

**Goal**: Remove all "cheating" code that was using ground truth schema hints to guide extraction. Create a pure heuristic-based extractor that can work on any PDF without pre-existing schema knowledge.

**Decision**: After implementing pure heuristics, we decided to pivot to a Gemini-based approach instead, as Gemini excels at PDF analysis and can infer field types more reliably than heuristics alone.

**Status**: Branch frozen. Switching to new branch for Gemini integration.

## Changes Made

### 1. Removed Expected Schema Hints (extractor.py)

**Deleted lines 38-80**: Removed code that loaded curated schema from `i589_schema.json`
```python
# REMOVED:
_EXPECTED_SCHEMA_PATH = Path(__file__).resolve().parent / "test_schemas" / "test_pdfs" / "i589_schema.json"
_EXPECTED_FIELD_DEFS_BY_ID: Dict[str, Dict] = {}
_EXPECTED_PDF_TO_OPTION: Dict[str, Dict] = {}
_EXPECTED_TABLE_DEFS_BY_SECTION: Dict[str, List[Dict[str, Any]]] = {}
# ... loading logic
```

### 2. Deleted Functions Using Expected Schema

**Removed from extractor.py**:
- `_build_field_from_expected()` - Built fields from curated schema definitions
- `_group_checkbox_fields()` - Grouped checkboxes using expected metadata
- `_apply_expected_overrides()` - Applied schema hints to override field properties
- `_build_table_field()` - Built table fields from expected definitions
- `_apply_expected_tables()` - Applied pre-defined table structures

**Simplified**:
- `_group_radio_fields()` - Now uses only heuristic clustering by pdf_field_name

### 3. Updated Table Detection (table_detection.py)

**Changes**:
- Removed `expected_tables` parameter from `consolidate_tables()`
- Removed global `_EXPECTED_TABLES_BY_SECTION` variable
- Updated `_is_supported_section()` to use pattern matching instead of expected table lookup
- Simplified `_detect_tables_in_section()` to use pure heuristics
- Updated `_build_table_from_columns()` to remove expected table matching
- Simplified `_infer_table_metadata()` to use only heuristic patterns
- Simplified `_build_multi_entry_config()` to use only section-based rules

### 4. Created Comparison Tool

**New file**: `compare_extraction.py`
- Compares extracted schema with ground truth
- Reports field counts by type and section
- Lists table detection results
- Shows radio/checkbox grouping stats

## Current State

### Extraction Metrics

**Overall**:
- Raw PDF fields: **448**
- After heuristic extraction: **276 fields**
- Ground truth target: **170 fields**
- Gap: **+106 fields** (need better consolidation)

### Field Type Distribution

| Type | Ground Truth | Extracted | Difference |
|------|--------------|-----------|------------|
| text | 71 | 185 | +114 |
| checkbox | 16 | 86 | +70 |
| table | 10 | 5 | -5 |
| radio | 26 | 0 | -26 |
| date | 15 | 0 | -15 |
| textarea | 13 | 0 | -13 |
| signature | 7 | 0 | -7 |
| select | 3 | 0 | -3 |
| tel | 3 | 0 | -3 |
| email | 1 | 0 | -1 |
| number | 1 | 0 | -1 |

### Section-Level Breakdown

| Section | Ground Truth | Extracted | Difference |
|---------|--------------|-----------|------------|
| part_a_i | 40 | 58 | +18 |
| part_a_ii | 30 | 38 | +8 |
| part_a_iii | 5 | 31 | +26 |
| part_b_questions | 18 | 24 | +6 |
| part_c_questions | 13 | 20 | +7 |
| part_d_signature | 9 | 14 | +5 |
| part_e_declaration | 17 | 12 | -5 |
| part_f_interview | 16 | 8 | -8 |
| part_g_hearing | 12 | 8 | -4 |
| supplement_a_section | 5 | 56 | +51 |
| supplement_b_section | 5 | 7 | +2 |

### Table Detection Results

**Successfully Detected** (1/10):
- ✅ `part_a_ii_children_table` (22 cols × 4 rows) - **Perfect match!**

**Partially Detected** (4 tables in Part A.III with incorrect IDs):
- ❌ `part_a_iii_table` (4 cols × 2 rows) - needs proper ID
- ❌ `part_a_iii_table` (4 cols × 5 rows) - needs proper ID
- ❌ `part_a_iii_table` (4 cols × 4 rows) - needs proper ID
- ❌ `part_a_iii_table` (3 cols × 3 rows) - needs proper ID

**Missing** (5/10):
- ❌ `part_a_i_us_entries` (4 cols × 3 rows)
- ❌ `part_a_iii_last_address_abroad` (6 cols × 1 row)
- ❌ `part_d_family_assisted_details` (2 cols × 2 rows)
- ❌ `supplement_a_children_table` (22 cols × 4 rows)
- ❌ `supplement_b_continuation_table` (3 cols × 3 rows)

## Issues Identified

### 1. Field Type Inference Broken

**Problem**: All fields are being classified as "text" or "checkbox"
- No date fields detected (should be 15)
- No email fields detected (should be 1)
- No telephone fields detected (should be 3)
- No signature fields detected (should be 7)
- No textarea fields detected (should be 13)
- No number fields detected (should be 1)
- No select dropdowns detected (should be 3)

**Root Cause**: PDF widgets don't carry semantic type information. The PDF only knows:
- Text field (all text inputs, dates, emails, tel, textareas look the same)
- Checkbox
- Radio button
- Combobox/Listbox
- Signature field

**Solution Options**:
1. **Heuristic approach**: Infer types from field names/labels
   - "date" or "birth" → date field
   - "email" → email field
   - "phone" or "tel" → tel field
   - Large height → textarea
   - Signature widget type → signature
2. **Gemini approach**: Send PDF page images + field data to Gemini, ask it to classify types

### 2. Radio Button Grouping Not Working

**Problem**: 0 radio groups detected vs 26 in ground truth

**Root Cause**: `_group_radio_fields()` is working, but there are no radio buttons being created in the first place. The PDF extraction is classifying these as checkboxes instead.

**Example from ground truth**:
- "Sex" field should be radio with Male/Female options
- "In U.S.?" fields should be radio with Yes/No options
- Instead being detected as individual checkboxes

**Solution**: Better widget type detection or post-processing to convert checkbox groups to radio groups based on patterns.

### 3. Checkbox Explosion

**Problem**: 86 checkbox fields vs 16 in ground truth

**Excess**: +70 checkboxes that should be grouped

**Examples of what should be grouped**:
- Yes/No checkbox pairs → radio groups
- Male/Female checkbox pairs → radio groups
- Multiple related checkboxes → checkbox groups

**Solution**: Implement spatial/naming-based clustering to identify checkbox groups, then convert to appropriate field types.

### 4. Table Detection Gaps

**Problem**: Only 5 tables detected vs 10 in ground truth

**Specific Issues**:
- Part A.I: US entries table not detected (should be 4 cols × 3 rows)
- Part A.III: 4 tables detected but all have generic ID "part_a_iii_table"
  - Need proper IDs: education_history, employment_history, residences_last_5_years, last_address_abroad
- Part D: family_assisted_details not detected (2 cols × 2 rows)
- Supplements: Missing children table and continuation table

**Root Cause**:
- Minimum column threshold (3) might be too high for small tables
- Table ID inference needs better heuristics
- Need to detect 1-row tables (last_address_abroad)

### 5. PDF Field Name Preservation

**Critical Requirement**: We MUST preserve original PDF field names for round-trip filling.

**Current Status**: ✅ Working correctly
- Each field has `pdf_field_name` attribute with original PDF widget name
- Example: `PtAILine1_ANumber[0]`, `ChildAlien1`, etc.

**When writing values back to PDF**:
```python
field = form_schema.get_field("part_a_i_a_number")
pdf_field_name = field.pdf_field_name  # "PtAILine1_ANumber[0]"
# Use pdf_field_name to write value back to PDF widget
```

## If Returning to This Branch

### Priority 1: Fix Field Type Inference

**Approach**: Add heuristic rules to `extract_schema()` function

```python
def infer_field_type(widget, field_label):
    """Infer semantic field type from PDF widget and label."""
    label_lower = field_label.lower()

    # Signature fields
    if widget.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
        return FieldType.SIGNATURE

    # Date fields
    if any(keyword in label_lower for keyword in ['date', 'birth', 'dob', 'expiration']):
        return FieldType.DATE

    # Email fields
    if 'email' in label_lower:
        return FieldType.EMAIL

    # Phone/Tel fields
    if any(keyword in label_lower for keyword in ['phone', 'telephone', 'tel']):
        return FieldType.TEL

    # Number fields
    if 'number' in label_lower and 'phone' not in label_lower:
        # Could be A-Number, SSN, I-94, etc.
        return FieldType.NUMBER

    # Textarea vs Text (use widget height)
    if widget.field_type == fitz.PDF_WIDGET_TYPE_TEXT:
        if widget.rect.height > 50:  # Tall fields are textareas
            return FieldType.TEXTAREA
        return FieldType.TEXT

    # Select dropdowns
    if widget.field_type in (fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX):
        return FieldType.SELECT

    # Checkboxes and radios
    if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
        return FieldType.CHECKBOX
    if widget.field_type == fitz.PDF_WIDGET_TYPE_RADIO:
        return FieldType.RADIO

    return FieldType.TEXT  # Default fallback
```

### Priority 2: Implement Checkbox/Radio Grouping

**Strategy**: After extraction, cluster checkboxes by:
1. Spatial proximity (same Y coordinate ± tolerance)
2. Naming patterns (e.g., `Checkbox_Sex_Male`, `Checkbox_Sex_Female`)
3. Label similarity (e.g., both labeled "Sex. Select Male" and "Sex. Select Female")

**When to convert to radio**:
- Exactly 2 checkboxes with labels containing Yes/No
- Exactly 2 checkboxes with labels containing Male/Female
- Field names suggest mutual exclusivity

### Priority 3: Improve Table Detection

**Issues to fix**:
1. Lower minimum column threshold from 3 to 2 for small tables
2. Add better table ID inference based on column content
3. Detect single-row tables
4. Handle supplement tables separately

**Example enhancement**:
```python
def _infer_table_id(section_id, columns):
    """Infer specific table ID based on column content."""
    column_labels = [col.label.lower() for col in columns]

    if section_id == "part_a_iii":
        if any("education" in label for label in column_labels):
            return "part_a_iii_education_history"
        if any("employer" in label or "occupation" in label for label in column_labels):
            return "part_a_iii_employment_history"
        if any("address" in label for label in column_labels):
            if any("residence" in label for label in column_labels):
                return "part_a_iii_residences_last_5_years"
            else:
                return "part_a_iii_last_address_abroad"
        if any("family" in label or "spouse" in label for label in column_labels):
            return "part_a_iii_family_info"

    # ... more heuristics
    return f"{section_id}_table"  # Fallback
```

## Key Files Modified

### Modified Files

1. **pdf_schema_extractor/extractor.py**
   - Removed: Lines 38-80 (expected schema loading)
   - Removed: `_build_field_from_expected()`, `_group_checkbox_fields()`, `_apply_expected_overrides()`, `_build_table_field()`, `_apply_expected_tables()`
   - Modified: `_group_radio_fields()` - simplified to pure heuristics
   - Modified: `extract_schema()` - removed calls to deleted functions

2. **pdf_schema_extractor/table_detection.py**
   - Modified: `_is_supported_section()` - pattern-based instead of expected table lookup
   - Modified: `consolidate_tables()` - removed expected_tables parameter
   - Modified: `_detect_tables_in_section()` - pure heuristic detection
   - Modified: `_build_table_from_columns()` - removed expected table matching
   - Modified: `_infer_table_metadata()` - pure heuristic inference
   - Modified: `_build_multi_entry_config()` - section-based rules only

### New Files

1. **compare_extraction.py**
   - Comprehensive comparison tool
   - Shows field counts, types, sections, tables
   - Useful for debugging extraction quality

### Test Files

1. **test_extraction.py** (existing)
   - Runs extraction on i-589.pdf
   - Outputs to `pdf_schema_extractor/test_schemas/extracted_schema.json`

## Testing

**Run extraction**:
```bash
python3 test_extraction.py
```

**Compare with ground truth**:
```bash
python3 compare_extraction.py
```

**Expected output**:
- 276 fields extracted
- 5 tables detected
- Field type issues evident in comparison

## Notes

- The heuristic approach is viable but requires extensive rule engineering
- Gemini can likely infer field types more accurately than pattern matching
- PDF widgets have limited semantic information - labels are the best source
- Original PDF field names are correctly preserved for round-trip filling
- Children table detection works perfectly - good foundation to build on

## Next Branch: Gemini Integration

Switching to new branch to explore Gemini-based extraction:
- Use Gemini to infer field types from PDF pages
- Use Gemini to validate/refine table structures
- Build verifier to ensure Gemini output aligns with actual PDF widgets
- Hybrid approach: heuristics for structure, Gemini for semantics
