"""Unit tests for the bd polyglot-pdf-jnjj.39 harness debug helpers.

These are PURE functions in scripts/spikes/measure_form_session_costs.py -- the
timestamp-window tool attribution, the transcript-chunk joiner, and the JSON-safe
coercer. No live Gemini, no audio, no network. Criterion 2 of jnjj.39 (reliable
attribution) is demonstrated here: the window method attributes a tool call to the
RIGHT question even when it lands after the loop's mutable counter moved on -- the
exact failure mode of the legacy per_question_tools that started the jnjj.38 saga.
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# numpy import lives at module top of the spike; skip cleanly if the spike's deps
# are absent in this environment (it is a spike, not core).
pytest.importorskip("numpy")
from scripts.spikes.measure_form_session_costs import (  # noqa: E402
    attribute_tools_by_window,
    _chunks_in_window,
    _jsonable,
)


def test_window_attribution_buckets_call_by_timestamp():
    """A tool call's timestamp -- not the loop counter -- decides its question."""
    windows = [
        {"q": 1, "t_start": 0.0, "t_end": 10.0},
        {"q": 2, "t_start": 12.0, "t_end": 22.0},
    ]
    tool_io = [
        {"ts": 5.0, "tool": "update_form_fields"},   # inside q1
        {"ts": 15.0, "tool": "confirm_field"},        # inside q2
    ]
    assert attribute_tools_by_window(tool_io, windows) == {
        "1": ["update_form_fields"],
        "2": ["confirm_field"],
    }


def test_window_attribution_beats_legacy_on_late_call():
    """The jnjj.38 failure mode: a call the LOOP attributed to a later question
    (because it stamped current_q after advancing) belongs, by timestamp, to the
    question whose window it actually fell in. A call AFTER the last window's end
    attributes to that last passed window (not dropped)."""
    windows = [
        {"q": 1, "t_start": 0.0, "t_end": 10.0},
        {"q": 2, "t_start": 12.0, "t_end": 22.0},
    ]
    # This call lands at ts=24, AFTER q2's window closed -- the model was slow. The
    # legacy counter (already on q3 by now) would mis-stamp it; the window method
    # attributes it to q2 (the last window it passed), never silently drops it.
    tool_io = [{"ts": 24.0, "tool": "update_form_fields"}]
    assert attribute_tools_by_window(tool_io, windows) == {"2": ["update_form_fields"]}


def test_window_attribution_pre_q1_is_q0():
    """A call before q1's window (the greeting turn) buckets to q0, not q1."""
    windows = [{"q": 1, "t_start": 5.0, "t_end": 10.0}]
    assert attribute_tools_by_window([{"ts": 1.0, "tool": "x"}], windows) == {"0": ["x"]}


def test_chunks_joined_in_window_only():
    """Transcript chunks inside the window join in order; outside are excluded."""
    chunks = [
        {"ts": 1.0, "text": "Hel"},
        {"ts": 2.0, "text": "lo"},
        {"ts": 99.0, "text": " later"},
    ]
    assert _chunks_in_window(chunks, {"t_start": 0.0, "t_end": 10.0}) == "Hello"


def test_jsonable_coerces_non_serializable():
    """A stray non-JSON value is coerced to repr, never raised -- the debug write
    must not crash on an unexpected tool-arg type."""
    class _Sentinel:
        pass

    out = _jsonable({"ok": 1, "bad": _Sentinel(), "nested": [_Sentinel()]})
    assert out["ok"] == 1
    assert isinstance(out["bad"], str)        # coerced to repr
    assert isinstance(out["nested"][0], str)  # recursed into the list
    import json
    json.dumps(out)  # must now be serializable
