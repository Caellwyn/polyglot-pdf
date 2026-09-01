import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional
import inspect
from copy import deepcopy
import json
import re
import os
import socket
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

from websockets.exceptions import ConnectionClosed

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
import structlog

from backend.utils.json_recovery import extract_json_from_part
from backend.utils.dev_file_logger import get_dev_logger, DEV_LOGGING_ENABLED
from backend.utils.structured_logger import get_logger as get_structured_logger
from backend.utils.token_file_logger import get_token_logger
from backend.config import get_pricing_for_model, model_family

from backend.ports.live_ai_port import ILiveAI, LiveAISession


# Local-dev debug dumps below resolve against the PROJECT ROOT derived from
# __file__, never the process cwd: the local launchers run uvicorn from
# backend/ (to scope the --reload watch away from sibling worktrees), so a
# cwd-relative "backend/logs" would land in backend/backend/logs. Use this for
# any new dump path rather than a bare relative string.
_LOG_ROOT = Path(__file__).resolve().parents[2] / "backend" / "logs"


# ============================================================================
# LOGGING TAG GUIDE (ASCII tags for easy log scanning -- bd polyglot-pdf-bw8)
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


def _dedupe_responses_by_id(responses):
    """Drop duplicate FunctionResponses that share a call id, keeping the first.

    Defensive hardening (bd polyglot-pdf-ux15): a single event is handled by BOTH
    the model_turn.parts path and the event.tool_call path, each appending to the
    same per-event ``responses`` list. If one event ever carried the SAME call in
    both shapes, Gemini would receive TWO FunctionResponses for one call id -- a
    protocol violation. Live evidence (3 instrumented native-audio runs, bd ux15
    notes) shows the two shapes do NOT co-occur today, so this is a no-op in
    practice; it exists so a future SDK/model change that DID emit both cannot send
    a duplicate. Responses with no id (the rare genuinely-id-less call) cannot be a
    duplicate-by-id and are always kept. Returns ``(deduped_list, dropped_ids)`` so
    the caller can LOG a dropped duplicate -- the assumption staying observable
    matters more than the silent drop.
    """
    seen_ids: set = set()
    deduped = []
    dropped_ids = []
    for resp in responses:
        rid = getattr(resp, "id", None)
        if rid and rid in seen_ids:
            dropped_ids.append(rid)
            continue
        if rid:
            seen_ids.add(rid)
        deduped.append(resp)
    return deduped, dropped_ids


def _tool_error_envelope(message: str = "The tool call failed; ask the user to repeat.") -> dict:
    """Structured, PII-free error body for a FunctionResponse when a tool callback
    RAISES (bd polyglot-pdf-wpw.1 / WS-C2).

    Replaces the bare ``{}`` ack that a callback exception used to send: an empty
    body reads to the model as "the tool succeeded with no data," so it
    confabulates success and moves on -- the user's value is silently lost. The
    body nests the failure under an ``error`` key -- the exact shape the official
    Live API docs use to report a tool failure (their ``except`` branch sends
    ``response={"error": ...}``; see docs/genai_docs). The Live API
    ``FunctionResponse`` carries only a free-form ``response`` dict (no dedicated
    output/error channel in google-genai 1.38's type -- verified), so an
    ``error`` key inside ``response`` is THE documented way to make the model
    read the call as FAILED and re-ask. The ``status``/``retryable`` fields ride
    alongside: ``retryable`` lets the model distinguish a transient failure
    (re-ask) from a permanent one.

    NO PII in THIS body: the message is a fixed, caller-controlled string --
    NEVER the exception text (which can embed the field value the callback was
    handling) and NEVER the arguments. The scrubbing guarantee is scoped to the
    model-facing FunctionResponse this helper builds; it does NOT extend to the
    surrounding ``except`` block, whose pre-existing dev_logger.log_error call
    still passes ``str(e)`` and ``parsed_arguments`` (the terminal write emits
    ``str(e)`` unconditionally). Redacting that callback-error log path is a
    separate, pre-existing concern tracked under bd polyglot-pdf-oeq / hjo. The
    legitimate "callback returned None" case keeps the ``{}`` coercion (the tks
    every-named-call-gets-a-response invariant); only a RAISE produces this
    envelope.
    """
    return {"status": "error", "retryable": True, "error": message, "message": message}


# Rough chars-per-token used to estimate the unevictable SI+tools floor. The Live
# API re-bills the whole context every turn; the system instruction + tool
# declarations are NEVER evicted, so they set a hard floor under any sliding
# window. ~4 chars/token is the same coarse estimate this file already uses for
# token accounting (the debug SI write + the per-turn response estimate); it does
# NOT need to be exact -- the derived window only needs to land JUST ABOVE the
# floor, and the headroom/margin knobs absorb the estimator's slop. bd jnjj.35.
_FLOOR_CHARS_PER_TOKEN = 4


# Live API bounds for context_window_compression.trigger_tokens (wire-verified
# 2026-07-05: Vertex closes the connect with 1007 "Context window trigger tokens
# must be within [5000, 128000]" for anything outside them). Used by
# _build_live_config to clamp derived/configured triggers -- see the clamp there.
_COMPRESSION_TRIGGER_MIN_TOKENS = 5000
_COMPRESSION_TRIGGER_MAX_TOKENS = 128_000


# WS close codes that count as a SPONTANEOUS drop worth forwarding to the client
# so it can reconnect (bd polyglot-pdf-ppfy). 1011 is the intermittent Gemini 2.5
# native-audio "Input data processing failed" that motivated this; 1006 is an
# abnormal closure with no close frame (also a genuine unexpected drop). A NORMAL
# close (1000) and a GoAway-driven server-lifecycle close are deliberately EXCLUDED
# -- those are routine and the client already handles a GoAway via its own
# pre-emptive reconnect, so re-forwarding them would mislabel a normal reset as an
# AI failure. Same catch block sees "normal end, GoAway expiry, 1011" alike, so the
# code -- not merely "an exception was caught" -- is what distinguishes the case.
_SPONTANEOUS_DROP_CLOSE_CODES = frozenset({1011, 1006})


def _merge_speech_config(config: Dict[str, Any], key: str, value: Any) -> None:
    """Set ONE key inside config['speech_config'], preserving whatever is
    already there.

    speech_config has two independent contributors -- the session language
    (`language_code`) and the prebuilt voice (`voice_config`) -- set by separate,
    separately-gated blocks in _build_live_config. Each must be able to run
    first, last, or alone.

    This exists because a bare `config['speech_config'] = {...}` in EITHER block
    silently drops the other contributor's key: no exception, no log, and the
    session simply connects with the default voice (or without the language
    hint). Routing both writers through one helper makes that failure
    STRUCTURALLY impossible rather than a rule each call site has to remember --
    which matters because the earlier "just write both blocks as merges" fix was
    reverted by an unrelated edit and the test suite stayed green (it was
    grepping source text for a single-quoted assignment, so a double-quoted one
    walked straight past it).
    """
    speech_cfg = config.get('speech_config')
    if not isinstance(speech_cfg, dict):
        speech_cfg = {}
    speech_cfg[key] = value
    config['speech_config'] = speech_cfg


def estimate_si_floor_tokens(
    system_instruction: Optional[str],
    function_declarations: Optional[List[Dict[str, Any]]],
) -> int:
    """Estimate the unevictable SI+tools floor (in tokens) for a Live session.

    The floor = the system-instruction text plus the serialized tool declarations,
    both of which the Live API keeps in context for the whole session and re-bills
    every turn. A sliding window can only evict CONVERSATION turns, never this
    base, so the window's target_tokens must sit ABOVE it (bd jnjj.35 / A6).

    Coarse on purpose (see _FLOOR_CHARS_PER_TOKEN): the caller adds a headroom
    band on top, so an exact tokenizer is not warranted here.
    """
    si_chars = len(system_instruction) if system_instruction else 0
    tools_chars = (
        len(json.dumps(function_declarations, ensure_ascii=False))
        if function_declarations
        else 0
    )
    return (si_chars + tools_chars) // _FLOOR_CHARS_PER_TOKEN


