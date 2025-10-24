"""
Development file logger for Gemini API messages and tool calls.

Writes detailed logs to daily .jsonl files in backend/logs/ for analysis.
Only active when VFF_DEV_LOGGING=true.

Files are named: gemini_YYYY-MM-DD.jsonl
Format: One JSON object per line for easy DataFrame loading
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


# Check if dev logging is enabled
DEV_LOGGING_ENABLED = os.getenv("VFF_DEV_LOGGING", "false").lower() in ("true", "1", "yes")


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
            print(f"⚠️  Dev file logger error: {e}", file=sys.stderr)

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
            f"⚠️  INVALID TOOL CALL: {tool_name} - {error}",
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
            f"⚠️  FIELD UPDATE REJECTED: {field_id} - {reason}",
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
            f"❌ ERROR [{error_type}]: {error_message}",
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
