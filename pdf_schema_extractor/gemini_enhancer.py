#!/usr/bin/env python3
"""
Gemini-based semantic enhancement for PDF schema extraction.

This module uses Gemini AI to infer semantic field types, identify field groups,
and validate table structures that are difficult to detect with pure heuristics.
"""

import os
import json
import requests
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .models import FormField, FieldType


@dataclass
class FieldTypeInference:
    """Result of Gemini field type inference."""
    field_id: str
    semantic_type: str
    confidence: float
    reasoning: str
    date_format: Optional[str] = None
    date_precision: Optional[str] = None
    rows: Optional[int] = None


class GeminiEnhancer:
    """Enhances heuristically-extracted schema using Gemini AI."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash-lite"):
        """
        Initialize Gemini enhancer.

        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
            model: Gemini model to use (default: gemini-2.5-flash-lite)
        """
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def infer_field_types(self, fields: List[FormField], batch_size: int = 20) -> List[FormField]:
        """
        Infer semantic field types for all fields using Gemini.

        Args:
            fields: List of FormField objects to enhance
            batch_size: Number of fields to process per API call

        Returns:
            List of enhanced FormField objects with corrected types
        """
        enhanced_fields = []

        # Process fields in batches to reduce API calls
        for i in range(0, len(fields), batch_size):
            batch = fields[i:i + batch_size]

            # Skip table fields - they're already correct
            text_fields = [f for f in batch if f.type in (FieldType.TEXT, FieldType.CHECKBOX)]
            if not text_fields:
                enhanced_fields.extend(batch)
                continue

            print(f"  Inferring types for fields {i+1}-{min(i+batch_size, len(fields))}...")

            try:
                inferences = self._infer_batch(text_fields)
                enhanced_batch = self._apply_inferences(batch, inferences)
                enhanced_fields.extend(enhanced_batch)
            except Exception as e:
                print(f"  Warning: Gemini inference failed for batch: {e}")
                print(f"  Falling back to original types for this batch")
                enhanced_fields.extend(batch)

        return enhanced_fields

    def _infer_batch(self, fields: List[FormField]) -> List[FieldTypeInference]:
        """Infer types for a batch of fields."""
        prompt = self._build_field_type_prompt(fields)
        response_text = self._call_gemini(prompt, response_schema=self._field_type_schema())

        # Parse JSON response
        inferences_data = json.loads(response_text)
        inferences = []

        for item in inferences_data.get('inferences', []):
            inferences.append(FieldTypeInference(
                field_id=item['field_id'],
                semantic_type=item['semantic_type'],
                confidence=item.get('confidence', 0.5),
                reasoning=item.get('reasoning', ''),
                date_format=item.get('date_format'),
                date_precision=item.get('date_precision'),
                rows=item.get('rows')
            ))

        return inferences

    def _build_field_type_prompt(self, fields: List[FormField]) -> str:
        """Build prompt for batch field type inference."""
        fields_text = ""
        for field in fields:
            fields_text += f"""
Field ID: {field.id}
Label: {field.name}
PDF Field Name: {field.pdf_field_name}
Current Type: {field.type.value}
Section: {field.section_id}
---
"""

        return f"""You are a PDF form field type classifier. Analyze these form fields and infer their semantic types.

Available semantic types:
- text: Generic text input
- textarea: Multi-line text input (usually taller fields)
- date: Date input (look for: birth, expiration, date)
- email: Email address
- tel: Phone/telephone number
- number: Numeric input (SSN, A-Number, I-94)
- signature: Signature field
- checkbox: Single checkbox
- radio: Radio button (mutually exclusive options)

Fields to analyze:
{fields_text}

For each field, provide:
1. field_id: The ID of the field
2. semantic_type: One of the types above
3. confidence: Float 0.0-1.0 (how confident you are)
4. reasoning: Brief explanation (max 50 words)

For date fields, also provide:
- date_format: e.g., "mm/dd/yyyy", "mm/yyyy", "yyyy"
- date_precision: "full", "month_year", or "year_only"

For textarea fields, also provide:
- rows: Estimated number of rows (2-20)

Return your analysis as JSON matching the schema provided."""

    def _field_type_schema(self) -> Dict[str, Any]:
        """JSON schema for field type inference response."""
        return {
            "type": "object",
            "properties": {
                "inferences": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field_id": {"type": "string"},
                            "semantic_type": {
                                "type": "string",
                                "enum": ["text", "textarea", "date", "email", "tel", "number", "signature", "checkbox", "radio"]
                            },
                            "confidence": {"type": "number"},
                            "reasoning": {"type": "string"},
                            "date_format": {"type": "string"},
                            "date_precision": {"type": "string"},
                            "rows": {"type": "integer"}
                        },
                        "required": ["field_id", "semantic_type", "confidence", "reasoning"]
                    }
                }
            },
            "required": ["inferences"]
        }

    def _apply_inferences(
        self,
        fields: List[FormField],
        inferences: List[FieldTypeInference]
    ) -> List[FormField]:
        """Apply Gemini inferences to fields."""
        # Build lookup map
        inference_map = {inf.field_id: inf for inf in inferences}

        enhanced = []
        for field in fields:
            inference = inference_map.get(field.id)

            if inference and inference.confidence >= 0.5:
                # Apply the inference
                try:
                    new_type = FieldType(inference.semantic_type)

                    # Only change if different from current type
                    if new_type != field.type:
                        # Create updated field
                        field.type = new_type

                        # Apply type-specific enhancements
                        if new_type == FieldType.TEXTAREA and inference.rows:
                            field.rows = inference.rows
                        elif new_type == FieldType.DATE:
                            if inference.date_format:
                                field.format = inference.date_format
                            if inference.date_precision:
                                # Would need to add date_precision to model
                                pass

                        print(f"    ✓ {field.id}: {field.type.value} (confidence: {inference.confidence:.2f})")

                except (ValueError, AttributeError) as e:
                    print(f"    Warning: Could not apply inference for {field.id}: {e}")

            enhanced.append(field)

        return enhanced

    def _call_gemini(self, prompt: str, response_schema: Optional[Dict] = None) -> str:
        """
        Make API call to Gemini.

        Args:
            prompt: The prompt to send
            response_schema: Optional JSON schema for structured output

        Returns:
            Response text from Gemini
        """
        url = f"{self.base_url}/models/{self.model}:generateContent"

        headers = {
            'Content-Type': 'application/json',
            'x-goog-api-key': self.api_key
        }

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        # Add structured output config if schema provided
        if response_schema:
            payload["generationConfig"] = {
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
                "temperature": 0.1  # Low temperature for consistent results
            }

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        return result['candidates'][0]['content']['parts'][0]['text']


# Convenience function for use in extractor
def enhance_fields_with_gemini(fields: List[FormField]) -> List[FormField]:
    """
    Enhance fields using Gemini AI.

    This is a convenience wrapper around GeminiEnhancer.infer_field_types()
    that handles initialization and error handling.

    Args:
        fields: List of FormField objects to enhance

    Returns:
        List of enhanced FormField objects
    """
    try:
        enhancer = GeminiEnhancer()
        return enhancer.infer_field_types(fields)
    except ValueError as e:
        print(f"  Warning: Gemini enhancement skipped: {e}")
        return fields
    except Exception as e:
        print(f"  Warning: Gemini enhancement failed: {e}")
        print(f"  Falling back to original field types")
        return fields
