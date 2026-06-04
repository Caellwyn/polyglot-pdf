"""
Token usage file logger for local development.

Logs token events to backend/logs/token_usage.jsonl for visualization dashboard.
NOT used in production - BigQuery will handle that.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class TokenFileLogger:
    """Logs token usage events to a JSONL file for local monitoring."""

    def __init__(self, log_dir: str = "backend/logs"):
        """
        Initialize token file logger.

        Args:
            log_dir: Directory for log files (relative to project root)
        """
        # Get project root (3 levels up from this file: utils -> backend -> project)
        project_root = Path(__file__).parent.parent.parent
        self.log_file = project_root / log_dir / "token_usage.jsonl"

        # Create logs directory if it doesn't exist
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Create file if it doesn't exist
        if not self.log_file.exists():
            self.log_file.touch()

    def log_token_event(
        self,
        *,
        # Session identifiers
        form_id: str,
        form_session_id: str,
        gemini_session_id: str,

        # Token counts
        prompt_tokens: int,
        response_tokens: int,
        total_tokens: int,

        # Modality breakdown
        text_input: int,
        audio_input: int,
        text_output: int,
        audio_output: int,

        # Costs
        text_input_cost: float,
        audio_input_cost: float,
        text_output_cost: float,
        audio_output_cost: float,
        total_cost_usd: float,

        # Session cumulative
        session_total_tokens: int,
        session_total_cost_usd: float,
        session_text_input: int,
        session_audio_input: int,
        session_text_output: int,
        session_audio_output: int,

        # Optional context
        section_id: Optional[str] = None,
        event_type: str = "token_usage",
    ) -> None:
        """
        Log a token usage event to the JSONL file.

        Args:
            form_id: Form identifier (e.g., "I-90")
            form_session_id: Overall form filling session ID (persists across Gemini sessions)
            gemini_session_id: Specific Gemini session ID
            prompt_tokens: Tokens in the prompt
            response_tokens: Tokens in the response
            total_tokens: Total tokens for this event
            text_input: Text input tokens
            audio_input: Audio input tokens
            text_output: Text output tokens
            audio_output: Audio output tokens
            text_input_cost: Cost for text input
            audio_input_cost: Cost for audio input
            text_output_cost: Cost for text output
            audio_output_cost: Cost for audio output
            total_cost_usd: Total cost in USD
            session_total_tokens: Cumulative tokens for this Gemini session
            session_total_cost_usd: Cumulative cost for this Gemini session
            session_text_input: Cumulative text input tokens for this session
            session_audio_input: Cumulative audio input tokens for this session
            session_text_output: Cumulative text output tokens for this session
            session_audio_output: Cumulative audio output tokens for this session
            section_id: Current section ID (the user-facing navigation unit, e.g. "part_1_2_addresses")
            event_type: Event type (default: "token_usage")
        """
        event = {
            # Metadata
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),

            # Identifiers
            "form_id": form_id,
            "form_session_id": form_session_id,
            "gemini_session_id": gemini_session_id,
            "section_id": section_id,

            # This event's token counts
            "event": {
                "prompt_tokens": prompt_tokens,
                "response_tokens": response_tokens,
                "total_tokens": total_tokens,
                "text_input": text_input,
                "audio_input": audio_input,
                "text_output": text_output,
                "audio_output": audio_output,
            },

            # This event's costs
            "cost": {
                "text_input_usd": round(text_input_cost, 8),
                "audio_input_usd": round(audio_input_cost, 8),
                "text_output_usd": round(text_output_cost, 8),
                "audio_output_usd": round(audio_output_cost, 8),
                "total_usd": round(total_cost_usd, 8),
            },

            # Cumulative session totals
            "session_cumulative": {
                "total_tokens": session_total_tokens,
                "total_cost_usd": round(session_total_cost_usd, 8),
                "text_input": session_text_input,
                "audio_input": session_audio_input,
                "text_output": session_text_output,
                "audio_output": session_audio_output,
            },
        }

        # Append to JSONL file (newline-delimited JSON)
        # Write atomically to prevent partial reads by file watcher
        try:
            # Serialize to string first, then write in one operation
            line = json.dumps(event, ensure_ascii=False) + '\n'
            with open(self.log_file, 'a', encoding='utf-8', buffering=1) as f:
                f.write(line)
                f.flush()  # Force write to disk immediately
        except Exception as e:
            # Silently fail - don't crash the app over logging
            print(f"[TokenFileLogger] Failed to write event: {e}")

    def clear_log(self) -> None:
        """Clear the token usage log file."""
        if self.log_file.exists():
            self.log_file.write_text('')


# Global instance for easy access
_token_logger: Optional[TokenFileLogger] = None


def get_token_logger() -> TokenFileLogger:
    """Get or create the global token logger instance."""
    global _token_logger
    if _token_logger is None:
        _token_logger = TokenFileLogger()
    return _token_logger
