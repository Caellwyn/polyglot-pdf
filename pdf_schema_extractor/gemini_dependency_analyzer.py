#!/usr/bin/env python3
"""
Gemini Dependency Analyzer - Extract bidirectional conditional dependencies using structured outputs.

Forces Gemini to return properly structured conditional logic matching our schema model.
No more string-format conditionals or parsing failures.
"""

import json
import os
import sys
import time
import requests
from typing import Dict, List, Optional
from pathlib import Path


class GeminiDependencyAnalyzer:
    """Analyze conditional dependencies using Gemini with forced structured output."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable required")

        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = "gemini-2.0-flash-exp"  # Supports structured outputs
        self.upload_url = f"{self.base_url}/files"

    def _upload_file(self, file_path: str) -> str:
        """Upload PDF to Gemini File API."""
        files = {'file': open(file_path, 'rb')}
        headers = {'X-Goog-Upload-Protocol': 'multipart'}

        response = requests.post(
            self.upload_url,
            headers=headers,
            files=files,
            params={'key': self.api_key}
        )

        if response.status_code != 200:
            raise Exception(f"Upload failed: {response.text}")

        result = response.json()
        return result['file']['uri']

    def _wait_for_processing(self, file_uri: str, timeout: int = 60) -> str:
        """Wait for PDF to be processed."""
        file_name = file_uri.split('/')[-1]
        get_url = f"{self.upload_url}/{file_name}"

        start_time = time.time()
        while time.time() - start_time < timeout:
            response = requests.get(get_url, params={'key': self.api_key})

            if response.status_code != 200:
                raise Exception(f"Failed to check file status: {response.text}")

            result = response.json()
            state = result.get('state')

            if state == 'ACTIVE':
                return file_name
            elif state == 'FAILED':
                raise Exception(f"File processing failed: {result.get('error')}")

            time.sleep(2)

        raise TimeoutError(f"File processing timeout after {timeout}s")

    def _build_response_schema(self) -> Dict:
        """
        Build JSON schema for structured output matching FormField model.

        Forces Gemini to return bidirectional conditional logic.
        """
        return {
            "type": "OBJECT",
            "properties": {
                "fields": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "field_id": {
                                "type": "STRING",
                                "description": "Exact field ID from schema"
                            },
                            "show_if": {
                                "type": "OBJECT",
                                "description": "Conditional logic - this field is triggered by another field",
                                "properties": {
                                    "field": {
                                        "type": "STRING",
                                        "description": "Field ID that controls visibility of this field"
                                    },
                                    "operator": {
                                        "type": "STRING",
                                        "enum": ["equals", "not_equals", "contains", "is_checked", "is_empty", "is_not_empty", "in", "not_in"],
                                        "description": "Comparison operator"
                                    },
                                    "value": {
                                        "type": "STRING",
                                        "description": "Value that triggers this field to show (use 'true'/'false' for booleans)"
                                    }
                                },
                                "required": ["field", "operator", "value"]
                            },
                            "conditional_fields": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                                "description": "List of field IDs that THIS field controls/triggers"
                            },
                            "needs_unlock": {
                                "type": "BOOLEAN",
                                "description": "Whether this field requires PDF read-only bit flipping"
                            },
                            "confidence": {
                                "type": "STRING",
                                "enum": ["high", "medium", "low"],
                                "description": "Confidence level of this conditional relationship"
                            }
                        },
                        "required": ["field_id"]
                    }
                }
            },
            "required": ["fields"]
        }

    def _build_prompt(self, schema: Dict) -> str:
        """Build prompt for Gemini dependency analysis."""
        # Get field list
        field_list = []
        for field in schema.get('fields', []):
            field_info = {
                'id': field['id'],
                'name': field.get('name', ''),
                'type': field.get('type', ''),
                'read_only': field.get('read_only', False),
                'section': field.get('section', '')
            }
            field_list.append(field_info)

        return f"""# Conditional Dependency Analysis Task

You are analyzing a PDF form to identify ALL conditional field dependencies.

## Your Task

For EACH field in the schema, determine:
1. **Is it triggered by another field?** (show_if)
2. **Does it trigger other fields?** (conditional_fields)

## Field List

```json
{json.dumps(field_list, indent=2)}
```

## Instructions

### Finding Trigger Relationships (show_if)

Look at the instruction PDF and form PDF carefully. Identify fields that:
- Say "complete only if..." or "show only if..."
- Are read-only and depend on another field's value
- Have conditional logic described in instructions

**Examples:**
- "Q5a-c: Complete only if you answered YES to Question 4"
  → Q5a show_if: {{field: "p1_q4", operator: "equals", value: "yes"}}
- "Part 4 accommodation details: Show only if 'Yes' selected for requesting accommodations"
  → show_if: {{field: "p4_q1", operator: "equals", value: "yes"}}
- "Conditional Permanent Resident fields: Show only if you are a conditional permanent resident"
  → show_if: {{field: "p2_status", operator: "equals", value: "conditional_permanent_resident"}}

### Finding Controlled Fields (conditional_fields)

For each trigger field, list ALL fields it controls.

**Example:**
- Field p1_q4 "Has your name legally changed?" controls: ["p1_q5a", "p1_q5b", "p1_q5c"]
  → p1_q4 conditional_fields: ["p1_q5a", "p1_q5b", "p1_q5c"]

### Unlock Detection (needs_unlock)

Set needs_unlock=true if:
- Field is read_only=true AND has conditional logic
- Instructions say it "unlocks" or "becomes available"
- It's a PDF field that needs the READ_ONLY bit cleared

### Confidence Levels

