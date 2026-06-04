"""Unit tests for TokenFileLogger wire format.

Locks in two related fixes:
- bd polyglot-pdf-tb7: token events carry the active section id (was always null).
- bd polyglot-pdf-zun: the payload key is section-canonical ("section_id"),
  not the historical "part_id" drift.
"""

import json

import pytest

from backend.utils.token_file_logger import TokenFileLogger


def _log_one_event(logger: TokenFileLogger, *, section_id):
    """Write a single token event with all required kwargs, varying section_id."""
    logger.log_token_event(
        form_id="I-90",
        form_session_id="fs-1",
        gemini_session_id="gs-1",
        prompt_tokens=10,
        response_tokens=5,
        total_tokens=15,
        text_input=10,
        audio_input=0,
        text_output=5,
        audio_output=0,
        text_input_cost=0.0,
        audio_input_cost=0.0,
        text_output_cost=0.0,
        audio_output_cost=0.0,
        total_cost_usd=0.0,
        session_total_tokens=15,
        session_total_cost_usd=0.0,
        session_text_input=10,
        session_audio_input=0,
        session_text_output=5,
        session_audio_output=0,
        section_id=section_id,
    )


def _read_events(log_file):
    with open(log_file, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.fixture
def logger(tmp_path):
    """A TokenFileLogger pointed at an isolated temp log file."""
    log = TokenFileLogger()
    log.log_file = tmp_path / "token_usage.jsonl"
    log.log_file.parent.mkdir(parents=True, exist_ok=True)
    log.log_file.touch()
    return log


def test_event_uses_section_id_key_not_part_id(logger):
    """zun: the payload carries section_id, and no legacy part_id key remains."""
    _log_one_event(logger, section_id="part_1_2_addresses")

    events = _read_events(logger.log_file)
    assert len(events) == 1
    assert events[0]["section_id"] == "part_1_2_addresses"
    assert "part_id" not in events[0]


def test_event_section_id_is_logged_when_provided(logger):
    """tb7: a real (non-null) section id reaches the logged event."""
    _log_one_event(logger, section_id="part_3_eligibility")

    events = _read_events(logger.log_file)
    assert events[0]["section_id"] == "part_3_eligibility"


def test_event_section_id_defaults_to_none(logger):
    """section_id is optional and serializes as null when omitted."""
    logger.log_token_event(
        form_id="I-90",
        form_session_id="fs-1",
        gemini_session_id="gs-1",
        prompt_tokens=1,
        response_tokens=1,
        total_tokens=2,
        text_input=1,
        audio_input=0,
        text_output=1,
        audio_output=0,
        text_input_cost=0.0,
        audio_input_cost=0.0,
        text_output_cost=0.0,
        audio_output_cost=0.0,
        total_cost_usd=0.0,
        session_total_tokens=2,
        session_total_cost_usd=0.0,
        session_text_input=1,
        session_audio_input=0,
        session_text_output=1,
        session_audio_output=0,
    )

    events = _read_events(logger.log_file)
    assert events[0]["section_id"] is None
    assert "part_id" not in events[0]
