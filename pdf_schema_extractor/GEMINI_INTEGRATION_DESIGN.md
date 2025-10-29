# Gemini Integration Design

## Overview

This document outlines the architecture for integrating Gemini AI into the PDF schema extraction pipeline. The goal is to leverage Gemini's multimodal capabilities to infer semantic field types and validate table structures that are difficult to detect with pure heuristics.

## Architecture

### Hybrid Approach: Heuristics + Gemini

```
┌─────────────────────────────────────────────────────────────┐
│                     PDF EXTRACTION PIPELINE                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1: Heuristic Structure Detection                      │
│  - Extract raw PDF widgets                                   │
│  - Detect sections and parts                                 │
│  - Identify table patterns (rows/columns)                    │
│  - Group radio buttons by pdf_field_name                     │
│  - Preserve PDF field names for round-trip                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2: Gemini Semantic Enhancement                        │
│  - Infer field types (date, email, tel, textarea, etc.)      │
│  - Identify checkbox/radio groupings                         │
│  - Validate table structures                                 │
│  - Generate semantic field IDs and spoken names              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 3: Verification & Reconciliation                      │
│  - Verify Gemini output aligns with PDF widgets              │
│  - Ensure PDF field names are preserved                      │
│  - Check that all widgets are accounted for                  │
│  - Flag any discrepancies for manual review                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                   ┌──────────────────┐
                   │  FINAL SCHEMA    │
                   └──────────────────┘
```

## Use Cases for Gemini

### 1. Field Type Inference

**Problem**: PDF widgets only have basic types (text, checkbox, radio, select). We need semantic types (date, email, tel, textarea, signature, etc.).

**Gemini Solution**: Send field label + context to Gemini for classification.

**Example**:
```
Input to Gemini:
{
  "pdf_field_name": "PtAILine1_DOB[0]",
  "label": "Part. A. 1. Information About You. 1. Date of Birth (Mo/Yr)",
  "widget_type": "text",
  "height": 15.2,
  "width": 120.5
}

Gemini Response:
{
  "semantic_type": "date",
  "date_precision": "month_year",
  "format": "mm/yyyy",
  "validation": {
    "required": true,
    "date_constraint": "past_only"
  }
}
```

### 2. Checkbox/Radio Grouping

**Problem**: Multiple checkboxes that should be grouped as radio buttons or checkbox groups.

**Gemini Solution**: Analyze spatial layout + labels to identify groups.

**Example**:
```
Input to Gemini:
{
  "candidates": [
    {"pdf_field_name": "Checkbox_Sex_Male[0]", "label": "Sex. Select Male", "x": 100, "y": 200},
    {"pdf_field_name": "Checkbox_Sex_Female[0]", "label": "Sex. Select Female", "x": 200, "y": 200}
  ]
}

Gemini Response:
{
  "group_type": "radio",
  "field_id": "sex",
  "field_label": "Sex",
  "options": [
    {"value": "male", "label": "Male", "pdf_field_name": "Checkbox_Sex_Male[0]"},
    {"value": "female", "label": "Female", "pdf_field_name": "Checkbox_Sex_Female[0]"}
  ]
}
```

### 3. Table Validation

**Problem**: Heuristically detected tables may have wrong column groupings or IDs.

**Gemini Solution**: Validate table structure and suggest better column names/IDs.

**Example**:
```
Input to Gemini:
{
  "section": "part_a_iii",
  "detected_table": {
    "columns": [
      {"pdf_field_name": "TextField13[0]", "label": "Name of School"},
      {"pdf_field_name": "TextField13[1]", "label": "Type of School"},
      {"pdf_field_name": "TextField13[2]", "label": "Location"},
      {"pdf_field_name": "TextField13[3]", "label": "Dates Attended"}
    ],
    "rows": 3
  }
}

Gemini Response:
{
  "table_id": "part_a_iii_education_history",
  "table_name": "Education History",
  "validated": true,
  "column_suggestions": [
    {"id": "school_name", "label": "Name of School", "type": "text"},
    {"id": "school_type", "label": "Type of School", "type": "text"},
    {"id": "location", "label": "Location (City/Town, Country)", "type": "text"},
    {"id": "dates_attended", "label": "Dates Attended", "type": "text"}
  ]
}
```

