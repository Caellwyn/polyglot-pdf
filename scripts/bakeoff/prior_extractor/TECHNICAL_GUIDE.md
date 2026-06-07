# PDF Schema Extractor - Technical Guide

## Architecture Overview

```
PDF File
    ↓
widget_inventory.py → Extract widgets (PyMuPDF)
    ↓
heuristic_hierarchy_parser.py → Parse Part/Section/Question structure
    ↓
table_detection.py → Consolidate repeating patterns
    ↓
extract_field_order_from_labels.py → Sort by question numbers
    ↓
extractor.py → Generate initial schema
    ↓
pdf_annotator.py → Create annotated PDF
    ↓
[Phase 2] gemini_enhancer.py → AI enhancements
    ↓
[Phase 2] schema_merger.py → Merge heuristic + Gemini
    ↓
FormSchema (JSON conforming to form_models.py)
```

---

## Core Modules

### **form_models.py** - Schema Definition
**Status**: ✅ Stable - Do not modify without review

Pydantic models defining the canonical schema structure used by all downstream applications.

**Key Models**:
- `FormSchema` - Complete form definition
- `FormField` - Field with type, validation, help text, conditionals
- `FormSection`, `FormPart` - Hierarchical organization
- `TableColumn`, `MultiEntryConfig` - Multi-entry tables
- `ConditionalDisplay` - Show/hide logic
- `FieldOption` - Radio/checkbox/select options

### **widget_inventory.py** - Widget Extraction
**Status**: ✅ Stable

Extracts all form widgets from PDF using PyMuPDF.

**Key Functions**:
- `extract_widget_inventory(pdf_path)` - Main entry point
- `parse_field_flags(flags)` - Convert bit flags to booleans
- `format_for_gemini(widgets)` - Simplified output for AI

**Output**: Widget dictionaries with field_name, label, type, flags, position, options

### **heuristic_hierarchy_parser.py** - Tooltip Parsing
**Status**: ✅ Stable

Parses tooltip structure to extract Part/Section/Question hierarchy.

**Key Functions**:
- `parse_tooltip_hierarchy(tooltip)` - Regex-based extraction
- `extract_spoken_name(description)` - Clean field names

**Output**: Hierarchy with part, section, question, spoken_name

### **table_detection.py** - Table Consolidation
**Status**: ✅ Stable

Detects repeating field patterns (Child 1, Child 2...) and consolidates into TABLE fields.

**Key Functions**:
- `consolidate_tables(fields)` - Main entry point

**Output**: Fields with TABLE type, TableColumn definitions, row-to-PDF mapping

### **extract_field_order_from_labels.py** - Field Ordering
**Status**: ✅ Stable

Sorts fields by hierarchical question numbers (1.3.A, 2.4.B).

**Key Functions**:
- `extract_question_number(tooltip, label)` - Parse numbering
- `sort_by_question_number(widgets)` - Proper ordering

**Output**: Reordered schema with question_number and position metadata

### **pdf_annotator.py** - Visual Annotation
**Status**: ✅ Stable

Creates annotated PDFs with field IDs overlaid on form fields for Gemini visual reference.

**Key Functions**:
- `annotate_pdf_with_field_names(pdf_path, output_path)` - Main entry point

**Output**: Annotated PDF with field IDs displayed near each field

### **extractor.py** - Main Orchestrator
**Status**: ⚠️ Needs refactoring (Phase 1.2)

Orchestrates complete extraction pipeline and generates initial schema.

**Current Issues**:
- Mixes orchestration with helper utilities
- Will extract helpers to extraction_helpers.py in Phase 1.2

---

## Planned Modules (Phase 2+)

### **gemini_models.py** (Phase 2.1)
Pydantic models for Gemini API input/output:
- `GeminiInput` - Simplified schema sent to Gemini
- `GeminiEnhancement` - Groupings, spoken names, help text, conditionals
- `WidgetGroup`, `ConditionalRule`, `FieldEnhancement`

### **gemini_enhancer.py** (Phase 2.2)
Gemini API integration:
- Upload annotated PDF
- Send simplified schema
- Request structured enhancements
- Parse response into GeminiEnhancement

### **schema_merger.py** (Phase 2.4)
Merge heuristic + Gemini enhancements:
- Apply groupings, spoken names, help text
- Resolve conflicts (Gemini wins if valid)
- Validate 100% widget coverage
- Ensure conformance to form_models.py

### **extraction_pipeline.py** (Phase 3.1)
End-to-end orchestrator with caching, error handling, cost tracking

### **cli.py** (Phase 4.2)
Command-line interface

---

## Data Flow

### 1. Widget Extraction
```python
widgets = extract_widget_inventory(pdf_path)
# [{field_name, label, type, flags, position, ...}, ...]
```

### 2. Hierarchy Parsing
```python
hierarchies = parse_all_tooltips(widgets)
# {field_name: {part, section, question, spoken_name}, ...}
```

### 3. Initial Schema Generation
```python
fields = extractor.create_initial_fields(widgets, hierarchies)
# [FormField(...), ...]
```

### 4. Table Consolidation
```python
fields = table_detection.consolidate_tables(fields)
# Individual fields → TABLE fields with columns
```

### 5. Field Ordering
```python
fields = extract_field_order.reorder_fields(fields)
# Fields sorted by question number
```

