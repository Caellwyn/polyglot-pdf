# PDF Schema Extractor - Turnover Document

## Project Context

**Goal**: Iterate on `pdf_schema_extractor/extractor.py` to extract schema from `i589.pdf` that matches the ground truth in `i589_schema.json`.

**Key Requirement**: Reduce field count from 448 raw PDF fields to 156 by detecting and consolidating repeating fields into table structures.

**User Expectation**: Tool must be fully automated without manual intervention.

## Current Status

### Metrics
- **Starting Point**: 448 individual PDF form fields
- **Current Result**: 92 fields after table detection
- **Target**: 156 fields
- **Gap**: Need to refine table detection (currently too aggressive in some areas)

### Test Command
```bash
cd /home/user/polyglot-pdf
python3 test_extraction.py
```

This runs the extractor and saves results to `pdf_schema_extractor/test_schemas/extracted_schema.json`.

## Critical Discoveries

### 1. PDF Field Naming Patterns (Documented in PDF_FIELD_PATTERNS.md)

**Pattern A: Numbered Field Names**
- Row number is embedded in the field name: `ChildAlien1`, `ChildAlien2`, `ChildAlien3`, `ChildAlien4`
- The number indicates the **logical table row**, not the physical PDF row
- One logical row spans multiple physical Y positions

Example - Child 1 (logical row 1):
```
Y=518.0:  ChildAlien1[0], ChildPassport1[0], ChildMarital1[0], ChildSSN1[0]
Y=548.0:  ChildLast1[0], ChildFirst1[0], ChildMiddle1[0], ChildDOB1[0]
Y=578.0:  ChildCity1[0], ChildNat1[0], ChildRace1[0], ...
```

All these fields belong to the same logical table row (Child 1).

**Pattern B: Array Indices**
- Field names use array indices: `TextField13[0]`, `TextField13[1]`, `TextField13[2]`
- Array index can indicate row number (in some cases) or column differentiation (in other cases)
- Same base name (`TextField13`) is reused across multiple tables at different spatial positions

**Critical Insight**: Some fields use array indices to differentiate **columns within the same row**:
```
TextField8[0]  → Passport/ID (column 2)
TextField8[1]  → Marital Status (column 3)
TextField8[2]  → SSN (column 4)
TextField8[3]  → City/Country of Birth (column 9)
```

These are all at the **same Y position** but represent different columns.

### 2. Ground Truth Structure

**Children Table** (from i589_schema.json):
- ID: `part_a_ii_children_table`
- Dimensions: **22 columns × 4 rows = 88 cells**
- Section: `part_a_ii`

Column examples (from ground truth):
```json
{
  "id": "a_number",
  "pdf_field_name": "PtAILine1_ANumber[1]"
},
{
  "id": "passport_id",
  "pdf_field_name": "TextField8[0]"
},
{
  "id": "marital_status",
  "pdf_field_name": "TextField8[1]"
}
```

**Key Observation**: The ground truth uses array index `[1]` for column templates, while actual data uses `[0]`.

## What's Working

### Pattern A Detection (extractor.py lines 284-339)
```python
# Successfully detects numbered field names
# Groups Child1, Child2, Child3, Child4 into a 4-row table
# Excludes generic names (TextField, DateTimeField, CheckBox)
match = re.match(r'^([A-Za-z_]{2,}?)([1-8])$', pdf_name_no_idx)
```

**Result**: Creates 11-column × 4-row children table
- Includes: ChildAlien, ChildLast, ChildFirst, ChildMiddle, ChildDOB, ChildCity, ChildNat, ChildRace, ChildPassport, ChildMarital, ChildSSN

### Pattern B Detection (extractor.py lines 341-402)
```python
# Detects array-indexed fields
# Groups by spatial regions (Y gaps > 100px)
# Requires minimum 3 rows to avoid radio button false positives
```

**Result**: Creates tables from TextField13[0-29] patterns in Part A.III

## Critical Problem

### The Children Table Is Missing 11 Columns

**Currently Detected**: 11 columns (Pattern A only)
- ChildAlien1, ChildLast1, ChildFirst1, ChildMiddle1, ChildDOB1, ChildCity1, ChildNat1, ChildRace1, ChildPassport1, ChildMarital1, ChildSSN1

**Ground Truth Requires**: 22 columns (Pattern A + Pattern B combined)
- The 11 Pattern A columns PLUS
- TextField8[0-5] (passport, marital status, SSN, city, nationality, race)
- DateTimeField9[0] (DOB)
- CheckBox fields (sex, in_us)
- Conditional fields (place_of_last_entry, date_of_last_entry, i94_number, etc.)

**Why They're Missing**:
Pattern A and Pattern B run independently. When Pattern A creates the children table with Child1-4 fields, Pattern B doesn't know to add the TextField8[0], TextField8[1] fields that appear at the same Y positions.

## Architectural Issue

### Current Architecture (Flawed)
```
1. Run Pattern A → Create tables from numbered field names
2. Run Pattern B → Create separate tables from remaining array-indexed fields
3. Result: Two separate children tables (11 cols and 94 cols)
```

### Required Architecture
```
1. Identify logical rows using Pattern A (Child1 = row 1, Child2 = row 2, etc.)
2. For each logical row, collect ALL fields at those Y positions:
   - Pattern A fields (ChildXXX1)
   - Pattern B fields (TextField8[N], DateTimeField9[0])
   - Other fields at same Y (checkboxes, radio buttons)
3. Sort by X position to get column order
4. Result: Single 22-column × 4-row children table
```

## Specific Next Steps

### Step 1: Hybrid Pattern Detection

Modify `detect_table_patterns()` to merge patterns:

