"""
Half-Cascade Pipeline Service - Phase 3A

This service orchestrates the complete half-cascade architecture:
1. Receives complete audio utterances from frontend
2. Transcribes via Flash-Lite ASR with structured output
3. Executes tool calls for form updates
4. Generates multi-language TTS audio
5. Streams audio chunks back to frontend
6. Returns transcripts for conversation history

Key Features:
- End-to-end audio processing pipeline
- Tool call integration
- Multi-language TTS streaming
- Stateless design (frontend holds state)
- <1 second latency target (P95)
- Graceful error recovery
"""

import asyncio
import base64
import structlog
from typing import Dict, List, Optional, Any, AsyncIterator
from dataclasses import dataclass

# Handle both package imports and direct imports for testing
try:
    from ..services.flash_lite_asr import FlashLiteASR
    from ..services.flash_tts_service import FlashTTSService
    from ..services.tts_segment_queue import SegmentQueue
    from ..services.structured_output_parser import StructuredOutputParser
    from ..models.websocket_messages import (
        create_processing_status,
        create_language_status,
        create_transcript,
        create_audio_response_chunk,
        create_half_cascade_error,
    )
except ImportError:
    from services.flash_lite_asr import FlashLiteASR
    from services.flash_tts_service import FlashTTSService
    from services.tts_segment_queue import SegmentQueue
    from services.structured_output_parser import StructuredOutputParser
    from models.websocket_messages import (
        create_processing_status,
        create_language_status,
        create_transcript,
        create_audio_response_chunk,
        create_half_cascade_error,
    )

_log = structlog.get_logger().bind(module="half_cascade_pipeline")


@dataclass
class PipelineRequest:
    """Request data for half-cascade pipeline processing."""
    audio_data_base64: str  # Base64-encoded audio (PCM16, 16kHz)
    form_state: str  # "field:value|field:value" format
    current_field: Optional[str] = None
    current_part: Optional[str] = None
    conversation_history: List[Dict[str, str]] = None
    session_id: Optional[str] = None

    def __post_init__(self):
        if self.conversation_history is None:
            self.conversation_history = []


@dataclass
class PipelineResponse:
    """Response data from half-cascade pipeline."""
    user_transcript: str
    assistant_response: str
    detected_language: str
    tool_calls: List[Dict[str, Any]]
    audio_chunks: List[bytes]  # Generated audio chunks
    segments: List[Dict[str, Any]]  # Response segments with language tags
    success: bool = True
    error: Optional[str] = None


