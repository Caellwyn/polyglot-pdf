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
from typing import List, Dict, Any, Optional
from pathlib import Path

from google import genai
from google.genai import types

try:
    from .gemini_models_v2 import (
        SpokenNamesResponse, GroupingsResponse, ConditionalsResponse,
        get_spoken_names_schema, get_groupings_schema, get_conditionals_schema,
    )
except ImportError:
    from gemini_models_v2 import (
        SpokenNamesResponse, GroupingsResponse, ConditionalsResponse,
        get_spoken_names_schema, get_groupings_schema, get_conditionals_schema,
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

        # Modernized for the bake-off (bd polyglot-pdf-7a9.4): the original used
        # gemini-2.0-flash-exp (now retired). Per the epic's REFINEMENT 1, the
        # one-off authoring (b) pass can use the strongest model; override via
        # BAKEOFF_ENHANCER_MODEL. Default to a current Flash for the many cheap
        # per-batch calls.
        self.model = os.getenv("BAKEOFF_ENHANCER_MODEL", "gemini-2.5-flash")

        # Modernized for the bake-off (bd polyglot-pdf-7a9.4): the original hand-
        # rolled the v1beta REST Files API, which 404s with the current GCP-bound
        # API key format. Use the google-genai SDK with inline PDF bytes instead
        # (no separate upload step). _upload_pdf now just caches the bytes.
        self.client = genai.Client(api_key=self.api_key)
        self._pdf_bytes: Optional[bytes] = None
        self._current_pdf_path: Optional[str] = None

    def _upload_pdf(self, pdf_path: str) -> str:
        """Cache the PDF bytes for inline use; returns the path as the handle."""
        if self._pdf_bytes is not None and self._current_pdf_path == pdf_path:
            return pdf_path
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        self._pdf_bytes = pdf_path_obj.read_bytes()
        self._current_pdf_path = pdf_path
        print(f"[OK] PDF loaded inline: {pdf_path} ({len(self._pdf_bytes)} bytes)")
        return pdf_path

    def _call_gemini_api(
        self,
        pdf_uri: str,
        prompt: str,
        response_schema: dict,
        temperature: float = 0.2
    ) -> dict:
        """One structured-output call via the SDK; returns a REST-shaped dict.

        The callers parse candidates[0].content.parts[0].text, so we wrap the
        SDK response text in that shape to keep them unchanged.
        """
        resp = self.client.models.generate_content(
            model=self.model,
            contents=[
                types.Part.from_bytes(data=self._pdf_bytes,
                                      mime_type="application/pdf"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type="application/json",
                response_schema=response_schema,
                max_output_tokens=65536,
            ),
        )
        return {"candidates": [{"content": {"parts": [{"text": resp.text}]}}]}

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
            schema = SpokenNamesResponse  # Pydantic class -> SDK response_schema

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
        schema = GroupingsResponse

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
            schema = ConditionalsResponse

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
- "First Name" and "First Name" in different sections -> "Applicant First Name", "Spouse First Name"
- Multiple date fields -> "Birth Date", "Marriage Date", "Entry Date"

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
