#!/usr/bin/env python3
"""
Form-agnostic Gemini-assisted PDF schema extraction.

This module can extract schemas from ANY PDF form using Gemini AI.
No form-specific logic. Fully generalizable.
"""

import os
import json
import time
import requests
import fitz
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class Section:
    """Detected section in PDF."""
    id: str
    title: str
    page_start: int
    page_end: int
    estimated_fields: int

@dataclass
class ExtractionResult:
    """Result of Gemini extraction."""
    success: bool
    section_id: str
    fields: List[Dict[str, Any]]
    raw_response: str
    error: Optional[str] = None

class GeminiExtractor:
    """Form-agnostic PDF schema extractor using Gemini AI."""

    # Data model template (Pydantic-compatible JSON)
    DATA_MODEL_SCHEMA = """
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

      "group_id": "group_name",
      "group_label": "Group Label",
      "group_kind": "radio|checkbox",
      "options": [
        {"value": "yes", "label": "Yes", "pdf_field_name": "CheckboxYes[0]"}
      ],

      "columns": [
        {"id": "col_id", "label": "Column Header", "type": "text", "pdf_field_name": "Field[0]"}
      ],
      "multi_entry": {
        "min_entries": 1,
        "max_entries": 4,
        "initial_rows": 4
      }
    }
  ]
}
"""

    def __init__(self, api_key: Optional[str] = None, model: str = 'gemini-2.0-flash-exp'):
        """Initialize extractor."""
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com"

    def extract_schema(self, pdf_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract complete schema from PDF form.

        Args:
            pdf_path: Path to PDF file
            output_dir: Optional directory to save intermediate results

        Returns:
            Complete schema dict with all fields
        """
        print(f"\n{'='*60}")
        print(f"GEMINI FORM-AGNOSTIC EXTRACTION")
        print(f"{'='*60}")
        print(f"PDF: {pdf_path}")

        # Setup output directory
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
        else:
            output_path = Path(pdf_path).parent

        # Step 1: Upload PDF to Gemini
        print(f"\n[1/5] Uploading PDF to Gemini...")
        file_uri = self._upload_pdf(pdf_path)
        print(f"  File URI: {file_uri}")

        # Step 2: Detect sections
        print(f"\n[2/5] Detecting sections...")
        sections = self._detect_sections(pdf_path)
        print(f"  Found {len(sections)} sections:")
        for i, section in enumerate(sections, 1):
            print(f"    {i}. {section.title} (pages {section.page_start}-{section.page_end}, ~{section.estimated_fields} fields)")

        # Step 3: Extract each section
        print(f"\n[3/5] Extracting sections with Gemini...")
        section_results = []
        for i, section in enumerate(sections, 1):
            print(f"\n  Extracting {i}/{len(sections)}: {section.title}")
            result = self._extract_section(file_uri, section)

            if result.success:
                print(f"    [PASS] {len(result.fields)} fields extracted")
                # Save intermediate result
                if output_dir:
                    chunk_path = output_path / f"chunk_{section.id}.json"
                    with open(chunk_path, 'w', encoding='utf-8') as f:
                        json.dump({
                            "section": section.__dict__,
                            "fields": result.fields,
                            "raw_response": result.raw_response
                        }, f, indent=2)
            else:
                print(f"    [ERROR] {result.error}")

            section_results.append(result)

        # Step 4: Merge sections
        print(f"\n[4/5] Merging section schemas...")
        merged_schema = self._merge_sections(section_results)
        print(f"  Total fields: {len(merged_schema['fields'])}")

        # Step 5: Validate
        print(f"\n[5/5] Validating schema...")
        validation = self._validate_schema(pdf_path, merged_schema)
        print(f"  Widget coverage: {validation['coverage']*100:.1f}%")
        if validation['warnings']:
            print(f"  Warnings: {len(validation['warnings'])}")

        # Save final schema
        output_file = output_path / "gemini_extracted_schema.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(merged_schema, f, indent=2)

        print(f"\n{'='*60}")
        print(f"Extraction complete!")
        print(f"Output: {output_file}")
        print(f"{'='*60}\n")

        return merged_schema

    def _upload_pdf(self, pdf_path: str) -> str:
        """Upload PDF to Gemini File API."""
        file_size = os.path.getsize(pdf_path)
        display_name = Path(pdf_path).name

        # Step 1: Initial resumable request
        initial_headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": "application/pdf",
            "Content-Type": "application/json"
        }

        initial_response = requests.post(
            f"{self.base_url}/upload/v1beta/files?key={self.api_key}",
            headers=initial_headers,
            json={"file": {"display_name": display_name}},
            timeout=30
        )
        initial_response.raise_for_status()

        upload_url = initial_response.headers.get("X-Goog-Upload-URL")
        if not upload_url:
            raise ValueError("No upload URL in response")

        # Step 2: Upload file bytes
        with open(pdf_path, 'rb') as f:
            file_data = f.read()

        upload_headers = {
            "Content-Length": str(file_size),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize"
        }

        upload_response = requests.put(upload_url, headers=upload_headers, data=file_data, timeout=60)
        upload_response.raise_for_status()

        file_info = upload_response.json()
        file_uri = file_info['file']['uri']
        file_name = file_info['file']['name']

        # Step 3: Wait for processing
        for attempt in range(10):
            check_response = requests.get(f"{self.base_url}/v1beta/{file_name}?key={self.api_key}", timeout=10)
            check_response.raise_for_status()
            state = check_response.json().get('file', {}).get('state', 'PROCESSING')

            if state == 'ACTIVE':
                break
            elif state == 'FAILED':
                raise ValueError("File processing failed")

            time.sleep(2)

        return file_uri

    def _detect_sections(self, pdf_path: str) -> List[Section]:
        """
        Auto-detect sections from PDF structure.
        Form-agnostic: works on any PDF.
        """
        doc = fitz.open(pdf_path)
        sections = []

        # Extract all widgets for field count estimation
        # Store as (page_num, widget) tuples
        all_widgets = []
        for page_num, page in enumerate(doc):
            for widget in page.widgets():
                all_widgets.append((page_num, widget))

        # Strategy 1: Look for section headers (large bold text, patterns like "Part", "Section")
        section_candidates = []
        for page_num, page in enumerate(doc):
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block:
                    continue

                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        size = span["size"]
                        flags = span["flags"]  # font flags (bold, italic, etc.)

                        # Heuristic: Section headers are usually:
                        # - Larger font (>12pt)
                        # - Bold (flags & 16)
                        # - Start with "Part", "Section", etc.
                        # - Or are numbered ("1.", "A.", "I.")
                        if self._is_section_header(text, size, flags):
                            section_candidates.append({
                                "text": text,
                                "page": page_num,
                                "y": block["bbox"][1],
                                "size": size
                            })

        # If we found section headers, use them
        if section_candidates:
            for i, candidate in enumerate(section_candidates):
                section_id = self._generate_section_id(candidate["text"])
                page_start = candidate["page"]
                page_end = section_candidates[i+1]["page"] if i+1 < len(section_candidates) else len(doc)

                # Estimate field count (all_widgets is list of (page_num, widget) tuples)
                estimated_fields = sum(
                    1 for page_num, w in all_widgets
                    if page_start <= page_num < page_end
                )

                sections.append(Section(
                    id=section_id,
                    title=candidate["text"],
                    page_start=page_start,
                    page_end=page_end,
                    estimated_fields=max(5, estimated_fields // (page_end - page_start + 1))
                ))
        else:
            # Strategy 2: Fixed chunking if no section structure
            # Aim for ~30-40 fields per chunk
            total_widgets = len(all_widgets)
            chunk_size = 35
            num_chunks = (total_widgets + chunk_size - 1) // chunk_size

            for i in range(num_chunks):
                start_idx = i * chunk_size
                end_idx = min((i+1) * chunk_size, total_widgets)

                sections.append(Section(
                    id=f"chunk_{i+1}",
                    title=f"Fields {start_idx+1}-{end_idx}",
                    page_start=0,  # Will extract by field index instead
                    page_end=len(doc),
                    estimated_fields=end_idx - start_idx
                ))

        return sections

    def _is_section_header(self, text: str, size: float, flags: int) -> bool:
        """Check if text looks like a section header."""
        if not text or len(text) < 3:
            return False

        # Check font size (>11pt)
        if size < 11:
            return False

        # Check for bold (flag bit 16)
        is_bold = (flags & 16) != 0

        # Check for section patterns
        text_lower = text.lower()
        patterns = [
            text_lower.startswith("part "),
            text_lower.startswith("section "),
            text_lower.startswith("supplement "),
            "information about" in text_lower,
            "to be completed" in text_lower,
        ]

        # Check for numbered headers
        import re
        numbered = bool(re.match(r'^([A-Z]\.?|[IVX]+\.?|\d+\.?)\s+', text))

        return (is_bold and any(patterns)) or (is_bold and numbered and size > 12)

    def _generate_section_id(self, title: str) -> str:
        """Generate clean section ID from title."""
        import re
        # Remove special characters, convert to lowercase, replace spaces with underscores
        clean = re.sub(r'[^\w\s]', '', title.lower())
        clean = re.sub(r'\s+', '_', clean.strip())
        return clean[:50]  # Limit length

    def _extract_section(self, file_uri: str, section: Section) -> ExtractionResult:
        """Extract one section using Gemini."""
        prompt = f"""
Extract ONLY the fields from "{section.title}" of this form.

**CRITICAL**: Follow this EXACT data model structure:

{self.DATA_MODEL_SCHEMA}

**Your Task:**
1. Extract ALL fields from {section.title}
2. Group related checkboxes as radio/checkbox groups
3. Detect tables with column definitions
4. Infer semantic field types (date, email, tel, textarea, number, signature)
5. Include pdf_field_name from the actual PDF form

**Requirements:**
- Consolidate Yes/No checkbox pairs → radio groups
- Consolidate mutually exclusive checkboxes (sex, marital status, etc.) → radio groups
- Detect repeating row patterns → tables with columns
- Use semantic types: date for dates, textarea for long text fields, tel for phones, etc.
- MUST include "pdf_field_name" field for round-trip filling
- For tables, define columns with their types

Return JSON:
{{
  "section_id": "{section.id}",
  "section_title": "{section.title}",
  "total_fields": 0,
  "fields": [
    // ... array of fields following the data model above
  ],
  "notes": "Any observations about this section"
}}

Extract ONLY fields from {section.title}. Don't include fields from other sections!
"""

        try:
            response_text = self._call_gemini(file_uri, prompt)

            # Parse response
            response_data = json.loads(response_text)

            return ExtractionResult(
                success=True,
                section_id=section.id,
                fields=response_data.get("fields", []),
                raw_response=response_text
            )

        except Exception as e:
            return ExtractionResult(
                success=False,
                section_id=section.id,
                fields=[],
                raw_response="",
                error=str(e)
            )

    def _call_gemini(self, file_uri: str, prompt: str) -> str:
        """Call Gemini API."""
        url = f'{self.base_url}/v1beta/models/{self.model}:generateContent?key={self.api_key}'

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"file_data": {"mime_type": "application/pdf", "file_uri": file_uri}}
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "maxOutputTokens": 8192
            }
        }

        response = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=180)
        response.raise_for_status()

        return response.json()['candidates'][0]['content']['parts'][0]['text']

    def _merge_sections(self, section_results: List[ExtractionResult]) -> Dict[str, Any]:
        """Merge all section extractions into complete schema."""
        all_fields = []
        field_ids_seen = set()

        for result in section_results:
            if not result.success:
                continue

            for field in result.fields:
                # Deduplicate by ID
                field_id = field.get("id", "")
                if field_id and field_id not in field_ids_seen:
                    all_fields.append(field)
                    field_ids_seen.add(field_id)

        # Count field types
        type_counts = {}
        for field in all_fields:
            ftype = field.get("type", "unknown")
            type_counts[ftype] = type_counts.get(ftype, 0) + 1

        return {
            "total_fields": len(all_fields),
            "fields": all_fields,
            "field_type_summary": type_counts,
            "sections": [r.section_id for r in section_results if r.success]
        }

    def _validate_schema(self, pdf_path: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Basic validation of extracted schema."""
        doc = fitz.open(pdf_path)

        # Get all PDF widgets
        pdf_widgets = []
        for page in doc:
            pdf_widgets.extend(page.widgets())

        pdf_field_names = {w.field_name for w in pdf_widgets if w.field_name}

        # Get all PDF field names from schema
        schema_pdf_names = set()
        for field in schema.get("fields", []):
            if field.get("pdf_field_name"):
                schema_pdf_names.add(field["pdf_field_name"])

            # Check table columns
            if field.get("columns"):
                for col in field["columns"]:
                    if col.get("pdf_field_name"):
                        schema_pdf_names.add(col["pdf_field_name"])

            # Check options
            if field.get("options"):
                for opt in field["options"]:
                    if opt.get("pdf_field_name"):
                        schema_pdf_names.add(opt["pdf_field_name"])

        # Calculate coverage
        if pdf_field_names:
            coverage = len(schema_pdf_names & pdf_field_names) / len(pdf_field_names)
        else:
            coverage = 0.0

        warnings = []
        if coverage < 0.95:
            warnings.append(f"Widget coverage is only {coverage*100:.1f}%")

        missing = pdf_field_names - schema_pdf_names
        if missing and len(missing) < 20:  # Don't spam if many missing
            warnings.append(f"Missing {len(missing)} widgets: {list(missing)[:5]}")

        return {
            "coverage": coverage,
            "total_widgets": len(pdf_field_names),
            "covered_widgets": len(schema_pdf_names & pdf_field_names),
            "warnings": warnings
        }


# Convenience function
def extract_form_schema(pdf_path: str, api_key: Optional[str] = None, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract schema from PDF form using Gemini AI.

    Args:
        pdf_path: Path to PDF file
        api_key: Gemini API key (or use GEMINI_API_KEY env var)
        output_dir: Optional directory to save intermediate results

    Returns:
        Complete schema dict

    Example:
        >>> schema = extract_form_schema("my_form.pdf")
        >>> print(f"Extracted {schema['total_fields']} fields")
    """
    extractor = GeminiExtractor(api_key=api_key)
    return extractor.extract_schema(pdf_path, output_dir=output_dir)