```python
# After identifying numbered field patterns (Pattern A)
for row_num in row_nums_sorted:
    # Collect Pattern A fields
    row_fields = []
    for base_name in sorted(bases_dict.keys()):
        if row_num in bases_dict[base_name]:
            row_fields.extend(bases_dict[base_name][row_num])

    # NEW: Also collect all other fields at the same Y positions
    # Get Y positions of Pattern A fields
    y_positions = set()
    for field in row_fields:
        y_key = round(field.pdf_position.y / 20) * 20
        y_positions.add(y_key)

    # Find all other fields at these Y positions
    for field in fields_list:
        if field.id not in used_field_ids:
            field_y_key = round(field.pdf_position.y / 20) * 20
            if field_y_key in y_positions:
                row_fields.append(field)
                used_field_ids.add(field.id)

    # Sort by X position for column order
    row_fields_sorted = sorted(row_fields, key=lambda f: f.pdf_position.x)
    table_rows.append(row_fields_sorted)
```

### Step 2: Verify Against Ground Truth

Compare detected columns with ground truth:
```bash
# Extract children table columns from both
jq '.fields[] | select(.id == "part_a_ii_children_table") | .columns[] | .pdf_field_name' \
  pdf_schema_extractor/test_schemas/test_pdfs/i589_schema.json > gt_columns.txt

jq '.fields[] | select(.id == "part_a_ii_children_table" and (.columns | length) > 15) | .columns[] | .pdf_field_name' \
  pdf_schema_extractor/test_schemas/extracted_schema.json > extracted_columns.txt

diff gt_columns.txt extracted_columns.txt
```

### Step 3: Handle Spouse Fields

The 94-column spurious table is likely including spouse fields mixed with children fields. Need to:
1. Separate spouse (array index [0]) from children (numbered suffix 1-4)
2. Spouse fields should NOT be in the children table

## Files and Documentation

### Key Files
- `pdf_schema_extractor/extractor.py` - Main extraction logic (lines 258-445 for table detection)
- `pdf_schema_extractor/test_schemas/test_pdfs/i589_schema.json` - Ground truth
- `pdf_schema_extractor/test_schemas/extracted_schema.json` - Current output
- `test_extraction.py` - Test harness

### Documentation Created
- `pdf_schema_extractor/PDF_FIELD_PATTERNS.md` - Comprehensive forensic analysis of PDF patterns
- `pdf_schema_extractor/TABLE_DETECTION_STATUS.md` - Earlier progress report (now outdated)
- `pdf_schema_extractor/PROGRESS_REPORT.md` - Earlier progress report (now outdated)

### Debug Commands

**Check children table structure:**
```bash
jq '.fields[] | select(.id == "part_a_ii_children_table") | {cols: (.columns | length), rows: .multi_entry.initial_rows}' \
  pdf_schema_extractor/test_schemas/extracted_schema.json
```

**List all tables:**
```bash
jq '.fields[] | select(.type == "table") | {section: .section_id, id: .id, cols: (.columns | length), rows: .multi_entry.initial_rows}' \
  pdf_schema_extractor/test_schemas/extracted_schema.json
```

**Field counts per section:**
```bash
jq '.sections[] | {id: .id, extracted: (.fields | length)}' \
  pdf_schema_extractor/test_schemas/extracted_schema.json
```

## Test Data Expectations

### Ground Truth Tables (10 total, 300 cells)
```
part_a_i_us_entries:                 4 cols × 3 rows = 12 cells
part_a_ii_children_table:           22 cols × 4 rows = 88 cells
part_a_iii_last_address_abroad:      6 cols × 1 row  = 6 cells
part_a_iii_residences_last_5_years:  6 cols × 5 rows = 30 cells
part_a_iii_education_history:        5 cols × 3 rows = 15 cells
part_a_iii_employment_history:       4 cols × 4 rows = 16 cells
part_a_iii_family_info:              4 cols × 8 rows = 32 cells
part_d_family_assisted_details:      2 cols × 2 rows = 4 cells
supplement_a_children_table:        22 cols × 4 rows = 88 cells
supplement_b_continuation_table:     3 cols × 3 rows = 9 cells
```

### Current Detection Results
```
part_a_i: 1 table (should be 1 + individual fields = ~40 total fields)
part_a_ii: 2 tables (should be 1 table + individual spouse fields = ~30 total fields)
part_a_iii: 1 table (should be 5 tables + minimal individual = ~5 total fields)
```

## Git Branch
- Branch: `claude/session-011CUYgdN87X1DfDMnUzQpwV`
- All changes committed and pushed

## Recommended Approach for Next Session

1. **Read this turnover document**
2. **Read PDF_FIELD_PATTERNS.md** for detailed pattern analysis
3. **Review current extractor.py** lines 258-445 (table detection logic)
4. **Implement hybrid pattern approach** as outlined in Step 1 above
5. **Test** with `python3 test_extraction.py`
6. **Verify** children table has 22 columns
7. **Iterate** on Part A.III (should create 5 separate tables, not 1)
8. **Compare** final output with ground truth using jq commands above

## Success Criteria

- [ ] Total field count: 150-160 fields (close to 156 target)
- [ ] Children table: 22 columns × 4 rows
- [ ] Part A.III: 5 separate tables detected
- [ ] No spurious 94-column tables
- [ ] All sections have field counts within ±5 of ground truth

## Notes

- The PDF uses inconsistent patterns intentionally (form design, not extractor bug)
- Array index [0] vs [1]: [0] for actual data fields, [1] for column templates in some cases
- Conditional fields (show_if) create variable row structures - this is expected
- Radio buttons use array indices [0, 1] for male/female or yes/no - don't create tables from these
