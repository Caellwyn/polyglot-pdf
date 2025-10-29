# Gemini-Assisted PDF Schema Extraction Guide

## Overview

This guide documents the hybrid approach for extracting form schemas from PDF files using Gemini AI + heuristics.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    PDF Form Input                        │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  Phase 1: PDF Upload & Preprocessing                    │
│  - Upload PDF to Gemini File API                        │
│  - Wait for processing (ACTIVE state)                   │
│  - Extract raw widgets with PyMuPDF                      │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  Phase 2: Section Detection (Auto)                      │
│  - Detect form parts/sections from PDF                  │
│  - Calculate optimal chunk size (~25-40 fields/chunk)   │
│  - Generate section boundaries                          │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  Phase 3: Chunked Gemini Extraction                     │
│  - Extract each section separately                      │
│  - Apply data model constraints                         │
│  - Consolidate checkboxes → radio groups               │
│  - Detect tables with columns                          │
│  - Infer semantic field types                          │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  Phase 4: Schema Merging                                │
│  - Combine all section schemas                          │
│  - Resolve cross-section references                     │
│  - Validate completeness                                │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  Phase 5: Verification (Multi-Layer)                    │
│  - Widget coverage check (95%+ required)                │
│  - Type compatibility validation                        │
│  - Heuristic cross-validation                          │
│  - Structural consistency check                         │
└─────────────────────────────────────────────────────────┘
                           ↓
                  ┌──────────────┐
                  │ Final Schema │
                  └──────────────┘
```

## Key Components

### 1. PDF Upload (Gemini File API)

**Why**: Gemini's multimodal capabilities require the file to be uploaded first.

**API Pattern**:
```python
# Step 1: Initial resumable request
POST https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}
Headers:
  X-Goog-Upload-Protocol: resumable
  X-Goog-Upload-Command: start
  X-Goog-Upload-Header-Content-Length: {file_size}
  X-Goog-Upload-Header-Content-Type: application/pdf
  Content-Type: application/json
Body:
  {"file": {"display_name": "form.pdf"}}

Response Headers:
  X-Goog-Upload-URL: {upload_url}

# Step 2: Upload file bytes
PUT {upload_url}
Headers:
  Content-Length: {file_size}
  X-Goog-Upload-Offset: 0
  X-Goog-Upload-Command: upload, finalize
Body: {binary_pdf_data}

Response:
  {"file": {"uri": "...", "name": "files/..."}}

# Step 3: Wait for processing
GET https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}
Poll until: state == "ACTIVE"
```

**Key Learnings**:
- Files can take 20+ seconds to process
- Must poll for ACTIVE state before using
- File URI is reusable for multiple requests

### 2. Section Detection (Auto)

**Why**: Need to chunk extraction to work around 8K token output limit.

**Strategies**:

**Strategy A: Heuristic Section Detection** (Recommended)
```python
def detect_sections(pdf_path):
    """Auto-detect sections from PDF structure."""
    doc = fitz.open(pdf_path)
    sections = []

    # Look for section headers (large text, bold, patterns like "Part A", "Section 1")
    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if is_section_header(block):
                sections.append({
                    "id": generate_section_id(block["text"]),
                    "title": block["text"],
                    "page": page_num,
                    "y_position": block["bbox"][1]
                })

    # Calculate field count per section
    for i, section in enumerate(sections):
        start_page = section["page"]
        end_page = sections[i+1]["page"] if i+1 < len(sections) else len(doc)
        section["estimated_fields"] = estimate_field_count(doc, start_page, end_page)

    return sections
```

**Strategy B: Fixed Chunking**
```python
def create_fixed_chunks(total_widgets, chunk_size=30):
    """Create evenly-sized chunks if no section structure."""
    num_chunks = (total_widgets + chunk_size - 1) // chunk_size
    return [
        {
            "id": f"chunk_{i+1}",
            "title": f"Fields {i*chunk_size+1}-{min((i+1)*chunk_size, total_widgets)}",
            "start_idx": i * chunk_size,
            "end_idx": min((i+1) * chunk_size, total_widgets)
        }
        for i in range(num_chunks)
    ]
```

**Strategy C: Hybrid** (Best)
- Use heuristic detection first
- If sections are too large (>50 fields), subdivide
- If no sections found, use fixed chunking

### 3. Data Model Definition

**Critical**: Give Gemini our EXACT Pydantic model structure in JSON Schema format.

**Why**:
- Ensures conformance to our models
- No parsing errors
- Direct validation possible
- Consistent output format

**Example**:
```json
{
  "fields": [
    {
      "id": "unique_field_id",
      "name": "Display Label",
      "spoken_name": "How to say it",
      "type": "text|textarea|date|number|tel|email|select|radio|checkbox|signature|table",
      "section_id": "section_id",
      "section_label": "Section Title",
      "pdf_field_name": "ActualPDFFieldName[0]",
      "description": "What this field asks for",

      "group_id": "group_name (for radio/checkbox groups)",
      "group_label": "Group Label",
      "group_kind": "radio|checkbox",
      "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "CheckboxYes[0]"}
      ],

      "columns": [
        {"id": "col_id", "label": "Column Header", "type": "text"}
      ],
      "multi_entry": {
        "min_entries": 1,
        "max_entries": 4
      }
    }
  ]
}
```

### 4. Gemini Prompting Strategy

**Template**:
```
Extract ONLY the fields from "{section_title}" of this form.

