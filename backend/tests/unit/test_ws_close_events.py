"""Counted WebSocket close events (bd polyglot-pdf-e4dt8 / E3.8).

WHY THIS FILE EXISTS. Cloud Monitoring's log-based metrics
(scripts/setup-monitoring.sh: ws_close_1011_count, ws_close_1013_count) count
log ENTRIES matching a filter, and the alert policies fire on those counts.
That only works if every close produces an entry of ONE shape with the code in
ONE place. Before this bead the /fill route closed eight different ways -- some
lines carried the code, some only a prose reason, some (the schema and source
rejections) nothing at all -- so no single filter could count "the 1013s".

Two things are pinned here, and they fail for different reasons:

  1. THE SHAPE. log_ws_close emits a ws_error event whose metadata carries
     close_code and reason_token, at a severity DERIVED from the code. If the
     shape drifts, the monitoring filters silently match nothing -- the
     failure mode is an alert that never fires, which no other test notices.
  2. THE SET. Every close on the /fill route routes through _close_ws. This is
     the CLAUDE.md scar #8 guard: fixing the eight known sites is not the job,
     pinning the complete set is, so the ninth close added to this route is
     either routed through the wrapper or fails here.
"""
import ast
import json
import pathlib

import pytest

from backend.utils.structured_logger import (
    WS_CLOSE_SEVERITY,
    StructuredLogger,
)


def _repo_root() -> pathlib.Path:
    p = pathlib.Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "backend" / "routes").is_dir():
            return parent
    return p.parent.parent.parent.parent


REPO_ROOT = _repo_root()
WS_ROUTES = REPO_ROOT / "backend" / "routes" / "websocket_routes.py"


def _emitted(capsys) -> dict:
    """The single JSON entry StructuredLogger printed to stdout."""
    out = capsys.readouterr().out.strip()
    assert out, "log_ws_close emitted nothing"
    return json.loads(out.splitlines()[-1])


# The close-code family named by the bead, with the severity each one MUST
# carry, written out HERE rather than read from WS_CLOSE_SEVERITY.
#
# Deriving the expectation from the table under test would be vacuous: flipping
# 1011 to WARNING in the table would flip the expectation with it and every
# assertion would still pass (verified by mutation -- deriving it did exactly
# that). This is the independent statement of intent the table is checked
# against, and it is the WHOLE family, not a sample, so a mutation to any one
# row reddens (memory: mutation-verify per PARAMETRIZATION, not per test).
#
# The reasoning per code lives in StructuredLogger.log_ws_close's docstring;
# the short version is that a Gemini-side drop (1011/1006) is a real failure
# and everything else on this list is expected traffic whose RATE is what
# matters.
EXPECTED_CLOSE_SEVERITY = {
    1006: "ERROR",
    1007: "WARNING",
    1008: "WARNING",
    1011: "ERROR",
    1013: "WARNING",
}


def test_severity_table_matches_the_expected_family():
    """The shipped table IS the expected family -- no more, no less.

    Catches both directions: a severity changed in the table, and a code
    quietly added to or dropped from it (a dropped 1011 would fall to the
    ERROR default and look fine, while the monitoring filter that names the
    code kept counting nothing).
    """
    assert WS_CLOSE_SEVERITY == EXPECTED_CLOSE_SEVERITY, (
        "backend/utils/structured_logger.py's WS_CLOSE_SEVERITY drifted from "
        "the family this bead pins. Shipped: {!r}".format(
            dict(sorted(WS_CLOSE_SEVERITY.items()))))


@pytest.mark.parametrize("code,expected_severity", sorted(
    EXPECTED_CLOSE_SEVERITY.items()))
def test_log_ws_close_shape_per_code(code, expected_severity, capsys):
    """One entry, event_type ws_error, code + token in metadata, right severity."""
    StructuredLogger(client_id="test").log_ws_close(
        close_code=code,
        reason_token="unit_test_token",
        form_session_id="fs-1",
        ws_session_id="ws-1",
    )
    entry = _emitted(capsys)

    assert entry["severity"] == expected_severity, (
        "close code {} logged at severity {} but the WS_CLOSE_SEVERITY table "
        "says {}. The monitoring alert policies filter on severity, so a "
        "mismatch here means the policy sees the wrong population."
        .format(code, entry["severity"], expected_severity))

    msg = entry["message"]
    assert msg["event_type"] == "ws_error", (
        "the monitoring metric filters on event_type=ws_error; got "
        + repr(msg["event_type"]))
    assert msg["metadata"]["close_code"] == code, (
        "close_code must be in metadata at a FIXED key -- the log-based "
        "metric's filter names metadata.close_code exactly")
    assert msg["metadata"]["reason_token"] == "unit_test_token"
    assert msg["form_session_id"] == "fs-1"
    assert msg["ws_session_id"] == "ws-1"


def test_unclassified_close_code_is_error_not_silently_dropped():
    """An unknown code must be LOUD.

    A `.get(code)` returning None would emit severity=None, which Cloud
    Logging rejects or files as DEFAULT -- the entry vanishes from every
    severity-filtered view. Defaulting to ERROR means a code nobody classified
    shows up rather than disappearing.
    """
    assert WS_CLOSE_SEVERITY.get(4999, "ERROR") == "ERROR"


def test_log_ws_close_emits_no_prose_message(capsys):
    """error_message carries the TOKEN, not formatted or user-derived text.

    A close reason assembled from a client-supplied string would be a PII
    vector (docs/standards/hipaa-pii-policy.md). Pinning that the field equals
    the token exactly is what stops a later "improvement" from interpolating
    context into it.
    """
    StructuredLogger(client_id="test").log_ws_close(
        close_code=1013, reason_token="budget_exhausted")
    entry = _emitted(capsys)
    assert entry["message"]["metadata"]["error_message"] == "budget_exhausted"


