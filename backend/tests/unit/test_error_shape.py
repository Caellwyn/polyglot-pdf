"""The PII-safe exception shape that reaches Cloud Error Reporting.

WHY THIS FILE EXISTS. A P0 PII decision (bd polyglot-pdf-p84m) established
that structlog's stock format_exc_info processor cannot run on any production
path in this app: it renders the exception MESSAGE into the JSON "exception"
field, and in a form-filling app that message routinely embeds a field VALUE
(an A-number, a date of birth, a name). The response at the time was local:
two call sites in backend/adapters/live_ai_gemini.py were rewritten to log
error_type=type(e).__name__ and to gate self._log.exception(...) behind
DEV_LOGGING_ENABLED, while every OTHER .exception() / exc_info=True site under
backend/ kept rendering the message straight into Cloud Logging.

That is the CLAUDE.md scar #8 shape exactly -- one instance of a set fixed,
the set left un-enumerated. This file pins the SET instead of the instance,
in two halves:

  1. The runtime half. An exception whose message carries a sentinel goes
     through the PRODUCTION processor chain; the rendered line must carry the
     exception TYPE and the FRAMES (file, line, function) and must NOT carry
     the sentinel anywhere.
  2. The structural half. Every .exception(...) / exc_info=True site under
     backend/ is enumerated from the AST and checked against the register in
     backend/utils/logging.py -- so adding a new site is VISIBLE, and swapping
     the processor back is caught by its own test.

WHY FRAMES AT ALL. Cloud Error Reporting groups errors by the stack trace
shape. A bare error_type=... line (the 2026-06 local fix) is PII-safe but
ungroupable -- Error Reporting shows nothing, and the operator is back to
grepping Cloud Logging by hand. Frames without the message give grouping AND
a debuggable location while carrying no user data: a file path, a line number
and a function name are all repository facts.
"""
import ast
import io
import json
import logging
import pathlib

import pytest
import structlog

from backend.utils.logging import (
    EXCEPTION_LOGGING_SITES,
    configure_logging,
    pii_safe_exception_info,
)


def _repo_root() -> pathlib.Path:
    p = pathlib.Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "backend" / "routes").is_dir():
            return parent
    return p.parent.parent.parent.parent


REPO_ROOT = _repo_root()

# The sentinel stands in for a field value. It is deliberately a string no
# other part of the repo contains, so "absent from the output" is a real
# assertion and not an accident of the renderer.
SENTINEL = "A-123-456-789-SENTINEL-PII"

# A SECOND sentinel that appears in this file's SOURCE TEXT on the raising
# line, and nowhere in the exception message. Its only route into a log is a
# renderer that prints the frame's source line -- which is a real leak shape
# here, because a raise like
#   raise ValueError("alien number " + a_number)
# has the value in a local, while
#   raise ValueError("rejected A-123-456-789")
# has it in the source. Pinning both closes the door on both.
SOURCE_SENTINEL = "SRC-987-654-321-SENTINEL-PII"


def _raise_with_sentinel():
    """A real raise, so the traceback has real frames from a real file."""
    raise ValueError("failed to parse alien number " + SENTINEL)


def _raise_with_sentinel_in_the_source_line():
    """The sentinel is a LITERAL on the RAISING line, not in the message.

    The exception's own message is clean, so a message-scrubbing renderer
    passes this case while a renderer that also prints the frame's SOURCE
    text leaks the literal. The two are different failures; this function
    exists to separate them.
    """
    field_label = "SRC-987-654-321-SENTINEL-PII"; raise KeyError(field_label[:3])


@pytest.fixture
def capture_root_stream():
    """Capture what the root logging handler actually WRITES.

    Asserting on the real handler output (rather than on a structlog capture
    processor) is the point: the leak this file guards happens at RENDER time,
    in the processor chain configure_logging() installs, and a capture
    processor inserted mid-chain would short-circuit exactly the step under
    test.
    """
    stream = io.StringIO()
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level

    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.handlers = [handler]
    root.setLevel(logging.DEBUG)

    # configure_logging() calls basicConfig, which is a no-op when the root
    # already has a handler -- so our capture handler survives the call and
    # receives the rendered lines.
    try:
        yield stream
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
        # Drop the cached bound logger so the next test's configure_logging()
        # is actually honoured (cache_logger_on_first_use=True otherwise pins
        # the first chain for the whole process).
        structlog.reset_defaults()


