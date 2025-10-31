#!/usr/bin/env python3
"""
Label Overlay Extraction: Uses annotated PDF with field names overlaid.
This simplifies Gemini's task by showing exact field names directly on the form.
"""

import os
import json
import time
import requests
from typing import List, Dict, Any, Optional
from pathlib import Path
from pdf_annotator import annotate_pdf_with_field_names
from widget_inventory import extract_widget_inventory


class GeminiLabelOverlayExtractor:
    def __init__(self, api_key: Optional[str] = None, model: str = 'gemini-2.0-flash-exp'):
        """Initialize with Gemini API key."""
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def _upload_pdf(self, pdf_path: str) -> str:
        """Upload PDF to Gemini File API."""
        file_size = os.path.getsize(pdf_path)

        # Step 1: Initiate resumable upload
        upload_base_url = "https://generativelanguage.googleapis.com/upload/v1beta/files"
        headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": "application/pdf",
            "Content-Type": "application/json"
        }

        metadata = {"file": {"display_name": Path(pdf_path).name}}

        response = requests.post(
            f"{upload_base_url}?key={self.api_key}",
            headers=headers,
            json=metadata,
            timeout=30
        )

        if response.status_code != 200:
            raise Exception(f"Upload initiation failed: {response.status_code} - {response.text}")

        upload_url = response.headers.get("X-Goog-Upload-URL")
        if not upload_url:
            raise Exception("No upload URL in response")

        # Step 2: Upload file content
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()

        upload_headers = {
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
            "Content-Length": str(file_size)
        }

        upload_response = requests.put(
            upload_url,
            headers=upload_headers,
            data=pdf_content,
            timeout=60
        )

        if upload_response.status_code != 200:
            raise Exception(f"Upload failed: {upload_response.status_code} - {upload_response.text}")

        file_info = upload_response.json().get("file", {})
        return file_info.get("uri")

    def _wait_for_processing(self, file_uri: str, timeout: int = 60) -> str:
        """Wait for Gemini to process the uploaded file."""
        file_name = file_uri.split('/')[-1]
        start_time = time.time()

        while time.time() - start_time < timeout:
            response = requests.get(
                f"{self.base_url}/files/{file_name}?key={self.api_key}",
                timeout=10
            )

            if response.status_code == 200:
                state = response.json().get("state")
                if state == "ACTIVE":
                    return file_name
            time.sleep(2)

        raise TimeoutError(f"File processing timed out after {timeout}s")

    def _build_label_overlay_prompt(self, total_widgets: int, target_fields: int = 150) -> str:
        """
        Build prompt for label overlay extraction.

        The key difference: We reference the VISIBLE field names in the PDF image.
        """
        return f"""
# PDF Form Schema Extraction - Label Overlay Mode

You are analyzing a government form PDF where **every field has its exact PDF widget name overlaid in red text**.

## Your Task

Extract a comprehensive, structured schema by:
1. **Looking at the visual form layout** (sections, tables, grouping)
2. **Reading the red field name labels** directly on each field
3. **Grouping related widgets** into logical form fields

## Critical Information

- **Total widgets:** {total_widgets} (every red label you see)
- **Target fields:** ~{target_fields} (consolidate widgets into logical fields)
- **Consolidation ratio:** ~{total_widgets / target_fields:.1f}:1 (many widgets → fewer fields)

## Widget Consolidation Patterns

### 1. Radio/Checkbox Groups (N→1)
**Visual:** Multiple checkboxes near each other with similar labels
**Example:**
- You see: `CheckBox_Male[0]`, `CheckBox_Female[0]`, `CheckBox_Other[0]`
- Extract as: ONE field with `type: "radio"`, three options, list all in `consolidated_widgets`

### 2. Tables (M×N→1)
**Visual:** Grid layout with repeated field name patterns
**Example:**
- You see: `Pt4Line1_DateFrom[0]`, `Pt4Line1_DateTo[0]`, `Pt4Line2_DateFrom[0]`, `Pt4Line2_DateTo[0]`
- Extract as: ONE table field with columns ["date_from", "date_to"], rows array, list all in `consolidated_widgets`

### 3. Standalone Fields (1→1)
**Visual:** Single text field or checkbox
**Example:**
- You see: `PtAILine1_ANumber[0]`
- Extract as: ONE field with `pdf_field_name: "PtAILine1_ANumber[0]"`, `consolidated_widgets: ["PtAILine1_ANumber[0]"]`

## Required Output Format

```json
{{
  "form_metadata": {{
    "title": "Form Title from PDF",
    "form_number": "Form number if visible",
    "total_pages": <number>
  }},
  "fields": [
    {{
      "id": "descriptive_field_id",
      "name": "User-Friendly Field Name",
      "type": "text|checkbox|radio|select|table|group",
      "pdf_field_name": "PdfFieldName[0]",  // For standalone widgets only
      "consolidated_widgets": ["Widget1[0]", "Widget2[0]"],  // ALL widgets in this field
      "required": true,
      "label": "Question/Label text from form",
      "section": "Section name from visual headers",

      // For radio/select only:
      "options": [
        {{"value": "option1", "label": "Option 1", "pdf_field_name": "CheckBox1[0]"}}
      ],

      // For tables only:
      "columns": [
        {{"id": "col1", "name": "Column 1", "type": "text"}},
      ],
      "rows": []  // Empty - filled by user
    }}
  ]
}}
```

## CRITICAL VALIDATION RULES

1. **Widget Accounting:**
   - Count ALL red field name labels visible in the PDF
   - EVERY label must appear in exactly ONE field's `consolidated_widgets` array
   - Validation: sum(len(field.consolidated_widgets)) == {total_widgets}

2. **Field Naming:**
   - Use EXACT field names you see in red labels (including [0] suffix)
   - No guessing - if you see "PtAILine1_ANumber[0]", use exactly that

3. **Grouping Strategy:**
   - Look for **visual proximity** (checkboxes near each other = radio group)
   - Look for **patterns** in field names (Line1, Line2, Line3 = table rows)
   - Look for **section headers** in the form (bold text, larger font)
   - Aim for ~{target_fields} total fields (aggressive consolidation)

4. **Type Inference:**
   - Multiple checkboxes near each other → `radio` or `checkbox[]`
   - Grid pattern → `table`
   - Single checkbox → `checkbox`
   - Text field → `text`

## Example: Travel History Table

**What you see in PDF:**
```
Red labels in a grid:
Pt4Line1_DateFrom[0]  Pt4Line1_DateTo[0]  Pt4Line1_Place[0]
Pt4Line2_DateFrom[0]  Pt4Line2_DateTo[0]  Pt4Line2_Place[0]
Pt4Line3_DateFrom[0]  Pt4Line3_DateTo[0]  Pt4Line3_Place[0]
```

**What you extract:**
```json
{{
  "id": "travel_history",
  "type": "table",
  "consolidated_widgets": [
    "Pt4Line1_DateFrom[0]", "Pt4Line1_DateTo[0]", "Pt4Line1_Place[0]",
    "Pt4Line2_DateFrom[0]", "Pt4Line2_DateTo[0]", "Pt4Line2_Place[0]",
    "Pt4Line3_DateFrom[0]", "Pt4Line3_DateTo[0]", "Pt4Line3_Place[0]"
  ],
  "columns": [
    {{"id": "date_from", "name": "Date From", "type": "text"}},
    {{"id": "date_to", "name": "Date To", "type": "text"}},
    {{"id": "place", "name": "Place", "type": "text"}}
  ],
  "rows": []
}}
```
(9 widgets → 1 field, 3.0x consolidation)

## Begin Extraction

Analyze the annotated PDF and extract the complete schema following these rules.
**Remember:** Every red label must be accounted for in `consolidated_widgets`.
"""

    def extract_schema(self, pdf_path: str, annotated_pdf_path: str = None) -> Dict[str, Any]:
        """
        Extract schema using label overlay approach.

        Args:
            pdf_path: Original PDF path
            annotated_pdf_path: Pre-generated annotated PDF (optional, will generate if not provided)

        Returns:
            Complete schema dictionary
        """
        # Generate annotated PDF if not provided
        if not annotated_pdf_path:
            print("[Step 0/4] Generating annotated PDF...")
            annotated_pdf_path = annotate_pdf_with_field_names(pdf_path)

        # Get widget count for validation
        widgets = extract_widget_inventory(pdf_path)
        total_widgets = len(widgets)

        print(f"\n{'='*70}")
        print(f"GEMINI LABEL OVERLAY EXTRACTION")
        print(f"{'='*70}")
        print(f"PDF: {pdf_path}")
        print(f"Annotated PDF: {annotated_pdf_path}")
        print(f"Total widgets: {total_widgets}")

        # Upload annotated PDF
        file_uri = self._upload_pdf(annotated_pdf_path)

        # Wait for processing
        self._wait_for_processing(file_uri)

        # Extract schema
        print(f"[Step 3/4] Extracting schema from annotated PDF...")
        prompt = self._build_label_overlay_prompt(total_widgets)

        # Call Gemini API
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "file_data": {
                                "mime_type": "application/pdf",
                                "file_uri": file_uri
                            }
                        },
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }

        response = requests.post(url, json=payload, timeout=120)

        if response.status_code != 200:
            raise Exception(f"API call failed: {response.status_code} - {response.text}")

        result = response.json()
        response_text = result['candidates'][0]['content']['parts'][0]['text']

        try:
            schema = json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"  ERROR: JSON truncation detected at position {e.pos}")
            print(f"  This likely means Gemini hit the 8K output token limit")
            print(f"  Attempting to parse partial JSON...")

            # Save raw response for debugging
            with open("gemini_label_overlay_partial.json", 'w', encoding='utf-8') as f:
                f.write(response_text)
            print(f"  Raw response saved to: gemini_label_overlay_partial.json")

            # Try to extract what we can
            try:
                # Find where fields array starts
                fields_start = response_text.find('"fields": [')
                if fields_start != -1:
                    # Count complete field objects
                    fields_section = response_text[fields_start:]
                    complete_fields = fields_section.count('},')
                    print(f"  Partial extraction found ~{complete_fields} complete fields before truncation")
                    print(f"  ⚠️  Label overlay approach may need batching like hybrid extractor")
            except Exception:
                pass

            raise

        print(f"  Extracted {len(schema.get('fields', []))} fields")

        # Validate coverage
        print(f"[Step 4/4] Validating widget coverage...")
        consolidated_widgets_all = set()
        for field in schema.get('fields', []):
            consolidated_widgets_all.update(field.get('consolidated_widgets', []))

        widget_field_names = {w['field_name'] for w in widgets}
        covered_widgets = consolidated_widgets_all & widget_field_names
        coverage = len(covered_widgets) / len(widget_field_names) if widget_field_names else 0

        print(f"  Widget coverage: {len(covered_widgets)} / {len(widget_field_names)} ({coverage*100:.1f}%)")

        if coverage < 0.95:
            print(f"  ⚠️  WARNING: Coverage below 95% - some widgets may be missing")

        print(f"\n{'='*70}")
        print(f"EXTRACTION COMPLETE")
        print(f"{'='*70}")
        print(f"Total fields: {len(schema.get('fields', []))}")
        print(f"Widget coverage: {coverage*100:.1f}%")

        return schema


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python gemini_label_overlay_extractor.py <pdf_path> [annotated_pdf_path] [output_json]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    annotated_pdf_path = sys.argv[2] if len(sys.argv) > 2 else None
    output_path = sys.argv[3] if len(sys.argv) > 3 else "gemini_label_overlay_schema.json"

    extractor = GeminiLabelOverlayExtractor()
    schema = extractor.extract_schema(pdf_path, annotated_pdf_path)

    # Save schema
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print(f"\nSchema saved to: {output_path}")
