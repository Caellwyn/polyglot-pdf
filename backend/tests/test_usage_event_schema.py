"""Every usage_kind emits the FULL usage-event key set (bd polyglot-pdf-wio6m).

WHY THIS FILE EXISTS. Usage event v2 collapses three paid call paths -- Gemini
Live, plain generate_content, and Cloud Text-to-Speech -- onto ONE event shape
so the Cloud Logging -> BigQuery sink sees one column shape instead of three.
That only holds if every wrapper emits every key. At the sink a MISSING key and
a NULL are different things: a row that simply omits firm_id drops silently out
of a GROUP BY on firm_id, so a per-firm cost total under-reports with no error
anywhere. A null row shows up as a null and is queryable.

So the property under test is not "the emitter works" -- it is "no wrapper can
quietly stop writing a key". The keys are derived from
log_schemas.USAGE_CONTEXT_KEYS, never hand-listed here, so adding a key to the
envelope without wiring it into the emitter fails this test rather than shipping
a column that is present on some rows only (scar #8: pin the SET).
"""

import json

import pytest

from backend.utils.log_schemas import USAGE_CONTEXT_KEYS, UsageKind
from backend.utils.structured_logger import StructuredLogger

try:  # py3.8+ runtime access to a Literal's members
    from typing import get_args
except ImportError:  # pragma: no cover
    from typing_extensions import get_args


# DERIVED from the closed Literal, not typed out again: a new usage_kind is
# covered by this test the day it is added to the schema.
ALL_USAGE_KINDS = get_args(UsageKind)

# usage_kind is part of the required key set too -- it is what distinguishes the
# paths now that they share one shape, so a row without it is unattributable.
REQUIRED_KEYS = frozenset(USAGE_CONTEXT_KEYS) | {"usage_kind"}


def _emitted(capsys):
    """Parse the single JSON line the logger printed to stdout."""
    out = capsys.readouterr().out.strip()
    assert out, "logger emitted nothing"
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected exactly one log line, got {len(lines)}"
    return json.loads(lines[0])["message"]


def _call_wrapper(logger, usage_kind):
    """Invoke the wrapper that owns this usage_kind, with NO context ids.

    Deliberately passes no firm_id/employee_id/link_jti/kit_id/channel/model:
    the whole claim is that the keys appear even when the caller has no values
    for them, which is exactly the state the paths are in before beads
    polyglot-pdf-cjifh and polyglot-pdf-t86oz plumb the ids through.
    """
    if usage_kind == "live_voice":
        logger.log_gemini_api_response(
            form_id="i-90",
            form_version="1",
            form_session_id="fs-1",
            ws_session_id="ws-1",
            metadata={"total_token_count": 10},
        )
    elif usage_kind.startswith("text_"):
        logger.log_text_ai_usage(usage_kind=usage_kind,
                                 metadata={"total_token_count": 10})
    elif usage_kind.startswith("tts_"):
        logger.log_tts_usage(usage_kind=usage_kind,
                             metadata={"character_count": 10})
    else:  # pragma: no cover - a new prefix must be routed deliberately
        raise AssertionError(
            f"usage_kind {usage_kind!r} matches no wrapper; add a branch here "
            "when a new paid path is introduced"
        )


def test_every_usage_kind_is_routed():
    """No usage_kind is orphaned: each maps to exactly one wrapper.

    Guards the helper above -- without this, a new kind whose prefix matches
    nothing would make every parametrized case below error rather than fail
    with a readable reason.
    """
    for kind in ALL_USAGE_KINDS:
        assert (kind == "live_voice"
                or kind.startswith("text_")
                or kind.startswith("tts_")), f"unrouted usage_kind: {kind}"