**Data Model** (follow this EXACT structure):
{data_model_json}

**Your Task:**
1. Extract ALL fields from {section_title}
2. Group related checkboxes as radio/checkbox groups
3. Detect tables with column definitions
4. Infer semantic field types (date, email, tel, textarea, number, signature)
5. Include pdf_field_name from the actual PDF

**Requirements:**
- Consolidate Yes/No checkbox pairs → radio groups
- Consolidate mutually exclusive checkboxes → radio groups
- Detect repeating row patterns → tables
- Use semantic types based on field labels
- MUST include "pdf_field_name" for round-trip filling

Return JSON:
{
  "section_id": "{section_id}",
  "section_title": "{section_title}",
  "total_fields": 0,
  "fields": [...]
}

Extract ONLY fields from {section_title}. Don't include other sections!
```

**Key Elements**:
- Clear section boundary
- Exact data model
- Specific requirements (grouping, typing, etc.)
- Constrained output format
- Emphasis on PDF field names

### 5. Schema Merging

**Challenge**: Combine multiple section extractions into coherent schema.

**Algorithm**:
```python
def merge_section_schemas(section_extractions, pdf_widgets):
    """Merge all section schemas."""
    all_fields = []
    field_ids_seen = set()

    for section_data in section_extractions:
        for field in section_data["fields"]:
            # Deduplicate by ID
            if field["id"] not in field_ids_seen:
                all_fields.append(field)
                field_ids_seen.add(field["id"])
            else:
                # Handle duplicates (log warning)
                print(f"Warning: Duplicate field ID {field['id']}")

    # Cross-section validation
    validate_cross_references(all_fields)

    # Widget coverage check
    coverage = calculate_widget_coverage(pdf_widgets, all_fields)

    return {
        "total_fields": len(all_fields),
        "fields": all_fields,
        "coverage": coverage,
        "sections": [s for s in section_extractions]
    }
```

## Lessons Learned

### What Works

✅ **Chunked Extraction**
- Sections of 20-40 fields extract reliably
- Respects section boundaries
- No token limit issues

✅ **Giving Gemini Exact Data Model**
- Output conforms to Pydantic models
- No parsing errors
- Direct validation possible

✅ **Table Detection**
- Gemini finds 240% more tables than heuristics
- Accurate column detection
- High confidence (95%+)

✅ **Radio Grouping**
- Identifies mutually exclusive checkboxes
- Consolidates Yes/No pairs
- Reduces field count significantly

✅ **Field Type Inference**
- 90-95% accuracy on semantic types
- Handles date, email, tel, textarea, number, signature
- Better than pure heuristics

### What Doesn't Work

❌ **Single Large Request**
- Hits 8K token output limit (~900 lines)
- Response truncates mid-field

❌ **Vague Prompts**
- Produces inconsistent structure
- Hard to parse
- Missing required fields

❌ **No Section Boundaries**
- Extracts from wrong sections
- Includes duplicate fields

❌ **Inline Base64 PDF**
- Doesn't work reliably
- Must use File Upload API

### Optimal Configuration

**Model**: `gemini-2.0-flash-exp`
- Fast (2-3 seconds per section)
- Accurate for classification
- Supports 8K output tokens
- Cost-effective

**Chunking**: 25-40 fields per section
- Stays well under token limit
- Allows detailed output
- Section-aligned

**Temperature**: 0.1
- Deterministic output
- Consistent structure
- Minimal hallucinations

## Cost Analysis

**Per PDF Form**:
- Upload: ~1 MB = negligible cost
- Section extractions: 5-10 API calls × $0.002 = $0.01-0.02
- Field type enhancement: 10-15 batches × $0.001 = $0.01-0.015

**Total**: ~$0.02-0.04 per PDF

**At Scale**:
- 100 PDFs: ~$2-4
- 1,000 PDFs: ~$20-40

Very affordable for production use.

## Error Handling

### API Failures

```python
def call_gemini_with_retry(file_uri, prompt, max_retries=3):
    """Call Gemini with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return call_gemini(file_uri, prompt)
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"Timeout, retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Rate limit
                time.sleep(10)
            else:
                raise
```

### Graceful Degradation

```python
def extract_with_fallback(pdf_path, section):
    """Try Gemini, fall back to heuristics."""
    try:
        return extract_section_with_gemini(pdf_path, section)
    except Exception as e:
        print(f"Gemini failed: {e}, using heuristics")
        return extract_section_heuristic(pdf_path, section)
```

## Testing Strategy

### Unit Tests
- Test section detection on various PDFs
- Test prompt generation
- Test schema merging logic
- Test error handling

### Integration Tests
- Full extraction on known PDFs
- Compare with ground truth (if available)
- Verify widget coverage
- Test round-trip filling

### Verification Tests
- Widget coverage >= 95%
- Type compatibility 100%
- Structural consistency
- No hallucinated fields

## Next Steps

1. ✅ Chunked extraction working (first 3 sections)
2. 🔄 Generalize to form-agnostic pipeline
3. 📋 Extract all remaining sections
4. 📋 Build verification system
5. 📋 Compare with canonical schema
6. 📋 Test on additional PDF forms

## References

- Gemini API Docs: https://ai.google.dev/docs
- File Upload Guide: `gemini_rest_api_guides/gemini_upload_pdfs.txt`
- Structured Output: `gemini_rest_api_guides/gemini_structured_outputs.txt`
- Pydantic Models: `models.py`
