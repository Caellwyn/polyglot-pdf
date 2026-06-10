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
from backend.utils.dev_file_logger import get_dev_logger, DEV_LOGGING_ENABLED
from backend.utils.structured_logger import get_logger as get_structured_logger
from backend.utils.token_file_logger import get_token_logger
from backend.config import get_pricing_for_model, model_family

from backend.ports.live_ai_port import ILiveAI, LiveAISession


# ============================================================================
# LOGGING TAG GUIDE (ASCII tags for easy log scanning; was emoji -- bd polyglot-pdf-bw8)
# ============================================================================
# [send] Initial message/prompt sent to Gemini
# [ok] Operation completed successfully  
# [activity] Activity signal sent (turn control)
# [text] Text message sent (hints, prompts)
# [audio-start] Gemini started speaking (first audio chunk)
# [transcript] Gemini finished speaking (transcript received)
# [interrupt] Gemini interrupted by user (barge-in)
# [mic] User started speaking (activity_start from frontend)
# [mic-off] User stopped speaking (activity_end from frontend)
# [warn] Warning (non-fatal issue)
# [error] Error (operation failed)
# ============================================================================


def _build_function_response(tool_name, response_payload, call_id):
    """Build a types.FunctionResponse, echoing the call_id back when present.

    bd polyglot-pdf-0ux: Gemini Live sends a tool call WITH an id (verified on the
    event.tool_call path via probe_tool_call_id.py, e.g.
    id='function-call-211044821233914278'), and the SDK's AI-Studio (mldev) path
    REQUIRES that id to be echoed on the response -- it raises
    _FUNCTION_RESPONSE_REQUIRES_ID otherwise (google.genai live.py), crashing the
    receive loop right after the first fill. (The Vertex path tolerates a missing
    id, which is why this stayed latent in prod.) Earlier code dropped the id based
    on a wrong "the SDK matches by order" assumption.

    We include the id whenever we have one -- which is the normal case (real tool
    calls always carry an id). We omit it only if it is genuinely absent, which
    keeps the Vertex path working and matches the prior behavior there. NOTE: on
    AI Studio a genuinely-id-less response would STILL fail at send time
    (send_tool_response re-checks and raises _FUNCTION_RESPONSE_REQUIRES_ID) -- the
    omit-if-absent branch does not prevent that crash, it only avoids forcing an
    `id=None` field. We accept that because an id-less call is not something we have
    actually observed; if it ever occurs on AI Studio it should surface loudly
    rather than be papered over with a synthetic id the model never sent.
    """
    fr_kwargs = {"name": tool_name, "response": response_payload}
    if call_id:
        fr_kwargs["id"] = call_id
    return types.FunctionResponse(**fr_kwargs)


