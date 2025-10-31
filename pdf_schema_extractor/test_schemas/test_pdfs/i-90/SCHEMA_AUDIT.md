# I-90 Schema Audit - Issues Found in Manual Review

**Date:** October 31, 2025
**Source:** Manual review of i-90_filled_test.pdf
**Reviewer:** User

---

## Critical Issues Summary

### Issue Categories:
1. **Field Type Mismatches** - Checkboxes that should be radio buttons (23 fields)
2. **Missing Dropdowns** - Text fields that should be select/dropdown (8 fields)
3. **Missing Validation** - Phone numbers, dates, zip codes without validation (17 fields)
4. **Conditional Logic** - Fields that should unlock based on other fields (3+ relationships)

---

## Part 1: Information About You

### Q4 → Q5 Conditional Logic ⚠️ CRITICAL
- **Issue:** Q4 was marked 'yes' but Q5a, 5b, 5c did not unlock
- **Fix:** Add conditional logic: `if P1 Q4 == 'yes' then show Q5a, Q5b, Q5c`
- **Fields affected:** P1_checkbox5[0], P1_checkbox5[1], P1_checkbox5[2] (or similar)

### Q6c - Wrong Field Type
- **Current:** checkbox
- **Should be:** radio (mutually exclusive - can't select multiple address types)
- **Field:** P1_checkbox4 group (Apt/Ste/Flr)

### Q6e - Missing Dropdown
- **Current:** text (wasn't filled in test)
- **Should be:** select (states dropdown)
- **Validation:** Must be valid 2-letter state code
- **Field:** P1_Line6e_State[0]

### Q6f - Missing Validation
- **Current:** text
- **Should be:** text with validation
- **Validation:** Numeric only, max 5 digits (zip code)
- **Field:** P1_Line6f_ZipCode[0] (or similar)

### Q9 - Missing Date Field
- **Current:** text
- **Should be:** date
- **Validation:** MM/DD/YYYY format
- **Field:** (need to find date of birth field)

---

## Part 2: Application Type

### Q1a → Q2 Conditional Logic ⚠️ CRITICAL
- **Issue:** Q2 should unlock when Q1a is selected
- **Fix:** Add conditional logic: `if P2 Q1a == true then show Q2`
- **Complex:** Q2 has multiple sub-conditions based on reason for replacement
- **Recommendation:** Use Gemini + i-90instr.pdf to map full conditional tree

### Q2 - Missing Validation
- **Current:** text (but didn't get filled - may be read-only issue)
- **Should be:** text with validation
- **Validation:** Exactly 12 digits (USCIS case/receipt number)
- **Field:** P2_Line2 (need exact name)

---

## Part 3: Processing Information

### Q3, Q5, Q6, Q7, Q10, Q11 - Wrong Field Type
- **Current:** checkbox
- **Should be:** radio (mutually exclusive options)
- **Fields:**
  - P3 Q3: (Yes/No for accommodation request)
  - P3 Q5: (Yes/No)
  - P3 Q6: (Yes/No)
  - P3 Q7: (Yes/No)
  - P3 Q10: (Yes/No)
  - P3 Q11: (Yes/No)

### Q8 - Missing Dropdowns
- **Current:** text fields (2 fields)
- **Should be:** select dropdowns
- **Fields:**
  - Feet: dropdown (0-7 feet)
  - Inches: dropdown (0-11 inches)

---

## Part 4: Accommodations

### Q1 - Wrong Field Type
- **Current:** checkbox
- **Should be:** radio (mutually exclusive)
- **Field:** P4 Q1 options

---

## Part 5: Applicant's Statement

### Q3, Q4, Q5 - Missing Validation
- **Current:** text
- **Should be:** text with validation
- **Validation:** Phone number format, exactly 10 digits
- **Format:** (XXX) XXX-XXXX or XXX-XXX-XXXX
- **Fields:**
  - P5 Q3: Daytime phone
  - P5 Q4: Mobile phone
  - P5 Q5: Evening phone

---

## Part 6: Contact Information (Interpreter)

### Q3b - Wrong Field Type
- **Current:** checkbox
- **Should be:** radio (mutually exclusive)

### Q3d - Missing Dropdown
- **Current:** text
- **Should be:** select (states dropdown)
- **Validation:** Valid 2-letter state code

### Q3g - Missing Validation
- **Current:** text
- **Should be:** text with validation
- **Validation:** Postal code format

### Q4, Q5, Q6 - Missing Validation
- **Current:** text
- **Should be:** text with validation
- **Validation:** Phone number, exactly 10 digits

---

## Part 7: Contact Information (Preparer)

### Q3b - Wrong Field Type
- **Current:** checkbox
- **Should be:** radio

### Q3d - Missing Dropdown
- **Current:** text
- **Should be:** select (states dropdown)

### Q3e - Missing Validation
- **Current:** text
- **Should be:** text with validation
- **Validation:** ZIP code, 5 digits

### Q3g - Missing Validation
- **Current:** text
- **Should be:** text with validation
- **Validation:** Postal code

### Q4, Q5, Q6 - Missing Validation
- **Current:** text
- **Should be:** text with validation
- **Validation:** Phone number, exactly 10 digits

### Q7a + Q7b - Wrong Field Type ⚠️ CRITICAL
- **Issue:** Currently separate fields
- **Should be:** Single radio group with 2 options
- **Fix:** Consolidate into one radio group "Is preparer an attorney or accredited representative?"
- **Options:**
  - Q7a: "Yes, I am an attorney or accredited representative"
  - Q7b: "No, I am not an attorney or accredited representative"

### Q8b - Missing Date Field
- **Current:** text
- **Should be:** date
- **Validation:** MM/DD/YYYY format

---

## Systematic Fixes Needed

### 1. Fix Field Types (Priority: HIGH)
```
Checkbox → Radio conversions:
- P1 Q6c (address type)
- P3 Q3, Q5, Q6, Q7, Q10, Q11 (Yes/No questions)
- P4 Q1 (accommodation type)
- P6 Q3b, P7 Q3b (address unit type)
- P7 Q7a+Q7b (consolidate into single radio group)

Text → Select conversions:
- P1 Q6e (state)
- P3 Q8 feet (height feet)
- P3 Q8 inches (height inches)
- P6 Q3d (state)
- P7 Q3d (state)
```

### 2. Add Validation Rules (Priority: HIGH)
```
Phone numbers (10 digits):
- P5 Q3, Q4, Q5
- P6 Q4, Q5, Q6
- P7 Q4, Q5, Q6

ZIP codes (5 digits):
- P1 Q6f
- P7 Q3e

Postal codes:
- P6 Q3g
- P7 Q3g

Receipt numbers (12 digits):
- P2 Q2

Dates (MM/DD/YYYY):
- P1 Q9 (date of birth)
- P7 Q8b (date signed)
```

### 3. Fix Conditional Logic (Priority: CRITICAL)
```
Simple conditionals:
- P1 Q4 = 'yes' → show Q5a, Q5b, Q5c

Complex conditionals (needs Gemini):
- P2 Q1a = selected → show Q2
- P2 Q2 visibility/requirements depend on which Q1 option selected
- Refer to i-90instr.pdf for complete conditional tree
```

---

## Recommended Fix Strategy

### Phase 1: Automated Fixes (can do now)
1. Create schema field type fixer
2. Add validation rules to known field patterns
3. Convert obvious checkbox → radio based on field names

### Phase 2: Gemini-Assisted Fixes (needs API call)
1. Send i-90instr.pdf to Gemini
2. Ask for complete conditional logic tree for Part 2
3. Ask for validation rules from instructions
4. Update schema with Gemini-identified conditionals

### Phase 3: Re-test
1. Apply all fixes to schema
2. Run round-trip test again
3. Generate new filled PDF
4. Manual review to verify fixes

---

## Open Questions

1. **Dropdown options:** What are the exact options for height feet/inches?
   - Feet: 0-7? or specific range?
   - Inches: 0-11

2. **State dropdown:** Should we use full state names or abbreviations?
   - Likely abbreviations (2-letter codes)

3. **P2 Q2 conditionals:** Exactly which P2 Q1 option unlocks Q2?
   - Need to consult i-90instr.pdf

4. **Phone number format:** Should we store with/without formatting?
   - Recommendation: Store digits only, format for display

---

## Impact Assessment

- **Fields with issues:** ~40-50 fields out of 147 (27-34%)
- **Critical issues:** 3 (conditional logic bugs)
- **High priority:** 23 (type mismatches)
- **Medium priority:** 17 (validation missing)
- **Low priority:** 8 (dropdown vs text)

**Overall:** Schema is structurally sound but needs significant refinement before production use.
