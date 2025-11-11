# PDF Schema Extractor - Implementation Plan

> **STATUS UPDATE (2025-11-10 - End of Day)**:
> - ✅ **Phase 2 COMPLETE**: Gemini V2 integration with batching fully implemented and tested
> - ✅ V2 files: `gemini_models_v2.py`, `gemini_enhancer_v2.py`, `schema_merger_v2.py`, `test_gemini_extraction_v2.py`
> - ✅ Tested on I-90 form (132 fields): All spoken names unique, cost $0.0015/form
> - ✅ V1 files archived to `archive/v1_reference/`
> - ⏳ **Next Priority**: Phase 3 - Build orchestration pipeline and comprehensive testing
>
> See commit history for V2 implementation details.

## Overview
Upgrade the PDF schema extraction pipeline to use Gemini AI for enhanced field grouping, spoken names, help text, and conditional logic detection.

## Goals
1. Clean, maintainable extraction pipeline with clear separation of concerns
2. Gemini AI integration for semantic understanding
3. 100% widget coverage with bidirectional PDF mapping
4. Full conformance to `form_models.py` schema
5. Ready for schema-editor integration

---

## Phase 1: Foundation & Cleanup (Week 1)

### 1.1: Code Audit & Reorganization
**Goal**: Clean up existing code and establish clear module boundaries

**Tasks**:
- [x] Audit existing modules (completed in planning)
- [ ] Create `_archive/` folder and move deprecated code:
  - `automated_extractor.py` (salvage patterns, then archive)
  - `compare_schemas.py` (utility, move to tools/)
  - `_archive/enhanced_pdf_annotator.py` (already archived)
- [ ] Document what each keeper module does:
  - `widget_inventory.py` - Widget extraction
  - `heuristic_hierarchy_parser.py` - Tooltip parsing
  - `table_detection.py` - Table consolidation
  - `extract_field_order_from_labels.py` - Field ordering
  - `pdf_annotator.py` - Visual annotations
  - `extractor.py` - Main schema builder (to be refactored)

**Testing**:
```bash
# Verify existing modules still work
python widget_inventory.py test_pdfs/i-589.pdf
python pdf_annotator.py test_pdfs/i-589.pdf
python heuristic_hierarchy_parser.py test_pdfs/i-589.pdf
```

**Deliverable**: Clean module structure with archived cruft

---

### 1.2: Refactor `extractor.py`
**Goal**: Simplify extractor.py to orchestrate helpers instead of duplicating logic

**Tasks**:
- [ ] Create `extraction_helpers.py` for shared utilities:
  - `generate_semantic_field_id()`
  - `clean_field_name()`
  - `generate_spoken_name()` (initial heuristic)
  - `extract_help_text()`
  - `infer_validation()`
  - `extract_complete_metadata()`
- [ ] Refactor `extractor.py` to call helpers instead of inline logic
- [ ] Remove duplicate tooltip parsing (use `heuristic_hierarchy_parser.py`)
- [ ] Ensure extractor produces valid `FormSchema` conformant to `form_models.py`

**Testing**:
```bash
# Run extractor on test PDF
python extractor.py test_pdfs/i-589.pdf -o test_output/i-589_heuristic.json

# Validate against form_models.py
python -c "
from form_models import FormSchema
import json
with open('test_output/i-589_heuristic.json') as f:
    schema = FormSchema(**json.load(f))
    print('✓ Schema valid!')
"
```

**Deliverable**: Refactored `extractor.py` that produces valid schemas

---

### 1.3: Improve PDF Annotator
**Goal**: Ensure annotated PDFs are optimal for Gemini visual understanding

**Tasks**:
- [ ] Test current annotator with various PDFs
- [ ] Adjust font size/color for readability
- [ ] Ensure field IDs are unique and match schema exactly
- [ ] Add option to annotate with semantic IDs vs PDF field names
- [ ] Consider adding colored boxes around field groups (if helpful)