def test_exception_processor_emits_frames_without_the_message(capture_root_stream):
    """RED BEFORE THE FIX: structlog.processors.format_exc_info renders the
    exception message into the "exception" field, so the sentinel appears in
    the output. GREEN AFTER: the PII-safe processor renders type + frames.

    Both halves are asserted, not just the absence half. A processor that
    emitted NOTHING would pass a message-absent assertion while destroying the
    error reporting this bead exists to build.
    """
    configure_logging()
    log = structlog.get_logger("test_error_shape")

    try:
        _raise_with_sentinel()
    except ValueError:
        log.exception("unit_test_exception_shape")

    rendered = capture_root_stream.getvalue()
    assert rendered.strip(), "nothing was logged at all"

    # The sentinel (a stand-in for a field value) must appear NOWHERE.
    assert SENTINEL not in rendered, (
        "the exception MESSAGE reached the rendered log line -- this is the "
        "P0 PII leak (bd polyglot-pdf-p84m). Rendered: " + rendered)

    payload = json.loads(rendered.strip().splitlines()[-1])

    # Cloud Error Reporting groups on a stack_trace-shaped field plus an
    # uppercase severity. Both must be present or the error never appears in
    # the Error Reporting console at all.
    assert payload.get("severity") == "ERROR", (
        "severity must be present and UPPERCASE for Cloud Error Reporting to "
        "pick the entry up; got " + repr(payload.get("severity")))
    assert "stack_trace" in payload, (
        "no stack_trace field -- Error Reporting has nothing to group on")

    stack_trace = payload["stack_trace"]
    assert "ValueError" in stack_trace, (
        "the exception TYPE is missing from stack_trace: " + stack_trace)
    assert "_raise_with_sentinel" in stack_trace, (
        "the raising FUNCTION is missing from stack_trace: " + stack_trace)
    assert "test_error_shape.py" in stack_trace, (
        "the raising FILE is missing from stack_trace: " + stack_trace)

    # The exception type is also emitted as its own queryable field, so a
    # Cloud Logging filter can count by type without parsing the trace.
    assert payload.get("error_type") == "ValueError", (
        "error_type field missing or wrong: " + repr(payload.get("error_type")))


def test_processor_emits_no_locals_and_no_source_lines(capture_root_stream):
    """Frames only: file, line, function. Never locals, never source text.

    A traceback rendering that includes source LINES would re-open the leak by
    a different door: the raising line here is `raise RuntimeError(secret)`,
    whose source text does not contain the value, but the VALUE sits in a
    local. Renderers that include locals (e.g. rich tracebacks) would print
    it. Pin the shape, not one example.
    """
    configure_logging()
    log = structlog.get_logger("test_error_shape")

    local_only_secret = SENTINEL

    try:
        raise RuntimeError(local_only_secret)
    except RuntimeError:
        log.exception("unit_test_no_locals")

    rendered = capture_root_stream.getvalue()
    assert SENTINEL not in rendered, (
        "a LOCAL variable's value reached the log -- the renderer is emitting "
        "locals or source text, not just frames. Rendered: " + rendered)
    payload = json.loads(rendered.strip().splitlines()[-1])
    assert "RuntimeError" in payload["stack_trace"]


def test_processor_emits_no_frame_source_text(capture_root_stream):
    """The frame's SOURCE LINE must not be rendered either.

    Separate from the locals test above, and it has to be: rendering
    `FrameSummary.line` (the "make it look like a real traceback" change) does
    NOT trip the locals assertion, because in that test the value lives only
    in a local and the source text is clean. Here the sentinel is a LITERAL on
    the raising line and the message is clean, so this is the only assertion
    that catches it. Verified by mutation: adding f.line to the rendered frame
    reddens THIS test and nothing else.
    """
    configure_logging()
    log = structlog.get_logger("test_error_shape")

    try:
        _raise_with_sentinel_in_the_source_line()
    except KeyError:
        log.exception("unit_test_no_source_text")

    rendered = capture_root_stream.getvalue()
    assert SOURCE_SENTINEL not in rendered, (
        "the raising line's SOURCE TEXT reached the log. Frames must carry "
        "file, line and function only -- a source literal is as much a leak "
        "as the message. Rendered: " + rendered)
    payload = json.loads(rendered.strip().splitlines()[-1])
    # Still a usable trace: the function name is there even though the line
    # text is not.
    assert "_raise_with_sentinel_in_the_source_line" in payload["stack_trace"]


