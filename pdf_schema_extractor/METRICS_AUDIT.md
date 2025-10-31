# Evaluation Metrics Audit

**Date:** October 30, 2025
**Purpose:** Verify our metrics actually measure what we think they measure

---

## Summary: Major Issues Found

1. ❌ **Widget Coverage** doesn't check `consolidated_widgets` field
2. ⚠️ **Type Compatibility** only checks fields with `pdf_field_name`
3. ⚠️ **Structural Consistency** has low discriminatory power
4. ❌ **Heuristic Cross-Validation** is NOT IMPLEMENTED (hardcoded to 80%)

---

## Metric 1: Widget Coverage

### What We Think It Measures
"Percentage of PDF form widgets represented in the schema"

### What It Actually Measures

**Source Code Analysis:**
```python
# Line 122-141: verify_widget_coverage()
# 1. Gets ALL PDF widgets (unfiltered)
# 2. Normalizes field names (strips hierarchy)
# 3. Collects schema names via _collect_pdf_field_names()
```

**_collect_pdf_field_names() checks:**
- ✅ `field.pdf_field_name`
- ✅ `columns[].pdf_field_name`
- ✅ `options[].pdf_field_name`
- ❌ **DOES NOT CHECK** `consolidated_widgets`

### Impact
- **Hybrid v2**: 82.4% (uses `consolidated_widgets` ✓)
- **Minimal**: 73.5% (uses `consolidated_widgets` ✓)
- **Verifier thinks minimal is worse, but it's not!**

### Issues
1. **Doesn't recognize `consolidated_widgets` array** (our new tracking method)
2. **Includes filtered widgets** (barcodes, read-only) we intentionally exclude
3. **Pass threshold**: 95% (very strict)

### What It Should Measure
"Percentage of CLEAN PDF widgets (after filtering) that appear in either:
- `pdf_field_name` (standalone)
- `consolidated_widgets[]` (grouped)
- `options[].pdf_field_name` (radio/checkbox)
- `columns[].pdf_field_name` (tables)"

---

## Metric 2: Type Compatibility

### What We Think It Measures
"Schema field types compatible with actual PDF widget types"

### What It Actually Measures

**Source Code Analysis:**
```python
# Line 192-260: verify_type_compatibility()
# 1. Gets PDF widgets by normalized name
# 2. For each field WITH pdf_field_name:
#    - Look up widget
#    - Check TYPE_COMPATIBILITY matrix
# 3. Also checks table columns with pdf_field_name
```

### Type Compatibility Matrix
```python
"text": ["text", "textarea", "date", "email", "tel", "number"],
"checkbox": ["checkbox", "radio"],
"radio": ["radio"],
"select": ["select"],
"signature": ["signature"],
```

### Issues
1. **Only checks fields with `pdf_field_name`** - skips groups without it
2. **Checkbox can match radio** (may be intentional for consolidation)
3. **Pass threshold**: 100% (extremely strict)

### What It Should Measure
"For every widget in the PDF, verify its type is compatible with how the schema uses it (checking consolidated_widgets)"

---

## Metric 3: Structural Consistency

### What We Think It Measures
"Schema has valid internal structure (no broken references, proper groups)"

### What It Actually Measures

**Source Code Analysis:**
```python
# Line 308-380: verify_structural_consistency()
# Checks:
# 1. Radio groups have 2+ options
# 2. Tables have columns
# 3. show_if fields exist
# 4. No duplicate field IDs
# 5. Groups have options
# 6. Field IDs are valid
```

### Issues
1. **Limited checks** - only 6 validation rules
2. **Low discriminatory power** - Most schemas pass easily on some checks
3. **No deep validation** of:
   - `consolidated_widgets` completeness
   - Table column mappings
   - Group/option consistency
4. **Score calculation**: checks_passed / total_checks (can be low if many checks)

