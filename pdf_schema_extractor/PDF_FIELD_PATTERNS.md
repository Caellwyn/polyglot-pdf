# PDF Field Naming Pattern Analysis

## Key Discovery: Multi-Row Table Representation

After forensic analysis of the i-589.pdf and ground truth schema, I've discovered how tables are represented in the PDF.

## Pattern 1: Spouse vs Children Fields

### Part A.II Structure
- **Spouse**: Individual fields (NOT a table) use array index `[0]`
- **Children**: Table with 22 columns × 4 rows

### Array Index Pattern
```
PtAIILine1_ANumber[0]     → Spouse's A-Number (individual field)
PtAIILine1_ANumber[1]     → Child A-Number column template (in schema)

PtAIILine5_LastName[0]    → Spouse's Last Name (individual field)
PtAIILine5_LastName[1]    → Child Last Name column template (in schema)
```

### Actual PDF Fields for Children
The PDF uses **numbered field names** for actual child data:
```
Child 1:  ChildAlien1[0], ChildLast1[0], ChildFirst1[0], ...
Child 2:  ChildAlien2[0], ChildLast2[0], ChildFirst2[0], ...
Child 3:  ChildAlien3[0], ChildLast3[0], ChildFirst3[0], ...
Child 4:  ChildAlien4[0], ChildLast4[0], ChildFirst4[0], ...
```

**The number in the field name (Child**1**, Child**2**) indicates the TABLE ROW.**

## Pattern 2: Multi-Row Layout Per Table Row

Each logical table row (one child) **spans MULTIPLE physical PDF rows**:

### Child 1 Fields (Page 2):
```
Y=518.0:  ChildAlien1[0], ChildPassport1[0], ChildMarital1[0], ChildSSN1[0]
Y=548.0:  ChildLast1[0], ChildFirst1[0], ChildMiddle1[0], ChildDOB1[0]
Y=578.0:  ChildCity1[0], ChildNat1[0], ChildRace1[0], ...
... (possibly more rows for conditional fields)
```

### Child 2 Fields (Page 3):
```
Y=67.0:   ChildAlien2[0], ChildPassport2[0], ChildMarital2[0], ChildSSN2[0]
Y=98.0:   ChildFirst2[0], ChildMiddle2[0], ChildDOB2[0]
Y=99.0:   ChildLast2[0]
Y=126.0:  ChildCity2[0], ChildNat2[0], ChildRace2[0], ...
```

**Key Insight**: Fields at the same Y coordinate = same physical row, but may belong to different columns of the same logical table row.

## Pattern 3: Array Indices as Column Identifiers

Some fields use **array indices to differentiate columns** in the same table:

### Example: TextField8 in Children Table
```
TextField8[0]  → Column 2: Passport/ID
TextField8[1]  → Column 3: Marital Status
TextField8[2]  → Column 4: SSN
TextField8[3]  → Column 9: City/Country of Birth
TextField8[4]  → Column 10: Nationality
TextField8[5]  → Column 11: Race/Ethnic/Tribal Group
```

All these `TextField8[N]` fields belong to **the same logical table row** (same child) but are **different columns**.

## Pattern 4: Conditional Fields (show_if)

Some columns only appear when certain conditions are met:

```json
{
  "id": "location_not_in_us",
  "pdf_field_name": "PtAIILine15_Specify[1]",
  "show_if": {
    "field": "in_us",
    "operator": "equals",
    "value": "no"
  }
}
```

This explains why different children have different numbers of physical rows - conditional fields create variable-length layouts.

## Pattern 5: Part A.III Tables (Array Index Pattern)

Part A.III uses a different pattern - pure array indices without numbered field names:

### Last Address Abroad Table:
```
TextField15[0], TextField16[0], TextField17[0], ... → Row 0 (single row table)
```

### Residences Last 5 Years Table:
```
Row 0:  TextField13[0], TextField13[1], TextField13[2], ..., DateTimeField21[0], DateTimeField22[0]
Row 1:  TextField13[6], TextField13[7], TextField13[8], ..., DateTimeField24[0], DateTimeField25[0]
Row 2:  TextField13[12], TextField13[13], TextField13[14], ..., DateTimeField26[0], DateTimeField27[0]
...
```

**Array index indicates position within the table**, but the same base name (e.g., TextField13) is reused across multiple tables with different spatial positions.

## Detection Algorithm Requirements

Based on these patterns, the algorithm must:

1. **Group by numbered field name suffix first**: `Child1`, `Child2`, `Child3` indicate table rows
2. **Within each numbered group, collect ALL Y positions**: One logical row spans multiple physical rows
3. **Group fields at same Y by X coordinate**: Left-to-right = columns
4. **Handle array indices as column differentiators**: `TextField8[0]`, `TextField8[1]`, `TextField8[2]` are separate columns
5. **Use spatial gaps to separate tables**: Large Y gaps (>80px) or page boundaries indicate new tables
6. **Handle conditional fields**: Not all rows have same number of fields (some have show_if conditions)

## Ground Truth Mapping Strategy

The ground truth schema uses **array index [1]** for column templates, representing "the first actual data row" (Child 1), while **[0]** is used for the parent record (Spouse).

To extract column definitions:
1. Find all fields with numbered suffix "1" (e.g., `Child*1`)
2. Add all fields with array index [1] at those Y positions
3. Sort by X coordinate to get column order
4. The total set = all 22 columns

## Example: Children Table Structure

**Logical Table**: 22 columns × 4 rows = 88 cells

**Physical PDF Layout**:
- Child 1: 3-4 physical rows on Page 2 (Y: 518, 548, 578, ...)
- Child 2: 4-5 physical rows on Page 3 (Y: 67, 98, 99, 126, ...)
- Child 3: 3-4 physical rows on Page 3 (Y: 300, 332, 360, ...)
- Child 4: 3-4 physical rows on Page 3 (Y: 534, 566, 594, ...)

**Field Names**:
- Row indicator: `Child**N**` where N = 1, 2, 3, 4
- Column indicator: Base name + array index OR field type
- Examples:
  - `ChildAlien1[0]` = Row 1, Column 1 (A-Number)
  - `ChildLast1[0]` = Row 1, Column 5 (Last Name)
  - `TextField8[0]` at Y=518 = Row 1, Column 2 (Passport)
  - `TextField8[1]` at Y=518 = Row 1, Column 3 (Marital Status)

## Critical Realization

**The number in the field name is the TABLE ROW NUMBER, NOT the physical PDF row number!**

- `ChildAlien1`, `ChildLast1`, `ChildFirst1`, `ChildCity1` all belong to **logical row 1** (Child 1)
- But they appear at **different Y positions** (518, 548, 578) in the PDF
- They must be **grouped together** into a single table row with multiple columns

This is why my current algorithm is failing - I'm grouping by Y position and treating each Y position as a separate row, when I should be grouping by the **number in the field name** to get logical rows.
