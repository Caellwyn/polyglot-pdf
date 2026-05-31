from typing import Annotated
from fastapi import Depends, FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables from .env file (if it exists)
load_dotenv()

from .config import Settings, get_settings
from .routes import websocket_routes
from .routes.vad_config_routes import vad_config_websocket
from .routes import pdf_fill_routes
from .routes import disclaimer_routes
from .routes import form_kit_routes
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(websocket_routes.router)
app.include_router(websocket_routes.router, prefix="/api")  # Handle Firebase rewrites
app.include_router(pdf_fill_routes.router)
app.include_router(disclaimer_routes.router)
app.include_router(form_kit_routes.router)


@app.websocket("/ws/vad-config")
async def vad_config_endpoint(websocket: WebSocket):
    """WebSocket endpoint for VAD configuration updates from tuning lab"""
    await vad_config_websocket(websocket)


@app.get("/health")
async def health(settings: Annotated[Settings, Depends(get_settings)]):
    return {
        "status": "ok",
        "models": {
            "native": settings.MODEL_NATIVE,
            "labeling": settings.MODEL_LABELING,
        },
        "use_premium_model": settings.USE_PREMIUM_MODEL,
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