## Implementation Plan

### Module Structure

```
pdf_schema_extractor/
├── extractor.py              # Main extraction (Phase 1: Heuristics)
├── gemini_enhancer.py        # NEW: Gemini semantic enhancement (Phase 2)
├── schema_verifier.py        # NEW: Verification logic (Phase 3)
├── table_detection.py        # Existing heuristic table detection
└── models.py                 # Pydantic models
```

### New Module: gemini_enhancer.py

```python
"""
Gemini-based semantic enhancement for PDF schema extraction.
"""

from typing import List, Dict, Any, Optional
import os
import requests
from .models import FormField, FieldType

class GeminiEnhancer:
    """Enhances heuristically-extracted schema using Gemini AI."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash-lite"):
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY')
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def infer_field_types(self, fields: List[FormField]) -> List[FormField]:
        """Infer semantic field types for all fields."""
        # Batch fields to reduce API calls
        batches = self._batch_fields(fields, batch_size=50)

        enhanced_fields = []
        for batch in batches:
            enhanced_batch = self._infer_field_types_batch(batch)
            enhanced_fields.extend(enhanced_batch)

        return enhanced_fields

    def identify_field_groups(self, fields: List[FormField]) -> Dict[str, List[FormField]]:
        """Identify checkbox/radio groups that should be consolidated."""
        # Group checkboxes by proximity and label similarity
        checkbox_candidates = [f for f in fields if f.type == FieldType.CHECKBOX]

        if not checkbox_candidates:
            return {}

        prompt = self._build_grouping_prompt(checkbox_candidates)
        response = self._call_gemini(prompt)
        groups = self._parse_grouping_response(response)

        return groups

    def validate_table(self, table_field: FormField) -> Dict[str, Any]:
        """Validate and enhance a detected table structure."""
        prompt = self._build_table_validation_prompt(table_field)
        response = self._call_gemini(prompt)
        validation = self._parse_table_validation(response)

        return validation

    def _call_gemini(self, prompt: str) -> str:
        """Make API call to Gemini."""
        url = f"{self.base_url}/models/{self.model}:generateContent"

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,  # Low temperature for consistent results
                "response_mime_type": "application/json"
            }
        }

        response = requests.post(
            f"{url}?key={self.api_key}",
            json=payload,
            timeout=60
        )
        response.raise_for_status()

        result = response.json()
        return result['candidates'][0]['content']['parts'][0]['text']

    def _build_field_type_prompt(self, field: FormField) -> str:
        """Build prompt for field type inference."""
        return f"""
Analyze this PDF form field and infer its semantic type.

Field Information:
- Label: {field.name}
- PDF Field Name: {field.pdf_field_name}
- Widget Type: {field.type.value}
- Section: {field.section_id}

Return JSON with this structure:
{{
  "semantic_type": "one of: text, textarea, date, email, tel, number, signature",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}

For date fields, also include:
{{
  "date_precision": "full|month_year|year_only",
  "format": "mm/dd/yyyy|mm/yyyy|yyyy"
}}

For textarea fields, also include:
{{
  "rows": estimated number of rows (2-20)
}}
"""

    # ... more helper methods
```

### New Module: schema_verifier.py

