"""Tests for the adapter's dev I/O capture helper (bd polyglot-pdf-kbf).

The adapter's `_dev_log_io` captures FULL Gemini message bodies (tool-call args,
tool responses, text turns) to debug unreliable update_form_fields tool calls.
Because those bodies are PII/PHI, the capture MUST be a no-op unless the
backend/.env.DEV marker enables the dev file logger -- it must NEVER reach the
production (Cloud Run) log path. These tests pin both halves of that contract:

  1. dev ON  -> full bodies land in the daily gemini_*.jsonl, with seq + model.
  2. dev OFF -> nothing is written at all.

We drive `_dev_log_io` on a bare object (no live Gemini session needed) by
binding the unbound method to a tiny stand-in that carries the attributes the
helper reads.
"""

import json

import pytest

import backend.utils.dev_file_logger as dev_mod
from backend.adapters.live_ai_gemini import LiveAIGemini


class _Stub:
    """Minimal stand-in carrying just the attributes _dev_log_io reads."""

    _dev_io_seq = 0
    _model_name = "gemini-3.1-flash-live-preview"
    _instance_id = "LiveAI-test"
    _form_session_id = "fss_test_123"

    # Bind the real adapter method onto this stub.
    _dev_log_io = LiveAIGemini._dev_log_io


def _fresh_logger(tmp_path, enabled: bool):
    """Build a DevFileLogger pointed at tmp_path with the given enabled state."""
    logger = dev_mod.DevFileLogger(log_dir=str(tmp_path))
    logger.enabled = enabled
    return logger


def test_dev_io_captures_full_body_when_enabled(tmp_path, monkeypatch):
    logger = _fresh_logger(tmp_path, enabled=True)
    # Patch the name as imported INTO the adapter module (that is the reference
    # _dev_log_io actually calls), not just the source module.
    monkeypatch.setattr("backend.adapters.live_ai_gemini.get_dev_logger", lambda: logger)

    stub = _Stub()
    # A tool response carrying a "field value" (PII) -- exactly what we want in
    # the LOCAL dev log and nowhere near production.
    stub._dev_log_io(
        "send",
        "tool_response",
        {"tool_name": "update_form_fields", "response": {"value": "A123456789"}},
    )
    stub._dev_log_io(
        "receive",
        "tool_call",
        {"tool_name": "update_form_fields", "parsed_arguments": {"field_id": "p1", "value": "Smith"}},
    )

    log_file = logger._get_log_file_path()
    assert log_file.exists(), "dev log file should be written when enabled"
    lines = [json.loads(l) for l in log_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2

    first, second = lines
    # Full bodies are present (this is the point -- local only).
    assert first["content"]["response"] == {"value": "A123456789"}
    assert second["content"]["parsed_arguments"] == {"field_id": "p1", "value": "Smith"}
    # Enrichment: monotonic seq + active model, for timeline reconstruction + A/B.
    assert first["content"]["seq"] == 1
    assert second["content"]["seq"] == 2
    assert first["content"]["model"] == "gemini-3.1-flash-live-preview"
    # Session correlation fields.
    assert first["direction"] == "send"
    assert second["direction"] == "receive"
    assert first["session_id"] == "LiveAI-test"
    assert first["ws_session_id"] == "fss_test_123"


def test_dev_io_is_noop_when_disabled(tmp_path, monkeypatch):
    logger = _fresh_logger(tmp_path, enabled=False)
    # Patch the name as imported INTO the adapter module (that is the reference
    # _dev_log_io actually calls), not just the source module.
    monkeypatch.setattr("backend.adapters.live_ai_gemini.get_dev_logger", lambda: logger)

    stub = _Stub()
    stub._dev_log_io(
        "send",
        "tool_response",
        {"tool_name": "update_form_fields", "response": {"value": "A123456789"}},
    )

    # Disabled logger writes NOTHING -- no file, no PII anywhere.
    log_file = logger._get_log_file_path()
    assert not log_file.exists(), "disabled dev logger must not write any file"
    # And it short-circuits BEFORE doing any work: the seq counter must not even
    # advance in the hot path when logging is off (fresh-eyes / Copilot review).
    assert stub._dev_io_seq == 0, "disabled path must not increment the seq counter"


def test_dev_io_never_raises(tmp_path, monkeypatch):
    """A broken dev logger must never break the live session -- the helper
    swallows all exceptions."""

    class _Boom:
        # MUST be enabled, or _dev_log_io short-circuits before ever calling
        # log_gemini_message and the except-path is never exercised (Copilot
        # review of PR #104). With enabled=True the helper proceeds and we prove
        # it swallows the raised error.
        enabled = True

        def log_gemini_message(self, **kwargs):
            raise RuntimeError("disk full")

    monkeypatch.setattr("backend.adapters.live_ai_gemini.get_dev_logger", lambda: _Boom())
    stub = _Stub()
    # Must not raise despite the logger blowing up...
    stub._dev_log_io("send", "tool_response", {"tool_name": "x", "response": {}})
    # ...and we must have actually reached the failing call (seq advanced past
    # the short-circuit), so the except-path was genuinely exercised.
    assert stub._dev_io_seq == 1
