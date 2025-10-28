# Table Detection Status

## Current Progress

**Field Count**: 448 → 74 fields (target: 156)

### Algorithm Improvements Implemented

1. **Y-Position First Grouping**
   - Groups fields by Y coordinate (vertical position)
   - Detects row indices from PDF field names
   - Handles both patterns:
     - Array indices: `TextField13[0]`, `TextField13[1]`
     - Numbered names: `ChildAlien1`, `ChildAlien2`

2. **Index Restart Detection**
   - Detects when indices restart (e.g., 1→2→3→1 indicates new table)
   - Tracks seen indices to prevent merging separate tables

3. **Y-Gap Detection**
   - Splits tables when vertical gap > 80 pixels
   - Helps separate visually distinct table sections

4. **Semantic Table Naming**
   - Generates meaningful IDs: `children_table`, `us_entries`, `education_history`
   - Based on PDF field name patterns and context

## Current Issues

1. **Children Table Fragmentation**
   - Detected as 3 separate tables instead of 1
   - Rows: 4 cols × 3 rows, 6 cols × 17 rows, 5 cols × 15 rows
   - Target: 22 cols × 4 rows = 88 cells

2. **Part A.III Over-Consolidation**
   - All 5 tables merged into 1 large table
   - Need better boundary detection between tables

3. **Field Count by Section** (Extracted vs Target):
   - part_a_i: 21 vs 40 ❌
   - part_a_ii: 1 vs 30 ❌
   - part_a_iii: 1 vs 5 ❌
   - part_b_questions: 4 vs 18 ❌
   - part_c_questions: 15 vs 13 ✅
   - part_d_signature: 7 vs 9 ✅
   - part_e_declaration: 1 vs 17 ❌
   - part_f_interview: 3 vs 16 ❌
   - part_g_hearing: 8 vs 12 ❌

## Next Steps for Refinement

1. **Improve Row Grouping Logic**
   - Use field name similarity to group columns
   - Detect when field types change (indicates table boundary)

2. **Column Detection**
   - Currently missing many columns in tables
   - Need to group fields at same Y position but different X positions

3. **Table Boundary Heuristics**
   - Add detection for section headers/labels
   - Use field name prefixes to identify table groups
   - Analyze field tooltip text for table context

4. **Testing & Validation**
   - Compare detected table structures with ground truth
   - Add tests for each table type
   - Validate cell counts match expected

## Algorithm Trade-offs

**Current Approach**: Aggressive consolidation (reduces from 448 to 74)
- **Pros**: Significantly reduces field count, detects major table patterns
- **Cons**: Over-consolidates in some sections, fragments complex tables

**Alternative Approaches**:
1. **Conservative**: Only create tables when 100% confident → More fields, fewer errors
2. **Rule-based**: Manual configuration for known table patterns → More accurate, less flexible
3. **ML-based**: Train model on labeled examples → Best accuracy, requires training data

## Conclusion

The Y-position-first approach shows promise, reducing field count by 84% (448 → 74). However, precise table boundary detection remains challenging due to:
- Complex PDF field naming conventions
- Mixed patterns within single forms
- Conditional/optional fields creating irregular row structures

Further refinement needed to reach target of 156 fields while maintaining correct table structures.