```python
"""
Verification logic to ensure Gemini output aligns with PDF structure.
"""

from typing import List, Dict, Set, Tuple
from .models import FormField, FormSchema

class SchemaVerifier:
    """Verifies that enhanced schema maintains integrity with PDF."""

    def verify_schema(self, pdf_widgets: List[Dict], schema: FormSchema) -> Dict[str, Any]:
        """
        Verify schema against PDF widgets.

        Returns:
            {
                "valid": bool,
                "errors": List[str],
                "warnings": List[str],
                "coverage": float (0-1)
            }
        """
        errors = []
        warnings = []

        # Check 1: All PDF widgets are accounted for
        pdf_field_names = {w['name'] for w in pdf_widgets}
        schema_pdf_names = set()

        for field in schema.fields:
            if field.pdf_field_name:
                schema_pdf_names.add(field.pdf_field_name)
            if field.type == FieldType.TABLE and field.columns:
                for col in field.columns:
                    if col.pdf_field_name:
                        schema_pdf_names.add(col.pdf_field_name)
            if field.options:
                for opt in field.options:
                    if opt.pdf_field_name:
                        schema_pdf_names.add(opt.pdf_field_name)

        missing_widgets = pdf_field_names - schema_pdf_names
        if missing_widgets:
            errors.append(f"Missing {len(missing_widgets)} PDF widgets in schema: {list(missing_widgets)[:5]}")

        # Check 2: No duplicate PDF field names
        pdf_name_usage = {}
        for field in schema.fields:
            if field.pdf_field_name:
                pdf_name_usage.setdefault(field.pdf_field_name, []).append(field.id)

        for pdf_name, field_ids in pdf_name_usage.items():
            if len(field_ids) > 1:
                warnings.append(f"PDF field {pdf_name} used by multiple schema fields: {field_ids}")

        # Check 3: Field type compatibility
        for widget in pdf_widgets:
            # Find corresponding schema field
            schema_field = self._find_field_by_pdf_name(schema, widget['name'])
            if schema_field:
                compatible = self._check_type_compatibility(widget['type'], schema_field.type)
                if not compatible:
                    errors.append(
                        f"Type mismatch: PDF widget {widget['name']} is {widget['type']}, "
                        f"but schema field {schema_field.id} is {schema_field.type}"
                    )

        coverage = len(schema_pdf_names) / len(pdf_field_names) if pdf_field_names else 0

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "coverage": coverage
        }

    def _find_field_by_pdf_name(self, schema: FormSchema, pdf_name: str) -> Optional[FormField]:
        """Find schema field by PDF field name."""
        for field in schema.fields:
            if field.pdf_field_name == pdf_name:
                return field
            # Check table columns
            if field.columns:
                for col in field.columns:
                    if col.pdf_field_name == pdf_name:
                        # Return a mock field for column
                        return FormField(
                            id=col.id,
                            name=col.label,
                            type=col.type,
                            section_id=field.section_id,
                            pdf_field_name=col.pdf_field_name
                        )
            # Check options
            if field.options:
                for opt in field.options:
                    if opt.pdf_field_name == pdf_name:
                        return field
        return None

    def _check_type_compatibility(self, widget_type: str, field_type: FieldType) -> bool:
        """Check if widget type is compatible with field type."""
        compatibility_map = {
            "text": [FieldType.TEXT, FieldType.TEXTAREA, FieldType.DATE, FieldType.EMAIL, FieldType.TEL, FieldType.NUMBER],
            "checkbox": [FieldType.CHECKBOX, FieldType.RADIO],  # Checkboxes can be grouped as radio
            "radio": [FieldType.RADIO],
            "select": [FieldType.SELECT],
            "signature": [FieldType.SIGNATURE],
        }

        return field_type in compatibility_map.get(widget_type, [])
```

## Integration into Main Pipeline

```python
# In extractor.py

def extract_schema(pdf_path: str, use_gemini: bool = True) -> FormSchema:
    """Extract schema with optional Gemini enhancement."""

    # PHASE 1: Heuristic extraction (existing code)
    doc = fitz.open(pdf_path)
    fields = []  # ... extract fields heuristically
    sections = []  # ... detect sections
    fields_with_tables = consolidate_tables(fields)  # ... detect tables
    grouped_fields = _group_radio_fields(fields_with_tables, sections)

    # PHASE 2: Gemini enhancement (NEW)
    if use_gemini:
        enhancer = GeminiEnhancer()

        # Infer field types
        print("  Enhancing with Gemini: inferring field types...")
        enhanced_fields = enhancer.infer_field_types(grouped_fields)

        # Identify field groups
        print("  Enhancing with Gemini: identifying field groups...")
        field_groups = enhancer.identify_field_groups(enhanced_fields)

        # Apply groupings
        final_fields = _apply_field_groups(enhanced_fields, field_groups)

        # Validate tables
        print("  Enhancing with Gemini: validating tables...")
        for field in final_fields:
            if field.type == FieldType.TABLE:
                validation = enhancer.validate_table(field)
                if validation.get('suggestions'):
                    field = _apply_table_suggestions(field, validation)
    else:
        final_fields = grouped_fields

    # Build schema
    schema = FormSchema(
        source=FormSource.PDF,
        form_metadata=extract_complete_metadata(doc),
        sections=sections,
        fields=final_fields,
        extraction_info=ExtractionInfo(...)
    )

    # PHASE 3: Verification (NEW)
    if use_gemini:
        verifier = SchemaVerifier()
        verification = verifier.verify_schema(
            pdf_widgets=[...],  # Raw widgets from PyMuPDF
            schema=schema
        )

        print(f"  Verification: {verification['coverage']*100:.1f}% coverage")
        if verification['errors']:
            print(f"  ⚠ {len(verification['errors'])} errors found")
            for error in verification['errors'][:5]:
                print(f"    - {error}")

        schema.extraction_info.manual_review_required = not verification['valid']

    return schema
```

