"""
Gemini API Integration for PDF Schema Enhancement

Handles PDF upload, API calls, and response parsing for semantic enhancement.

@version 1.0.0
@date 2025-11-10
"""

import os
import json
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from gemini_models import (
    SimplifiedField,
    GeminiInput,
    GeminiEnhancement,
    get_gemini_response_schema
)

# Load environment variables
load_dotenv()


class GeminiEnhancer:
    """
    Handles Gemini API integration for PDF schema enhancement.

    Features:
    - PDF upload via resumable upload API
    - Structured output generation
    - Cost tracking
    - Error handling with retries
    """

    BASE_URL = "https://generativelanguage.googleapis.com"
    DEFAULT_MODEL = "gemini-2.0-flash-exp"

    # Cost per million tokens (as of Nov 2025)
    INPUT_COST_PER_M = 0.01875   # $0.01875 per 1M input tokens
    OUTPUT_COST_PER_M = 0.075    # $0.075 per 1M output tokens

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        """
        Initialize Gemini enhancer.

        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
            model: Model to use (default: gemini-2.0-flash-exp)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        self.model = model
        self.total_cost = 0.0
        self.last_response = None

    def upload_pdf(self, pdf_path: str, display_name: Optional[str] = None) -> Dict[str, str]:
        """
        Upload PDF to Gemini using resumable upload protocol.

        Args:
            pdf_path: Path to PDF file
            display_name: Display name for the file (defaults to filename)

        Returns:
            Dict with 'uri' and 'name' of uploaded file

        Raises:
            Exception if upload fails
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        file_size = pdf_path.stat().st_size
        display_name = display_name or pdf_path.stem

        print(f"[UPLOAD] Uploading PDF: {pdf_path.name} ({file_size:,} bytes)")

        # Step 1: Initialize resumable upload
        init_url = f"{self.BASE_URL}/upload/v1beta/files?key={self.api_key}"
        init_headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": "application/pdf",
            "Content-Type": "application/json"
        }
        init_body = {
            "file": {
                "display_name": display_name
            }
        }

        init_response = requests.post(init_url, headers=init_headers, json=init_body)
        init_response.raise_for_status()

        # Extract upload URL from response headers
        upload_url = init_response.headers.get("X-Goog-Upload-URL")
        if not upload_url:
            raise Exception("No upload URL in response headers")

        # Step 2: Upload file content
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()

        upload_headers = {
            "Content-Length": str(file_size),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize"
        }

        upload_response = requests.post(upload_url, headers=upload_headers, data=pdf_bytes)
        upload_response.raise_for_status()

        file_info = upload_response.json()
        file_uri = file_info["file"]["uri"]
        file_name = file_info["file"]["name"]

        print(f"[OK] PDF uploaded: {file_name}")
        print(f"   URI: {file_uri}")

        # Step 3: Wait for file to be processed (if needed)
        state = file_info["file"].get("state", "ACTIVE")
        if state == "PROCESSING":
            print("[WAIT] Waiting for file processing...")
            file_uri, file_name = self._wait_for_file_active(file_name)

        return {
            "uri": file_uri,
            "name": file_name
        }

    def _wait_for_file_active(self, file_name: str, max_wait: int = 60) -> tuple:
        """
        Wait for uploaded file to become ACTIVE.

        Args:
            file_name: File name from upload response
            max_wait: Maximum seconds to wait

        Returns:
            Tuple of (file_uri, file_name)
        """
        check_url = f"{self.BASE_URL}/v1beta/{file_name}?key={self.api_key}"
        start_time = time.time()

        while time.time() - start_time < max_wait:
            response = requests.get(check_url)
            response.raise_for_status()
            file_info = response.json()

            state = file_info.get("state", "UNKNOWN")
            if state == "ACTIVE":
                return file_info["uri"], file_info["name"]
            elif state == "FAILED":
                raise Exception(f"File processing failed: {file_info.get('error')}")

            time.sleep(2)

        raise Exception(f"File processing timeout after {max_wait}s")

    def enhance_schema(
        self,
        annotated_pdf_path: str,
        simplified_fields: list[SimplifiedField],
        form_metadata: Dict[str, Any]
    ) -> GeminiEnhancement:
        """
        Enhance schema using Gemini API.

        Args:
            annotated_pdf_path: Path to annotated PDF with field IDs overlaid
            simplified_fields: List of SimplifiedField objects
            form_metadata: Form metadata (number, title, etc.)

        Returns:
            GeminiEnhancement with semantic improvements
        """
        # Upload annotated PDF
        file_info = self.upload_pdf(annotated_pdf_path)
        file_uri = file_info["uri"]

        # Build input object
        gemini_input = GeminiInput(
            form_metadata=form_metadata,
            fields=simplified_fields
        )

        # Generate prompt
        system_instruction = self._build_system_instruction()
        user_prompt = self._build_user_prompt(gemini_input)

        print(f"\n[GEMINI] Calling Gemini API...")
        print(f"   Model: {self.model}")
        print(f"   Fields: {len(simplified_fields)}")

        # Call Gemini API
        response = self._call_gemini_api(
            file_uri=file_uri,
            user_prompt=user_prompt,
            system_instruction=system_instruction,
            fields_json=json.dumps([f.model_dump() for f in simplified_fields], indent=2)
        )

        # Parse response
        enhancement = self._parse_response(response)

        # Track costs
        self._calculate_cost(response)

        return enhancement

    def _build_system_instruction(self) -> str:
        """Build system instruction for Gemini."""
        return """You are an expert government form analyst specializing in PDF form extraction.

Your task is to analyze a PDF form and enhance a machine-generated schema with semantic understanding.

You will receive:
1. An annotated PDF with field IDs overlaid on the visual form (colored boxes with IDs)
2. A JSON list of field metadata (ID, type, label, position)

Your job is to provide semantic enhancements:

**1. Widget Groups** - Identify related fields that should be grouped
   - Address blocks (street, city, state, zip)
   - Name fields (first, middle, last)
   - Radio button groups (mutually exclusive choices)
   - Checkbox groups (multiple selections)
   - Date ranges (from date, to date)

**2. Spoken Names** - CRITICAL: Must be UNIQUE across entire form
   - Create short, natural voice-friendly names (2-4 words max)
   - Add CONTEXT PREFIXES for disambiguation:
     * Names: "your first name", "spouse's first name", "father's given name"
     * Addresses: "mailing street", "home street", "prior street"
     * Dates: "birth date", "entry date", "marriage date", "expiration date"
   - Use common abbreviations: "SSN", "A-Number", "I-94"
   - Examples:
     * "A-Number" not just "number"
     * "father's given name" not just "given name"
     * "mailing zip code" not just "zip code"

   **VALIDATE BEFORE RETURNING:** Check that ALL spoken names are unique!

**3. Help Text** - User-friendly instructions
   - What the field is for
   - Where to find the information
   - Format requirements
   - Examples of valid values
   - Legal warnings if applicable

**4. Conditional Logic** - Show/hide relationships (best effort)
   - If field X = "Yes", show fields [Y, Z]
   - If checkbox A is checked, require field B
   - Look for visual cues: "If yes, complete below", "Select all that apply"

**5. Validation Rules** - Format patterns
   - SSN: format_preset "ssn"
   - A-Number: format_preset "a_number"
   - Phone: format_preset "phone"
   - Email: format_preset "email"
   - Dates: format_preset "date"

**Quality Requirements:**
- ALL spoken names MUST be unique (no duplicates)
- All field IDs referenced must exist in the input list
- Help text should be clear, specific, and helpful
- Prioritize spoken names and help text over groups/conditionals

Focus your effort on creating excellent spoken names and help text - these are most important!"""

    def _build_user_prompt(self, gemini_input: GeminiInput) -> str:
        """Build user prompt for specific form."""
        form_num = gemini_input.form_metadata.get("form_number", "Unknown")
        form_title = gemini_input.form_metadata.get("title", "Unknown Form")
        num_fields = len(gemini_input.fields)

        return f"""Analyze the attached PDF form ({form_num}: {form_title}) and enhance the field schema.

The PDF has field IDs overlaid in colored boxes. Use these IDs when referencing fields.

This form has {num_fields} fields. Focus on:

1. **Creating unique spoken names** - Add context prefixes to disambiguate similar fields
   - If there are multiple "first name" fields, use "your first name", "spouse's first name", etc.
   - If there are multiple addresses, use "mailing address", "home address", "prior address"

2. **Writing helpful instructions** - Clear, specific help text for each field

3. **Identifying groups** - Address blocks, name groups, date ranges (best effort)

4. **Detecting conditional logic** - Look for "if yes" instructions (best effort)

**CRITICAL:** Verify all spoken names are unique before returning!

The field list is provided separately. Analyze the visual PDF to understand the context and meaning of each field."""

    def _call_gemini_api(
        self,
        file_uri: str,
        user_prompt: str,
        system_instruction: str,
        fields_json: str
    ) -> Dict[str, Any]:
        """
        Call Gemini API with structured output.

        Args:
            file_uri: URI of uploaded PDF
            user_prompt: User prompt
            system_instruction: System instruction
            fields_json: JSON string of simplified fields

        Returns:
            API response dict
        """
        url = f"{self.BASE_URL}/v1beta/models/{self.model}:generateContent"

        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }

        body = {
            "contents": [{
                "parts": [
                    {
                        "file_data": {
                            "mime_type": "application/pdf",
                            "file_uri": file_uri
                        }
                    },
                    {
                        "text": f"Field list:\n```json\n{fields_json}\n```"
                    },
                    {
                        "text": user_prompt
                    }
                ]
            }],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "temperature": 0.1,  # Low for consistency
                "responseMimeType": "application/json",
                "responseSchema": get_gemini_response_schema()
            }
        }

        response = requests.post(url, headers=headers, json=body)
        response.raise_for_status()

        self.last_response = response.json()
        return self.last_response

    def _parse_response(self, response: Dict[str, Any]) -> GeminiEnhancement:
        """
        Parse Gemini API response into GeminiEnhancement object.

        Args:
            response: Raw API response

        Returns:
            GeminiEnhancement object
        """
        if "candidates" not in response or len(response["candidates"]) == 0:
            raise Exception("No candidates in Gemini response")

        candidate = response["candidates"][0]
        if "content" not in candidate:
            raise Exception("No content in candidate")

        parts = candidate["content"]["parts"]
        if len(parts) == 0 or "text" not in parts[0]:
            raise Exception("No text in response parts")

        # Parse JSON response
        enhancement_json = json.loads(parts[0]["text"])

        # Convert to Pydantic model
        enhancement = GeminiEnhancement(**enhancement_json)

        print(f"\n[OK] Enhancement received:")
        print(f"   Widget groups: {len(enhancement.widget_groups)}")
        print(f"   Conditional rules: {len(enhancement.conditional_rules)}")
        print(f"   Field enhancements: {len(enhancement.field_enhancements)}")
        print(f"   Confidence: {enhancement.confidence:.2%}")

        return enhancement

    def _calculate_cost(self, response: Dict[str, Any]) -> None:
        """Calculate and track API costs."""
        if "usageMetadata" not in response:
            print("[WARN] No usage metadata in response")
            return

        metadata = response["usageMetadata"]
        prompt_tokens = metadata.get("promptTokenCount", 0)
        candidates_tokens = metadata.get("candidatesTokenCount", 0)
        total_tokens = metadata.get("totalTokenCount", 0)

        input_cost = (prompt_tokens / 1_000_000) * self.INPUT_COST_PER_M
        output_cost = (candidates_tokens / 1_000_000) * self.OUTPUT_COST_PER_M
        total_cost = input_cost + output_cost

        self.total_cost += total_cost

        print(f"\n[COST] API Cost:")
        print(f"   Input tokens: {prompt_tokens:,} (${input_cost:.4f})")
        print(f"   Output tokens: {candidates_tokens:,} (${output_cost:.4f})")
        print(f"   Total: {total_tokens:,} tokens (${total_cost:.4f})")
        print(f"   Session total: ${self.total_cost:.4f}")


def enhance_pdf_schema(
    annotated_pdf_path: str,
    simplified_fields: list[SimplifiedField],
    form_metadata: Dict[str, Any],
    api_key: Optional[str] = None
) -> GeminiEnhancement:
    """
    Convenience function for one-shot schema enhancement.

    Args:
        annotated_pdf_path: Path to annotated PDF
        simplified_fields: List of SimplifiedField objects
        form_metadata: Form metadata
        api_key: Optional API key (defaults to env var)

    Returns:
        GeminiEnhancement object
    """
    enhancer = GeminiEnhancer(api_key=api_key)
    return enhancer.enhance_schema(annotated_pdf_path, simplified_fields, form_metadata)
