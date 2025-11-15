"""
Flash-Lite ASR (Automatic Speech Recognition) Service.

Handles integration with Gemini 2.5 Flash-Lite Preview for audio transcription
and response generation with structured output in the half-cascade architecture.
"""

import base64
import json
from typing import Dict, List, Optional, Tuple, Any
import structlog
import httpx

from backend.models.half_cascade_schema import (
    FlashLiteResponse,
    generate_json_schema_for_gemini,
    SUPPORTED_LANGUAGES
)
from backend.services.structured_output_parser import get_parser

_log = structlog.get_logger().bind(module="flash_lite_asr")


class FlashLiteASR:
    """
    Gemini Flash-Lite ASR service for half-cascade architecture.

    Handles audio transcription, language detection, and response generation
    with structured JSON output.
    """

    # API Configuration
    DEFAULT_MODEL = "gemini-2.5-flash-lite-preview"
    API_ENDPOINT_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    # Audio Configuration
    AUDIO_ENCODING = "audio/pcm"  # 16-bit PCM
    AUDIO_SAMPLE_RATE = 16000  # 16kHz

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        session_id: Optional[str] = None
    ):
        """
        Initialize Flash-Lite ASR service.

        Args:
            api_key: Gemini API key
            model: Flash-Lite model name
            session_id: Optional session ID for logging
        """
        self._api_key = api_key
        self._model = model
        self._session_id = session_id
        self._parser = get_parser()

        # HTTP client for API requests
        self._client = httpx.AsyncClient(timeout=30.0)

        # System instruction template
        self._system_instruction = self._build_system_instruction()

        _log.info(
            "flash_lite_asr_initialized",
            model=model,
            session_id=session_id
        )

    def _build_system_instruction(self) -> str:
        """
        Build system instruction for Flash-Lite.

        Returns:
            str: System instruction template
        """
        return """You are a multilingual form-filling assistant for USCIS immigration forms.

OUTPUT FORMAT:
You must output valid JSON matching the provided schema. Include the user's transcribed speech in "user_transcript" field.

LANGUAGE HANDLING:
1. Detect the user's spoken language from their audio
2. Set "detected_language" field with the BCP 47 language code
3. Tag each response segment with its language
4. Respond in the user's detected language (not English unless they speak English)
5. Form field values must be in English, but conversation is in user's language

CONTEXT HANDLING:
You will receive the current form state and conversation history with each request.
Use this context to:
- Avoid re-asking for information already provided
- Reference previous answers when clarifying
- Maintain conversational continuity
- Guide user through the form logically

TOOL INTEGRATION:
Include tool calls in the "tool_calls" array when updating form fields.
Always confirm the value with the user before calling tools.

ACCURACY REQUIREMENTS:
- Confirm each field value verbally before proceeding
- Ask for clarification if uncertain
- Validate logical consistency (e.g., dates, ages, phone numbers)
- One field at a time for accuracy

CURRENT FORM SCHEMA:
{schema}"""

    async def transcribe_and_respond(
        self,
        audio_bytes: bytes,
        form_schema: Dict[str, Any],
        form_state: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        current_field: Optional[str] = None,
        current_part: Optional[str] = None
    ) -> FlashLiteResponse:
        """
        Send audio to Flash-Lite and get structured response.

        Args:
            audio_bytes: Raw audio bytes (PCM16, 16kHz)
            form_schema: Current form schema for context
            form_state: Current form field values
            conversation_history: Recent conversation turns
            current_field: Currently focused field ID
            current_part: Current part/section ID

        Returns:
            FlashLiteResponse: Parsed and validated response

        Raises:
            Exception: If API request fails or response is invalid
        """
        # Build context prompt
        context = self._build_context(
            form_schema=form_schema,
            form_state=form_state,
            conversation_history=conversation_history,
            current_field=current_field,
            current_part=current_part
        )

        # Encode audio as base64
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')

        # Build request payload
        request_payload = self._build_request_payload(
            audio_b64=audio_b64,
            context=context
        )

        _log.info(
            "flash_lite_request",
            audio_bytes=len(audio_bytes),
            context_length=len(context),
            session_id=self._session_id
        )

        # Send request to Flash-Lite API
        try:
            response = await self._send_request(request_payload)

            # Parse and validate response
            parsed_response = self._parse_response(response)

            _log.info(
                "flash_lite_response_received",
                detected_language=parsed_response.detected_language,
                segments=len(parsed_response.segments),
                tool_calls=len(parsed_response.tool_calls) if parsed_response.tool_calls else 0,
                session_id=self._session_id
            )

            return parsed_response

        except Exception as e:
            _log.error(
                "flash_lite_request_failed",
                error=str(e),
                session_id=self._session_id
            )
            raise

    def _build_context(
        self,
        form_schema: Dict[str, Any],
        form_state: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        current_field: Optional[str],
        current_part: Optional[str]
    ) -> str:
        """
        Build context string for Flash-Lite prompt.

        Context includes:
        - Form schema (for caching)
        - Current form state
        - Current field/part
        - Recent conversation history

        Args:
            form_schema: Form schema dict
            form_state: Current field values
            conversation_history: Recent conversation turns
            current_field: Current field ID
            current_part: Current part ID

        Returns:
            str: Formatted context string
        """
        # Format schema (simplified for token efficiency)
        schema_str = json.dumps(form_schema, indent=None, separators=(',', ':'))

        # Format form state (compact pipe-separated format)
        if form_state:
            state_entries = [
                f"{field_id}:{value}"
                for field_id, value in form_state.items()
                if value  # Only include non-empty values
            ]
            form_state_str = "|".join(state_entries)
        else:
            form_state_str = "(empty)"

        # Format conversation history (last 5-10 turns)
        history_lines = []
        for turn in conversation_history[-10:]:  # Last 10 turns max
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            history_lines.append(f"{role.capitalize()}: {content}")
        history_str = "\n".join(history_lines) if history_lines else "(no history)"

        # Build complete context
        context = f"""---
Current form values: {form_state_str}
Current field: {current_field or "(none)"}
Current part: {current_part or "(none)"}
Recent conversation:
{history_str}
---"""

        return context

    def _build_request_payload(
        self,
        audio_b64: str,
        context: str
    ) -> Dict[str, Any]:
        """
        Build API request payload for Flash-Lite.

        Args:
            audio_b64: Base64-encoded audio
            context: Context string

        Returns:
            dict: Request payload for Gemini API
        """
        # Get structured output schema
        output_schema = generate_json_schema_for_gemini()

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": context
                        },
                        {
                            "inline_data": {
                                "mime_type": f"{self.AUDIO_ENCODING};rate={self.AUDIO_SAMPLE_RATE}",
                                "data": audio_b64
                            }
                        }
                    ]
                }
            ],
            "systemInstruction": {
                "parts": [
                    {
                        "text": self._system_instruction.format(
                            schema="(See form schema in context)"
                        )
                    }
                ]
            },
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": output_schema,
                "temperature": 0.7,
                "topP": 0.95,
                "topK": 40
            }
        }

        return payload

    async def _send_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send request to Flash-Lite API.

        Args:
            payload: Request payload

        Returns:
            dict: API response

        Raises:
            Exception: If request fails
        """
        url = self.API_ENDPOINT_TEMPLATE.format(model=self._model)

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key
        }

        response = await self._client.post(
            url,
            headers=headers,
            json=payload
        )

        response.raise_for_status()

        return response.json()

    def _parse_response(self, api_response: Dict[str, Any]) -> FlashLiteResponse:
        """
        Parse API response and extract structured JSON.

        Args:
            api_response: Raw API response

        Returns:
            FlashLiteResponse: Parsed and validated response

        Raises:
            ValueError: If response format is invalid
        """
        try:
            # Extract generated content
            candidates = api_response.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates in API response")

            candidate = candidates[0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])

            if not parts:
                raise ValueError("No parts in candidate content")

            # Extract JSON text
            json_text = parts[0].get("text", "")

            if not json_text:
                raise ValueError("Empty response text")

            # Parse using structured output parser
            parsed = self._parser.parse_response(json_text)

            return parsed

        except Exception as e:
            _log.error(
                "response_parse_failed",
                error=str(e),
                response_keys=list(api_response.keys()),
                session_id=self._session_id
            )
            raise

    async def cleanup(self) -> None:
        """Cleanup resources."""
        await self._client.aclose()

        _log.info(
            "flash_lite_asr_cleaned_up",
            session_id=self._session_id
        )


def create_flash_lite_asr(
    api_key: str,
    model: str = FlashLiteASR.DEFAULT_MODEL,
    session_id: Optional[str] = None
) -> FlashLiteASR:
    """
    Factory function to create Flash-Lite ASR instance.

    Args:
        api_key: Gemini API key
        model: Model name
        session_id: Optional session ID

    Returns:
        FlashLiteASR: Configured ASR instance
    """
    return FlashLiteASR(
        api_key=api_key,
        model=model,
        session_id=session_id
    )