**Testing**:
```bash
# Create annotated PDF
python pdf_annotator.py test_pdfs/i-589.pdf -o test_output/i-589_annotated.pdf

# Manually review PDF to verify:
# - All fields have visible IDs
# - IDs are readable
# - IDs match schema field IDs
```

**Deliverable**: Improved `pdf_annotator.py` ready for Gemini

---

## Phase 2: Gemini Integration ✅ COMPLETE (2025-11-10)

### 2.1: Design Gemini Schemas ✅ COMPLETE
**Goal**: Define input/output Pydantic models for Gemini API

**Status**: ✅ Implemented as `gemini_models_v2.py` with 3 separate response types
- `SpokenNamesResponse` - spoken names + help_text field enhancements
- `GroupingsResponse` - radio/checkbox widget groupings
- `ConditionalsResponse` - conditional rules (optional)

**V2 Changes from Original Plan**:
- Split into 3 separate API call types instead of single combined response
- Batching support built into models (50 fields per call)
- Changed "warning" field to "help_text" based on user feedback
- Groupings explicitly filtered to radio/checkbox only

**Tasks**:
- [ ] Create `gemini_models.py` with Pydantic schemas:
  ```python
  # Input schema (what we send to Gemini)
  class SimplifiedField(BaseModel):
      id: str
      label: str
      type: str
      page: int
      position: Dict[str, float]

  class GeminiInput(BaseModel):
      fields: List[SimplifiedField]
      form_metadata: Dict[str, Any]

  # Output schema (what Gemini returns)
  class WidgetGroup(BaseModel):
      group_type: str  # "radio", "checkbox", "address", "related"
      field_ids: List[str]
      purpose: str
      spoken_name: Optional[str]

  class ConditionalRule(BaseModel):
      trigger_field_id: str
      operator: str
      value: Any
      affected_field_ids: List[str]
      action: str  # "show", "hide", "enable", "disable", "require"

  class FieldEnhancement(BaseModel):
      field_id: str
      spoken_name: Optional[str]
      spoken_aliases: Optional[List[str]]
      help_text: Optional[Dict[str, str]]  # {"inline": "...", "tooltip": "...", ...}
      validation: Optional[Dict[str, Any]]  # {"format_preset": "ssn", "required": true, ...}
      likely_type: Optional[str]  # Gemini's suggestion if different from heuristic

  class GeminiEnhancement(BaseModel):
      widget_groups: List[WidgetGroup]
      conditional_rules: List[ConditionalRule]
      field_enhancements: List[FieldEnhancement]
      confidence: float  # Overall confidence 0-1
      notes: Optional[str]  # Any warnings or observations
  ```

**Testing**:
```bash
# Validate models can serialize/deserialize
python -c "
from gemini_models import GeminiInput, GeminiEnhancement
import json

# Test input model
input_data = {
    'fields': [{'id': 'test', 'label': 'Test', 'type': 'text', 'page': 1, 'position': {'x': 0, 'y': 0}}],
    'form_metadata': {'title': 'Test Form'}
}
model = GeminiInput(**input_data)
print('✓ Input model valid')

# Test output model
output_data = {
    'widget_groups': [],
    'conditional_rules': [],
    'field_enhancements': [],
    'confidence': 0.9
}
model = GeminiEnhancement(**output_data)
print('✓ Output model valid')
"
```

**Deliverable**: ✅ `gemini_models_v2.py` with validated Pydantic schemas

**Testing Results**:
- ✅ All models import and serialize correctly
- ✅ Tested on I-90 form (132 fields)
- ✅ All spoken names unique (CRITICAL requirement met)
- ✅ Cost: $0.0015 per form

---

### 2.2: Create Gemini Enhancer Module ✅ COMPLETE
**Goal**: Implement Gemini API integration with structured outputs

**Status**: ✅ Implemented as `gemini_enhancer_v2.py` with batching and caching
- PDF upload using resumable upload protocol
- PDF URI caching (upload once, reuse across all API calls)
- Three separate enhancement methods: `enhance_spoken_names()`, `enhance_groupings()`, `enhance_conditionals()`
- BATCH_SIZE = 50 fields per call (tested safe limit to prevent truncation)
- Exponential backoff and error handling

