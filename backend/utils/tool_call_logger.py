"""Tool call logging utility for tracking Gemini Live API tool invocations."""

import json
import os
from datetime import datetime


def _ensure_logs_dir() -> str | None:
    """Ensure the .logs directory exists and return its path."""
    try:
        logs_dir = os.path.join(os.getcwd(), ".logs")
        os.makedirs(logs_dir, exist_ok=True)
        return logs_dir
    except Exception:
        return None


def append_tool_call_log(entry: dict) -> None:
    """
    Append a tool call log entry to the gemini_tool_calls.log file.
    
    Args:
        entry: Dictionary containing tool call information to log
    """
    try:
        logs_dir = _ensure_logs_dir()
        if not logs_dir:
            return
        path = os.path.join(logs_dir, "gemini_tool_calls.log")
        ts = datetime.utcnow().isoformat() + "Z"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(ts + " " + json.dumps(entry, default=str) + "\n")
    except Exception:
        pass