@pytest.mark.parametrize("usage_kind", ALL_USAGE_KINDS)
def test_wrapper_emits_full_key_set(usage_kind, capsys):
    """Every wrapper writes every envelope key, values allowed to be None."""
    _call_wrapper(StructuredLogger(), usage_kind)
    metadata = _emitted(capsys)["metadata"]

    missing = REQUIRED_KEYS - set(metadata)
    assert not missing, (
        f"usage_kind {usage_kind!r} omitted {sorted(missing)}. A missing key is "
        "not a null at the BigQuery sink -- these rows would vanish from a "
        "GROUP BY on the omitted column."
    )


@pytest.mark.parametrize("usage_kind", ALL_USAGE_KINDS)
def test_wrapper_stamps_its_own_usage_kind(usage_kind, capsys):
    """The emitted usage_kind is the one the caller asked for.

    Pins the ATTRIBUTION, not just the presence of the key: a wrapper that
    hard-coded one kind for every call would pass the key-set test above while
    making every text row look like a validator row.
    """
    _call_wrapper(StructuredLogger(), usage_kind)
    metadata = _emitted(capsys)["metadata"]
    assert metadata["usage_kind"] == usage_kind


@pytest.mark.parametrize("usage_kind", ALL_USAGE_KINDS)
def test_context_keys_default_to_none_not_absent(usage_kind, capsys):
    """With no ids supplied, the context keys are present AND null.

    The complement of the key-set test: it would also pass if the emitter
    invented placeholder strings. Nulls are what the sink needs; a fabricated
    id would silently corrupt per-firm attribution.
    """
    _call_wrapper(StructuredLogger(), usage_kind)
    metadata = _emitted(capsys)["metadata"]
    for key in USAGE_CONTEXT_KEYS:
        assert metadata[key] is None, (
            f"{usage_kind}: expected {key} to be null when unsupplied, "
            f"got {metadata[key]!r}"
        )


def test_context_ids_round_trip_when_supplied():
    """Supplied ids reach the event unchanged (the beads 2/3 contract)."""
    logger = StructuredLogger()
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        logger.log_text_ai_usage(
            usage_kind="text_secretary",
            metadata={"total_token_count": 5},
            firm_id="firm-1",
            employee_id="emp-1",
            link_jti="jti-1",
            kit_id="i-90",
            channel="staging",
            model="gemini-2.5-flash-lite",
        )
    metadata = json.loads(buf.getvalue().strip())["message"]["metadata"]
    assert metadata["firm_id"] == "firm-1"
    assert metadata["employee_id"] == "emp-1"
    assert metadata["link_jti"] == "jti-1"
    assert metadata["kit_id"] == "i-90"
    assert metadata["channel"] == "staging"
    assert metadata["model"] == "gemini-2.5-flash-lite"


def test_metadata_cannot_shadow_envelope_keys(capsys):
    """A stray metadata entry never overrides an envelope key.

    The emitter writes counts first and the envelope on top, so a caller that
    happens to put "model" or "usage_kind" in its metadata dict cannot mislabel
    the row. Without the ordering, a caller's leftover key would win.
    """
    StructuredLogger().log_tts_usage(
        usage_kind="tts_notice",
        metadata={"usage_kind": "text_validator", "model": "wrong", "firm_id": "wrong"},
        model="en-US-Chirp3-HD-Algieba",
        firm_id="firm-real",
    )
    metadata = _emitted(capsys)["metadata"]
    assert metadata["usage_kind"] == "tts_notice"
    assert metadata["model"] == "en-US-Chirp3-HD-Algieba"
    assert metadata["firm_id"] == "firm-real"


def test_no_free_text_slot_in_the_envelope():
    """The envelope has no slot for a value or transcript (HIPAA by shape).

    Pins the PII property structurally rather than by grepping call sites: if
    someone adds a "text"/"value"/"transcript" context key, this fails here
    before backend/tests/test_no_pii_logging.py has to catch it downstream.
    """
    forbidden = {"value", "text", "transcript", "content", "prompt", "message"}
    overlap = forbidden & set(USAGE_CONTEXT_KEYS)
    assert not overlap, (
        f"usage envelope grew a free-text key: {sorted(overlap)}. Usage events "
        "carry ids, counts, costs and model names only."
    )