**V2 Implementation Details**:
- Prevents response truncation issue found in V1 (100 fields caused 27k char truncation)
- Separate focused prompts for each enhancement type
- Groupings automatically filtered to radio/checkbox fields only
- Structured output via `responseMimeType: "application/json"` with response schemas

**Tasks**:
- [ ] Create `gemini_enhancer.py`:
  ```python
  from google import genai
  from dotenv import load_dotenv
  import os

  load_dotenv()

  class GeminiEnhancer:
      def __init__(self, model="gemini-2.0-flash-exp"):
          self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
          self.model = model

      def upload_pdf(self, pdf_path: str) -> str:
          """Upload PDF and return file URI"""
          pass

      def enhance_schema(
          self,
          annotated_pdf_path: str,
          simplified_schema: GeminiInput
      ) -> GeminiEnhancement:
          """Send annotated PDF + schema to Gemini, get enhancements"""
          pass

      def _build_prompt(self) -> str:
          """Build detailed prompt for Gemini"""
          pass

      def _parse_response(self, response) -> GeminiEnhancement:
          """Parse Gemini response into GeminiEnhancement model"""
          pass
  ```
- [ ] Implement PDF upload using resumable upload API (see `gemini_upload_pdfs.txt`)
- [ ] Implement structured output request using `response_schema` parameter
- [ ] Add exponential backoff retry logic for API failures
- [ ] Add cost tracking and logging

**Testing**:
```bash
# Test Gemini API connection
python -c "
from gemini_enhancer import GeminiEnhancer
enhancer = GeminiEnhancer()
print('✓ Gemini client initialized')
"

# Test PDF upload
python -c "
from gemini_enhancer import GeminiEnhancer
enhancer = GeminiEnhancer()
file_uri = enhancer.upload_pdf('test_pdfs/i-589.pdf')
print(f'✓ PDF uploaded: {file_uri}')
"
```

**Deliverable**: ✅ Working `gemini_enhancer_v2.py` with PDF upload and batching

**Testing Results**:
- ✅ PDF upload works correctly
- ✅ URI caching prevents re-uploads
- ✅ 3 batches processed for I-90 (50+50+32 fields)
- ✅ All API calls successful

---

### 2.3: Implement Gemini Prompt Engineering ✅ COMPLETE
**Goal**: Craft effective prompts for Gemini to extract semantic understanding

**CRITICAL REQUIREMENT**: All spoken names must be **unique** across the entire form to support JIT field loading for token reduction.

**Tasks**:
- [ ] Write detailed system prompt explaining task:
  ```
  You are a government form analysis expert. Your task is to analyze a PDF form
  and its field schema to identify:

  1. **Widget Groups**: Related fields that should be grouped together
     - Radio button groups (select one)
     - Checkbox groups (select all that apply)
     - Address blocks (street, city, state, zip)
     - Related fields (first name, middle name, last name)

  2. **Spoken Names**: Short, natural names for voice interaction
     - **CRITICAL**: Each spoken name must be UNIQUE across the entire form
     - Add context prefixes for disambiguation:
       * Address fields: "mailing street", "home street", "prior street"
       * Name fields: "your last name", "spouse's last name", "child's last name"
       * Date fields: "birth date", "entry date", "marriage date"
     - Keep names concise (2-4 words maximum)
     - Use natural conversational language
     - Prefer common abbreviations: "SSN", "A-Number", "I-94"
     - Examples:
       * "A-Number" instead of "Alien Registration Number (A-Number), if any"
       * "birth date" instead of "Enter Date of Birth (Mo/Day/Yr)"
       * "mailing zip code" instead of "ZIP Code (mailing address)"

  3. **Help Text**: User-friendly instructions for each field
     - inline: Brief hints like "(if any)" or "(optional)"
     - tooltip: Hover explanations
     - instructions: Detailed guidance
     - example: Sample valid values

  4. **Conditional Logic**: Fields that show/hide based on other fields
     - If field X = "Yes", show fields [Y, Z]
     - If field A is checked, require field B

  5. **Validation Rules**: Field format and constraints
     - SSN format: XXX-XX-XXXX
     - Phone format: (XXX) XXX-XXXX
     - Date constraints: past_only, future_only

  You will receive:
  - An annotated PDF with field IDs overlaid on the visual form
  - A simplified JSON schema mapping field IDs to labels and types

  Analyze the visual layout and semantic meaning to provide enhancements.

  **UNIQUENESS VALIDATION**: Before returning your response, verify that all
  spoken names are unique. If duplicates exist, add context prefixes to
  disambiguate them.
  ```
