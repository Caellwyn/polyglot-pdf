"""
Gemini Flash API Adapter (Half-Cascade Architecture)

Handles interactions with Gemini 2.5 Flash-Lite (ASR) and Flash-TTS (TTS)
with explicit context caching support for multi-user scalability.

Architecture:
- ASR: Flash-Lite Preview (audio → structured JSON with language tags)
- TTS: Flash-TTS Preview (text → audio with language switching)
- Caching: Explicit caches for schema + annotated PDF

Key Features:
- Explicit context caching with shared cache references
- PDF upload and caching for visual cross-reference
- Cache validation and auto-refresh
- Vertex AI integration
- Structured output support
"""

import os
import json
import base64
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import timedelta
import structlog

# Vertex AI imports
try:
    from google import genai
    from google.genai import types
    from google.api_core import exceptions as gcp_exceptions
    VERTEX_AI_AVAILABLE = True
except ImportError:
    VERTEX_AI_AVAILABLE = False
    genai = None
    types = None
    gcp_exceptions = None

_log = structlog.get_logger().bind(module="gemini_flash_api")


class GeminiFlashClient:
    """
    Client for Gemini Flash-Lite and Flash-TTS APIs with explicit caching.

    Adapted from context_caching.py best practices:
    - Uploads PDF files for visual cross-reference
    - Creates explicit caches with schema + PDF
    - Validates and refreshes caches before expiry
    - Shares caches across concurrent users
    """

    def __init__(
        self,
        project_id: str,
        location: str = "us-central1",
        flash_lite_model: str = "gemini-2.5-flash-lite-preview",
        flash_tts_model: str = "gemini-2.5-flash-preview-tts"
    ):
        """
        Initialize Gemini Flash client.

        Args:
            project_id: Google Cloud project ID
            location: GCP region
            flash_lite_model: Flash-Lite model for ASR
            flash_tts_model: Flash-TTS model for TTS
        """
        if not VERTEX_AI_AVAILABLE:
            raise ImportError(
                "Vertex AI libraries not available. Install with: "
                "pip install google-generativeai google-cloud-aiplatform"
            )

        self.project_id = project_id
        self.location = location
        self.flash_lite_model = flash_lite_model
        self.flash_tts_model = flash_tts_model

        # Initialize Vertex AI client
        self.client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location
        )

        _log.info(
            "gemini_flash_client_initialized",
            project_id=project_id,
            location=location,
            flash_lite_model=flash_lite_model,
            flash_tts_model=flash_tts_model
        )

    async def create_explicit_cache(
        self,
        form_type: str,
        schema: Dict[str, Any],
        pdf_path: Path,
        ttl_days: int = 1  # 24 hours (Gemini max)
    ) -> Optional[str]:
        """
        Create explicit cache with schema + annotated PDF.

        Adapted from context_caching.py best practices.

        Args:
            form_type: Form type (e.g., "i-90")
            schema: Form schema dict
            pdf_path: Path to annotated PDF
            ttl_days: Time-to-live in days (max 1 for Gemini)

        Returns:
            str: Cache ID if successful, None otherwise
        """
        if not pdf_path.exists():
            _log.error(
                "pdf_not_found_for_caching",
                form_type=form_type,
                pdf_path=str(pdf_path)
            )
            return None

        try:
            # 1. Upload PDF file
            _log.info(
                "uploading_pdf_for_cache",
                form_type=form_type,
                pdf_path=str(pdf_path),
                file_size_mb=round(pdf_path.stat().st_size / (1024 * 1024), 2)
            )

            uploaded_file = self.client.files.upload(
                file=str(pdf_path),
                config=dict(mime_type='application/pdf')
            )

            _log.info(
                "pdf_uploaded",
                form_type=form_type,
                file_name=uploaded_file.name
            )

            # 2. Build system instruction
            system_instruction = self._build_system_instruction(form_type, schema)

            # 3. Build schema content as text
            schema_json_text = json.dumps(schema, indent=2)

            # 4. Combine all cached content
            # Order matters: System instruction → PDF → Schema
            full_knowledge_content = [
                types.Part.from_text(system_instruction),
                uploaded_file,  # Gemini can visually read this
                types.Part.from_text(
                    f"\n--- FULL FORM SCHEMA KNOWLEDGE BASE ---\n{schema_json_text}"
                )
            ]

            # 5. Convert TTL to seconds string (e.g., "86400s" for 1 day)
            ttl_seconds = str(int(timedelta(days=ttl_days).total_seconds())) + "s"

            # 6. Create cache
            _log.info(
                "creating_explicit_cache",
                form_type=form_type,
                ttl_days=ttl_days,
                model=self.flash_lite_model
            )

            cache = self.client.caches.create(
                model=self.flash_lite_model,
                contents=full_knowledge_content,
                config=types.CreateCachedContentConfig(
                    ttl=ttl_seconds,
                    # System instruction already included in contents
                )
            )

            _log.info(
                "explicit_cache_created",
                form_type=form_type,
                cache_id=cache.name,
                ttl=ttl_seconds
            )

            # 7. Clean up uploaded file (it's now in the cache)
            try:
                self.client.files.delete(name=uploaded_file.name)
                _log.debug(
                    "uploaded_file_deleted",
                    file_name=uploaded_file.name
                )
            except Exception as e:
                _log.warning(
                    "failed_to_delete_uploaded_file",
                    file_name=uploaded_file.name,
                    error=str(e)
                )

            return cache.name

        except Exception as e:
            _log.error(
                "cache_creation_failed",
                form_type=form_type,
                error=str(e),
                exc_info=True
            )
            return None

    def validate_cache(self, cache_id: str) -> bool:
        """
        Validate that a cache exists and is ready.

        Args:
            cache_id: Cache ID to validate

        Returns:
            bool: True if cache is valid and ready
        """
        if not cache_id or not cache_id.startswith("caches/"):
            return False

        try:
            cache = self.client.caches.get(name=cache_id)
            is_ready = cache.state == types.CachedContent.State.READY

            _log.debug(
                "cache_validated",
                cache_id=cache_id,
                state=cache.state,
                is_ready=is_ready
            )

            return is_ready

        except gcp_exceptions.NotFound:
            _log.warning(
                "cache_not_found",
                cache_id=cache_id
            )
            return False
        except Exception as e:
            _log.error(
                "cache_validation_failed",
                cache_id=cache_id,
                error=str(e)
            )
            return False

    async def delete_cache(self, cache_id: str) -> bool:
        """
        Delete a cache.

        Args:
            cache_id: Cache ID to delete

        Returns:
            bool: True if deletion successful
        """
        if not cache_id or not cache_id.startswith("caches/"):
            return False

        try:
            self.client.caches.delete(name=cache_id)
            _log.info("cache_deleted", cache_id=cache_id)
            return True

        except gcp_exceptions.NotFound:
            _log.warning("cache_already_deleted", cache_id=cache_id)
            return True  # Already deleted
        except Exception as e:
            _log.error(
                "cache_deletion_failed",
                cache_id=cache_id,
                error=str(e)
            )
            return False

    async def transcribe_audio_with_cache(
        self,
        audio_data: bytes,
        cache_id: str,
        form_state: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        current_field: Optional[str] = None,
        current_part: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Transcribe audio using Flash-Lite with cached context.

        Args:
            audio_data: Audio bytes (16kHz PCM16)
            cache_id: Active cache ID to use
            form_state: Current form field values
            conversation_history: Recent conversation turns
            current_field: Currently focused field
            current_part: Current part/section

        Returns:
            dict: Structured response with transcript, segments, tool calls
        """
        try:
            # 1. Encode audio as base64
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')

            # 2. Build dynamic context (uncached portion)
            dynamic_context = self._build_dynamic_context(
                form_state,
                conversation_history,
                current_field,
                current_part
            )

            # 3. Build conversation history
            history_parts = []
            for turn in conversation_history[-10:]:  # Last 10 turns
                history_parts.append(
                    types.Content(
                        role=turn.get('role', 'user'),
                        parts=[types.Part.from_text(turn.get('content', ''))]
                    )
                )

            # 4. Add current request with audio + dynamic context
            history_parts.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(dynamic_context),
                        types.Part.from_bytes(
                            data=audio_data,
                            mime_type="audio/pcm"
                        )
                    ]
                )
            )

            # 5. Call Flash-Lite with cached content
            _log.debug(
                "calling_flash_lite_with_cache",
                cache_id=cache_id,
                audio_size_kb=len(audio_data) / 1024,
                history_turns=len(history_parts)
            )

            response = self.client.models.generate_content(
                model=self.flash_lite_model,
                contents=history_parts,
                config=types.GenerateContentConfig(
                    cached_content=cache_id,
                    # Tool configuration would go here if needed
                )
            )

            # 6. Parse structured response
            # TODO: Parse based on your structured output schema
            result = {
                "user_transcript": response.text if hasattr(response, 'text') else "",
                "segments": [],  # Parse from structured output
                "tool_calls": []  # Parse from function calls
            }

            _log.info(
                "flash_lite_transcription_complete",
                cache_id=cache_id,
                transcript_length=len(result["user_transcript"])
            )

            return result

        except Exception as e:
            _log.error(
                "flash_lite_transcription_failed",
                cache_id=cache_id,
                error=str(e),
                exc_info=True
            )
            return None

    def _build_system_instruction(
        self,
        form_type: str,
        schema: Dict[str, Any]
    ) -> str:
        """
        Build system instruction for cached content.

        Args:
            form_type: Form type
            schema: Form schema

        Returns:
            str: System instruction text
        """
        form_title = schema.get("form_metadata", {}).get("title", f"Form {form_type.upper()}")

        instruction = f"""You are an expert USCIS {form_title} Form Assistant.

Your task is conversational: provide accurate, supportive guidance, answer document-specific
questions, and help users fill out the form correctly.

You have access to:
1. The annotated PDF (visual representation of the form)
2. The complete structural schema (field IDs, types, validation rules)
3. The user's current form state and conversation history

Use the PDF to understand field locations and visual context. Use the schema to ensure
correct field IDs and validation. Cross-reference both to provide accurate guidance.

Key responsibilities:
- Answer questions about where to find information
- Provide examples of correct field formats
- Explain what each field means and why it's required
- Guide users through the form logically
- Use exact field IDs from the schema for tool calls
"""

        return instruction

    def _build_dynamic_context(
        self,
        form_state: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        current_field: Optional[str],
        current_part: Optional[str]
    ) -> str:
        """
        Build dynamic context (uncached portion).

        Args:
            form_state: Current field values
            conversation_history: Recent conversation
            current_field: Current field ID
            current_part: Current part ID

        Returns:
            str: Formatted dynamic context
        """
        # Format form state (compact)
        if form_state:
            state_entries = [
                f"{field_id}:{value}"
                for field_id, value in form_state.items()
                if value
            ]
            form_state_str = "|".join(state_entries) if state_entries else "(empty)"
        else:
            form_state_str = "(empty)"

        context = f"""---
Current form values: {form_state_str}
Current field: {current_field or "(none)"}
Current part: {current_part or "(none)"}
---
Process the user's audio input and provide guidance."""

        return context


def create_flash_client(
    project_id: str,
    location: str = "us-central1"
) -> GeminiFlashClient:
    """
    Factory function to create Gemini Flash client.

    Args:
        project_id: Google Cloud project ID
        location: GCP region

    Returns:
        GeminiFlashClient: Configured client
    """
    return GeminiFlashClient(
        project_id=project_id,
        location=location
    )
