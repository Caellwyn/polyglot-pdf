#!/usr/bin/env python3
"""
Minimal Gemini Grouping Extractor - Only asks for semantic grouping, not full schema.

Separation of concerns:
- Gemini: Semantic understanding (groups, tables)
- Python: Precision (100% widget coverage, schema construction)
"""

import os
import json
import time
import requests
from typing import List, Dict, Any, Optional
from pathlib import Path
from pdf_annotator import annotate_pdf_with_field_names
from widget_inventory import extract_widget_inventory


class GeminiGroupingExtractor:
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

    def _build_grouping_prompt(self, total_widgets: int) -> str:
        """
        Build minimal prompt asking ONLY for grouping and table information.

        We're NOT asking for:
        - Full field schemas
        - Field types (we have those)
        - Individual field objects
        - Section mapping (we can parse from field names/tooltips)
        """
        return f"""# PDF Form Analysis - Grouping & Table Detection

You are analyzing a government form PDF with **{total_widgets} fields labeled in red**.

## Your ONLY Task

Identify:
1. **Radio/Checkbox Groups** - Multiple checkboxes that represent a single choice
2. **Tables** - Grid patterns of fields that form structured data

**DO NOT** extract full schemas, field types, or individual fields. Just tell us which widgets belong together.

## Output Format

```json
{{
  "groups": [
    {{
      "type": "radio",
      "widgets": ["CheckBox_Male[0]", "CheckBox_Female[0]"],
      "purpose": "Gender selection"
    }},
    {{
      "type": "checkbox_group",
      "widgets": ["CheckBox_Citizen[0]", "CheckBox_LPR[0]", "CheckBox_Other[0]"],
      "purpose": "Immigration status (multiple allowed)"
    }}
  ],
  "tables": [
    {{
      "widgets": [
        "Pt4Line1_DateFrom[0]", "Pt4Line1_DateTo[0]", "Pt4Line1_Place[0]",
        "Pt4Line2_DateFrom[0]", "Pt4Line2_DateTo[0]", "Pt4Line2_Place[0]",
        "Pt4Line3_DateFrom[0]", "Pt4Line3_DateTo[0]", "Pt4Line3_Place[0]"
      ],
      "rows": 3,
      "columns": [
        {{"field_pattern": "DateFrom", "label": "Date From"}},
        {{"field_pattern": "DateTo", "label": "Date To"}},
        {{"field_pattern": "Place", "label": "Place"}}
      ],
      "purpose": "Travel history"
    }}
  ]
}}
```

## Instructions

### For Groups
1. Look for **visually clustered checkboxes** near each other
2. If they represent a **single choice** (only one can be selected) → `type: "radio"`
3. If they represent **multiple choices** (multiple can be selected) → `type: "checkbox_group"`
4. List the exact widget field names (visible in red on the PDF)

### For Tables
1. Look for **grid patterns** of fields with similar visual layout
2. Identify **row patterns** (Line1, Line2, Line3 or repeated field sets)
3. Identify **column patterns** (common field name suffixes like DateFrom, DateTo, Place)
4. List ALL widget field names in the table (row by row)
5. Specify number of rows and column definitions

### What NOT to Include
- ❌ Individual standalone text fields
- ❌ Single checkboxes (not part of a group)
- ❌ Field types (we already have those)
- ❌ Complete schemas

## Validation

Your output should:
- Include ONLY groups and tables (not every field)
- Use exact field names from red labels on PDF
- Cover ~{total_widgets * 0.4:.0f}-{total_widgets * 0.6:.0f} widgets (rough estimate)
- Be concise (aim for ~170 groups/tables total)

## Example

If you see:
- 3 checkboxes near "Gender:" → 1 radio group (3 widgets)
- 10 rows × 3 columns of travel history → 1 table (30 widgets)
- 372 other individual text fields → DON'T list these

Output would contain 2 items (1 group + 1 table) covering 33 widgets.

Begin analysis. Focus ONLY on groups and tables.
"""

    def extract_groupings(self, pdf_path: str, annotated_pdf_path: str = None) -> Dict[str, Any]:
        """
        Extract ONLY grouping and table information from annotated PDF.

        Args:
            pdf_path: Original PDF path
            annotated_pdf_path: Pre-generated annotated PDF (optional)

        Returns:
            Grouping information dict with 'groups' and 'tables' arrays
        """
        # Generate annotated PDF if not provided
        if not annotated_pdf_path:
            print("[Step 0/4] Generating annotated PDF...")
            annotated_pdf_path = annotate_pdf_with_field_names(pdf_path)

        # Get widget count for validation
        widgets = extract_widget_inventory(pdf_path)
        total_widgets = len(widgets)

        print(f"\n{'='*70}")
        print(f"GEMINI GROUPING EXTRACTION (Minimal)")
        print(f"{'='*70}")
        print(f"PDF: {pdf_path}")
        print(f"Annotated PDF: {annotated_pdf_path}")
        print(f"Total widgets: {total_widgets}")

        # Upload annotated PDF
        print(f"\n[Step 1/4] Uploading annotated PDF...")
        file_uri = self._upload_pdf(annotated_pdf_path)
        print(f"  Uploaded: {file_uri}")

        # Wait for processing
        print(f"\n[Step 2/4] Waiting for PDF processing...")
        file_name = self._wait_for_processing(file_uri)
        print(f"  Ready: {file_name}")

        # Extract groupings
        print(f"\n[Step 3/4] Extracting groupings and tables...")
        prompt = self._build_grouping_prompt(total_widgets)

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
            groupings = json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"  ERROR: Failed to parse JSON response: {e}")
            print(f"  Raw response: {response_text[:500]}...")

            # Save for debugging
            with open("gemini_groupings_partial.json", 'w', encoding='utf-8') as f:
                f.write(response_text)
            print(f"  Raw response saved to: gemini_groupings_partial.json")
            raise

        num_groups = len(groupings.get('groups', []))
        num_tables = len(groupings.get('tables', []))
        print(f"  Found {num_groups} groups, {num_tables} tables")

        # Validate coverage
        print(f"\n[Step 4/4] Calculating coverage...")
        widgets_in_groups = set()
        for group in groupings.get('groups', []):
            widgets_in_groups.update(group.get('widgets', []))
        for table in groupings.get('tables', []):
            widgets_in_groups.update(table.get('widgets', []))

        widget_field_names = {w['field_name'] for w in widgets}
        covered_widgets = widgets_in_groups & widget_field_names
        coverage = len(covered_widgets) / len(widget_field_names) if widget_field_names else 0

        print(f"  Widgets in groups/tables: {len(covered_widgets)} / {len(widget_field_names)} ({coverage*100:.1f}%)")
        print(f"  Standalone widgets: {len(widget_field_names) - len(covered_widgets)}")

        print(f"\n{'='*70}")
        print(f"GROUPING EXTRACTION COMPLETE")
        print(f"{'='*70}")
        print(f"Groups: {num_groups}")
        print(f"Tables: {num_tables}")
        print(f"Total output items: {num_groups + num_tables} (vs {total_widgets} widgets)")
        print(f"Output reduction: {(num_groups + num_tables) / total_widgets * 100:.1f}% of full schema")

        return groupings


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python gemini_grouping_extractor.py <pdf_path> [annotated_pdf_path] [output_json]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    annotated_pdf_path = sys.argv[2] if len(sys.argv) > 2 else None
    output_path = sys.argv[3] if len(sys.argv) > 3 else "gemini_groupings.json"

    extractor = GeminiGroupingExtractor()
    groupings = extractor.extract_groupings(pdf_path, annotated_pdf_path)

    # Save groupings
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(groupings, f, indent=2, ensure_ascii=False)

    print(f"\nGroupings saved to: {output_path}")