- [ ] Add examples of good groupings/spoken names/help text
- [ ] Add spoken name uniqueness validation examples
- [ ] Test prompt with sample PDFs and iterate

**Testing**:
```bash
# Test full enhancement pipeline
python test_gemini_enhancement.py test_pdfs/i-589.pdf
# Should output:
# - Widget groups identified
# - Spoken names generated
# - Help text suggestions
# - Conditional rules detected
```

**Status**: ✅ Prompts implemented in `gemini_enhancer_v2.py`
- Separate focused prompts for spoken names, groupings, and conditionals
- Emphasizes uniqueness requirement for spoken names
- Instructs to add context prefixes for disambiguation
- Examples and guidelines for each enhancement type

**Testing Results**:
- ✅ I-90 form: All 132 spoken names unique
- ✅ Confidence levels: 95% average across all batches
- ✅ 24 radio/checkbox groups identified correctly
- ✅ Spoken names natural and concise (2-4 words)

**Deliverable**: ✅ Effective Gemini prompts that produce quality enhancements

---

### 2.4: Build Schema Merger ✅ COMPLETE
**Goal**: Intelligently merge heuristic extraction with Gemini enhancements

**Status**: ✅ Implemented as `schema_merger_v2.py`
- Handles batched responses from multiple API calls
- Validates spoken name uniqueness (CRITICAL - raises error if duplicates found)
- Applies enhancements to correct form_models.py structure
- Stores help text in `field.help.inline`
- Stores groups in `field.group_id` and `field.group_label`
- Stores conditionals in `field.conditional_fields`

**V2 Implementation**:
- `apply_spoken_names()` - concatenates all batched responses, validates uniqueness
- `apply_groupings()` - applies radio/checkbox groups
- `apply_conditionals()` - tracks conditional relationships
- `get_enhancement_stats()` - reports on what was enhanced

**Tasks**:
- [ ] Create `schema_merger.py`:
  ```python
  from typing import List, Dict, Set
  from form_models import FormSchema, FormField
  from gemini_models import GeminiEnhancement

  class SchemaMerger:
      def __init__(self):
          self.conflicts = []
          self.warnings = []

      def merge(
          self,
          heuristic_schema: FormSchema,
          gemini_enhancement: GeminiEnhancement,
          widgets: List[Dict]
      ) -> FormSchema:
          """Merge heuristic + Gemini → final schema"""
          pass

      def _apply_groupings(self, schema: FormSchema, groups: List) -> FormSchema:
          """Apply widget groupings from Gemini"""
          pass

      def _apply_field_enhancements(self, schema: FormSchema, enhancements: List) -> FormSchema:
          """Apply spoken names, help text, validation from Gemini"""
          pass

      def _apply_conditional_rules(self, schema: FormSchema, rules: List) -> FormSchema:
          """Apply conditional logic from Gemini"""
          pass

      def _validate_coverage(self, schema: FormSchema, widgets: List[Dict]) -> bool:
          """Ensure 100% widget coverage"""
          pass

      def _validate_conformance(self, schema: FormSchema) -> bool:
          """Ensure schema conforms to form_models.py"""
          pass

      def _validate_spoken_name_uniqueness(self, schema: FormSchema) -> bool:
          """Ensure all spoken names are unique (CRITICAL for JIT field loading)"""
          pass
  ```
