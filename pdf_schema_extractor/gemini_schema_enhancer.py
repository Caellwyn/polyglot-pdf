#!/usr/bin/env python3
"""
Gemini Schema Enhancer - Uses visual + text analysis to enhance schema.

Generates:
- Voice-friendly spoken names
- Help text for voice AI guidance
- Validation hints from context
"""

import json
import os
import requests
import time
from pathlib import Path
from typing import Dict, List, Any


class GeminiSchemaEnhancer:
    """Enhances schema using Gemini's visual and text analysis."""

    def __init__(self):
        self.api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            raise Exception("GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set")

        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = "gemini-2.0-flash-exp"

    def _upload_pdf(self, pdf_path: str) -> str:
        """Upload PDF to Gemini File API using resumable upload."""
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

    def _wait_for_processing(self, file_uri: str, max_wait: int = 60) -> str:
        """Wait for PDF processing to complete."""
        file_name = file_uri.split('/')[-1]
        url = f"{self.base_url}/files/{file_name}"
        params = {'key': self.api_key}

        for _ in range(max_wait):
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                file_data = response.json()
                if file_data.get('state') == 'ACTIVE':
                    return file_name
            time.sleep(1)

        raise Exception("PDF processing timeout")

    def enhance_schema(
        self,
        annotated_pdf_path: str,
        widgets_file: str,
        schema_file: str,
        output_file: str,
        batch_size: int = 40
    ) -> Dict[str, Any]:
        """
        Enhance schema with voice-friendly names and help text.

        Args:
            annotated_pdf_path: Annotated PDF for visual context
            widgets_file: Widget inventory with tooltips
            schema_file: Current schema
            output_file: Where to save enhanced schema
            batch_size: Number of fields to process per API call (default 40)
        """
        print("="*70)
        print("GEMINI SCHEMA ENHANCEMENT - BATCH MODE")
        print("="*70)

        # Load data
        print("\n[1/7] Loading data...")
        with open(widgets_file, 'r', encoding='utf-8') as f:
            widget_data = json.load(f)
            widgets = widget_data['widgets']
        print(f"  Loaded {len(widgets)} widgets")

        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)

        total_fields = len(schema.get('fields', []))
        print(f"  Loaded schema with {total_fields} fields")

        # Upload PDF (once for all batches)
        print("\n[2/7] Uploading annotated PDF...")
        file_uri = self._upload_pdf(annotated_pdf_path)
        print(f"  Uploaded: {file_uri}")

        # Wait for processing
        print("\n[3/7] Waiting for PDF processing...")
        file_name = self._wait_for_processing(file_uri)
        print(f"  Ready: {file_name}")

        # Process in batches
        print(f"\n[4/7] Generating enhancements in batches of {batch_size}...")
        all_enhancements = {"fields": []}

        num_batches = (total_fields + batch_size - 1) // batch_size

        for batch_num in range(num_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, total_fields)

            print(f"\n  Batch {batch_num + 1}/{num_batches}: Fields {start_idx + 1}-{end_idx}")

            # Build prompt for this batch
            prompt = self._build_enhancement_prompt(widgets, schema, start_idx, end_idx)

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
                    "temperature": 0.3,
                    "responseMimeType": "application/json"
                }
            }

            response = requests.post(url, json=payload, timeout=120)

            if response.status_code != 200:
                print(f"    WARNING: Batch {batch_num + 1} failed: {response.status_code}")
                continue

            result = response.json()
            response_text = result['candidates'][0]['content']['parts'][0]['text']

            try:
                batch_enhancements = json.loads(response_text)
                batch_fields = batch_enhancements.get('fields', [])
                all_enhancements['fields'].extend(batch_fields)
                print(f"    Enhanced {len(batch_fields)} fields")
            except json.JSONDecodeError as e:
                print(f"    WARNING: Failed to parse batch {batch_num + 1}: {e}")
                continue

            # Small delay to avoid rate limiting
            if batch_num < num_batches - 1:
                time.sleep(2)

        print(f"\n  Total enhanced: {len(all_enhancements['fields'])} fields")

        # Apply enhancements
        print("\n[5/7] Applying enhancements to schema...")
        enhanced_schema = self._apply_enhancements(schema, all_enhancements)

        # Save
        print("\n[6/7] Saving enhanced schema...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(enhanced_schema, f, indent=2, ensure_ascii=False)

        print("\n[7/7] Complete!")
        print("\n" + "="*70)
        print("ENHANCEMENT COMPLETE")
        print("="*70)
        print(f"Enhanced schema saved to: {output_file}")
        print(f"Enhanced {len(all_enhancements['fields'])} / {total_fields} fields")

        return enhanced_schema

    def _build_enhancement_prompt(self, widgets: List[Dict], schema: Dict, start_idx: int = 0, end_idx: int = None) -> str:
        """Build prompt for Gemini enhancement (minimal approach - only request what we need)."""

        if end_idx is None:
            end_idx = len(schema.get('fields', []))

        # Create field summary with tooltips for this batch
        field_summaries = []
        for i, field in enumerate(schema.get('fields', [])[start_idx:end_idx]):
            field_id = field.get('id')
            field_name = field.get('name')
            field_type = field.get('type')
            section = field.get('section', '')
            pdf_field = field.get('pdf_field_name', '')
            read_only = field.get('read_only', False)

            # For group fields, get tooltip from first consolidated widget
            tooltip = ""
            if pdf_field:
                for w in widgets:
                    if w.get('full_field_name') == pdf_field or w.get('field_name') == pdf_field:
                        tooltip = w.get('field_label', '')
                        break
            elif field.get('consolidated_widgets'):
                # Try first widget in group
                first_widget = field['consolidated_widgets'][0]
                for w in widgets:
                    widget_name = w.get('field_name', '')
                    if widget_name == first_widget or widget_name.lower() == first_widget.lower():
                        tooltip = w.get('field_label', '')
                        break

            field_summaries.append({
                "field_id": field_id,
                "current_name": field_name,
                "type": field_type,
                "section": section[:60],
                "tooltip": tooltip[:200],
                "read_only": read_only
            })

        prompt = f"""You are enhancing a schema for a voice-based immigration form filler that helps non-English speakers.

IMPORTANT: Only provide the information requested below. Do NOT regenerate the schema structure - just return enhancements.

**Your Task:**
For each field below, provide ONLY these enhancements:

1. **spoken_name**: Natural, conversational name for voice interaction (2-8 words)
   - Remove: "Enter", "Select", "Provide", "Check if" prefixes
   - Simplify technical jargon
   - Use common everyday language
   - Examples:
     * "Enter Alien Registration Number (A-Number)" → "alien number"
     * "Part 1. Information About You. Mailing Address. 6. C. Select Apartment" → "apartment"
     * "Your Date of Birth (mm/dd/yyyy)" → "date of birth"

2. **help_text**: Clear guidance for voice AI (1-3 sentences)
   - WHAT information is needed
   - WHY it's needed (if helpful context exists)
   - Common examples or formats
   - Important conditional logic (when to skip, when to pre-populate, etc.)
   - Examples:
     * "Your alien registration number (A-Number) is a 7-9 digit number on your green card"
     * "Enter your mailing address where you want to receive mail. If different from physical address, provide the in-care-of name"
     * "This field is read-only and pre-populates from Part 1. Used for reference in Part 8 additional information"

3. **conditional_logic** (ONLY if field has conditions):
   - When to show/hide the field
   - Dependencies on other fields
   - Pre-population rules
   - Examples:
     * "Show only if user selected 'Yes' to name change in question 4"
     * "Pre-populated from p1_line3b_givenname in Part 1, read-only"
     * "Skip if user is filing based on lost/stolen card"

4. **validation_hint** (ONLY if clear format exists):
   - Format requirements you can identify
   - From tooltips, visual cues, field labels
   - Examples: "7-9 digits", "MM/DD/YYYY", "2 letter state code"

**Field Information:**
{json.dumps(field_summaries, indent=2)}

**Visual Context Available:**
Use the annotated PDF to identify:
- Surrounding instructions and notes
- Section headers showing field purpose
- Visual indicators of conditional fields
- Pre-population notes (especially in Part 8)
- Relationships between fields

**Output Format (JSON ONLY):**
{{
  "fields": [
    {{
      "field_id": "exact_field_id_from_above",
      "spoken_name": "natural name",
      "help_text": "clear guidance",
      "conditional_logic": "when/why field appears (optional)",
      "validation_hint": "format if known (optional)"
    }}
  ]
}}

CRITICAL:
- Use EXACT field_id values from the input
- Focus on accuracy over completeness
- For Part 8 read-only fields, identify which Part 1 field they reference
- Make spoken names SHORT and NATURAL for voice interaction"""

        return prompt

    def _apply_enhancements(self, schema: Dict, enhancements: Dict) -> Dict:
        """Apply Gemini enhancements to schema (minimal approach)."""

        # Create enhancement lookup by field_id
        enhancement_map = {
            e['field_id']: e for e in enhancements.get('fields', [])
        }

        # Apply to schema fields
        enhanced_count = 0
        for field in schema.get('fields', []):
            field_id = field.get('id')

            if field_id in enhancement_map:
                enhancement = enhancement_map[field_id]
                enhanced_count += 1

                # Add spoken name
                if enhancement.get('spoken_name'):
                    field['spoken_name'] = enhancement['spoken_name']

                # Add help section
                help_section = field.get('help', {})
                if not isinstance(help_section, dict):
                    help_section = {}

                if enhancement.get('help_text'):
                    help_section['instructions'] = enhancement['help_text']

                if enhancement.get('validation_hint'):
                    help_section['format_hint'] = enhancement['validation_hint']

                if enhancement.get('conditional_logic'):
                    help_section['conditional_logic'] = enhancement['conditional_logic']

                if help_section:
                    field['help'] = help_section

        print(f"  Applied enhancements to {enhanced_count} fields")
        return schema


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 5:
        print("Usage: python gemini_schema_enhancer.py <annotated_pdf> <widgets_json> <schema_json> <output_json>")
        sys.exit(1)

    annotated_pdf = sys.argv[1]
    widgets_file = sys.argv[2]
    schema_file = sys.argv[3]
    output_file = sys.argv[4]

    enhancer = GeminiSchemaEnhancer()
    enhancer.enhance_schema(annotated_pdf, widgets_file, schema_file, output_file)
