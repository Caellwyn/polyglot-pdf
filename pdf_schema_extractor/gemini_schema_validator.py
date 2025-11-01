#!/usr/bin/env python3
"""
Gemini Schema Validator - Uses visual + instruction PDF analysis to identify issues.

Asks Gemini to identify:
1. Field type corrections (checkbox vs radio, text vs date vs select)
2. Validation rules (phone format, zip codes, etc.)
3. Conditional logic (which fields unlock others)
4. Enhanced semantic information (spoken names, help text)
"""

import json
import os
import requests
import time
from pathlib import Path
from typing import Dict, List, Any


class GeminiSchemaValidator:
    """Uses Gemini to validate and enhance schema."""

    def __init__(self):
        self.api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            raise Exception("GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set")

        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = "gemini-2.0-flash-exp"

    def _upload_file(self, file_path: str) -> str:
        """Upload file to Gemini File API using resumable upload."""
        file_size = os.path.getsize(file_path)
        file_ext = Path(file_path).suffix

        mime_types = {
            '.pdf': 'application/pdf',
            '.json': 'application/json',
        }
        mime_type = mime_types.get(file_ext, 'application/octet-stream')

        upload_base_url = "https://generativelanguage.googleapis.com/upload/v1beta/files"
        headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json"
        }

        metadata = {"file": {"display_name": Path(file_path).name}}

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

        with open(file_path, 'rb') as f:
            file_content = f.read()

        upload_headers = {
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
            "Content-Length": str(file_size)
        }

        upload_response = requests.put(
            upload_url,
            headers=upload_headers,
            data=file_content,
            timeout=60
        )

        if upload_response.status_code != 200:
            raise Exception(f"Upload failed: {upload_response.status_code} - {upload_response.text}")

        file_info = upload_response.json().get("file", {})
        return file_info.get("uri")

    def _wait_for_processing(self, file_uri: str, max_wait: int = 60) -> str:
        """Wait for file processing to complete."""
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

        raise Exception("File processing timeout")

    def validate_schema(
        self,
        annotated_pdf_path: str,
        instruction_pdf_path: str,
        schema_file: str,
        output_file: str,
        batch_size: int = 30
    ) -> Dict[str, Any]:
        """
        Validate and enhance schema using Gemini with both form and instruction PDFs.

        Args:
            annotated_pdf_path: Annotated form PDF for visual context
            instruction_pdf_path: Instruction PDF for conditional logic and validation rules
            schema_file: Current schema
            output_file: Where to save enhanced schema
            batch_size: Number of fields to process per API call
        """
        print("="*70)
        print("GEMINI SCHEMA VALIDATION & ENHANCEMENT")
        print("="*70)

        # Load schema
        print("\n[1/8] Loading schema...")
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)

        total_fields = len(schema.get('fields', []))
        print(f"  Loaded schema with {total_fields} fields")

        # Upload PDFs
        print("\n[2/8] Uploading annotated form PDF...")
        form_uri = self._upload_file(annotated_pdf_path)
        print(f"  Uploaded: {form_uri}")

        print("\n[3/8] Uploading instruction PDF...")
        instr_uri = self._upload_file(instruction_pdf_path)
        print(f"  Uploaded: {instr_uri}")

        # Wait for processing
        print("\n[4/8] Waiting for PDF processing...")
        form_name = self._wait_for_processing(form_uri)
        instr_name = self._wait_for_processing(instr_uri)
        print(f"  Ready: {form_name}, {instr_name}")

        # Process in batches
        print(f"\n[5/8] Analyzing fields in batches of {batch_size}...")
        all_validations = {"fields": []}

        num_batches = (total_fields + batch_size - 1) // batch_size

        for batch_num in range(num_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, total_fields)

            print(f"\n  Batch {batch_num + 1}/{num_batches}: Fields {start_idx + 1}-{end_idx}")

            # Build prompt for this batch
            prompt = self._build_validation_prompt(schema, start_idx, end_idx)

            # Call Gemini API with both PDFs
            url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "file_data": {
                                    "mime_type": "application/pdf",
                                    "file_uri": form_uri
                                }
                            },
                            {
                                "file_data": {
                                    "mime_type": "application/pdf",
                                    "file_uri": instr_uri
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

            response = requests.post(url, json=payload, timeout=180)

            if response.status_code != 200:
                print(f"    WARNING: Batch {batch_num + 1} failed: {response.status_code}")
                continue

            result = response.json()
            response_text = result['candidates'][0]['content']['parts'][0]['text']

            try:
                batch_validations = json.loads(response_text)
                batch_fields = batch_validations.get('fields', [])
                all_validations['fields'].extend(batch_fields)
                print(f"    Analyzed {len(batch_fields)} fields")
            except json.JSONDecodeError as e:
                print(f"    WARNING: Failed to parse batch {batch_num + 1}: {e}")
                continue

            # Small delay to avoid rate limiting
            if batch_num < num_batches - 1:
                time.sleep(2)

        print(f"\n  Total analyzed: {len(all_validations['fields'])} fields")

        # Apply validations and enhancements
        print("\n[6/8] Applying validations and enhancements...")
        enhanced_schema = self._apply_validations(schema, all_validations)

        # Generate summary report
        print("\n[7/8] Generating validation report...")
        self._generate_report(all_validations, schema)

        # Save
        print("\n[8/8] Saving validated schema...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(enhanced_schema, f, indent=2, ensure_ascii=False)

        print("\n" + "="*70)
        print("VALIDATION & ENHANCEMENT COMPLETE")
        print("="*70)
        print(f"Enhanced schema saved to: {output_file}")

        return enhanced_schema

    def _build_validation_prompt(self, schema: Dict, start_idx: int, end_idx: int) -> str:
        """Build comprehensive validation prompt with enhanced pattern detection."""

        field_summaries = []
        for field in schema.get('fields', [])[start_idx:end_idx]:
            field_summaries.append({
                "field_id": field.get('id'),
                "current_name": field.get('name'),
                "current_type": field.get('type'),
                "section": field.get('section', '')[:60],
                "pdf_field_name": field.get('pdf_field_name', ''),
                "read_only": field.get('read_only', False),
            })

        prompt = f"""You are a government immigration form expert analyzing Form I-90 (Application to Replace Permanent Residence Card).

**You have access to:**
1. **Annotated Form PDF** - The actual form with field names labeled
2. **Instruction PDF** - Official instructions with validation rules and conditional logic

**Your Task:** Analyze each field and provide comprehensive validation information.

**Fields to Analyze:**
{json.dumps(field_summaries, indent=2)}

**For each field, provide:**

1. **field_type_correction** (if current type is WRONG):

   CRITICAL - MUTUALLY EXCLUSIVE DETECTION:
   - Search the annotated PDF for these EXACT PHRASES in tooltips/labels:
     * "select only one box"
     * "select one box"
     * "mark only one"
     * "check only one"
   - If found → field_type_correction: "radio" (NOT checkbox)

   CRITICAL - YES/NO QUESTIONS:
   - ALL Yes/No questions are mutually exclusive → "radio"
   - Example: "Do you have..." with Yes/No options → "radio"

   Field Types:
   - "radio" - Mutually exclusive (can only select ONE)
   - "checkbox" - Multiple selection allowed
   - "select" - Dropdown menu (states, height, country, etc.)
   - "date" - Date fields (MM/DD/YYYY format)
   - "text" - Regular text input
   - "textarea" - Multi-line text

   **Common Patterns:**
   - State fields → "select" (dropdown with 50 states)
   - Height feet/inches → "select" (dropdown with specific ranges)
   - Date of Birth, Date Signed, Date of Admission → "date"
   - Country → "select" (dropdown)

2. **validation_rules** (from instruction PDF):

   Extract exact validation requirements:
   - phone_number: 10 digits, pattern: ^\(\\d{{3}}\) \\d{{3}}-\\d{{4}}$
   - zip_code: 5 digits, pattern: ^\\d{{5}}$
   - postal_code: alphanumeric, pattern: ^[A-Z0-9]{{3,10}}$
   - ssn: 9 digits, pattern: ^\\d{{9}}$
   - a_number: 7-9 digits, pattern: ^\\d{{7,9}}$
   - receipt_number: EXACTLY 12 digits, pattern: ^\\d{{12}}$
   - date: MM/DD/YYYY, pattern: ^(0[1-9]|1[0-2])\\/(0[1-9]|[12][0-9]|3[01])\\/(\\d{{4}})$
   - uscis_account: EXACTLY 12 characters

   **Look for field names/labels containing:**
   - "phone", "telephone", "mobile" → phone_number
   - "zip", "ZIP Code" → zip_code
   - "postal" → postal_code
   - "SSN", "Social Security" → ssn
   - "A-Number", "Alien Registration" → a_number
   - "receipt", "case number" → receipt_number
   - "date", "birth", "signed", "admission" → date
   - "USCIS Online Account" → uscis_account

   NOTE: Do NOT provide dropdown options - these will be extracted from PDF widget metadata.

3. **conditional_logic** (STRUCTURED FORMAT):

   For fields that are read_only=true OR have conditional dependencies:

   {{
     "trigger_field": "p1_q4",
     "trigger_value": "yes",
     "dependent_fields": ["p1_q5a", "p1_q5b", "p1_q5c"],
     "unlock_method": "flip_readonly_bit",
     "description": "When Q4 is answered Yes, unlock Q5a-c for name change details",
     "pdf_field_flag_change": {{
       "bit": 0,
       "current_value": 1,
       "required_value": 0
     }}
   }}

   unlock_method options:
   - "flip_readonly_bit" - Clear bit 0 in PDF field_flags to make editable
   - "voice_ai_only" - Only enforce in voice UI, PDF doesn't support
   - "javascript" - Requires PDF JavaScript (not supported by PyMuPDF)

   **From instruction PDF, identify:**
   - Which question/field triggers the conditional
   - What value unlocks the dependent fields
   - Which fields become available
   - Whether it requires PDF field flag modification

4. **spoken_name** (for voice AI):
   - Natural, conversational (2-8 words)
   - Remove: "Enter", "Select", "Provide" prefixes
   - Use everyday language
   - Example: "Alien Registration Number" → "alien number"

5. **help_text** (for voice guidance):
   - Clear explanation (1-3 sentences)
   - Include WHY needed + WHERE to find it
   - Reference instruction PDF for context
   - Example: "Your alien registration number (A-Number) is a 7-9 digit number found on your green card"

**Output Format (JSON):**
{{
  "fields": [
    {{
      "field_id": "exact_field_id_from_input",
      "field_type_correction": "radio" | "checkbox" | "select" | "date" | null,
      "validation_rules": {{
        "type": "phone_number" | "zip_code" | "postal_code" | "ssn" | "a_number" | "receipt_number" | "date" | "uscis_account",
        "pattern": "regex_pattern",
        "format_hint": "user-friendly format",
        "exact_length": 12  // For fields requiring exact length
      }},
      "conditional_logic": {{
        "trigger_field": "field_id",
        "trigger_value": "yes" | "option_value",
        "dependent_fields": ["field_id1", "field_id2"],
        "unlock_method": "flip_readonly_bit" | "voice_ai_only" | "javascript",
        "description": "human-readable explanation",
        "pdf_field_flag_change": {{
          "bit": 0,
          "current_value": 1,
          "required_value": 0
        }}
      }},
      "spoken_name": "natural voice name",
      "help_text": "clear guidance"
    }}
  ]
}}

NOTE: Dropdown options will be automatically extracted from PDF widget metadata - you only need to identify that field_type should be "select".

**CRITICAL INSTRUCTIONS:**
1. Use EXACT field_id values from input
2. Search annotated PDF for "select only one" phrases - these are ALWAYS radio
3. ALL Yes/No questions are radio, not checkbox
4. For select fields, just identify type="select" - options will be extracted from widget metadata
5. For read_only fields, identify unlock conditions and bit changes needed
6. Use instruction PDF to find exact validation requirements
7. Provide exact_length for fields like USCIS account (12 chars) and receipt numbers (12 digits)

**Priority Patterns to Find:**
- "select only one box" in tooltips → radio
- "Yes/No" questions → radio
- State/Country fields → select with options
- Height fields → select with ranges
- Date fields (birth, signed, admission) → date
- Phone, ZIP, SSN, A-Number → validation rules with exact patterns
- Read-only fields that unlock conditionally → conditional_logic with bit flip
"""

        return prompt

    def _apply_validations(self, schema: Dict, validations: Dict) -> Dict:
        """Apply Gemini-identified validations to schema."""

        # Create validation lookup
        validation_map = {
            v['field_id']: v for v in validations.get('fields', [])
        }

        corrections = {
            'type_changes': 0,
            'validation_added': 0,
            'conditional_added': 0,
            'semantic_enhanced': 0,
        }

        for field in schema.get('fields', []):
            field_id = field.get('id')

            if field_id not in validation_map:
                continue

            validation = validation_map[field_id]

            # Apply field type correction
            if validation.get('field_type_correction'):
                old_type = field.get('type')
                new_type = validation['field_type_correction']
                if old_type != new_type:
                    field['type'] = new_type
                    corrections['type_changes'] += 1

            # Apply validation rules
            if validation.get('validation_rules'):
                field['validation'] = validation['validation_rules']
                corrections['validation_added'] += 1

            # Add conditional logic
            if validation.get('conditional_logic'):
                if 'help' not in field:
                    field['help'] = {}
                field['help']['conditional_logic'] = validation['conditional_logic']
                corrections['conditional_added'] += 1

            # Add semantic info
            if validation.get('spoken_name'):
                field['spoken_name'] = validation['spoken_name']
                corrections['semantic_enhanced'] += 1

            if validation.get('help_text'):
                if 'help' not in field:
                    field['help'] = {}
                field['help']['instructions'] = validation['help_text']

        print(f"  Type corrections: {corrections['type_changes']}")
        print(f"  Validation rules added: {corrections['validation_added']}")
        print(f"  Conditional logic added: {corrections['conditional_added']}")
        print(f"  Semantic enhancements: {corrections['semantic_enhanced']}")

        return schema

    def _generate_report(self, validations: Dict, schema: Dict):
        """Generate summary report of issues found."""
        print("\n  Issues Found:")

        type_corrections = [v for v in validations.get('fields', []) if v.get('field_type_correction')]
        conditionals = [v for v in validations.get('fields', []) if v.get('conditional_logic')]
        validations_added = [v for v in validations.get('fields', []) if v.get('validation_rules')]

        print(f"    - Field type corrections: {len(type_corrections)}")
        print(f"    - Conditional logic identified: {len(conditionals)}")
        print(f"    - Validation rules identified: {len(validations_added)}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 5:
        print("Usage: python gemini_schema_validator.py <annotated_pdf> <instruction_pdf> <schema_json> <output_json>")
        print("\nExample:")
        print("  python gemini_schema_validator.py \\")
        print("    test_schemas/test_pdfs/i-90/i-90-annotated.pdf \\")
        print("    test_schemas/test_pdfs/i-90/i-90instr.pdf \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v3_validated.json \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v4_gemini_validated.json")
        sys.exit(1)

    annotated_pdf = sys.argv[1]
    instruction_pdf = sys.argv[2]
    schema_file = sys.argv[3]
    output_file = sys.argv[4]

    validator = GeminiSchemaValidator()
    validator.validate_schema(annotated_pdf, instruction_pdf, schema_file, output_file)