def test_exc_info_true_takes_the_same_path(capture_root_stream):
    """exc_info=True is the OTHER half of the enumerated set.

    backend/routes/editor_kit_routes.py uses `_log.warning(..., exc_info=True)`
    rather than `.exception(...)`. Both land in the same event dict key, so
    both must be scrubbed -- but "must" is not "is", and only a test that
    drives the exc_info=True shape specifically proves the processor does not
    special-case the .exception() path.
    """
    configure_logging()
    log = structlog.get_logger("test_error_shape")

    try:
        _raise_with_sentinel()
    except ValueError:
        log.warning("unit_test_exc_info_kwarg", exc_info=True)

    rendered = capture_root_stream.getvalue()
    assert SENTINEL not in rendered, (
        "exc_info=True leaked the exception message: " + rendered)
    payload = json.loads(rendered.strip().splitlines()[-1])
    assert "ValueError" in payload["stack_trace"]
    assert payload.get("error_type") == "ValueError"
    # A WARNING-level exception log stays WARNING; the processor must not
    # promote every traceback to ERROR (which would flood Error Reporting
    # with handled, expected conditions -- e.g. the readiness-lint warnings).
    assert payload.get("severity") == "WARNING", (
        "severity was rewritten: " + repr(payload.get("severity")))


def test_non_exception_lines_get_uppercase_severity_and_no_stack_trace(
        capture_root_stream):
    """A plain info line must not grow a stack_trace field.

    Error Reporting treats any entry carrying a stack_trace-shaped field as an
    error. Emitting one on every log line would turn routine INFO traffic into
    thousands of phantom errors.
    """
    configure_logging()
    log = structlog.get_logger("test_error_shape")
    log.info("unit_test_plain_line", count=3)

    payload = json.loads(
        capture_root_stream.getvalue().strip().splitlines()[-1])
    assert payload.get("severity") == "INFO"
    assert "stack_trace" not in payload
    assert "error_type" not in payload
    assert payload.get("count") == 3


def test_pii_safe_exception_info_is_pure_and_message_free():
    """The helper itself, called directly -- no logging plumbing involved.

    Keeps the guarantee testable without depending on the processor chain's
    wiring, so a wiring change cannot make this assertion vacuous.
    """
    try:
        _raise_with_sentinel()
    except ValueError as exc:
        info = pii_safe_exception_info(type(exc), exc, exc.__traceback__)

    assert info["error_type"] == "ValueError"
    assert SENTINEL not in json.dumps(info)
    assert "_raise_with_sentinel" in info["stack_trace"]
    assert "test_error_shape.py" in info["stack_trace"]


def test_pii_safe_exception_info_survives_a_chained_cause():
    """`raise X from Y` -- the cause's message must not leak either.

    Python's default traceback rendering walks __cause__ / __context__ and
    prints EVERY message in the chain. A scrubber that only handled the
    outermost exception would leak the inner one's, which in this app is
    exactly where a field value ends up (a low-level parse error wrapped in a
    domain error).
    """
    try:
        try:
            _raise_with_sentinel()
        except ValueError as inner:
            raise KeyError("outer failure") from inner
    except KeyError as exc:
        info = pii_safe_exception_info(type(exc), exc, exc.__traceback__)

    assert info["error_type"] == "KeyError"
    assert SENTINEL not in json.dumps(info), (
        "the CHAINED cause's message leaked: " + json.dumps(info))
    # The chain is still visible structurally -- the cause's TYPE is useful
    # for grouping and carries no user data.
    assert "ValueError" in info["stack_trace"], (
        "the chained cause vanished entirely; grouping loses the real "
        "origin: " + info["stack_trace"])