### 6. PDF Annotation (Phase 2)
```python
annotated_pdf = pdf_annotator.annotate_pdf(pdf_path)
# PDF with field IDs overlaid
```

### 7. Gemini Enhancement (Phase 2)
```python
enhancements = gemini_enhancer.enhance_schema(annotated_pdf, fields)
# GeminiEnhancement with groupings, names, help, conditionals
```

### 8. Schema Merge (Phase 2)
```python
final_schema = schema_merger.merge(heuristic_fields, enhancements)
# FormSchema conforming to form_models.py
```

---

## Testing

Each module is independently testable:

```bash
# Widget extraction
python widget_inventory.py test_pdfs/i-589.pdf

# Hierarchy parsing
python heuristic_hierarchy_parser.py test_pdfs/i-589.pdf

# PDF annotation
python pdf_annotator.py test_pdfs/i-589.pdf

# Full extraction
python extractor.py test_pdfs/i-589.pdf -o output.json

# Validate conformance
python -c "
from form_models import FormSchema
import json
with open('output.json') as f:
    schema = FormSchema(**json.load(f))
    print(f'✓ Valid schema with {len(schema.fields)} fields')
"
```

---

## Key Design Principles

1. **100% Widget Coverage** - Every PDF field must be in schema
2. **Round-trip Fidelity** - Schema → PDF → Schema preserves data
3. **Voice-First** - Spoken names optimized for voice interaction
4. **Validation** - All schemas conform to form_models.py
5. **Modularity** - Single responsibility per module
6. **Testability** - Independent module testing
7. **Gemini Optional** - Heuristic extraction works standalone

---

## File Organization

```
pdf_schema_extractor/
├── README.md                          # User-facing documentation
├── TECHNICAL_GUIDE.md                 # This file (developer docs)
├── IMPLEMENTATION_PLAN.md             # Roadmap with progress tracking
├── requirements.txt                   # Python dependencies
├── .env                               # Gemini API key
│
├── form_models.py                     # ✅ Schema definitions
├── widget_inventory.py                # ✅ Widget extraction
├── heuristic_hierarchy_parser.py      # ✅ Tooltip parsing
├── table_detection.py                 # ✅ Table consolidation
├── extract_field_order_from_labels.py # ✅ Field ordering
├── pdf_annotator.py                   # ✅ PDF annotation
├── extractor.py                       # ⚠️ Needs refactoring
├── pdf_field_flag_mutator.py          # 🔧 Utility (unlock fields)
│
├── _archive/                          # Deprecated code
└── test_schemas/                      # Test PDFs and schemas
```

---

## Adding New Functionality

### Example: Add New Field Type

1. **Update form_models.py**:
```python
class FieldType(str, Enum):
    # ... existing types
    NEW_TYPE = "new_type"
```

2. **Update widget_inventory.py** to detect it:
```python
def extract_widget_inventory(pdf_path):
    # ... detect new type in widget processing
    if widget.special_property:
        widget_type = "new_type"
```

3. **Update extractor.py** to handle it:
```python
def create_field(widget, hierarchy):
    if widget['field_type'] == 'new_type':
        # ... create FormField with type=FieldType.NEW_TYPE
```

4. **Add tests**:
```python
def test_new_field_type():
    # ... test extraction
```

### Example: Add New Heuristic

1. **Create helper in extraction_helpers.py** (Phase 1.2):
```python
def detect_special_pattern(label: str, position: dict) -> bool:
    """Detect special field pattern."""
    return special_logic(label, position)
```

2. **Use in extractor.py**:
```python
from extraction_helpers import detect_special_pattern

if detect_special_pattern(field.name, field.position):
    # ... apply special handling
```

---

## Troubleshooting

### Widget Extraction Issues

**Problem**: Some fields not extracted
**Solution**: Check `should_exclude_widget()` in widget_inventory.py - may be filtering too aggressively

**Problem**: Field types wrong (radio vs checkbox)
**Solution**: Check `parse_field_flags()` - use flags, not just widget.field_type

### Hierarchy Parsing Issues

**Problem**: Part/Section not detected
**Solution**: Check tooltip format - may need new regex pattern in heuristic_hierarchy_parser.py

### Table Detection Issues

**Problem**: Repeating fields not consolidated
**Solution**: Check `_is_supported_section()` - may need to enable table detection for that section

### Schema Validation Failures

**Problem**: Schema doesn't conform to form_models.py
**Solution**: Run validation and check error details:
```python
try:
    schema = FormSchema(**data)
except ValidationError as e:
    print(e.errors())
```

---

## Performance Considerations

- **Widget extraction**: Fast (~1-2 seconds per PDF)
- **Heuristic processing**: Fast (~0.5 seconds)
- **Gemini API**: Slow (~10-30 seconds) + cost (~$0.10-0.50)
- **Caching**: Implemented in Phase 3 to avoid re-processing

---

## Dependencies

```
PyMuPDF (fitz)  # PDF parsing
pydantic        # Schema validation
python-dotenv   # Environment variables
google-genai    # Gemini API (Phase 2)
```

See requirements.txt for versions.

---

## Next Steps

See IMPLEMENTATION_PLAN.md for detailed roadmap and progress tracking.
