# I-589 Schema Review

## Executive Summary

The i589_schema.json created by Gemini Pro is **highly comprehensive and well-structured** (2901 lines). It captures the complex I-589 form with excellent detail. However, there are several **compatibility issues** with our FormSchema specification that need to be addressed.

**Status**: ⚠️ Needs updates for full compatibility

---

## ✅ What Works Well

### 1. Core Structure
- ✅ **source**: Correctly set to "pdf"
- ✅ **form_metadata**: All required fields present (title, form_number, edition_date, etc.)
- ✅ **sections**: Well-organized with proper IDs, labels, and order
- ✅ **fields**: Comprehensive with 100+ fields properly defined

### 2. Field Definitions
- ✅ All required field properties: `id`, `name`, `spoken_name`, `type`, `section_id`
- ✅ PDF field mappings via `pdf_field_name`
- ✅ Validation rules properly structured
- ✅ Help text with inline hints
- ✅ Format presets (a_number, ssn, zip)

### 3. Complex Features
- ✅ **Conditional logic**: Simple `show_if` conditions work perfectly
- ✅ **Table structures**: Children table with 20+ columns, well-defined
- ✅ **Multi-entry config**: Proper use of `min_entries`, `initial_rows`, `overflow_instruction`
- ✅ **Radio/checkbox options**: Properly structured with values and labels
- ✅ **Date fields**: Format specifications included

---

## ⚠️ Compatibility Issues

### 1. **Parts Structure** (Not in Spec)
```json
"parts": [
  {
    "id": "part_a",
    "label": "Part A: Information About Applicant",
    "order": 1,
    "section_ids": ["part_a_i", "part_a_ii", "part_a_iii"]
  }
]
```

**Issue**: The spec doesn't include a "parts" hierarchy level.

**Impact**: Medium - This is actually a useful organizational feature for complex forms like I-589.

**Recommendation**:
- **Option A**: Add `parts` to the FormSchema spec as an optional organizational layer
- **Option B**: Remove parts and flatten the structure

### 2. **Supplement Structure** (Incomplete)
```json
// Current schema:
"supplements": [
  {
    "id": "supplement_a",
    "label": "Supplement A - Additional Children",
    "page_number": 11
  }
]

// Spec requires:
interface FormSupplement {
  id: string;
  name: string;              // ❌ Using "label" instead
  purpose: string;            // ❌ Missing
  trigger_condition?: string; // ❌ Missing
  fields: string[];           // ❌ Missing
  page_number?: number;       // ✅ Present
}
```

**Issue**: Missing required fields and using wrong property names.

**Impact**: High - Supplements won't work properly without field mappings.

**Fix Required**:
```json
"supplements": [
  {
    "id": "supplement_a",
    "name": "Supplement A - Additional Children",
    "purpose": "Overflow space for additional children beyond the 4 rows in Part A.II",
    "trigger_condition": "More than 4 children",
    "fields": ["part_a_ii_children_table"],
    "page_number": 11
  }
]
```

### 3. **Static Text Type** (Not in FieldType)
```json
{
  "id": "part_f_read_only_note",
  "type": "static_text",  // ❌ Not in FieldType union
  "default_value": "...",
  "read_only": true
}
```

**Issue**: `static_text` is not a valid FieldType.

**Impact**: Medium - TypeScript will reject this.

**Fix Required**: Add `static_text` to FieldType union in form_schema_types.ts:
```typescript
export type FieldType =
  | 'text'
  | 'textarea'
  // ... other types ...
  | 'signature'
  | 'static_text'  // Add this
  | 'address_group'
  | 'table';
```

### 4. **Read-Only Property** (Not in FormField)
```json
{
  "id": "part_f_asylum_officer_signature",
  "type": "signature",
  "read_only": true,  // ❌ Not in FormField interface
  "section_id": "part_f_interview"
}
```

**Issue**: `read_only` property not defined in FormField interface.

**Impact**: Low - Easy to add.

**Fix Required**: Add to FormField interface:
```typescript
export interface FormField {
  // ... existing properties ...
  read_only?: boolean;  // Add this
}
```

### 5. **Complex Conditionals with OR Logic** (Extended beyond spec)
```json
{
  "show_if": {
    "condition": "OR",  // ❌ Not in ConditionalDisplay
    "rules": [
      {
        "field": "part_c_q2a_travel_through_other_countries",
        "operator": "equals",
        "value": "yes"
      },
      {
        "field": "part_c_q2b_status_in_other_countries",
        "operator": "equals",
        "value": "yes"
      }
    ]
  }
}
```

**Issue**: Spec only supports simple single-condition logic.

**Impact**: High - Many I-589 fields use OR/AND logic.

**Fix Required**: Extend ConditionalDisplay to support complex logic:
```typescript
export interface ConditionalDisplay {
  // Simple condition (existing)
  field?: string;
  operator?: ConditionalOperator;
  value?: string | number | boolean;

  // Complex conditions (new)
  condition?: 'AND' | 'OR';
  rules?: ConditionalDisplay[];
}
```

