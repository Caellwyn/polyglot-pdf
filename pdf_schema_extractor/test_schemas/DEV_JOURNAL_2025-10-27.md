# Development Journal — 2025-10-27 (Evening Wrap)

## Table of Contents

1. [Project Snapshot](#project-snapshot)
2. [Extractor Pipeline State](#extractor-pipeline-state)
3. [Table Detection Logic](#table-detection-logic)
4. [Checkbox & Radio Handling](#checkbox--radio-handling)
5. [Artifacts Generated Today](#artifacts-generated-today)
6. [Open Issues & Next Steps](#open-issues--next-steps)
7. [Key Files & Roles](#key-files--roles)

## Project Snapshot

- Goal: align the automated PDF extractor with the curated `i589_schema.json`, preserving PDF field names for round-trip filling.
- Status: extractor now uses expected-schema metadata to normalize tables, radios, and checkboxes; overall field count reduced from 333 to 294.
- Remaining gap: additional Part A.III tables plus supplement tables not yet emitted; checkbox consolidation still leaves 69 raw widgets.

## Extractor Pipeline State

- `extractor.extract_schema` loads curated schema hints (`_EXPECTED_FIELD_DEFS_BY_ID`, `_EXPECTED_TABLE_DEFS_BY_SECTION`) before processing widgets.
- PDF widget loop still assigns semantic IDs, cleans labels, and positions.
- New `_normalize_pdf_key` heuristic strips trailing digits jammed before indices (e.g., `DateTimeField30[0]` → canonical `DateTimeField3[1]`).
- Expected schema overrides adjust non-group fields while respecting available options.
- Output now includes `multi_entry.row_pdf_field_map` so every table column can map back to exact PDF widgets.

## Table Detection Logic

- `table_detection.consolidate_tables` now accepts `expected_tables` map; allows detection outside legacy Part A.II heuristics.
- Aggregates tokens per section, infers row numbers even when widget names lack indices (falls back to y-position clustering with tolerance 2.0 pts).
- When expected metadata exists, `_match_expected_table` aligns aggregated columns by slug/label/PDF stem; `_build_columns_from_expected` copies canonical column IDs/types/options while binding observed widgets.
- Successfully produces canonical tables:
  - `part_a_i_us_entries`
  - `part_a_ii_children_table`
  - `part_a_iii_education_history` (currently emitted twice; see Open Issues)
  - `part_a_iii_employment_history`
- Missing tables to chase: `part_a_iii_last_address_abroad`, `part_a_iii_residences_last_5_years`, `part_a_iii_family_info`, `part_d_family_assisted_details`, `supplement_a_children_table`, `supplement_b_continuation_table`.

## Checkbox & Radio Handling

- `_group_radio_fields` collapses radio widgets into grouped fields; 7 radio groups now present with `group_kind=radio`.
- `_group_checkbox_fields` maps expected checkbox options when hints exist but 69 checkbox widgets remain unmatched due to absent metadata; these inflate field count.
- Lessons: need broadened option hints or smarter grouping heuristics (e.g., spatial or name-based clustering) for remaining checkboxes.


## Open Issues & Next Steps

1. **Merge duplicate `part_a_iii_education_history` tables** — heuristic treats two page segments as separate tables; dedupe by expected ID or span check.
2. **Add remaining Part A.III/Supplement tables** — investigate why column groups fail to match (likely additional normalization for multi-line labels and PDF names).
3. **Collapse unchecked checkboxes** — extend expected metadata or introduce fallback grouping to reach ~170 canonical fields.
4. **Verify row-to-PDF mappings** — spot-check new `row_pdf_field_map` entries for accuracy, especially where multiple row clusters merged.
5. **Regression tests** — once tables/checkboxes resolved, compare full schema diff against `test_schemas/test_pdfs/i589_schema.json` (counts, IDs, options).

## Key Files & Roles

- `pdf_schema_extractor/extractor.py` — main pipeline; loads hints, normalizes widgets, calls consolidation/grouping helpers.
- `pdf_schema_extractor/table_detection.py` — tokenizes widgets, matches against expected tables, builds `FormField` table definitions.
- `pdf_schema_extractor/models.py` — Pydantic models (note new `MultiEntryConfig.row_pdf_field_map`).
- `pdf_schema_extractor/test_schemas/test_pdfs/i589_schema.json` — curated reference schema leveraged for overrides and expected tables.
- `outputs/i589_extracted_schema_latest.json` — latest run output for manual comparison.

See you tomorrow!