def test_log_ws_close_preserves_caller_metadata(capsys):
    """Caller metadata survives alongside the two fixed keys.

    The adapter's 1011 event carries event_count and error_type; the route's
    1008 carries not_enrolled. If log_ws_close replaced the caller's dict
    instead of extending it, those would vanish and the only test that noticed
    would be one that looked.
    """
    StructuredLogger(client_id="test").log_ws_close(
        close_code=1011,
        reason_token="gemini_session_dropped",
        metadata={"event_count": 7, "error_type": "APIError"},
    )
    meta = _emitted(capsys)["message"]["metadata"]
    assert meta["event_count"] == 7
    assert meta["error_type"] == "APIError"
    assert meta["close_code"] == 1011


def test_log_ws_close_does_not_mutate_the_callers_dict(capsys):
    """The caller's dict is copied, not written through.

    The adapter builds its metadata dict inline today, but a caller that
    reused one across two closes would find close_code from the FIRST close
    stuck on the second -- a wrong-code entry that the metric would happily
    count.
    """
    caller_dict = {"event_count": 1}
    StructuredLogger(client_id="test").log_ws_close(
        close_code=1006, reason_token="t", metadata=caller_dict)
    capsys.readouterr()
    assert "close_code" not in caller_dict, (
        "log_ws_close wrote into the caller's metadata dict")


# ---------------------------------------------------------------------------
# The SET: every close on /fill goes through _close_ws
# ---------------------------------------------------------------------------

# Closes that legitimately do NOT go through _close_ws, each with the reason.
# An allowlist, not a blacklist: a new close is covered by default and has to
# be argued INTO this set (memory: pin with an allowlist, never a blacklist).
#
# Attribution is by the INNERMOST enclosing function, which is what the AST
# reports and what a reader looking at the line sees. Three of these sit in a
# nested `watchdog_task` -- there are three such closures in this module (two
# on the diagnostic routes, one on /fill), so the CODE is what separates them.
_UNCOUNTED_CLOSES = {
    # /ws/echo and /ws/audio are DIAGNOSTIC routes, not the product socket.
    # They take no schema, no link and no form session; a 1008 there means an
    # operator poked a debug endpoint without a token. Counting them would mix
    # operator traffic into the client-facing close metrics.
    ("ws_echo", 1008),
    ("ws_audio", 1008),
    # 1001 ("going away") from a diagnostic route's ping watchdog -- same
    # reasoning as the 1008s above.
    ("watchdog_task", 1001),
    # 1000 is a NORMAL close. The /fill idle timeout is the socket working as
    # designed; a metric counting it would fire on every healthy session that
    # went quiet.
    ("watchdog_task", 1000),
}


def _close_calls():
    """Every `*.close(code=...)` call under websocket_routes.py, by function.

    AST-derived rather than grepped so the enclosing function name is real
    (a grep would have to guess it from indentation) and so a multi-line call
    is not missed.
    """
    tree = ast.parse(WS_ROUTES.read_text(encoding="utf-8"))
    found = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def _visit_fn(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_FunctionDef = _visit_fn
        visit_AsyncFunctionDef = _visit_fn

        def visit_Call(self, node):
            is_close = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "close"
            )
            if is_close:
                code = None
                for kw in node.keywords:
                    if kw.arg == "code" and isinstance(kw.value, ast.Constant):
                        code = kw.value.value
                found.append((
                    self.stack[-1] if self.stack else "<module>",
                    code,
                    node.lineno,
                ))
            self.generic_visit(node)

    V().visit(tree)
    return found


def test_the_close_enumeration_actually_finds_calls():
    """Guard the guard: an empty enumeration would pass the next test forever."""
    calls = _close_calls()
    assert len(calls) >= 5, (
        "the AST walk found only {} close() call(s) in websocket_routes.py -- "
        "the walk is probably broken, not the route".format(len(calls)))


def test_every_fill_close_routes_through_the_counted_wrapper():
    """The SET (CLAUDE.md scar #8).

    A close added to the /fill route with a bare `websocket.close(code=...)`
    fails HERE. That is the moment to route it through _close_ws (or to argue
    it into _UNCOUNTED_CLOSES with a reason), rather than after it has shipped
    a close the monitoring metrics cannot see.
    """
    offenders = []
    for fn, code, lineno in _close_calls():
        # The two calls INSIDE _close_ws are the wrapper's own; it is what
        # every other site delegates to.
        if fn == "_close_ws":
            continue
        if (fn, code) in _UNCOUNTED_CLOSES:
            continue
        offenders.append("{}:{} in {}() closes with code {}".format(
            WS_ROUTES.name, lineno, fn, code))

    assert not offenders, (
        "close(code=...) call(s) on websocket_routes.py that do not go "
        "through _close_ws, so Cloud Monitoring's log-based metrics never "
        "see them:\n  " + "\n  ".join(offenders)
        + "\nRoute them through _close_ws, or add (function, code) to "
          "_UNCOUNTED_CLOSES in this file with the reason it should not be "
          "counted.")


def test_uncounted_allowlist_has_no_stale_entries():
    """A retired close must leave the allowlist too.

    Otherwise the allowlist grows into a blanket exemption: a future close in
    a function that once had an exempt one inherits the exemption silently.
    """
    actual = {(fn, code) for fn, code, _ in _close_calls()}
    stale = _UNCOUNTED_CLOSES - actual
    assert not stale, (
        "_UNCOUNTED_CLOSES names close(s) that no longer exist: "
        + ", ".join(sorted("{}/{}".format(f, c) for f, c in stale)))