### 6. **Table Column Conditionals** (Not in TableColumn)
```json
{
  "id": "location_not_in_us",
  "label": "Specify location",
  "type": "text",
  "show_if": {  // ❌ Not in TableColumn interface
    "field": "in_us",
    "operator": "equals",
    "value": "no"
  }
}
```

**Issue**: TableColumn doesn't support `show_if`.

**Impact**: Medium - Needed for conditional columns.

**Fix Required**: Add to TableColumn interface:
```typescript
export interface TableColumn {
  id: string;
  label: string;
  type: FieldType;
  width?: number;
  validation?: ValidationRules;
  help?: FieldHelp;
  show_if?: ConditionalDisplay;  // Add this
  options?: FieldOption[];        // Add this for select/radio in tables
  format?: DateFormat;            // Add this for date columns
}
```

### 7. **Section page_numbers Array** (vs single page_number)
```json
{
  "id": "part_a_ii",
  "page_numbers": [2, 3],  // ❌ Spec expects page_number: number
  "label": "Part A.II: Information About Your Spouse and Children"
}
```

**Issue**: Spec defines `page_number?: number` (singular).

**Impact**: Low - Sections often span multiple pages.

**Fix Required**: Change to array in spec:
```typescript
export interface FormSection {
  id: string;
  label: string;
  description?: string;
  order: number;
  fields: string[];
  page_numbers?: number[];  // Change from page_number to page_numbers
  required?: boolean;
  show_if?: ConditionalDisplay;
}
```

### 8. **overflow_to_supplement Property** (Not in FormField)
```json
{
  "id": "part_b_q1a_past_harm_details",
  "type": "textarea",
  "overflow_to_supplement": "supplement_b",  // ❌ Not in spec
  "help": {
    "inline": "(Use Supplement B if needed.)"
  }
}
```

**Issue**: This useful property isn't in the FormField interface.

**Impact**: Medium - Important for PDF forms with overflow pages.

**Fix Required**: Add to FormField:
```typescript
export interface FormField {
  // ... existing properties ...
  overflow_to_supplement?: string;  // Add this - references supplement ID
}
```

---

## 📊 Detailed Statistics

- **Total fields**: 162 fields
- **Sections**: 9 sections across 7 parts
- **Table fields**: 3 complex tables (US entries, children, residences, etc.)
- **Conditional fields**: ~80 fields with show_if conditions
- **Read-only fields**: ~15 fields (Parts F & G)
- **Supplements**: 2 (Supplement A & B)

---

## 🔧 Required Updates

### Priority 1 (Breaking Issues)
1. Fix supplement structure (add name, purpose, trigger_condition, fields)
2. Add `static_text` to FieldType union
3. Add `read_only` to FormField interface
4. Support complex conditionals (OR/AND logic)

### Priority 2 (Enhancement)
5. Add `show_if`, `options`, `format` to TableColumn interface
6. Change section `page_number` to `page_numbers` array
7. Add `overflow_to_supplement` to FormField interface

### Priority 3 (Optional)
8. Consider adding `parts` structure to spec for better organization

---

## 🎯 Recommendations

### Short Term (Use Current Schema)
The schema can be used **with minor modifications** by:
1. Updating TypeScript interfaces to match schema extensions
2. Implementing OR logic in conditional rendering
3. Handling static_text as a special case

### Long Term (Standardize)
1. **Update FormSchema specification** to incorporate these patterns
2. **Document the extensions** as official features
3. **Create validation tool** to verify schemas against spec
4. **Add JSON Schema** for automated validation

---

## ✨ What Gemini Did Exceptionally Well

1. **Comprehensive Coverage**: Captured all 162 fields across 12 pages
2. **Proper Nesting**: Table columns with conditional sub-fields
3. **PDF Mappings**: Every field mapped to PDF field names
4. **Spoken Names**: Great voice interaction support
5. **Validation**: Format presets and validation rules properly applied
6. **Help Text**: Inline help properly extracted from PDF
7. **Multi-entry Tables**: Properly configured with overflow instructions

---

## 🚀 Next Steps

1. **Decision Point**: Do we update the spec or modify the schema?
   - **Recommendation**: Update the spec - these are genuinely useful extensions

2. **Implementation Path**:
   ```
   a) Update form_schema_types.ts with missing properties
   b) Fix supplement structure in i589_schema.json
   c) Test schema loading and validation
   d) Document the extended features
   ```

3. **Validation**: Create a schema validator to catch these issues automatically

---

## Conclusion

The Gemini-generated schema is **production-ready with minor fixes**. It's actually more sophisticated than our current spec in several ways. The recommended approach is to:

1. ✅ Accept the schema's innovations (OR logic, static_text, etc.)
2. 🔧 Update our FormSchema types to match
3. 🔨 Fix the supplement structure
4. 📝 Document these as official features

**Overall Grade**: A- (Excellent work, needs minor spec alignment)