### What It Should Measure
"Comprehensive structural validation:
- All `consolidated_widgets` exist in PDF
- No widget appears twice
- Group options cover all group widgets
- Table columns map to actual widgets
- All references are valid"

---

## Metric 4: Heuristic Cross-Validation

### What We Think It Measures
"Agreement between schema and heuristic extraction"

### What It Actually Measures

**Source Code Analysis:**
```python
# Line 390-405: verify_heuristic_crossval()
warnings = ["Heuristic cross-validation not yet implemented"]
return VerificationResult(
    layer="heuristic_crossval",
    passed=True,
    score=0.8,  # Assume good for now  ← HARDCODED!
    warnings=warnings,
    details={"status": "not_implemented"}
)
```

### Issues
1. ❌ **NOT IMPLEMENTED AT ALL**
2. ❌ **Hardcoded to 80%** - gives false confidence
3. ❌ **Always passes** - meaningless metric

### What It Should Measure
"Comparison with heuristic extractor:
- Field count similarity
- Type agreement
- Grouping agreement
- Widget coverage agreement"

---

## Overall Scoring Formula

```python
confidence_score = sum(l.score for l in layers) / len(layers)
overall_passed = all(l.passed for l in layers[:2])  # Only layers 1-2 critical
```

### Issues
1. **Equal weighting** - All layers count equally, even fake ones (layer 4)
2. **Only 2 critical** - Layers 3-4 don't affect pass/fail
3. **Hardcoded 80%** from layer 4 inflates all confidence scores by 20%!

---

## Impact on Our Evaluations

| Approach | Reported Conf | Real Conf (minus fake 80%) | True Status |
|----------|---------------|----------------------------|-------------|
| Canonical | 75.5% | **71.8%** | Widget coverage is low (22.5%) |
| Hybrid V2 | 68.8% | **64.9%** | Good, but structural issues |
| Minimal | 65.6% | **61.2%** | Better than reported (consolidated_widgets not counted) |

**All confidence scores are inflated by ~4% due to fake layer 4!**

---

## Recommendations

### Priority 1: Fix Widget Coverage
```python
def _collect_pdf_field_names(self, field, names):
    # Add this:
    for widget_name in field.get("consolidated_widgets", []):
        names.add(widget_name)
```

### Priority 2: Remove/Implement Heuristic Cross-Validation
Either:
- **Remove** layer 4 entirely (reduce confusion)
- **Implement** it properly (compare with actual heuristic extraction)

### Priority 3: Enhance Structural Consistency
Add checks for:
- `consolidated_widgets` completeness
- Widget deduplication
- Group/option consistency

### Priority 4: Adjust Type Compatibility
- Check widgets in `consolidated_widgets` too
- Consider group context (checkboxes in radio group = radio type)

---

## Corrected Metrics (If We Fix Widget Coverage)

**Assuming we check consolidated_widgets:**

| Approach | Widget Coverage | Type Compat | Struct | Heuristic | Conf (real) |
|----------|----------------|-------------|--------|-----------|-------------|
| Hybrid V2 | **100%** ✓ | 100% | 12.8% | N/A | **~70%** |
| Minimal | **100%** ✓ | 100% | 9.0% | N/A | **~69%** |

**Both approaches would show 100% widget coverage!**

---

## Conclusion

Our metrics have significant blind spots:

1. ❌ **Widget coverage** doesn't see our new `consolidated_widgets` field
2. ❌ **Heuristic validation** is fake (hardcoded 80%)
3. ⚠️ **Structural consistency** is weak (only 6 basic checks)
4. ⚠️ **All confidence scores** are inflated by ~4%

**Action Required:** Update verifier to properly measure what we think it measures!

---

## Next Steps

1. Update `_collect_pdf_field_names()` to check `consolidated_widgets`
2. Remove layer 4 or implement it properly
3. Re-run all verifications with fixed metrics
4. Compare actual performance of hybrid vs minimal approaches
