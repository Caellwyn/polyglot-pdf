# I-90 Schema Fixes Required

**Date:** October 31, 2025
**Source:** Manual review of i-90_filled_v4_gemini_test.pdf
**Status:** Issues identified, systematic fixes needed

---

## Issue Categories

### 1. PDF Field Flag Manipulation (CRITICAL)
**Problem:** Schema identifies conditionals, but PDF field flags need to be mutated to unlock fields.

#### Fields Requiring READ_ONLY Bit Flip (Bit 0)
- **Part 1 Q5a, Q5b, Q5c** - Should unlock when Q4 = 'yes'
  - Currently: `read_only = True` (bit 0 set)
  - Fix: Flip bit 0 to `False` when Q4 is answered 'yes'
  - Schema has conditional logic, but PDF isn't modified

- **Part 2 Q2** - Should unlock when Q1a selected
  - Currently: `read_only = True` (bit 0 set)
  - Fix: Flip bit 0 to `False` when Q1a is selected
  - Complex conditional tree (see instruction PDF)

**Solution Needed:** Create PDF field flag mutator that:
- Reads conditional logic from schema
- Modifies source PDF field flags before filling
- Creates "unlocked" version of PDF for conditional fields

---

### 2. Dropdown Fields Not Filling

#### State Dropdowns (Type: select)
**Issue:** Round-trip tester generates test data but doesn't fill dropdowns

Affected fields:
- **P1 Q6e** - Mailing address state
- **P1 Q7d** - Physical address state (if different)
- **P6 Q3d** - Interpreter address state
- **P7 Q3d** - Preparer address state

**Current Status:**
- Schema correctly identifies as `type: select`
- Gemini correctly changed from `radio` → `select`
- Round-trip tester doesn't handle select fields

**Fix Required:**
- Update `round_trip_tester.py` to handle field type 4 (select/dropdown)
- Generate appropriate test value (e.g., "CA", "NY")
- Set dropdown value using PyMuPDF select API

#### Height Dropdowns
- **P3 Q8 Feet** - Should be dropdown (0-7 feet)
- **P3 Q8 Inches** - Should be dropdown (0-11 inches)

**Current Status:** Schema says `select`, but not filling

---

### 3. Validation Rules Not Enforcing

#### Max Length Not Enforcing
**Issue:** Fields accept more/fewer digits than allowed

Affected fields:
- **P1 Q2** - USCIS Online Account (should be exactly 12 digits)
  - Currently accepting fewer digits
  - Schema has `max_length: 12` but not validated

- **P2 Q2** - Receipt/case number (12 digits)
  - Schema has validation rule, but not enforced

**Fix Required:**
- Round-trip tester should generate exact length
- Add validation in test data generation
- Enforce max_length in schema

#### Numeric-Only Validation
**Issue:** ZIP codes and numeric fields not validating as numeric

Affected fields:
- **P1 Q6f** - ZIP code (5 digits, numeric)
- **P1 Q7e** - ZIP code (5 digits, numeric)
- **P7 Q3e** - ZIP code (5 digits, numeric)

**Current Status:**
- Schema has validation: `pattern: ^\d{5}$`
- Round-trip tester generates "11111" but doesn't validate
- Need to enforce numeric-only

**Fix Required:**
- Add validation check in round-trip tester
- Generate data matching validation pattern
- Verify numeric-only in output

#### Phone Number Validation
Affected fields:
- P5 Q3, Q4, Q5 (10 digits)
- P6 Q4, Q5, Q6 (10 digits)
- P7 Q4, Q5, Q6 (10 digits)

**Current Status:**
- Schema has validation: `pattern: ^\(\d{3}\) \d{3}-\d{4}$`
- max_length set to 10 or 13
- Need to generate properly formatted test data

---

### 4. Field Type Corrections Still Needed

#### Checkbox → Radio Conversions
**Issue:** Fields labeled "Select only one box" are still checkboxes

**Pattern to detect:** Tooltip contains "select only one" or "select one box"

Affected fields (from manual review):
- **Part 3**: Multiple Yes/No questions say "select only one"
  - P3 Q3, Q5, Q6, Q7, Q10, Q11
  - Gemini may have missed some

- **Part 4 Q1** - Accommodation type (select only one)

- **Part 6 Q3b** - Apt/Ste/Flr (already consolidated, verify radio)

- **Part 7 Q3b** - Apt/Ste/Flr (already consolidated, verify radio)

**Fix Required:**
- Add pattern detection: "select only one" or "select one box" in tooltips
- Auto-convert checkbox → radio for these patterns
- Re-run on widget inventory before schema building

---

### 5. Date Fields Not Filling

#### Part 7 Q8b
**Issue:** Date field not filling in round-trip test

**Current Status:**
- Schema type: `date` (correctly identified)
- Validation: `MM/DD/YYYY` pattern
- Round-trip tester not generating/filling date fields

**Fix Required:**
- Add date field handling in round-trip tester (field_type check)
- Generate test date: "01/01/2000"
- Verify PyMuPDF can set date field values

**Other date fields to verify:**
- P1 Q9 - Date of birth
- P1 Q15 - Date of admission

---

### 6. Group Consolidation Issues

#### Part 7 Q7a + Q7b
**Issue:** Should be single radio group (Yes/No for attorney status)

**Current Status:**
- Gemini identified as separate radio fields
- Should be consolidated into one group with 2 options