- **high**: Clear instruction ("complete only if X is Y")
- **medium**: Implicit from context (field order, similar patterns)
- **low**: Uncertain, needs manual review

## Critical Rules

1. **Use EXACT field IDs** from the schema
2. **Both directions**: If A triggers B, then:
   - A gets: conditional_fields: ["B"]
   - B gets: show_if: {{field: "A", operator: "equals", value: "..."}}
3. **Operators**: Use "equals" for most cases, "is_checked" for checkboxes
4. **Values**: Use the actual value that triggers (e.g., "yes", "true", option ID)
5. **Pre-populated fields**: These are NOT conditional, skip them
6. **Signature fields**: Skip signature fields

## Example Output Structure

```json
{{
  "fields": [
    {{
      "field_id": "p1_q4",
      "conditional_fields": ["p1_q5a", "p1_q5b", "p1_q5c"],
      "confidence": "high"
    }},
    {{
      "field_id": "p1_q5a",
      "show_if": {{
        "field": "p1_q4",
        "operator": "equals",
        "value": "yes"
      }},
      "needs_unlock": true,
      "confidence": "high"
    }},
    {{
      "field_id": "p1_q5b",
      "show_if": {{
        "field": "p1_q4",
        "operator": "equals",
        "value": "yes"
      }},
      "needs_unlock": true,
      "confidence": "high"
    }},
    {{
      "field_id": "p1_q5c",
      "show_if": {{
        "field": "p1_q4",
        "operator": "equals",
        "value": "yes"
      }},
      "needs_unlock": true,
      "confidence": "high"
    }}
  ]
}}
```

Now analyze ALL fields and return complete bidirectional dependencies.
"""

    def analyze_dependencies(
        self,
        form_pdf_path: str,
        instruction_pdf_path: str,
        schema: Dict
    ) -> Dict:
        """
        Analyze conditional dependencies using Gemini with structured outputs.

        Returns:
            Dict with bidirectional conditional relationships
        """
        print("="*70)
        print("GEMINI DEPENDENCY ANALYZER - Structured Outputs")
        print("="*70)

        # Upload PDFs
        print("\n[1/5] Uploading form PDF...")
        form_uri = self._upload_file(form_pdf_path)
        print(f"  Uploaded: {form_uri}")

        print("\n[2/5] Uploading instruction PDF...")
        instr_uri = self._upload_file(instruction_pdf_path)
        print(f"  Uploaded: {instr_uri}")

        # Wait for processing
        print("\n[3/5] Waiting for PDF processing...")
        form_name = self._wait_for_processing(form_uri)
        instr_name = self._wait_for_processing(instr_uri)
        print(f"  Ready: {form_name}, {instr_name}")

        # Build prompt
        prompt = self._build_prompt(schema)

        # Build response schema
        response_schema = self._build_response_schema()

        # Call Gemini API with structured output
        print("\n[4/5] Analyzing dependencies with Gemini...")
        print(f"  Model: {self.model}")
        print(f"  Using structured outputs (forced schema)")

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{
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
            }],
            "generationConfig": {
                "temperature": 0.2,  # Low temp for precise extraction
                "responseMimeType": "application/json",
                "responseSchema": response_schema
            }
        }

        response = requests.post(url, json=payload, timeout=180)

        if response.status_code != 200:
            raise Exception(f"Gemini API failed: {response.status_code} - {response.text}")

        result = response.json()
        response_text = result['candidates'][0]['content']['parts'][0]['text']

        # Parse structured response (guaranteed to match schema)
        dependencies = json.loads(response_text)

        print(f"\n[5/5] Extracted dependencies:")
        print(f"  Total fields analyzed: {len(dependencies.get('fields', []))}")

        # Count relationships
        trigger_fields = len([f for f in dependencies.get('fields', []) if f.get('conditional_fields')])
        dependent_fields = len([f for f in dependencies.get('fields', []) if f.get('show_if')])
        needs_unlock = len([f for f in dependencies.get('fields', []) if f.get('needs_unlock')])

        print(f"  Trigger fields (controls others): {trigger_fields}")
        print(f"  Dependent fields (triggered by others): {dependent_fields}")
        print(f"  Fields needing unlock: {needs_unlock}")

        return dependencies


def main():
    if len(sys.argv) < 4:
        print("Usage: python gemini_dependency_analyzer.py <form.pdf> <instructions.pdf> <schema.json> [output.json]")
        print("\nExample:")
        print("  python gemini_dependency_analyzer.py \\")
        print("    test_schemas/test_pdfs/i-90/i-90.pdf \\")
        print("    test_schemas/test_pdfs/i-90/i-90_instructions.pdf \\")
        print("    test_schemas/test_pdfs/i-90/i-90_schema_v7_final.json \\")
        print("    test_schemas/test_pdfs/i-90/i-90_dependencies.json")
        sys.exit(1)

    form_pdf = sys.argv[1]
    instr_pdf = sys.argv[2]
    schema_path = sys.argv[3]
    output_path = sys.argv[4] if len(sys.argv) > 4 else schema_path.replace('.json', '_dependencies.json')

    # Load schema
    print("Loading schema...")
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)

    # Analyze dependencies
    analyzer = GeminiDependencyAnalyzer()
    dependencies = analyzer.analyze_dependencies(form_pdf, instr_pdf, schema)

    # Save results
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(dependencies, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print("DEPENDENCIES SAVED")
    print(f"{'='*70}")
    print(f"Output: {output_path}")
    print(f"\nNext steps:")
    print(f"  1. Review dependencies (especially medium/low confidence)")
    print(f"  2. Run: python apply_dependencies.py {schema_path} {output_path}")
    print(f"  3. Validate with: python schema_validator.py")


if __name__ == "__main__":
    main()