class HalfCascadePipeline:
    """
    Main orchestrator for half-cascade architecture.

    Coordinates:
    - Flash-Lite ASR for transcription
    - Tool execution for form updates
    - Flash-TTS for multi-language audio generation
    - WebSocket messaging for frontend updates
    """

    def __init__(
        self,
        api_key: str,
        websocket,
        flash_lite_model: str = "gemini-2.5-flash-lite-preview",
        flash_tts_model: str = "gemini-2.5-flash-preview-tts",
        session_id: Optional[str] = None,
        tool_executor: Optional[Any] = None,
    ):
        """
        Initialize half-cascade pipeline.

        Args:
            api_key: Gemini API key
            websocket: WebSocket connection for sending updates
            flash_lite_model: ASR model name
            flash_tts_model: TTS model name
            session_id: Session ID for logging
            tool_executor: Tool executor for form updates (optional)
        """
        self._api_key = api_key
        self._websocket = websocket
        self._session_id = session_id
        self._tool_executor = tool_executor

        # Initialize services
        self._asr = FlashLiteASR(
            api_key=api_key,
            model=flash_lite_model,
            session_id=session_id
        )

        self._tts = FlashTTSService(
            model_name=flash_tts_model,
            session_id=session_id
        )

        self._segment_queue = SegmentQueue(
            tts_service=self._tts,
            buffer_chunks=3,
            max_concurrent_synthesis=2
        )

        self._parser = StructuredOutputParser()

        _log.info(
            "half_cascade_pipeline_initialized",
            session_id=session_id,
            flash_lite_model=flash_lite_model,
            flash_tts_model=flash_tts_model
        )

    async def process_utterance(
        self,
        request: PipelineRequest,
        schema: Optional[Dict] = None,
    ) -> PipelineResponse:
        """
        Process a complete audio utterance through the half-cascade pipeline.

        Flow:
        1. Send processing status: "buffering"
        2. Transcribe audio via Flash-Lite ASR
        3. Send processing status: "transcribing"
        4. Parse structured JSON response
        5. Extract user transcript, segments, tool calls
        6. Send language status to frontend
        7. Execute tool calls (if any)
        8. Send processing status: "generating"
        9. Generate TTS audio for each segment
        10. Send processing status: "synthesizing"
        11. Stream audio chunks to frontend
        12. Return transcript for conversation history

        Args:
            request: Pipeline request with audio and state
            schema: Optional form schema for context

        Returns:
            PipelineResponse with transcripts, audio, and tool results

        Raises:
            Exception: If pipeline processing fails
        """
        log = _log.bind(session_id=request.session_id)
        log.info(
            "pipeline_processing_started",
            has_audio=bool(request.audio_data_base64),
            has_form_state=bool(request.form_state),
            history_length=len(request.conversation_history)
        )

        try:
            # Step 1: Decode audio data
            await self._send_status("buffering", progress=10)
            audio_bytes = base64.b64decode(request.audio_data_base64)
            log.info("audio_decoded", bytes=len(audio_bytes))

            # Step 2: Parse form state into dict
            form_state_dict = self._parse_form_state(request.form_state)

            # Step 3: Transcribe via Flash-Lite ASR
            await self._send_status("transcribing", progress=30)

            # Call Flash-Lite ASR with proper parameters
            flash_response = await self._asr.transcribe_and_respond(
                audio_bytes=audio_bytes,
                form_schema=schema or {},
                form_state=form_state_dict,
                conversation_history=request.conversation_history,
                current_field=request.current_field,
                current_part=request.current_part
            )

            log.info("asr_response_received", has_response=bool(flash_response))

            # Step 4: Extract fields from Pydantic response
            user_transcript = flash_response.user_transcript
            detected_language = flash_response.detected_language
            segments = flash_response.segments
            tool_calls = flash_response.tool_calls or []

            log.info(
                "response_parsed",
                user_transcript=user_transcript[:50] if user_transcript else None,
                detected_language=detected_language,
                segment_count=len(segments),
                tool_call_count=len(tool_calls)
            )

            # Step 5: Send language status to frontend
            await self._send_language_status(
                detected=detected_language,
                current=detected_language,
                confidence=segments[0].confidence if segments and segments[0].confidence else 0.95
            )

            # Step 6: Execute tool calls (Phase 3B integration point)
            await self._send_status("generating", progress=50)
            if tool_calls and self._tool_executor:
                await self._execute_tools(tool_calls)

            # Step 7: Generate TTS audio for each segment
            await self._send_status("synthesizing", progress=70)

            # Queue all segments for synthesis
            for segment in segments:
                self._segment_queue.add_segment(
                    text=segment.text,
                    language=segment.language,
                    confidence=segment.confidence
                )

            # Step 8: Stream audio chunks to frontend
            audio_chunks = []
            async for chunk in self._segment_queue.stream_audio():
                # Base64 encode audio data for WebSocket transmission
                audio_b64 = base64.b64encode(chunk.data).decode('utf-8')

                # Send audio chunk to frontend
                await self._send_audio_chunk(
                    audio_data=audio_b64,
                    language=chunk.language,
                    is_final=chunk.is_last_in_segment
                )
                audio_chunks.append(chunk.data)

            # Step 9: Build assistant response text
            assistant_response = " ".join([seg.text for seg in segments])

            # Step 10: Send transcript to frontend
            await self._send_transcript(
                user_transcript=user_transcript,
                assistant_response=assistant_response,
                language=detected_language
            )

            log.info(
                "pipeline_processing_completed",
                audio_chunks=len(audio_chunks),
                assistant_response_length=len(assistant_response)
            )

            # Convert tool calls to dicts for response
            tool_calls_dicts = [
                {"tool": tc.tool, "args": tc.args}
                for tc in tool_calls
            ] if tool_calls else []

            # Convert segments to dicts for response
            segments_dicts = [
                {
                    "text": seg.text,
                    "language": seg.language,
                    "confidence": seg.confidence
                }
                for seg in segments
            ]

            return PipelineResponse(
                user_transcript=user_transcript,
                assistant_response=assistant_response,
                detected_language=detected_language,
                tool_calls=tool_calls_dicts,
                audio_chunks=audio_chunks,
                segments=segments_dicts,
                success=True
            )

        except Exception as e:
            log.error("pipeline_processing_failed", error=str(e), exc_info=True)
            await self._send_error(
                error_code="pipeline_error",
                message=str(e),
                recoverable=True
            )
            raise

    def _parse_form_state(self, form_state: str) -> Dict[str, Any]:
        """
        Parse compact form state string into dict.

        Format: "field1:value1|field2:value2|field3:value3"

        Args:
            form_state: Compact form state string

        Returns:
            Dict mapping field IDs to values
        """
        if not form_state:
            return {}

        result = {}
        pairs = form_state.split("|")
        for pair in pairs:
            if ":" in pair:
                field_id, value = pair.split(":", 1)
                result[field_id] = value

        return result

    async def _execute_tools(self, tool_calls: List[Any]) -> None:
        """
        Execute tool calls for form updates.

        Args:
            tool_calls: List of ToolCall Pydantic models

        Note:
            This is a placeholder for Phase 3B integration.
            Tool executor should be injected during initialization.
        """
        log = _log.bind(session_id=self._session_id)

        if not self._tool_executor:
            log.warning("tool_executor_not_configured", tool_count=len(tool_calls))
            return

        log.info("executing_tools", tool_count=len(tool_calls))

        for tool_call in tool_calls:
            # Handle both Pydantic models and dicts
            if hasattr(tool_call, 'tool'):
                tool_name = tool_call.tool
                tool_args = tool_call.args
            else:
                tool_name = tool_call.get("tool")
                tool_args = tool_call.get("args", {})

            try:
                # Execute tool via injected executor
                result = await self._tool_executor.execute(tool_name, tool_args)
                log.info(
                    "tool_executed",
                    tool=tool_name,
                    success=result.get("success", False)
                )
            except Exception as e:
                log.error(
                    "tool_execution_failed",
                    tool=tool_name,
                    error=str(e),
                    exc_info=True
                )
                # Don't fail entire pipeline on tool errors
                continue

    async def _send_status(self, stage: str, progress: int = 0) -> None:
        """Send processing status to frontend."""
        if self._websocket:
            message = create_processing_status(stage=stage, progress=progress)
            await self._websocket.send_json(message)

    async def _send_language_status(
        self,
        detected: str,
        current: str,
        confidence: float
    ) -> None:
        """Send language detection status to frontend."""
        if self._websocket:
            message = create_language_status(
                detected=detected,
                current=current,
                confidence=confidence
            )
            await self._websocket.send_json(message)

    async def _send_transcript(
        self,
        user_transcript: str,
        assistant_response: str,
        language: str
    ) -> None:
        """Send transcript to frontend for conversation history."""
        if self._websocket:
            message = create_transcript(
                user_transcript=user_transcript,
                assistant_response=assistant_response,
                language=language
            )
            await self._websocket.send_json(message)

    async def _send_audio_chunk(
        self,
        audio_data: bytes,
        language: str,
        is_final: bool
    ) -> None:
        """Send audio chunk to frontend."""
        if self._websocket:
            message = create_audio_response_chunk(
                audio_data=audio_data,
                language=language,
                is_final=is_final
            )
            await self._websocket.send_json(message)

    async def _send_error(
        self,
        error_code: str,
        message: str,
        recoverable: bool,
        fallback_activated: bool = False
    ) -> None:
        """Send error message to frontend."""
        if self._websocket:
            error_message = create_half_cascade_error(
                error_code=error_code,
                message=message,
                fallback_activated=fallback_activated,
                recoverable=recoverable
            )
            await self._websocket.send_json(error_message)

    async def cleanup(self) -> None:
        """Clean up pipeline resources."""
        log = _log.bind(session_id=self._session_id)
        log.info("cleaning_up_pipeline")

        # Close HTTP client in ASR service
        if hasattr(self._asr, '_client'):
            await self._asr._client.aclose()

        # Cancel any pending synthesis tasks
        if hasattr(self._segment_queue, '_synthesis_tasks'):
            for task in self._segment_queue._synthesis_tasks:
                if not task.done():
                    task.cancel()

        log.info("pipeline_cleanup_complete")
