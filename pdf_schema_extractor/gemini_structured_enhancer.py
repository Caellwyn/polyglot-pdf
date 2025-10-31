#!/usr/bin/env python3
"""
Gemini-based schema extraction using ONLY structured widget inventory.
No PDF upload, no OCR - just field names + labels.

This tests if Gemini can do semantic analysis, grouping, and table detection
from structured data alone.
"""

import os
import json
import requests
import time
from typing import List, Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv


class GeminiStructuredEnhancer:
    """Enhance widget inventory using Gemini (structured data only)."""

    def __init__(self, api_key: Optional[str] = None, model: str = 'gemini-2.0-flash-exp'):
        """Initialize enhancer."""
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def enhance_schema(self, widgets: List[Dict[str, Any]], batch_size: int = 100) -> Dict[str, Any]:
        """
        Enhance widget inventory with semantic analysis.

        Args:
            widgets: Widget inventory from widget_inventory.py
            batch_size: Number of widgets to process per request

        Returns:
            Enhanced schema with grouping, typing, and structure
        """
        print(f"\n{'='*70}")
        print(f"GEMINI STRUCTURED ENHANCEMENT")
        print(f"{'='*70}")
        print(f"Total widgets: {len(widgets)}")
        print(f"Processing in batches of {batch_size}...")

        all_fields = []

        # Process in batches to handle large forms
        for i in range(0, len(widgets), batch_size):
            batch = widgets[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(widgets) + batch_size - 1) // batch_size

            print(f"\nBatch {batch_num}/{total_batches}: Processing {len(batch)} widgets...")

            try:
                fields = self._enhance_batch(batch, batch_num)
                all_fields.extend(fields)
                print(f"  Extracted {len(fields)} fields from batch {batch_num}")
            except Exception as e:
                print(f"  ERROR in batch {batch_num}: {e}")
                # Fallback: create basic fields from widgets
                for widget in batch:
                    all_fields.append({
                        "id": widget["field_name"].lower().replace('[', '_').replace(']', ''),
                        "name": widget["field_label"][:50] or widget["field_name"],
                        "pdf_field_name": widget["field_name"],
                        "type": widget["field_type"]
                    })

        schema = {
            "total_fields": len(all_fields),
            "fields": all_fields
        }

        print(f"\n{'='*70}")
        print(f"ENHANCEMENT COMPLETE")
        print(f"{'='*70}")
        print(f"Total fields in schema: {len(all_fields)}")

        return schema

    def _enhance_batch(self, widgets: List[Dict[str, Any]], batch_num: int) -> List[Dict[str, Any]]:
        """Enhance a batch of widgets."""

        # Build prompt with widget inventory
        prompt = self._build_enhancement_prompt(widgets)

        # Call Gemini
        response = self._call_gemini(prompt)

        # Parse response
        try:
            result = json.loads(response)
            return result.get('fields', [])
        except json.JSONDecodeError as e:
            print(f"  Warning: Failed to parse JSON response: {e}")
            print(f"  Response preview: {response[:200]}...")
            raise

    def _build_enhancement_prompt(self, widgets: List[Dict[str, Any]]) -> str:
        """Build prompt for Gemini enhancement."""

        # Simplify widget data for prompt
        simplified_widgets = []
        for w in widgets:
            simplified_widgets.append({
                "field_name": w["field_name"],
                "label": w["field_label"],
                "type": w["field_type"],
                "page": w["page"]
            })

        widgets_json = json.dumps(simplified_widgets, indent=2, ensure_ascii=False)

        prompt = f"""You are a PDF form schema analyzer. Below is a complete list of form widgets extracted from a PDF, including their exact field names, labels (tooltips), and types.

**WIDGET INVENTORY:**
```json
{widgets_json}
```

**YOUR TASK:**

Analyze these widgets and create a structured schema. For each widget or group of related widgets:

1. **Use EXACT field_name** - The "field_name" from the inventory MUST be used exactly as "pdf_field_name" in your output
2. **Infer semantic type** - Based on the label, determine if it's: text, textarea, date, email, tel, number, signature, checkbox, radio, select, or table
3. **Detect groups** - Identify radio button groups, checkbox groups based on similar labels
4. **Detect tables** - Find repeating patterns (e.g., "Child1", "Child2", "Child3") that indicate table rows
5. **Generate clean IDs** - Create snake_case field IDs from labels
6. **Create spoken names** - Natural language names for screen readers

**GROUPING RULES:**
- **Radio groups**: Mutually exclusive options (Yes/No, Male/Female, Single/Married)
- **Checkbox groups**: Multiple selections allowed
- **Tables**: Repeating numbered patterns (Spouse vs Child1, Child2, Child3...)

**TABLE DETECTION HINTS:**
- Look for numbered suffixes: "Child1[0]", "Child2[0]", "Child3[0]" = table with 3 rows
- Different base names at same number = columns: "ChildLast1", "ChildFirst1", "ChildDOB1" = 3 columns
- Count rows by max number, count columns by unique fields per row

**OUTPUT FORMAT:**
Return JSON with this EXACT structure:

```json
{{
  "fields": [
    {{
      "id": "alien_registration_number",
      "name": "Alien Registration Number (A-Number)",
      "spoken_name": "alien registration number",
      "type": "text",
      "pdf_field_name": "PtAILine1_ANumber[0]",
      "description": "Enter your A-Number if you have one"
    }},
    {{
      "id": "gender",
      "name": "Gender",
      "spoken_name": "gender",
      "type": "radio",
      "pdf_field_name": null,
      "group_id": "gender",
      "group_label": "Gender",
      "group_kind": "radio",
      "options": [
        {{"value": "male", "label": "Male", "pdf_field_name": "CheckBox_Male[0]"}},
        {{"value": "female", "label": "Female", "pdf_field_name": "CheckBox_Female[0]"}}
      ]
    }},
    {{
      "id": "children_table",
      "name": "Children Information",
      "spoken_name": "children information table",
      "type": "table",
      "pdf_field_name": null,
      "columns": [
        {{"id": "child_last_name", "label": "Last Name", "type": "text", "pdf_field_name": "ChildLast[1]"}},
        {{"id": "child_first_name", "label": "First Name", "type": "text", "pdf_field_name": "ChildFirst[1]"}}
      ],
      "multi_entry": {{
        "min_entries": 0,
        "max_entries": 4,
        "initial_rows": 4
      }}
    }}
  ]
}}
```

**CRITICAL REQUIREMENTS:**
- Every widget in the inventory MUST appear in your output (either as a field or within a group/table)
- Use exact "field_name" values as "pdf_field_name" - NO modifications, NO guessing
- For groups/tables, set top-level "pdf_field_name" to null, but include it in options/columns
- Infer types from labels: "Date of Birth" → "date", "Email" → "email", "Phone" → "tel", etc.

Return ONLY the JSON object, no additional text.
"""
        return prompt

    def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API with text prompt (no file upload)."""

        url = f"{self.base_url}/models/{self.model}:generateContent"

        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "topP": 0.95,
                "topK": 40,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json"
            }
        }

        response = requests.post(
            f"{url}?key={self.api_key}",
            headers=headers,
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            raise Exception(f"Gemini API error: {response.status_code} - {response.text}")

        result = response.json()

        if 'candidates' not in result or not result['candidates']:
            raise Exception(f"No candidates in response: {result}")

        content = result['candidates'][0]['content']
        text = content['parts'][0].get('text', '')

        return text


def main():
    """Test the structured enhancement approach."""

    # Load environment
    load_dotenv(Path(__file__).parent / '.env', override=True)

    # Load widget inventory
    inventory_path = "i589_widgets_filtered.json"

    if not Path(inventory_path).exists():
        print(f"ERROR: Widget inventory not found: {inventory_path}")
        print("Run: python widget_inventory.py test_schemas/test_pdfs/i-589.pdf i589_widgets_filtered.json")
        return

    print(f"Loading widget inventory: {inventory_path}")
    with open(inventory_path) as f:
        inventory = json.load(f)

    widgets = inventory['widgets']
    print(f"Loaded {len(widgets)} widgets")

    # Enhance with Gemini
    enhancer = GeminiStructuredEnhancer()
    schema = enhancer.enhance_schema(widgets, batch_size=100)

    # Save result
    output_path = "gemini_structured_schema.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print(f"\nSchema saved to: {output_path}")

    # Quick validation
    schema_field_names = set()
    for field in schema['fields']:
        if field.get('pdf_field_name'):
            schema_field_names.add(field['pdf_field_name'])

        # Check options
        for option in field.get('options', []):
            if option.get('pdf_field_name'):
                schema_field_names.add(option['pdf_field_name'])

        # Check columns
        for col in field.get('columns', []):
            if col.get('pdf_field_name'):
                schema_field_names.add(col['pdf_field_name'])

    widget_field_names = {w['field_name'] for w in widgets}
    coverage = len(schema_field_names & widget_field_names) / len(widget_field_names)

    print(f"\nQuick Coverage Check:")
    print(f"  Widget inventory: {len(widget_field_names)} fields")
    print(f"  Schema coverage: {len(schema_field_names & widget_field_names)} fields")
    print(f"  Coverage: {coverage*100:.1f}%")

    missing = widget_field_names - schema_field_names
    if missing:
        print(f"  Missing: {len(missing)} fields")
        if len(missing) <= 10:
            print(f"    {list(missing)}")


if __name__ == "__main__":
    main()
