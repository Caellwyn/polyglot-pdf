"""
Development-friendly logging utility for debugging Gemini tool calls.

This module provides clear, readable logging for tool calls and responses
that is easy to read during development, while keeping production logs
structured and compliant.

Usage:
    from backend.utils.dev_logger import log_tool_call, log_tool_response
    
    # In tool call handler:
    log_tool_call(tool_name, arguments)
    
    # Before returning:
    log_tool_response(tool_name, response)
"""

import json
import os
from typing import Any, Dict, Optional
from datetime import datetime


# Enable dev logging via environment variable (defaults to FALSE for production safety)
# Set VFF_DEV_LOGGING=true in your local .env to enable detailed tool call logging
DEV_LOGGING_ENABLED = os.getenv("VFF_DEV_LOGGING", "false").lower() in ("true", "1", "yes")


def _format_json(obj: Any, indent: int = 2) -> str:
    """Format object as indented JSON, handling non-serializable objects."""
    try:
        return json.dumps(obj, indent=indent, default=str)
    except Exception:
        return repr(obj)


def _print_separator(char: str = "=", width: int = 100):
    """Print a separator line."""
    print(char * width)


def log_tool_call(tool_name: str, arguments: Dict[str, Any], session_id: Optional[str] = None):
    """
    Log a tool call from Gemini in a readable format.
    
    Args:
        tool_name: Name of the tool being called
        arguments: Arguments dictionary
        session_id: Optional session ID for context
    """
    if not DEV_LOGGING_ENABLED:
        return
    
    timestamp = datetime.utcnow().strftime("%H:%M:%S.%f")[:-3]
    
    _print_separator("=")
    print(f"🔧 GEMINI TOOL CALL [{timestamp}]")
    if session_id:
        print(f"   Session: {session_id}")
    print(f"   Tool: {tool_name}")
    _print_separator("-", 100)
    
    print("📥 ARGUMENTS:")
    print(_format_json(arguments))
    
    _print_separator("=")
    print()  # Blank line for readability


def log_tool_response(tool_name: str, response: Dict[str, Any], session_id: Optional[str] = None):
    """
    Log a tool response being sent back to Gemini.
    
    Args:
        tool_name: Name of the tool that was called
        response: Response dictionary being sent to Gemini
        session_id: Optional session ID for context
    """
    if not DEV_LOGGING_ENABLED:
        return
    
    timestamp = datetime.utcnow().strftime("%H:%M:%S.%f")[:-3]
    
    _print_separator("=")
    print(f"📤 TOOL RESPONSE [{timestamp}]")
    if session_id:
        print(f"   Session: {session_id}")
    print(f"   Tool: {tool_name}")
    _print_separator("-", 100)
    
    print("📤 RESPONSE:")
    print(_format_json(response))
    
    _print_separator("=")
    print()  # Blank line for readability


def log_raw_tool_event(event_name: str, data: Dict[str, Any], session_id: Optional[str] = None):
    """
    Log raw tool-related events (for debugging SDK issues).
    
    Args:
        event_name: Description of the event
        data: Raw data from the event
        session_id: Optional session ID
    """
    if not DEV_LOGGING_ENABLED:
        return
    
    timestamp = datetime.utcnow().strftime("%H:%M:%S.%f")[:-3]
    
    _print_separator("*")
    print(f"🔍 RAW TOOL EVENT [{timestamp}]: {event_name}")
    if session_id:
        print(f"   Session: {session_id}")
    _print_separator("-", 100)
    
    print(_format_json(data))
    
    _print_separator("*")
    print()


def log_tool_error(tool_name: str, error: Exception, arguments: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None):
    """
    Log tool execution errors.
    
    Args:
        tool_name: Name of the tool that errored
        error: The exception that occurred
        arguments: Optional arguments that were passed
        session_id: Optional session ID
    """
    if not DEV_LOGGING_ENABLED:
        return
    
    timestamp = datetime.utcnow().strftime("%H:%M:%S.%f")[:-3]
    
    _print_separator("!")
    print(f"❌ TOOL ERROR [{timestamp}]")
    if session_id:
        print(f"   Session: {session_id}")
    print(f"   Tool: {tool_name}")
    print(f"   Error: {type(error).__name__}: {error}")
    _print_separator("-", 100)
    
    if arguments:
        print("📥 ARGUMENTS (that caused error):")
        print(_format_json(arguments))
    
    _print_separator("!")
    print()


def set_dev_logging(enabled: bool):
    """
    Enable or disable dev logging at runtime.
    
    Args:
        enabled: Whether to enable dev logging
    """
    global DEV_LOGGING_ENABLED
    DEV_LOGGING_ENABLED = enabled
    print(f"🔧 Dev logging {'ENABLED' if enabled else 'DISABLED'}")
