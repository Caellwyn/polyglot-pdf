"""
Gemini-based schema enhancement - V2 with batching and separate API calls.

V2 Features:
- Three separate API calls (spoken names, groupings, conditionals)
- Batching: 50 fields per call to prevent response truncation
- PDF upload caching: Upload once, reuse URI across all calls
- Focused prompts for each enhancement type
"""

import os
import json
import requests
from typing import List, Dict, Any, Optional
from pathlib import Path

from gemini_models_v2 import (
    SpokenNamesResponse,
    GroupingsResponse,
    ConditionalsResponse,
    get_spoken_names_schema,
    get_groupings_schema,
    get_conditionals_schema
)


# Batch size for processing fields (tested safe limit)
BATCH_SIZE = 50


class GeminiEnhancerV2:
    """Enhances PDF form schemas using Google Gemini 2.0 Flash with batching."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the enhancer with API credentials."""
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        self.model = "gemini-2.0-flash-exp"
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

        # Cache for uploaded PDF URI (reused across all API calls)
        self._uploaded_pdf_uri: Optional[str] = None
        self._current_pdf_path: Optional[str] = None

    def _upload_pdf(self, pdf_path: str) -> str:
        """
        Upload PDF using resumable upload protocol.
        Caches the URI for reuse across multiple API calls.
        """
        # Return cached URI if same PDF
        if self._uploaded_pdf_uri and self._current_pdf_path == pdf_path:
            print(f"[CACHE] Reusing uploaded PDF URI")
            return self._uploaded_pdf_uri

        print(f"[UPLOAD] Uploading PDF: {pdf_path}")

        # Read PDF file
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        file_size = pdf_path_obj.stat().st_size

        # Step 1: Initiate resumable upload
        init_url = f"{self.base_url}/upload/files?key={self.api_key}"
        init_headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": "application/pdf",
            "Content-Type": "application/json"
        }
        init_body = {
            "file": {
                "display_name": pdf_path_obj.name
            }
        }

        init_response = requests.post(init_url, headers=init_headers, json=init_body)
        init_response.raise_for_status()

        upload_url = init_response.headers.get("X-Goog-Upload-URL")
        if not upload_url:
            raise RuntimeError("No upload URL returned from initiation")

        # Step 2: Upload file content
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()

        upload_headers = {
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
            "Content-Length": str(file_size)
        }

        upload_response = requests.post(upload_url, headers=upload_headers, data=pdf_data)
        upload_response.raise_for_status()

        upload_result = upload_response.json()
        file_uri = upload_result.get("file", {}).get("uri")

        if not file_uri:
            raise RuntimeError("No file URI returned from upload")

        print(f"[OK] PDF uploaded: {file_uri}")

        # Cache the URI
        self._uploaded_pdf_uri = file_uri
        self._current_pdf_path = pdf_path

        return file_uri

    def _call_gemini_api(
        self,
        pdf_uri: str,
        prompt: str,
        response_schema: dict,
        temperature: float = 0.2
    ) -> dict:
        """Make a single API call to Gemini with structured output."""
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"file_data": {"file_uri": pdf_uri, "mime_type": "application/pdf"}},
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "responseModalities": ["TEXT"],
                "responseMimeType": "application/json",
                "responseSchema": response_schema
            }
        }

        response = requests.post(url, json=payload)
        response.raise_for_status()

        return response.json()

    def enhance_spoken_names(
        self,
        pdf_path: str,
        fields: List[Dict[str, Any]],
        form_metadata: Dict[str, Any]
    ) -> List[SpokenNamesResponse]:
        """
        Enhance spoken names and help text for fields in batches.

        Returns:
            List of SpokenNamesResponse objects (one per batch)
        """
        print(f"\n[GEMINI] Enhancing spoken names for {len(fields)} fields...")

        # Upload PDF once
        pdf_uri = self._upload_pdf(pdf_path)

        # Process in batches
        batches = [fields[i:i + BATCH_SIZE] for i in range(0, len(fields), BATCH_SIZE)]
        responses = []

        for batch_idx, batch in enumerate(batches, 1):
            print(f"[GEMINI] Processing batch {batch_idx}/{len(batches)} ({len(batch)} fields)...")

            prompt = self._build_spoken_names_prompt(batch, form_metadata)
            schema = get_spoken_names_schema()

            response_data = self._call_gemini_api(pdf_uri, prompt, schema)

            # Parse response
            candidate = response_data.get("candidates", [{}])[0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])

            if not parts:
                raise RuntimeError(f"No response parts in batch {batch_idx}")

            text = parts[0].get("text", "")
            parsed = json.loads(text)

            response_obj = SpokenNamesResponse(**parsed)
            responses.append(response_obj)

            print(f"[OK] Batch {batch_idx}: {len(response_obj.field_enhancements)} enhancements")

        return responses

    def enhance_groupings(
        self,
        pdf_path: str,
        fields: List[Dict[str, Any]],
        form_metadata: Dict[str, Any]
    ) -> GroupingsResponse:
        """
        Enhance widget groupings for radio/checkbox fields only.

        Returns:
            Single GroupingsResponse with all identified groups
        """
        # Filter to only radio and checkbox fields
        groupable_fields = [
            f for f in fields
            if f.get("field_type") in ["radio", "checkbox"]
        ]

        if not groupable_fields:
            print("[INFO] No radio/checkbox fields to group")
            return GroupingsResponse(widget_groups=[])

        print(f"\n[GEMINI] Identifying groups for {len(groupable_fields)} radio/checkbox fields...")

        # Upload PDF once
        pdf_uri = self._upload_pdf(pdf_path)

        prompt = self._build_groupings_prompt(groupable_fields, form_metadata)
        schema = get_groupings_schema()

        response_data = self._call_gemini_api(pdf_uri, prompt, schema)

        # Parse response
        candidate = response_data.get("candidates", [{}])[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        if not parts:
            raise RuntimeError("No response parts in groupings call")

        text = parts[0].get("text", "")
        parsed = json.loads(text)

        response_obj = GroupingsResponse(**parsed)

        print(f"[OK] Identified {len(response_obj.widget_groups)} groups")

        return response_obj

    def enhance_conditionals(
        self,
        pdf_path: str,
        fields: List[Dict[str, Any]],
        form_metadata: Dict[str, Any]
    ) -> List[ConditionalsResponse]:
        """
        Enhance conditional rules in batches (best effort, optional).

        Returns:
            List of ConditionalsResponse objects (one per batch)
        """
        print(f"\n[GEMINI] Identifying conditional rules for {len(fields)} fields...")

        # Upload PDF once
        pdf_uri = self._upload_pdf(pdf_path)

        # Process in batches
        batches = [fields[i:i + BATCH_SIZE] for i in range(0, len(fields), BATCH_SIZE)]
        responses = []

        for batch_idx, batch in enumerate(batches, 1):
            print(f"[GEMINI] Processing batch {batch_idx}/{len(batches)} ({len(batch)} fields)...")

            prompt = self._build_conditionals_prompt(batch, form_metadata)
            schema = get_conditionals_schema()

            response_data = self._call_gemini_api(pdf_uri, prompt, schema)

            # Parse response
            candidate = response_data.get("candidates", [{}])[0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])

            if not parts:
                raise RuntimeError(f"No response parts in batch {batch_idx}")

            text = parts[0].get("text", "")
            parsed = json.loads(text)

            response_obj = ConditionalsResponse(**parsed)
            responses.append(response_obj)

            print(f"[OK] Batch {batch_idx}: {len(response_obj.conditional_rules)} rules")

        return responses

    # ========================================================================
    # PROMPT BUILDERS
    # ========================================================================

    def _build_spoken_names_prompt(
        self,
        fields: List[Dict[str, Any]],
        form_metadata: Dict[str, Any]
    ) -> str:
        """Build focused prompt for spoken names and help text."""
        form_title = form_metadata.get("form_title", "Unknown Form")
        form_number = form_metadata.get("form_number", "")

        prompt = f"""You are analyzing form "{form_title}" {form_number}.

Your task: Generate clear, unique spoken names and helpful directions for each field.

CRITICAL: Each spoken name must be UNIQUE. Add context prefixes to disambiguate similar fields.

Example:
- "First Name" and "First Name" in different sections → "Applicant First Name", "Spouse First Name"
- Multiple date fields → "Birth Date", "Marriage Date", "Entry Date"

Guidelines:
- Spoken names: Clear, natural, conversational (how you'd ask for this info verbally)
- Help text: Brief directions or clarifications (optional, only if helpful)
- Confidence: Your confidence level (0.0 to 1.0)

Fields to enhance:
{json.dumps(fields, indent=2)}

Return JSON with field_enhancements array containing spoken_name, help_text, and confidence for each field.
"""
        return prompt

    def _build_groupings_prompt(
        self,
        fields: List[Dict[str, Any]],
        form_metadata: Dict[str, Any]
    ) -> str:
        """Build focused prompt for radio/checkbox groupings."""
        form_title = form_metadata.get("form_title", "Unknown Form")

        prompt = f"""You are analyzing form "{form_title}".

Your task: Identify logical groups of related radio buttons and checkboxes.

Guidelines:
- Only group radio buttons and checkboxes
- Group name: Logical name (e.g., "marital_status", "contact_preferences")
- Group label: Human-readable label (e.g., "Marital Status", "Contact Preferences")
- is_exclusive: True for radio buttons (only one can be selected), False for checkboxes
- Confidence: Your confidence level (0.0 to 1.0)

Fields to analyze:
{json.dumps(fields, indent=2)}

Return JSON with widget_groups array.
"""
        return prompt

    def _build_conditionals_prompt(
        self,
        fields: List[Dict[str, Any]],
        form_metadata: Dict[str, Any]
    ) -> str:
        """Build focused prompt for conditional rules (best effort)."""
        form_title = form_metadata.get("form_title", "Unknown Form")

        prompt = f"""You are analyzing form "{form_title}".

Your task: Identify conditional rules where field values affect other fields (show/hide/require).

This is BEST EFFORT - only identify rules you're confident about.

Guidelines:
- condition_type: "show", "hide", or "require"
- trigger_field_id: The field whose value triggers the rule
- trigger_value: The value that triggers (if applicable)
- description: Clear explanation of the rule
- Confidence: Your confidence level (0.0 to 1.0)

Fields to analyze:
{json.dumps(fields, indent=2)}

Return JSON with conditional_rules array. Return empty array if no confident rules found.
"""
        return prompt