def derive_compression_window(
    system_instruction: Optional[str],
    function_declarations: Optional[List[Dict[str, Any]]],
    *,
    window_headroom_tokens: int,
    trigger_margin_tokens: int,
    injection_budget_tokens: int = 0,
) -> Dict[str, int]:
    """Derive a per-form (trigger_tokens, target_tokens) from the SI+tools floor.

    jnjj.25 proved the eviction calibration is load-bearing AND form-specific: the
    window must sit JUST ABOVE the unevictable floor (too loose -> Gemini barely
    evicts; too tight -> compression fires turn 1). So instead of a fixed constant
    tuned for one form, derive both per-form:

        floor   = estimate_si_floor_tokens(SI, tools)
        window  = floor  + window_headroom_tokens   (room for a couple fields)
        trigger = window + trigger_margin_tokens    (pile-up before eviction)

    Returns a dict ready to drop into the adapter's compression config. With
    the config.py defaults (headroom 599, margin 1500; bd polyglot-pdf-7872)
    and the session's tool list (7 declarations -- continuous mode drops
    switch_section, and name_spellback is appended by default since bd
    polyglot-pdf-apkdl), the CURRENT default DTI form derives a 5499 floor ->
    6098 window -> 7598 trigger, above the API minimum 5000. Those three are
    MEASURED (2026-08-25, by executing this function on the shipped config),
    not estimated -- RE-EXECUTE rather than trusting them, since they move
    whenever the SI or the tool list does (they dropped
    ~1.4k when the v4 SI diet cut the SI to 11,994 chars, bd polyglot-pdf-6a79;
    the clamp-up + retune path in _build_live_config still fires only for forms
    with a much smaller SI floor). Re-execute this function rather than trusting
    these figures -- they move with the SI text and the kit's injection budget.
    injection_budget_tokens (bd wsao.8) adds headroom for the largest
    per-field inline guidance injection on top. bd jnjj.35 / A6.
    """
    floor = estimate_si_floor_tokens(system_instruction, function_declarations)
    # injection_budget_tokens (bd wsao.8): headroom for the LARGEST per-field
    # inline guidance injection this form can produce (the clamped
    # help.details, ~<=5.3k tokens at the 20k-char budget + index slop).
    # Without it a details-bearing initiating message can exceed the
    # assembled window and Vertex closes 1007 AT SESSION ASSEMBLE -- the
    # session never opens (the wsao.2 measured failure). 0 for a details-less
    # form -> the FORMULA is unchanged from pre-wsao.8 (the derived numbers
    # still move whenever the SI text itself grows). The default DTI form
    # currently derives ~6.3k window / ~7.8k trigger -- above the API minimum
    # (already true before wsao.8), so the clamp-to-5000 path fires only for
    # forms with a much smaller SI floor.
    window = floor + max(1, window_headroom_tokens) + max(0, injection_budget_tokens)
    trigger = window + max(1, trigger_margin_tokens)
    return {"floor": floor, "window": window, "trigger": trigger}


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
        # Fired when the Live server sends a GoAway message before terminating the
        # connection (bd polyglot-pdf-c5t). Carries time_left (a duration string)
        # so the client can pre-emptively reconnect before the abrupt close. The
        # backend only DETECTS + FORWARDS -- the client owns the reconnect (it owns
        # the stateless reconnect path), so no server-side session state is added.
        self._on_go_away = None
        # Fired when Gemini reports the current generation was INTERRUPTED by a
        # barge-in (bd polyglot-pdf-s7uf / 0rpu Stage 2). The client schedules
        # received audio on a session-lifetime playback cursor, so without this
        # forward it keeps playing the dead generation's tail after the model
        # already stopped -- the reason barge-in "does not work" from the user's
        # standpoint. Same discipline as on_go_away: DETECT + FORWARD only.
        self._on_interrupted = None
        # Fired when the Gemini session ends by a SPONTANEOUS drop (e.g. a 1011
        # "Input data processing failed" close) -- NOT an intentional finalize and
        # NOT a section-switch shutdown (bd polyglot-pdf-ppfy). Without this the
        # client-facing WS stays open behind a dead Gemini and the user freezes on
        # "connected"; the callback lets the backend forward the drop so the client
        # can reconnect. Like on_go_away, the backend only DETECTS + FORWARDS.
        self._on_session_dropped = None
        # Fired when the agent's turn is DONE so the thinking indicator's processing
        # state clears (bd polyglot-pdf-wpw.5). Covers the turn-end cases the
        # first-audio clear misses: a barge-in/interruption, AND a server
        # turn_complete/generation_complete with no output audio (e.g. a silent /
        # text-only turn, or the ask_secretary pending instruction where the principal
        # may say nothing). Critically NOT tied to output transcripts, which are off
        # on the default production path (Codex PR #273).
        self._on_processing_done = None
        # Fired when Gemini's native VAD produces an INPUT transcription -- i.e. it
        # heard a real user utterance (bd polyglot-pdf-l3a.4). This is the only
        # reliable "user is present / actually spoke" signal: continuous silence and
        # background noise stream as audio frames but do NOT yield an input
        # transcription. The idle-timeout watchdog resets on this (not on raw mic
        # bytes) so a walk-away with the mic open eventually times out. Optional; a
        # caller that does not pass it leaves input transcription unsurfaced (the
        # pre-l3a.4 behavior). The text itself is NEVER passed to the callback --
        # only the fact a turn occurred -- to keep PHI out of the liveness path.
        self._on_user_activity = None
        # Optional diagnostic observer for the RAW per-turn usage_metadata object
        # (default None = production no-op). Lets a measurement harness inspect fields
        # the cost path does not consume -- e.g. cached_content_token_count / traffic_type
        # -- to tell context-compression activation from a silent no-op (bd l3a.1).
        self._on_raw_usage = None
        # Optional diagnostic observer for the INPUT-transcription TEXT (what Gemini
        # heard), default None = production no-op (bd polyglot-pdf-jnjj.39). Follows
        # the _on_raw_usage harness-observer shape (default-None, set directly by the
        # measurement spike); its receive-loop except branch LOGS the error (a PHI-
        # safe internal message, never the transcript) rather than swallowing it, so
        # an observer bug is visible. Production NEVER sets this: the liveness path
        # (_on_user_activity) is deliberately text-LESS to keep PHI out (the input
        # transcript is user speech). Only the LOCAL-ONLY measurement spike opts in --
        # so the PHI boundary is preserved (default-off, never deployed).
        self._on_input_transcript = None
        self._system_instruction: Optional[str] = None
        self._function_declarations: Optional[List[Dict[str, Any]]] = None

        # Whether Gemini should be asked to return transcripts/text
        self._enable_transcripts = False
        # Local-dev transcript capture (bd polyglot-pdf-0rpu); set from settings
        # in _build_live_config, read by the receive loop. Default False so a
        # session that never built a config cannot log PHI.
        self._dev_transcripts = False

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
        # Spontaneous-drop detection (bd polyglot-pdf-ppfy). Set at the
        # ConnectionClosed/APIError catch in the receive loop so the bg-task
        # done-callback can tell a real error-drop (1011) apart from a clean end (a
        # no-events break leaves these None) OR a benign server-lifecycle close
        # (a normal 1000 / a GoAway-expiry close, which the client already handles
        # via its own reconnect and MUST NOT be re-forwarded as a "dropped" event).
        # _spontaneous_drop_code holds the WS close code so the predicate can gate
        # on the actual failure mode. Reset per-session in _run_session_loop.
        # _dropped_notified latches the notify so a drop is forwarded at most once
        # per session; reset per-session in set_callbacks.
        self._spontaneous_drop_exc: Optional[BaseException] = None
        self._spontaneous_drop_code: Optional[int] = None
        self._dropped_notified: bool = False
        # A GoAway was received this session (bd polyglot-pdf-ppfy). A GoAway is a
        # server-lifecycle reset the client ALREADY reconnects on (via on_go_away ->
        # handleGoAwayReconnect); the real close that follows it -- whatever its code
        # -- must NOT ALSO fire gemini_session_dropped (which would double-drive the
        # client's reconnect / mislabel a routine reset as an AI failure). It is
        # undocumented whether Gemini's post-GoAway close code can fall in
        # {1011,1006}, so this flag excludes the case regardless of the code (fresh-
        # eyes). Reset per-session in _run_session_loop.
        self._go_away_seen: bool = False

        # Session-resumption handle (bd polyglot-pdf-2nikx; SESSION_RESUMPTION_ENABLED,
        # default off -- see config.py). Captured from LiveServerSessionResumptionUpdate
        # messages on the receive stream when session_resumption was requested at
        # connect. NOT reset per-session (unlike _go_away_seen above): the whole
        # point is that it SURVIVES a reconnect so the NEXT connect can present it.
        # A caller resuming an inert (flag-off) session simply never sees a message
        # to capture, so this field stays None and connect() never attaches a
        # session_resumption config -- inert when the flag is off. Exposed via
        # get_resumption_handle() rather than read directly, so a future caller
        # doesn't reach into adapter internals.
        self._resumption_handle: Optional[str] = None

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

        # SPEND CEILING COUNTER (bd polyglot-pdf-ik7e). Deliberately SEPARATE
        # from _session_total_cost, which _run_session_loop zeroes on every
        # Gemini session start -- and a SECTION SWITCH starts a new Gemini
        # session on this same adapter (form_filling_service
        # _switch_to_section_locked: finalize() then start_session(), with the
        # WebSocket left open). So _session_total_cost holds only the CURRENT
        # section's spend.
        #
        # That is fine for the per-session cost LOG, which is what it feeds.
        # It is fatally wrong for a ceiling: the shipped kits have 8 (W-7),
        # 13 (f1040) and 27 (i-90) sections, so banking _session_total_cost at
        # teardown would discard 88-96% of what a client actually spent, and a
        # $10 ceiling would behave like $80-$250 while LOOKING enforced.
        #
        # This one is never reset for the life of the adapter, which is the
        # life of the WebSocket connection.
        self._connection_total_cost: float = 0.0

        # Cumulative modality tracking
        self._session_text_input_tokens: int = 0
        self._session_audio_input_tokens: int = 0
        self._session_text_output_tokens: int = 0
        self._session_audio_output_tokens: int = 0
        # Guard so the session-end cost summary is emitted at most once per session
        # (finalize() can be entered more than once / concurrently). Reset at the
        # start of each session loop.
        self._cost_summary_emitted: bool = False

        # Timing state for voice round-trip observability (bd polyglot-pdf-cwsy).
        # All timestamps are time.monotonic() seconds.
        # _timing_last_activity_end: monotonic timestamp of the most recent
        #   activity_end (or audio_stream_end) sent to Gemini. Reset after each
        #   tool response is sent so the next turn starts fresh.
        # _timing_first_inbound_audio: monotonic timestamp of the FIRST inbound
        #   audio frame after the most recent tool response -- used as the burst
        #   reference in native-VAD mode where no activity_end is sent. Set on
        #   the first enqueued frame; reset after each tool response.
        # _timing_audio_dropped: count of audio frames dropped due to a full
        #   queue during this session. Included in session-end summary.
        self._timing_last_activity_end: Optional[float] = None
        self._timing_first_inbound_audio: Optional[float] = None
        self._timing_audio_dropped: int = 0
        # Count of inbound audio frames dropped because they arrived BEFORE the
        # Gemini session was ready (bd polyglot-pdf-3to5). stream_audio drops these
        # rather than enqueuing them into a consumerless queue that would overflow
        # and then burst on drain -> 1011. Surfaced in the session-close rollup so
        # the handshake-gate is observable. Reset per session in _run_session_loop.
        self._pre_ready_dropped: int = 0

        # Injectable clock + sleep for the real-time audio pacer (bd
        # polyglot-pdf-3to5). Default to the real monotonic clock and asyncio.sleep;
        # tests substitute a fake clock that only advances when _sleep is awaited, so
        # "exactly N frames over T seconds" is deterministic without wall-clock flake.
        # See _audio_sender_loop's fixed-cadence tick.
        self._clock = time.monotonic
        self._sleep = asyncio.sleep

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

        # BCP-47 transcription language bias (bd polyglot-pdf-y25o; set by the
        # service from the handshake's spoken_language, read at connect time).
        self._transcription_language_codes: Optional[List[str]] = None

        # Monotonic per-instance sequence counter for the dev I/O log, so a
        # captured gemini_<date>.jsonl can be re-ordered into the exact
        # send/receive sequence even across interleaved turns (bd polyglot-pdf-kbf).
        self._dev_io_seq: int = 0

        # LOCAL-DEV-ONLY output-audio dump state (bd polyglot-pdf-0rpu). Latched
        # from settings in _build_live_config; default False so a session that
        # never built a config cannot write PHI.
        self._dev_audio_dump: bool = False
        self._dump_buf: bytearray = bytearray()
        self._dump_gen: int = 0
        self._dump_first_seq: Optional[int] = None
        # Output sample rate, latched with the flag (settings is not in scope in
        # the receive loop or here-adjacent helpers).
        self._dump_rate: int = 24000

    # Cap a single generation's dump buffer: 30 MB is ~10.5 minutes of 24 kHz
    # PCM16 mono -- far beyond any real generation, so hitting it means a
    # runaway; force-flush rather than grow without bound.
    _DUMP_BUF_CAP_BYTES = 30 * 1024 * 1024

    def _dev_dump_audio(self, audio_bytes: bytes) -> None:
        """Append one output-audio chunk to the per-generation dump buffer.

        DEV-ONLY (double-gated: .env.DEV marker AND LIVE_DEV_AUDIO_DUMP). Broad
        guard: diagnostics must never break the receive loop (_dev_log_io rule).
        """
        try:
            if not self._dev_audio_dump:
                return
            if self._dump_first_seq is None:
                self._dump_first_seq = self._dev_io_seq
            self._dump_buf.extend(audio_bytes)
            if len(self._dump_buf) > self._DUMP_BUF_CAP_BYTES:
                self._dev_flush_audio_dump("buffer_cap")
        except Exception:
            pass

    def _dev_flush_audio_dump(self, reason: str) -> None:
        """Write the buffered generation to one WAV and log its identity.

        One WAV per generation: called on the interrupted edge, the
        turn_complete/generation_complete edge, and session close -- so a
        partial (interrupted) generation still leaves its evidence on disk.
        Filenames carry ws-session, generation index, and first seq so each WAV
        correlates to the transcript timeline in the JSONL (no colons: Windows).
        """
        try:
            if not self._dev_audio_dump or not self._dump_buf:
                return
            import datetime as _dt
            import wave as _wave
            day = _dt.date.today().isoformat()
            out_dir = _LOG_ROOT / "audio_out" / f"gemini_{day}"
            out_dir.mkdir(parents=True, exist_ok=True)
            sess = (self._form_session_id or self._instance_id or "session").replace(":", "-")
            attempt = getattr(self, "_live_attempt", 0)
            name = f"{sess}_a{attempt}_g{self._dump_gen}_s{self._dump_first_seq or 0}.wav"
            path = out_dir / name
            with _wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self._dump_rate)
                w.writeframes(bytes(self._dump_buf))
            self._dev_log_io("local", "audio_dump", {
                "file": str(path),
                "bytes": len(self._dump_buf),
                "gen": self._dump_gen,
                "first_seq": self._dump_first_seq,
                "last_seq": self._dev_io_seq,
                "reason": reason,
            })
            self._dump_buf = bytearray()
            self._dump_gen += 1
            self._dump_first_seq = None
        except Exception:
            pass

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
                "section", never "part" -- see docs/standards/terminology.md)
        """
        self._form_session_id = form_session_id
        self._form_id = form_id
        self._current_section_id = current_section_id

    def set_transcription_language_codes(self, codes: Optional[List[str]]):
        """Set the BCP-47 language_codes hint for input/output transcription
        (bd polyglot-pdf-y25o).

        Biases the ASR listener toward the user's chosen session language so a
        mumbled session-language word is not transcribed as a neighboring
        language (which drags the native-audio model's language auto-detect
        with it). Applied by _build_live_config at the NEXT connect -- the Live
        config is per-connect. The spoken language is PINNED per session (bd
        polyglot-pdf-87a9), so in practice the codes are set once, before the
        connect; were they ever to change they would take effect on
        the next session (re)establishment; the SI language lock governs until
        then. None clears the hint (unbiased multilingual ASR).
        """
        self._transcription_language_codes = codes or None

    def set_callbacks(
        self,
        on_form_update=None,
        on_transcript=None,
        on_audio=None,
        on_tool_call=None,
        on_go_away=None,
        on_interrupted=None,
        on_session_dropped=None,
        on_user_activity=None,
        on_processing_done=None,
        system_instruction: str | None = None,
        tool_declarations: list[Dict[str, Any]] | None = None,
        enable_transcripts: bool = False,
        injection_budget_tokens: int = 0,
    ):
        """Register callbacks and ensure the background session task is running.

        Callbacks should be async callables. They will be awaited when invoked.
        on_go_away is optional (bd polyglot-pdf-c5t): older callers that do not
        pass it leave GoAway detection logged-only, with no forward.
        on_interrupted is optional (bd polyglot-pdf-s7uf): fired on a Gemini
        barge-in interruption; callers that omit it leave the interruption
        logged-only (the pre-Stage-2 behavior).
        on_user_activity is optional (bd polyglot-pdf-l3a.4): fired on a native-VAD
        input transcription (a real user turn); callers that omit it leave input
        transcription unsurfaced.
        """
        # Removed verbose logging - session lifecycle is logged elsewhere

        self._on_form_update = on_form_update
        self._on_transcript = on_transcript
        self._on_audio = on_audio
        self._on_tool_call = on_tool_call
        self._on_go_away = on_go_away
        self._on_interrupted = on_interrupted
        self._on_session_dropped = on_session_dropped
        self._on_user_activity = on_user_activity
        # bd polyglot-pdf-wpw.5: fired when the agent turn is done (interrupt or
        # turn_complete) so the thinking indicator clears even with no output audio.
        # Optional.
        if on_processing_done is not None:
            self._on_processing_done = on_processing_done
        self._system_instruction = system_instruction
        self._function_declarations = deepcopy(tool_declarations) if tool_declarations else None
        # Compression-window headroom for the largest per-field inline
        # guidance injection (bd wsao.8; see derive_compression_window).
        self._injection_budget_tokens = max(0, int(injection_budget_tokens or 0))
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
        # Reset the spontaneous-drop notify latch per (re)connect so a NEW session
        # that later drops is forwarded once, independent of a prior session's drop
        # (bd polyglot-pdf-ppfy).
        self._dropped_notified = False

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
            #
            # NOTE: the spontaneous-drop notify (bd polyglot-pdf-ppfy) is fired from
            # INSIDE _run_session_loop at the ConnectionClosed/APIError catch, NOT
            # here -- doing it in the loop's own context is race-free (a done-callback
            # reading shared drop markers could be beaten by a restart resetting them;
            # bd polyglot-pdf-bcrn). This callback keeps only its original job.
            self._bg_task.add_done_callback(lambda _t, _ev=closed_event: _ev.set())
            # Removed verbose logging - session start logged below
        else:
            self._log.warn("bg_task_already_running_callbacks_overwritten", 
                          task_id=id(self._bg_task),
                          warning="Multiple connections may be sharing callbacks!")

    def is_session_active(self) -> bool:
        """Check if Gemini session is currently active (has running background task)."""
        return self._bg_task is not None and not self._bg_task.done()

    def get_resumption_handle(self) -> Optional[str]:
        """Return the latest captured session-resumption handle, if any.

        None when SESSION_RESUMPTION_ENABLED is off (never requested, so the
        server never sends an update to capture) or when no resumable update
        has arrived yet this session (bd polyglot-pdf-2nikx).
        """
        return self._resumption_handle

    def _was_spontaneous_drop(self) -> bool:
        """True only when the session ended by a real, unexpected ERROR drop.

        A spontaneous drop is a ConnectionClosed/APIError caught in the receive
        loop whose WS close code is in _SPONTANEOUS_DROP_CLOSE_CODES (1011/1006).
        Excluded cases (all reach the SAME catch block but are routine, so
        re-forwarding them would mislabel a normal reset as an AI failure):
          - a normal close (code not in the set),
          - a section-switch graceful shutdown (`_close_after_flush`),
          - an intentional finalize() (`_intentional_shutdown`),
          - a GoAway-driven close (`_go_away_seen`): a GoAway is a
            server-lifecycle reset the client ALREADY reconnects on, and it is
            undocumented whether Gemini's post-GoAway close code can fall in the
            drop set -- so exclude it regardless of the code (fresh-eyes).
        The flag guards are belt-and-suspenders: the graceful break paths exit
        BEFORE the drop catch, so the drop marker normally stays None on those
        paths, but a drop racing in during an already-requested shutdown or after a
        GoAway must still not fire (bd polyglot-pdf-ppfy).
        """
        return (
            self._spontaneous_drop_exc is not None
            and self._spontaneous_drop_code in _SPONTANEOUS_DROP_CLOSE_CODES
            and not self._intentional_shutdown
            and not self._close_after_flush
            and not self._go_away_seen
        )

    async def _safe_notify_dropped(self) -> None:
        """Await the on_session_dropped callback, swallowing errors (bd ppfy).

        Mirrors the on_go_away forward discipline: the backend only DETECTS +
        FORWARDS, and a failed forward (e.g. the client WS already closed) must
        never crash the session teardown.
        """
        try:
            if self._on_session_dropped is not None:
                await self._on_session_dropped()
        except Exception:
            self._log.exception("on_session_dropped_callback_error")

    async def _audio_sender_loop(self, session):
        """Forward queued audio frames into the live session at a real-time cadence.

        Real-time pacing (bd polyglot-pdf-3to5). The client sends mic audio at a
        clean 1.0x real-time but in bursty 8ms/256-byte frames. The OLD sender
        forwarded each frame the instant it dequeued AND injected an un-paced
        gap-fill silence frame on every sub-interval gap, so the OUTBOUND stream ran
        ~2.2x real-time (silence was ~54% of bytes) and tripped a recurring Gemini
        1011 "sending data too fast". When AUDIO_PACING_ENABLED (default), this runs
        a fixed WS_CHUNK_MS monotonic-clock tick that emits exactly one
        WS_CHUNK_MS-sized frame per tick from a byte accumulator -- the wire cadence
        is real-time, never faster -- and gap-fill silence is sent ONLY on a genuine
        underrun tick. When disabled, the legacy wait_for/timeout gap-fill path runs
        (a clean revert switch preserving the bd 7f7m behavior).

        Gap-fill is now permanently OFF (bd polyglot-pdf-v1m8g) -- see the note at
        its pin below. The surrounding cadence/pacing logic still runs. Config is
        read ONCE per session; extracted to a method (not a closure) so the cadence
        logic is unit-testable with a mock session + injectable clock.
        """
        chunk_count = 0
        from backend.config import get_settings
        _settings = get_settings()
        _in_rate = int(getattr(_settings, "AUDIO_IN_RATE", 16000))
        _mime_type = f"audio/pcm;rate={_in_rate}"
        # Gap-fill is DEAD (bd polyglot-pdf-v1m8g). It existed to keep Gemini's own
        # VAD from being starved of trailing audio by manufacturing a continuous
        # stream; with that VAD gone, turns are bracketed by activity_start/end and
        # audio is expected ONLY inside a bracket, so injecting silence between PTT
        # turns would send un-bracketed audio and desync the turn state (the exact
        # hazard bd polyglot-pdf-7f7m documented). Pinned False here rather than
        # left reading AUDIO_GAPFILL_ENABLED, so the setting cannot resurrect a
        # path that is now always wrong. Removing the plumbing it threads through
        # (both senders) is bd polyglot-pdf-ggdpn.
        _gapfill_enabled = False
        _gapfill_timeout_s = (
            max(1, int(getattr(_settings, "AUDIO_GAPFILL_INTERVAL_MS", 25))) / 1000.0
        )
        # One chunk of mono PCM16 silence at AUDIO_IN_RATE = rate * (ms/1000) * 2 bytes.
        _chunk_ms = max(1, int(getattr(_settings, "WS_CHUNK_MS", 20)))
        _frame_bytes = (_in_rate * _chunk_ms // 1000) * 2
        _silence_frame = bytes(_frame_bytes)
        _pacing_enabled = bool(getattr(_settings, "AUDIO_PACING_ENABLED", True))
        _max_buffer_ms = max(_chunk_ms, int(getattr(_settings, "AUDIO_MAX_BUFFER_MS", 200)))
        _max_buffer_bytes = (_in_rate * _max_buffer_ms // 1000) * 2
        _frame_interval_s = _chunk_ms / 1000.0
        # nonlocal-mutated counters shared with _send_frame.
        _silence_frames_sent = 0

        async def _send_frame(data: bytes, *, is_silence: bool):
            nonlocal chunk_count, _silence_frames_sent
            try:
                chunk_count += 1
                # Log first REAL chunk only (verify sender is working).
                if chunk_count == 1 and not is_silence:
                    self._log.info("[mic] [Sender] First audio chunk sending to Gemini", bytes=len(data))

                await session.send_realtime_input(
                    audio=types.Blob(data=data, mime_type=_mime_type)
                )

                if is_silence:
                    _silence_frames_sent += 1
                    # Rollup only (never per-frame) so gap-fill is observable
                    # without flooding logs.
                    if _silence_frames_sent == 1 or _silence_frames_sent % 100 == 0:
                        self._dev_log_io("send", "gemini_gapfill", {
                            "silence_frames": _silence_frames_sent,
                        })

                # ACTUAL send-to-Gemini rollup (bd polyglot-pdf-2m9): this fires
                # AFTER send_realtime_input returns, so it proves audio crossed
                # the backend->Gemini boundary -- distinct from stream_audio's
                # "audio_summary" which only proves it reached the queue. If
                # "gemini_send" frames lag the queued frames, audio is stuck in
                # the queue / the sender is starved; if they match but Gemini
                # stays silent, the problem is on Gemini's side.
                self._gemini_sent_bytes = getattr(self, "_gemini_sent_bytes", 0) + len(data)
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

        if _pacing_enabled:
            await self._run_paced_sender(
                _send_frame,
                frame_bytes=_frame_bytes,
                frame_interval_s=_frame_interval_s,
                max_buffer_bytes=_max_buffer_bytes,
                silence_frame=_silence_frame,
                gapfill_enabled=_gapfill_enabled,
            )
        else:
            await self._run_legacy_sender(
                _send_frame,
                silence_frame=_silence_frame,
                gapfill_enabled=_gapfill_enabled,
                gapfill_timeout_s=_gapfill_timeout_s,
            )
        self._log.info("[stop] [Sender] Audio sender stopping",
                       total_chunks_sent=chunk_count,
                       silence_frames_sent=_silence_frames_sent)

    async def _run_paced_sender(
        self,
        send_frame,
        *,
        frame_bytes: int,
        frame_interval_s: float,
        max_buffer_bytes: int,
        silence_frame: bytes,
        gapfill_enabled: bool,
    ) -> None:
        """Fixed-cadence drain: emit exactly one frame per frame_interval_s tick.

        A monotonic `next_send` deadline advances by a FIXED frame_interval each
        tick, so the outbound cadence is real-time and can never burst to "catch
        up" -- the property that stops the 1011. Variable-size inbound frames feed a
        byte accumulator that is re-chunked to fixed frame_bytes on emit. On a tick
        with a full frame buffered we send real audio; on an underrun we send one
        silence frame (native-VAD gap-fill) if allowed, else nothing. The
        accumulator is capped at max_buffer_bytes (drop OLDEST, frame-aligned) so we
        never fall more than AUDIO_MAX_BUFFER_MS behind real-time.
        """
        buf = bytearray()
        seen_real_audio = False
        stopping = False  # sentinel seen -> stop pulling new input, drain buf, exit

        # Pre-first-audio: block for the first real chunk (or sentinel). Emit
        # nothing before real audio exists -- there is no cadence to keep yet.
        while not seen_real_audio:
            item = await self._audio_queue.get()
            if item is None:
                return
            seen_real_audio = True
            buf.extend(item)

        next_send = self._clock()
        while True:
            # Bound latency: never buffer more than max_buffer_bytes; drop the
            # OLDEST whole frames beyond the cap (keeps the freshest audio, best for
            # turn-taking / barge-in). frame-aligned so we never emit a half-sample.
            if len(buf) > max_buffer_bytes and frame_bytes > 0:
                overflow = ((len(buf) - max_buffer_bytes) // frame_bytes) * frame_bytes
                if overflow > 0:
                    del buf[:overflow]
                    self._timing_audio_dropped += overflow // frame_bytes
                    now = self._clock()
                    if now - self._last_audio_queue_warning >= self._audio_queue_warning_interval:
                        self._last_audio_queue_warning = now
                        self._log.warn(
                            "[warn] AUDIO_PACING_DROP_OLDEST",
                            message="Dropping oldest buffered audio to bound latency "
                                    "(input outpaced real-time; suppressing similar "
                                    "warnings for 5s)",
                            dropped_frames_session=self._timing_audio_dropped,
                        )

            # Pull everything currently ready (non-blocking) into the accumulator,
            # bounded by the tick deadline. Once the sentinel is seen we stop pulling
            # but keep PACED-emitting the buffered remainder (so trailing real audio
            # is not discarded and is still sent at real-time cadence).
            if not stopping:
                sentinel = await self._drain_ready_into(buf, frame_bytes, next_send)
                if sentinel:
                    stopping = True

            if stopping and len(buf) < frame_bytes:
                # Buffer drained to at most a sub-frame remainder (<=19ms); drop it
                # and exit. This is the only place a partial frame is discarded.
                break

            if len(buf) >= frame_bytes:
                frame = bytes(buf[:frame_bytes])
                del buf[:frame_bytes]
                await send_frame(frame, is_silence=False)
            elif not stopping and gapfill_enabled and not (
                self._close_after_flush or self._intentional_shutdown
            ):
                # Genuine underrun: one silence frame keeps native-VAD's stream
                # continuous. Suppressed once a graceful shutdown owns the socket or
                # a sentinel has begun the drain.
                await send_frame(silence_frame, is_silence=True)
            # else: emit nothing this tick (manual VAD, gap-fill off, or shutting down)

            # Advance the deadline by a FIXED interval (not now+interval) so cadence
            # never drifts. Sleep until it; if we fell a full frame behind (a slow
            # send_realtime_input), reset to now -- degrade to real-time-or-slower,
            # NEVER faster. That clamp is what prevents the too-fast 1011.
            next_send += frame_interval_s
            now = self._clock()
            if now < next_send:
                await self._sleep(next_send - now)
            elif now > next_send + frame_interval_s:
                next_send = now

    async def _drain_ready_into(self, buf: bytearray, frame_bytes: int, deadline: float) -> bool:
        """Pull queued audio into `buf` without blocking past `deadline`.

        Non-blocking get_nowait drains everything already queued; if still short of a
        full frame and time remains before the tick deadline, wait for ONE more item
        up to the remaining time (this doubles as the inter-tick idle wait so an idle
        native-VAD stream still ticks silence every interval without busy-spinning).
        Returns True iff the None sentinel was seen (caller should stop).
        """
        while True:
            try:
                item = self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is None:
                return True
            buf.extend(item)

        if len(buf) < frame_bytes:
            remaining = deadline - self._clock()
            if remaining > 0:
                try:
                    item = await asyncio.wait_for(self._audio_queue.get(), timeout=remaining)
                    if item is None:
                        return True
                    buf.extend(item)
                except asyncio.TimeoutError:
                    pass
        return False

    async def _run_legacy_sender(
        self,
        send_frame,
        *,
        silence_frame: bytes,
        gapfill_enabled: bool,
        gapfill_timeout_s: float,
    ) -> None:
        """Legacy un-paced drain + gap-fill (bd 7f7m), kept behind AUDIO_PACING_ENABLED=false
        as a clean revert switch. Forwards each real chunk immediately; on a stall
        longer than gapfill_timeout_s (and after real audio, not during shutdown)
        emits one silence frame. Does NOT pace -- retained only for rollback.
        """
        seen_real_audio = False
        while True:
            if gapfill_enabled and seen_real_audio:
                try:
                    chunk = await asyncio.wait_for(
                        self._audio_queue.get(), timeout=gapfill_timeout_s
                    )
                except asyncio.TimeoutError:
                    if self._close_after_flush or self._intentional_shutdown:
                        chunk = await self._audio_queue.get()
                    else:
                        await send_frame(silence_frame, is_silence=True)
                        continue
            else:
                chunk = await self._audio_queue.get()

            if chunk is None:
                break

            seen_real_audio = True
            await send_frame(chunk, is_silence=False)

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
        # Handshake readiness gate (bd polyglot-pdf-3to5). The audio sender loop does
        # not exist until AFTER live.connect() completes (~4.5s locally); _session_ready
        # flips True at that same moment. Frames that arrive BEFORE the session is
        # ready have NO consumer -- enqueuing them fills the maxsize queue, which then
        # bursts on drain into a too-fast stream and trips a 1011. Audio is
        # loss-tolerant, so DROP pre-ready frames rather than buffering a backlog
        # ("don't buffer during handshake"). Count + rate-limited log for observability.
        if not self._session_ready:
            self._pre_ready_dropped += 1
            now = time.monotonic()
            if now - self._last_audio_queue_warning >= self._audio_queue_warning_interval:
                self._last_audio_queue_warning = now
                self._log.info(
                    "[mic] AUDIO_DROPPED_PRE_READY",
                    message="Dropping mic audio -- Gemini session not ready yet "
                            "(suppressing similar for 5s)",
                    pre_ready_dropped_session=self._pre_ready_dropped,
                )
            return
        try:
            # Log first audio chunk to verify queueing
            if not hasattr(self, '_first_adapter_audio_logged'):
                self._log.info("[mic] [Adapter] First audio chunk enqueued", bytes=len(audio_chunk), queue_size=self._audio_queue.qsize())
                self._first_adapter_audio_logged = True
            # timing_activity_start/end checkpoint 3 (native-VAD burst reference):
            # record the first inbound frame's monotonic time so timing_tool_call_received
            # has a reference even when no activity_end was sent (bd polyglot-pdf-cwsy).
            # Only set when no activity_end reference exists and not yet captured for
            # this burst. A None-check on the fast path; the assignment only runs once.
            if self._timing_first_inbound_audio is None and self._timing_last_activity_end is None:
                self._timing_first_inbound_audio = time.monotonic()
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
            # Increment per-session drop counter for timing_audio_drops_session (bd polyglot-pdf-cwsy).
            self._timing_audio_dropped += 1
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
        # Returns True iff the turn was actually handed to the live session this call,
        # False if it was queued (session not ready), dropped (no session), or the send
        # raised. Callers that ignore the return are unaffected (back-compat); the B5
        # validator steer (bd polyglot-pdf-jnjj.17) uses it to decide whether to HOLD
        # the section -- a steer that was not actually voiced must not trap the user
        # (Codex/Opus PR #275).
        #
        # Check if session is ready - if not, queue the message
        if not self._session_ready:
            self._log.info("[config] CLIENT_CONTENT_QUEUED (session not ready yet)",
                          message_length=len(text),  # never log message text (may carry field content) -- bd hjo
                          queue_size=len(self._pending_client_content) + 1)
            self._pending_client_content.append(text)
            return False

        if self._current_session is None:
            self._log.warning("[warn] SEND_CLIENT_CONTENT_NO_SESSION")
            return False

        try:
            self._log.info("SEND_CLIENT_CONTENT", message_length=len(text))  # never log message text -- bd hjo

            # DEBUG: Append client content to debug file for token analysis.
            # This writes the RAW message text (which can embed field values), so
            # it is gated behind the same local-dev marker as the PHI logger --
            # production containers have no .env.DEV, so this never runs in prod. bd hjo
            if DEV_LOGGING_ENABLED:
                try:
                    debug_file = _LOG_ROOT / "gemini_system_instruction.txt"
                    debug_file.parent.mkdir(parents=True, exist_ok=True)
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
            return True
        except Exception as exc:
            self._log.error("send_client_content_failed", error=str(exc), message_length=len(text))  # never log message text -- bd hjo
            return False

    async def send_activity_start(self):
        """Send activity_start signal to Gemini (user started speaking).

        Signals the beginning of user speech. Should be called when frontend
        VAD detects speech start, before sending audio chunks.

        Reference: Gemini Live API docs lines 419-435
        """
        # No native-VAD guard any more (bd polyglot-pdf-v1m8g): Gemini's automatic
        # detection is unconditionally disabled, so these manual brackets are the
        # ONLY turn signal and are always sent. The guard that used to drop them
        # existed to avoid interleaving two detectors; there is only one now.
        if self._current_session is None:
            # Session not active - silently ignore (session loss already logged elsewhere)
            self._log.warning("[warn] ACTIVITY_START called but session is None")
            return

        try:
            _t_act_start = time.monotonic()
            await self._current_session.send_realtime_input(activity_start=types.ActivityStart())
            # timing_activity_start checkpoint 3 (bd polyglot-pdf-cwsy).
            # Record the timestamp of the forwarded activity_start signal; clear
            # the native-VAD burst reference so the next audio burst starts fresh.
            self._timing_last_activity_end = None
            self._timing_first_inbound_audio = None
            self._log.info(
                "timing_activity_start",
                ts_monotonic=round(_t_act_start, 4),
            )
        except Exception as e:
            self._log.error("[error] ACTIVITY_START_FAILED", error=str(e))

    async def send_activity_end(self):
        """Send activity_end signal to Gemini (user stopped speaking).

        Signals the end of user speech and flushes Gemini's cached audio buffer.
        Should be called when frontend VAD detects speech end.

        Reference: Gemini Live API docs lines 419-435
        """
        if self._current_session is None:
            # Session not active - silently ignore (session loss already logged elsewhere)
            self._log.warning("[warn] ACTIVITY_END called but session is None")
            return

        # PTT release IS the turn boundary (bd polyglot-pdf-v1m8g). With Gemini's
        # automatic detection off, activity_end is the documented way to close the
        # turn and there is no second detector to conflict with -- so it is sent
        # unconditionally. The old native-VAD arm sent audio_stream_end instead,
        # because manual activity signals were suppressed in that mode and PTT
        # otherwise left Gemini with neither a boundary nor trailing silence; that
        # whole branch is gone with the mode it served.
        try:
            _t_act_end = time.monotonic()
            await self._current_session.send_realtime_input(activity_end=types.ActivityEnd())
            # timing_activity_end checkpoint 3 (bd polyglot-pdf-cwsy).
            # Record the timestamp so timing_tool_call_received can compute
            # since_activity_end_ms.
            self._timing_last_activity_end = _t_act_end
            self._timing_first_inbound_audio = None
            self._log.info(
                "timing_activity_end",
                ts_monotonic=round(_t_act_end, 4),
            )
        except Exception as e:
            self._log.error("[error] ACTIVITY_END_FAILED", error=str(e))

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
            # The session TOTAL lives only in self._session_total_*, so this is
            # the one place it reaches the logs; per-turn token/cost is logged
            # during the session. Counts/costs/ids ONLY -- never field values/transcripts
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
                        # checkpoint 9: include drop count in session summary
                        # so every cost-summary row shows whether frames were dropped.
                        audio_frames_dropped=self._timing_audio_dropped,
                        # Handshake-gate observability (bd polyglot-pdf-3to5): frames
                        # dropped because they arrived before the Gemini session was
                        # ready. A modest count at connect is expected + healthy (it
                        # proves the gate prevented a pre-ready backlog).
                        pre_ready_dropped=self._pre_ready_dropped,
                    )
                except Exception as e:  # noqa: BLE001 -- summary must never block teardown
                    self._log.warning("session_cost_summary_failed", error=str(e))
            # timing_audio_drops_session checkpoint 9 (bd polyglot-pdf-cwsy):
            # emit a dedicated timing event when any frames were dropped this
            # session so a log scan for "timing_audio_drops_session" surfaces
            # queue-pressure sessions without scanning every cost summary.
            if self._timing_audio_dropped > 0:
                try:
                    self._log.info(
                        "timing_audio_drops_session",
                        audio_frames_dropped=self._timing_audio_dropped,
                    )
                except Exception:
                    pass
            # Reset the drop counter for any subsequent session on this instance.
            self._timing_audio_dropped = 0
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
        """Gemini's automatic activity detection is ALWAYS disabled.

        Push-to-talk owns activation (bd polyglot-pdf-v1m8g). PTT *knows* when the
        user is speaking -- they are holding the button -- and the client brackets
        each turn with explicit ``activity_start`` / ``activity_end``. Letting
        Gemini's VAD *infer* the same thing from the audio would add a second gate
        that can only estimate what the first one states exactly, and the two can
        disagree. One turn signal, not two.

        So this returns the constant ``{'disabled': True}``. The sensitivity and
        padding knobs it used to read are GONE from config rather than defaulted
        off: the Live API REJECTS (close code 1007) a config that sets
        ``disabled=True`` alongside any of them, so they were never expressible
        together anyway, and a knob nothing can safely turn on is a trap for the
        next caller (CLAUDE.md scar #7).

        `settings` is retained (unused) so the call sites and the contract smoke
        test keep their shape. See docs/standards/voice-and-vad.md.
        """
        return {'disabled': True}

    def _build_live_config(self, settings) -> Dict[str, Any]:
        """Build the Live connect config exactly as the session loop sends it.

        Extracted from _run_session_loop so external callers (the contract
        smoke test, probes) can drive the REAL config shape instead of a
        hand-rolled minimal dict that 3.1 rejects with 1007
        (bd polyglot-pdf-a7k / polyglot-pdf-4td1).
        """
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

        # Session resumption (bd polyglot-pdf-2nikx; SESSION_RESUMPTION_ENABLED,
        # default OFF -- see config.py for why production stays off this flag).
        # When on, ask the Live server for SessionResumptionUpdate messages
        # (types.SessionResumptionConfig, verified field names against the
        # installed google-genai SDK, 2026-08-27) and, if a handle from a PRIOR
        # session on this adapter instance is already stored, present it so the
        # server resumes that session's state instead of starting fresh. Inert
        # when the flag is off: no key is added to config at all, so a
        # production connect (flag off) is byte-identical to before this change.
        if getattr(settings, "SESSION_RESUMPTION_ENABLED", False):
            config["session_resumption"] = {
                "handle": self._resumption_handle,
            }
            self._log.info(
                "session_resumption_requested",
                resuming=bool(self._resumption_handle),
            )

        # Enable automatic voice activity detection for realtime audio input
        # This allows Gemini to detect when user starts/stops speaking
        try:
            config["realtime_input_config"] = {
                "automatic_activity_detection": self._build_vad_settings(settings)
            }
        except Exception as e:
            self._log.warn("failed_to_set_realtime_input_config", error=str(e))
        
        # Input transcription is needed for TWO independent reasons, so it is
        # requested if EITHER holds (bd polyglot-pdf-l3a.4):
        #   1. transcripts are enabled (the client wants to SEE what Gemini heard); or
        #   2. the idle-liveness callback is registered -- `on_user_activity` fires on
        #      a non-empty `input_transcription`, the only reliable "user spoke" signal
        #      (see the receive loop). Without `input_audio_transcription` in the config
        #      Gemini emits NO input_transcription events, so the callback never fires;
        #      combined with audio no longer bumping the idle clock, an actively-speaking
        #      user on the DEFAULT production path (send_transcript=False) would be wrongly
        #      timed out. Requesting input transcription does NOT forward the text -- the
        #      callback gets none, and only `output_audio_transcription` (gated below on
        #      _enable_transcripts) drives the client-visible transcript. So PHI stays
        #      server-side regardless (bd hjo). (Codex review, PR #214.)
        if self._enable_transcripts or self._on_user_activity is not None:
            config['input_audio_transcription'] = {}
        # Output transcription is the client-visible transcript -- only when requested.
        if self._enable_transcripts:
            config['output_audio_transcription'] = {}

        # LOCAL-DEV-ONLY transcript capture (bd polyglot-pdf-0rpu, maintainer
        # 2026-08-05: "turn on transcripts for local dev ONLY... It's important
        # for privacy that they are turned off for deploy").
        #
        # DOUBLE-GATED, and it must stay that way: DEV_LOGGING_ENABLED (the
        # gitignored backend/.env.DEV marker, which cannot exist on Cloud Run)
        # AND the explicit LIVE_DEV_TRANSCRIPTS opt-in. Transcripts are PHI --
        # this is the same marker that already gates raw-body dev logging, so a
        # deployed service cannot turn it on even if the env var is set.
        #
        # WHY: without the spoken text, a voice bug is diagnosable only by
        # inference. bd 0rpu burned three rounds establishing what the model
        # SAID, because the tool calls prove what was STORED but nothing records
        # what reached the user's ears.
        # Latched onto the instance because the receive loop (_handle_session)
        # does NOT take `settings` -- reading it there would NameError into the
        # loop's blanket `except Exception: pass` and silently log nothing.
        self._dev_transcripts = bool(
            DEV_LOGGING_ENABLED and getattr(settings, "LIVE_DEV_TRANSCRIPTS", False)
        )
        if self._dev_transcripts:
            config.setdefault('input_audio_transcription', {})
            config.setdefault('output_audio_transcription', {})
            self._log.info("[dev] transcript capture ON (LOCAL DEV ONLY -- "
                           "PHI, never enabled in deploy)")

        # LOCAL-DEV-ONLY per-generation output-audio dump (bd polyglot-pdf-0rpu):
        # the attribution ground truth for the text/audio desync -- wrong letters
        # INSIDE the dumped WAV = model-side; WAV correct but heard wrong =
        # client-side playback. Same double-gate + same instance-latch rationale
        # as _dev_transcripts above. PHI: WAVs are spoken form values; they land
        # only under gitignored backend/logs/.
        self._dev_audio_dump = bool(
            DEV_LOGGING_ENABLED and getattr(settings, "LIVE_DEV_AUDIO_DUMP", False)
        )
        self._dump_rate = int(getattr(settings, "AUDIO_OUT_RATE", 24000) or 24000)
        if self._dev_audio_dump:
            self._log.info("[dev] output-audio dump ON (LOCAL DEV ONLY -- "
                           "PHI, never enabled in deploy)")

        # ASR language bias (bd polyglot-pdf-y25o): carry the session language's
        # BCP-47 code on the transcription configs so the ASR listens FOR that
        # language -- the SI only steers the LLM's output language, and an
        # unbiased multilingual ASR transcribing a mumbled es word as pt drags
        # the model's auto-detect with it ("distrito quintal", tester
        # 2026-07-16). Applied only to transcription blocks already requested
        # above (the hint never turns transcription on by itself). getattr-guard:
        # minimal Settings stubs in unit tests may not define the flag.
        lang_codes = getattr(self, "_transcription_language_codes", None)
        if lang_codes and getattr(settings, "TRANSCRIPTION_LANGUAGE_HINT_ENABLED", False):
            if 'input_audio_transcription' in config:
                config['input_audio_transcription'] = {'language_codes': list(lang_codes)}
            if 'output_audio_transcription' in config:
                config['output_audio_transcription'] = {'language_codes': list(lang_codes)}
            self._log.info("[lang] Transcription language bias applied",
                          language_codes=list(lang_codes))

        # API-level speech language (bd polyglot-pdf-m1lg): Google's Live docs
        # recommend speech_config.language_code match the user's language --
        # but the recommendation is scoped to the CASCADED gemini-live-2.5-
        # flash tier (docs/genai_docs/live-api-best-practices.md:56); this
        # repo runs native-audio, where the field is endpoint-VERIFIED ACCEPTED
        # (probe_transcription_lang_codes.py --arm speech-lang, 2026-07-22),
        # not doc-recommended.
        # Reuses the SAME per-session bias codes as the block above (seeded
        # from the handshake spoken language); never set for an unmapped
        # language. Kill-switch mirrors the y25o hint flag pattern.
        # MERGE, never assign -- symmetric with the voice block below. A plain
        # assignment here would drop a voice_config that had already been set,
        # so neither block may care which one runs first.
        if lang_codes and getattr(settings, "SPEECH_LANGUAGE_CODE_ENABLED", False):
            _merge_speech_config(config, 'language_code', list(lang_codes)[0])
            self._log.info("[lang] speech_config.language_code applied",
                          language_code=list(lang_codes)[0])

        # Prebuilt voice (bd polyglot-pdf-rvac follow-up, maintainer 2026-08-03).
        # Google's default voice when unset is "Puck" (Upbeat) -- the wrong
        # register for a stressful legal intake, and the SI's PACE/ARTICULATION
        # prose does NOT reliably control delivery on native audio (the Live docs
        # document no pace/prosody parameter), so the voice IS the lever.
        # MERGE, never assign: the language_code block above may already own
        # config['speech_config'], and a bare assignment here would silently drop
        # it (and vice versa -- this block must not care which ran first).
        voice_name = (getattr(settings, "LIVE_VOICE_NAME", "") or "").strip()
        if voice_name:
            _merge_speech_config(
                config, 'voice_config',
                {'prebuilt_voice_config': {'voice_name': voice_name}},
            )
            self._log.info("[voice] speech_config.voice_config applied",
                          voice_name=voice_name)

        # Sampling temperature (bd polyglot-pdf-0rpu; PROMOTED to a deployable
        # setting by the maintainer 2026-08-10).
        #
        # HISTORY, because this reverses an explicit earlier ruling: it landed
        # LOCAL-DEV-ONLY, double-gated on DEV_LOGGING_ENABLED, on the maintainer's
        # 2026-08-05 call that "there's not much point in having a slider for
        # deployment anyway". That changed once 0.4 was judged BY EAR to make the
        # model's speech measurably clearer, and once every spell-back validation
        # run (bd 22h1f / 44ywm) was conducted at 0.4 -- deploying at Google's
        # default 1.0 would have shipped a configuration we never tested. So the
        # dev-marker gate is gone and LIVE_TEMPERATURE is honored wherever it is
        # set; the local "slider" is simply the same env var, unchanged.
        #
        # STILL UNSET BY DEFAULT: the setting defaults to "" (config.py), and an
        # empty value sends NO temperature, so a deploy that does not set it
        # keeps Google's default byte-identically to before. Only an explicit
        # value changes behavior.
        #
        # WHY it exists: a logged local session (gemini_2026-08-05.jsonl) shows
        # the model handed "Stored value: name_1b_last = 'Smith'" and then
        # telling the user "You said Jose" -- a value from two fields earlier.
        # The default temperature is 1.0 (maximum variability), where a
        # conversationally-plausible continuation can outrank the literal tool
        # response. Lower temperature is the standard lever for that.
        #
        # DO NOT set 0 on native audio: googleapis/js-genai#1578 reports
        # runaway/no-audio output and a 1011 session close at temperature 0, and
        # Google warns that below-1.0 values can loop or degrade. Sweep 0.3-0.6.
        raw_temp = (getattr(settings, "LIVE_TEMPERATURE", "") or "").strip()
        if raw_temp:
            try:
                temp = float(raw_temp)
            except ValueError:
                self._log.warn("LIVE_TEMPERATURE is not a number -- ignoring",
                               value=raw_temp)
            else:
                # Clamp away from the known-bad 0 while leaving the useful
                # range free; a typo must not silently break every session.
                if temp <= 0.0 or temp > 2.0:
                    self._log.warn(
                        "LIVE_TEMPERATURE out of the safe range "
                        "(0 < t <= 2; 0 is known to 1011 native audio) -- ignoring",
                        value=temp)
                else:
                    config['temperature'] = temp
                    self._log.info("LIVE_TEMPERATURE applied",
                                   temperature=temp)

        # Context-window compression (epic polyglot-pdf-l3a, bead -45o). A server-side
        # sliding window bounds the live context so per-turn re-billing stops compounding
        # (quadratic -> linear cumulative cost) and audio sessions can run past the 15-min
        # cap. Gated behind CONTEXT_COMPRESSION_ENABLED (default on, bd polyglot-pdf-7872)
        # so it's one env var from reverting. Syntax verified against the installed
        # google-genai; the SDK
        # accepts these snake_case keys and aliases them to triggerTokens / slidingWindow /
        # targetTokens. See docs/components/context-compression.md.
        if settings.CONTEXT_COMPRESSION_ENABLED:
            # Per-form derivation (bd jnjj.35 / A6): when DTI is the SI shape and the
            # derive flag is on, size the window from THIS form's rendered SI+tools
            # floor rather than the static env constants (which are tuned for nothing
            # in particular and are wrong for any form whose floor differs). The
            # static TRIGGER/WINDOW remain the explicit override -- used when
            # derivation is off, or when there is no DTI SI to measure a floor from
            # (a non-DTI SI has no calibrated floor, so deriving would be guesswork).
            # jnjj.25 proved the calibration is load-bearing; see
            # scripts/spikes/jnjj_25_dti_cost_findings.md.
            derive = (
                getattr(settings, "CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR", False)
                and getattr(settings, "USE_DTI", False)
                and bool(self._system_instruction)
            )
            if derive:
                derived = derive_compression_window(
                    self._system_instruction,
                    self._function_declarations,
                    window_headroom_tokens=settings.CONTEXT_COMPRESSION_WINDOW_HEADROOM_TOKENS,
                    trigger_margin_tokens=settings.CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS,
                    injection_budget_tokens=getattr(
                        self, "_injection_budget_tokens", 0),
                )
                trigger_tokens = derived["trigger"]
                window_tokens = derived["window"]
            else:
                trigger_tokens = settings.CONTEXT_COMPRESSION_TRIGGER_TOKENS
                window_tokens = settings.CONTEXT_COMPRESSION_WINDOW_TOKENS
            # Live API hard bound (wire-verified 2026-07-05 on Vertex: connect dies
            # with 1007 "Context window trigger tokens must be within [5000, 128000]").
            # A derived or configured trigger below the minimum fails the ENTIRE
            # connect -- the session never opens -- so clamp here and log loudly: a
            # less aggressive eviction beats a dead session. This bites the DTI
            # per-form derivation specifically (the I-90 DTI floor derives a ~2800
            # trigger, well under the API minimum).
            clamped_trigger = min(max(trigger_tokens, _COMPRESSION_TRIGGER_MIN_TOKENS),
                                  _COMPRESSION_TRIGGER_MAX_TOKENS)
            if clamped_trigger != trigger_tokens:
                trigger_was_raised = clamped_trigger > trigger_tokens
                self._log.warning(
                    "compression_trigger_clamped_to_api_bounds",
                    requested_trigger_tokens=trigger_tokens,
                    clamped_trigger_tokens=clamped_trigger,
                    derived_from_si_floor=derive,
                )
                trigger_tokens = clamped_trigger
                # When the DERIVED trigger was raised to the API minimum, RE-TUNE
                # the derived window with it (Codex PR #321 P1): keeping the raw
                # derived window (~floor + headroom, e.g. 2200 on the I-90) under
                # a 5000 trigger makes each eviction chop ~2800+ tokens down to
                # just above the SI floor -- stripping the current-field guidance
                # DTI depends on (measured 2026-07-05: the 5000/2200 run drifted
                # post-eviction; 5000/3500 stayed coherent across 7 evictions).
                # Preserve the derivation's margin semantic instead: the window
                # rises with the trigger so only ~trigger_margin tokens are
                # evicted per cycle, exactly as the raw derivation intended.
                # Never LOWER the window (max with the derived value).
                if derive and trigger_was_raised:
                    retuned_window = max(
                        window_tokens,
                        trigger_tokens
                        - settings.CONTEXT_COMPRESSION_TRIGGER_MARGIN_TOKENS,
                    )
                    if retuned_window != window_tokens:
                        self._log.warning(
                            "compression_window_retuned_with_clamped_trigger",
                            derived_window_tokens=window_tokens,
                            retuned_window_tokens=retuned_window,
                        )
                        window_tokens = retuned_window
            # Re-assert the API's window < trigger invariant AFTER the clamp: a
            # trigger clamped DOWN from above the maximum could otherwise land at
            # or below the window (the Settings-level validator runs pre-clamp and
            # the derive path computes the pair independently). Same halving rule
            # as the Settings validator.
            if window_tokens >= trigger_tokens:
                self._log.warning(
                    "compression_window_clamped_below_trigger",
                    requested_window_tokens=window_tokens,
                    clamped_window_tokens=max(1, trigger_tokens // 2),
                )
                window_tokens = max(1, trigger_tokens // 2)
            config["context_window_compression"] = {
                "trigger_tokens": trigger_tokens,
                "sliding_window": {
                    "target_tokens": window_tokens,
                },
            }
            self._log.info(
                "context_window_compression_enabled",
                trigger_tokens=trigger_tokens,
                window_tokens=window_tokens,
                derived_from_si_floor=derive,
                si_floor_tokens=(
                    derived["floor"] if derive else None
                ),
            )
            # Mirror the ACTUAL post-clamp config into the dev JSONL (bd 0rpu):
            # the 2026-08-05 desync investigation could not tell which
            # trigger/window a recorded session ran because this only ever went
            # to console. Now every captured session is self-labeling.
            self._dev_log_io("local", "compression_config", {
                "enabled": True,
                "trigger_tokens": trigger_tokens,
                "window_tokens": window_tokens,
                "derived_from_si_floor": derive,
                "si_floor_estimate_tokens": derived["floor"] if derive else None,
            })
        else:
            # A compression-OFF run must be self-labeling too (attribution Run A).
            self._dev_log_io("local", "compression_config", {"enabled": False})

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
                    debug_file = _LOG_ROOT / "gemini_system_instruction.txt"
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

        # Turn off model "thinking" tokens (shipped with bd polyglot-pdf-ppfy; a
        # maintainer-requested cost/latency win, no bead of its own -- NOT the 3v5m
        # failover, which is a separate, still-open design bead). The form-fill
        # turn loop needs no chain-of-thought, and thinking tokens bill at the
        # output rate. Send the 2.5-family `thinking_budget=0` form ONLY to a model
        # that is positively identified as 2.5 (an explicit allowlist, not "!= 3.1")
        # -- model_family() is a PRICING fallback that maps any unrecognized string
        # to "2.5", so gating on `!= "3.1"` would send `thinking_budget` to an
        # unknown/typo'd model that may not accept it (fresh-eyes). 3.1 uses a
        # different `thinking_level` field and is left at its default. Dict form
        # mirrors the other snake_case config keys the SDK aliases. Effect on
        # native-audio Live is unverified upstream
        # (docs/genai_docs/live-api-best-practices.md), so this is safe-if-ignored.
        # Gated by DISABLE_MODEL_THINKING (default on).
        if settings.DISABLE_MODEL_THINKING and model_family(self._model_name) == "2.5":
            config["thinking_config"] = {"thinking_budget": 0}
        return config

    def session_cost_usd(self) -> float:
        """USD spent on THIS CONNECTION, live (bd polyglot-pdf-ik7e).

        Public because the spend ceiling needs it from the route at teardown,
        and reaching through the counter from there would couple the route to
        this adapter's internals.

        Reads _connection_total_cost, NOT _session_total_cost: the latter is
        zeroed on every Gemini session start, and a SECTION SWITCH starts a
        new one on this same adapter without dropping the WebSocket -- so it
        would report only the last section of an 8-to-27 section form.

        Scope is ONE CONNECTION. A reconnect builds a new adapter and starts
        at zero, which is exactly why the ceiling accumulates per-jti in the
        store rather than trusting any single connection's total.
        """
        return float(self._connection_total_cost)

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
        # Belt-and-suspenders: force the readiness flag False at the START of a
        # session loop (bd polyglot-pdf-3to5). It is already set False by the
        # teardown paths (finalize / begin_graceful_shutdown) before a restart, and a
        # spontaneous drop tears down the whole WS -> a fresh adapter -- so it never
        # leaks True today. Resetting it here anyway keeps the pre-ready audio gate
        # (stream_audio) correct even if a future caller starts a session loop without
        # routing through those teardown paths first; it is flipped True below only at
        # the handshake, once the sender loop is live.
        self._session_ready = False
        # Reset timing state for this session (bd polyglot-pdf-cwsy).
        self._timing_last_activity_end = None
        self._timing_first_inbound_audio = None
        self._timing_audio_dropped = 0
        # Reset the pre-ready drop counter per session (bd polyglot-pdf-3to5) so each
        # (re)connect's handshake-window drops are attributed to that session only.
        self._pre_ready_dropped = 0
        # Reset spontaneous-drop markers per session so a clean end this time is not
        # misread as a drop from a prior session (bd polyglot-pdf-ppfy).
        self._spontaneous_drop_exc = None
        self._spontaneous_drop_code = None
        self._go_away_seen = False

        config = self._build_live_config(settings)

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

                # Start a task to forward queued audio into the session. The loop
                # body lives in _audio_sender_loop (a method, not a closure) so the
                # gap-fill cadence logic is unit-testable with a mock session
                # (bd polyglot-pdf-7f7m).
                sender_task = asyncio.create_task(self._audio_sender_loop(session))
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

                # timing_session_connect_ready checkpoint 1 (bd polyglot-pdf-cwsy).
                # _t_connect_start is set just before the while-attempt loop in
                # _run_session_loop; it is a nonlocal from that scope. The delta is
                # the wall time from "connect object created" to "session receiving".
                try:
                    _t_ready = time.monotonic()
                    _connect_ms = round((_t_ready - _t_connect_start) * 1000)
                    self._log.info(
                        "timing_session_connect_ready",
                        connect_to_ready_ms=_connect_ms,
                        attempt=self._live_attempt,
                    )
                except Exception:
                    pass

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
                                        # The TEXT itself, not just its length
                                        # (bd polyglot-pdf-0rpu). Lengths alone
                                        # cannot answer "what did she SAY?" --
                                        # the question that made 0rpu take three
                                        # rounds to diagnose. PHI: gated on the
                                        # .env.DEV marker AND the explicit
                                        # LIVE_DEV_TRANSCRIPTS opt-in, so it can
                                        # never write in a deployed service.
                                        if getattr(self, "_dev_transcripts", False):
                                            _it_text = (getattr(_it, "text", "") or "") if _it else ""
                                            _ot_text = (getattr(_ot, "text", "") or "") if _ot else ""
                                            if _it_text or _ot_text:
                                                self._dev_log_io("receive", "transcript", {
                                                    "heard_from_user": _it_text,
                                                    "spoken_by_model": _ot_text,
                                                })
                                    except Exception:
                                        pass

                                # GoAway: the Live server sends this BEFORE it
                                # terminates the connection, with time_left (a
                                # duration string) (bd polyglot-pdf-c5t). Surface it
                                # so the client can pre-emptively reconnect ahead of
                                # the abrupt close instead of hitting a mid-turn drop.
                                # Detection is best-effort and never breaks the loop:
                                # the real close still arrives later as ConnectionClosed
                                # / APIError and takes the graceful-break path below.
                                go_away = getattr(event, "go_away", None)
                                if go_away is not None:
                                    time_left = getattr(go_away, "time_left", None)
                                    # Mark the session GoAway'd so a subsequent close
                                    # is not ALSO forwarded as a spontaneous drop (bd
                                    # polyglot-pdf-ppfy): the client already reconnects
                                    # on the GoAway itself.
                                    self._go_away_seen = True
                                    self._log.warning(
                                        "gemini_go_away_received",
                                        time_left=time_left,
                                        event_count=event_count,
                                    )
                                    if self._on_go_away is not None:
                                        try:
                                            await self._on_go_away(time_left)
                                        except Exception:
                                            self._log.exception("on_go_away_callback_error")

                                # Session-resumption update (bd polyglot-pdf-2nikx):
                                # only sent when session_resumption was requested at
                                # connect (SESSION_RESUMPTION_ENABLED; see
                                # _build_live_config), so this is a no-op read on the
                                # default production path. LiveServerSessionResumption
                                # Update carries new_handle (empty when the point is
                                # not resumable, e.g. mid function-call/generation) and
                                # resumable (bool) -- store the handle only when the
                                # server marked this point resumable, so a later
                                # connect never presents a handle the server already
                                # told us would lose data. Best-effort and never
                                # breaks the loop, same discipline as GoAway above.
                                # NO PII in the log: presence/length only, never the
                                # token value (bd hjo).
                                resumption_update = getattr(
                                    event, "session_resumption_update", None)
                                if resumption_update is not None:
                                    try:
                                        new_handle = getattr(
                                            resumption_update, "new_handle", None)
                                        resumable = bool(
                                            getattr(resumption_update, "resumable", False))
                                        if resumable and new_handle:
                                            self._resumption_handle = new_handle
                                            self._log.info(
                                                "session_resumption_handle_captured",
                                                handle_present=True,
                                                handle_len=len(new_handle),
                                                event_count=event_count,
                                            )
                                    except Exception:
                                        self._log.exception(
                                            "session_resumption_update_handling_error")

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

                                            # Ground-truth capture BEFORE playback forwarding
                                            # (bd 0rpu): pre-client bytes, so the dump proves
                                            # what the MODEL generated, not what was played.
                                            self._dev_dump_audio(audio_bytes)
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
                                            
                                            # Flush the dump BEFORE resetting counters: an
                                            # interrupted generation's PARTIAL audio is exactly
                                            # the evidence the desync investigation wants (bd 0rpu).
                                            self._dev_flush_audio_dump("interrupted")

                                            # Reset audio tracking since generation was interrupted
                                            self._audio_chunk_count = 0
                                            self._first_audio_time = None

                                            # Clear the thinking indicator (bd polyglot-pdf-wpw.5):
                                            # an interrupted turn produces no audio/transcript, the
                                            # normal clear edges, so signal it here or it would stay
                                            # set until the max-duration timer.
                                            if self._on_processing_done is not None:
                                                try:
                                                    await self._on_processing_done()
                                                except Exception:
                                                    self._log.warning("on_processing_done_callback_error")

                                            # Forward the interruption to the client (bd
                                            # polyglot-pdf-s7uf / 0rpu Stage 2): the client
                                            # schedules audio on a session-lifetime cursor and
                                            # keeps playing the dead generation's tail unless
                                            # told to flush. Errors swallowed -- a send failure
                                            # never crashes the receive loop (same discipline
                                            # as on_go_away).
                                            if self._on_interrupted is not None:
                                                try:
                                                    await self._on_interrupted()
                                                except Exception:
                                                    self._log.warning("on_interrupted_callback_error")

                                            # Skip further processing of this event
                                            continue
                                        
                                        # ========================================
                                        # Normal processing (no interruption)
                                        # ========================================

                                        # Clear the thinking indicator on a REAL turn end (bd
                                        # polyglot-pdf-wpw.5, Codex PR #273): the agent's turn is
                                        # complete, so processing is over. This fires on the actual
                                        # server_content.turn_complete / generation_complete flag --
                                        # NOT on output_transcription, which is OFF on the default
                                        # production path (send_transcript=False), so a silent/
                                        # audio-less completion would otherwise never clear and would
                                        # dedup the next turn's processing:true. (on_audio remains the
                                        # fast clear for the common audio-reply case; this is the
                                        # backstop for the no-audio case.)
                                        if (getattr(server_content, "turn_complete", False)
                                                or getattr(server_content, "generation_complete", False)):
                                            # Generation boundary: close out this generation's
                                            # output-audio dump (bd 0rpu; no-op unless enabled).
                                            self._dev_flush_audio_dump("turn_complete")
                                            if self._on_processing_done is not None:
                                                try:
                                                    await self._on_processing_done()
                                                except Exception:
                                                    self._log.warning("on_processing_done_callback_error")

                                        # Handle input transcription (what Gemini heard from user)
                                        input_transcription = getattr(server_content, "input_transcription", None)
                                        # A non-empty input transcription means native VAD detected a REAL
                                        # user utterance -- the one reliable "user is present" signal (bd
                                        # polyglot-pdf-l3a.4). Continuous silence / background noise stream as
                                        # audio frames but never produce one. Fire on_user_activity so the WS
                                        # idle watchdog resets on real turns, not on raw mic bytes (a
                                        # walk-away with the mic open then times out instead of burning the
                                        # 15-min session). NEVER pass the text -- only signal that a turn
                                        # occurred -- to keep PHI out of the liveness path (bd hjo).
                                        if (input_transcription is not None
                                                and getattr(input_transcription, "text", None)
                                                and self._on_user_activity is not None):
                                            try:
                                                await self._on_user_activity()
                                            except Exception:
                                                # Liveness signal must never crash the receive loop.
                                                self._log.exception("on_user_activity_callback_error")
                                        # bd polyglot-pdf-jnjj.39: optional diagnostic
                                        # observer for the input-transcript TEXT (what
                                        # Gemini heard). Default None in production (PHI:
                                        # the liveness path above stays text-less); only
                                        # the local-only measurement spike sets it.
                                        if (input_transcription is not None
                                                and getattr(input_transcription, "text", None)
                                                and self._on_input_transcript is not None):
                                            try:
                                                self._on_input_transcript(input_transcription.text)
                                            except Exception as _obs_err:
                                                # A diagnostic observer must never crash the
                                                # loop. Log ONLY the exception TYPE, never the
                                                # traceback/message: this observer receives the
                                                # raw input transcript (user speech), and an
                                                # error mid-parse could embed that text in the
                                                # exception -- _log.exception would then leak
                                                # PHI to logs (Codex PR #246 round 3). Type name
                                                # is safe metadata.
                                                self._log.warning(
                                                    "on_input_transcript_observer_error",
                                                    error_type=type(_obs_err).__name__)

                                        # Handle output transcription (what Gemini said)
                                        transcription = getattr(server_content, "output_transcription", None)
                                        if transcription is not None and getattr(transcription, "text", None):
                                            # Log transcript receipt (indicates Gemini finished speaking)
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
                                                                # Rare inline_data path (bd 0rpu): dump raw;
                                                                # record a non-PCM mime rather than transcode.
                                                                if mime_type and "pcm" not in str(mime_type).lower():
                                                                    self._dev_log_io("receive", "audio_dump_mime", {
                                                                        "mime_type": str(mime_type)})
                                                                self._dev_dump_audio(audio_bytes)
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

                                                            # timing_tool_call_received checkpoint 4
                                                            # (bd polyglot-pdf-cwsy): compute delta
                                                            # since the last activity_end (or the
                                                            # first-inbound-audio burst reference for
                                                            # native-VAD). This is the headline number
                                                            # that attributes the 49s latency.
                                                            try:
                                                                _t_tool_recv = time.monotonic()
                                                                _ref = (
                                                                    self._timing_last_activity_end
                                                                    or self._timing_first_inbound_audio
                                                                )
                                                                _since_ms = (
                                                                    round((_t_tool_recv - _ref) * 1000)
                                                                    if _ref is not None else None
                                                                )
                                                                self._log.info(
                                                                    "timing_tool_call_received",
                                                                    tool=tool_name,
                                                                    since_activity_end_ms=_since_ms,
                                                                    path="model_turn.parts",
                                                                )
                                                            except Exception:
                                                                pass

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

                                                                    _t_cb_start = time.monotonic()
                                                                    response_payload = await self._on_tool_call(tool_name, parsed_arguments)
                                                                    _cb_ms = round((time.monotonic() - _t_cb_start) * 1000)

                                                                    # timing_tool_callback_ms checkpoint 5
                                                                    # (bd polyglot-pdf-cwsy).
                                                                    self._log.info(
                                                                        "timing_tool_callback_ms",
                                                                        tool=tool_name,
                                                                        callback_ms=_cb_ms,
                                                                        path="model_turn.parts",
                                                                    )
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
                                                                    # The verbose traceback (which prints str(e) -- and an
                                                                    # exception string can embed the field value the callback
                                                                    # was handling) is DEV-ONLY: print_exc/str(e) reach
                                                                    # stderr -> Cloud Run -> Cloud Logging in production, where
                                                                    # PII must never go (bd polyglot-pdf-p84m). Gate it on the
                                                                    # same flag the dev file log uses; production keeps only the
                                                                    # PII-free structured line below.
                                                                    if DEV_LOGGING_ENABLED:
                                                                        import traceback
                                                                        print(f"\n{'='*80}")
                                                                        print(f"TOOL CALLBACK ERROR: {tool_name}")
                                                                        print(f"{'='*80}")
                                                                        traceback.print_exc()
                                                                        print(f"{'='*80}\n")
                                                                        # Full traceback (rendered by format_exc_info) is DEV-ONLY.
                                                                        self._log.exception("tool_callback_error", tool=tool_name)
                                                                    else:
                                                                        # Production: NEVER self._log.exception here -- structlog's
                                                                        # format_exc_info processor (backend/utils/logging.py) renders
                                                                        # the traceback AND the exception message into the JSON
                                                                        # "exception" field, and that message can embed the field value
                                                                        # the callback was handling (bd polyglot-pdf-p84m; Codex PR #141
                                                                        # P0). Log the tool name + exception TYPE only -- no str(e),
                                                                        # no exc_info.
                                                                        self._log.error("tool_callback_error", tool=tool_name, error_type=type(e).__name__)

                                                                    # Dev logging: Log tool errors
                                                                    dev_logger = get_dev_logger()
                                                                    dev_logger.log_error(
                                                                        error_type="tool_callback_error",
                                                                        error_message=str(e),
                                                                        context={"tool_name": tool_name, "arguments": parsed_arguments}
                                                                    )

                                                                    # Send a STRUCTURED error body (not the silent {} the None
                                                                    # coercion below would otherwise produce) so the model knows
                                                                    # the call FAILED and re-asks, instead of confabulating
                                                                    # success on an empty ack (bd polyglot-pdf-wpw.1). PII-free:
                                                                    # a fixed message, never the exception text.
                                                                    response_payload = _tool_error_envelope()
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

                                            # timing_tool_call_received checkpoint 4
                                            # (bd polyglot-pdf-cwsy): headline latency number.
                                            try:
                                                _t_tool_recv2 = time.monotonic()
                                                _ref2 = (
                                                    self._timing_last_activity_end
                                                    or self._timing_first_inbound_audio
                                                )
                                                _since_ms2 = (
                                                    round((_t_tool_recv2 - _ref2) * 1000)
                                                    if _ref2 is not None else None
                                                )
                                                self._log.info(
                                                    "timing_tool_call_received",
                                                    tool=tool_name,
                                                    since_activity_end_ms=_since_ms2,
                                                    path="event.tool_call",
                                                )
                                            except Exception:
                                                pass

                                            response_payload = None

                                            if self._on_tool_call is not None and tool_name:
                                                try:
                                                    _t_cb2_start = time.monotonic()
                                                    response_payload = await self._on_tool_call(tool_name, parsed_arguments)
                                                    _cb2_ms = round((time.monotonic() - _t_cb2_start) * 1000)
                                                    # timing_tool_callback_ms checkpoint 5 (bd polyglot-pdf-cwsy).
                                                    self._log.info(
                                                        "timing_tool_callback_ms",
                                                        tool=tool_name,
                                                        callback_ms=_cb2_ms,
                                                        path="event.tool_call",
                                                    )
                                                    self._log.info("tool_callback_returned", tool_name=tool_name, has_response=response_payload is not None, response_keys=list(response_payload.keys()) if isinstance(response_payload, dict) else None)
                                                    # direction="local": backend's own callback output, not inbound.
                                                    self._dev_log_io("local", "tool_callback_result", {
                                                        "path": "event.tool_call",
                                                        "tool_name": tool_name,
                                                        "call_id": call_id,
                                                        "response": response_payload,
                                                    })
                                                except Exception as e:
                                                    # Verbose traceback (prints str(e), which can embed the
                                                    # field value) is DEV-ONLY -- in production it would reach
                                                    # Cloud Logging (bd polyglot-pdf-p84m). Gate on the dev flag.
                                                    if DEV_LOGGING_ENABLED:
                                                        import traceback
                                                        print(f"\n{'='*80}")
                                                        print(f"TOOL CALLBACK ERROR (PATH 2): {tool_name}")
                                                        print(f"{'='*80}")
                                                        traceback.print_exc()
                                                        print(f"{'='*80}\n")
                                                        # Full traceback (rendered by format_exc_info) is DEV-ONLY.
                                                        self._log.exception("tool_callback_error", tool=tool_name)
                                                    else:
                                                        # Production: NEVER self._log.exception here -- format_exc_info renders
                                                        # the exception MESSAGE (which can embed a field value) into the JSON
                                                        # "exception" field -> Cloud Logging (bd polyglot-pdf-p84m; Codex PR
                                                        # #141 P0). Tool name + exception TYPE only.
                                                        self._log.error("tool_callback_error", tool=tool_name, error_type=type(e).__name__)
                                                    # Structured error body, not the silent {} (bd
                                                    # polyglot-pdf-wpw.1) -- same as the model_turn.parts
                                                    # path above, so the model re-asks on a callback raise.
                                                    response_payload = _tool_error_envelope()
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
                                        # Defensive dedup (bd polyglot-pdf-ux15): never send two
                                        # FunctionResponses for one call id, even if a future event carried
                                        # the same call on BOTH the model_turn.parts and event.tool_call
                                        # paths. A no-op today (the shapes do not co-occur live); log loudly
                                        # if it ever fires so the assumption stays observable.
                                        responses, _dropped_dup_ids = _dedupe_responses_by_id(responses)
                                        if _dropped_dup_ids:
                                            # Log the dropped call ids (NOT bodies): a Gemini call id is a
                                            # model-generated token like "function-call-2110448..." -- it is
                                            # NOT a field value / PII, and it is what makes this warning
                                            # actionable (which call, in which turn) if the no-co-occurrence
                                            # assumption ever breaks. The response BODY (which can carry PII)
                                            # is never logged here.
                                            self._log.warning(
                                                "duplicate_tool_response_dropped",
                                                dropped_count=len(_dropped_dup_ids),
                                                dropped_call_ids=_dropped_dup_ids,
                                            )

                                        # Log tool responses being sent to Gemini, for token analysis ONLY.
                                        # NEVER print resp.response -- a tool response (e.g. ask_secretary /
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

                                        # timing_tool_response_sent checkpoint 6
                                        # (bd polyglot-pdf-cwsy): measure the send_tool_response
                                        # call duration. Also reset the activity/audio burst
                                        # reference so the NEXT turn measures from a clean start.
                                        _t_send_resp_start = time.monotonic()
                                        try:
                                            await session.send_tool_response(function_responses=responses)
                                            _send_resp_ms = round((time.monotonic() - _t_send_resp_start) * 1000)
                                            _tool_names_sent = [r.name for r in responses]
                                            self._log.info(
                                                "timing_tool_response_sent",
                                                tool_names=_tool_names_sent,
                                                send_ms=_send_resp_ms,
                                            )
                                        finally:
                                            # Reset burst-reference state for the next turn --
                                            # in a finally so a failed send cannot leave stale
                                            # references that inflate the next turn's
                                            # since_activity_end_ms (fresh-eyes, PR #150).
                                            self._timing_last_activity_end = None
                                            self._timing_first_inbound_audio = None
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
                                            # Survives a section switch; see
                                            # the declaration (bd ik7e).
                                            self._connection_total_cost += total_cost
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

                                                # Structured stdout emit for Cloud Logging (bd polyglot-pdf-5c2h).
                                                # The file above is local-dev-only and lives on the Cloud Run
                                                # container's ephemeral FS; this emits the SAME per-turn counts +
                                                # costs as one JSON line to stdout so a deployed run's per-turn
                                                # token burn survives as queryable jsonPayload (not just the
                                                # human-readable print() block). Counts + costs ONLY -- the
                                                # StructuredLogger schema carries no field-value slot, so this
                                                # stays HIPAA-safe by construction. Additive: never disturbs the
                                                # file write or the print() block above.
                                                try:
                                                    get_structured_logger().log_gemini_api_response(
                                                        form_id=self._form_id,
                                                        form_version="",
                                                        form_session_id=self._form_session_id,
                                                        ws_session_id=self._instance_id,
                                                        metadata={
                                                            # This turn's counts (raw + per-modality)
                                                            "prompt_token_count": prompt_tokens,
                                                            "candidates_token_count": response_tokens,
                                                            "total_token_count": total_tokens,
                                                            "text_input": text_input_tokens,
                                                            "audio_input": audio_input_tokens,
                                                            "text_output": text_output_tokens,
                                                            "audio_output": audio_output_tokens,
                                                            # This turn's costs (per-modality + total)
                                                            "text_input_cost_usd": round(text_input_cost, 8),
                                                            "audio_input_cost_usd": round(audio_input_cost, 8),
                                                            "text_output_cost_usd": round(text_output_cost, 8),
                                                            "audio_output_cost_usd": round(audio_output_cost, 8),
                                                            "cost_estimate_usd": round(total_cost, 8),
                                                            # Session cumulative totals
                                                            "session_tokens_so_far": self._session_total_tokens,
                                                            "session_cost_so_far_usd": round(self._session_total_cost, 8),
                                                            "section_id": self._current_section_id,
                                                        },
                                                    )
                                                except Exception as emit_err:
                                                    self._log.warning("token_structured_emit_error", error=str(emit_err))
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
                                    # If a graceful shutdown was requested (e.g.
                                    # send_tool_response raised AFTER the switch_section
                                    # callback set _close_after_flush), BREAK rather than
                                    # continue -- otherwise the loop keeps iterating until
                                    # the swap task's 5s wait_for backstop fires, a
                                    # demo-visible freeze (fresh-eyes PR #135).
                                    if self._close_after_flush:
                                        self._log.info("graceful_shutdown_after_event_error")
                                        break
                                    continue
                        # google-genai >= 2.x converts websocket closures inside
                        # AsyncSession.receive() into genai errors.APIError
                        # (code = the WS close code) instead of letting
                        # ConnectionClosed propagate; the send_* methods still
                        # raise raw ConnectionClosed. Catch BOTH so every
                        # server-side close (normal end, GoAway expiry, 1011)
                        # takes this graceful break path, not the unexpected-
                        # error re-raise below. bd polyglot-pdf-x52p
                        except (ConnectionClosed, genai_errors.APIError) as exc:
                            # Read the WS close code (bd polyglot-pdf-ppfy). A raw
                            # ConnectionClosed exposes it as .rcvd.code (its top-level
                            # .code is deprecated in websockets 13.1+), so read .rcvd
                            # FIRST; an APIError (session.receive() re-raises websocket
                            # closures as APIError with the WS close code) carries it
                            # as .code.
                            close_code = getattr(getattr(exc, "rcvd", None), "code", None)
                            if close_code is None:
                                close_code = getattr(exc, "code", None)
                            print(f"\n{'='*80}")
                            print(f"[error] GEMINI CONNECTION DROPPED")
                            print(f"{'='*80}")
                            print(f"Reason: {str(exc)}")
                            print(f"Events received before disconnect: {event_count}")
                            print(f"Intentional shutdown: {self._intentional_shutdown}")
                            print(f"{'='*80}\n")

                            self._log.error("gemini_session_connection_closed",
                                          reason=str(exc),
                                          close_code=close_code,
                                          event_count=event_count,
                                          intentional_shutdown=self._intentional_shutdown)
                            # Record the drop + its close code (bd polyglot-pdf-ppfy)
                            # so _was_spontaneous_drop() can tell a real error-drop
                            # (1011/1006) apart from a clean no-events end or a benign
                            # normal/GoAway close, and forward ONLY a genuine drop.
                            self._spontaneous_drop_exc = exc
                            self._spontaneous_drop_code = close_code
                            # Forward the drop to the client HERE, inside the loop's
                            # own execution -- this is unambiguously THIS session's
                            # context and can await directly. Firing here (rather than
                            # from the bg-task done-callback) closes a race where a
                            # restart_gemini_session() slipping into the
                            # task-done-but-callback-not-yet-fired window resets the
                            # drop markers before a done-callback could read them (bd
                            # polyglot-pdf-bcrn, caught pre-PR). The _dropped_notified
                            # latch + _was_spontaneous_drop() guards still apply.
                            if (
                                self._on_session_dropped is not None
                                and not self._dropped_notified
                                and self._was_spontaneous_drop()
                            ):
                                self._dropped_notified = True
                                await self._safe_notify_dropped()
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
                        # Leave any partial generation's audio on disk before the
                        # close marker (bd 0rpu; no-op unless the dump is enabled).
                        self._dev_flush_audio_dump("session_close")
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

            # timing_session_connect_ready checkpoint 1 (bd polyglot-pdf-cwsy):
            # capture the connect-attempt start time; the ready timestamp is set
            # inside _handle_session once the session is accepting messages.
            _t_connect_start = time.monotonic()

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
                # Reset per attempt so a retry's connect_to_ready_ms measures THIS
                # attempt only, not prior failures + backoff (fresh-eyes, PR #150).
                _t_connect_start = time.monotonic()
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
