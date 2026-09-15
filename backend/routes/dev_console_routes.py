"""
Dev console-log ingest (bd polyglot-pdf-2m9).

A DEV-ONLY endpoint that receives batches of the frontend's console output and
writes them into the same dev log stream as the Gemini I/O events
(backend/logs/gemini_<date>.jsonl), so `scripts/logs.py` can show ONE correlated
timeline -- e.g. a "[PTT] press" console line right next to the audio_summary
frames it produced. This removes the copy/paste loop for frontend logs.

HARD-GATED on DEV_LOGGING_ENABLED (the backend/.env.DEV marker): in production the
route returns 404, so the browser never ships console output to the server and no
PII/PHI is captured server-side (same gating as the rest of the dev logger).

SECOND, INDEPENDENT GATE on K_SERVICE (bd polyglot-pdf-6088m, sprint 23 C4;
PF-10). The marker-file gate above is a FILE presence check: it is correct only
because backend/.env.* is excluded by .dockerignore (pinned by
tests/test_dockerignore_env_exclusion.py), so the marker can never exist inside
a built container. That is one indirection between "we are in production" and
"this route 404s" -- a dockerignore edit that narrowed the pattern, or a build
context that bypassed it, would silently re-enable this route in prod with no
code change here. K_SERVICE is set by Cloud Run and by nothing else (the same
signal backend/services/auth.py's VFF_DISABLE_AUTH bypass checks), so checking
it directly closes the route even if the marker-file gate is ever defeated by a
packaging mistake. Neither gate is redundant: the marker gate is what makes
local dev logging opt-in at all; K_SERVICE is the fail-closed backstop for a
deployed service specifically.
"""
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import structlog

from backend.utils.dev_file_logger import DEV_LOGGING_ENABLED, get_dev_logger

_log = structlog.get_logger().bind(module="dev_console_routes")

router = APIRouter(tags=["dev"])


class ConsoleEntry(BaseModel):
    """One captured console.* call from the frontend."""
    level: str = Field("log", description="console level: log|info|warn|error|debug")
    text: str = Field("", description="Stringified console arguments")
    ts: Optional[int] = Field(None, description="Client epoch ms when logged")


class ConsoleBatch(BaseModel):
    """A flushed batch of console entries from one browser session."""
    ws_session_id: Optional[str] = Field(None, description="Frontend form-session id, if known")
    entries: List[ConsoleEntry] = Field(default_factory=list)


@router.post("/dev/console-log")
async def ingest_console_log(batch: ConsoleBatch) -> Dict[str, Any]:
    """Append a batch of frontend console lines to the dev log stream.

    No-op-by-404 unless dev logging is enabled, so production never accepts this.
    Fails closed on K_SERVICE too (see module docstring) -- a deployed service
    404s here even if the marker-file gate were ever defeated.
    """
    if not DEV_LOGGING_ENABLED or os.getenv("K_SERVICE"):
        # Do not advertise the endpoint in prod.
        raise HTTPException(status_code=404, detail="Not found")

    logger = get_dev_logger()
    if not getattr(logger, "enabled", False):
        return {"ok": True, "written": 0}

    written = 0
    for e in batch.entries:
        # direction="frontend" keeps these distinct from Gemini send/receive while
        # sharing the schema, so logs.py can interleave or filter them.
        logger.log_event(
            direction="frontend",
            message_type=f"console_{e.level}",
            content={"text": e.text, "client_ts": e.ts},
            ws_session_id=batch.ws_session_id,
        )
        written += 1
    return {"ok": True, "written": written}
