"""Unit tests for StructuredLogger stdout emit (Cloud Logging jsonPayload).

Locks in bd polyglot-pdf-5c2h: the per-turn token event emits as one structured
JSON line to stdout (event_type "gemini_api_response") so a deployed run's per-turn
token burn survives as queryable jsonPayload -- not just the human-readable print()
block. Also guards the HIPAA invariant: the envelope has no field-value slot, so no
PII can ride along.
"""

import io
import json
from contextlib import redirect_stdout

from backend.utils.structured_logger import StructuredLogger


def _emit_token_event(logger, **overrides):
    """Drive log_gemini_api_response with a representative token metadata block."""
    metadata = {
        "prompt_token_count": 1200,
        "candidates_token_count": 40,
        "total_token_count": 1240,
        "text_input": 1150,
        "audio_input": 50,
        "text_output": 40,
        "audio_output": 0,
        "text_input_cost_usd": 0.000575,
        "audio_input_cost_usd": 0.00015,
        "text_output_cost_usd": 0.00008,
        "audio_output_cost_usd": 0.0,
        "cost_estimate_usd": 0.000805,
        "session_tokens_so_far": 1240,
        "session_cost_so_far_usd": 0.000805,
        "section_id": "part_1_2_addresses",
    }
    metadata.update(overrides)
    buf = io.StringIO()
    with redirect_stdout(buf):
        logger.log_gemini_api_response(
            form_id="I-90",
            form_version="",
            form_session_id="fs-1",
            ws_session_id="gs-1",
            metadata=metadata,
            section_number=None,
        )
    return buf.getvalue()


def test_token_event_emits_single_cloud_logging_line():
    """One call -> exactly one JSON line in the Cloud Run / BigQuery envelope."""
    out = _emit_token_event(StructuredLogger(client_id="demo"))
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    # Cloud Run envelope: severity + timestamp + message.
    assert entry["severity"] == "INFO"
    assert "timestamp" in entry
    msg = entry["message"]
    assert msg["event_type"] == "gemini_api_response"
    assert msg["source"] == "backend"
    assert msg["client_id"] == "demo"


def test_token_event_carries_counts_and_costs():
    """Per-modality counts, per-turn + session costs all survive to the payload."""
    out = _emit_token_event(StructuredLogger(client_id="demo"))
    msg = json.loads(out.splitlines()[0])["message"]
    assert msg["form_id"] == "I-90"
    assert msg["form_session_id"] == "fs-1"
    assert msg["ws_session_id"] == "gs-1"
    meta = msg["metadata"]
    assert meta["total_token_count"] == 1240
    assert meta["text_input"] == 1150
    assert meta["audio_input"] == 50
    assert meta["cost_estimate_usd"] == 0.000805
    assert meta["session_tokens_so_far"] == 1240
    assert meta["section_id"] == "part_1_2_addresses"


def test_token_event_carries_no_field_value():
    """HIPAA guard: no 'value' slot anywhere in the emitted event."""
    out = _emit_token_event(StructuredLogger(client_id="demo"))
    entry = json.loads(out.splitlines()[0])
    # The whole serialized line must not contain a field-value key.
    assert "\"value\"" not in out
    assert "value" not in entry["message"]
    assert "value" not in entry["message"]["metadata"]