- [ ] Implement fuzzy matching for field IDs (adapt from `schema_builder_from_groupings.py`)
- [ ] Implement conflict resolution (Gemini wins if valid)
- [ ] Add validation checks:
  - **100% unique spoken names** (CRITICAL - blocks JIT field loading if violated)
  - 100% widget coverage
  - All field IDs unique
  - All references valid (section_ids, conditional field_ids, etc.)
  - Schema conforms to `form_models.py`

**Testing**:
```bash
# Test merger with mock data
python test_schema_merger.py

# Test full pipeline
python -c "
from extraction_pipeline import extract_pdf_schema
schema = extract_pdf_schema('test_pdfs/i-589.pdf')
print(f'✓ Extracted {len(schema.fields)} fields')
print(f'✓ Widget coverage: {schema.extraction_info.extraction_confidence * 100}%')
"
```

**Testing Results**:
- ✅ All modules import correctly
- ✅ Spoken name uniqueness validation works
- ✅ Enhancement statistics accurate
- ✅ Conforms to form_models.py structure

**Deliverable**: ✅ `schema_merger_v2.py` that produces valid, enhanced schemas

---

### 2.5: Testing Script ✅ COMPLETE
**Goal**: End-to-end testing script for V2 implementation

**Status**: ✅ Implemented as `test_gemini_extraction_v2.py`
- Complete CLI with argparse (pdf_path, schema_path, output, flags)
- Optional flags: `--skip-annotation`, `--skip-groupings`, `--skip-conditionals`
- Cost tracking across all batched API calls
- Enhancement statistics reporting
- Works with existing annotated PDFs

**Testing Results**:
- ✅ I-90 form processed successfully
- ✅ All 132 fields enhanced
- ✅ Outputs valid FormSchema JSON
- ✅ Cost estimation accurate ($0.0015/form)

**Deliverable**: ✅ Working test script with comprehensive options

---

### 2.6: Phase 2 Cleanup & Documentation ✅ COMPLETE

**Completed**:
- ✅ V1 files moved to `archive/v1_reference/`
- ✅ README.md updated with V2 info and cost estimates
- ✅ SCHEMA_EXTRACTION_UPGRADE_PLAN.md status note added
- ✅ All V2 files committed to git
- ✅ Attribute names fixed to match form_models.py

**What's Not Yet Done** (Phase 3 priorities):
- [ ] Full integration with heuristic extractor (currently requires pre-extracted schema)
- [ ] Orchestration pipeline that runs: extract → annotate → enhance → merge
- [ ] Comprehensive test suite with multiple PDFs
- [ ] Cost optimization and caching
- [ ] CLI tool for end users

---

## Phase 3: Orchestration & Testing ⏳ NEXT PRIORITY

**Current Status**: Phase 2 V2 implementation complete, ready for full pipeline integration

**Key Missing Pieces**:
1. Integration with heuristic extractor (V2 currently requires pre-extracted schemas)
2. Single command that goes from PDF → final enhanced schema
3. Batch processing for multiple PDFs
4. Comprehensive test suite
5. Production-ready CLI tool

---

### 3.1: Build Main Pipeline Orchestrator ⏳ PENDING
**Goal**: Clean entry point that coordinates all steps

**Priority**: HIGH - Needed to make V2 implementation usable end-to-end

**Updated Requirements**:
- Must call `test_gemini_extraction_v2.py` functionality (not duplicate code)
- Should integrate with existing heuristic extractor
- Need to determine: Does heuristic extractor output conform to form_models.py?
- If not, may need extractor refactoring first (see Phase 1.2)

