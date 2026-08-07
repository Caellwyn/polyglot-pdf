import asyncio

from typing import Annotated
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import structlog

# Load environment variables from .env file (if it exists)
load_dotenv()

from .config import Settings, get_settings, parse_extra_origins
from .routes import websocket_routes
from .routes import pdf_fill_routes
from .routes import tts_routes
from .routes import disclaimer_routes
from .routes import form_kit_routes
from .routes import editor_kit_routes
from .routes import dev_console_routes
from .utils.confirmation_logger import (
    confirmation_sink_status,
    flush_confirmation_sink,
)
from .utils.logging import configure_logging


configure_logging()

_log = structlog.get_logger().bind(module="main")

app = FastAPI(title="Web Form Voice Filler API", version="0.1.0")


async def _drain_confirmation_sink_bounded() -> None:
    """Drain queued Firestore confirmation writes on shutdown, BOUNDED.

    bd polyglot-pdf-z2is, tightened in review round 3: a sync handler would
    block the event loop, and a stalled Firestore commit (gapic default
    deadline 60s) outlives Cloud Run's ~10s SIGTERM grace -- so the drain runs
    in a thread with a 5s cap. On timeout the thread keeps draining in the
    background until SIGKILL (best available); the loop is never blocked.
    """
    try:
        await asyncio.wait_for(asyncio.to_thread(flush_confirmation_sink), timeout=5.0)
    except asyncio.TimeoutError:
        _log.error("confirmation_sink_drain_timeout", timeout_s=5.0)


app.add_event_handler("shutdown", _drain_confirmation_sink_bounded)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",  # Added for dev server port conflicts
        "http://127.0.0.1:5175",
        "http://localhost:5176",  # Schema form dev server
        "http://127.0.0.1:5176",
        "http://localhost:5177",  # Schema form dev server
        "http://127.0.0.1:5177",
        "http://localhost:3001",  # Schema editor dev server
        "http://127.0.0.1:3001",
        # The hosted schema-editor origin(s) arrive via env: it calls this
        # service directly (no Hosting /api rewrite -- its 60s cap would kill
        # minutes-long extraction requests), so CORS must allow it here
        # (bd polyglot-pdf-92qe.1).
    ] + parse_extra_origins(get_settings().CORS_EXTRA_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(websocket_routes.router)
app.include_router(websocket_routes.router, prefix="/api")  # Handle Firebase rewrites
app.include_router(pdf_fill_routes.router)
app.include_router(tts_routes.router)  # deterministic spell-back TTS (bd 22h1f; 503 unless SPELLBACK_TOOL_ENABLED)
app.include_router(disclaimer_routes.router)
app.include_router(form_kit_routes.router)
app.include_router(editor_kit_routes.router)  # token-gated hosted-editor surface (bd 92qe.1)
app.include_router(dev_console_routes.router)  # dev-only console ingest (bd polyglot-pdf-2m9; 404 in prod)


@app.get("/health")
async def health(settings: Annotated[Settings, Depends(get_settings)]):
    # Sink probe (bd z2is round 3): verifies the confirmation trail can WRITE
    # (IAM drift otherwise fails silently). Cached 5 min inside; the wait_for
    # bounds a stalled Firestore so /health never hangs on a broken sink.
    try:
        sink_status = await asyncio.wait_for(
            asyncio.to_thread(confirmation_sink_status), timeout=3.0
        )
    except asyncio.TimeoutError:
        sink_status = "error: probe timed out"
    return {
        "status": "ok",
        "confirmation_sink": sink_status,
        "models": {
            "native": settings.MODEL_NATIVE,
            "labeling": settings.MODEL_LABELING,
        },
        "use_premium_model": settings.USE_PREMIUM_MODEL,
        # Auth/service mode: vertexai=true -> Vertex (ADC/SA); false -> AI Studio
        # (Gemini Developer API via GEMINI_API_KEY). Lets a deploy be verified
        # without dumping env vars.
        "vertexai": settings.VERTEXAI,
        "audio": {
            "in_rate": settings.AUDIO_IN_RATE,
            "out_rate": settings.AUDIO_OUT_RATE,
        },
        "limits": {
            "max_upload_mb": settings.MAX_UPLOAD_MB,
            "ws_chunk_ms": settings.WS_CHUNK_MS,
        },
        "env": {
            "gemini_api_key_present": bool(settings.GEMINI_API_KEY),
        },
    }


@app.get("/version")
async def version():
    return {"version": app.version}