**Fix Required:**
- Manually consolidate in schema fixer
- Pattern: "p7_checkbox7" and "p7_checkbox7extend" → single radio group
- Similar to Apt/Ste/Flr consolidation logic

---

## Systematic Fix Plan

### Phase 1: Round-Trip Tester Improvements
**File:** `round_trip_tester.py`

1. **Add dropdown/select support**
   ```python
   elif widget.field_type == 4:  # Select/dropdown
       # Generate appropriate value from options
       # Set using widget APIs for dropdowns
   ```

2. **Add date field support**
   ```python
   if field.get('type') == 'date':
       test_data[pdf_name] = "01/01/2000"
   ```

3. **Enforce validation rules in test data generation**
   ```python
   validation = field.get('validation', {})
   if validation.get('type') == 'phone_number':
       test_data[pdf_name] = "(555) 123-4567"
   elif validation.get('type') == 'zip_code':
       test_data[pdf_name] = "90210"
   elif validation.get('type') == 'receipt_number':
       test_data[pdf_name] = "123456789012"  # Exactly 12 digits
   ```

4. **Respect max_length in COMB fields**
   ```python
   if field.get('is_comb'):
       max_len = field.get('max_length', 10)
       test_data[pdf_name] = '1' * max_len  # Exact length
   ```

---

### Phase 2: PDF Field Flag Mutator
**New File:** `pdf_conditional_field_mutator.py`

**Purpose:** Create modified PDF with conditional fields unlocked

**Algorithm:**
1. Load schema with conditional logic
2. Open source PDF
3. For each field with `conditional_logic`:
   - Parse condition (e.g., "if P1 Q4 = yes")
   - Identify dependent fields (e.g., P1 Q5a, Q5b, Q5c)
   - Flip READ_ONLY bit (bit 0) from 1 → 0
4. Save modified PDF as `{form}_unlocked.pdf`
5. Use unlocked PDF for round-trip testing

**Key Functions:**
```python
def parse_conditional(conditional_text: str) -> dict:
    """Extract trigger field and dependent fields from conditional text."""

def flip_readonly_bit(widget, enable: bool):
    """Flip bit 0 in field_flags."""
    if enable:
        widget.field_flags &= ~(1 << 0)  # Clear bit 0
    else:
        widget.field_flags |= (1 << 0)   # Set bit 0

def unlock_conditional_fields(pdf_path: str, schema: dict, output_path: str):
    """Create unlocked PDF based on schema conditionals."""
```

---

### Phase 3: Enhanced Field Type Detection
**File:** `widget_inventory.py` or new `detect_radio_from_tooltips.py`

**Pattern Detection:**
1. Extract all tooltips
2. Search for patterns:
   - "select only one box"
   - "select one box"
   - "mark only one"
   - "check only one"
3. If found → mark widget as `suggested_type: radio`
4. Use in schema builder to override checkbox

**Enhancement:**
```python
def detect_mutually_exclusive(widget) -> bool:
    """Check if tooltip indicates mutually exclusive selection."""
    tooltip = widget.field_label or ""
    patterns = [
        "select only one",
        "select one box",
        "mark only one",
        "check only one",
    ]
    return any(p in tooltip.lower() for p in patterns)
```

---

### Phase 4: Schema Consolidation Fixes
**File:** `fix_i90_schema_validation.py` (enhance)

**Additional Consolidations:**
1. **Part 7 Q7a + Q7b** → Single radio group
   - Pattern: p7_checkbox7* fields
   - Group name: "Attorney or Accredited Representative"
   - Options: ["Yes", "No"]

2. **Verify all Apt/Ste/Flr consolidations**
   - Already done: P1, P6, P7
   - Check if any missed

---

## Priority Order

### Critical (Blocking Production)
1. ✅ **PDF Field Flag Mutator** - Without this, conditionals don't work
2. ✅ **Round-trip dropdown support** - Can't test state fields
3. ✅ **Round-trip date support** - Can't test date fields
4. ✅ **Validation enforcement in test data** - Max length violations

### High (Quality Issues)
5. ✅ **"Select only one" pattern detection** - Auto-detect radio fields
6. ✅ **Part 7 Q7 consolidation** - Manual fix needed

### Medium (Nice to Have)
7. ⚠️ **Validation reporting** - Show which fields fail validation
8. ⚠️ **Better test data generation** - Use realistic values

---

## Success Criteria

After all fixes:
1. ✅ Round-trip test fills 100% of fillable fields (including dropdowns, dates)
2. ✅ Conditional fields unlock when dependencies met
3. ✅ All validation rules enforced (phone, zip, date formats)
4. ✅ All "select only one" fields are radio, not checkbox
5. ✅ Max length respected for all COMB fields
6. ✅ Manual review shows correct field types and values

---

## Estimated Effort

- Phase 1 (Round-trip improvements): 1-2 hours
- Phase 2 (PDF mutator): 2-3 hours (most complex)
- Phase 3 (Pattern detection): 30 minutes
- Phase 4 (Schema fixes): 30 minutes

**Total:** 4-6 hours of development + testing

---

## Notes

- PDF field flag manipulation is complex - may need to create "unlocked template" PDFs
- Some conditionals might require JavaScript in PDF (not supported by PyMuPDF)
- For production: Voice AI would fill conditionally based on schema, not PDF flags
- Round-trip testing is validation tool, not production filling mechanism
