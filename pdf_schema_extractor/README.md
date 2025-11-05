# PDF Schema Extractor

Extracts structured schemas from PDF forms (primarily USCIS immigration forms) to power multilingual voice AI form filling.

**Status:** Active development - Core extraction pipeline working, Gemini integration in progress

---

## Quick Reference

### What This Does

Converts PDF forms → JSON schemas with:
- Field types (text, checkbox, radio, select, date, etc.)
- Validation rules and constraints
- Conditional logic (show_if, unlock_when)
- Hierarchical organization (parts, sections, fields)
- Table detection (repeating field patterns)

### What You Need

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your-key-here"  # For future Gemini integration
```

---

## Core Files

### Production Pipeline (Working)

**Step 1: Extract Widget Inventory**
```bash
python widget_inventory.py <pdf_path>
```
- Extracts all editable PDF widgets
- Parses field flags (read_only, required, multiline, etc.)
- Outputs: `{form}_widgets.json`

**Step 2: Create Annotated PDF** (Optional - for debugging)
```bash
python pdf_annotator.py <pdf_path>
```
- Overlays field names on PDF for visual verification
- Outputs: `{form}-annotated.pdf`

**Step 3: Parse Tooltip Hierarchy**
```bash
python heuristic_hierarchy_parser.py <pdf_path>
```
- Extracts hierarchical question numbers from tooltips
- Parses section structure (Part 1.3.A format)
- Outputs: `{form}_hierarchy.json`

**Step 4: Build Complete Schema**
```bash
python schema_builder_from_groupings.py <pdf_path> <groupings_json>
```
- Combines widget inventory + groupings + hierarchy
- Applies fuzzy matching to group related fields
- Validates 100% widget coverage
- Outputs: `{form}_schema.json`

**Note:** `<groupings_json>` currently requires manual creation or Gemini extraction (tools in progress)

---

### Utility Scripts

**Extract Field Ordering**
```bash
python extract_field_order_from_labels.py <pdf> <schema_json> <output_json>
```
- Parses hierarchical question numbers (1.3.A, 2.4.B, etc.)
- Adds `question_number` and `pdf_position` to fields
- Ensures fields render in natural reading order

**Build Conditional Index**
```bash
python build_conditional_index.py <schema_json> <output_json>
```
- Creates bidirectional conditional logic index
- Maps trigger fields → dependent fields
- Maps dependent fields → trigger fields
- Adds `controls_fields` metadata to triggers

**Mutate PDF Field Flags** (Testing only)
```bash
python pdf_field_flag_mutator.py <pdf> <schema_json> <output_pdf>
```
- Flips read_only bits for testing unlock behavior
- Used to validate conditional field unlocking
- Generates test PDFs with modified field flags

---

### Core Library Modules

**form_models.py** (30KB)
- Pydantic v1.1.0 models for schema validation
- Defines: FormSchema, FormField, ConditionalDisplay, ValidationRules, etc.
- Single source of truth for schema structure

**table_detection.py** (40KB)
- Consolidates repeating widget patterns into semantic tables
- Detects children lists, employment history, address groups
- Uses heuristics: repeated stems, spatial clustering, label patterns

**extractor.py** (29KB)
- Main extraction engine (used by other scripts)
- Imports: form_models, table_detection
- Provides: FormSchema parsing, field grouping, validation

---

## Current Schemas

### I-90 (Green Card Replacement) ✅
- **Location:** `test_schemas/test_pdfs/i-90/i-90_schema.json`
- **Status:** v11 - Production ready
- **Fields:** 132 fields (consolidated from 137)
- **Coverage:** 99.5% (187/188 widgets)
- **Features:**
  - ✅ Full conditional logic (21 dependencies)
  - ✅ Hierarchical ordering (question_number)
  - ✅ Bidirectional conditional index
  - ✅ Round-trip tested (100% success)

### I-589 (Asylum Application) ⚠️
- **Location:** `test_schemas/test_pdfs/i-589/final_schema_minimal.json`
- **Status:** Complete but needs conformance update
- **Fields:** 303 fields
- **Coverage:** 100% (405/405 widgets)
- **Note:** Pre-dates v1.1.0 model updates

---

## Missing Pieces (In Progress)

**Gemini Integration Layer:**
- `gemini_grouping_extractor.py` - Extract semantic groups/tables from annotated PDFs
- `gemini_schema_enhancer.py` - Add spoken names, help text, validation hints
- `gemini_dependency_analyzer.py` - Auto-extract conditional dependencies

**Validation Pipeline:**
- `validate_schema.py` - Pydantic validation + reference checking
- `round_trip_tester.py` - Fill PDF + verify data integrity

**Dependency Tools:**
- `apply_csv_dependencies.py` - Apply manual CSV dependency mappings
- `review_dependencies.py` - Interactive dependency review/correction

**Note:** These tools exist in project history but are not yet integrated into the current branch. Will be restored as needed.

---

## Architecture Decisions

**Separation of Concerns:**
- **Python** (100% reliable): Widget extraction, coverage guarantees, structure validation
- **Gemini** (semantic): Field grouping, table detection, spoken names, help text
- **Human** (edge cases): Review complex conditionals, verify section boundaries

**Why This Works:**
- Python ensures 100% widget coverage (no fields lost)
- Gemini handles semantic understanding (what fields mean)
- Human review only for ambiguous cases (~5-10% of fields)

**Quality Targets:**
- Widget coverage: 100%
- Round-trip accuracy: 100%
- Conditional logic: 95%+ auto-extracted
- Section accuracy: 95%+

---

## Test Data

**I-90 Files:**
- `i-90.pdf` - Original USCIS form
- `i-90_schema.json` - Current schema (v11)
- `i-90_dependencies.csv` - Manual dependency mappings
- `i-90-annotated.pdf` - Debug visualization
- `I-90-filled-2025-11-04.pdf` - Test output

**I-589 Files:**
- `i-589.pdf` - Original USCIS form
- `final_schema_minimal.json` - Complete schema
- `i589_widgets_clean.json` - Widget inventory
- `gemini_groupings.json` - Gemini-extracted groups

---

## Archive

**_archive/enhanced_pdf_annotator.py**
- Enhanced annotator with group visualization
- Requires Gemini groupings file
- Kept for future reference

---

## Contributing

**Before modifying:**
1. Read `planning_documents/PROJECT_STATUS.md` for current state
2. Check `form_models.py` for schema structure (v1.1.0)
3. All schemas must validate against Pydantic models
4. Maintain 100% widget coverage in extraction

**When adding forms:**
1. Extract widgets: `widget_inventory.py`
2. Build schema: `schema_builder_from_groupings.py`
3. Validate: Check against form_models.py
4. Test: Round-trip fill + verify

---

## Support

**Questions?**
- Check `planning_documents/PROJECT_STATUS.md` - Detailed status
- Check `planning_documents/TECHNICAL_GUIDE.md` - Architecture
- Review code comments in core modules

**Issues?**
- Widget extraction: Check `widget_inventory.py`
- Schema validation: Check `form_models.py`
- Table detection: Check `table_detection.py`
