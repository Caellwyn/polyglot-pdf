#!/usr/bin/env python3
"""
Hybrid Gemini-based PDF schema extraction using:
- PDF upload (visual context for accurate typing & table detection)
- Widget inventory (exact field names to prevent hallucination)
- Code execution (PyMuPDF access for verification)
- Comprehensive system prompt (all filtering rules and instructions)

This combines the best of all approaches.
"""

import os
import json
import requests
import time
from typing import List, Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv


class GeminiHybridExtractor:
    """
    Hybrid PDF schema extractor using Gemini with PDF + widget inventory + code execution.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = 'gemini-2.0-flash-exp'):
        """Initialize extractor."""
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def extract_schema(
        self,
        pdf_path: str,
        widget_inventory: List[Dict[str, Any]],
        batch_size: int = 50,
        output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract complete schema using hybrid approach with batching.

        Args:
            pdf_path: Path to PDF file
            widget_inventory: Pre-extracted widget inventory with field names/labels
            batch_size: Number of widgets per batch (default 50 to avoid truncation)
            output_dir: Optional directory for intermediate results

        Returns:
            Complete schema dict
        """
        print(f"\n{'='*70}")
        print(f"GEMINI HYBRID EXTRACTION (PDF + Inventory)")
        print(f"{'='*70}")
        print(f"PDF: {pdf_path}")
        print(f"Widgets: {len(widget_inventory)}")
        print(f"Batch size: {batch_size}")

        # Step 1: Upload PDF to Gemini
        print(f"\n[Step 1/4] Uploading PDF to Gemini...")
        file_uri = self._upload_pdf(pdf_path)
        print(f"  Uploaded: {file_uri}")

        # Step 2: Wait for processing
        print(f"\n[Step 2/4] Waiting for PDF processing...")
        file_name = self._wait_for_processing(file_uri)
        print(f"  Ready: {file_name}")

        # Step 3: Extract schema in batches
        print(f"\n[Step 3/4] Extracting schema in batches...")
        all_fields = []
        num_batches = (len(widget_inventory) + batch_size - 1) // batch_size

        for i in range(0, len(widget_inventory), batch_size):
            batch = widget_inventory[i:i + batch_size]
            batch_num = (i // batch_size) + 1

            print(f"  Batch {batch_num}/{num_batches}: Processing {len(batch)} widgets...")

            try:
                fields = self._extract_batch(file_uri, batch, batch_num)
                all_fields.extend(fields)
                print(f"    Extracted {len(fields)} fields")
            except Exception as e:
                print(f"    ERROR: {e}")
                # Continue with other batches

        # Step 4: Merge into final schema
        print(f"\n[Step 4/4] Merging batches...")
        schema = {
            "total_fields": len(all_fields),
            "fields": all_fields
        }

        print(f"\n{'='*70}")
        print(f"EXTRACTION COMPLETE")
        print(f"{'='*70}")
        print(f"Total fields: {len(all_fields)}")

        return schema

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

        # Step 2: Upload file bytes
        with open(pdf_path, 'rb') as f:
            file_data = f.read()

        headers = {
            "Content-Length": str(file_size),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize"
        }

        response = requests.put(upload_url, headers=headers, data=file_data)

        if response.status_code not in (200, 201):
            raise Exception(f"Upload failed: {response.status_code} - {response.text}")

        result = response.json()
        return result['file']['uri']

    def _wait_for_processing(self, file_uri: str, max_wait: int = 60) -> str:
        """Wait for file to be processed."""
        file_name = file_uri.split('/')[-1]
        url = f"{self.base_url}/files/{file_name}"

        start_time = time.time()
        while time.time() - start_time < max_wait:
            response = requests.get(f"{url}?key={self.api_key}")

            if response.status_code != 200:
                raise Exception(f"Get file failed: {response.status_code} - {response.text}")

            result = response.json()
            state = result.get('state')

            if state == 'ACTIVE':
                return file_name
            elif state == 'FAILED':
                raise Exception(f"File processing failed: {result}")

            time.sleep(2)

        raise Exception(f"File processing timeout after {max_wait}s")

    def _extract_batch(
        self,
        file_uri: str,
        widget_batch: List[Dict[str, Any]],
        batch_num: int
    ) -> List[Dict[str, Any]]:
        """Extract schema for a batch of widgets."""

        prompt = self._build_hybrid_prompt(widget_batch, batch_num)

        # Call Gemini with code execution tool
        url = f"{self.base_url}/models/{self.model}:generateContent"

        payload = {
            "contents": [{
                "parts": [
                    {"file_data": {"file_uri": file_uri, "mime_type": "application/pdf"}},
                    {"text": prompt}
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "topP": 0.95,
                "topK": 40,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json"
            },
            # Note: Code execution cannot be used with PDF uploads (API limitation)
            # We prioritize visual PDF access over code execution
        }

        response = requests.post(
            f"{url}?key={self.api_key}",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=120
        )

        if response.status_code != 200:
            raise Exception(f"Gemini API error: {response.status_code} - {response.text}")

        result = response.json()

        # Extract response
        if 'candidates' not in result or not result['candidates']:
            raise Exception(f"No candidates in response: {result}")

        parts = result['candidates'][0]['content']['parts']

        # Look for text response (JSON schema)
        schema_text = None
        for part in parts:
            if 'text' in part:
                schema_text = part['text']

        if not schema_text:
            raise Exception("No text response from Gemini")

        # Parse JSON response
        batch_result = json.loads(schema_text)
        return batch_result.get('fields', [])

    def _build_hybrid_prompt(self, widget_batch: List[Dict[str, Any]], batch_num: int) -> str:
        """Build comprehensive prompt with all instructions."""

        # Simplify widget data for prompt
        simplified_widgets = []
        for w in widget_batch:
            simplified_widgets.append({
                "field_name": w["field_name"],
                "label": w["field_label"],
                "type": w["field_type"],
                "page": w["page"]
            })

        widgets_json = json.dumps(simplified_widgets, indent=2, ensure_ascii=False)

        prompt = f"""You are an expert PDF form schema analyzer with access to both visual and programmatic data.

**YOUR TASK:** Extract a schema for THIS BATCH of widgets (Batch #{batch_num}).

**RESOURCES AVAILABLE:**

1. **Visual PDF Analysis** - You can see the form layout, fields, labels, spatial relationships
2. **Widget Inventory** - Complete list of actual PDF widget field names (see below)

**WIDGET INVENTORY (CRITICAL - USE THESE EXACT NAMES):**
```json
{widgets_json}
```

**FILTERING RULES (IGNORE THESE WIDGETS):**
- ✗ Barcodes (PDF417BarCode, etc.)
- ✗ Signature fields (already filtered from inventory above)
- ✗ Read-only fields
- ✗ Hidden fields
- ✗ Administrative buttons

The inventory above has already been filtered. Use ONLY these widgets.

**YOUR ANALYSIS TASKS:**

1. **Use Exact Widget Names**
   - Every field MUST use "field_name" from the inventory as "pdf_field_name"
   - NEVER make up or modify field names
   - For groups/tables, set top-level pdf_field_name to null, but include in options/columns

2. **Infer Semantic Types** (use visual context + labels)
   - text → Generic text input
   - textarea → Multi-line text (3+ lines tall visually)
   - date → Date fields (look for "date", "DOB", "/  /" patterns)
   - email → Email addresses
   - tel → Phone/telephone numbers
   - number → Numeric only fields
   - signature → Signature boxes (if any remain after filtering)
   - checkbox → Individual checkboxes
   - radio → Radio button groups (mutually exclusive)
   - select → Dropdown menus
   - table → Repeating data entry patterns

3. **Detect Groups**
   - **Radio groups**: Mutually exclusive options (Yes/No, Male/Female, Married/Single/Divorced)
   - **Checkbox groups**: Multiple selections allowed
   - Look for visual grouping and label patterns

4. **Detect Tables** (CRITICAL)
   - Look for numbered patterns in field names: "Child1", "Child2", "Child3"
   - Different base names at same number = columns: "ChildLast1", "ChildFirst1" = 2 columns
   - Count rows by max number (Child1-4 = 4 rows)
   - Count columns by unique field patterns per row
   - Visual layout: fields aligned in grid pattern
   - Examples: Spouse info (1 row) vs Children info (multiple rows)

5. **Generate Clean Field IDs**
   - snake_case from labels
   - Descriptive and unique

6. **Create Spoken Names**
   - Natural language for screen readers
   - "alien registration number", "date of birth", etc.

**TABLE DETECTION STRATEGY:**

Use BOTH visual and field name analysis:
- **Visual**: Look for grid layouts, repeating sections
- **Field names**: Numbered suffixes indicate rows (Spouse vs Child1, Child2, Child3, Child4)
- **Example**:
  ```
  Spouse section (1 row):
    PtAIILine1_ANumber[0]  → Spouse's A-Number
    PtAIILine5_LastName[0] → Spouse's Last Name

  Children section (4 rows):
    ChildAlien1[0], ChildLast1[0], ChildFirst1[0]  → Row 1
    ChildAlien2[0], ChildLast2[0], ChildFirst2[0]  → Row 2
    ChildAlien3[0], ChildLast3[0], ChildFirst3[0]  → Row 3
    ChildAlien4[0], ChildLast4[0], ChildFirst4[0]  → Row 4
    = Table with 3 columns × 4 rows
  ```

**CRITICAL WIDGET ACCOUNTING RULE:**

You are processing exactly {len(simplified_widgets)} widgets in this batch. Your output MUST account for ALL {len(simplified_widgets)} widgets.

**How to account for widgets:**
1. **Standalone field**: 1 widget → 1 field (set pdf_field_name + consolidated_widgets: [field_name])
2. **Radio/Checkbox group**: N widgets → 1 field (pdf_field_name=null, list all in consolidated_widgets + options)
3. **Table**: M×N widgets → 1 field (pdf_field_name=null, list all in consolidated_widgets + columns × rows)

**Widget Tracking Strategy:**
- Match widget labels to visual fields using: section info, tooltips, position, field patterns
- Group related widgets that are mutually exclusive or form tables
- EVERY widget's field_name MUST appear in your output exactly once

**OUTPUT FORMAT (EXACT STRUCTURE REQUIRED):**

```json
{{
  "fields": [
    {{
      "id": "alien_registration_number",
      "name": "Alien Registration Number (A-Number)",
      "spoken_name": "alien registration number",
      "type": "text",
      "pdf_field_name": "PtAILine1_ANumber[0]",
      "consolidated_widgets": ["PtAILine1_ANumber[0]"],
      "description": "Your A-Number if you have one"
    }},
    {{
      "id": "gender",
      "name": "Gender",
      "spoken_name": "gender",
      "type": "radio",
      "pdf_field_name": null,
      "consolidated_widgets": ["CheckBox_Male[0]", "CheckBox_Female[0]"],
      "group_id": "gender",
      "group_label": "Gender",
      "group_kind": "radio",
      "options": [
        {{"value": "male", "label": "Male", "pdf_field_name": "CheckBox_Male[0]"}},
        {{"value": "female", "label": "Female", "pdf_field_name": "CheckBox_Female[0]"}}
      ]
    }},
    {{
      "id": "children_info",
      "name": "Children Information",
      "spoken_name": "children information",
      "type": "table",
      "pdf_field_name": null,
      "consolidated_widgets": ["ChildAlien1[0]", "ChildLast1[0]", "ChildFirst1[0]", "ChildAlien2[0]", "ChildLast2[0]", "ChildFirst2[0]"],
      "columns": [
        {{"id": "alien_number", "label": "Alien Number", "type": "text", "pdf_field_name": "ChildAlien[1]"}},
        {{"id": "last_name", "label": "Last Name", "type": "text", "pdf_field_name": "ChildLast[1]"}},
        {{"id": "first_name", "label": "First Name", "type": "text", "pdf_field_name": "ChildFirst[1]"}}
      ],
      "multi_entry": {{
        "min_entries": 0,
        "max_entries": 2,
        "initial_rows": 2
      }}
    }}
  ]
}}
```

**VALIDATION REQUIREMENTS:**

✓ EVERY widget from batch MUST be in consolidated_widgets of some field
✓ consolidated_widgets array MUST NOT be empty for any field
✓ Sum of all consolidated_widgets lengths MUST equal {len(simplified_widgets)}
✓ All pdf_field_name values MUST match inventory field_name exactly
✓ Types must match visual appearance and widget types
✓ Tables: consolidated_widgets = all column widgets × all row widgets
✓ Groups: consolidated_widgets = all option widgets

**IMPORTANT:**
- Return ONLY the JSON object
- No markdown formatting, no additional text
- Ensure 100% widget coverage
- Do not hallucinate field names

Begin your analysis now.
"""

        return prompt


def main():
    """Test hybrid extraction."""

    # Load environment
    load_dotenv(Path(__file__).parent / '.env', override=True)

    # Check for widget inventory
    inventory_path = "i589_widgets_clean.json"
    if not Path(inventory_path).exists():
        print(f"ERROR: Widget inventory not found: {inventory_path}")
        print("Run: python widget_inventory.py test_schemas/test_pdfs/i-589.pdf i589_widgets_clean.json")
        return

    # Load inventory
    print(f"Loading widget inventory: {inventory_path}")
    with open(inventory_path) as f:
        inventory = json.load(f)
    widgets = inventory['widgets']

    # Extract schema
    pdf_path = "test_schemas/test_pdfs/i-589.pdf"
    extractor = GeminiHybridExtractor()
    schema = extractor.extract_schema(pdf_path, widgets)

    # Save result
    output_path = "gemini_hybrid_schema.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print(f"\nSchema saved to: {output_path}")

    # Quick validation using consolidated_widgets
    consolidated_widgets_all = set()
    fields_with_consolidated = 0
    fields_without_consolidated = 0

    for field in schema.get('fields', []):
        consolidated = field.get('consolidated_widgets', [])
        if consolidated:
            consolidated_widgets_all.update(consolidated)
            fields_with_consolidated += 1
        else:
            fields_without_consolidated += 1

    widget_field_names = {w['field_name'] for w in widgets}
    coverage = len(consolidated_widgets_all & widget_field_names) / len(widget_field_names) if widget_field_names else 0

    print(f"\nQuick Coverage Check (via consolidated_widgets):")
    print(f"  Widget inventory: {len(widget_field_names)} widgets")
    print(f"  Consolidated widgets: {len(consolidated_widgets_all)} widgets")
    print(f"  Coverage: {len(consolidated_widgets_all & widget_field_names)} / {len(widget_field_names)} ({coverage*100:.1f}%)")
    print(f"  Fields with consolidated_widgets: {fields_with_consolidated}/{len(schema.get('fields', []))}")

    if fields_without_consolidated > 0:
        print(f"  WARNING: {fields_without_consolidated} fields missing consolidated_widgets!")

    missing = widget_field_names - consolidated_widgets_all
    if missing:
        print(f"  Missing widgets: {len(missing)}")
        if len(missing) <= 20:
            print(f"    {list(missing)[:20]}")

    extra = consolidated_widgets_all - widget_field_names
    if extra:
        print(f"  Extra/hallucinated widgets: {len(extra)}")


if __name__ == "__main__":
    main()