## Error Handling

### Gemini API Failures

- **Timeout**: Retry up to 3 times with exponential backoff
- **Rate Limit**: Batch requests and add delay between batches
- **Invalid Response**: Fall back to heuristic result, log warning
- **Network Error**: Fall back to heuristic extraction

### Graceful Degradation

All Gemini features are optional. If `use_gemini=False` or Gemini fails, the extractor falls back to pure heuristics:

```python
try:
    enhanced_fields = enhancer.infer_field_types(fields)
except GeminiAPIError as e:
    print(f"⚠ Gemini enhancement failed: {e}. Using heuristic results.")
    enhanced_fields = fields  # Fall back to heuristics
```

## Testing Strategy

### Unit Tests

```python
def test_field_type_inference():
    """Test that Gemini correctly infers field types."""
    field = FormField(
        id="dob",
        name="Date of Birth (Mo/Yr)",
        type=FieldType.TEXT,
        pdf_field_name="PtAILine1_DOB[0]",
        ...
    )

    enhancer = GeminiEnhancer()
    enhanced = enhancer.infer_field_types([field])[0]

    assert enhanced.type == FieldType.DATE
    assert enhanced.date_precision == DatePrecision.MONTH_YEAR
```

### Integration Tests

```python
def test_full_extraction_with_gemini():
    """Test complete extraction pipeline with Gemini."""
    schema = extract_schema("i-589.pdf", use_gemini=True)

    # Verify field counts are close to ground truth
    assert len(schema.fields) in range(160, 180)  # Target: 170

    # Verify field types are correctly inferred
    date_fields = [f for f in schema.fields if f.type == FieldType.DATE]
    assert len(date_fields) >= 10  # Should detect most date fields

    # Verify tables are detected
    tables = [f for f in schema.fields if f.type == FieldType.TABLE]
    assert len(tables) >= 8  # Should detect most tables
```

## Cost Optimization

### Batch Processing

Process multiple fields in a single API call to reduce costs:

```python
def _infer_field_types_batch(fields: List[FormField], batch_size: int = 50):
    """Process up to 50 fields per API call."""
    prompt = f"Analyze these {len(fields)} form fields and infer types:\n\n"
    for i, field in enumerate(fields):
        prompt += f"{i+1}. Label: {field.name}, PDF: {field.pdf_field_name}\n"

    # ... make single API call for entire batch
```

### Caching

Cache Gemini responses for identical field patterns:

```python
cache_key = f"{field.name}:{field.pdf_field_name}:{field.type}"
if cache_key in response_cache:
    return response_cache[cache_key]
```

### Model Selection

- Use `gemini-2.0-flash-lite` for most tasks (fast, cheap)
- Use `gemini-1.5-pro` only for complex table validation if needed

## Next Steps

1. **Fix Gemini API Access** - Resolve 403 errors
2. **Implement `gemini_enhancer.py`** - Field type inference first
3. **Implement `schema_verifier.py`** - Ensure round-trip integrity
4. **Test with i-589.pdf** - Compare results with ground truth
5. **Iterate on Prompts** - Refine prompts for better accuracy
6. **Add More PDFs** - Test generalization to other forms
