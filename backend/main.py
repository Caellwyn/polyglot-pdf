from typing import Annotated
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables from .env file (if it exists)
load_dotenv()

from .config import Settings, get_settings, parse_extra_origins
from .routes import websocket_routes
from .routes import pdf_fill_routes
from .routes import disclaimer_routes
from .routes import form_kit_routes
from .routes import editor_kit_routes
from .routes import dev_console_routes
from .utils.logging import configure_logging


configure_logging()

app = FastAPI(title="Web Form Voice Filler API", version="0.1.0")

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
app.include_router(disclaimer_routes.router)
app.include_router(form_kit_routes.router)
app.include_router(editor_kit_routes.router)  # token-gated hosted-editor surface (bd 92qe.1)
app.include_router(dev_console_routes.router)  # dev-only console ingest (bd polyglot-pdf-2m9; 404 in prod)


@app.get("/health")
async def health(settings: Annotated[Settings, Depends(get_settings)]):
    return {
        "status": "ok",
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

