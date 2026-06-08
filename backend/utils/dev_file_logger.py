"""
Development file logger for Gemini API messages and tool calls.

Writes detailed logs to daily .jsonl files in backend/logs/ for analysis.
Only active in DEVELOPMENT mode (automatic detection).

ENVIRONMENT DETECTION (AUTOMATIC - NO MANUAL FLAGS):
- Development: If backend/.env.DEV file exists -> Enable detailed logging (includes PHI)
- Production: If backend/.env.DEV does NOT exist -> Disable detailed logging (HIPAA safe)

This approach prevents human error:
- .env* files are gitignored and dockerignored
- Production containers never have .env.DEV
- Developers create .env.DEV locally to enable debug logs
- No manual flag flipping needed!

Files are named: gemini_YYYY-MM-DD.jsonl
Format: One JSON object per line for easy DataFrame loading
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _is_development_mode() -> bool:
    """
    Detect if we're running in development mode.

    Checks for existence of backend/.env.DEV marker file.
    This file should ONLY exist in local development environments.

    Returns:
        True if running in development mode (PHI logging allowed)
        False if running in production mode (PHI logging disabled)
    """
    # Check multiple possible locations for the marker file
    marker_paths = [
        Path("backend/.env.DEV"),           # From project root
        Path(".env.DEV"),                   # From backend/ directory
        Path(__file__).parent.parent / ".env.DEV",  # Relative to this file
    ]

    for marker_path in marker_paths:
        if marker_path.exists():
            return True

    return False


# Automatic environment detection - no manual flags!
DEV_LOGGING_ENABLED = _is_development_mode()


class DevFileLogger:
    """
    Development logger that writes to daily .jsonl files.

    Features:
    - Daily rotation (gemini_YYYY-MM-DD.jsonl)
    - JSON Lines format (one object per line)
    - Terminal output for errors/warnings
    - Detailed Gemini messages and tool calls
    """

    def __init__(self, log_dir: str = "backend/logs"):
        """
        Initialize the dev file logger.

        Args:
            log_dir: Directory for log files (relative to project root)
        """
        self.log_dir = Path(log_dir)
        self.enabled = DEV_LOGGING_ENABLED

        if self.enabled:
            # Create logs directory
            self.log_dir.mkdir(parents=True, exist_ok=True)
            # Use sys.stdout.write for emoji-safe output
            msg = f"[DevLogger] Development mode ENABLED - Logging field values to: {self.log_dir}\n"
            sys.stdout.write(msg)
            sys.stdout.flush()
        else:
            msg = "[DevLogger] Production mode - Field values will NOT be logged (HIPAA compliant)\n"
            sys.stdout.write(msg)
            sys.stdout.flush()

    def _get_log_file_path(self) -> Path:
        """Get the path for today's log file."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.log_dir / f"gemini_{today}.jsonl"

    def _write_to_file(self, entry: Dict[str, Any]) -> None:
        """Write a log entry to the daily file."""
        if not self.enabled:
            return

        try:
            log_file = self._get_log_file_path()
            with open(log_file, "a", encoding="utf-8") as f:
                # Write as JSON Lines (one object per line)
                json.dump(entry, f, default=str, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            # If file logging fails, output to terminal
            print(f"[warn] Dev file logger error: {e}", file=sys.stderr)

    def _write_to_terminal(self, message: str, severity: str = "INFO") -> None:
        """Write a message to terminal (always, regardless of file logging)."""
        if severity in ("ERROR", "CRITICAL", "WARNING"):
            print(message, file=sys.stderr, flush=True)
        else:
            print(message, file=sys.stdout, flush=True)

    def log_gemini_message(
        self,
        direction: str,  # "send" or "receive"
        message_type: str,  # "audio", "text", "tool_call", "tool_response", etc.
        content: Dict[str, Any],
        session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
    ) -> None:
        """
        Log a Gemini API message.

        Args:
            direction: "send" (to Gemini) or "receive" (from Gemini)
            message_type: Type of message
            content: Message content (may include PHI in dev mode)
            session_id: Optional session ID
            ws_session_id: Optional WebSocket session ID
        """
        if not self.enabled:
            return

        timestamp = datetime.now(timezone.utc).isoformat()

        entry = {
            "timestamp": timestamp,
            "direction": direction,
            "message_type": message_type,
            "session_id": session_id,
            "ws_session_id": ws_session_id,
            "content": content,
        }

        self._write_to_file(entry)

    # ------------------------------------------------------------------
    # Turn / audio / session lifecycle (bd polyglot-pdf-2m9)
    #
    # These fill the debugging blind spots that plain text_turn/tool_call logging
    # left: whether user mic audio reaches Gemini, whether Gemini responds with
    # audio, where turn boundaries fall, and when sessions open/close. Audio is
    # logged as PER-TURN ROLLUPS (frames/bytes/ms), never per-frame, so the log
    # stays navigable. All events use the same schema (timestamp/direction/
    # message_type/session_id/ws_session_id/content), so the explorer + any
    # analytics consumer keep working.
    # ------------------------------------------------------------------

    def log_event(
        self,
        direction: str,        # "send" | "receive" | "local" | "ws"
        message_type: str,
        content: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
        terminal: bool = False,
        severity: str = "INFO",
    ) -> None:
        """Generic structured event. The single funnel for the lifecycle helpers
        below; use it directly for ad-hoc events. Optionally mirrors to terminal."""
        self.log_gemini_message(
            direction=direction,
            message_type=message_type,
            content=content or {},
            session_id=session_id,
            ws_session_id=ws_session_id,
        )
        if terminal:
            self._write_to_terminal(f"[{message_type}] {content or {}}", severity=severity)

    def log_session_lifecycle(
        self,
        phase: str,            # "open" | "close"
        reason: Optional[str] = None,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
    ) -> None:
        """A Gemini Live session opened or closed. Makes session churn (e.g. the
        disclaimer -> first-section restart, or any unexpected reconnect) explicit."""
        self.log_event(
            direction="local",
            message_type=f"session_{phase}",
            content={"reason": reason, "model": model},
            session_id=session_id,
            ws_session_id=ws_session_id,
        )

    def log_turn_event(
        self,
        phase: str,            # "activity_start" | "activity_end"
        source: Optional[str] = None,   # "ptt" | "silero" | "native" | "manual"
        session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
    ) -> None:
        """A user turn boundary. `source` records who decided it (PTT button,
        client Silero VAD, native Gemini VAD, or a manual prompt)."""
        self.log_event(
            direction="send",
            message_type=phase,
            content={"source": source},
            session_id=session_id,
            ws_session_id=ws_session_id,
        )

    def log_audio_summary(
        self,
        direction: str,        # "send" (user->Gemini) | "receive" (Gemini->user)
        frames: int,
        total_bytes: int,
        duration_ms: Optional[float] = None,
        session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
    ) -> None:
        """Per-turn audio rollup -- the answer to 'did audio actually flow this
        direction, and how much'. Emitted at turn/response end, NOT per frame."""
        self.log_event(
            direction=direction,
            message_type="audio_summary",
            content={
                "frames": frames,
                "bytes": total_bytes,
                "duration_ms": duration_ms,
            },
            session_id=session_id,
            ws_session_id=ws_session_id,
        )

    def log_model_response(
        self,
        text: Optional[str] = None,
        transcript: Optional[str] = None,
        session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
    ) -> None:
        """Gemini produced a text/transcript response (when transcripts are on)."""
        self.log_event(
            direction="receive",
            message_type="model_response",
            content={"text": text, "transcript": transcript},
            session_id=session_id,
            ws_session_id=ws_session_id,
        )

    def log_ws_event(
        self,
        event: str,            # "connect" | "close" | "error" | custom
        detail: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
    ) -> None:
        """WebSocket-layer event (connect/close/error) -- separates transport
        problems from Gemini-session problems when triaging 'nothing happened'."""
        self.log_event(
            direction="ws",
            message_type=f"ws_{event}",
            content=detail or {},
            session_id=session_id,
            ws_session_id=ws_session_id,
        )

    def log_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
    ) -> None:
        """
        Log a tool call from Gemini.

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments
            session_id: Optional session ID
            ws_session_id: Optional WebSocket session ID
        """
        self.log_gemini_message(
            direction="receive",
            message_type="tool_call",
            content={
                "tool_name": tool_name,
                "arguments": arguments,
            },
            session_id=session_id,
            ws_session_id=ws_session_id,
        )

    def log_tool_response(
        self,
        tool_name: str,
        response: Dict[str, Any],
        session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
    ) -> None:
        """
        Log a tool response sent to Gemini.

        Args:
            tool_name: Name of the tool
            response: Response sent to Gemini
            session_id: Optional session ID
            ws_session_id: Optional WebSocket session ID
        """
        self.log_gemini_message(
            direction="send",
            message_type="tool_response",
            content={
                "tool_name": tool_name,
                "response": response,
            },
            session_id=session_id,
            ws_session_id=ws_session_id,
        )

    def log_invalid_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        error: str,
        session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
    ) -> None:
        """
        Log an invalid tool call (also output to terminal).

        Args:
            tool_name: Name of the tool
            arguments: Invalid arguments
            error: Error description
            session_id: Optional session ID
            ws_session_id: Optional WebSocket session ID
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        entry = {
            "timestamp": timestamp,
            "direction": "receive",
            "message_type": "invalid_tool_call",
            "session_id": session_id,
            "ws_session_id": ws_session_id,
            "content": {
                "tool_name": tool_name,
                "arguments": arguments,
                "error": error,
            },
        }

        self._write_to_file(entry)

        # Also output to terminal
        self._write_to_terminal(
            f"[warn] INVALID TOOL CALL: {tool_name} - {error}",
            severity="WARNING"
        )

    def log_field_update_rejected(
        self,
        field_id: str,
        reason: str,
        session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
    ) -> None:
        """
        Log a rejected field update (also output to terminal).

        Args:
            field_id: Field that was rejected
            reason: Rejection reason
            session_id: Optional session ID
            ws_session_id: Optional WebSocket session ID
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        entry = {
            "timestamp": timestamp,
            "message_type": "field_update_rejected",
            "session_id": session_id,
            "ws_session_id": ws_session_id,
            "content": {
                "field_id": field_id,
                "reason": reason,
            },
        }

        self._write_to_file(entry)

        # Also output to terminal
        self._write_to_terminal(
            f"[warn] FIELD UPDATE REJECTED: {field_id} - {reason}",
            severity="WARNING"
        )

    def log_error(
        self,
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        ws_session_id: Optional[str] = None,
    ) -> None:
        """
        Log an error (always output to terminal).

        Args:
            error_type: Type of error
            error_message: Error description
            context: Additional context
            session_id: Optional session ID
            ws_session_id: Optional WebSocket session ID
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        entry = {
            "timestamp": timestamp,
            "message_type": "error",
            "session_id": session_id,
            "ws_session_id": ws_session_id,
            "content": {
                "error_type": error_type,
                "error_message": error_message,
                "context": context or {},
            },
        }

        self._write_to_file(entry)

        # Always output errors to terminal
        self._write_to_terminal(
            f"[error] ERROR [{error_type}]: {error_message}",
            severity="ERROR"
        )


# Global dev logger instance
_dev_logger: Optional[DevFileLogger] = None


def get_dev_logger() -> DevFileLogger:
    """
    Get or create the global dev file logger instance.

    Returns:
        DevFileLogger instance
    """
    global _dev_logger
    if _dev_logger is None:
        _dev_logger = DevFileLogger()
    return _dev_logger