class LiveAIGeminiSession(LiveAISession):
    """Adapter for the Gemini Live AI session."""

    def __init__(self, session):
        self._session = session

    async def send_audio(self, pcm16_16k: bytes) -> None:
        await self._session.send_realtime_input(
            audio=types.Blob(data=pcm16_16k, mime_type="audio/pcm;rate=16000")
        )

    async def send_tool_response(self, responses: List[Dict[str, Any]]) -> None:
        # Route through _build_function_response so this wrapper shares the hot
        # path's id-handling (bd polyglot-pdf-0ux): echo the call id back when
        # present, omit it when absent. Using .get("id") also avoids a KeyError
        # on a response dict that lacks an id. (bd polyglot-pdf-c4a)
        function_responses = [
            _build_function_response(r["name"], r["response"], r.get("id"))
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

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash-native-audio-preview-12-2025",
             vertexai: bool = False,
             project: str | None = None, 
             location: str = "us-central1"):
        # Prefer constructing a genai.Client() instance. Tests should patch
        # `genai.Client` to return a mock client exposing `.aio.live`.
        self._client = None
        
        # Generate unique instance ID for debugging multi-tab scenarios
        import uuid
        self._instance_id = f"LiveAI-{str(uuid.uuid4())[:8]}"
        # Per-live-session attempt counter (bd polyglot-pdf-2m9, Codex review PR #119).
        # The SAME adapter instance is reused across a Gemini restart (disclaimer ->
        # first-section). Without a per-attempt suffix every restart shares one
        # session_id and scripts/logs.py collapses the separate open/close pairs +
        # frame totals into one row, hiding the very churn the markers expose. The
        # dev-log session_id is "<instance_id>#<attempt>"; ws_session_id still groups
        # all attempts of one form session. Bumped at each session_open.
        self._live_attempt = 0

        # Store these as instance variables for later use
        self._vertexai = vertexai
        self._project = project
        self._location = location
        self._model_name = model
        # Persist the API key so any later client rebuild (the reconstruction
        # branch in connect()) can rebuild a keyed AI Studio client instead of a
        # bare keyless one. The PRIMARY client used by the session loop is the one
        # built just below in __init__ (the loop calls self._client.aio.live.connect
        # directly, never the public connect() method), so storing the key here is
        # what makes the AI Studio (vertexai=False) path work; the connect()
        # rebuild is belt-and-suspenders for external callers of connect().
        self._api_key = api_key

        # Warn loudly on a misconfigured AI Studio path: vertexai=False (AI Studio)
        # authenticates ONLY via an API key -- there is no ADC/service-account path.
        # With no key, construction still falls through to a bare ClientCls() below,
        # which silently tries ADC and then fails cryptically at the first session.
        # We do NOT raise here: bare LiveAIGemini() (api_key=None, vertexai=False) is
        # the default used by mocked unit tests, which never authenticate for real.
        # Real deploys also surface this via /health's gemini_api_key_present flag.
        if not vertexai and api_key is None:
            try:
                structlog.get_logger().warning(
                    "live_ai_no_api_key_on_ai_studio_path",
                    detail=(
                        "vertexai=False (AI Studio) but no API key; client will fall "
                        "back to ADC and likely fail at session start. Set "
                        "GEMINI_API_KEY or VERTEXAI=true."
                    ),
                )
            except Exception:
                pass

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
        # Optional diagnostic observer for the RAW per-turn usage_metadata object
        # (default None = production no-op). Lets a measurement harness inspect fields
        # the cost path does not consume -- e.g. cached_content_token_count / traffic_type
        # -- to tell context-compression activation from a silent no-op (bd l3a.1).
        self._on_raw_usage = None
        self._system_instruction: Optional[str] = None
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
        # Cooperative graceful-shutdown signal (bd polyglot-pdf-0c1 / y4a). A
        # tool callback running ON the receive task (e.g. switch_section) cannot
        # cancel its own task to tear down the session -- that orphans the
        # FunctionResponse it is about to send. Instead it calls
        # begin_graceful_shutdown(), which sets _close_after_flush; the receive
        # loop FLUSHES its pending tool responses and then breaks cleanly. The
        # detached swap task awaits _closed_event (set in _run_session_loop's
        # finally) before starting the new session, so the old loop is fully wound
        # down first. _closed_event is created per-session in set_callbacks.
        self._close_after_flush: bool = False
        self._closed_event: Optional[asyncio.Event] = None

        # Session readiness flag and message queue for race condition handling
        self._session_ready: bool = False  # True when Gemini session is ready to receive messages
        self._pending_client_content: List[str] = []  # Queue for send_client_content() calls before session ready

        # Rate limiting for audio queue warnings
        self._last_audio_queue_warning: float = 0.0  # Timestamp of last warning
        self._audio_queue_warning_interval: float = 5.0  # Log at most once per 5 seconds

        # Lock to avoid concurrent start/stop races
        self._task_lock = asyncio.Lock()

        # Token tracking for cost analysis
        self._session_total_tokens: int = 0
        self._session_prompt_tokens: int = 0
        self._session_candidate_tokens: int = 0

        # Cumulative cost tracking
        self._session_total_cost: float = 0.0

        # Cumulative modality tracking
        self._session_text_input_tokens: int = 0
        self._session_audio_input_tokens: int = 0
        self._session_text_output_tokens: int = 0
        self._session_audio_output_tokens: int = 0
        # Guard so the session-end cost summary is emitted at most once per session
        # (finalize() can be entered more than once / concurrently). Reset at the
        # start of each session loop.
        self._cost_summary_emitted: bool = False

        # Structured logger for this adapter
        self._log = structlog.get_logger().bind(
            adapter="LiveAIGemini",
            model=self._model_name,
            vertexai=self._vertexai,
            instance_id=self._instance_id  # Track which instance is logging
        )

        # Session context for token logging (set by service)
        self._form_session_id: Optional[str] = None
        self._form_id: Optional[str] = None
        self._current_section_id: Optional[str] = None

        # Monotonic per-instance sequence counter for the dev I/O log, so a
        # captured gemini_<date>.jsonl can be re-ordered into the exact
        # send/receive sequence even across interleaved turns (bd polyglot-pdf-kbf).
        self._dev_io_seq: int = 0

    def _dev_log_io(self, direction: str, message_type: str, content: Dict[str, Any]) -> None:
        """Capture one Gemini send/receive event to the dev file logger.

        DEV-ONLY: get_dev_logger() is a no-op unless backend/.env.DEV exists, so
        this NEVER writes to Cloud Run / production logs -- it only appends to the
        local backend/logs/gemini_<date>.jsonl. That gating is what lets us log
        FULL message bodies (tool-call args, tool responses, hints = PII/PHI)
        here, which the production structlog path must never do (bd polyglot-pdf-oeq).

        Stamps each entry with a monotonic seq + the active model so a captured
        log is fully reconstructable and A/B-distinguishable (bd polyglot-pdf-kbf).
        Wrapped in a broad guard: debug logging must never break the session.
        """
        try:
            dev_logger = get_dev_logger()
            # Short-circuit BEFORE any work when disabled (the common/production
            # case): this runs in the hot receive loop ~6x per tool-call turn, so
            # skip the seq increment + dict build when nothing will be written.
            if not getattr(dev_logger, "enabled", False):
                return
            self._dev_io_seq += 1
            # Apply caller content FIRST, then stamp seq/model LAST so the
            # enrichment fields always win -- a caller that happens to pass a
            # "seq" or "model" key in content can't silently clobber the timeline
            # /A-B fields (Copilot review of PR #104).
            enriched = dict(content)
            enriched["seq"] = self._dev_io_seq
            enriched["model"] = self._model_name
            # Suffix the session_id with the live-session attempt so each Gemini
            # restart is a DISTINCT row in scripts/logs.py (Codex review PR #119);
            # ws_session_id still groups all attempts of one form session.
            attempt = getattr(self, "_live_attempt", 0)
            session_id = f"{self._instance_id}#{attempt}" if attempt else self._instance_id
            dev_logger.log_gemini_message(
                direction=direction,
                message_type=message_type,
                content=enriched,
                session_id=session_id,
                ws_session_id=self._form_session_id,
            )
        except Exception:
            # Never let diagnostic logging interfere with the live session.
            pass

    @asynccontextmanager
    async def connect(self, model: str, config: Dict[str, Any]) -> AsyncIterator[LiveAISession]:
        """Connects to the Gemini Live API and yields a session wrapper.

        Uses the underlying genai client's async context manager for live.connect.
        """
        if self._client is None or not hasattr(self._client, "aio"):
            # Reconstruct a client if one was never built (or got torn down).
            # NOTE: the session loop uses self._client.aio.live.connect directly
            # and does NOT route through this method, so this branch is a guard for
            # external callers of connect(), not the hot reconnect path. It mirrors
            # __init__'s three-way construction (Vertex / keyed AI Studio / bare).
            ClientCls = getattr(genai, "Client", None)
            if ClientCls is not None:
                try:
                    if self._vertexai:
                        self._client = ClientCls(
                            vertexai=True,
                            project=self._project or os.getenv("GOOGLE_CLOUD_PROJECT"),
                            location=self._location
                        )
                    elif self._api_key is not None:
                        self._client = ClientCls(api_key=self._api_key)
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

    def set_session_context(
        self,
        form_session_id: str,
        form_id: str,
        current_section_id: Optional[str] = None,
    ):
        """Set session context for token logging.

        Args:
            form_session_id: Overall form filling session ID (persists across Gemini sessions)
            form_id: Form identifier (e.g., "I-90")
            current_section_id: Current section ID (the user-facing navigation unit;
                see docs/standards/terminology.md -- this was historically mis-named
                "part", a section-state naming bug, bd polyglot-pdf-gfb.4)
        """
        self._form_session_id = form_session_id
        self._form_id = form_id
        self._current_section_id = current_section_id

    def set_callbacks(
        self,
        on_form_update=None,
        on_transcript=None,
        on_audio=None,
        on_tool_call=None,
        system_instruction: str | None = None,
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
        self._function_declarations = deepcopy(tool_declarations) if tool_declarations else None
        # Honor explicit enable_transcripts flag from the caller (UI/service).
        # If enable_transcripts is False, we will not request TEXT responses from Gemini
        # even if an on_transcript callback is present.
        self._enable_transcripts = bool(enable_transcripts)

        # CRITICAL FIX: Reset intentional shutdown flag BEFORE checking task status
        # This prevents section-switching crashes where finalize() sets the flag
        # but the new session immediately exits thinking it was intentionally shut down
        self._intentional_shutdown = False
        # Reset the cooperative-shutdown flag too: a stale _close_after_flush left
        # over from a prior session must NEVER make the NEW receive loop break on
        # its first turn (bd polyglot-pdf-0c1). The fresh _closed_event below
        # belongs to the new task -- begin_graceful_shutdown returns THIS instance,
        # so a swap task always awaits the event for the session it is replacing.
        self._close_after_flush = False

        # Start background task if not already running
        if self._bg_task is None or self._bg_task.done():
            # Lazily create audio and text queues
            # Audio queue has max size to prevent blocking - drops frames if backed up
            self._audio_queue = asyncio.Queue(maxsize=100)  # ~2 seconds of audio at 50fps
            self._text_queue = asyncio.Queue()
            closed_event = asyncio.Event()
            self._closed_event = closed_event
            self._bg_task = asyncio.create_task(self._run_session_loop())
            # Set _closed_event when the task COMPLETES by any path -- normal
            # return, exception, OR cancellation (bd polyglot-pdf-0c1). A
            # done-callback is strictly more robust than a try/finally in the
            # coroutine body (it also fires on cancel) and needs no re-indent of
            # the ~1200-line loop. Bind THIS event (not self._closed_event) so a
            # later session's callback can't race-set the wrong event. The
            # done-callback runs on the loop thread after the task finishes.
            self._bg_task.add_done_callback(lambda _t, _ev=closed_event: _ev.set())
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
            self._log.warn("[warn] AUDIO_QUEUE_NOT_STARTED", message="Audio dropped - queue not initialized")
            return
        try:
            # Log first audio chunk to verify queueing
            if not hasattr(self, '_first_adapter_audio_logged'):
                self._log.info("[mic] [Adapter] First audio chunk enqueued", bytes=len(audio_chunk), queue_size=self._audio_queue.qsize())
                self._first_adapter_audio_logged = True
            # Inbound-audio rollup (bd polyglot-pdf-2m9): count user->Gemini frames and
            # emit a dev-log summary on the FIRST frame and every 100 thereafter, so the
            # log shows whether mic audio actually reaches Gemini (and at what rate)
            # without a per-frame flood. The receive loop does the same for Gemini->user.
            self._audio_in_frames = getattr(self, "_audio_in_frames", 0) + 1
            self._audio_in_bytes = getattr(self, "_audio_in_bytes", 0) + len(audio_chunk)
            if self._audio_in_frames == 1 or self._audio_in_frames % 100 == 0:
                self._dev_log_io("send", "audio_summary", {
                    "frames": self._audio_in_frames,
                    "bytes": self._audio_in_bytes,
                })
            # Non-blocking put - drops frame if queue is full instead of blocking
            self._audio_queue.put_nowait(audio_chunk)
        except asyncio.QueueFull:
            # Queue backed up - drop this audio frame to avoid blocking
            # Audio is resilient to dropped frames (slight quality degradation vs blocking control msgs)
            # Rate limit this warning to avoid flooding logs (only log once per interval)
            import time
            current_time = time.time()
            if current_time - self._last_audio_queue_warning >= self._audio_queue_warning_interval:
                self._log.warn("[warn] AUDIO_QUEUE_FULL", message="Dropping audio frames - queue backed up (suppressing similar warnings for 5s)")
                self._last_audio_queue_warning = current_time
            pass

    async def send_text_message(self, text: str):
        """Send a text message to the live session (e.g., next field hints).

        Messages are queued and sent asynchronously without blocking.
        Used for providing context to Gemini after tool responses.
        """
        if self._text_queue is None:
            # If the queue isn't started, drop message (no-op) for safety
            return

        # Log text message for debugging -- never log the text itself: callers
        # build it with field values (e.g. audio_handler "...with value: X"). bd hjo
        self._log.debug("TEXT_MESSAGE_QUEUED",
                      message_length=len(text))

        await self._text_queue.put(text)

    async def _send_text_turn(self, session, text: str) -> None:
        """Send a user-role text turn to Gemini, choosing the method by model family.

        gemini-3.1-flash-live-preview REJECTS send_client_content() text turns
        with close code 1007 ("invalid argument") -- verified against the live AI
        Studio endpoint (bd polyglot-pdf-1g6 / backend/scripts/probe_3p1_1007.py):
        the same text via session.send_realtime_input(text=...) is accepted and
        returns audio. So for the 3.1 family we use send_realtime_input(text=);
        for 2.5 / others we keep send_client_content (the 2.5 path on
        send_realtime_input is unconfirmed, so we do not change it). When the 2.5
        family is re-verified this branch can collapse to a single call.
        """
        # DEV-ONLY: the FULL text turn sent to Gemini (next-field hints, language
        # /context prompts). The structlog path logs only its length (PII: text
        # may embed field content -- bd hjo). Captures which send method was used
        # per model family, to debug tool-call prompting (bd polyglot-pdf-kbf).
        self._dev_log_io("send", "text_turn", {
            "method": "send_realtime_input" if model_family(self._model_name) == "3.1" else "send_client_content",
            "text": text,
        })
        if model_family(self._model_name) == "3.1":
            await session.send_realtime_input(text=text)
        else:
            # Preserve the EXACT pre-fix 2.5 shape (no explicit role -- the SDK
            # defaults the turn author to "user"): the point of the model gate is
            # to leave the 2.5 / prod path untouched. Do not add a role key here.
            await session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True,
            )

    async def send_client_content(self, text: str):
        """Send client content to Gemini to initiate a response.

        Uses session.send_client_content() to prompt Gemini to speak.
        This is different from send_text_message which queues text hints.

        Used for initiating conversation in a specific language or context.

        If session is not ready yet, the message is queued and will be sent
        automatically once the session becomes ready.

        Args:
            text: Message to send to Gemini (e.g., language change instruction)
        """
        # Check if session is ready - if not, queue the message
        if not self._session_ready:
            self._log.info("[config] CLIENT_CONTENT_QUEUED (session not ready yet)",
                          message_length=len(text),  # never log message text (may carry field content) -- bd hjo
                          queue_size=len(self._pending_client_content) + 1)
            self._pending_client_content.append(text)
            return

        if self._current_session is None:
            self._log.warning("[warn] SEND_CLIENT_CONTENT_NO_SESSION")
            return

        try:
            self._log.info("SEND_CLIENT_CONTENT", message_length=len(text))  # never log message text -- bd hjo

            # DEBUG: Append client content to debug file for token analysis.
            # This writes the RAW message text (which can embed field values), so
            # it is gated behind the same local-dev marker as the PHI logger --
            # production containers have no .env.DEV, so this never runs in prod. bd hjo
            if DEV_LOGGING_ENABLED:
                try:
                    debug_file = Path("backend/logs/gemini_system_instruction.txt")
                    with open(debug_file, "a", encoding="utf-8") as f:
                        f.write("\n\n" + "=" * 80 + "\n")
                        f.write("CLIENT CONTENT MESSAGE SENT TO GEMINI\n")
                        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                        f.write(f"Length: {len(text)} chars\n")
                        f.write(f"Estimated tokens: ~{len(text) // 4}\n")
                        f.write("=" * 80 + "\n\n")
                        f.write(text)
                        f.write("\n\n" + "=" * 80 + "\n")
                except Exception as e:
                    self._log.warn("failed_to_append_debug_file", error=str(e))

            await self._send_text_turn(self._current_session, text)
        except Exception as exc:
            self._log.error("send_client_content_failed", error=str(exc), message_length=len(text))  # never log message text -- bd hjo

    async def send_activity_start(self):
        """Send activity_start signal to Gemini (user started speaking).

        Signals the beginning of user speech. Should be called when frontend
        VAD detects speech start, before sending audio chunks.

        Reference: Gemini Live API docs lines 419-435
        """
        # Native-VAD guard (bd polyglot-pdf-333): when Gemini's own VAD is enabled
        # (DISABLE_GEMINI_VAD=False), manual activity signals must NOT be sent --
        # interleaving them with automatic detection is the conflicting turn-taking
        # state _build_vad_settings warns about. Drop them server-side regardless of
        # what the frontend sends.
        from backend.config import get_settings
        if not get_settings().DISABLE_GEMINI_VAD:
            return

        if self._current_session is None:
            # Session not active - silently ignore (session loss already logged elsewhere)
            self._log.warning("[warn] ACTIVITY_START called but session is None")
            return

        try:
            await self._current_session.send_realtime_input(activity_start=types.ActivityStart())
            # Success - no logging (noisy, system works)
        except Exception as e:
            self._log.error("[error] ACTIVITY_START_FAILED", error=str(e))

    async def send_activity_end(self):
        """Send activity_end signal to Gemini (user stopped speaking).

        Signals the end of user speech and flushes Gemini's cached audio buffer.
        Should be called when frontend VAD detects speech end.

        Reference: Gemini Live API docs lines 419-435
        """
        from backend.config import get_settings
        native_vad = not get_settings().DISABLE_GEMINI_VAD

        if self._current_session is None:
            # Session not active - silently ignore (session loss already logged elsewhere)
            self._log.warning("[warn] ACTIVITY_END called but session is None")
            return

        # Native-VAD turn boundary for PTT (bd polyglot-pdf-6vo, Codex review PR #119).
        # In native mode the manual activity_start/end are suppressed (interleaving
        # them with automatic VAD is the conflicting state bd-333 warns about). But
        # PTT-as-a-gate then withholds all audio after release, so Gemini would get
        # NEITHER an activity_end NOR trailing silence and its VAD may never close the
        # turn -> session goes silent after PTT release. audio_stream_end is the
        # documented realtime signal to finalize the audio segment and is compatible
        # with automatic VAD (it is not the conflicting activity_end), so we send THAT
        # in native mode and the real activity_end only in manual mode.
        try:
            if native_vad:
                await self._current_session.send_realtime_input(audio_stream_end=True)
            else:
                await self._current_session.send_realtime_input(activity_end=types.ActivityEnd())
            # Success - no logging (noisy, system works)
        except Exception as e:
            self._log.error("[error] ACTIVITY_END_FAILED", error=str(e), native_vad=native_vad)

    def begin_graceful_shutdown(self) -> asyncio.Event:
        """Ask the receive loop to exit cleanly AFTER flushing pending tool responses.

        SYNCHRONOUS and lock-free on purpose: this is called from a tool callback
        running ON the receive task (switch_section), where awaiting finalize()
        would cancel that very task and orphan the FunctionResponse it is about to
        send (bd polyglot-pdf-0c1 / y4a). Instead we set flags the receive loop
        polls: it flushes its pending tool responses, then breaks. The returned
        Event is set by _run_session_loop's finally on EVERY exit path, so the
        caller (a detached swap task) can await it before starting the new session
        -- guaranteeing the old loop is fully wound down first (no two live loops
        sharing callbacks, plan hazard 5).

        Suppresses auto-retry (_intentional_shutdown) and stops new client content
        from being sent on the dying session (_session_ready=False). Returns the
        per-session _closed_event (created in set_callbacks); if no session is
        running, returns an already-set event so a caller never hangs.
        """
        self._close_after_flush = True
        self._intentional_shutdown = True
        self._session_ready = False
        if self._closed_event is None:
            # No live session/task -> nothing to wind down; hand back a set event.
            ev = asyncio.Event()
            ev.set()
            return ev
        return self._closed_event

    async def finalize(self):
        """Stop the background task and clear resources.

        Safe to call from OUTSIDE the receive task (WS disconnect, manual switch,
        Level-3 timeout). It must NEVER be awaited from a callback running ON
        _bg_task -- that is the y4a self-cancel that orphans the switch_section
        response (bd polyglot-pdf-0c1). The guard below converts such a misuse into
        a cooperative shutdown instead of a self-cancel, so the bug can never be
        reintroduced by a future caller.
        """
        # Self-call guard: if we are running ON the background task, cancelling it
        # would cancel ourselves mid-callback and orphan any pending tool response.
        # Downgrade to a cooperative shutdown and return.
        bg = self._bg_task
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        if bg is not None and current is bg:
            self._log.error(
                "finalize_called_from_bg_task",
                message="finalize() invoked from the receive task -- downgrading to "
                        "begin_graceful_shutdown() to avoid the y4a self-cancel",
            )
            self.begin_graceful_shutdown()
            return

        async with self._task_lock:
            # Set the shutdown flags INSIDE the lock (bd polyglot-pdf-0c1 shutdown
            # race): a concurrent start/stop must see a consistent
            # (_intentional_shutdown / _session_ready / _pending_client_content)
            # snapshot, not a half-applied one.
            self._intentional_shutdown = True
            self._session_ready = False
            self._pending_client_content.clear()

            if self._bg_task is not None:
                self._bg_task.cancel()
                try:
                    await self._bg_task
                except asyncio.CancelledError:
                    pass
                self._bg_task = None

            # Emit a session-end cost summary now that the background session loop
            # has been cancelled/awaited -- the _session_total_* counters are final
            # (emitting earlier would race _run_session_loop still updating them).
            # The session TOTAL was previously lost on finalize (it only lived in
            # self._session_total_*); per-turn token/cost is logged during the
            # session. Counts/costs/ids ONLY -- never field values/transcripts
            # (bd hjo / no-PII). Emit AT MOST ONCE per session (finalize() can be
            # entered more than once / concurrently) and only if a session actually
            # billed tokens. The logger is already bound with instance_id + model,
            # so don't re-emit them; there is no Gemini *server* session id to log.
            # Guarded so a logging failure can never block teardown. (bd polyglot-pdf-tak)
            if not self._cost_summary_emitted and self._session_total_tokens > 0:
                self._cost_summary_emitted = True
                try:
                    self._log.info(
                        "session_cost_summary",
                        form_session_id=self._form_session_id,
                        form_id=self._form_id,
                        total_tokens=self._session_total_tokens,
                        prompt_tokens=self._session_prompt_tokens,
                        total_cost_usd=round(self._session_total_cost, 8),
                        text_input_tokens=self._session_text_input_tokens,
                        audio_input_tokens=self._session_audio_input_tokens,
                        text_output_tokens=self._session_text_output_tokens,
                        audio_output_tokens=self._session_audio_output_tokens,
                    )
                except Exception as e:  # noqa: BLE001 -- summary must never block teardown
                    self._log.warning("session_cost_summary_failed", error=str(e))
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

    @staticmethod
    def _build_vad_settings(settings) -> Dict[str, Any]:
        """Build the ``automatic_activity_detection`` config from settings.

        The Live API REJECTS (close code 1007) a config that sets
        ``disabled=True`` AND any of the sensitivity/padding fields together.
        So this is a hard either/or:

        - VAD disabled (``DISABLE_GEMINI_VAD=True``, the default): return ONLY
          ``{'disabled': True}``. We drive turn-taking with manual
          ``activity_start`` / ``activity_end`` signals instead -- see
          ``docs/standards/voice-and-vad.md``.
        - VAD enabled: omit ``disabled`` and pass through whichever
          sensitivity/padding knobs (``VAD_*``) are configured.

        Returns ``{}`` when VAD is enabled but no knobs are set (Gemini then
        uses its own defaults). bd polyglot-pdf-p1t

        A *typo'd* sensitivity value (e.g. ``VAD_*_SENSITIVITY=MEDIUM``) is
        whitelisted/skipped with a warning rather than allowed to raise: an
        unrecognized enum lookup used to ``KeyError`` out of here and the broad
        ``except`` in the caller dropped the ENTIRE ``realtime_input_config``,
        silently reverting to Gemini's default VAD while the adapter still sent
        manual ``activity_start/end`` -- a conflicting turn-taking state.
        bd polyglot-pdf-u01
        """
        if settings.DISABLE_GEMINI_VAD:
            return {'disabled': True}

        # Valid sensitivities are LOW / HIGH (UNSPECIFIED means "leave unset");
        # anything else is a config typo and is skipped, not fatal.
        _VALID_SENSITIVITY = {'LOW', 'HIGH', 'UNSPECIFIED'}

        def _resolve_sensitivity(raw, enum_type, prefix, field):
            if not raw or raw == 'UNSPECIFIED':
                return None
            if raw not in _VALID_SENSITIVITY:
                structlog.get_logger().warning(
                    "invalid_vad_sensitivity_skipped",
                    field=field,
                    value=raw,
                    valid=sorted(_VALID_SENSITIVITY),
                )
                return None
            return enum_type[f"{prefix}_{raw}"]

        vad_settings: Dict[str, Any] = {}
        start = _resolve_sensitivity(
            settings.VAD_START_SENSITIVITY, types.StartSensitivity,
            'START_SENSITIVITY', 'VAD_START_SENSITIVITY',
        )
        if start is not None:
            vad_settings['start_of_speech_sensitivity'] = start
        end = _resolve_sensitivity(
            settings.VAD_END_SENSITIVITY, types.EndSensitivity,
            'END_SENSITIVITY', 'VAD_END_SENSITIVITY',
        )
        if end is not None:
            vad_settings['end_of_speech_sensitivity'] = end
        if settings.VAD_PREFIX_PADDING_MS is not None:
            vad_settings['prefix_padding_ms'] = settings.VAD_PREFIX_PADDING_MS
        if settings.VAD_SILENCE_DURATION_MS is not None:
            vad_settings['silence_duration_ms'] = settings.VAD_SILENCE_DURATION_MS
        return vad_settings

    async def _run_session_loop(self):
        """Background loop that connects to Gemini Live and handles audio and events.

        This is a minimal implementation: connect, send audio from queue, and
        dispatch simple transcript/tool events to callbacks. It's intentionally
        conservative so tests and local dev don't require full protocol coverage.
        """

        # Import settings at the start to avoid UnboundLocalError
        from backend.config import get_settings
        settings = get_settings()

        # Reset token counters for this session
        self._session_total_tokens = 0
        self._session_prompt_tokens = 0
        self._session_candidate_tokens = 0
        self._session_total_cost = 0.0
        self._session_text_input_tokens = 0
        self._session_audio_input_tokens = 0
        self._session_text_output_tokens = 0
        self._session_audio_output_tokens = 0
        self._cost_summary_emitted = False

        # Build a minimal config; request AUDIO responses and use native
        # transcription output.
        response_modalities = ["AUDIO"]

        if self._function_declarations:
            tools_config = [{"function_declarations": deepcopy(self._function_declarations)}]
            # Log tool declarations being sent to Gemini
            tool_names = [decl.get("name") for decl in self._function_declarations]
            self._log.info("[tools] Sending tool declarations to Gemini",
                          tool_count=len(tool_names),
                          tool_names=tool_names)
        else:
            tools_config = [{
                "function_declarations": [
                    {"name": "update_form_fields"},
                    {"name": "get_form_status"},
                ]
            }]
            self._log.warning("[warn] No function_declarations provided - using fallback tools only")

        config = {
            "response_modalities": response_modalities,
            "tools": tools_config,
        }

        # HALLUCINATION_REDUCTION (Oct 30, 2025): Enable proactive audio
        # This helps Gemini ignore dirty/choppy audio and background conversation
        if settings.PROACTIVE_AUDIO:
            config["proactivity"] = {
                "proactive_audio": True
            }
        
        # Enable automatic voice activity detection for realtime audio input
        # This allows Gemini to detect when user starts/stops speaking
        try:
            config["realtime_input_config"] = {
                "automatic_activity_detection": self._build_vad_settings(settings)
            }
        except Exception as e:
            self._log.warn("failed_to_set_realtime_input_config", error=str(e))
        
        # Enable input transcription to see what Gemini is hearing
        if self._enable_transcripts:
            config['input_audio_transcription'] = {}
            config['output_audio_transcription'] = {}

        # Context-window compression (epic polyglot-pdf-l3a, bead -45o). A server-side
        # sliding window bounds the live context so per-turn re-billing stops compounding
        # (quadratic -> linear cumulative cost) and audio sessions can run past the 15-min
        # cap. Gated behind CONTEXT_COMPRESSION_ENABLED (default off) so it's one env var
        # from reverting. Syntax verified against the installed google-genai; the SDK
        # accepts these snake_case keys and aliases them to triggerTokens / slidingWindow /
        # targetTokens. See docs/components/context-compression.md.
        if settings.CONTEXT_COMPRESSION_ENABLED:
            config["context_window_compression"] = {
                "trigger_tokens": settings.CONTEXT_COMPRESSION_TRIGGER_TOKENS,
                "sliding_window": {
                    "target_tokens": settings.CONTEXT_COMPRESSION_WINDOW_TOKENS,
                },
            }
            self._log.info(
                "context_window_compression_enabled",
                trigger_tokens=settings.CONTEXT_COMPRESSION_TRIGGER_TOKENS,
                window_tokens=settings.CONTEXT_COMPRESSION_WINDOW_TOKENS,
            )

        if self._system_instruction:
            config["system_instruction"] = self._system_instruction
            # Log initial system instruction for debugging -- never log its text:
            # it's built from section field values and can embed PII/PHI. bd hjo
            self._log.debug("INITIAL_SYSTEM_INSTRUCTION",
                          system_instruction_length=len(self._system_instruction))

            # DEBUG: Write system instruction to file for token analysis.
            # The system instruction is built from section field values, so this
            # raw write is gated behind the local-dev marker (no .env.DEV in prod). bd hjo
            if DEV_LOGGING_ENABLED:
                try:
                    debug_file = Path("backend/logs/gemini_system_instruction.txt")
                    debug_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write("=" * 80 + "\n")
                        f.write("SYSTEM INSTRUCTION SENT TO GEMINI\n")
                        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                        f.write(f"Length: {len(self._system_instruction)} chars\n")
                        f.write(f"Estimated tokens: ~{len(self._system_instruction) // 4}\n")
                        f.write("=" * 80 + "\n\n")
                        f.write(self._system_instruction)
                        f.write("\n\n" + "=" * 80 + "\n")
                        f.write("END OF SYSTEM INSTRUCTION\n")
                        f.write("=" * 80 + "\n")
                except Exception as e:
                    self._log.warn("failed_to_write_debug_file", error=str(e))

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

            # Log session configuration before connecting
            self._log.info("[config] Gemini session config",
                          model=self._model_name,
                          has_system_instruction=bool(self._system_instruction),
                          system_instruction_length=len(self._system_instruction) if self._system_instruction else 0,
                          tool_count=len(self._function_declarations) if self._function_declarations else 0)

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
                    chunk_count = 0
                    while True:
                        # Use a sentinel (None) to allow graceful shutdown without
                        # relying solely on task cancellation. This wakes the
                        # sender if it's blocked on get().
                        chunk = await self._audio_queue.get()
                        if chunk is None:
                            # Sentinel received: exit the send loop cleanly
                            self._log.info("[stop] [Sender] Audio sender stopping", total_chunks_sent=chunk_count)
                            break
                        try:
                            chunk_count += 1
                            # Log first chunk only (verify sender is working)
                            if chunk_count == 1:
                                self._log.info("[mic] [Sender] First audio chunk sending to Gemini", bytes=len(chunk))

                            await session.send_realtime_input(
                                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                            )

                            # ACTUAL send-to-Gemini rollup (bd polyglot-pdf-2m9): this fires
                            # AFTER send_realtime_input returns, so it proves audio crossed
                            # the backend->Gemini boundary -- distinct from stream_audio's
                            # "audio_summary" which only proves it reached the queue. If
                            # "gemini_send" frames lag the queued frames, audio is stuck in
                            # the queue / the sender is starved; if they match but Gemini
                            # stays silent, the problem is on Gemini's side.
                            self._gemini_sent_bytes = getattr(self, "_gemini_sent_bytes", 0) + len(chunk)
                            if chunk_count == 1 or chunk_count % 100 == 0:
                                self._dev_log_io("send", "gemini_send", {
                                    "frames": chunk_count,
                                    "bytes": self._gemini_sent_bytes,
                                })
                        except Exception as e:
                            self._log.error("[error] AUDIO_SEND_FAILED", error=str(e), chunk_number=chunk_count)
                            self._dev_log_io("send", "gemini_send_failed", {
                                "chunk_number": chunk_count, "error": str(e),
                            })
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
                            # NOTE: Removing these causes "unknown_control" errors in frontend!
                            # Keeping them enables Gemini to properly process text messages.
                            # await session.send_realtime_input(activity_start=types.ActivityStart())
                            
                            await self._send_text_turn(session, text)

                            # await session.send_realtime_input(activity_end=types.ActivityEnd())
                            
                            # Log successful text send for debugging
                            self._log.debug("[text] TEXT_MESSAGE_SENT",
                                          text_length=len(text))  # never log message text (user-turn content) -- bd hjo
                        except Exception as e:
                            self._log.error("[error] TEXT_SEND_FAILED", error=str(e))
                            # swallow for robustness
                            pass

                text_sender_task = asyncio.create_task(text_sender())
                self._current_text_sender_task = text_sender_task
                # Store session reference for potential direct sends
                self._current_session = session

                # Reset per-session audio rollup counters (bd polyglot-pdf-2m9,
                # Codex review PR #119): this same adapter instance is reused across a
                # Gemini restart (e.g. disclaimer -> first-section), so without this
                # the audio_summary / gemini_send / session_close totals would carry
                # frames+bytes from the PRIOR session and misattribute audio flow to
                # the wrong restart in scripts/logs.py.
                self._audio_in_frames = 0
                self._audio_in_bytes = 0
                self._gemini_sent_bytes = 0
                self._audio_chunk_count = 0
                self._audio_out_bytes = 0
                self._first_audio_time = None

                # New live-session attempt -> distinct session_id in the dev log so
                # logs.py does not collapse restarts (Codex review PR #119). Bump
                # BEFORE the session_open marker so that marker carries the new id.
                self._live_attempt = getattr(self, "_live_attempt", 0) + 1

                # Session lifecycle marker (bd polyglot-pdf-2m9): makes the session
                # boundary explicit in the dev log, so churn (e.g. the disclaimer ->
                # first-section restart, or an unexpected reconnect) is visible at a
                # glance instead of inferred from repeated text_turns.
                self._dev_log_io("local", "session_open", {"attempt": self._live_attempt})

                # Mark session as ready and send any queued client content messages
                self._session_ready = True

                # Clear console output for focused logging
                print(f"\n{'='*80}")
                print(f"[ok] GEMINI SESSION READY")
                print(f"Instance: {self._instance_id}")
                print(f"Model: {self._model_name}")
                print(f"Waiting for user to speak...")
                print(f"{'='*80}\n")
                if self._pending_client_content:
                    self._log.info("[send] SENDING_QUEUED_CLIENT_CONTENT",
                                  queued_count=len(self._pending_client_content))
                    for queued_msg in self._pending_client_content:
                        try:
                            self._log.info("SEND_CLIENT_CONTENT (from queue)", message_length=len(queued_msg))  # never log message text -- bd hjo
                            await self._send_text_turn(session, queued_msg)
                        except Exception as exc:
                            self._log.error("queued_client_content_send_failed",
                                          error=str(exc),
                                          message_length=len(queued_msg))  # never log message text -- bd hjo
                    # Clear the queue after sending
                    self._pending_client_content.clear()
                    self._log.info("[ok] QUEUED_CLIENT_CONTENT_SENT")

                try:
                    event_count = 0
                    while True:
                        received_any = False
                        try:
                            async for event in session.receive():
                                event_count += 1
                                received_any = True

                                # Catch-all event-shape probe (bd polyglot-pdf-2m9):
                                # the audio_summary only fires on audio bytes, so a
                                # response that comes back as text / transcript /
                                # turn_complete with NO audio is currently invisible --
                                # exactly the "Gemini went silent" blind spot. Log a
                                # compact shape of EVERY received event (which fields are
                                # present + flags), with NO content (PHI-safe: lengths /
                                # booleans only). This tells us whether Gemini sends
                                # anything at all after the user's audio, and whether it
                                # shows it HEARD the user (input_transcription present).
                                # DEV_LOGGING_ENABLED gate FIRST (fresh-eyes PR #119): this
                                # probe runs on every received event in the hot loop, so skip
                                # the ~10 getattr calls + dict build entirely in prod (where
                                # the marker is absent) -- _dev_log_io's own short-circuit
                                # would otherwise only save the write, not this caller-side work.
                                if DEV_LOGGING_ENABLED:
                                    try:
                                        _sc = getattr(event, "server_content", None)
                                        _it = getattr(_sc, "input_transcription", None) if _sc else None
                                        _ot = getattr(_sc, "output_transcription", None) if _sc else None
                                        _mt = getattr(_sc, "model_turn", None) if _sc else None
                                        self._dev_log_io("receive", "event_shape", {
                                            "n": event_count,
                                            "has_audio": getattr(event, "data", None) is not None,
                                            "has_server_content": _sc is not None,
                                            "interrupted": bool(getattr(_sc, "interrupted", False)) if _sc else False,
                                            "turn_complete": bool(getattr(_sc, "turn_complete", False)) if _sc else False,
                                            "generation_complete": bool(getattr(_sc, "generation_complete", False)) if _sc else False,
                                            "input_transcription_len": len(getattr(_it, "text", "") or "") if _it else 0,
                                            "output_transcription_len": len(getattr(_ot, "text", "") or "") if _ot else 0,
                                            "model_turn_parts": len(getattr(_mt, "parts", []) or []) if _mt else 0,
                                            "tool_call": getattr(event, "tool_call", None) is not None,
                                        })
                                    except Exception:
                                        pass

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
                                                self._audio_out_bytes = 0

                                            self._audio_chunk_count += 1
                                            self._audio_out_bytes = getattr(self, "_audio_out_bytes", 0) + len(audio_bytes)

                                            # Track first audio chunk timing (for transcript correlation)
                                            if self._audio_chunk_count == 1:
                                                import time
                                                self._first_audio_time = time.time()
                                                self._log.info("[audio] [Gemini Audio] First audio chunk received",
                                                             bytes=len(audio_bytes),
                                                             chunk_number=1)
                                                # Mark that Gemini has responded (cancel fallback resend)
                                                gemini_has_responded = True

                                            # Outbound-audio rollup (bd polyglot-pdf-2m9): dev-log a summary on
                                            # the first chunk + every 100, so the log shows whether Gemini
                                            # actually responded with audio (and how much) without per-frame noise.
                                            if self._audio_chunk_count == 1 or self._audio_chunk_count % 100 == 0:
                                                self._dev_log_io("receive", "audio_summary", {
                                                    "frames": self._audio_chunk_count,
                                                    "bytes": self._audio_out_bytes,
                                                })

                                            await self._on_audio(audio_bytes)
                                            continue

                                    server_content = getattr(event, "server_content", None)
                                    if server_content is not None:
                                        # ========================================
                                        # CHECK FOR INTERRUPTION (Barge-in)
                                        # ========================================
                                        interrupted = getattr(server_content, "interrupted", False)
                                        if interrupted:
                                            # Get canceled tool call IDs (and names: a barge-in that
                                            # cancels an in-flight update_form_fields would explain a
                                            # "tool call never landed" symptom -- bd polyglot-pdf-kbf).
                                            model_turn = getattr(server_content, "model_turn", None)
                                            canceled_ids = []
                                            canceled_tool_names = []
                                            canceled_call_count = 0
                                            if model_turn:
                                                parts = getattr(model_turn, "parts", [])
                                                for part in parts:
                                                    function_call = getattr(part, "function_call", None)
                                                    if function_call:
                                                        # Count EVERY canceled function call, so the count is
                                                        # consistent with canceled_tool_names even when the SDK
                                                        # omits an id or a name on some calls (bd polyglot-pdf-kbf).
                                                        canceled_call_count += 1
                                                        call_id = getattr(function_call, "id", None)
                                                        if call_id:
                                                            canceled_ids.append(call_id)
                                                        fc_name = getattr(function_call, "name", None)
                                                        if fc_name:
                                                            canceled_tool_names.append(fc_name)

                                            import time
                                            now = time.time()
                                            elapsed_since_audio_start = None
                                            if hasattr(self, '_first_audio_time') and self._first_audio_time:
                                                elapsed_since_audio_start = int((now - self._first_audio_time) * 1000)

                                            self._log.info(
                                                "[interrupt] GEMINI_INTERRUPTED",
                                                canceled_tool_calls=canceled_call_count,
                                                call_ids=[cid[:8] for cid in canceled_ids],
                                                # tool NAMES are safe to log (not values) and tell us if a
                                                # form-fill call was the casualty of the barge-in.
                                                canceled_tool_names=canceled_tool_names,
                                                audio_chunks_before_interrupt=getattr(self, '_audio_chunk_count', 0),
                                                elapsed_since_audio_start_ms=elapsed_since_audio_start,
                                                timestamp_ms=int(now * 1000)
                                            )
                                            # DEV-ONLY: full interrupt detail in-sequence with the rest of
                                            # the I/O log, so a barge-in that killed a tool call is visible
                                            # in the captured timeline (bd polyglot-pdf-kbf).
                                            self._dev_log_io("receive", "interrupted", {
                                                "canceled_tool_calls": canceled_call_count,
                                                "canceled_tool_names": canceled_tool_names,
                                                "audio_chunks_before_interrupt": getattr(self, '_audio_chunk_count', 0),
                                                "elapsed_since_audio_start_ms": elapsed_since_audio_start,
                                            })
                                            
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
                                            
                                            self._log.info("[transcript] GEMINI_TRANSCRIPT_RECEIVED",
                                                         text_length=len(transcription.text),
                                                         # never log transcript text -- it's user speech / field content (PHI). bd hjo
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
                                                    # Log what we're receiving from Gemini
                                                    part_types = [type(p).__name__ for p in parts]
                                                    has_function_calls = any(hasattr(p, 'function_call') and getattr(p, 'function_call', None) for p in parts)
                                                    self._log.info("[model-turn] Gemini model_turn received",
                                                                  part_count=len(parts),
                                                                  part_types=part_types,
                                                                  has_function_calls=has_function_calls)

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

                                                            # PROMINENT logging for debugging
                                                            self._log.info("[tools] GEMINI SENT TOOL CALL",
                                                                          tool_name=tool_name,
                                                                          call_id=call_id[:8] if call_id else None,
                                                                          has_payload=bool(payload),
                                                                          payload_type=type(payload).__name__)

                                                            if isinstance(payload, str):
                                                                try:
                                                                    import json as _json
                                                                    parsed_arguments = _json.loads(payload)
                                                                except Exception:
                                                                    parsed_arguments = {}
                                                            else:
                                                                parsed_arguments = payload or {}

                                                            # DEV-ONLY full-body capture: the exact tool call Gemini emitted
                                                            # (raw payload + parsed args), to debug update_form_fields
                                                            # reliability (bd polyglot-pdf-kbf). No-op in production.
                                                            self._dev_log_io("receive", "tool_call", {
                                                                "path": "model_turn.parts",
                                                                "tool_name": tool_name,
                                                                "call_id": call_id,
                                                                "payload_type": type(payload).__name__,
                                                                "payload_raw": repr(payload)[:2000] if payload is not None else None,
                                                                "parsed_arguments": parsed_arguments,
                                                            })
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
                                                                    dev_logger = get_dev_logger()
                                                                    dev_logger.log_invalid_tool_call(
                                                                        tool_name=tool_name or "unknown",
                                                                        arguments={
                                                                            "call_id": call_id,
                                                                            "payload_type": type(payload).__name__,
                                                                            "payload_repr": repr(payload)[:500] if payload else None,
                                                                            "part_type": type(part).__name__,
                                                                        },
                                                                        error="Empty tool arguments after parsing attempts",
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

                                                                    # DEV-ONLY: the FULL response the callback produced for this
                                                                    # tool -- i.e. the body Gemini will receive (validation errors,
                                                                    # next_field_hint, "field confirmed", etc). This is what she
                                                                    # reacts to when she says "trouble saving" (bd polyglot-pdf-kbf).
                                                                    # direction="local": this is the backend's OWN output, not data
                                                                    # received from Gemini -- the on-wire send is the "tool_response"
                                                                    # entry below. Keeps a log reader from misreading it as inbound.
                                                                    self._dev_log_io("local", "tool_callback_result", {
                                                                        "path": "model_turn.parts",
                                                                        "tool_name": tool_name,
                                                                        "call_id": call_id,
                                                                        "response": response_payload,
                                                                    })
                                                                except Exception as e:
                                                                    # Print full traceback to console for debugging
                                                                    import traceback
                                                                    print(f"\n{'='*80}")
                                                                    print(f"TOOL CALLBACK ERROR: {tool_name}")
                                                                    print(f"{'='*80}")
                                                                    traceback.print_exc()
                                                                    print(f"{'='*80}\n")

                                                                    self._log.exception("tool_callback_error", tool=tool_name, error=str(e))

                                                                    # Dev logging: Log tool errors
                                                                    dev_logger = get_dev_logger()
                                                                    dev_logger.log_error(
                                                                        error_type="tool_callback_error",
                                                                        error_message=str(e),
                                                                        context={"tool_name": tool_name, "arguments": parsed_arguments}
                                                                    )
                                                            elif tool_name == "update_form_fields" and self._on_form_update:
                                                                await self._on_form_update(parsed_arguments)

                                                            if response_payload is None:
                                                                response_payload = {}

                                                            # ALWAYS emit a FunctionResponse for a named tool call
                                                            # (bd polyglot-pdf-tks). Gemini Live BLOCKS until every
                                                            # function call it issued gets a response; a call with no
                                                            # response leaves her waiting forever -- which breaks the
                                                            # very first tool-call/response loop. Two ways this used to
                                                            # silently drop the response on THIS (model_turn.parts) path:
                                                            #   1. the gate required call_id, so a function_call with no
                                                            #      'id' produced no response at all; and
                                                            #   2. a callback exception (caught above) left response_payload
                                                            #      None -> coerced to {} here, but the call_id gate could
                                                            #      still skip the append.
                                                            # Echo the call_id back when present (bd polyglot-pdf-0ux):
                                                            # the SDK's AI-Studio path REQUIRES it, and the old claim that
                                                            # the SDK "matches by order" was wrong (see _build_function_response).
                                                            if tool_name:
                                                                responses.append(
                                                                    _build_function_response(tool_name, response_payload, call_id)
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

                                            # DEV-ONLY full-body capture for the alternate (event.tool_call) path
                                            # (bd polyglot-pdf-kbf). No-op in production.
                                            self._dev_log_io("receive", "tool_call", {
                                                "path": "event.tool_call",
                                                "tool_name": tool_name,
                                                "call_id": call_id,
                                                "payload_type": type(payload).__name__,
                                                "payload_raw": repr(payload)[:2000] if payload is not None else None,
                                                "parsed_arguments": parsed_arguments,
                                            })

                                            response_payload = None

                                            if self._on_tool_call is not None and tool_name:
                                                try:
                                                    response_payload = await self._on_tool_call(tool_name, parsed_arguments)
                                                    self._log.info("tool_callback_returned", tool_name=tool_name, has_response=response_payload is not None, response_keys=list(response_payload.keys()) if isinstance(response_payload, dict) else None)
                                                    # direction="local": backend's own callback output, not inbound.
                                                    self._dev_log_io("local", "tool_callback_result", {
                                                        "path": "event.tool_call",
                                                        "tool_name": tool_name,
                                                        "call_id": call_id,
                                                        "response": response_payload,
                                                    })
                                                except Exception as e:
                                                    # Print full traceback to console for debugging (PATH 2)
                                                    import traceback
                                                    print(f"\n{'='*80}")
                                                    print(f"TOOL CALLBACK ERROR (PATH 2): {tool_name}")
                                                    print(f"{'='*80}")
                                                    traceback.print_exc()
                                                    print(f"{'='*80}\n")
                                                    self._log.exception("tool_callback_error", tool=tool_name)
                                            elif tool_name == "update_form_fields" and self._on_form_update:
                                                await self._on_form_update(parsed_arguments)

                                            if response_payload is None:
                                                self._log.warning("tool_response_was_none", tool_name=tool_name, setting_to_empty_dict=True)
                                                response_payload = {}

                                            if tool_name:
                                                # Echo the call_id back on the FunctionResponse (bd
                                                # polyglot-pdf-0ux). The SDK's AI-Studio (mldev) path
                                                # REQUIRES the id and raises _FUNCTION_RESPONSE_REQUIRES_ID
                                                # without it (live.py send_tool_response), which crashes the
                                                # receive loop after the first fill. The model DOES send an
                                                # id on this event.tool_call path (verified:
                                                # probe_tool_call_id.py shows fc.id='function-call-...'); the
                                                # old "should NOT include id" comment was wrong for this SDK.
                                                # _build_function_response includes the id when present (it is,
                                                # here) -- see its docstring for the omit-if-absent behavior.
                                                responses.append(
                                                    _build_function_response(tool_name, response_payload, call_id)
                                                )

                                    if responses:
                                        # Log tool responses being sent to Gemini, for token analysis ONLY.
                                        # NEVER print resp.response -- a tool response (e.g. get_field_value /
                                        # get_form_status) can carry field VALUES = PII/PHI, and stdout ->
                                        # Cloud Run logs (bd polyglot-pdf-oeq). Log the tool name + response
                                        # SIZE (char/estimated-token count), never the body.
                                        for resp in responses:
                                            response_str = str(resp.response)
                                            estimated_tokens = len(response_str) // 4  # rough: 1 token ~ 4 chars
                                            self._log.info(
                                                "tool_response_sent",
                                                tool=resp.name,
                                                response_chars=len(response_str),
                                                estimated_tokens=estimated_tokens,
                                            )
                                            # DEV-ONLY: the FULL tool-response body actually sent on the
                                            # wire to Gemini (the redacted log above only records its
                                            # size). Ground truth for what Gemini receives back from each
                                            # tool (bd polyglot-pdf-kbf). No-op in production.
                                            self._dev_log_io("send", "tool_response", {
                                                "tool_name": resp.name,
                                                "response": getattr(resp, "response", None),
                                            })

                                        await session.send_tool_response(function_responses=responses)
                                        # Don't send additional prompts - just let Gemini process the tool responses
                                        # and generate its natural continuation

                                        # COOPERATIVE FLUSH POINT (bd polyglot-pdf-0c1 /
                                        # y4a): a switch_section callback (handled inline
                                        # above) called begin_graceful_shutdown(), so the
                                        # FunctionResponse it produced is now ON THE WIRE
                                        # for the OLD session. Break out of the receive loop
                                        # cleanly -- the swap to the new section happens on a
                                        # detached task that awaits _closed_event. This is the
                                        # single flush point for BOTH tool-call paths
                                        # (model_turn.parts + event.tool_call feed the same
                                        # `responses` list sent just above). The inner break
                                        # exits the `async for`; the `if not received_any or
                                        # _close_after_flush` check below exits the while-loop.
                                        if self._close_after_flush:
                                            self._log.info("graceful_shutdown_after_tool_flush")
                                            break

                                    # ========================================
                                    # TOKEN TRACKING (extract usage metadata)
                                    # ========================================
                                    # The server periodically sends messages with UsageMetadata
                                    if hasattr(event, 'usage_metadata') and event.usage_metadata:
                                        try:
                                            usage = event.usage_metadata

                                            # Diagnostic-only: hand the RAW usage object to an
                                            # optional observer before we reduce it to cost fields.
                                            # None in production (no-op); a harness uses it to read
                                            # cached_content_token_count / traffic_type (bd l3a.1).
                                            if self._on_raw_usage is not None:
                                                try:
                                                    self._on_raw_usage(usage)
                                                except Exception:
                                                    pass  # never let a diagnostic observer break billing

                                            # Extract token counts (Python SDK uses snake_case)
                                            # Handle None values defensively - API may return None for some fields
                                            prompt_tokens = prompt_token_count if (prompt_token_count := getattr(usage, "prompt_token_count", None)) is not None else 0
                                            response_tokens = response_token_count if (response_token_count := getattr(usage, "response_token_count", None)) is not None else 0
                                            total_tokens = total_token_count if (total_token_count := getattr(usage, "total_token_count", None)) is not None else 0

                                            # Debug log if we got unexpected None values
                                            if not total_tokens and (prompt_tokens or response_tokens):
                                                self._log.debug(
                                                    "usage_metadata_partial",
                                                    prompt=prompt_tokens,
                                                    response=response_tokens,
                                                    total=total_tokens
                                                )

                                            # Extract modality breakdowns (TEXT vs AUDIO)
                                            # Python SDK: prompt_tokens_details, response_tokens_details
                                            prompt_details = getattr(usage, "prompt_tokens_details", None) or []
                                            response_details = getattr(usage, "response_tokens_details", None) or []

                                            # Parse input modalities using pattern matching
                                            text_input_tokens = 0
                                            audio_input_tokens = 0
                                            for detail in prompt_details:
                                                match detail:
                                                    case types.ModalityTokenCount(modality=modality, token_count=count):
                                                        # Handle None count values
                                                        safe_count = count if count is not None else 0
                                                        if modality == types.Modality.TEXT:
                                                            text_input_tokens += safe_count
                                                        elif modality == types.Modality.AUDIO:
                                                            audio_input_tokens += safe_count

                                            # Parse output modalities
                                            text_output_tokens = 0
                                            audio_output_tokens = 0
                                            for detail in response_details:
                                                match detail:
                                                    case types.ModalityTokenCount(modality=modality, token_count=count):
                                                        # Handle None count values
                                                        safe_count = count if count is not None else 0
                                                        if modality == types.Modality.TEXT:
                                                            text_output_tokens += safe_count
                                                        elif modality == types.Modality.AUDIO:
                                                            audio_output_tokens += safe_count

                                            # Calculate costs by modality, using the
                                            # rate row for the ACTIVE model's family so
                                            # a 2.5 vs 3.1 A/B is costed correctly.
                                            pricing = get_pricing_for_model(self._model_name)
                                            text_input_cost = text_input_tokens * pricing["text_input"]
                                            audio_input_cost = audio_input_tokens * pricing["audio_input"]
                                            text_output_cost = text_output_tokens * pricing["text_output"]
                                            audio_output_cost = audio_output_tokens * pricing["audio_output"]
                                            total_cost = text_input_cost + audio_input_cost + text_output_cost + audio_output_cost

                                            # Update cumulative counters
                                            self._session_prompt_tokens += prompt_tokens
                                            self._session_candidate_tokens += response_tokens
                                            self._session_total_tokens += total_tokens
                                            self._session_total_cost += total_cost
                                            self._session_text_input_tokens += text_input_tokens
                                            self._session_audio_input_tokens += audio_input_tokens
                                            self._session_text_output_tokens += text_output_tokens
                                            self._session_audio_output_tokens += audio_output_tokens

                                            # Clear console logging for token usage
                                            print(f"\n{'='*80}")
                                            print(f"[tokens] TOKEN USAGE")
                                            print(f"{'='*80}")
                                            print(f"Prompt: {prompt_tokens:,} tokens (text: {text_input_tokens:,}, audio: {audio_input_tokens:,})")
                                            print(f"Response: {response_tokens:,} tokens (text: {text_output_tokens:,}, audio: {audio_output_tokens:,})")
                                            print(f"Total this turn: {total_tokens:,} tokens")
                                            print(f"Cost this turn: ${total_cost:.6f}")
                                            print(f"Session total: {self._session_total_tokens:,} tokens (${self._session_total_cost:.6f})")
                                            print(f"{'='*80}\n")

                                            # Log to file for token dashboard (local dev only)
                                            # Only log if session context is available
                                            if self._form_session_id and self._form_id:
                                                try:
                                                    token_logger = get_token_logger()
                                                    self._log.debug("token_file_logging",
                                                                  form_id=self._form_id,
                                                                  form_session_id=self._form_session_id,
                                                                  gemini_session_id=self._instance_id)
                                                    token_logger.log_token_event(
                                                        form_id=self._form_id,
                                                        form_session_id=self._form_session_id,
                                                        gemini_session_id=self._instance_id,
                                                        section_id=self._current_section_id,
                                                        # This event's token counts
                                                        prompt_tokens=prompt_tokens,
                                                        response_tokens=response_tokens,
                                                        total_tokens=total_tokens,
                                                        # Modality breakdown
                                                        text_input=text_input_tokens,
                                                        audio_input=audio_input_tokens,
                                                        text_output=text_output_tokens,
                                                        audio_output=audio_output_tokens,
                                                        # Costs
                                                        text_input_cost=text_input_cost,
                                                        audio_input_cost=audio_input_cost,
                                                        text_output_cost=text_output_cost,
                                                        audio_output_cost=audio_output_cost,
                                                        total_cost_usd=total_cost,
                                                        # Session cumulative
                                                        session_total_tokens=self._session_total_tokens,
                                                        session_total_cost_usd=self._session_total_cost,
                                                        session_text_input=self._session_text_input_tokens,
                                                        session_audio_input=self._session_audio_input_tokens,
                                                        session_text_output=self._session_text_output_tokens,
                                                        session_audio_output=self._session_audio_output_tokens,
                                                    )
                                                except Exception as log_err:
                                                    # Don't fail silently - we need to know if logging fails
                                                    self._log.warning("token_file_logging_error", error=str(log_err))
                                            else:
                                                # Debug: Why didn't we log?
                                                self._log.debug("token_file_logging_skipped",
                                                              has_form_session_id=bool(self._form_session_id),
                                                              has_form_id=bool(self._form_id),
                                                              form_session_id=self._form_session_id,
                                                              form_id=self._form_id)
                                        except Exception as e:
                                            self._log.warning("token_extraction_error", error=str(e), exc_info=True)

                                except Exception:
                                    self._log.exception("event_handling_error")
                                    continue
                        except ConnectionClosed as exc:
                            print(f"\n{'='*80}")
                            print(f"[error] GEMINI CONNECTION DROPPED")
                            print(f"{'='*80}")
                            print(f"Reason: {str(exc)}")
                            print(f"Events received before disconnect: {event_count}")
                            print(f"Intentional shutdown: {self._intentional_shutdown}")
                            print(f"{'='*80}\n")

                            self._log.error("gemini_session_connection_closed",
                                          reason=str(exc),
                                          event_count=event_count,
                                          intentional_shutdown=self._intentional_shutdown)
                            break

                        # Exit the while-loop on a cooperative graceful shutdown (the
                        # `break` after send_tool_response above lands here) OR when
                        # the session produced no events (bd polyglot-pdf-0c1).
                        if self._close_after_flush:
                            self._log.info("receive_loop_exit_graceful_shutdown")
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
                        # Session lifecycle marker (bd polyglot-pdf-2m9): pair to
                        # session_open; records the final audio-in/out rollup so a
                        # closed session shows at a glance whether any audio flowed.
                        self._dev_log_io("local", "session_close", {
                            "events": event_count if 'event_count' in locals() else 0,
                            "audio_in_frames": getattr(self, "_audio_in_frames", 0),
                            "audio_out_frames": getattr(self, "_audio_chunk_count", 0),
                        })
                        self._log.info("gemini_session_cleaned_up",
                                     instance_id=self._instance_id,
                                     event_count=event_count if 'event_count' in locals() else 0,
                                     message="Session closed and cleaned up")
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

            print(f"\n{'='*80}")
            print(f"[session] GEMINI SESSION STARTING")
            print(f"{'='*80}")
            print(f"Max connection attempts: {max_attempts}")
            print(f"Model: {self._model_name}")
            print(f"{'='*80}\n")

            while attempt < max_attempts:
                # Check if session was intentionally finalized (Level 3 timeout, manual disconnect)
                # If so, don't retry - just exit cleanly
                if self._intentional_shutdown:
                    print(f"\n{'='*80}")
                    print(f"[closed] SESSION INTENTIONALLY CLOSED - NO RETRY")
                    print(f"{'='*80}\n")

                    self._log.info("session_intentionally_closed_no_retry")
                    return

                attempt += 1

                if attempt > 1:
                    print(f"\n{'='*80}")
                    print(f"[retry] RETRY ATTEMPT {attempt}/{max_attempts}")
                    print(f"{'='*80}")
                    print(f"Previous error: {str(last_exc) if last_exc else 'Unknown'}")
                    print(f"{'='*80}\n")
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
                    if attempt > 1:
                        print(f"\n{'='*80}")
                        print(f"[ok] RETRY SUCCESSFUL - CONNECTION RESTORED")
                        print(f"{'='*80}")
                        print(f"Successful attempt: {attempt}/{max_attempts}")
                        print(f"{'='*80}\n")

                        self._log.info("retry_successful",
                                      attempt=attempt,
                                      max_attempts=max_attempts)

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
                        print(f"\n{'='*80}")
                        print(f"[warn] CONNECTION ATTEMPT FAILED")
                        print(f"{'='*80}")
                        print(f"Attempt: {attempt}/{max_attempts}")
                        print(f"Error: {str(e)}")
                        print(f"Host: {host}")
                        print(f"DNS result: {dns_result}")
                        print(f"Is name error: {is_name_err}")
                        print(f"{'='*80}\n")

                        self._log.error('connect_attempt_failed',
                                       attempt=attempt,
                                       max_attempts=max_attempts,
                                       error=str(e),
                                       host=host,
                                       dns=dns_result,
                                       is_name_error=is_name_err)
                    except Exception:
                        pass

                    if attempt >= max_attempts or not is_name_err:
                        print(f"\n{'='*80}")
                        print(f"[fatal] ALL RETRY ATTEMPTS EXHAUSTED")
                        print(f"{'='*80}")
                        print(f"Failed after {attempt} attempts")
                        print(f"Final error: {str(e)}")
                        print(f"{'='*80}\n")

                        self._log.error("all_retries_exhausted",
                                       attempts=attempt,
                                       final_error=str(e))

                        # Give up and re-raise the last exception
                        raise

                    # Backoff before retrying
                    backoff_seconds = 0.5 * (2 ** (attempt - 1))
                    print(f"[wait] Waiting {backoff_seconds}s before retry...")

                    try:
                        await asyncio.sleep(backoff_seconds)
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
