import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional
import inspect
from copy import deepcopy
import json
import re
import os
import socket
import urllib.parse
from datetime import datetime
from pathlib import Path

from websockets.exceptions import ConnectionClosed

from google import genai
from google.genai import types
import structlog

from backend.utils.json_recovery import extract_json_from_part

from backend.ports.live_ai_port import ILiveAI, LiveAISession


# ============================================================================
# LOGGING EMOJI GUIDE (for easier log scanning)
# ============================================================================
# 📤 Initial message/prompt sent to Gemini
# ✅ Operation completed successfully  
# 🏁 Activity signal sent (turn control)
# 💬 Text message sent (hints, prompts)
# 🔊 Gemini started speaking (first audio chunk)
# 📝 Gemini finished speaking (transcript received)
# 🚨 Gemini interrupted by user (barge-in)
# 🎤 User started speaking (activity_start from frontend)
# 🤐 User stopped speaking (activity_end from frontend)
# ⚠️ Warning (non-fatal issue)
# ❌ Error (operation failed)
# ============================================================================


class LiveAIGeminiSession(LiveAISession):
    """Adapter for the Gemini Live AI session."""

    def __init__(self, session):
        self._session = session

    async def send_audio(self, pcm16_16k: bytes) -> None:
        await self._session.send_realtime_input(
            audio=types.Blob(data=pcm16_16k, mime_type="audio/pcm;rate=16000")
        )

    async def send_tool_response(self, responses: List[Dict[str, Any]]) -> None:
        function_responses = [
            types.FunctionResponse(id=r["id"], name=r["name"], response=r["response"])
            for r in responses
        ]
        # Use send_tool_response directly as shown in Vertex AI examples
        await self._session.send_tool_response(function_responses=function_responses)

    async def receive(self) -> AsyncIterator[Any]:
        # The session's receive() method returns an async iterator.
        async for chunk in self._session.receive():
            yield chunk