def _ast_exception_sites():
    """Every `.exception(...)` call and `exc_info=` kwarg under backend/.

    Derived from the AST rather than a grep so a multi-line call (the shape
    backend/services/validation_handler.py actually uses) is not missed, and
    so a hand-maintained list cannot drift from the tree.

    Scope mirrors backend/tests/unit/test_deployed_iam_envelope.py: everything
    under backend/ that SHIPS. Tests are excluded (a test may deliberately
    render an exception into an assertion message), backend/scripts/* are
    excluded (operator probes, same carve-out as scripts/), and
    backend/utils/logging.py itself is excluded -- it DEFINES the processor
    rather than calling a logger through it.
    """
    backend = REPO_ROOT / "backend"
    sites = set()
    for path in sorted(backend.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in rel or rel == "backend/utils/logging.py":
            continue
        if rel.startswith("backend/scripts/"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            is_exception_call = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "exception"
            )
            has_exc_info = any(kw.arg == "exc_info" for kw in node.keywords)
            if is_exception_call or has_exc_info:
                sites.add((rel, node.lineno))
    return sites


def test_the_ast_enumeration_actually_finds_sites():
    """Guard the guard.

    If the AST walk broke (a rename, a moved directory, an exclusion typo) it
    would return the empty set, and the register test below would pass
    vacuously forever while new leak sites landed unchecked.
    """
    sites = _ast_exception_sites()
    assert len(sites) >= 10, (
        "the AST enumeration found only {} exception-logging site(s) under "
        "backend/. That is far below the known population -- the walk is "
        "probably broken, not the tree.".format(len(sites)))


def test_every_exception_logging_site_is_enumerated():
    """The SET, pinned (CLAUDE.md scar #8).

    Every FILE that renders an exception through structlog is listed in
    backend/utils/logging.py's EXCEPTION_LOGGING_SITES. Adding one without
    updating that list fails HERE, which is the moment to ask whether the new
    site is safe -- rather than after it has shipped a field value to Cloud
    Logging.

    The list is a REGISTER, not a permission gate: every site routes through
    the one shared processor by construction (structlog has a single global
    chain), so the list's job is to make an addition VISIBLE, and to make the
    claim "all of them go through the safe processor" checkable by a reviewer
    against a real enumeration instead of against recall.
    """
    actual = {rel for rel, _ in _ast_exception_sites()}
    pinned = set(EXCEPTION_LOGGING_SITES)

    added = actual - pinned
    removed = pinned - actual

    assert not added, (
        "New exception-logging file(s) not in EXCEPTION_LOGGING_SITES: "
        + ", ".join(sorted(added))
        + ". Every such site renders through backend/utils/logging.py's "
        "pii_safe_exception_processor. Confirm the new site is PII-safe, then "
        "add it to that list.")
    assert not removed, (
        "EXCEPTION_LOGGING_SITES names file(s) that no longer log exceptions: "
        + ", ".join(sorted(removed))
        + ". Remove them so the register stays honest.")


def test_stock_format_exc_info_is_not_in_the_processor_chain():
    """The processor swap itself is pinned.

    Without this, someone re-adding structlog.processors.format_exc_info
    "to get tracebacks back" would restore the P0 leak while every other test
    in this file still passed -- the safe processor would run too, and its
    assertions are all about what IT emits.
    """
    configure_logging()
    chain = structlog.get_config()["processors"]
    names = [getattr(p, "__name__", type(p).__name__) for p in chain]
    try:
        assert "format_exc_info" not in names, (
            "structlog.processors.format_exc_info is back in the chain. It "
            "renders the exception MESSAGE (bd polyglot-pdf-p84m P0) -- use "
            "pii_safe_exception_processor instead. Chain: " + repr(names))
        assert "pii_safe_exception_processor" in names, (
            "the PII-safe exception processor is not in the chain -- "
            "exceptions render as exc_info: true with no trace at all. "
            "Chain: " + repr(names))
    finally:
        structlog.reset_defaults()