**Tasks**:
- [ ] Create `extraction_pipeline.py`:
  ```python
  from pathlib import Path
  from typing import Optional
  import logging

  from widget_inventory import extract_widget_inventory
  from heuristic_hierarchy_parser import parse_all_tooltips
  from extractor import extract_schema as extract_heuristic_schema
  from pdf_annotator import annotate_pdf_with_field_names
  from gemini_enhancer import GeminiEnhancer
  from gemini_models import GeminiInput
  from schema_merger import SchemaMerger
  from form_models import FormSchema

  class ExtractionPipeline:
      def __init__(self, use_gemini: bool = True, gemini_model: str = "gemini-2.0-flash-exp"):
          self.use_gemini = use_gemini
          self.gemini_enhancer = GeminiEnhancer(model=gemini_model) if use_gemini else None
          self.logger = logging.getLogger(__name__)

      def extract(self, pdf_path: str, output_path: Optional[str] = None) -> FormSchema:
          """
          Extract schema from PDF with optional Gemini enhancement.

          Steps:
          1. Extract widgets with metadata
          2. Parse hierarchies and create initial schema (heuristic)
          3. Create annotated PDF (if using Gemini)
          4. Send to Gemini for enhancements (if enabled)
          5. Merge heuristic + Gemini → final schema
          6. Validate and save

          Args:
              pdf_path: Path to PDF file
              output_path: Optional path to save JSON schema

          Returns:
              FormSchema object
          """
          pass

      def _extract_heuristic(self, pdf_path: str) -> FormSchema:
          """Run heuristic extraction"""
          pass

      def _enhance_with_gemini(self, pdf_path: str, heuristic_schema: FormSchema):
          """Get Gemini enhancements"""
          pass

      def _merge_and_validate(self, heuristic_schema, gemini_data, widgets) -> FormSchema:
          """Merge and validate final schema"""
          pass

  def extract_pdf_schema(
      pdf_path: str,
      output_path: Optional[str] = None,
      use_gemini: bool = True
  ) -> FormSchema:
      """Convenience function for one-shot extraction"""
      pipeline = ExtractionPipeline(use_gemini=use_gemini)
      return pipeline.extract(pdf_path, output_path)
  ```
- [ ] Add progress logging at each step
- [ ] Add error handling with fallbacks
- [ ] Add cost tracking for Gemini API calls

**Testing**:
```bash
# Test full pipeline end-to-end
python extraction_pipeline.py test_pdfs/i-589.pdf -o test_output/i-589_final.json

# Test without Gemini (fallback)
python extraction_pipeline.py test_pdfs/i-589.pdf --no-gemini -o test_output/i-589_heuristic.json

# Validate output
python validate_schema.py test_output/i-589_final.json
```

**Deliverable**: Working end-to-end pipeline

---

### 3.2: Comprehensive Testing Suite
**Goal**: Ensure reliability and quality

**Tasks**:
- [ ] Create `tests/` directory with:
  - `test_widget_inventory.py` - Widget extraction tests
  - `test_heuristic_parser.py` - Tooltip parsing tests
  - `test_table_detection.py` - Table consolidation tests
  - `test_gemini_enhancer.py` - Gemini integration tests (may need mocks)
  - `test_schema_merger.py` - Merge logic tests
  - `test_validation.py` - Schema validation tests
  - `test_spoken_name_uniqueness.py` - **Spoken name uniqueness validation tests (CRITICAL)**
  - `test_integration.py` - Full pipeline tests
- [ ] Create test fixtures:
  - Sample PDFs (i-589, i-90, etc.)
  - Expected outputs for each step
  - Mock Gemini responses for deterministic testing
- [ ] Add pytest configuration
- [ ] Aim for >80% code coverage

**Testing**:
```bash
# Run all tests
pytest tests/ -v --cov=pdf_schema_extractor

# Run specific test file
pytest tests/test_gemini_enhancer.py -v

# Run with coverage report
pytest tests/ --cov=pdf_schema_extractor --cov-report=html
```

**Deliverable**: Comprehensive test suite

---

### 3.3: Performance & Cost Optimization
**Goal**: Minimize Gemini API costs and improve speed

**Tasks**:
- [ ] Implement caching for Gemini responses:
  - Cache by PDF hash to avoid re-processing same PDFs
  - Store in `_cache/` directory
- [ ] Optimize simplified schema sent to Gemini:
  - Only send essential fields
  - Limit label length to reduce tokens
- [ ] Add cost estimation before Gemini calls
- [ ] Add batch processing support for multiple PDFs
- [ ] Profile and optimize bottlenecks