class LiveAIGemini(ILiveAI):
    """Adapter for the Gemini Live AI service.

    Constructor accepts the same convenience parameters as LabelingAIGemini so the
    dependency provider can pass either `api_key`, `vertexai` or `model` as keywords.
    """

    def __init__(self, api_key: str | None = None, model: str = "gemini-live-2.5-flash",
             vertexai: bool = False,
             project: str | None = None, 
             location: str = "us-central1"):
        # Prefer constructing a genai.Client() instance. Tests should patch
        # `genai.Client` to return a mock client exposing `.aio.live`.
        self._client = None
        
        # Generate unique instance ID for debugging multi-tab scenarios
        import uuid
        self._instance_id = f"LiveAI-{str(uuid.uuid4())[:8]}"
        
        # Store these as instance variables for later use
        self._vertexai = vertexai
        self._project = project
        self._location = location
        self._model_name = model
        self._client = None
        
        try:
            ClientCls = getattr(genai, "Client", None)
            if ClientCls is not None:
                # try:
                if vertexai:
                    # Vertex AI does not use API keys; the client will
                    # use Application Default Credentials.
                    self._client = ClientCls(
                        vertexai=True,
                        project=project or os.getenv("GOOGLE_CLOUD_PROJECT"),
                        location=location
                    )
                elif api_key is not None:
                    self._client = ClientCls(api_key=api_key)
                else:
                    self._client = ClientCls()
                # except Exception:
                #     # If construction fails (tests may intentionally raise),
                #     # fall back to leaving _client as None and let callers
                #     # handle it.
                #     self._client = None
        except Exception:
            self._client = None

        # Callbacks set by the service
        self._on_form_update = None
        self._on_transcript = None
        self._on_audio = None
        self._on_tool_call = None
        self._system_instruction: Optional[str] = None
        self._initial_message: str = ""
        self._function_declarations: Optional[List[Dict[str, Any]]] = None

        # Whether Gemini should be asked to return transcripts/text
        self._enable_transcripts = False

        # Background task and queue for audio streaming
        self._audio_queue: Optional[asyncio.Queue] = None
        self._text_queue: Optional[asyncio.Queue] = None  # Queue for text messages (hints)
        self._bg_task: Optional[asyncio.Task] = None
        self._current_sender_task: Optional[asyncio.Task] = None
        self._current_text_sender_task: Optional[asyncio.Task] = None
        self._current_session: Optional[Any] = None  # Store active Gemini session for text messages
        self._intentional_shutdown: bool = False  # Track intentional finalize() to prevent auto-retry

        # Lock to avoid concurrent start/stop races
        self._task_lock = asyncio.Lock()
        
        # Structured logger for this adapter
        self._log = structlog.get_logger().bind(
            adapter="LiveAIGemini", 
            model=self._model_name, 
            vertexai=self._vertexai,
            instance_id=self._instance_id  # Track which instance is logging
        )
    
    @asynccontextmanager
    async def connect(self, model: str, config: Dict[str, Any]) -> AsyncIterator[LiveAISession]:
        """Connects to the Gemini Live API and yields a session wrapper.

        Uses the underlying genai client's async context manager for live.connect.
        """
        if self._client is None or not hasattr(self._client, "aio"):
            # Attempt to construct a Client instance if possible.
            ClientCls = getattr(genai, "Client", None)
            if ClientCls is not None:
                try:
                    if self._vertexai:
                        self._client = ClientCls(
                            vertexai=True,
                            project=self._project or os.getenv("GOOGLE_CLOUD_PROJECT"),
                            location=self._location
                        )
                    else:
                        self._client = ClientCls()
                except Exception:
                    # leave _client as None
                    self._client = None

        connect_obj = self._client.aio.live.connect(model=model, config=config)

        # Modern SDKs return an async context manager; older ones return an awaitable.
        if hasattr(connect_obj, '__aenter__') and hasattr(connect_obj, '__aexit__'):
            async with connect_obj as live_session:
                yield LiveAIGeminiSession(live_session)
            return

        session = await connect_obj
        try:
            yield LiveAIGeminiSession(session)
        finally:
            close = getattr(session, 'close', None)
            if close:
                try:
                    result = close()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    pass

    def set_callbacks(
        self,
        on_form_update=None,
        on_transcript=None,
        on_audio=None,
        on_tool_call=None,
        system_instruction: str | None = None,
        initial_message: str | None = None,
        tool_declarations: list[Dict[str, Any]] | None = None,
        enable_transcripts: bool = False,
    ):
        """Register callbacks and ensure the background session task is running.

        Callbacks should be async callables. They will be awaited when invoked.
        """
        # Removed verbose logging - session lifecycle is logged elsewhere
        
        self._on_form_update = on_form_update
        self._on_transcript = on_transcript
        self._on_audio = on_audio
        self._on_tool_call = on_tool_call
        self._system_instruction = system_instruction
        self._initial_message = initial_message
        self._function_declarations = deepcopy(tool_declarations) if tool_declarations else None
        # Honor explicit enable_transcripts flag from the caller (UI/service).
        # If enable_transcripts is False, we will not request TEXT responses from Gemini
        # even if an on_transcript callback is present.
        self._enable_transcripts = bool(enable_transcripts)

        # Start background task if not already running
        if self._bg_task is None or self._bg_task.done():
            # Reset intentional shutdown flag when starting a new session
            self._intentional_shutdown = False
            
            # Lazily create audio and text queues
            # Audio queue has max size to prevent blocking - drops frames if backed up
            self._audio_queue = asyncio.Queue(maxsize=100)  # ~2 seconds of audio at 50fps
            self._text_queue = asyncio.Queue()
            self._bg_task = asyncio.create_task(self._run_session_loop())
            # Removed verbose logging - session start logged below
        else:
            self._log.warn("bg_task_already_running_callbacks_overwritten", 
                          task_id=id(self._bg_task),
                          warning="Multiple connections may be sharing callbacks!")

    def is_session_active(self) -> bool:
        """Check if Gemini session is currently active (has running background task)."""
        return self._bg_task is not None and not self._bg_task.done()

    async def stream_audio(self, audio_chunk: bytes):
        """Enqueue an audio chunk to be sent to the live session.
        
        Uses non-blocking put to avoid blocking WebSocket message loop.
        Drops audio frames if queue is backed up (better than blocking control messages).
        """
        if self._audio_queue is None:
            # If the queue isn't started, drop audio (no-op) to keep behavior
            # safe for unit tests where live AI is not configured.
            return
        try:
            # Non-blocking put - drops frame if queue is full instead of blocking
            self._audio_queue.put_nowait(audio_chunk)
        except asyncio.QueueFull:
            # Queue backed up - drop this audio frame to avoid blocking
            # Audio is resilient to dropped frames (slight quality degradation vs blocking control msgs)
            # Silent drop - this is expected behavior during normal operation
            pass

    async def send_text_message(self, text: str):
        """Send a text message to the live session (e.g., next field hints).
        
        Messages are queued and sent asynchronously without blocking.
        Used for providing context to Gemini after tool responses.
        """
        if self._text_queue is None:
            # If the queue isn't started, drop message (no-op) for safety
            return
        
        # Log text message for debugging
        self._log.debug("TEXT_MESSAGE_QUEUED", 
                      message=text)
        
        await self._text_queue.put(text)

    async def send_activity_start(self):
        """Send activity_start signal to Gemini (user started speaking).
        
        This is a client-driven VAD signal that tells Gemini to interrupt
        current generation because the user is now speaking.
        """
        if self._current_session is None:
            self._log.warning("⚠️ ACTIVITY_START_NO_SESSION")
            return
        
        try:
            from google.genai import types
            # No logging - too noisy, visible on frontend
            await self._current_session.send_realtime_input(activity_start=types.ActivityStart())
        except Exception as e:
            self._log.error("❌ ACTIVITY_START_FAILED", error=str(e))

    async def send_activity_end(self):
        """Send activity_end signal to Gemini (user stopped speaking).
        
        This is a client-driven VAD signal that tells Gemini the user
        has finished speaking and it's safe to respond.
        """
        if self._current_session is None:
            # Session not active - silently ignore (session loss already logged elsewhere)
            return
        
        try:
            from google.genai import types
            # No logging - too noisy, visible on frontend
            await self._current_session.send_realtime_input(activity_end=types.ActivityEnd())
        except Exception as e:
            self._log.error("❌ ACTIVITY_END_FAILED", error=str(e))

    async def finalize(self):
        """Stop the background task and clear resources."""
        # Set flag to prevent auto-retry after intentional shutdown
        self._intentional_shutdown = True
        
        async with self._task_lock:
            if self._bg_task is not None:
                self._bg_task.cancel()
                try:
                    await self._bg_task
                except asyncio.CancelledError:
                    pass
                self._bg_task = None
            # Drain/clear the audio queue
            if self._audio_queue is not None:
                while not self._audio_queue.empty():
                    try:
                        self._audio_queue.get_nowait()
                    except Exception:
                        break
                # Signal any running sender with sentinel and wait for it
                try:
                    if self._current_sender_task is not None:
                        try:
                            self._audio_queue.put_nowait(None)
                        except Exception:
                            # schedule a put to wake the sender
                            async def _put_sentinel(q):
                                try:
                                    await q.put(None)
                                except Exception:
                                    pass

                            asyncio.create_task(_put_sentinel(self._audio_queue))

                        try:
                            self._current_sender_task.cancel()
                        except Exception:
                            pass

                        try:
                            await asyncio.wait_for(self._current_sender_task, timeout=1.0)
                        except asyncio.CancelledError:
                            # Expected when we cancel the sender
                            pass
                        except asyncio.TimeoutError:
                            # Sender didn't stop in time, force cancel
                            self._current_sender_task.cancel()
                            try:
                                await self._current_sender_task
                            except asyncio.CancelledError:
                                pass
                        except Exception:
                            pass
                        finally:
                            self._current_sender_task = None
                except Exception:
                    pass

                self._audio_queue = None

            # Drain/clear the text queue
            if self._text_queue is not None:
                while not self._text_queue.empty():
                    try:
                        self._text_queue.get_nowait()
                    except Exception:
                        break
                # Signal any running text sender with sentinel and wait for it
                try:
                    if self._current_text_sender_task is not None:
                        try:
                            self._text_queue.put_nowait(None)
                        except Exception:
                            async def _put_text_sentinel(q):
                                try:
                                    await q.put(None)
                                except Exception:
                                    pass
                            asyncio.create_task(_put_text_sentinel(self._text_queue))

                        try:
                            self._current_text_sender_task.cancel()
                        except Exception:
                            pass

                        try:
                            await asyncio.wait_for(self._current_text_sender_task, timeout=1.0)
                        except asyncio.CancelledError:
                            pass
                        except asyncio.TimeoutError:
                            self._current_text_sender_task.cancel()
                            try:
                                await self._current_text_sender_task
                            except asyncio.CancelledError:
                                pass
                        except Exception:
                            pass
                        finally:
                            self._current_text_sender_task = None
                except Exception:
                    pass

                self._text_queue = None
            
            # Clear session reference
            self._current_session = None

    async def _run_session_loop(self):
        """Background loop that connects to Gemini Live and handles audio and events.

        This is a minimal implementation: connect, send audio from queue, and
        dispatch simple transcript/tool events to callbacks. It's intentionally
        conservative so tests and local dev don't require full protocol coverage.
        """

        # Build a minimal config; request AUDIO responses and use native
        # transcription output.
        response_modalities = ["AUDIO"]

        if self._function_declarations:
            tools_config = [{"function_declarations": deepcopy(self._function_declarations)}]
        else:
            tools_config = [{
                "function_declarations": [
                    {"name": "update_form_fields"},
                    {"name": "get_form_status"},
                ]
            }]

        config = {
            "response_modalities": response_modalities,
            "tools": tools_config,

        }
        
        # Enable automatic voice activity detection for realtime audio input
        # This allows Gemini to detect when user starts/stops speaking
        try:
            # Load VAD config from backend settings
            from backend.config import get_settings
            settings = get_settings()
            vad_settings = {}
            
            # Build VAD settings from config
            if settings.DISABLE_GEMINI_VAD:
                vad_settings['disabled'] = True

            if settings.VAD_START_SENSITIVITY and settings.VAD_START_SENSITIVITY != 'UNSPECIFIED':
                vad_settings['start_of_speech_sensitivity'] = types.StartSensitivity[f"START_SENSITIVITY_{settings.VAD_START_SENSITIVITY}"]
            
            if settings.VAD_END_SENSITIVITY and settings.VAD_END_SENSITIVITY != 'UNSPECIFIED':
                vad_settings['end_of_speech_sensitivity'] = types.EndSensitivity[f"END_SENSITIVITY_{settings.VAD_END_SENSITIVITY}"]
            
            if settings.VAD_PREFIX_PADDING_MS is not None:
                vad_settings['prefix_padding_ms'] = settings.VAD_PREFIX_PADDING_MS
            
            if settings.VAD_SILENCE_DURATION_MS is not None:
                vad_settings['silence_duration_ms'] = settings.VAD_SILENCE_DURATION_MS
            
            # Removed verbose VAD config logging
            
            # Apply VAD settings (use defaults if none configured)
            config["realtime_input_config"] = {
                "automatic_activity_detection": vad_settings if vad_settings else {}
            }
        except Exception as e:
            self._log.warn("failed_to_set_realtime_input_config", error=str(e))
        
        # Enable input transcription to see what Gemini is hearing
        if self._enable_transcripts:
            config['input_audio_transcription'] = {}
            config['output_audio_transcription'] = {}
        
        if self._system_instruction:
            config["system_instruction"] = self._system_instruction
            # Log initial system instruction for debugging
            self._log.debug("INITIAL_SYSTEM_INSTRUCTION",
                          system_instruction=self._system_instruction)

        # If client is missing, exit
        if self._client is None:
            self._log.warn("no_genai_client_configured")
            return

        try:
            # Await the connect coroutine to obtain a session
            # Quick DNS diagnostics for common Google/GenAI hosts to help
            # surface clearer errors when socket.gaierror occurs during connect.
            try:
                candidates = [
                    'api.generativeai.googleapis.com',
                    'generativeai.googleapis.com',
                    'www.google.com',
                ]
                dns_ok = []
                dns_fail = []
                for host in candidates:
                    try:
                        infos = socket.getaddrinfo(host, 443)
                        dns_ok.append((host, len(infos)))
                    except Exception as e:
                        dns_fail.append((host, str(e)))
            except Exception:
                # Never let diagnostics break the session loop
                pass

            try:
                connect_obj = self._client.aio.live.connect(model=self._model_name, config=config)
            except Exception as e:
                # Surface a clearer message when name resolution fails or socket errors occur
                try:
                    import socket as _s
                    if isinstance(e, (_s.gaierror, _s.error)):
                        self._log.error('connect_creation_failed_name_error', error=str(e))
                    else:
                        self._log.error('connect_creation_failed', error=str(e))
                except Exception:
                    self._log.error('connect_creation_failed', error=str(e))
                raise

            # Use shared helper to recover JSON payloads from non-data parts
            _extract_json_from_part = extract_json_from_part

            # Helper to run the per-session sender/receive loops for a given session
            async def _handle_session(session):
                # Track if Gemini has responded (to implement fallback retry)
                gemini_has_responded = False

                # Start a task to forward queued audio into the session
                async def audio_sender():
                    while True:
                        # Use a sentinel (None) to allow graceful shutdown without
                        # relying solely on task cancellation. This wakes the
                        # sender if it's blocked on get().
                        chunk = await self._audio_queue.get()
                        if chunk is None:
                            # Sentinel received: exit the send loop cleanly
                            break
                        try:
                            await session.send_realtime_input(
                                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                            )
                        except Exception as e:
                            self._log.error("audio_send_failed", error=str(e))
                            # swallow for robustness
                            pass

                sender_task = asyncio.create_task(audio_sender())
                # Record the running sender so external finalizers can
                # cancel/await it reliably.
                self._current_sender_task = sender_task

                # Start a task to forward queued text messages into the session
                async def text_sender():
                    while True:
                        # Use a sentinel (None) to allow graceful shutdown
                        text = await self._text_queue.get()
                        if text is None:
                            # Sentinel received: exit the send loop cleanly
                            break
                        try:
                            import time
                            t_start = time.time()
                            
                            # Wrap ALL text messages with activity signals for reliable response
                            # (recovery prompts, tool responses, etc.)
                            await session.send_realtime_input(activity_start=types.ActivityStart())
                            
                            await session.send_client_content(
                                turns={"role": "user", "parts": [{"text": text}]},
                                turn_complete=True  # Explicitly complete the turn to trigger response
                            )
                            
                            await session.send_realtime_input(activity_end=types.ActivityEnd())
                            
                            # Removed verbose logging - only errors are logged
                        except Exception as e:
                            self._log.error("❌ TEXT_SEND_FAILED", error=str(e))
                            # swallow for robustness
                            pass

                text_sender_task = asyncio.create_task(text_sender())
                self._current_text_sender_task = text_sender_task
                # Store session reference for potential direct sends
                self._current_session = session
                
                self._log.info("gemini_session_established", 
                             instance_id=self._instance_id,
                             message="Gemini Live session active and ready - waiting for user to speak")

                # ============================================================================
                # INITIAL MESSAGE DISABLED - User initiates conversation with greeting
                # ============================================================================
                # The 09-2025 model doesn't reliably respond to text-only messages.
                # Instead, we show a multilingual greeting carousel and wait for user to speak.
                # This allows natural language detection and highlights translation capability.
                #
                # if self._initial_message:
                #     try:
                #         import time
                #         await asyncio.sleep(0.5)
                #         t0 = time.time()
                #         is_section_switch = "Section" in self._initial_message and "moving to" in self._initial_message.lower()
                #         fallback_delay = 1.5 if is_section_switch else 3.0
                #         self._log.info("📤 INITIAL_MESSAGE_SENDING", 
                #                      length=len(self._initial_message),
                #                      timestamp_ms=int(t0 * 1000),
                #                      is_section_switch=is_section_switch,
                #                      fallback_delay_sec=fallback_delay)
                #         await session.send_realtime_input(activity_start=types.ActivityStart())
                #         await session.send_client_content(
                #             turns={"role": "user", "parts": [{"text": self._initial_message}]},
                #             turn_complete=True
                #         )
                #         await session.send_realtime_input(activity_end=types.ActivityEnd())
                #         self._log.info("📤 INITIAL_MESSAGE_SENT_WITH_ACTIVITY_SIGNALS")
                #         async def fallback_resend():
                #             await asyncio.sleep(fallback_delay)
                #             if not gemini_has_responded:
                #                 self._log.warning("⚠️ INITIAL_MESSAGE_FALLBACK", 
                #                                  delay_sec=fallback_delay,
                #                                  is_section_switch=is_section_switch,
                #                                  message="No response, resending initial message")
                #                 try:
                #                     await session.send_realtime_input(activity_start=types.ActivityStart())
                #                     await session.send_client_content(
                #                         turns={"role": "user", "parts": [{"text": self._initial_message}]},
                #                         turn_complete=True
                #                     )
                #                     await session.send_realtime_input(activity_end=types.ActivityEnd())
                #                 except Exception as e:
                #                     self._log.error("❌ FALLBACK_RESEND_FAILED", error=str(e))
                #         asyncio.create_task(fallback_resend())
                #     except Exception as e:
                #         self._log.exception("❌ INITIAL_MESSAGE_FAILED", error=str(e))
                # ============================================================================

                # Start heartbeat task to keep session alive during idle periods
                # Sends a small silence packet every 30 seconds to prevent timeout
                async def heartbeat():
                    while True:
                        try:
                            # Wait 30 seconds between heartbeats
                            await asyncio.sleep(30)
                            if self._current_session is not None:
                                # Send 20ms of silence (320 bytes at 16kHz PCM16)
                                silence = bytes(320)  # 160 samples * 2 bytes/sample = 320 bytes
                                await session.send_realtime_input(
                                    audio=types.Blob(data=silence, mime_type="audio/pcm;rate=16000")
                                )
                                self._log.debug("heartbeat_sent")
                        except asyncio.CancelledError:
                            # Task was cancelled, exit cleanly
                            break
                        except Exception as e:
                            self._log.warning("heartbeat_failed", error=str(e))

                heartbeat_task = asyncio.create_task(heartbeat())

                try:
                    event_count = 0
                    while True:
                        received_any = False
                        try:
                            async for event in session.receive():
                                event_count += 1
                                received_any = True
                                
                                # Audio/transcript/tool extraction
                                responses: list[types.FunctionResponse] = []
                                try:
                                    if getattr(event, "data", None) is not None:
                                        audio_bytes: bytes | None = None
                                        if isinstance(event.data, (bytes, bytearray)):
                                            audio_bytes = bytes(event.data)
                                        else:
                                            audio_bytes = getattr(event.data, "data", None)
                                        if audio_bytes and self._on_audio:
                                            # Track audio streaming for debugging transcript timing
                                            if not hasattr(self, '_audio_chunk_count'):
                                                self._audio_chunk_count = 0
                                                self._first_audio_time = None
                                            
                                            self._audio_chunk_count += 1
                                            
                                            # Track first audio chunk timing (for transcript correlation)
                                            if self._audio_chunk_count == 1:
                                                import time
                                                self._first_audio_time = time.time()
                                                self._log.info("🎵 [Gemini Audio] First audio chunk received", 
                                                             bytes=len(audio_bytes),
                                                             chunk_number=1)
                                                # Mark that Gemini has responded (cancel fallback resend)
                                                gemini_has_responded = True
                                            elif self._audio_chunk_count % 10 == 0:
                                                # Log every 10th chunk at INFO level
                                                self._log.info("🎵 [Gemini Audio] Chunk received",
                                                             chunk_number=self._audio_chunk_count,
                                                             bytes=len(audio_bytes))
                                            
                                            await self._on_audio(audio_bytes)
                                            continue

                                    server_content = getattr(event, "server_content", None)
                                    if server_content is not None:
                                        # ========================================
                                        # CHECK FOR INTERRUPTION (Barge-in)
                                        # ========================================
                                        interrupted = getattr(server_content, "interrupted", False)
                                        if interrupted:
                                            # Get canceled tool call IDs
                                            model_turn = getattr(server_content, "model_turn", None)
                                            canceled_ids = []
                                            if model_turn:
                                                parts = getattr(model_turn, "parts", [])
                                                for part in parts:
                                                    function_call = getattr(part, "function_call", None)
                                                    if function_call:
                                                        call_id = getattr(function_call, "id", None)
                                                        if call_id:
                                                            canceled_ids.append(call_id)
                                            
                                            import time
                                            now = time.time()
                                            elapsed_since_audio_start = None
                                            if hasattr(self, '_first_audio_time') and self._first_audio_time:
                                                elapsed_since_audio_start = int((now - self._first_audio_time) * 1000)
                                            
                                            self._log.info(
                                                "🚨 GEMINI_INTERRUPTED", 
                                                canceled_tool_calls=len(canceled_ids),
                                                call_ids=[cid[:8] for cid in canceled_ids],
                                                audio_chunks_before_interrupt=getattr(self, '_audio_chunk_count', 0),
                                                elapsed_since_audio_start_ms=elapsed_since_audio_start,
                                                timestamp_ms=int(now * 1000)
                                            )
                                            
                                            # Reset audio tracking since generation was interrupted
                                            self._audio_chunk_count = 0
                                            self._first_audio_time = None
                                            
                                            # Skip further processing of this event
                                            continue
                                        
                                        # ========================================
                                        # Normal processing (no interruption)
                                        # ========================================
                                        
                                        # Handle input transcription (what Gemini heard from user)
                                        input_transcription = getattr(server_content, "input_transcription", None)
                                        
                                        # Handle output transcription (what Gemini said)
                                        transcription = getattr(server_content, "output_transcription", None)
                                        if transcription is not None and getattr(transcription, "text", None):
                                            # Log transcript receipt (indicates Gemini finished speaking)
                                            import time
                                            now = time.time()
                                            elapsed_since_first_audio = None
                                            if hasattr(self, '_first_audio_time') and self._first_audio_time:
                                                elapsed_since_first_audio = int((now - self._first_audio_time) * 1000)
                                            
                                            self._log.info("📝 GEMINI_TRANSCRIPT_RECEIVED", 
                                                         text_length=len(transcription.text),
                                                         text_preview=transcription.text[:50],
                                                         audio_chunks_received=getattr(self, '_audio_chunk_count', 0),
                                                         elapsed_since_first_audio_ms=elapsed_since_first_audio,
                                                         timestamp_ms=int(now * 1000))
                                            
                                            # Reset audio tracking for next turn
                                            self._audio_chunk_count = 0
                                            self._first_audio_time = None
                                            
                                            if self._on_transcript:
                                                await self._on_transcript(transcription.text)
                                        else:
                                            model_turn = getattr(server_content, "model_turn", None)
                                            if model_turn is not None:
                                                parts = getattr(model_turn, "parts", [])
                                                if parts:
                                                    for part in parts:
                                                        # Check for audio in inline_data
                                                        inline_data = getattr(part, "inline_data", None)
                                                        if inline_data is not None:
                                                            audio_bytes = getattr(inline_data, "data", None)
                                                            mime_type = getattr(inline_data, "mime_type", None)
                                                            if audio_bytes and self._on_audio:
                                                                await self._on_audio(audio_bytes)
                                                        
                                                        # Check for function calls in parts (alternative to tool_call events)
                                                        function_call = getattr(part, "function_call", None)
                                                        if function_call:
                                                            tool_name = getattr(function_call, "name", None)
                                                            call_id = getattr(function_call, "id", None)
                                                            payload = getattr(function_call, "arguments", None) or getattr(function_call, "response", None) or getattr(function_call, "args", None)
                                                            
                                                            self._log.info("function_call_detected", 
                                                                          tool_name=tool_name,
                                                                          call_id=call_id,
                                                                          has_payload=bool(payload))

                                                            if isinstance(payload, str):
                                                                try:
                                                                    import json as _json
                                                                    parsed_arguments = _json.loads(payload)
                                                                except Exception:
                                                                    parsed_arguments = {}
                                                            else:
                                                                parsed_arguments = payload or {}
                                                            # If parsed_arguments is empty, attempt to recover JSON from
                                                            # non-data/code parts (some model responses put JSON into
                                                            # executable_code/code_execution_result sections).
                                                            if not parsed_arguments:
                                                                recovered = None
                                                                try:
                                                                    recovered = _extract_json_from_part(part)
                                                                    if recovered:
                                                                        parsed_arguments = recovered
                                                                except Exception:
                                                                    recovered = None

                                                                # If still empty, capture a detailed dump of the part
                                                                # and surrounding server_content for debugging.
                                                                if not parsed_arguments:
                                                                    # Dev logging: Show empty tool call for debugging
                                                                    from backend.utils.dev_logger import log_raw_tool_event
                                                                    log_raw_tool_event(
                                                                        "empty_tool_arguments",
                                                                        {
                                                                            "tool_name": tool_name,
                                                                            "call_id": call_id,
                                                                            "payload_type": type(payload).__name__,
                                                                            "payload_repr": repr(payload)[:500] if payload else None,
                                                                            "part_type": type(part).__name__,
                                                                        }
                                                                    )

                                                            response_payload = None

                                                            if self._on_tool_call is not None and tool_name:
                                                                try:
                                                                    # REDACT: Don't log arguments or response (contain field values)
                                                                    self._log.info("invoking_tool_callback", 
                                                                                  tool=tool_name, 
                                                                                  args_keys=list(parsed_arguments.keys()) if isinstance(parsed_arguments, dict) else None,
                                                                                  callback_id=id(self._on_tool_call))
                                                                    
                                                                    response_payload = await self._on_tool_call(tool_name, parsed_arguments)
                                                                    
                                                                    self._log.info("tool_callback_completed", tool=tool_name, response_ok=bool(response_payload))
                                                                except Exception as e:
                                                                    self._log.exception("tool_callback_error", tool=tool_name, error=str(e))
                                                                    
                                                                    # Dev logging: Log tool errors
                                                                    from backend.utils.dev_logger import log_tool_error
                                                                    log_tool_error(tool_name, e, parsed_arguments)
                                                            elif tool_name == "update_form_fields" and self._on_form_update:
                                                                await self._on_form_update(parsed_arguments)

                                                            if response_payload is None:
                                                                response_payload = {}

                                                            if tool_name and call_id:
                                                                responses.append(
                                                                    types.FunctionResponse(
                                                                        id=call_id,
                                                                        name=tool_name,
                                                                        response=response_payload,
                                                                    )
                                                                )

                                                    # Handle text transcription (only from first part for backwards compatibility)
                                                    text = getattr(parts[0], "text", None) or getattr(parts[0], "display_text", None)
                                                    if text and self._on_transcript:
                                                        await self._on_transcript(text)

                                    if getattr(event, "tool_call", None):
                                        for fc in event.tool_call.function_calls:
                                            tool_name = getattr(fc, "name", None)
                                            call_id = getattr(fc, "id", None)
                                            payload = getattr(fc, "arguments", None) or getattr(fc, "response", None) or getattr(fc, "args", None)

                                            if isinstance(payload, str):
                                                try:
                                                    import json as _json

                                                    parsed_arguments = _json.loads(payload)
                                                except Exception:
                                                    parsed_arguments = {}
                                            else:
                                                parsed_arguments = payload or {}

                                            # If parsed_arguments is empty here, log the raw tool_call
                                            # object for inspection (SDK may have placed data in
                                            # non-standard fields or nested objects).
                                            if not parsed_arguments:
                                                try:
                                                    # Try to serialize some helpful fields
                                                    raw_fc = {}
                                                    for name in ('arguments', 'response', 'args', 'name', 'id', 'raw'):
                                                        try:
                                                            raw_fc[name] = getattr(fc, name, None)
                                                        except Exception:
                                                            raw_fc[name] = None

                                                    # Keep repr trimmed
                                                    def _trim(x):
                                                        try:
                                                            s = repr(x)
                                                            return s if len(s) < 1000 else s[:1000] + '...'
                                                        except Exception:
                                                            return None

                                                    raw_fc_trimmed = {k: _trim(v) for k, v in raw_fc.items()}
                                                    
                                                    # Log warning about unparsed tool call
                                                    self._log.warn("raw_tool_call_unparsed", tool_name=tool_name, call_id=call_id, raw_fc=raw_fc_trimmed)
                                                except Exception:
                                                    try:
                                                        self._log.warn("raw_tool_call_unparsed_failed")
                                                    except Exception:
                                                        pass

                                            response_payload = None

                                            if self._on_tool_call is not None and tool_name:
                                                try:
                                                    response_payload = await self._on_tool_call(tool_name, parsed_arguments)
                                                    self._log.info("tool_callback_returned", tool_name=tool_name, has_response=response_payload is not None, response_keys=list(response_payload.keys()) if isinstance(response_payload, dict) else None)
                                                except Exception:
                                                    self._log.exception("tool_callback_error", tool=tool_name)
                                            elif tool_name == "update_form_fields" and self._on_form_update:
                                                await self._on_form_update(parsed_arguments)

                                            if response_payload is None:
                                                self._log.warning("tool_response_was_none", tool_name=tool_name, setting_to_empty_dict=True)
                                                response_payload = {}

                                            if tool_name:
                                                # According to Google's example code, FunctionResponse should NOT include 'id'
                                                # The SDK matches responses to calls internally
                                                self._log.info("preparing_function_response", tool_name=tool_name, response_has_success=response_payload.get("success") if isinstance(response_payload, dict) else None)
                                                responses.append(
                                                    types.FunctionResponse(
                                                        name=tool_name,
                                                        response=response_payload,
                                                    )
                                                )
                                                self._log.debug("tool_response_prepared", tool_name=tool_name, call_id=call_id)

                                    if responses:
                                        self._log.info("sending_tool_responses", count=len(responses), response_ids=[r.id for r in responses])
                                        await session.send_tool_response(function_responses=responses)
                                        self._log.info("tool_responses_sent_successfully", waiting_for_model_response=True)
                                        # Don't send additional prompts - just let Gemini process the tool responses
                                        # and generate its natural continuation

                                except Exception:
                                    self._log.exception("event_handling_error")
                                    continue
                        except ConnectionClosed as exc:
                            self._log.error("gemini_session_connection_closed", 
                                          reason=str(exc), 
                                          event_count=event_count)
                            break

                        if not received_any:
                            self._log.error("gemini_session_no_events_received", 
                                          event_count=event_count,
                                          message="Session ended - no events from Gemini")
                            break

                except Exception:
                    self._log.exception("receive_loop_unexpected_error")
                    raise

                # Clean up sender when receive loop ends. First, try to
                # signal the sender via a sentinel placed on the queue so it
                # can exit its loop. This avoids relying only on cancellation
                # which in some environments can leave a task pending.
                try:
                    if self._audio_queue is not None:
                        try:
                            # Try non-blocking put to wake the sender
                            self._audio_queue.put_nowait(None)
                        except Exception:
                            # If put_nowait fails (unlikely), schedule a task to
                            # put the sentinel so the sender is woken.
                            async def _put_sentinel(q):
                                try:
                                    await q.put(None)
                                except Exception:
                                    pass

                            asyncio.create_task(_put_sentinel(self._audio_queue))
                except Exception:
                    pass

                # Also signal text sender to exit
                try:
                    if self._text_queue is not None:
                        try:
                            self._text_queue.put_nowait(None)
                        except Exception:
                            async def _put_text_sentinel(q):
                                try:
                                    await q.put(None)
                                except Exception:
                                    pass
                            asyncio.create_task(_put_text_sentinel(self._text_queue))
                except Exception:
                    pass

                # Finally, cancel and await the sender task to ensure it
                # is finished before continuing. Use a short timeout to
                # avoid hangs in test environments if the task does not
                # terminate promptly.
                try:
                    sender_task.cancel()
                except Exception:
                    pass

                try:
                    await asyncio.wait_for(sender_task, timeout=1.0)
                except asyncio.CancelledError:
                    pass
                except asyncio.TimeoutError:
                    try:
                        async def _drain_task(t):
                            try:
                                await t
                            except Exception:
                                pass

                        asyncio.create_task(_drain_task(sender_task))
                    except Exception:
                        pass
                finally:
                    # Clear the tracked sender task reference
                    try:
                        self._current_sender_task = None
                    except Exception:
                        pass

                # Clean up text sender task
                try:
                    text_sender_task.cancel()
                except Exception:
                    pass

                try:
                    await asyncio.wait_for(text_sender_task, timeout=1.0)
                except asyncio.CancelledError:
                    pass
                except asyncio.TimeoutError:
                    try:
                        async def _drain_text_task(t):
                            try:
                                await t
                            except Exception:
                                pass
                        asyncio.create_task(_drain_text_task(text_sender_task))
                    except Exception:
                        pass
                finally:
                    try:
                        self._current_text_sender_task = None
                        self._current_session = None
                        self._log.info("gemini_session_cleaned_up",
                                     instance_id=self._instance_id,
                                     event_count=event_count if 'event_count' in locals() else 0,
                                     message="Session closed and cleaned up")
                    except Exception:
                        pass

                # Clean up heartbeat task
                try:
                    heartbeat_task.cancel()
                except Exception:
                    pass

                try:
                    await asyncio.wait_for(heartbeat_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                except Exception:
                    pass

            # Connect may return either an async context manager (usable with
            # `async with`) or an awaitable/coroutine yielding a session. Handle
            # both shapes.
            # Attempt to connect with retries for transient DNS/socket errors.
            max_attempts = 3
            attempt = 0
            last_exc = None
            websocket_base_override = os.environ.get('GENAI_WEBSOCKET_BASE')
            while attempt < max_attempts:
                # Check if session was intentionally finalized (Level 3 timeout, manual disconnect)
                # If so, don't retry - just exit cleanly
                if self._intentional_shutdown:
                    self._log.info("session_intentionally_closed_no_retry")
                    return
                    
                attempt += 1
                try:
                    # Re-create connect_obj each attempt to avoid reusing a failed object
                    if websocket_base_override:
                        # If the environment requests an override, attempt to patch the client's websocket base URL.
                        try:
                            api_client = getattr(self._client, '_api_client', None)
                            if api_client is not None and hasattr(api_client, '_websocket_base_url'):
                                # Monkey-patch a small lambda that returns the override bytes/string
                                api_client._websocket_base_url = lambda: websocket_base_override
                        except Exception:
                            pass

                    connect_obj = self._client.aio.live.connect(model=self._model_name, config=config)
                    # If it's an async context manager it will have __aenter__
                    if hasattr(connect_obj, "__aenter__") and hasattr(connect_obj, "__aexit__"):
                        async with connect_obj as session:
                            await _handle_session(session)
                    else:
                        # Assume awaitable/coroutine returning a session object
                        session = await connect_obj
                        await _handle_session(session)
                    # success, break out
                    last_exc = None
                    break
                except Exception as e:
                    last_exc = e
                    # If it's a name resolution / socket error, log and retry with backoff
                    is_name_err = False
                    try:
                        import socket as _s
                        if isinstance(e, (_s.gaierror, _s.error)):
                            is_name_err = True
                    except Exception:
                        pass

                    # Extract a probable host for diagnostics
                    host = None
                    try:
                        candidate = (
                            getattr(connect_obj, 'url', None)
                            or getattr(connect_obj, 'uri', None)
                            or getattr(connect_obj, '_url', None)
                            or getattr(connect_obj, 'endpoint', None)
                        )
                        if candidate and isinstance(candidate, str):
                            parsed = urllib.parse.urlparse(candidate)
                            host = parsed.hostname or (parsed.netloc.split(':')[0] if parsed.netloc else None)
                        if not host:
                            rep = repr(connect_obj)
                            m = re.search(r"(wss?://[^\s,\)\]]+)", rep)
                            if m:
                                host = urllib.parse.urlparse(m.group(1)).hostname
                    except Exception:
                        host = None

                    dns_result = None
                    if host:
                        try:
                            infos = socket.getaddrinfo(host, None)
                            dns_result = len(infos)
                        except Exception as de:
                            dns_result = str(de)

                    try:
                        self._log.error('connect_attempt_failed', attempt=attempt, error=str(e), host=host, dns=dns_result)
                    except Exception:
                        pass

                    if attempt >= max_attempts or not is_name_err:
                        # Give up and re-raise the last exception
                        raise

                    # Backoff before retrying
                    try:
                        await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                    except Exception:
                        pass

        except asyncio.CancelledError:
            # Task cancelled: allow exit
            return
        except Exception as e:
            # Log the exception message and a formatted traceback so operators
            # can diagnose connection/auth errors more easily.
            try:
                import traceback as _tb

                tb = _tb.format_exc()
            except Exception:
                tb = None
            self._log.error("session_loop_error", error=str(e), traceback=tb)
            return