**Testing**:
```bash
# Test caching
python extraction_pipeline.py test_pdfs/i-589.pdf  # First run (calls Gemini)
python extraction_pipeline.py test_pdfs/i-589.pdf  # Second run (uses cache)
# Should show: "Using cached Gemini response"

# Test cost estimation
python -c "
from extraction_pipeline import ExtractionPipeline
pipeline = ExtractionPipeline()
cost = pipeline.estimate_cost('test_pdfs/i-589.pdf')
print(f'Estimated cost: ${cost:.4f}')
"
```

**Deliverable**: Optimized pipeline with caching and cost tracking

---

## Phase 4: Documentation & Integration Prep (Week 4)

### 4.1: Documentation
**Goal**: Clear usage docs for future integration

**Tasks**:
- [ ] Create `README.md` with:
  - Overview of extraction pipeline
  - Installation instructions
  - Usage examples
  - API reference
- [ ] Create `ARCHITECTURE.md` explaining:
  - Module responsibilities
  - Data flow
  - Gemini integration details
- [ ] Add docstrings to all public functions
- [ ] Create `TROUBLESHOOTING.md` for common issues
- [ ] Document Gemini API requirements and costs

**Deliverable**: Complete documentation

---

### 4.2: CLI Tool
**Goal**: User-friendly command-line interface

**Tasks**:
- [ ] Create `cli.py`:
  ```python
  import click
  from extraction_pipeline import extract_pdf_schema

  @click.command()
  @click.argument('pdf_path', type=click.Path(exists=True))
  @click.option('-o', '--output', help='Output JSON path')
  @click.option('--no-gemini', is_flag=True, help='Skip Gemini enhancement')
  @click.option('--model', default='gemini-2.0-flash-exp', help='Gemini model')
  @click.option('--verbose', is_flag=True, help='Verbose logging')
  def extract(pdf_path, output, no_gemini, model, verbose):
      """Extract schema from PDF form"""
      pass
  ```
- [ ] Add progress bars with `rich` or `tqdm`
- [ ] Add colorful output for better UX
- [ ] Add validation checks before processing

**Testing**:
```bash
# Test CLI
python cli.py test_pdfs/i-589.pdf -o output.json --verbose
python cli.py test_pdfs/i-589.pdf --no-gemini
python cli.py --help
```

**Deliverable**: Polished CLI tool

---

### 4.3: Integration Preparation
**Goal**: Ready for schema-editor integration

**Tasks**:
- [ ] Define API contract for schema-editor:
  ```python
  # Expected interface
  def extract_pdf_schema(pdf_path: str) -> Dict[str, Any]:
      """
      Returns:
      {
        "schema": {...},  # FormSchema as dict
        "annotated_pdf_path": "...",
        "metadata": {
          "extraction_time": "...",
          "gemini_cost": 0.05,
          "confidence": 0.92,
          "warnings": []
        }
      }
      """
  ```
- [ ] Create integration examples
- [ ] Document expected inputs/outputs
- [ ] Prepare migration path for existing schemas

**Deliverable**: Integration-ready API

---

## Success Criteria

### Phase 1 (Foundation)
- [ ] All existing test PDFs extract successfully with heuristic pipeline
- [ ] Schemas conform to `form_models.py`
- [ ] Code is clean and well-documented
- [ ] No degradation from current extraction quality

### Phase 2 (Gemini)
- [ ] Gemini API integration works reliably
- [ ] Enhanced schemas show improvement over heuristic-only
- [ ] Gemini suggestions are >90% accurate
- [ ] **100% unique spoken names across all test forms** (CRITICAL - blocks token reduction)
- [ ] Cost per PDF is <$0.50

### Phase 3 (Integration)
- [ ] Full pipeline extracts schemas in <2 minutes per PDF
- [ ] Test coverage >80%
- [ ] All test PDFs pass validation
- [ ] Caching works correctly

### Phase 4 (Polish)
- [ ] Complete documentation
- [ ] CLI tool is user-friendly
- [ ] Ready for schema-editor integration

---

## Risk Mitigation

### Risk: Gemini API costs too high
**Mitigation**:
- Implement aggressive caching
- Use cheaper flash model instead of pro
- Batch process multiple PDFs
- Monitor costs and adjust

### Risk: Gemini enhancements are low quality
**Mitigation**:
- Extensive prompt engineering
- Human validation of sample outputs
- Fallback to heuristic if confidence is low
- Allow manual override of Gemini suggestions

### Risk: Schema merger conflicts
**Mitigation**:
- Clear conflict resolution rules (Gemini wins if valid)
- Log all conflicts for review
- Validation catches bad merges
- Allow user to review before saving

### Risk: Breaking changes to existing code
**Mitigation**:
- Archive old code, don't delete
- Maintain backward compatibility where possible
- Test against existing PDFs
- Version schemas clearly

---

## Timeline Summary

| Phase | Duration | Deliverables |
|-------|----------|-------------|
| 1: Foundation | Week 1 | Refactored codebase, improved annotator |
| 2: Gemini | Week 2 | Working Gemini integration, schema merger |
| 3: Testing | Week 3 | Full pipeline, test suite, optimization |
| 4: Polish | Week 4 | Documentation, CLI, integration prep |

**Total**: 4 weeks to production-ready extraction pipeline

---

## Next Steps

1. Review this plan with stakeholders
2. Set up development environment
3. Begin Phase 1.1: Code audit and reorganization
4. Schedule weekly check-ins to review progress

---

## Spoken Name Uniqueness - Integration with Token Reduction

### Why This Matters

The **Token Reduction Implementation Plan** (Phase 1) requires unique spoken names to support Just-In-Time (JIT) field loading. The manifest-first approach sends only field_id/spoken_name pairs initially, then loads complete field schemas as needed via voice commands.

**Without unique spoken names**, Gemini cannot reliably identify which field the user is referring to, breaking the JIT system.

### Implementation Strategy

1. **Gemini-Driven Generation** (Phase 2.3)
   - Gemini analyzes full form context to generate contextually-aware spoken names
   - Explicitly instructed to ensure uniqueness before returning results
   - Leverages visual understanding from annotated PDF

2. **Validation at Multiple Levels**
   - Schema merger validates uniqueness after Gemini enhancement (Phase 2.4)
   - Integration tests verify uniqueness on all test forms (Phase 3.2)
   - Success criteria blocks completion if any duplicates found

3. **Disambiguation Strategy**
   - Context prefixes: "mailing street" vs "home street" vs "prior street"
   - Relationship prefixes: "your last name" vs "spouse's last name"
   - Event prefixes: "birth date" vs "entry date" vs "marriage date"

### Fallback Strategy

If Gemini fails to produce unique names:

1. **Auto-fix in Schema Merger**: Detect duplicates and apply systematic disambiguation
2. **Manual Review Flag**: Mark schema for human review before deployment
3. **Block Production**: Do not deploy schemas with duplicate spoken names

### Verification Command

After schema extraction, verify uniqueness:

```bash
python -c "
from form_models import FormSchema
import json
from collections import Counter

with open('output_schema.json') as f:
    schema = FormSchema(**json.load(f))
    spoken_names = [field.spoken_name for field in schema.fields]
    duplicates = [name for name, count in Counter(spoken_names).items() if count > 1]

    if duplicates:
        print(f'❌ FAILED: Found {len(duplicates)} duplicate spoken names:')
        for name in duplicates:
            print(f'  - {name}')
        exit(1)
    else:
        print(f'✅ PASSED: All {len(spoken_names)} spoken names are unique')
"
```

### Impact on Timeline

- **No additional time required**: Uniqueness constraint integrates into existing Gemini prompt engineering (Phase 2.3)
- **Validation adds <5 minutes per form**: Automated check during testing
- **Blocks**: Token Reduction Phase 2 cannot begin until all schemas have unique spoken names

---

## Notes

- Each phase builds on previous phases
- Testing is continuous, not just Phase 3
- Gemini integration is modular - can be disabled if needed
- Focus on maintainability and clear interfaces
- Document as you go, not at the end
- **Spoken name uniqueness is a CRITICAL requirement for token reduction**
